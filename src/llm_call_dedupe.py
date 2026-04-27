"""Shared helpers for LLM call dedupe and guarded-publish refused cooldown."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_PATH = ROOT / "logs" / "llm_call_dedupe_ledger.jsonl"
DEFAULT_GUARDED_PUBLISH_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
_CONTENT_HASH_SKIP_REASONS = frozenset({"refused_cooldown"})


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _read_jsonl_rows(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def compute_content_hash(post_id: int, body_text: str) -> str:
    del post_id
    normalized = str(body_text or "").strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def find_recent_record(
    post_id: int,
    content_hash: str,
    ledger_path: str | Path,
    cooldown_hours: int = 24,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    threshold = _now_jst(now) - timedelta(hours=max(int(cooldown_hours), 0))
    for payload in reversed(_read_jsonl_rows(ledger_path)):
        try:
            row_post_id = int(payload.get("post_id"))
        except (TypeError, ValueError):
            continue
        if row_post_id != int(post_id):
            continue
        if str(payload.get("content_hash") or "") != str(content_hash):
            continue
        if str(payload.get("skip_reason") or "") in _CONTENT_HASH_SKIP_REASONS:
            continue
        timestamp = _parse_ts(payload.get("timestamp"))
        if timestamp is None or timestamp < threshold:
            continue
        return dict(payload)
    return None


def is_recently_processed(
    post_id: int,
    content_hash: str,
    ledger_path: str | Path,
    cooldown_hours: int = 24,
    *,
    now: datetime | None = None,
) -> bool:
    return find_recent_record(
        post_id,
        content_hash,
        ledger_path,
        cooldown_hours,
        now=now,
    ) is not None


def record_call(
    post_id: int,
    content_hash: str,
    result: str,
    skip_reason: str | None = None,
    *,
    ledger_path: str | Path = DEFAULT_LEDGER_PATH,
    now: datetime | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "timestamp": _now_jst(now).isoformat(),
        "post_id": int(post_id),
        "content_hash": str(content_hash),
        "result": str(result),
        "skip_reason": skip_reason,
    }
    for key, value in extra.items():
        payload[key] = value

    target = Path(ledger_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str))
        handle.write("\n")
    return payload


def find_recent_refused_history(
    post_id: int,
    history_path: str | Path = DEFAULT_GUARDED_PUBLISH_HISTORY_PATH,
    cooldown_hours: int = 24,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    threshold = _now_jst(now) - timedelta(hours=max(int(cooldown_hours), 0))
    for payload in reversed(_read_jsonl_rows(history_path)):
        try:
            row_post_id = int(payload.get("post_id"))
        except (TypeError, ValueError):
            continue
        if row_post_id != int(post_id):
            continue
        if str(payload.get("status") or "") != "refused":
            continue
        timestamp = _parse_ts(payload.get("ts"))
        if timestamp is None:
            return dict(payload)
        if timestamp >= threshold:
            return dict(payload)
    return None


__all__ = [
    "DEFAULT_GUARDED_PUBLISH_HISTORY_PATH",
    "DEFAULT_LEDGER_PATH",
    "compute_content_hash",
    "find_recent_record",
    "find_recent_refused_history",
    "is_recently_processed",
    "record_call",
]
