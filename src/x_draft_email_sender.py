"""X draft digest mail adapter built on top of ticket 072 bridge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
from typing import Literal
from zoneinfo import ZoneInfo

from src.mail_delivery_bridge import (
    MailRequest,
    MailResult,
    load_credentials_from_env,
    send as bridge_send_default,
)


JST = ZoneInfo("Asia/Tokyo")
_CANDIDATE_LINE_RE = re.compile(r"^candidate\s+\d+\s*$", re.MULTILINE)


@dataclass(frozen=True)
class XDraftEmailRequest:
    body_text_path: str
    body_html_path: str | None = None
    override_subject_datetime: str | None = None
    override_recipient: list[str] | None = None
    item_count_override: int | None = None


@dataclass(frozen=True)
class XDraftEmailResult:
    status: Literal["sent", "dry_run", "suppressed"]
    reason: str | None
    subject: str | None
    recipients: list[str]
    item_count: int
    bridge_result: MailResult | None


BridgeSend = Callable[..., MailResult]
NowProvider = Callable[[], datetime]
_DEFAULT_CREDENTIALS_LOADER = load_credentials_from_env


def _normalized_recipients(values: list[str]) -> list[str]:
    recipients: list[str] = []
    for value in values:
        for item in str(value or "").split(","):
            address = item.strip()
            if address:
                recipients.append(address)
    return recipients


def _read_required_body_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_optional_body_html(path: str | None) -> str | None:
    if path is None:
        return None
    return Path(path).read_text(encoding="utf-8")


def _now_jst() -> datetime:
    return datetime.now(JST)


def _format_subject_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        current = value.replace(tzinfo=JST)
    else:
        current = value.astimezone(JST)
    return current.strftime("%Y-%m-%d %H:%M")


def build_subject(now_jst: str | None, override: str | None) -> str:
    subject_datetime = (override or "").strip() or (now_jst or "").strip() or _format_subject_datetime(_now_jst())
    return f"[X下書き] Giants news drafts {subject_datetime}"


def resolve_recipients(override: list[str] | None) -> list[str]:
    if override is not None:
        return _normalized_recipients(override)

    x_draft_recipients = _normalized_recipients([os.environ.get("X_DRAFT_EMAIL_TO", "")])
    if x_draft_recipients:
        return x_draft_recipients

    return _normalized_recipients([os.environ.get("MAIL_BRIDGE_TO", "")])


def count_items(body_text: str) -> int:
    return len(_CANDIDATE_LINE_RE.findall(body_text))


def _suppressed(
    reason: str,
    *,
    recipients: list[str] | None = None,
    item_count: int = 0,
) -> XDraftEmailResult:
    return XDraftEmailResult(
        status="suppressed",
        reason=reason,
        subject=None,
        recipients=list(recipients or []),
        item_count=max(item_count, 0),
        bridge_result=None,
    )


def send(
    request: XDraftEmailRequest,
    *,
    dry_run: bool = True,
    bridge_send: BridgeSend = bridge_send_default,
    now_provider: NowProvider | None = None,
) -> XDraftEmailResult:
    body_text_path = request.body_text_path.strip()
    if not body_text_path:
        return _suppressed("MISSING_BODY")

    try:
        body_text = _read_required_body_text(body_text_path)
    except FileNotFoundError:
        return _suppressed("MISSING_BODY")

    if not body_text.strip():
        return _suppressed("EMPTY_BODY")

    item_count = request.item_count_override if request.item_count_override is not None else count_items(body_text)
    if item_count <= 0:
        return _suppressed("NO_ITEMS", item_count=item_count)

    recipients = resolve_recipients(request.override_recipient)
    if not recipients:
        return _suppressed("NO_RECIPIENT", item_count=item_count)

    body_html = _read_optional_body_html(request.body_html_path)
    current = now_provider() if now_provider is not None else _now_jst()
    subject = build_subject(_format_subject_datetime(current), request.override_subject_datetime)
    mail_request = MailRequest(
        to=recipients,
        subject=subject,
        text_body=body_text,
        html_body=body_html,
    )

    if dry_run:
        return XDraftEmailResult(
            status="dry_run",
            reason=None,
            subject=subject,
            recipients=recipients,
            item_count=item_count,
            bridge_result=None,
        )

    bridge_result = bridge_send(mail_request, dry_run=False)
    if bridge_result.status == "suppressed":
        return XDraftEmailResult(
            status="suppressed",
            reason=bridge_result.reason,
            subject=None,
            recipients=recipients,
            item_count=item_count,
            bridge_result=bridge_result,
        )
    if bridge_result.status == "dry_run":
        return XDraftEmailResult(
            status="dry_run",
            reason=bridge_result.reason,
            subject=subject,
            recipients=recipients,
            item_count=item_count,
            bridge_result=bridge_result,
        )
    return XDraftEmailResult(
        status="sent",
        reason=bridge_result.reason,
        subject=subject,
        recipients=recipients,
        item_count=item_count,
        bridge_result=bridge_result,
    )
