from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from src import repair_provider_ledger
from src import runner_ledger_integration
from src.guarded_publish_runner import (
    DEFAULT_BACKUP_DIR,
    DEFAULT_CLEANUP_LOG_PATH,
    DEFAULT_HISTORY_PATH,
    DEFAULT_MAX_BURST,
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
    parser.add_argument(
        "--max-burst",
        type=int,
        default=DEFAULT_MAX_BURST,
        help="Per invocation publish cap (default 20, hard max 30).",
    )
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


def _history_file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _read_history_rows_from_offset(path: Path, start_offset: int) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(max(int(start_offset), 0))
        payload = handle.read()
    if not payload:
        return []
    rows: list[dict[str, object]] = []
    for raw_line in payload.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _post_body(post: dict[str, object]) -> str:
    content = post.get("content")
    if isinstance(content, dict):
        return str(content.get("raw") or content.get("rendered") or "")
    return ""


def _backup_body(path_value: object) -> str:
    if not path_value:
        return ""
    payload = json.loads(Path(str(path_value)).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if isinstance(content, dict):
        return str(content.get("raw") or content.get("rendered") or "")
    return ""


def _ledger_status(row: dict[str, object]) -> str:
    status = str(row.get("status") or "").strip()
    hold_reason = str(row.get("hold_reason") or "").strip()
    if status == "sent":
        return "success"
    if hold_reason in {"cleanup_failed_post_condition", "publish_failed", "cleanup_backup_failed"}:
        return "failed"
    return "skipped"


def _persist_guarded_publish_ledger(
    *,
    sink: runner_ledger_integration.BestEffortLedgerSink,
    history_path: Path,
    start_offset: int,
) -> None:
    if not sink.enabled:
        return

    rows = _read_history_rows_from_offset(history_path, start_offset)
    if not rows:
        return

    wp = None

    def get_wp() -> WPClient:
        nonlocal wp
        if wp is None:
            wp = _make_wp_client()
        return wp

    for row in rows:
        post_id = int(row.get("post_id") or 0)
        before_body = ""
        after_body = ""
        try:
            before_body = _backup_body(row.get("backup_path"))
        except Exception as exc:
            print(f"[ledger] warning: failed to read backup post_id={post_id}: {exc}", file=sys.stderr)
        try:
            current_post = get_wp().get_post(post_id)
            after_body = _post_body(current_post)
        except Exception as exc:
            print(f"[ledger] warning: failed to fetch current post_id={post_id}: {exc}", file=sys.stderr)
        if not before_body:
            before_body = after_body

        judgment = str(row.get("judgment") or "").strip()
        row_status = str(row.get("status") or "").strip()
        hold_reason = str(row.get("hold_reason") or "").strip()
        quality_flags = ["guarded_publish", judgment, row_status]
        if bool(row.get("cleanup_required")):
            quality_flags.append("cleanup_required")
        if row.get("cleanup_success") is False:
            quality_flags.append("cleanup_failed")

        entry = runner_ledger_integration.build_entry(
            lane="guarded_publish",
            provider="gemini",
            model="guarded-publish-runner",
            source_post_id=post_id,
            before_body=before_body,
            after_body=after_body,
            status=_ledger_status(row),
            error_code=hold_reason or str(row.get("error") or "").strip() or None,
            quality_flags=quality_flags,
            fallback_reason=str(row.get("error") or "").strip() or None,
            input_payload={
                "lane": "guarded_publish",
                "history_row": row,
            },
            artifact_uri=str(row.get("backup_path") or "memory://guarded_publish"),
        )
        sink.persist(
            entry,
            before_body=before_body,
            after_body=after_body,
            extra_meta={"history_row": row},
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _load_dotenv_if_available()
    history_path = Path(args.history_path)
    ledger_sink = runner_ledger_integration.BestEffortLedgerSink(
        collection_name=repair_provider_ledger.DEFAULT_FIRESTORE_COLLECTION,
        fallback_path=repair_provider_ledger.resolve_jsonl_ledger_path(),
    )
    history_offset = _history_file_size(history_path) if args.live and ledger_sink.enabled else 0
    try:
        report = run_guarded_publish(
            input_from=args.input_from,
            live=args.live,
            max_burst=args.max_burst,
            daily_cap_allow=args.daily_cap_allow,
            backup_dir=args.backup_dir,
            history_path=history_path,
            yellow_log_path=args.yellow_log_path,
            cleanup_log_path=args.cleanup_log_path,
        )
    except (GuardedPublishAbortError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.live:
        _persist_guarded_publish_ledger(
            sink=ledger_sink,
            history_path=history_path,
            start_offset=history_offset,
        )
    _emit_output(dump_guarded_publish_report(report, fmt=args.format), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
