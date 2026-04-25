"""Dry-run CLI for PUB-005-A2 X post template candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from src.wp_client import WPClient
from src.x_published_poster import PublishedArticle
from src.x_post_template_candidates import (
    generate_template_candidates,
    load_template_candidate_history,
    record_template_candidate_history,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate dry-run X post template candidates for a published WP article.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--post-id", type=int, help="Published WordPress post ID to fetch read-only.")
    source_group.add_argument("--fixture", help="Path to a JSON fixture containing one article payload.")
    parser.add_argument("--history", help="Optional post history JSON used to refuse duplicate post_id entries.")
    parser.add_argument(
        "--record-history",
        action="store_true",
        help="Write the accepted post_id to the history file after rendering candidates.",
    )
    return parser.parse_args(argv)


def _extract_rendered(value: Any) -> str:
    if isinstance(value, dict):
        rendered = value.get("rendered")
        if rendered is not None:
            return str(rendered)
    if value is None:
        return ""
    return str(value)


def _extract_first_paragraph(value: str) -> str:
    text = str(value or "")
    start = text.find("<p")
    if start < 0:
        return text
    end = text.find("</p>", start)
    if end < 0:
        return text
    return text[start : end + 4]


def _article_from_wp_post(payload: dict[str, Any]) -> PublishedArticle:
    return PublishedArticle(
        article_id=payload.get("id") or "",
        title=_extract_rendered(payload.get("title")),
        excerpt=_extract_rendered(payload.get("excerpt")),
        body_first_paragraph=_extract_first_paragraph(_extract_rendered(payload.get("content"))),
        canonical_url=str(payload.get("link") or ""),
        published_at=payload.get("date") or payload.get("date_gmt"),
        post_status=str(payload.get("status") or ""),
    )


def _load_fixture_article(path: str) -> PublishedArticle:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("articles"), list):
        items = payload["articles"]
    elif isinstance(payload, dict) and isinstance(payload.get("article"), dict):
        items = [payload["article"]]
    elif isinstance(payload, dict):
        items = [payload]
    else:
        raise ValueError("fixture JSON must contain one article payload")

    if len(items) != 1:
        raise ValueError("fixture JSON must contain exactly one article payload")
    if not isinstance(items[0], dict):
        raise ValueError("fixture article payload must be a JSON object")
    return PublishedArticle.from_mapping(items[0])


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        history = load_template_candidate_history(args.history) if args.history else {}

        if args.fixture:
            article = _load_fixture_article(args.fixture)
        else:
            post = WPClient().get_post(args.post_id)
            article = _article_from_wp_post(post)

        batch = generate_template_candidates(article, post_history=history)
        print(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2))

        if args.record_history and args.history and batch.accepted:
            record_template_candidate_history(args.history, history, batch.post_id, posted_at=batch.generated_at)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
