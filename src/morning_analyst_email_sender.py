"""Morning analyst digest mail adapter built on top of ticket 072 bridge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Literal

from src.mail_delivery_bridge import (
    BridgeCredentials,
    MailRequest,
    MailResult,
    load_credentials_from_env,
    send as bridge_send_default,
)


@dataclass(frozen=True)
class AnalystDigestMeta:
    latest_date: str
    comparison_ready: bool
    status: str | None


@dataclass(frozen=True)
class AnalystEmailRequest:
    digest_json_path: str
    body_text_path: str
    body_html_path: str | None = None
    override_subject_date: str | None = None
    override_recipient: list[str] | None = None


@dataclass(frozen=True)
class AnalystEmailResult:
    status: Literal["sent", "dry_run", "suppressed"]
    reason: str | None
    subject: str | None
    recipients: list[str]
    bridge_result: MailResult | None


BridgeSend = Callable[..., MailResult]


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no"}
    return bool(value)


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


def load_digest_meta(path: str) -> AnalystDigestMeta:
    digest_path = Path(path)
    try:
        payload = json.loads(digest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid digest json: {digest_path}") from exc

    if not isinstance(payload, dict):
        raise KeyError("window")
    window = payload.get("window")
    if not isinstance(window, dict):
        raise KeyError("window")

    status_value = window.get("status")
    return AnalystDigestMeta(
        latest_date=str(window.get("latest_date") or "").strip(),
        comparison_ready=_coerce_bool(window.get("comparison_ready", True)),
        status=None if status_value is None else str(status_value),
    )


def build_subject(meta: AnalystDigestMeta, override_date: str | None) -> str:
    subject_date = (override_date or meta.latest_date).strip()
    prefix = "[analyst]" if meta.comparison_ready else "[analyst][蓄積中]"
    return f"{prefix} Giants morning digest {subject_date}".rstrip()


def resolve_recipients(override: list[str] | None) -> list[str]:
    if override is not None:
        return _normalized_recipients(override)

    analyst_recipients = _normalized_recipients([os.environ.get("ANALYST_EMAIL_TO", "")])
    if analyst_recipients:
        return analyst_recipients

    return _normalized_recipients([os.environ.get("MAIL_BRIDGE_TO", "")])


def _suppressed(reason: str, *, recipients: list[str] | None = None) -> AnalystEmailResult:
    return AnalystEmailResult(
        status="suppressed",
        reason=reason,
        subject=None,
        recipients=list(recipients or []),
        bridge_result=None,
    )


def send(
    request: AnalystEmailRequest,
    *,
    dry_run: bool = True,
    bridge_send: BridgeSend = bridge_send_default,
) -> AnalystEmailResult:
    try:
        meta = load_digest_meta(request.digest_json_path)
    except FileNotFoundError:
        return _suppressed("MISSING_DIGEST")
    except ValueError:
        return _suppressed("MISSING_DIGEST")
    except KeyError:
        return _suppressed("INVALID_DIGEST")

    try:
        body_text = _read_required_body_text(request.body_text_path)
    except FileNotFoundError:
        return _suppressed("EMPTY_BODY")

    if not body_text.strip():
        return _suppressed("EMPTY_BODY")

    recipients = resolve_recipients(request.override_recipient)
    if not recipients:
        return _suppressed("NO_RECIPIENT")

    body_html = _read_optional_body_html(request.body_html_path)
    subject = build_subject(meta, request.override_subject_date)
    mail_request = MailRequest(
        to=recipients,
        subject=subject,
        text_body=body_text,
        html_body=body_html,
        metadata={
            "latest_date": meta.latest_date,
            "comparison_ready": meta.comparison_ready,
            "status": meta.status,
        },
    )

    if dry_run:
        return AnalystEmailResult(
            status="dry_run",
            reason=None,
            subject=subject,
            recipients=recipients,
            bridge_result=None,
        )

    bridge_result = bridge_send(mail_request, dry_run=False)
    if bridge_result.status == "suppressed":
        return AnalystEmailResult(
            status="suppressed",
            reason=bridge_result.reason,
            subject=None,
            recipients=recipients,
            bridge_result=bridge_result,
        )
    if bridge_result.status == "dry_run":
        return AnalystEmailResult(
            status="dry_run",
            reason=bridge_result.reason,
            subject=subject,
            recipients=recipients,
            bridge_result=bridge_result,
        )
    return AnalystEmailResult(
        status="sent",
        reason=bridge_result.reason,
        subject=subject,
        recipients=recipients,
        bridge_result=bridge_result,
    )
