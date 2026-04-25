from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from src.guarded_publish_evaluator import dump_report, scan_wp_drafts
from src.wp_client import WPClient


ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _make_wp_client() -> WPClient:
    _load_dotenv_if_available()
    return WPClient()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_guarded_publish_evaluator",
        description="Read-only guarded publish evaluator dry-run for WordPress drafts.",
    )
    parser.add_argument("--window-hours", type=int, default=96, help="Only evaluate drafts modified within this many hours.")
    parser.add_argument("--max-pool", type=int, default=100, help="Maximum draft pool to scan (clamped to 100).")
    parser.add_argument("--format", choices=("json", "human"), default="json", help="Output format.")
    parser.add_argument("--output", help="Write output to this path instead of stdout.")
    parser.add_argument(
        "--exclude-published-today",
        action="store_true",
        help="Exclude drafts whose normalized title or game key matches a post already published today.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.window_hours < 0:
        print("--window-hours must be >= 0", file=sys.stderr)
        return 1
    if args.max_pool <= 0:
        print("--max-pool must be > 0", file=sys.stderr)
        return 1

    wp_client = _make_wp_client()
    report = scan_wp_drafts(
        wp_client,
        window_hours=args.window_hours,
        max_pool=args.max_pool,
        exclude_published_today=args.exclude_published_today,
    )
    rendered = dump_report(report, fmt=args.format)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
