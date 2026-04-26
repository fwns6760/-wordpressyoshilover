"""Dry-run CLI for ticket 076 publish notice mail."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from dotenv import load_dotenv

if __package__ in {None, ""}:  # pragma: no cover - direct script execution support
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src.publish_notice_email_sender import (  # noqa: E402
    AlertMailRequest,
    BurstSummaryEntry,
    BurstSummaryRequest,
    DEFAULT_DAILY_CAP,
    DEFAULT_SUMMARY_EVERY,
    EmergencyMailRequest,
    PublishNoticeRequest,
    build_burst_summary_requests,
    build_emergency_subject,
    emit_emergency_hook,
    send,
    send_alert,
    send_summary,
)
from src.publish_notice_scanner import JST, scan  # noqa: E402


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
    parser.add_argument("--summary-every", type=int, default=DEFAULT_SUMMARY_EVERY)
    parser.add_argument("--daily-cap", type=int, default=DEFAULT_DAILY_CAP)
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


def _summary_entry_from_request(request: PublishNoticeRequest) -> BurstSummaryEntry:
    return BurstSummaryEntry(
        post_id=request.post_id,
        title=request.title,
        category=request.subtype,
        publishable=True,
        cleanup_required=False,
        cleanup_success=None,
    )


def _summary_request_from_payload(payload: dict[str, Any]) -> BurstSummaryRequest:
    entries = [
        BurstSummaryEntry(
            post_id=entry["post_id"],
            title=str(entry["title"]),
            category=str(entry.get("category") or "unknown"),
            publishable=bool(entry.get("publishable")),
            cleanup_required=bool(entry.get("cleanup_required")),
            cleanup_success=entry.get("cleanup_success"),
        )
        for entry in payload.get("entries") or []
    ]
    return BurstSummaryRequest(
        entries=entries,
        cumulative_published_count=int(payload["cumulative_published_count"]),
        daily_cap=int(payload.get("daily_cap", DEFAULT_DAILY_CAP)),
        hard_stop_count=int(payload.get("hard_stop_count", 0)),
        hold_count=int(payload.get("hold_count", 0)),
    )


def _alert_request_from_payload(payload: dict[str, Any]) -> AlertMailRequest:
    return AlertMailRequest(
        alert_type=str(payload["alert_type"]),
        post_id=payload.get("post_id"),
        title=None if payload.get("title") is None else str(payload.get("title")),
        category=None if payload.get("category") is None else str(payload.get("category")),
        reason=None if payload.get("reason") is None else str(payload.get("reason")),
        detail=None if payload.get("detail") is None else str(payload.get("detail")),
        publishable=payload.get("publishable"),
        cleanup_required=payload.get("cleanup_required"),
        cleanup_success=payload.get("cleanup_success"),
        hold_reason=None if payload.get("hold_reason") is None else str(payload.get("hold_reason")),
    )


def _emergency_request_from_payload(payload: dict[str, Any]) -> EmergencyMailRequest:
    return EmergencyMailRequest(
        post_id=payload.get("post_id"),
        title=None if payload.get("title") is None else str(payload.get("title")),
        reason=None if payload.get("reason") is None else str(payload.get("reason")),
        detail=None if payload.get("detail") is None else str(payload.get("detail")),
    )


def _queue_result(
    queue_path: str | Path,
    *,
    notice_kind: str,
    post_id: int | str,
    status: str,
    reason: str | None,
    subject: str,
    recipients: list[str],
    publish_time_iso: str | None = None,
) -> None:
    path = Path(queue_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sent_at_iso = datetime.now(JST).isoformat()
    payload = {
        "status": status,
        "reason": reason,
        "subject": subject,
        "recipients": recipients,
        "post_id": post_id,
        "recorded_at": sent_at_iso,
        "sent_at": sent_at_iso,
        "notice_kind": notice_kind,
    }
    if publish_time_iso is not None:
        payload["publish_time_iso"] = str(publish_time_iso or "")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _print_result(notice_kind: str, post_id: int | str, result: Any) -> None:
    print(
        f"[result] kind={notice_kind} post_id={post_id} status={result.status} reason={result.reason} "
        f"subject={result.subject!r} recipients={result.recipients}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        load_dotenv()
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
                    duplicate_history_path=args.queue_path,
                )
                _queue_result(
                    args.queue_path,
                    notice_kind="per_post",
                    post_id=request.post_id,
                    status=mail_result.status,
                    reason=mail_result.reason,
                    subject=mail_result.subject,
                    recipients=mail_result.recipients,
                    publish_time_iso=request.publish_time_iso,
                )
                _print_result("per_post", request.post_id, mail_result)
            summary_requests = build_burst_summary_requests(
                [_summary_entry_from_request(request) for request in result.emitted],
                summary_every=args.summary_every,
                daily_cap=args.daily_cap,
            )
            for summary_request in summary_requests:
                summary_result = send_summary(
                    summary_request,
                    dry_run=dry_run,
                    send_enabled=send_enabled,
                )
                summary_post_id = f"summary:{summary_request.cumulative_published_count}"
                _queue_result(
                    args.queue_path,
                    notice_kind="summary",
                    post_id=summary_post_id,
                    status=summary_result.status,
                    reason=summary_result.reason,
                    subject=summary_result.subject,
                    recipients=summary_result.recipients,
                )
                _print_result("summary", summary_post_id, summary_result)
            return 0

        if args.stdin:
            payload = _read_payload_from_stdin()
        else:
            payload = _read_payload_from_path(str(args.input))
        notifications = payload.get("notifications")
        if isinstance(notifications, list):
            for index, item in enumerate(notifications, start=1):
                if not isinstance(item, dict):
                    raise TypeError(f"notification #{index} must be a JSON object")
                notification_type = str(item.get("type") or "").strip()
                if notification_type == "per_post":
                    request = _request_from_payload(item)
                    result = send(
                        request,
                        dry_run=dry_run,
                        send_enabled=send_enabled,
                        duplicate_history_path=args.queue_path,
                    )
                    _queue_result(
                        args.queue_path,
                        notice_kind="per_post",
                        post_id=request.post_id,
                        status=result.status,
                        reason=result.reason,
                        subject=result.subject,
                        recipients=result.recipients,
                        publish_time_iso=request.publish_time_iso,
                    )
                    _print_result("per_post", request.post_id, result)
                    continue
                if notification_type == "summary":
                    summary_request = _summary_request_from_payload(item)
                    result = send_summary(
                        summary_request,
                        dry_run=dry_run,
                        send_enabled=send_enabled,
                    )
                    summary_post_id = f"summary:{summary_request.cumulative_published_count}"
                    _queue_result(
                        args.queue_path,
                        notice_kind="summary",
                        post_id=summary_post_id,
                        status=result.status,
                        reason=result.reason,
                        subject=result.subject,
                        recipients=result.recipients,
                    )
                    _print_result("summary", summary_post_id, result)
                    continue
                if notification_type == "alert":
                    alert_request = _alert_request_from_payload(item)
                    result = send_alert(
                        alert_request,
                        dry_run=dry_run,
                        send_enabled=send_enabled,
                    )
                    alert_post_id = alert_request.post_id if alert_request.post_id is not None else f"alert:{index}"
                    _queue_result(
                        args.queue_path,
                        notice_kind="alert",
                        post_id=alert_post_id,
                        status=result.status,
                        reason=result.reason,
                        subject=result.subject,
                        recipients=result.recipients,
                    )
                    _print_result("alert", alert_post_id, result)
                    continue
                if notification_type == "emergency_hook":
                    emergency_request = _emergency_request_from_payload(item)
                    hook_result = emit_emergency_hook(emergency_request)
                    print(
                        f"[result] kind=emergency_hook post_id={emergency_request.post_id} status=hook_preview "
                        f"reason=None subject={build_emergency_subject(emergency_request)!r} hook_result={hook_result!r}"
                    )
                    continue
                raise ValueError(f"unsupported notification type: {notification_type}")
            return 0

        request = _request_from_payload(payload)
        result = send(
            request,
            dry_run=dry_run,
            send_enabled=send_enabled,
            duplicate_history_path=args.queue_path,
        )
        _queue_result(
            args.queue_path,
            notice_kind="per_post",
            post_id=request.post_id,
            status=result.status,
            reason=result.reason,
            subject=result.subject,
            recipients=result.recipients,
            publish_time_iso=request.publish_time_iso,
        )
        _print_result("per_post", request.post_id, result)
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[result] status=error error_type={type(exc).__name__} message={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
