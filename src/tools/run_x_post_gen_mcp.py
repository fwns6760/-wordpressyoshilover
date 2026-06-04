"""Tavily MCP + Gemini Flash Lite で巨人関連 X 投稿案を生成する CLI runner。

実行例:
    export GEMINI_API_KEY=...
    export TAVILY_API_KEY=...
    python -m src.tools.run_x_post_gen_mcp

    # 量を絞って smoke:
    python -m src.tools.run_x_post_gen_mcp --max-queries 2

    # JSON で吐く:
    python -m src.tools.run_x_post_gen_mcp --output json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Sequence

from src.x_post_gen_mcp import (
    DEFAULT_QUERIES,
    GEMMA_MODEL_ID,
    PostDraft,
    generate_post_drafts_sync,
)

LOG = logging.getLogger("x_post_gen_mcp")


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate X post drafts about the 巨人 using Tavily MCP (stdio) "
            "+ Gemini Flash Lite via Gemini API free tier."
        ),
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=5,
        help=(
            "Maximum queries to run (default 5). Each query = 1 Tavily search "
            "= 1 credit. Free tier is 1000 credits/month."
        ),
    )
    parser.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help=(
            "Explicit query list (overrides DEFAULT_QUERIES). Space-separated, "
            "Japanese ok."
        ),
    )
    parser.add_argument(
        "--model",
        default=GEMMA_MODEL_ID,
        help=f"Gemini API model id (default {GEMMA_MODEL_ID}).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.6,
        help="Generation temperature (default 0.6).",
    )
    parser.add_argument(
        "--output",
        choices=("stdout", "json"),
        default="stdout",
        help="Output format (default stdout).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print resolved queries and exit without calling Tavily/Gemini. "
            "$0 cost smoke."
        ),
    )
    return parser.parse_args(argv)


def _render_stdout(drafts: list[PostDraft]) -> str:
    parts: list[str] = []
    for draft in drafts:
        parts.append(f"=== query: {draft.query} ===")
        parts.append(f"model: {draft.model}")
        if draft.error:
            parts.append(f"ERROR: {draft.error}")
        else:
            parts.append(draft.draft if draft.draft else "(empty)")
        parts.append("")
    return "\n".join(parts)


def _render_json(drafts: list[PostDraft]) -> str:
    return json.dumps(
        [
            {
                "query": d.query,
                "model": d.model,
                "draft": d.draft,
                "error": d.error,
            }
            for d in drafts
        ],
        ensure_ascii=False,
        indent=2,
    )


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)

    if args.queries is not None:
        queries = list(args.queries)
    else:
        queries = list(DEFAULT_QUERIES)[: args.max_queries]

    if args.dry_run:
        LOG.info("[dry-run] queries=%s model=%s", queries, args.model)
        # dry-run は credentials を要求しない (cost = 0 を確認するため)
        return 0

    gemini_api_key = (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    )
    tavily_api_key = os.environ.get("TAVILY_API_KEY") or ""
    if not gemini_api_key:
        LOG.error(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) env var is required. "
            "Get one free at https://ai.google.dev/"
        )
        return 2
    if not tavily_api_key:
        LOG.error(
            "TAVILY_API_KEY env var is required. "
            "Get one free at https://tavily.com/"
        )
        return 2

    LOG.info(
        "Generating drafts: queries=%d model=%s temperature=%.2f",
        len(queries),
        args.model,
        args.temperature,
    )
    try:
        drafts = generate_post_drafts_sync(
            gemini_api_key=gemini_api_key,
            tavily_api_key=tavily_api_key,
            queries=queries,
            model=args.model,
            temperature=args.temperature,
        )
    except ImportError as exc:
        LOG.error(
            "Missing dependency: %s. Install with: "
            "pip install google-genai fastmcp",
            exc,
        )
        return 3
    except FileNotFoundError as exc:
        LOG.error(
            "Node.js / npx not found (Tavily MCP requires Node): %s. "
            "Install Node.js 20+ first.",
            exc,
        )
        return 4

    if args.output == "json":
        sys.stdout.write(_render_json(drafts) + "\n")
    else:
        sys.stdout.write(_render_stdout(drafts))

    error_count = sum(1 for d in drafts if d.error)
    LOG.info(
        "done: drafts=%d errors=%d",
        len(drafts),
        error_count,
    )
    return 0 if error_count == 0 else 5


if __name__ == "__main__":
    sys.exit(main())
