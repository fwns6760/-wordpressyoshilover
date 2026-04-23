"""Manual CLI for the 048 repair playbook ledger aggregator."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from src.repair_playbook import aggregate_fail_tags, format_promotion_summary


def _parse_now(raw_value: str | None) -> datetime:
    if not raw_value:
        return datetime.now(timezone.utc)
    value = raw_value.strip()
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate 038 ledger fail_tags for 048 promotion review")
    parser.add_argument("--aggregate", action="store_true", help="run the read-only ledger aggregation")
    parser.add_argument("--ledger-dir", type=Path, required=True, help="directory or file containing JSON/JSONL ledger records")
    parser.add_argument("--window", choices=("24h", "7d", "all"), default="all", help="filter formatted output by window")
    parser.add_argument("--now", help="ISO timestamp used as the aggregation clock; defaults to current UTC time")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.aggregate:
        raise SystemExit("--aggregate is required")

    candidates = aggregate_fail_tags(args.ledger_dir, now=_parse_now(args.now))
    if args.window != "all":
        candidates = [candidate for candidate in candidates if candidate.window == args.window]
    print(format_promotion_summary(candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
