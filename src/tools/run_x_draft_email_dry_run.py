"""Dry-run CLI for ticket 065 X draft email digest content."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.x_draft_email_digest import build_x_draft_email_digest, format_digest_human, format_digest_json


DEFAULT_FIXTURE: list[dict[str, Any]] = [
    {
        "news_family": "試合結果",
        "entity_primary": "巨人",
        "event_nucleus": "巨人 3-2 阪神 試合結果",
        "recommended_account": "official",
        "source_tier": "fact",
        "safe_fact": "巨人が阪神に3-2で勝利しました。",
        "title": "巨人、阪神に3-2で勝利",
        "published_url": "https://yoshilover.com/archives/065-sample-postgame/",
        "source_ref": "https://www.giants.jp/game/20260423/result/",
    },
    {
        "news_family": "コメント",
        "entity_primary": "阿部監督",
        "event_nucleus": "試合後コメント 話題",
        "recommended_account": "inner",
        "source_tier": "topic",
        "topic": "阿部監督の試合後コメント",
        "title": "阿部監督の試合後コメントが話題に",
        "published_url": "https://yoshilover.com/archives/065-sample-comment/",
        "source_ref": "https://x.com/hochi_giants/status/1234567890",
    },
]


def _load_fixture(path: str | None) -> list[dict[str, Any]]:
    if path is None:
        return list(DEFAULT_FIXTURE)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict) and isinstance(payload.get("articles"), list):
        return [dict(item) for item in payload["articles"]]
    raise ValueError("fixture must be a list or an object with an 'articles' list")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render one X draft email digest body without sending mail.")
    parser.add_argument("--fixture", help="Path to JSON fixture. Defaults to built-in sample fixture.")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--include-warnings", dest="include_warnings", action="store_true", default=True)
    parser.add_argument("--no-include-warnings", dest="include_warnings", action="store_false")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    articles = _load_fixture(args.fixture)
    result = build_x_draft_email_digest(
        articles,
        max_candidates=args.max_candidates,
        include_warnings=args.include_warnings,
    )
    if args.format == "json":
        print(format_digest_json(result, include_warnings=args.include_warnings))
    else:
        print(format_digest_human(result, include_warnings=args.include_warnings))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
