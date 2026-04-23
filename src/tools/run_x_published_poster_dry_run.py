"""Dry-run CLI for ticket 061-P1.1 published-article teaser generation."""

from __future__ import annotations

import argparse
import json
import sys

from src.x_published_poster import (
    PublishedArticle,
    build_post,
    generate_teaser,
    load_post_history,
    record_post_history,
    validate_post,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render published-article X post candidates without sending anything.")
    parser.add_argument("--input", help="Path to a JSON fixture. If omitted, JSON is read from stdin.")
    parser.add_argument(
        "--history",
        help="Optional JSON history file used for the 24h duplicate guard. Accepted posts are written back.",
    )
    return parser.parse_args(argv)


def _load_articles(input_path: str | None) -> list[PublishedArticle]:
    if input_path:
        with open(input_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("missing input JSON")
        payload = json.loads(raw)

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("articles"), list):
        items = payload["articles"]
    else:
        raise ValueError("input JSON must be a list or an object with an 'articles' list")

    return [PublishedArticle.from_mapping(dict(item)) for item in items]


def _format_ok(article_id: str | int, teaser: str, canonical_url: str) -> str:
    return f"[ok]   post_id={article_id}  teaser={json.dumps(teaser, ensure_ascii=False)}  url={canonical_url}"


def _format_skip(article_id: str | int, reason: str | None) -> str:
    return f"[skip] post_id={article_id}  reason={reason or 'UNKNOWN'}"


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        articles = _load_articles(args.input)
        history = load_post_history(args.history)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for article in articles:
        payload = build_post(article, post_history=history)
        if payload is not None:
            print(_format_ok(payload.article_id, payload.teaser, payload.canonical_url))
            if args.history:
                record_post_history(args.history, history, payload.article_id, posted_at=payload.published_at)
            else:
                history[str(payload.article_id)] = payload.published_at.isoformat()
            continue

        teaser = generate_teaser(article)
        validation = validate_post(article, teaser, article.canonical_url, post_history=history)
        print(_format_skip(article.article_id, validation.hard_fail_code))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
