from __future__ import annotations

import argparse
import sys
from typing import Sequence

from src.sns_topic_publish_bridge import dump_sns_topic_publish_bridge_report, run_sns_topic_publish_bridge


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_sns_topic_publish_bridge",
        description="Bridge 127 SNS topic draft_ready proposals into the PUB-004 evaluator/runner gate.",
    )
    parser.add_argument("--fixture", required=True, help="Path to the 127 source recheck JSON output.")
    parser.add_argument(
        "--max-burst",
        type=int,
        default=20,
        help="Per invocation publish cap (default 20, hard max 30).",
    )
    parser.add_argument("--live", action="store_true", help="Enable live guarded runner execution against mock drafts.")
    parser.add_argument(
        "--daily-cap-allow",
        action="store_true",
        help="Explicit confirmation that the JST daily cap has been checked.",
    )
    parser.add_argument("--format", choices=("json", "human"), default="json", help="Output format.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = run_sns_topic_publish_bridge(
            fixture_path=args.fixture,
            live=args.live,
            max_burst=args.max_burst,
            daily_cap_allow=args.daily_cap_allow,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    sys.stdout.write(dump_sns_topic_publish_bridge_report(report, fmt=args.format))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
