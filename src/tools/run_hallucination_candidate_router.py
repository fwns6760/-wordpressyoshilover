from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from src import hallucination_candidate_router as router


def _parse_priorities(value: str | None) -> tuple[str, ...]:
    if value is None or not str(value).strip():
        return router.VALID_PRIORITIES
    priorities = tuple(part.strip().lower() for part in str(value).split(",") if part.strip())
    if not priorities:
        return router.VALID_PRIORITIES
    invalid = [priority for priority in priorities if priority not in router.VALID_PRIORITIES]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid priorities: {', '.join(invalid)} (expected subset of {', '.join(router.VALID_PRIORITIES)})"
        )
    return priorities


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_hallucination_candidate_router",
        description="Rule-based HALLUC candidate router (dry-run only, no Gemini calls).",
    )
    parser.add_argument("--history", default=str(router.DEFAULT_HISTORY_PATH), help="guarded publish history JSONL path")
    parser.add_argument(
        "--yellow-log",
        default=str(router.DEFAULT_YELLOW_LOG_PATH),
        help="guarded publish yellow log JSONL path",
    )
    parser.add_argument("--output", help="write output to this path instead of stdout")
    parser.add_argument("--dry-run", action="store_true", help="explicit dry-run marker; this tool is read-only only")
    parser.add_argument("--max-candidates", type=int, default=router.DEFAULT_MAX_CANDIDATES, help="maximum candidates")
    parser.add_argument("--priority", type=_parse_priorities, help="comma-separated priority filter")
    parser.add_argument("--format", choices=("json", "tsv"), default="json", help="output format")
    return parser.parse_args(argv)


def _emit_output(text: str, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = router.build_hallucination_candidate_report(
        history_path=args.history,
        yellow_log_path=args.yellow_log,
        max_candidates=args.max_candidates,
        priorities=args.priority,
    )
    _emit_output(router.dump_hallucination_candidate_report(report, fmt=args.format), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
