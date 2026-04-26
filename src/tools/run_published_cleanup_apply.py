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


def run_published_cleanup_apply(*args, **kwargs):
    from src.published_cleanup_apply_runner import run_published_cleanup_apply as impl

    return impl(*args, **kwargs)


def dump_report(*args, **kwargs):
    from src.published_cleanup_apply_runner import dump_report as impl

    return impl(*args, **kwargs)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    from src.published_cleanup_apply_runner import DEFAULT_MAX_BURST

    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_published_cleanup_apply",
        description="Apply published cleanup proposals to already-published WordPress posts.",
    )
    parser.add_argument("--proposals-from", required=True, help="Path to the 153 cleanup proposals JSON.")
    parser.add_argument("--max-burst", type=int, default=DEFAULT_MAX_BURST, help="Maximum proposal rows to process.")
    parser.add_argument("--live", action="store_true", help="Actually update WP content after backup + verify.")
    parser.add_argument("--format", choices=("json", "human"), default="human", help="Output format.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        report = run_published_cleanup_apply(
            args.proposals_from,
            wp_client=_make_wp_client(),
            max_burst=args.max_burst,
            live=args.live,
        )
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    sys.stdout.write(dump_report(report, fmt=args.format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
