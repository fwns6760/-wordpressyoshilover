"""Durable ledger writer for body-contract fail outcomes."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


JST = timezone(timedelta(hours=9))
ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV = "ENABLE_BODY_CONTRACT_FAIL_LEDGER"
BODY_CONTRACT_FAIL_LEDGER_PATH_ENV = "BODY_CONTRACT_FAIL_LEDGER_PATH"
BODY_CONTRACT_FAIL_HISTORY_DEFAULT_PATH = Path("/tmp/pub004d/body_contract_fail_history.jsonl")
BODY_CONTRACT_FAIL_HISTORY_FALLBACK_PATH = Path("logs/body_contract_fail_history.jsonl")
BODY_CONTRACT_FAIL_STATE_BUCKET = "baseballsite-yoshilover-state"
BODY_CONTRACT_FAIL_STATE_KEY = "body_contract/body_contract_fail_history.jsonl"
BODY_CONTRACT_FAIL_RECORD_TYPE = "body_contract_fail"
BODY_CONTRACT_FAIL_SKIP_LAYER = "body_contract"
BODY_CONTRACT_FAIL_TERMINAL_STATE = "skip_accounted"


@dataclass(frozen=True)
class BodyContractFailLedgerResult:
    status: str
    record: dict[str, Any] | None
    local_path: Path | None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def body_contract_fail_ledger_enabled() -> bool:
    return _env_flag(ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV, False)


def _as_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def resolve_body_contract_fail_ledger_path(override: str | Path | None = None) -> Path:
    if override is not None and str(override).strip():
        return Path(override)
    env_value = str(os.environ.get(BODY_CONTRACT_FAIL_LEDGER_PATH_ENV, "")).strip()
    if env_value:
        return Path(env_value)
    return BODY_CONTRACT_FAIL_HISTORY_DEFAULT_PATH


def _candidate_local_paths(override: str | Path | None = None) -> list[Path]:
    primary = resolve_body_contract_fail_ledger_path(override)
    if override is not None and str(override).strip():
        return [primary]
    if str(os.environ.get(BODY_CONTRACT_FAIL_LEDGER_PATH_ENV, "")).strip():
        return [primary]
    if primary == BODY_CONTRACT_FAIL_HISTORY_FALLBACK_PATH:
        return [primary]
    return [primary, BODY_CONTRACT_FAIL_HISTORY_FALLBACK_PATH]


def _hash_source_url(source_url: str) -> str:
    normalized = str(source_url or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _hash_body_excerpt(body_excerpt: str) -> str | None:
    normalized = str(body_excerpt or "").strip()
    if not normalized:
        return None
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _normalize_list(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def build_body_contract_fail_record(
    *,
    source_url: str,
    source_title: str,
    generated_title: str,
    category: str,
    article_subtype: str,
    validation_result: Mapping[str, Any],
    validation_action: str | None = None,
    body_excerpt: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _as_jst(now)
    action = str(validation_action or validation_result.get("action") or "fail").strip().lower()
    if action not in {"fail", "reroll"}:
        action = "fail"
    fail_axes = _normalize_list(validation_result.get("fail_axes"))

    return {
        "ts": current.isoformat(),
        "record_type": BODY_CONTRACT_FAIL_RECORD_TYPE,
        "skip_layer": BODY_CONTRACT_FAIL_SKIP_LAYER,
        "terminal_state": BODY_CONTRACT_FAIL_TERMINAL_STATE,
        "validation_action": action,
        "source_url": str(source_url or "").strip(),
        "source_url_hash": _hash_source_url(source_url),
        "source_title": str(source_title or "").strip(),
        "generated_title": str(generated_title or "").strip(),
        "category": str(category or "").strip(),
        "article_subtype": str(article_subtype or "").strip(),
        "fail_axes": fail_axes,
        "expected_first_block": str(validation_result.get("expected_first_block") or "").strip(),
        "actual_first_block": str(validation_result.get("actual_first_block") or "").strip(),
        "missing_required_blocks": _normalize_list(validation_result.get("missing_required_blocks")),
        "has_source_block": _coerce_bool(validation_result.get("has_source_block")),
        "stop_reason": str(validation_result.get("stop_reason") or "").strip(),
        "body_excerpt_hash": _hash_body_excerpt(body_excerpt),
        "suppressed_mail_count": 0,
    }


def _append_local_record(
    record_line: str,
    *,
    override: str | Path | None = None,
    logger: logging.Logger | None = None,
) -> Path | None:
    active_logger = logger or logging.getLogger("body_contract_fail_ledger")
    last_error: OSError | None = None
    for path in _candidate_local_paths(override):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(record_line)
                handle.write("\n")
            return path
        except OSError as exc:
            last_error = exc
            continue

    active_logger.warning(
        json.dumps(
            {
                "event": "body_contract_fail_history_local_append_failed",
                "record_type": BODY_CONTRACT_FAIL_RECORD_TYPE,
                "skip_layer": BODY_CONTRACT_FAIL_SKIP_LAYER,
                "reason": type(last_error).__name__ if last_error is not None else "OSError",
            },
            ensure_ascii=False,
        )
    )
    return None


def _default_gcs_client():
    try:
        from google.cloud import storage

        return storage.Client()
    except Exception:
        return None


def append_body_contract_fail_gcs_record(
    record_line: str,
    *,
    logger: logging.Logger | None = None,
    gcs_client: Any | None = None,
) -> bool:
    active_logger = logger or logging.getLogger("body_contract_fail_ledger")
    client = gcs_client if gcs_client is not None else _default_gcs_client()
    if client is None:
        return False
    try:
        from google.api_core.exceptions import PreconditionFailed
    except Exception:
        PreconditionFailed = None

    blob = client.bucket(BODY_CONTRACT_FAIL_STATE_BUCKET).blob(BODY_CONTRACT_FAIL_STATE_KEY)
    for _ in range(4):
        try:
            if blob.exists():
                blob.reload()
                generation = int(blob.generation or 0)
                existing_payload = blob.download_as_text(encoding="utf-8")
            else:
                generation = 0
                existing_payload = ""
            next_payload = existing_payload
            if next_payload and not next_payload.endswith("\n"):
                next_payload += "\n"
            next_payload += f"{record_line}\n"
            blob.upload_from_string(
                next_payload,
                content_type="application/x-ndjson",
                if_generation_match=generation if generation else 0,
            )
            return True
        except Exception as exc:
            if PreconditionFailed is not None and isinstance(exc, PreconditionFailed):
                continue
            active_logger.warning(
                json.dumps(
                    {
                        "event": "body_contract_fail_history_gcs_append_failed",
                        "record_type": BODY_CONTRACT_FAIL_RECORD_TYPE,
                        "skip_layer": BODY_CONTRACT_FAIL_SKIP_LAYER,
                        "reason": type(exc).__name__,
                    },
                    ensure_ascii=False,
                )
            )
            return False
    return False


def record_body_contract_fail(
    *,
    source_url: str,
    source_title: str,
    generated_title: str,
    category: str,
    article_subtype: str,
    validation_result: Mapping[str, Any],
    validation_action: str | None = None,
    body_excerpt: str = "",
    logger: logging.Logger | None = None,
    ledger_path: str | Path | None = None,
    gcs_client: Any | None = None,
    now: datetime | None = None,
) -> BodyContractFailLedgerResult:
    if not body_contract_fail_ledger_enabled():
        return BodyContractFailLedgerResult(status="gate_off", record=None, local_path=None)

    record = build_body_contract_fail_record(
        source_url=source_url,
        source_title=source_title,
        generated_title=generated_title,
        category=category,
        article_subtype=article_subtype,
        validation_result=validation_result,
        validation_action=validation_action,
        body_excerpt=body_excerpt,
        now=now,
    )
    record_line = json.dumps(record, ensure_ascii=False)
    local_path = _append_local_record(record_line, override=ledger_path, logger=logger)
    if local_path is None:
        return BodyContractFailLedgerResult(status="local_append_failed", record=record, local_path=None)

    append_body_contract_fail_gcs_record(record_line, logger=logger, gcs_client=gcs_client)
    return BodyContractFailLedgerResult(status="recorded", record=record, local_path=local_path)


__all__ = [
    "BODY_CONTRACT_FAIL_HISTORY_DEFAULT_PATH",
    "BODY_CONTRACT_FAIL_HISTORY_FALLBACK_PATH",
    "BODY_CONTRACT_FAIL_LEDGER_PATH_ENV",
    "BODY_CONTRACT_FAIL_RECORD_TYPE",
    "BODY_CONTRACT_FAIL_SKIP_LAYER",
    "BODY_CONTRACT_FAIL_STATE_BUCKET",
    "BODY_CONTRACT_FAIL_STATE_KEY",
    "BODY_CONTRACT_FAIL_TERMINAL_STATE",
    "BodyContractFailLedgerResult",
    "ENABLE_BODY_CONTRACT_FAIL_LEDGER_ENV",
    "append_body_contract_fail_gcs_record",
    "body_contract_fail_ledger_enabled",
    "build_body_contract_fail_record",
    "record_body_contract_fail",
    "resolve_body_contract_fail_ledger_path",
]
