"""Shared helpers for LLM call dedupe and guarded-publish refused cooldown."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_PATH = ROOT / "logs" / "llm_call_dedupe_ledger.jsonl"
DEFAULT_GUARDED_PUBLISH_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
DEFAULT_CACHE_HIT_SPLIT_METRIC_LEDGER_PATH = ROOT / "logs" / "cache_hit_split_metric_ledger.jsonl"
ENABLE_CACHE_HIT_SPLIT_METRIC_ENV = "ENABLE_CACHE_HIT_SPLIT_METRIC"
CACHE_HIT_SPLIT_METRIC_LEDGER_PATH_ENV = "CACHE_HIT_SPLIT_METRIC_LEDGER_PATH"
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_CACHE_HIT_KINDS = frozenset({"exact_hit", "cooldown_hit", "dedupe_hit", "unknown"})
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


def _env_enabled(name: str, *, env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(name, "0")).strip().lower() in TRUE_VALUES


def cache_hit_split_metric_enabled(*, env: Mapping[str, str] | None = None) -> bool:
    return _env_enabled(ENABLE_CACHE_HIT_SPLIT_METRIC_ENV, env=env)


def resolve_cache_hit_split_metric_ledger_path(*, env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    raw = str(source.get(CACHE_HIT_SPLIT_METRIC_LEDGER_PATH_ENV, "")).strip()
    if raw:
        return Path(raw)
    return DEFAULT_CACHE_HIT_SPLIT_METRIC_LEDGER_PATH


def normalize_hit_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _CACHE_HIT_KINDS:
        return normalized
    return "unknown"


def resolve_hit_kind(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return "unknown"
    return normalize_hit_kind(payload.get("hit_kind"))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record_cache_hit_metric(
    *,
    hit_kind: str,
    post_id: int | str | None = None,
    content_hash: str | None = None,
    prompt_template_id: str | None = None,
    model: str | None = None,
    cached_model: str | None = None,
    source_url_hash: str | None = None,
    cache_hit_reason: str | None = None,
    skip_reason: str | None = None,
    layer: str | None = None,
    ledger_path: str | Path | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    **extra: Any,
) -> dict[str, Any] | None:
    if not cache_hit_split_metric_enabled(env=env):
        return None

    payload: dict[str, Any] = {
        "timestamp": _now_jst(now).isoformat(),
        "event": "cache_hit_split_metric",
        "hit_kind": normalize_hit_kind(hit_kind),
        "post_id": _int_or_none(post_id),
        "content_hash": str(content_hash or ""),
        "prompt_template_id": str(prompt_template_id or ""),
        "model": str(model or ""),
        "cached_model": str(cached_model or ""),
        "source_url_hash": str(source_url_hash or ""),
        "cache_hit_reason": str(cache_hit_reason or ""),
        "skip_reason": str(skip_reason or ""),
        "layer": str(layer or ""),
    }
    for key, value in extra.items():
        payload[key] = value

    target = Path(ledger_path) if ledger_path is not None else resolve_cache_hit_split_metric_ledger_path(env=env)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str))
        handle.write("\n")
    return payload


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
    if str(skip_reason or "") == "content_hash_dedupe":
        record_cache_hit_metric(
            hit_kind="dedupe_hit",
            post_id=post_id,
            content_hash=content_hash,
            prompt_template_id=extra.get("prompt_template_id"),
            model=extra.get("model"),
            cached_model=extra.get("model"),
            source_url_hash=extra.get("source_url_hash"),
            cache_hit_reason="content_hash_dedupe",
            skip_reason=skip_reason,
            layer="llm_call_dedupe",
            now=now,
            reused_from_timestamp=extra.get("reused_from_timestamp"),
        )
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
    "DEFAULT_CACHE_HIT_SPLIT_METRIC_LEDGER_PATH",
    "DEFAULT_LEDGER_PATH",
    "ENABLE_CACHE_HIT_SPLIT_METRIC_ENV",
    "CACHE_HIT_SPLIT_METRIC_LEDGER_PATH_ENV",
    "cache_hit_split_metric_enabled",
    "compute_content_hash",
    "find_recent_record",
    "find_recent_refused_history",
    "is_recently_processed",
    "normalize_hit_kind",
    "record_call",
    "record_cache_hit_metric",
    "resolve_cache_hit_split_metric_ledger_path",
    "resolve_hit_kind",
]
