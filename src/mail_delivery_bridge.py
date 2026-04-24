"""Shared Gmail SMTP delivery bridge with dry-run default."""

from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid
import importlib
import os
import smtplib
from typing import Any


DEFAULT_GMAIL_APP_PASSWORD_SECRET = "yoshilover-gmail-app-password"
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465
DEFAULT_SMTP_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class MailRequest:
    to: list[str]
    subject: str
    text_body: str
    html_body: str | None = None
    sender: str | None = None
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MailResult:
    status: str
    refused_recipients: dict[str, list[Any]]
    smtp_response: list[Any]
    reason: str | None = None


@dataclass(frozen=True)
class BridgeCredentials:
    app_password: str
    smtp_host: str
    smtp_port: int


def _project_id() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.environ.get("GCP_PROJECT", "").strip()
        or os.environ.get("GCLOUD_PROJECT", "").strip()
        or ""
    )


def _first_str(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _first_int(pairs: list[tuple[str, int | None]]) -> int:
    for key, default in pairs:
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        try:
            return int(value)
        except ValueError:
            continue
    for _key, default in pairs:
        if default is not None:
            return default
    return DEFAULT_SMTP_PORT


def _load_secret(secret_name: str) -> str:
    try:
        module = importlib.import_module("google.cloud.secretmanager")
    except ImportError as exc:
        raise RuntimeError("google.cloud.secretmanager is not available") from exc

    client_class = getattr(module, "SecretManagerServiceClient", None)
    if client_class is None:
        raise RuntimeError("google.cloud.secretmanager is not available")

    project_id = _project_id()
    if not project_id:
        raise RuntimeError("secret manager project id is not available")

    client = client_class()
    resource_name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(name=resource_name)
    payload = getattr(response, "payload", None)
    data = getattr(payload, "data", b"")
    if not data:
        raise RuntimeError(f"secret {secret_name} latest version is empty")
    if isinstance(data, bytes):
        return data.decode("utf-8")
    return str(data)


def _load_app_password() -> str:
    direct_primary = _first_str("MAIL_BRIDGE_GMAIL_APP_PASSWORD")
    if direct_primary:
        return direct_primary

    primary_secret_name = _first_str("MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME")
    if primary_secret_name:
        try:
            secret_value = _load_secret(primary_secret_name).strip()
        except Exception:
            secret_value = ""
        if secret_value:
            return secret_value

    direct_fallback = _first_str("GMAIL_APP_PASSWORD")
    if direct_fallback:
        return direct_fallback

    fallback_secret_name = _first_str("GMAIL_APP_PASSWORD_SECRET_NAME") or DEFAULT_GMAIL_APP_PASSWORD_SECRET
    try:
        secret_value = _load_secret(fallback_secret_name).strip()
    except Exception:
        secret_value = ""
    if secret_value:
        return secret_value

    raise RuntimeError("no Gmail app password configured")


def _smtp_host() -> str:
    return _first_str("MAIL_BRIDGE_SMTP_HOST", "FACT_CHECK_SMTP_HOST") or DEFAULT_SMTP_HOST


def _smtp_port() -> int:
    return _first_int(
        [
            ("MAIL_BRIDGE_SMTP_PORT", None),
            ("FACT_CHECK_SMTP_PORT", None),
            ("", DEFAULT_SMTP_PORT),
        ]
    )


def _normalized_recipients(recipients: list[str]) -> list[str]:
    return [address.strip() for address in recipients if address and address.strip()]


def _suppression_reason(request: MailRequest) -> str | None:
    if not request.to or not _normalized_recipients(request.to):
        return "NO_RECIPIENT"
    if not request.subject.strip():
        return "EMPTY_SUBJECT"
    if not request.text_body.strip() and not (request.html_body and request.html_body.strip()):
        return "EMPTY_BODY"
    return None


def _decode_smtp_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _serialize_refused_recipients(refused: Any) -> dict[str, list[Any]]:
    if not isinstance(refused, dict):
        return {}
    serialized: dict[str, list[Any]] = {}
    for recipient, response in refused.items():
        if isinstance(response, tuple) and len(response) >= 2:
            code, message = response[0], response[1]
        else:
            code, message = 0, response
        try:
            numeric_code = int(code)
        except Exception:
            numeric_code = 0
        serialized[str(recipient)] = [numeric_code, _decode_smtp_value(message)]
    return serialized


def _serialize_smtp_response(code: Any, message: Any) -> list[Any]:
    try:
        numeric_code = int(code)
    except Exception:
        numeric_code = 0
    return [numeric_code, _decode_smtp_value(message)]


def _resolve_smtp_username() -> str:
    username = _first_str("MAIL_BRIDGE_SMTP_USERNAME", "FACT_CHECK_EMAIL_FROM")
    if username:
        return username
    raise RuntimeError("no SMTP username configured")


def _resolve_sender(request: MailRequest, smtp_username: str) -> str:
    explicit_sender = (request.sender or "").strip()
    if explicit_sender:
        return explicit_sender
    return _first_str("MAIL_BRIDGE_FROM", "FACT_CHECK_EMAIL_FROM") or smtp_username


def _build_message(request: MailRequest, *, sender: str, recipients: list[str]) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = request.subject.strip()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    if request.reply_to and request.reply_to.strip():
        message["Reply-To"] = request.reply_to.strip()
    message["Message-ID"] = make_msgid(domain="yoshilover.com")
    message.set_content(request.text_body)
    if request.html_body and request.html_body.strip():
        message.add_alternative(request.html_body, subtype="html")
    return message


def load_credentials_from_env() -> BridgeCredentials:
    return BridgeCredentials(
        app_password=_load_app_password(),
        smtp_host=_smtp_host(),
        smtp_port=_smtp_port(),
    )


def send(
    request: MailRequest,
    *,
    dry_run: bool = True,
    credentials: BridgeCredentials | None = None,
) -> MailResult:
    reason = _suppression_reason(request)
    if reason:
        return MailResult(
            status="suppressed",
            refused_recipients={},
            smtp_response=[],
            reason=reason,
        )

    if dry_run:
        return MailResult(
            status="dry_run",
            refused_recipients={},
            smtp_response=[],
            reason=None,
        )

    smtp_username = _resolve_smtp_username()
    sender = _resolve_sender(request, smtp_username)
    active_credentials = credentials or load_credentials_from_env()
    recipients = _normalized_recipients(request.to)
    message = _build_message(request, sender=sender, recipients=recipients)

    with smtplib.SMTP_SSL(
        active_credentials.smtp_host,
        active_credentials.smtp_port,
        timeout=DEFAULT_SMTP_TIMEOUT_SECONDS,
    ) as smtp:
        smtp.login(smtp_username, active_credentials.app_password)
        refused = smtp.send_message(message)
        smtp_response = _serialize_smtp_response(*smtp.noop())

    return MailResult(
        status="sent",
        refused_recipients=_serialize_refused_recipients(refused),
        smtp_response=smtp_response,
        reason=None,
    )
