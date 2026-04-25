from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIMIT = 50


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


def scan_wp_published_posts(*args, **kwargs):
    from src.published_site_component_audit import scan_wp_published_posts as impl

    return impl(*args, **kwargs)


def write_report(*args, **kwargs):
    from src.published_site_component_audit import write_report as impl

    return impl(*args, **kwargs)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_published_site_component_audit",
        description="Read-only audit for published posts with site component / heading / dev-log cleanup candidates.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of published posts to audit.")
    parser.add_argument("--orderby", default="modified", help="WordPress orderby value. Default: modified.")
    parser.add_argument("--order", choices=("asc", "desc"), default="desc", help="WordPress order direction.")
    parser.add_argument("--format", choices=("json", "human"), default="human", help="Output format.")
    parser.add_argument("--output", help="Write the rendered report to this path instead of stdout.")
    parser.add_argument(
        "--include-todays-publishes",
        action="store_true",
        help="Include posts published today instead of filtering them out.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = scan_wp_published_posts(
            _make_wp_client(),
            limit=args.limit,
            orderby=args.orderby,
            order=args.order,
            include_todays_publishes=args.include_todays_publishes,
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
