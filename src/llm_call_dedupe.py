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
ENABLE_GEMINI_CACHE_MISS_BREAKER_ENV = "ENABLE_GEMINI_CACHE_MISS_BREAKER"
GEMINI_CACHE_MISS_BREAKER_THRESHOLD_ENV = "GEMINI_CACHE_MISS_BREAKER_THRESHOLD"
GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS_ENV = "GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS"
ENABLE_PER_POST_24H_GEMINI_BUDGET_ENV = "ENABLE_PER_POST_24H_GEMINI_BUDGET"
PER_POST_24H_GEMINI_BUDGET_LIMIT_ENV = "PER_POST_24H_GEMINI_BUDGET_LIMIT"
DEFAULT_GEMINI_CACHE_MISS_BREAKER_THRESHOLD = 0.5
DEFAULT_GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS = 3600
DEFAULT_PER_POST_24H_GEMINI_BUDGET_LIMIT = 5
PER_POST_24H_GEMINI_BUDGET_WINDOW_HOURS = 24
GEMINI_CACHE_OUTCOME_EVENT = "gemini_cache_outcome"
GEMINI_CALL_ATTEMPT_EVENT = "gemini_call_attempt"
GEMINI_CACHE_MISS_BREAKER_SKIP_REASON = "cache_miss_circuit_breaker"
PER_POST_24H_GEMINI_BUDGET_SKIP_REASON = "per_post_24h_gemini_budget_exhausted"
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


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    env: Mapping[str, str] | None = None,
) -> float:
    source = os.environ if env is None else env
    raw = str(source.get(name, "")).strip()
    try:
        value = float(raw) if raw else float(default)
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    source = os.environ if env is None else env
    raw = str(source.get(name, "")).strip()
    try:
        value = int(raw) if raw else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        value = max(value, minimum)
    return value


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


def gemini_cache_miss_breaker_enabled(*, env: Mapping[str, str] | None = None) -> bool:
    return _env_enabled(ENABLE_GEMINI_CACHE_MISS_BREAKER_ENV, env=env)


def resolve_gemini_cache_miss_breaker_threshold(*, env: Mapping[str, str] | None = None) -> float:
    return _env_float(
        GEMINI_CACHE_MISS_BREAKER_THRESHOLD_ENV,
        DEFAULT_GEMINI_CACHE_MISS_BREAKER_THRESHOLD,
        minimum=0.0,
        maximum=1.0,
        env=env,
    )


def resolve_gemini_cache_miss_breaker_window_seconds(*, env: Mapping[str, str] | None = None) -> int:
    return _env_int(
        GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS_ENV,
        DEFAULT_GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS,
        minimum=1,
        env=env,
    )


def per_post_24h_gemini_budget_enabled(*, env: Mapping[str, str] | None = None) -> bool:
    return _env_enabled(ENABLE_PER_POST_24H_GEMINI_BUDGET_ENV, env=env)


def resolve_per_post_24h_gemini_budget_limit(*, env: Mapping[str, str] | None = None) -> int:
    return _env_int(
        PER_POST_24H_GEMINI_BUDGET_LIMIT_ENV,
        DEFAULT_PER_POST_24H_GEMINI_BUDGET_LIMIT,
        minimum=0,
        env=env,
    )


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


def record_gemini_cache_outcome(
    *,
    cache_hit_reason: str,
    hit_kind: str = "unknown",
    post_id: int | str | None = None,
    content_hash: str | None = None,
    prompt_template_id: str | None = None,
    source_url_hash: str | None = None,
    ledger_path: str | Path | None = None,
    now: datetime | None = None,
    **extra: Any,
) -> dict[str, Any]:
    normalized_reason = str(cache_hit_reason or "").strip().lower()
    if normalized_reason in {"content_hash_exact", "cooldown_active", "content_hash_dedupe"}:
        cache_outcome = "hit"
    elif normalized_reason == "miss":
        cache_outcome = "miss"
    else:
        cache_outcome = "unknown"

    payload = {
        "timestamp": _now_jst(now).isoformat(),
        "event": GEMINI_CACHE_OUTCOME_EVENT,
        "cache_outcome": cache_outcome,
        "cache_hit_reason": normalized_reason,
        "hit_kind": normalize_hit_kind(hit_kind),
        "post_id": _int_or_none(post_id),
        "content_hash": str(content_hash or ""),
        "prompt_template_id": str(prompt_template_id or ""),
        "source_url_hash": str(source_url_hash or ""),
    }
    for key, value in extra.items():
        payload[key] = value

    target = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str))
        handle.write("\n")
    return payload


def record_gemini_call_attempt(
    *,
    post_id: int | str,
    content_hash: str | None = None,
    prompt_template_id: str | None = None,
    source_url_hash: str | None = None,
    provider: str = "gemini",
    model: str | None = None,
    ledger_path: str | Path | None = None,
    now: datetime | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "timestamp": _now_jst(now).isoformat(),
        "event": GEMINI_CALL_ATTEMPT_EVENT,
        "post_id": int(post_id),
        "content_hash": str(content_hash or ""),
        "prompt_template_id": str(prompt_template_id or ""),
        "source_url_hash": str(source_url_hash or ""),
        "provider": str(provider or "gemini"),
        "model": str(model or ""),
    }
    for key, value in extra.items():
        payload[key] = value

    target = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str))
        handle.write("\n")
    return payload


def _breaker_row_outcome(payload: Mapping[str, Any]) -> str | None:
    event = str(payload.get("event") or "").strip()
    if event == GEMINI_CACHE_OUTCOME_EVENT:
        outcome = str(payload.get("cache_outcome") or "").strip().lower()
        if outcome in {"hit", "miss"}:
            return outcome
        normalized_reason = str(payload.get("cache_hit_reason") or "").strip().lower()
        if normalized_reason in {"content_hash_exact", "cooldown_active", "content_hash_dedupe"}:
            return "hit"
        if normalized_reason == "miss":
            return "miss"
        return None

    skip_reason = str(payload.get("skip_reason") or "").strip().lower()
    if skip_reason == "content_hash_dedupe":
        return "hit"

    provider = str(payload.get("provider") or "").strip().lower()
    model = str(payload.get("model") or "").strip().lower()
    result = str(payload.get("result") or "").strip().lower()
    if provider == "gemini" or model.startswith("gemini-"):
        if not skip_reason and result in {"generated", "failed"}:
            return "miss"
    return None


def evaluate_gemini_cache_miss_breaker(
    *,
    ledger_path: str | Path | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    current = _now_jst(now)
    window_seconds = resolve_gemini_cache_miss_breaker_window_seconds(env=env)
    threshold = resolve_gemini_cache_miss_breaker_threshold(env=env)
    window_start = current - timedelta(seconds=window_seconds)
    enabled = gemini_cache_miss_breaker_enabled(env=env)

    miss_count = 0
    hit_count = 0
    hit_kind_counts: dict[str, int] = {}
    target = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER_PATH
    for payload in _read_jsonl_rows(target):
        timestamp = _parse_ts(payload.get("timestamp"))
        if timestamp is None or timestamp < window_start:
            continue
        outcome = _breaker_row_outcome(payload)
        if outcome == "miss":
            miss_count += 1
            continue
        if outcome != "hit":
            continue
        hit_count += 1
        hit_kind = resolve_hit_kind(payload)
        hit_kind_counts[hit_kind] = hit_kind_counts.get(hit_kind, 0) + 1

    total_count = miss_count + hit_count
    miss_rate = (miss_count / total_count) if total_count else 0.0
    tripped = enabled and total_count > 0 and miss_rate > threshold
    return {
        "enabled": enabled,
        "tripped": tripped,
        "threshold": threshold,
        "window_seconds": window_seconds,
        "window_start": window_start.isoformat(),
        "window_end": current.isoformat(),
        "miss_count": miss_count,
        "hit_count": hit_count,
        "total_count": total_count,
        "miss_rate": miss_rate,
        "hit_kind_counts": hit_kind_counts,
        "skip_reason": GEMINI_CACHE_MISS_BREAKER_SKIP_REASON if tripped else None,
    }


def _is_gemini_attempt_row(payload: Mapping[str, Any]) -> bool:
    if str(payload.get("event") or "").strip() == GEMINI_CALL_ATTEMPT_EVENT:
        return True

    if str(payload.get("skip_reason") or "").strip():
        return False

    provider = str(payload.get("provider") or "").strip().lower()
    model = str(payload.get("model") or "").strip().lower()
    result = str(payload.get("result") or "").strip().lower()
    if provider == "gemini" or model.startswith("gemini-"):
        return result in {"generated", "failed"}
    return False


def _is_gemini_cache_miss_row(payload: Mapping[str, Any]) -> bool:
    if str(payload.get("event") or "").strip() != GEMINI_CACHE_OUTCOME_EVENT:
        return False
    cache_outcome = str(payload.get("cache_outcome") or "").strip().lower()
    if cache_outcome:
        return cache_outcome == "miss"
    return str(payload.get("cache_hit_reason") or "").strip().lower() == "miss"


def evaluate_per_post_24h_gemini_budget(
    post_id: int | str | None,
    *,
    ledger_path: str | Path | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    current = _now_jst(now)
    window_start = current - timedelta(hours=PER_POST_24H_GEMINI_BUDGET_WINDOW_HOURS)
    enabled = per_post_24h_gemini_budget_enabled(env=env)
    limit = resolve_per_post_24h_gemini_budget_limit(env=env)
    normalized_post_id = _int_or_none(post_id)

    explicit_attempt_count = 0
    cache_miss_fallback_count = 0
    target = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER_PATH
    if normalized_post_id is not None:
        for payload in _read_jsonl_rows(target):
            row_post_id = _int_or_none(payload.get("post_id"))
            if row_post_id != normalized_post_id:
                continue
            timestamp = _parse_ts(payload.get("timestamp"))
            if timestamp is None or timestamp < window_start:
                continue
            if _is_gemini_attempt_row(payload):
                explicit_attempt_count += 1
                continue
            if _is_gemini_cache_miss_row(payload):
                cache_miss_fallback_count += 1

    if explicit_attempt_count > 0:
        call_count = explicit_attempt_count
        count_source = "explicit_attempts"
    else:
        call_count = cache_miss_fallback_count
        count_source = "cache_miss_fallback" if cache_miss_fallback_count > 0 else "none"

    remaining_calls = max(limit - call_count, 0)
    applicable = normalized_post_id is not None
    tripped = enabled and applicable and remaining_calls <= 0
    return {
        "enabled": enabled,
        "applicable": applicable,
        "post_id": normalized_post_id,
        "limit": limit,
        "window_hours": PER_POST_24H_GEMINI_BUDGET_WINDOW_HOURS,
        "window_start": window_start.isoformat(),
        "window_end": current.isoformat(),
        "count_source": count_source,
        "call_count": call_count,
        "remaining_calls": remaining_calls,
        "tripped": tripped,
        "skip_reason": PER_POST_24H_GEMINI_BUDGET_SKIP_REASON if tripped else None,
    }


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
    "ENABLE_GEMINI_CACHE_MISS_BREAKER_ENV",
    "ENABLE_PER_POST_24H_GEMINI_BUDGET_ENV",
    "GEMINI_CACHE_MISS_BREAKER_THRESHOLD_ENV",
    "GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS_ENV",
    "PER_POST_24H_GEMINI_BUDGET_LIMIT_ENV",
    "DEFAULT_GEMINI_CACHE_MISS_BREAKER_THRESHOLD",
    "DEFAULT_GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS",
    "DEFAULT_PER_POST_24H_GEMINI_BUDGET_LIMIT",
    "PER_POST_24H_GEMINI_BUDGET_WINDOW_HOURS",
    "GEMINI_CACHE_MISS_BREAKER_SKIP_REASON",
    "PER_POST_24H_GEMINI_BUDGET_SKIP_REASON",
    "cache_hit_split_metric_enabled",
    "compute_content_hash",
    "evaluate_per_post_24h_gemini_budget",
    "evaluate_gemini_cache_miss_breaker",
    "find_recent_record",
    "find_recent_refused_history",
    "gemini_cache_miss_breaker_enabled",
    "is_recently_processed",
    "normalize_hit_kind",
    "per_post_24h_gemini_budget_enabled",
    "record_call",
    "record_cache_hit_metric",
    "record_gemini_call_attempt",
    "record_gemini_cache_outcome",
    "resolve_cache_hit_split_metric_ledger_path",
    "resolve_gemini_cache_miss_breaker_threshold",
    "resolve_gemini_cache_miss_breaker_window_seconds",
    "resolve_per_post_24h_gemini_budget_limit",
    "resolve_hit_kind",
]
