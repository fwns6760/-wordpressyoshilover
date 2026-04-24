"""Local JSONL emitter for ticket 079 nucleus ledger entries."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.nucleus_ledger_adapter import (
    validator_result_to_context_flags,
    validator_result_to_fail_tags,
)
from src.title_body_nucleus_validator import validate_title_body_nucleus


JST = timezone(timedelta(hours=9))
ENV_EMIT_ENABLED = "NUCLEUS_LEDGER_EMIT_ENABLED"
ENV_SINK_DIR = "NUCLEUS_LEDGER_SINK_DIR"
ENV_PROMPT_VERSION = "NUCLEUS_LEDGER_PROMPT_VERSION"
ENV_TEMPLATE_VERSION = "NUCLEUS_LEDGER_TEMPLATE_VERSION"
DEFAULT_SINK_DIR = Path(__file__).resolve().parent.parent / "logs" / "nucleus_ledger"


@dataclass(frozen=True)
class DraftMeta:
    draft_id: int | str | None = None
    candidate_key: str | None = None
    subtype: str | None = None
    source_trust: str | None = None
    source_family: str | None = None
    chosen_lane: str = "fixed"
    chosen_model: str | None = None
    prompt_version: str | None = None
    template_version: str | None = None


@dataclass(frozen=True)
class NucleusLedgerEmitResult:
    status: str
    entry: dict | None
    sink_path: Path | None
    reason: str | None = None


def _clean_optional(value: object) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return text or None


def _as_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _is_enabled(enabled: bool | None) -> bool:
    if enabled is True:
        return True
    if enabled is False:
        return False
    return os.getenv(ENV_EMIT_ENABLED, "").strip() == "1"


def resolve_sink_dir(override: str | Path | None = None) -> Path:
    if override is not None and str(override).strip():
        return Path(override)
    env_value = os.getenv(ENV_SINK_DIR, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_SINK_DIR


def build_ledger_entry(
    draft_meta: DraftMeta,
    title: str,
    body: str,
    *,
    now: datetime | None = None,
) -> dict:
    current = _as_jst(now)
    validator_subtype = str(draft_meta.subtype or "fact_notice")
    result = validate_title_body_nucleus(title or "", body or "", validator_subtype)
    fail_tags = validator_result_to_fail_tags(result)
    context_flags = validator_result_to_context_flags(result)

    return {
        "date": current.strftime("%Y-%m-%d"),
        "draft_id": _clean_optional(draft_meta.draft_id),
        "candidate_key": _clean_optional(draft_meta.candidate_key),
        "subtype": _clean_optional(draft_meta.subtype),
        "fail_tags": fail_tags,
        "context_flags": context_flags,
        "source_trust": _clean_optional(draft_meta.source_trust),
        "source_family": _clean_optional(draft_meta.source_family),
        "chosen_lane": _clean_optional(draft_meta.chosen_lane) or "fixed",
        "chosen_model": _clean_optional(draft_meta.chosen_model),
        "prompt_version": _clean_optional(draft_meta.prompt_version) or _clean_optional(os.getenv(ENV_PROMPT_VERSION)),
        "template_version": _clean_optional(draft_meta.template_version)
        or _clean_optional(os.getenv(ENV_TEMPLATE_VERSION)),
        "repair_applied": "no",
        "repair_trigger": None,
        "repair_actions": [],
        "source_recheck_used": "no",
        "search_used": "no",
        "changed_scope": None,
        "outcome": "accept_draft",
        "note": None,
    }


def emit_nucleus_ledger_entry(
    draft_meta: DraftMeta,
    title: str,
    body: str,
    *,
    enabled: bool | None = None,
    sink_dir: str | Path | None = None,
    now: datetime | None = None,
) -> NucleusLedgerEmitResult:
    if not _is_enabled(enabled):
        return NucleusLedgerEmitResult(status="gate_off", entry=None, sink_path=None)

    entry = build_ledger_entry(draft_meta, title, body, now=now)
    sink_root = resolve_sink_dir(sink_dir)
    sink_path = sink_root / f"{entry['date']}.jsonl"

    try:
        sink_root.mkdir(parents=True, exist_ok=True)
        with sink_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False))
            handle.write("\n")
    except Exception as exc:
        return NucleusLedgerEmitResult(
            status="error",
            entry=entry,
            sink_path=sink_path,
            reason=str(exc),
        )

    return NucleusLedgerEmitResult(status="emitted", entry=entry, sink_path=sink_path)


__all__ = [
    "DEFAULT_SINK_DIR",
    "DraftMeta",
    "ENV_EMIT_ENABLED",
    "ENV_PROMPT_VERSION",
    "ENV_SINK_DIR",
    "ENV_TEMPLATE_VERSION",
    "JST",
    "NucleusLedgerEmitResult",
    "build_ledger_entry",
    "emit_nucleus_ledger_entry",
    "resolve_sink_dir",
]
