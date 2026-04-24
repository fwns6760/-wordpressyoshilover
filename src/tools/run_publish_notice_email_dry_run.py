"""Dry-run CLI for ticket 076 publish notice mail."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

if __package__ in {None, ""}:  # pragma: no cover - direct script execution support
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src.publish_notice_email_sender import (  # noqa: E402
    PublishNoticeRequest,
    send,
)
from src.publish_notice_scanner import _append_queue_log, scan  # noqa: E402


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan or send one publish notice mail in dry-run by default.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--scan", action="store_true", help="Scan published WP posts and send emitted notices.")
    source.add_argument("--input", help="Path to one JSON fixture.")
    source.add_argument("--stdin", action="store_true", help="Read one JSON fixture from stdin.")
    parser.add_argument("--send", action="store_true", help="Actually send mail. Default is dry-run.")
    parser.add_argument("--send-enabled", action="store_true", help="Force enable real send gate.")
    parser.add_argument("--cursor-path", default="logs/publish_notice_cursor.txt")
    parser.add_argument("--history-path", default="logs/publish_notice_history.json")
    parser.add_argument("--queue-path", default="logs/publish_notice_queue.jsonl")
    return parser.parse_args(argv)


def _read_payload_from_path(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("fixture must be a JSON object")
    return payload


def _read_payload_from_stdin() -> dict[str, Any]:
    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        raise TypeError("fixture must be a JSON object")
    return payload


def _request_from_payload(payload: dict[str, Any]) -> PublishNoticeRequest:
    return PublishNoticeRequest(
        post_id=payload["post_id"],
        title=str(payload["title"]),
        canonical_url=str(payload["canonical_url"]),
        subtype=str(payload["subtype"]),
        publish_time_iso=str(payload["publish_time_iso"]),
        summary=None if payload.get("summary") is None else str(payload.get("summary")),
    )


def _queue_result(queue_path: str | Path, request: PublishNoticeRequest, status: str, reason: str | None, subject: str, recipients: list[str]) -> None:
    _append_queue_log(
        queue_path,
        status=status,
        reason=reason,
        subject=subject,
        recipients=recipients,
        post_id=request.post_id,
        recorded_at_iso=str(request.publish_time_iso or ""),
    )


def _print_result(request: PublishNoticeRequest, result: Any) -> None:
    print(
        f"[result] post_id={request.post_id} status={result.status} reason={result.reason} "
        f"subject={result.subject!r} recipients={result.recipients}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        send_enabled = args.send_enabled or str(os.environ.get("PUBLISH_NOTICE_EMAIL_ENABLED", "")).strip() == "1"
        dry_run = not args.send

        if args.scan:
            result = scan(
                cursor_path=args.cursor_path,
                history_path=args.history_path,
                queue_path=args.queue_path,
            )
            print(
                f"[scan] emitted={len(result.emitted)} skipped={len(result.skipped)} "
                f"cursor_before={result.cursor_before} cursor_after={result.cursor_after}"
            )
            for post_id, reason in result.skipped:
                print(f"[skip] post_id={post_id} reason={reason}")
            for request in result.emitted:
                mail_result = send(
                    request,
                    dry_run=dry_run,
                    send_enabled=send_enabled,
                )
                _queue_result(
                    args.queue_path,
                    request,
                    mail_result.status,
                    mail_result.reason,
                    mail_result.subject,
                    mail_result.recipients,
                )
                _print_result(request, mail_result)
            return 0

        if args.stdin:
            payload = _read_payload_from_stdin()
        else:
            payload = _read_payload_from_path(str(args.input))
        request = _request_from_payload(payload)
        result = send(
            request,
            dry_run=dry_run,
            send_enabled=send_enabled,
        )
        _queue_result(args.queue_path, request, result.status, result.reason, result.subject, result.recipients)
        _print_result(request, result)
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[result] status=error error_type={type(exc).__name__} message={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
