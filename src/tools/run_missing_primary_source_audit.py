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


def scan_wp_drafts(*args, **kwargs):
    from src.missing_primary_source_recovery import scan_wp_drafts as impl

    return impl(*args, **kwargs)


def write_report(*args, **kwargs):
    from src.missing_primary_source_recovery import write_report as impl

    return impl(*args, **kwargs)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_missing_primary_source_audit",
        description="Read-only audit for missing primary source blockers in recent WordPress drafts.",
    )
    parser.add_argument("--window-hours", type=int, default=96, help="Audit drafts modified within this many hours.")
    parser.add_argument("--max-pool", type=int, default=200, help="Maximum number of recent draft posts to scan.")
    parser.add_argument("--format", choices=("json", "human"), default="human", help="Output format.")
    parser.add_argument("--output", help="Write the rendered report to this path instead of stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = scan_wp_drafts(
            _make_wp_client(),
            window_hours=args.window_hours,
            max_pool=args.max_pool,
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
