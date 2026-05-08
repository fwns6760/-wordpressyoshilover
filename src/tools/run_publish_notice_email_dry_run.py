"""Dry-run CLI for ticket 076 publish notice mail."""

from __future__ import annotations

import argparse
import json
import logging
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
    build_alert_body_text,
    build_body_text,
    build_emergency_subject,
    build_execution_summary_log,
    build_summary_body_text,
    build_zero_sent_alert_log,
    emit_emergency_hook,
    append_send_result,
    maybe_send_morning_heartbeat,
    send,
    send_alert,
    send_summary,
    summarize_execution_results,
)
from src.publish_notice_scanner import (  # noqa: E402
    _publish_notice_review_timeout_budget_seconds as _review_timeout_budget_seconds,
    _publish_notice_two_phase_enabled as _two_phase_enabled,
    scan,
    scan_direct_publish_only,
    scan_review_only,
)
from src import repair_provider_ledger  # noqa: E402
from src import runner_ledger_integration  # noqa: E402


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


def _load_state_fetch_reasons_from_env() -> dict[str, int] | None:
    raw = os.environ.get("PUBLISH_NOTICE_STATE_FETCH_REASONS", "")
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    cleaned: dict[str, int] = {}
    for key, value in parsed.items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        cleaned[str(key)] = count
    return cleaned or None


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
        is_backlog=payload.get("is_backlog"),
        notice_kind=str(payload.get("notice_kind") or "publish"),
        subject_override=None if payload.get("subject_override") is None else str(payload.get("subject_override")),
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


def _is_publish_notice_request(request: PublishNoticeRequest) -> bool:
    return str(getattr(request, "notice_kind", "publish") or "publish").strip() == "publish"


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


def _print_result(notice_kind: str, post_id: int | str, result: Any) -> None:
    print(
        f"[result] kind={notice_kind} post_id={post_id} status={result.status} reason={result.reason} "
        f"subject={result.subject!r} recipients={result.recipients}"
    )


def _notice_status(result: Any) -> str:
    if str(getattr(result, "status", "")).strip() == "sent":
        return "success"
    return "skipped"


def _result_text(result: Any) -> str:
    return json.dumps(
        {
            "status": str(getattr(result, "status", "")).strip(),
            "reason": getattr(result, "reason", None),
            "subject": str(getattr(result, "subject", "")).strip(),
            "recipients": list(getattr(result, "recipients", []) or []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _emit_notice_ledger(
    ledger_sink: runner_ledger_integration.BestEffortLedgerSink,
    *,
    notice_kind: str,
    post_id: int | str | None,
    before_body: str,
    result: Any,
    input_payload: dict[str, Any],
) -> None:
    if not ledger_sink.enabled:
        return
    quality_flags = ["publish_notice", notice_kind, str(getattr(result, "status", "")).strip() or "unknown"]
    entry = runner_ledger_integration.build_entry(
        lane="publish_notice",
        provider="gemini",
        model="publish-notice-email-sender",
        source_post_id=int(post_id) if str(post_id or "").isdigit() else 0,
        before_body=before_body,
        after_body=_result_text(result),
        status=_notice_status(result),
        error_code=None if _notice_status(result) == "success" else getattr(result, "reason", None),
        quality_flags=quality_flags,
        input_payload=input_payload,
        artifact_uri="memory://publish_notice",
    )
    ledger_sink.persist(
        entry,
        before_body=before_body,
        after_body=_result_text(result),
        extra_meta={
            "notice_kind": notice_kind,
            "post_id": post_id,
            "status": getattr(result, "status", None),
            "reason": getattr(result, "reason", None),
            "subject": getattr(result, "subject", None),
            "recipients": list(getattr(result, "recipients", []) or []),
        },
    )


def _send_per_post_requests(
    requests: Sequence[PublishNoticeRequest],
    *,
    queue_path: str,
    history_path: str,
    dry_run: bool,
    send_enabled: bool,
    ledger_sink: runner_ledger_integration.BestEffortLedgerSink,
) -> list[Any]:
    results: list[Any] = []
    for request in requests:
        mail_result = send(
            request,
            dry_run=dry_run,
            send_enabled=send_enabled,
            duplicate_history_path=queue_path,
        )
        append_send_result(
            queue_path,
            notice_kind="per_post",
            post_id=request.post_id,
            result=mail_result,
            publish_time_iso=request.publish_time_iso,
            request=request,
            history_path=history_path,
        )
        results.append(mail_result)
        _emit_notice_ledger(
            ledger_sink,
            notice_kind="per_post",
            post_id=request.post_id,
            before_body=build_body_text(request),
            result=mail_result,
            input_payload={
                "notice_kind": "per_post",
                "request": {
                    "post_id": request.post_id,
                    "title": request.title,
                    "canonical_url": request.canonical_url,
                    "subtype": request.subtype,
                    "publish_time_iso": request.publish_time_iso,
                },
            },
        )
        _print_result("per_post", request.post_id, mail_result)
    return results


def _send_summary_requests(
    summary_requests: Sequence[BurstSummaryRequest],
    *,
    queue_path: str,
    dry_run: bool,
    send_enabled: bool,
    ledger_sink: runner_ledger_integration.BestEffortLedgerSink,
) -> None:
    for summary_request in summary_requests:
        summary_result = send_summary(
            summary_request,
            dry_run=dry_run,
            send_enabled=send_enabled,
        )
        summary_post_id = f"summary:{summary_request.cumulative_published_count}"
        append_send_result(
            queue_path,
            notice_kind="summary",
            post_id=summary_post_id,
            result=summary_result,
        )
        _emit_notice_ledger(
            ledger_sink,
            notice_kind="summary",
            post_id=summary_post_id,
            before_body=build_summary_body_text(summary_request),
            result=summary_result,
            input_payload={
                "notice_kind": "summary",
                "summary_post_id": summary_post_id,
                "cumulative_published_count": summary_request.cumulative_published_count,
            },
        )
        _print_result("summary", summary_post_id, summary_result)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        load_dotenv()
        args = _parse_args(argv)
        send_enabled = args.send_enabled or str(os.environ.get("PUBLISH_NOTICE_EMAIL_ENABLED", "")).strip() == "1"
        dry_run = not args.send
        ledger_sink = runner_ledger_integration.BestEffortLedgerSink(
            collection_name=runner_ledger_integration.DEFAULT_NOTICE_COLLECTION,
            fallback_path=repair_provider_ledger.resolve_jsonl_ledger_path(),
        )

        if args.scan:
            per_post_results = []
            total_emitted = 0
            if _two_phase_enabled():
                direct_result = scan_direct_publish_only(
                    cursor_path=args.cursor_path,
                    history_path=args.history_path,
                    queue_path=args.queue_path,
                )
                print(
                    f"[scan:direct] emitted={len(direct_result.emitted)} skipped={len(direct_result.skipped)} "
                    f"cursor_before={direct_result.cursor_before} cursor_after={direct_result.cursor_after}"
                )
                for post_id, reason in direct_result.skipped:
                    print(f"[skip] phase=direct post_id={post_id} reason={reason}")
                direct_results = _send_per_post_requests(
                    direct_result.emitted,
                    queue_path=args.queue_path,
                    history_path=args.history_path,
                    dry_run=dry_run,
                    send_enabled=send_enabled,
                    ledger_sink=ledger_sink,
                )
                per_post_results.extend(direct_results)
                total_emitted += len(direct_result.emitted)

                summary_entries = [
                    _summary_entry_from_request(request)
                    for request in direct_result.emitted
                    if _is_publish_notice_request(request)
                ]
                summary_requests = build_burst_summary_requests(
                    summary_entries,
                    summary_every=args.summary_every,
                    daily_cap=args.daily_cap,
                )
                _send_summary_requests(
                    summary_requests,
                    queue_path=args.queue_path,
                    dry_run=dry_run,
                    send_enabled=send_enabled,
                    ledger_sink=ledger_sink,
                )

                if direct_result.cursor_before is not None:
                    try:
                        review_result = scan_review_only(
                            cursor_path=args.cursor_path,
                            history_path=args.history_path,
                            queue_path=args.queue_path,
                            budget_seconds=_review_timeout_budget_seconds(),
                        )
                    except Exception as exc:
                        print(
                            f"[scan:review] status=error error_type={type(exc).__name__} message={exc}",
                            file=sys.stderr,
                        )
                        review_result = None
                    if review_result is not None:
                        print(
                            f"[scan:review] emitted={len(review_result.emitted)} skipped={len(review_result.skipped)} "
                            f"cursor_before={review_result.cursor_before} cursor_after={review_result.cursor_after}"
                        )
                        for post_id, reason in review_result.skipped:
                            print(f"[skip] phase=review post_id={post_id} reason={reason}")
                        review_results = _send_per_post_requests(
                            review_result.emitted,
                            queue_path=args.queue_path,
                            history_path=args.history_path,
                            dry_run=dry_run,
                            send_enabled=send_enabled,
                            ledger_sink=ledger_sink,
                        )
                        per_post_results.extend(review_results)
                        total_emitted += len(review_result.emitted)
            else:
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
                legacy_results = _send_per_post_requests(
                    result.emitted,
                    queue_path=args.queue_path,
                    history_path=args.history_path,
                    dry_run=dry_run,
                    send_enabled=send_enabled,
                    ledger_sink=ledger_sink,
                )
                per_post_results.extend(legacy_results)
                summary_entries = [
                    _summary_entry_from_request(request)
                    for request in result.emitted
                    if _is_publish_notice_request(request)
                ]
                summary_requests = build_burst_summary_requests(
                    summary_entries,
                    summary_every=args.summary_every,
                    daily_cap=args.daily_cap,
                )
                _send_summary_requests(
                    summary_requests,
                    queue_path=args.queue_path,
                    dry_run=dry_run,
                    send_enabled=send_enabled,
                    ledger_sink=ledger_sink,
                )
                total_emitted = len(result.emitted)

            state_fetch_reasons = _load_state_fetch_reasons_from_env()
            if state_fetch_reasons:
                print(
                    f"[state_fetch] failed_count={sum(state_fetch_reasons.values())} "
                    f"reasons={json.dumps(state_fetch_reasons, sort_keys=True)}"
                )
            execution_summary = summarize_execution_results(
                per_post_results,
                emitted=total_emitted,
                state_fetch_reasons=state_fetch_reasons,
            )
            print(build_execution_summary_log(execution_summary))
            alert_line = build_zero_sent_alert_log(execution_summary)
            if alert_line is not None:
                logging.warning(alert_line)
            try:
                heartbeat_sent = maybe_send_morning_heartbeat(
                    queue_path=args.queue_path,
                    dry_run=dry_run,
                    send_enabled=send_enabled,
                    processed_this_fire=total_emitted,
                )
                if heartbeat_sent:
                    print("[heartbeat] morning summary mail emitted")
            except Exception as exc:  # heartbeat failure must not crash the cron
                print(
                    f"[heartbeat] status=error error_type={type(exc).__name__} message={exc}",
                    file=sys.stderr,
                )
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
                    append_send_result(
                        args.queue_path,
                        notice_kind="per_post",
                        post_id=request.post_id,
                        result=result,
                        publish_time_iso=request.publish_time_iso,
                        request=request,
                        history_path=args.history_path,
                    )
                    _emit_notice_ledger(
                        ledger_sink,
                        notice_kind="per_post",
                        post_id=request.post_id,
                        before_body=build_body_text(request),
                        result=result,
                        input_payload={"notice_kind": "per_post", "request": item},
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
                    append_send_result(
                        args.queue_path,
                        notice_kind="summary",
                        post_id=summary_post_id,
                        result=result,
                    )
                    _emit_notice_ledger(
                        ledger_sink,
                        notice_kind="summary",
                        post_id=summary_post_id,
                        before_body=build_summary_body_text(summary_request),
                        result=result,
                        input_payload={"notice_kind": "summary", "request": item},
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
                    append_send_result(
                        args.queue_path,
                        notice_kind="alert",
                        post_id=alert_post_id,
                        result=result,
                    )
                    _emit_notice_ledger(
                        ledger_sink,
                        notice_kind="alert",
                        post_id=alert_post_id,
                        before_body=build_alert_body_text(alert_request),
                        result=result,
                        input_payload={"notice_kind": "alert", "request": item},
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
        append_send_result(
            args.queue_path,
            notice_kind="per_post",
            post_id=request.post_id,
            result=result,
            publish_time_iso=request.publish_time_iso,
            request=request,
            history_path=args.history_path,
        )
        _emit_notice_ledger(
            ledger_sink,
            notice_kind="per_post",
            post_id=request.post_id,
            before_body=build_body_text(request),
            result=result,
            input_payload={"notice_kind": "per_post", "request": payload},
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
