from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from src.guarded_publish_runner import (
    DEFAULT_BACKUP_DIR,
    DEFAULT_CLEANUP_LOG_PATH,
    DEFAULT_HISTORY_PATH,
    DEFAULT_YELLOW_LOG_PATH,
    GuardedPublishAbortError,
    dump_guarded_publish_report,
    run_guarded_publish,
)
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
        prog="python3 -m src.tools.run_guarded_publish",
        description="PUB-004-B guarded publish runner (dry-run default, live publish gated).",
    )
    parser.add_argument("--input-from", required=True, help="PUB-004-A evaluator JSON path.")
    parser.add_argument("--max-burst", type=int, required=True, help="Per invocation publish cap (hard max 3).")
    parser.add_argument("--format", choices=("json", "human"), default="json", help="Output format.")
    parser.add_argument("--output", help="Write output to this path instead of stdout.")
    parser.add_argument("--live", action="store_true", help="Enable live WordPress write path.")
    parser.add_argument(
        "--daily-cap-allow",
        action="store_true",
        help="Explicit confirmation that the JST daily cap has been checked.",
    )
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="Backup root directory.")
    parser.add_argument("--history-path", default=str(DEFAULT_HISTORY_PATH), help="History JSONL path.")
    parser.add_argument("--yellow-log-path", default=str(DEFAULT_YELLOW_LOG_PATH), help="Yellow publish log JSONL path.")
    parser.add_argument(
        "--cleanup-log-path",
        default=str(DEFAULT_CLEANUP_LOG_PATH),
        help="Cleanup publish log JSONL path.",
    )
    return parser.parse_args(argv)


def _emit_output(text: str, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _load_dotenv_if_available()
    try:
        report = run_guarded_publish(
            input_from=args.input_from,
            live=args.live,
            max_burst=args.max_burst,
            daily_cap_allow=args.daily_cap_allow,
            backup_dir=args.backup_dir,
            history_path=args.history_path,
            yellow_log_path=args.yellow_log_path,
            cleanup_log_path=args.cleanup_log_path,
        )
    except (GuardedPublishAbortError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_output(dump_guarded_publish_report(report, fmt=args.format), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
