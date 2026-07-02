"""Shared Gemini model selection policy.

Default policy:
- JST 17:00-22:29 uses the primary model.
- Other hours use the fallback model.

The defaults are intentionally the same as the X-post lane so article and
repair lanes do not drift back to deprecated 2.x model IDs.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Mapping


DEFAULT_PRIMARY_MODEL = "gemini-3.5-flash"
DEFAULT_FALLBACK_MODEL = "gemini-3.1-flash-lite"
DEFAULT_PRIMARY_HOURS_JST = "17:00-22:30"

PRIMARY_MODEL_ENV = "GEMINI_PRIMARY_MODEL"
FALLBACK_MODEL_ENV = "GEMINI_FALLBACK_MODEL"
PRIMARY_HOURS_ENV = "GEMINI_PRIMARY_HOURS_JST"

JST = timezone(timedelta(hours=9))


def _env_value(env: Mapping[str, str], key: str, default: str) -> str:
    value = str(env.get(key, "")).strip()
    return value or default


def primary_model(env: Mapping[str, str] | None = None) -> str:
    return _env_value(env or os.environ, PRIMARY_MODEL_ENV, DEFAULT_PRIMARY_MODEL)


def fallback_model(env: Mapping[str, str] | None = None) -> str:
    return _env_value(env or os.environ, FALLBACK_MODEL_ENV, DEFAULT_FALLBACK_MODEL)


def primary_hours_jst(env: Mapping[str, str] | None = None) -> str:
    return _env_value(env or os.environ, PRIMARY_HOURS_ENV, DEFAULT_PRIMARY_HOURS_JST)


def _parse_time_point(value: str, *, allow_24: bool = False) -> int:
    raw = value.strip()
    if ":" in raw:
        hour_s, minute_s = raw.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s)
    else:
        hour = int(raw)
        minute = 0
    max_hour = 24 if allow_24 else 23
    if not (0 <= hour <= max_hour) or not (0 <= minute <= 59):
        raise ValueError(f"invalid time point: {value!r}")
    if hour == 24 and minute != 0:
        raise ValueError(f"invalid 24h time point: {value!r}")
    return hour * 60 + minute


def in_primary_hours(now: datetime | None = None, hours_spec: str | None = None) -> bool:
    """Return whether JST time is inside the primary model window.

    Invalid hour specs fail open to primary so a bad env value does not silently
    downgrade the night lane.
    """
    spec = (hours_spec if hours_spec is not None else primary_hours_jst()).strip()
    if not spec:
        return True
    try:
        start_s, end_s = spec.split("-", 1)
        start = _parse_time_point(start_s)
        end = _parse_time_point(end_s, allow_24=True)
    except ValueError:
        return True
    current = (now or datetime.now(JST)).astimezone(JST)
    minute_of_day = current.hour * 60 + current.minute
    if start <= end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end


def select_gemini_model(
    now: datetime | None = None,
    *,
    env: Mapping[str, str] | None = None,
    primary: str | None = None,
    fallback: str | None = None,
    hours_spec: str | None = None,
) -> str:
    env_map = env or os.environ
    primary_id = (primary or primary_model(env_map)).strip() or DEFAULT_PRIMARY_MODEL
    fallback_id = (fallback or fallback_model(env_map)).strip() or DEFAULT_FALLBACK_MODEL
    spec = hours_spec if hours_spec is not None else primary_hours_jst(env_map)
    return primary_id if in_primary_hours(now, spec) else fallback_id


def generate_content_url(api_key: str, model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent?key={api_key}"
    )


__all__ = [
    "DEFAULT_FALLBACK_MODEL",
    "DEFAULT_PRIMARY_HOURS_JST",
    "DEFAULT_PRIMARY_MODEL",
    "FALLBACK_MODEL_ENV",
    "PRIMARY_HOURS_ENV",
    "PRIMARY_MODEL_ENV",
    "fallback_model",
    "generate_content_url",
    "in_primary_hours",
    "primary_hours_jst",
    "primary_model",
    "select_gemini_model",
]
