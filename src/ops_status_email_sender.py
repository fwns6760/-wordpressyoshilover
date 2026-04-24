"""Ops status mail adapter built on top of ticket 072 bridge and ticket 070 renderer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any, Literal
from zoneinfo import ZoneInfo

from src.mail_delivery_bridge import (
    MailRequest,
    MailResult,
    load_credentials_from_env,
    send as bridge_send_default,
)
from src.ops_secretary_status import format_digest_human, render_ops_status_digest


JST = ZoneInfo("Asia/Tokyo")
_REJECT_MARKER = "[reject:"
_DEFAULT_CREDENTIALS_LOADER = load_credentials_from_env


@dataclass(frozen=True)
class OpsStatusEmailRequest:
    snapshot: Mapping[str, Any]
    body_html: str | None = None
    override_subject_datetime: str | None = None
    override_recipient: list[str] | None = None
    strict: bool = False


@dataclass(frozen=True)
class OpsStatusEmailResult:
    status: Literal["sent", "dry_run", "suppressed"]
    reason: str | None
    subject: str | None
    recipients: list[str]
    body_text_preview: str | None
    bridge_result: MailResult | None


BridgeSend = Callable[..., MailResult]
NowProvider = Callable[[], datetime]


def _normalized_recipients(values: list[str]) -> list[str]:
    recipients: list[str] = []
    for value in values:
        for item in str(value or "").split(","):
            address = item.strip()
            if address:
                recipients.append(address)
    return recipients


def _now_jst() -> datetime:
    return datetime.now(JST)


def _format_subject_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        current = value.replace(tzinfo=JST)
    else:
        current = value.astimezone(JST)
    return current.strftime("%Y-%m-%d %H:%M")


def _body_preview(body_text: str) -> str | None:
    if not body_text:
        return None
    return body_text[:200]


def _reject_reasons(body_text: str) -> list[str]:
    reasons: list[str] = []
    for chunk in body_text.split(_REJECT_MARKER)[1:]:
        reason, _, _rest = chunk.partition("]")
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def build_subject(now_jst: str | None, override: str | None) -> str:
    subject_datetime = (override or "").strip() or (now_jst or "").strip() or _format_subject_datetime(_now_jst())
    return f"[ops] Giants ops status {subject_datetime}"


def resolve_recipients(override: list[str] | None) -> list[str]:
    if override is not None:
        return _normalized_recipients(override)

    ops_recipients = _normalized_recipients([os.environ.get("OPS_EMAIL_TO", "")])
    if ops_recipients:
        return ops_recipients

    return _normalized_recipients([os.environ.get("MAIL_BRIDGE_TO", "")])


def render_body(snapshot: Mapping[str, Any], *, strict: bool) -> str:
    digest = render_ops_status_digest(snapshot, strict=strict)
    body_text = format_digest_human(digest)
    if strict and _REJECT_MARKER in body_text:
        reasons = ", ".join(_reject_reasons(body_text)) or "unknown"
        raise ValueError(f"renderer rejected forbidden field: {reasons}")
    return body_text


def _suppressed(
    reason: str,
    *,
    recipients: list[str] | None = None,
    body_text_preview: str | None = None,
    bridge_result: MailResult | None = None,
) -> OpsStatusEmailResult:
    return OpsStatusEmailResult(
        status="suppressed",
        reason=reason,
        subject=None,
        recipients=list(recipients or []),
        body_text_preview=body_text_preview,
        bridge_result=bridge_result,
    )


def send(
    request: OpsStatusEmailRequest,
    *,
    dry_run: bool = True,
    bridge_send: BridgeSend = bridge_send_default,
    now_provider: NowProvider | None = None,
) -> OpsStatusEmailResult:
    if not isinstance(request.snapshot, Mapping):
        return _suppressed("INVALID_SNAPSHOT")

    try:
        body_text = render_body(request.snapshot, strict=request.strict)
    except Exception as exc:
        return _suppressed(f"RENDERER_ERROR: {exc}")

    if not body_text.strip():
        return _suppressed("EMPTY_BODY")

    body_text_preview = _body_preview(body_text)
    recipients = resolve_recipients(request.override_recipient)
    if not recipients:
        return _suppressed("NO_RECIPIENT", recipients=recipients, body_text_preview=body_text_preview)

    current = now_provider() if now_provider is not None else _now_jst()
    subject = build_subject(_format_subject_datetime(current), request.override_subject_datetime)
    mail_request = MailRequest(
        to=recipients,
        subject=subject,
        text_body=body_text,
        html_body=request.body_html,
    )

    if dry_run:
        return OpsStatusEmailResult(
            status="dry_run",
            reason=None,
            subject=subject,
            recipients=recipients,
            body_text_preview=body_text_preview,
            bridge_result=None,
        )

    bridge_result = bridge_send(mail_request, dry_run=False)
    if bridge_result.status == "suppressed":
        return _suppressed(
            bridge_result.reason or "UNKNOWN_BRIDGE_SUPPRESSION",
            recipients=recipients,
            body_text_preview=body_text_preview,
            bridge_result=bridge_result,
        )
    if bridge_result.status == "dry_run":
        return OpsStatusEmailResult(
            status="dry_run",
            reason=bridge_result.reason,
            subject=subject,
            recipients=recipients,
            body_text_preview=body_text_preview,
            bridge_result=bridge_result,
        )
    return OpsStatusEmailResult(
        status="sent",
        reason=bridge_result.reason,
        subject=subject,
        recipients=recipients,
        body_text_preview=body_text_preview,
        bridge_result=bridge_result,
    )
