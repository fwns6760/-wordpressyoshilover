from __future__ import annotations

import argparse
import sys
from typing import Sequence

from src.guarded_publish_readiness_guard import DEFAULT_HISTORY_PATH, dump_report, evaluate_guarded_publish_readiness


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_guarded_publish_readiness_check",
        description="Read-only history audit for guarded publish readiness and regression signals.",
    )
    parser.add_argument(
        "--history-path",
        default=str(DEFAULT_HISTORY_PATH),
        help="Guarded publish history JSONL path.",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Look-back window in hours (default 24).",
    )
    parser.add_argument("--format", choices=("json", "human"), default="json", help="Output format.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = evaluate_guarded_publish_readiness(
            args.history_path,
            window_hours=args.window_hours,
        )
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    sys.stdout.write(dump_report(report, fmt=args.format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
