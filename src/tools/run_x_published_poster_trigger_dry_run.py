"""Dry-run CLI for ticket 061-P1.2 published-article polling trigger."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from src.x_published_poster import PublishedArticle
from src.x_published_poster_trigger import (
    fetch_published_since_wp,
    load_cursor,
    scan_and_queue,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll published WP posts and enqueue dry-run X post payloads.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--fixture", help="Path to a JSON fixture containing published-article payloads.")
    source_group.add_argument("--wp-url", help="Base WordPress URL used for read-only public REST polling.")
    parser.add_argument("--cursor", default="logs/x_published_poster_cursor.txt")
    parser.add_argument("--queue", default="logs/x_published_poster_queue.jsonl")
    parser.add_argument("--history", default="logs/x_published_poster_history.json")
    return parser.parse_args(argv)


def _load_fixture_articles(path: str) -> list[PublishedArticle]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("articles"), list):
        items = payload["articles"]
    else:
        raise ValueError("fixture JSON must be a list or an object with an 'articles' list")
    return [PublishedArticle.from_mapping(dict(item)) for item in items]


def _format_ok(entry: dict[str, object]) -> str:
    return (
        f"[ok]   post_id={entry['article_id']}  teaser={json.dumps(entry['teaser'], ensure_ascii=False)}  "
        f"url={entry['canonical_url']}"
    )


def _format_skip(article_id: str | int, reason: str) -> str:
    return f"[skip] post_id={article_id}  reason={reason}"


def _default_since_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        cursor_path = Path(args.cursor)
        queue_path = Path(args.queue)
        history_path = Path(args.history)
        since_iso = load_cursor(cursor_path) or _default_since_iso()

        queue_before = 0
        if queue_path.exists():
            queue_before = sum(1 for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip())

        if args.fixture:
            articles = _load_fixture_articles(args.fixture)

            def fetch_fn(_: str) -> list[PublishedArticle]:
                return list(articles)

        else:

            def fetch_fn(since: str) -> list[PublishedArticle]:
                return fetch_published_since_wp(args.wp_url, since)

        result = scan_and_queue(fetch_fn, cursor_path, queue_path, history_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"[detect] {result.detected} new posts (since={since_iso})")

    queued_entries = []
    if queue_path.exists():
        lines = [line for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines[queue_before:]:
            queued_entries.append(json.loads(line))

    for entry in queued_entries:
        print(_format_ok(entry))
    for article_id, reason in result.skipped:
        print(_format_skip(article_id, reason))
    print(
        f"[done] detected={result.detected} ok={result.ok} skipped={len(result.skipped)} "
        f"new_cursor={result.new_cursor}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
