from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _make_wp_client():
    _load_dotenv_if_available()
    from src.wp_client import WPClient

    return WPClient()


def generate_cleanup_proposals(*args, **kwargs):
    from src.published_cleanup_proposals import generate_cleanup_proposals as impl

    return impl(*args, **kwargs)


def write_report(*args, **kwargs):
    from src.published_cleanup_proposals import write_report as impl

    return impl(*args, **kwargs)


def _parse_post_ids(value: str) -> list[int]:
    post_ids: list[int] = []
    for token in (value or "").split(","):
        normalized = token.strip()
        if not normalized:
            continue
        post_ids.append(int(normalized))
    if not post_ids:
        raise ValueError("--post-ids requires at least one numeric id")
    return post_ids


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    from src.published_cleanup_proposals import DEFAULT_HISTORY_PATH

    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_published_cleanup_proposals",
        description="Read-only cleanup proposal audit for published posts using WP GET plus publish history fallback.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--post-ids", help="Comma-separated published WordPress post IDs.")
    group.add_argument("--from-history", type=int, help="Use the most recent N sent post_ids from today's publish history.")
    parser.add_argument("--history-path", default=str(DEFAULT_HISTORY_PATH), help="Guarded publish history JSONL path.")
    parser.add_argument("--format", choices=("json", "human"), default="human", help="Output format.")
    parser.add_argument("--output", help="Write the rendered report to this path instead of stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        post_ids = _parse_post_ids(args.post_ids) if args.post_ids else None
        report = generate_cleanup_proposals(
            _make_wp_client(),
            post_ids=post_ids,
            from_history=args.from_history,
            history_path=args.history_path,
        )
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    rendered = write_report(report, fmt=args.format, output_path=args.output)
    if not args.output:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
