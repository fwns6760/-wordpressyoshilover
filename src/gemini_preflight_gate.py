"""Gemini preflight article gate (282-COST).

Before `_gemini_cache_lookup`, decide whether the candidate is worth a Gemini
call at all. This is meta-level dedupe (subtype / duplicate / giants
relevance / placeholder etc.), distinct from 229-COST content-hash dedupe.

Default OFF via ENABLE_GEMINI_PREFLIGHT.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from body_validator import is_supported_subtype as _body_validator_supports_subtype
except ImportError:  # pragma: no cover - package import for tests
    from src.body_validator import is_supported_subtype as _body_validator_supports_subtype

try:
    from title_validator import title_has_person_name_candidate as _title_has_person_name_candidate
except ImportError:  # pragma: no cover - package import for tests
    from src.title_validator import title_has_person_name_candidate as _title_has_person_name_candidate

try:
    from source_trust import (
        classify_handle as _source_trust_classify_handle,
        classify_url as _source_trust_classify_url,
        classify_url_family as _source_trust_classify_url_family,
        get_family_trust_level as _source_trust_get_family_trust_level,
    )
except ImportError:  # pragma: no cover - package import for tests
    from src.source_trust import (
        classify_handle as _source_trust_classify_handle,
        classify_url as _source_trust_classify_url,
        classify_url_family as _source_trust_classify_url_family,
        get_family_trust_level as _source_trust_get_family_trust_level,
    )


TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
PREFLIGHT_ENV_FLAG = "ENABLE_GEMINI_PREFLIGHT"
LIVE_UPDATE_ENV_FLAG = "ENABLE_LIVE_UPDATE_ARTICLES"
PREFLIGHT_SKIP_LAYER = "preflight"

_BACKLOG_CUTOFF_HOURS = 6.0
_FARM_RESULT_MAX_AGE_HOURS = 24.0
_PLACEHOLDER_MIN_BODY_CHARS = 40
_PLACEHOLDER_MARKER_RE = re.compile(
    r"(placeholder|試合の詳細はこちら|詳しくはこちら|詳細はこちら|coming soon|追記予定|更新予定|tbd)",
    re.IGNORECASE,
)
_DEATH_OR_GRAVE_RE = re.compile(r"(死亡|死去|逝去|亡くな|危篤|重体|重症|重傷|意識不明|救急搬送)")
_GIANTS_MARKER_RE = re.compile(r"(巨人|ジャイアンツ|読売ジャイアンツ|読売|東京ドーム|yomiuri giants)", re.IGNORECASE)
_GIANTS_SOURCE_HANDLE_RE = re.compile(
    r"(tokyogiants|yomiuri[_-]?giants|hochi[_-]?giants|sanspo[_-]?giants)",
    re.IGNORECASE,
)
_DEATH_CONTEXT_RE = re.compile(r"(選手|投手|監督|コーチ|OB|関係者)")
_SOCIAL_OR_RUMOR_HOST_RE = re.compile(
    r"(x\.com|twitter\.com|2ch|5ch|ameblo\.jp|livedoor\.jp|note\.com|reddit\.com|redd\.it)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PreflightSkipResult:
    skip_reason: str


def _env_enabled(name: str, default: str = "") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in TRUTHY_ENV_VALUES


def _normalize_subtype(value: Any) -> str:
    subtype = str(value or "").strip().lower()
    if subtype.startswith("farm_result"):
        return "farm_result"
    return subtype


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _candidate_age_hours(candidate: dict[str, Any], now: datetime | None) -> float | None:
    raw_age = candidate.get("age_hours")
    try:
        if raw_age is not None:
            parsed = float(raw_age)
            if parsed >= 0:
                return parsed
    except (TypeError, ValueError):
        pass
    published_at = _parse_datetime(candidate.get("published_at"))
    if published_at is None:
        return None
    current = _parse_datetime(now) if now is not None else datetime.now(timezone.utc)
    if current is None:
        current = datetime.now(timezone.utc)
    delta = current - published_at
    return max(delta.total_seconds() / 3600.0, 0.0)


def _candidate_body_text(candidate: dict[str, Any]) -> str:
    parts = [
        str(candidate.get("body_text") or "").strip(),
        str(candidate.get("source_body") or "").strip(),
        str(candidate.get("summary") or "").strip(),
        str(candidate.get("source_fact_text") or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def _candidate_source_urls(candidate: dict[str, Any]) -> tuple[str, ...]:
    urls: list[str] = []
    primary = str(candidate.get("source_url") or "").strip()
    if primary:
        urls.append(primary)
    for link in candidate.get("source_links") or ():
        if isinstance(link, str):
            value = link.strip()
        elif isinstance(link, dict):
            value = str(link.get("url") or link.get("href") or "").strip()
        else:
            value = ""
        if value:
            urls.append(value)
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return tuple(deduped)


def _source_is_authoritative(url: str) -> bool:
    trust = _source_trust_classify_url(url)
    if trust in {"primary", "secondary"}:
        return True
    family = _source_trust_classify_url_family(url)
    return _source_trust_get_family_trust_level(family) in {"high", "mid-high", "mid"}


def _has_authoritative_source(candidate: dict[str, Any]) -> bool:
    source_handle = str(candidate.get("source_handle") or "").strip()
    if source_handle and _source_trust_classify_handle(source_handle) in {"primary", "secondary"}:
        return True
    return any(_source_is_authoritative(url) for url in _candidate_source_urls(candidate))


def _is_social_or_rumor_candidate(candidate: dict[str, Any]) -> bool:
    source_type = str(candidate.get("source_type") or "").strip().lower()
    if source_type in {"social_news", "social"}:
        return True
    return any(_SOCIAL_OR_RUMOR_HOST_RE.search(url or "") for url in _candidate_source_urls(candidate))


def _looks_giants_related(candidate: dict[str, Any]) -> bool:
    forced = candidate.get("is_giants_related")
    if isinstance(forced, bool):
        return forced
    title = str(candidate.get("title") or "").strip()
    source_name = str(candidate.get("source_name") or "").strip()
    source_handle = str(candidate.get("source_handle") or "").strip()
    source_blob = " ".join(
        part
        for part in (
            title,
            _candidate_body_text(candidate),
            source_name,
            source_handle,
            " ".join(_candidate_source_urls(candidate)),
        )
        if part
    )
    if _GIANTS_MARKER_RE.search(source_blob):
        return True
    if _GIANTS_SOURCE_HANDLE_RE.search(source_blob):
        return True
    return False


def _skip_existing_publish_same_source_url(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    if bool(candidate.get("existing_publish_same_source_url")):
        return True
    duplicate_guard_context = candidate.get("duplicate_guard_context")
    return isinstance(duplicate_guard_context, dict) and bool(duplicate_guard_context.get("existing_publish_same_source_url"))


def _skip_placeholder_body(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    body_text = _candidate_body_text(candidate)
    if not body_text:
        return True
    if _PLACEHOLDER_MARKER_RE.search(body_text):
        return True
    subtype = _normalize_subtype(candidate.get("article_subtype"))
    if _body_validator_supports_subtype(subtype) and len(body_text) < _PLACEHOLDER_MIN_BODY_CHARS:
        return True
    return False


def _skip_not_giants_related(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    return not _looks_giants_related(candidate)


def _skip_live_update_target_disabled(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    return _normalize_subtype(candidate.get("article_subtype")) == "live_update" and not _env_enabled(
        LIVE_UPDATE_ENV_FLAG,
        "0",
    )


def _skip_farm_lineup_backlog_blocked(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    if _normalize_subtype(candidate.get("article_subtype")) != "farm_lineup":
        return False
    is_backlog = candidate.get("is_backlog")
    if isinstance(is_backlog, bool):
        return is_backlog
    age_hours = _candidate_age_hours(candidate, now)
    return age_hours is not None and age_hours > _BACKLOG_CUTOFF_HOURS


def _skip_farm_result_age_exceeded(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    if _normalize_subtype(candidate.get("article_subtype")) != "farm_result":
        return False
    age_hours = _candidate_age_hours(candidate, now)
    return age_hours is not None and age_hours >= _FARM_RESULT_MAX_AGE_HOURS


def _skip_unofficial_source_only(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    if not _is_social_or_rumor_candidate(candidate):
        return False
    return not _has_authoritative_source(candidate)


def _skip_expected_hard_stop_death_or_grave(candidate: dict[str, Any], *, now: datetime | None) -> bool:
    if not _looks_giants_related(candidate):
        return False
    title = str(candidate.get("title") or "").strip()
    combined = "\n".join(part for part in (title, _candidate_body_text(candidate)) if part)
    if not _DEATH_OR_GRAVE_RE.search(combined):
        return False
    if _title_has_person_name_candidate(title):
        return True
    return bool(_DEATH_CONTEXT_RE.search(combined))


_SKIP_RULES: tuple[tuple[str, Any], ...] = (
    ("existing_publish_same_source_url", _skip_existing_publish_same_source_url),
    ("placeholder_body", _skip_placeholder_body),
    ("not_giants_related", _skip_not_giants_related),
    ("live_update_target_disabled", _skip_live_update_target_disabled),
    ("farm_lineup_backlog_blocked", _skip_farm_lineup_backlog_blocked),
    ("farm_result_age_exceeded", _skip_farm_result_age_exceeded),
    ("unofficial_source_only", _skip_unofficial_source_only),
    ("expected_hard_stop_death_or_grave", _skip_expected_hard_stop_death_or_grave),
)


def should_skip_gemini(candidate: dict[str, Any], *, now: datetime | None = None) -> tuple[bool, str | None]:
    if not _env_enabled(PREFLIGHT_ENV_FLAG):
        return False, None
    payload = dict(candidate or {})
    for skip_reason, predicate in _SKIP_RULES:
        if predicate(payload, now=now):
            return True, skip_reason
    return False, None


def emit_gemini_call_skipped(logger, *, candidate: dict[str, Any], skip_reason: str) -> None:
    payload = {
        "event": "gemini_call_skipped",
        "post_url": str(candidate.get("post_url") or candidate.get("source_url") or ""),
        "source_url_hash": str(candidate.get("source_url_hash") or ""),
        "content_hash": str(candidate.get("content_hash") or ""),
        "subtype": str(candidate.get("article_subtype") or ""),
        "skip_reason": str(skip_reason or ""),
        "skip_layer": PREFLIGHT_SKIP_LAYER,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))
