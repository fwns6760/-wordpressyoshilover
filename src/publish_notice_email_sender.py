"""Publish notice mail adapter built on top of ticket 072 bridge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import os
import re
from typing import Any, Literal
from zoneinfo import ZoneInfo

from src.mail_delivery_bridge import send as bridge_send_default


JST = ZoneInfo("Asia/Tokyo")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PublishNoticeRequest:
    post_id: int | str
    title: str
    canonical_url: str
    subtype: str
    publish_time_iso: str
    summary: str | None = None


@dataclass(frozen=True)
class PublishNoticeEmailResult:
    status: Literal["sent", "dry_run", "suppressed"]
    reason: str | None
    subject: str
    recipients: list[str]
    bridge_result: object | None = None


@dataclass(frozen=True)
class _BridgeMailRequest:
    to: list[str]
    subject: str
    text_body: str
    html_body: str | None = None
    sender: str | None = None
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


BridgeSend = Callable[..., object]


def _normalized_recipients(values: list[str]) -> list[str]:
    recipients: list[str] = []
    for value in values:
        for item in str(value or "").split(","):
            address = item.strip()
            if address:
                recipients.append(address)
    return recipients


def _format_publish_time_jst(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        current = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if current.tzinfo is None:
        current = current.replace(tzinfo=JST)
    else:
        current = current.astimezone(JST)
    return current.strftime("%Y-%m-%d %H:%M JST")


def _normalize_summary(summary: str | None) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(summary or "").strip())
    if not compact:
        return "(なし)"
    if len(compact) > 120:
        return f"{compact[:119]}…"
    return compact


def build_subject(title: str, publish_dt_jst: str | None = None, override: str | None = None) -> str:
    del publish_dt_jst
    if override is not None:
        return str(override)
    return f"[公開通知] Giants {title}"


def resolve_recipients(override: list[str] | None) -> list[str]:
    if override is not None:
        return _normalized_recipients(override)

    publish_notice_recipients = _normalized_recipients([os.environ.get("PUBLISH_NOTICE_EMAIL_TO", "")])
    if publish_notice_recipients:
        return publish_notice_recipients

    return _normalized_recipients([os.environ.get("MAIL_BRIDGE_TO", "")])


def build_body_text(request: PublishNoticeRequest) -> str:
    lines = [
        f"title: {str(request.title or '').strip()}",
        f"url: {str(request.canonical_url or '').strip()}",
        f"subtype: {str(request.subtype or '').strip() or 'unknown'}",
        f"publish time: {_format_publish_time_jst(request.publish_time_iso)}",
        f"summary: {_normalize_summary(request.summary)}",
    ]
    return "\n".join(lines)


def _suppressed(
    reason: str,
    *,
    subject: str,
    recipients: list[str] | None = None,
    bridge_result: object | None = None,
) -> PublishNoticeEmailResult:
    return PublishNoticeEmailResult(
        status="suppressed",
        reason=reason,
        subject=subject,
        recipients=list(recipients or []),
        bridge_result=bridge_result,
    )


def send(
    request: PublishNoticeRequest,
    *,
    dry_run: bool = True,
    send_enabled: bool | None = None,
    bridge_send: BridgeSend = bridge_send_default,
    override_recipient: list[str] | None = None,
    override_subject: str | None = None,
) -> PublishNoticeEmailResult:
    normalized_title = str(request.title or "").strip()
    subject = build_subject(normalized_title, override=override_subject)
    if not normalized_title:
        return _suppressed("EMPTY_TITLE", subject=subject)

    normalized_url = str(request.canonical_url or "").strip()
    if not normalized_url:
        return _suppressed("MISSING_URL", subject=subject)

    recipients = resolve_recipients(override_recipient)
    if not recipients:
        return _suppressed("NO_RECIPIENT", subject=subject, recipients=recipients)

    normalized_request = PublishNoticeRequest(
        post_id=request.post_id,
        title=normalized_title,
        canonical_url=normalized_url,
        subtype=str(request.subtype or "").strip() or "unknown",
        publish_time_iso=str(request.publish_time_iso or "").strip(),
        summary=request.summary,
    )
    body_text = build_body_text(normalized_request)

    if dry_run:
        return PublishNoticeEmailResult(
            status="dry_run",
            reason=None,
            subject=subject,
            recipients=recipients,
            bridge_result=None,
        )

    active_send_enabled = (
        send_enabled
        if send_enabled is not None
        else str(os.environ.get("PUBLISH_NOTICE_EMAIL_ENABLED", "")).strip() == "1"
    )
    if not active_send_enabled:
        return _suppressed("GATE_OFF", subject=subject, recipients=recipients)

    mail_request = _BridgeMailRequest(
        to=recipients,
        subject=subject,
        text_body=body_text,
        metadata={
            "post_id": normalized_request.post_id,
            "subtype": normalized_request.subtype,
            "publish_time_iso": normalized_request.publish_time_iso,
        },
    )
    bridge_result = bridge_send(mail_request, dry_run=False)
    bridge_status = str(getattr(bridge_result, "status", "") or "")
    bridge_reason = getattr(bridge_result, "reason", None)

    if bridge_status == "suppressed":
        return _suppressed(
            str(bridge_reason or "UNKNOWN_BRIDGE_SUPPRESSION"),
            subject=subject,
            recipients=recipients,
            bridge_result=bridge_result,
        )
    if bridge_status == "dry_run":
        return PublishNoticeEmailResult(
            status="dry_run",
            reason=None if bridge_reason is None else str(bridge_reason),
            subject=subject,
            recipients=recipients,
            bridge_result=bridge_result,
        )
    return PublishNoticeEmailResult(
        status="sent",
        reason=None if bridge_reason is None else str(bridge_reason),
        subject=subject,
        recipients=recipients,
        bridge_result=bridge_result,
    )


__all__ = [
    "JST",
    "PublishNoticeEmailResult",
    "PublishNoticeRequest",
    "build_body_text",
    "build_subject",
    "resolve_recipients",
    "send",
]
