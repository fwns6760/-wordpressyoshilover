"""HMAC tokens for YouTube Shorts approval buttons.

The token signs a YouTube video id, not a WordPress post id.  Keep this
separate from ``publish_button_token`` so the two state-changing buttons do not
share payload semantics by accident.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from urllib.parse import urlencode


_DEFAULT_SECRET = "yoshilover_yt_shorts_approval_default_2026_06_13"
_TOKEN_HMAC_LENGTH = 24
_DEFAULT_TTL_SECONDS = 7 * 86400
_VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{6,64}$")


def is_valid_video_id(video_id: str | None) -> bool:
    return bool(_VIDEO_ID_RE.fullmatch(str(video_id or "").strip()))


def _resolve_secret() -> str:
    env_secret = os.getenv("YT_SHORTS_APPROVAL_TOKEN_SECRET", "").strip()
    fallback = os.getenv("PUBLISH_BUTTON_TOKEN_SECRET", "").strip()
    return env_secret or fallback or _DEFAULT_SECRET


def _compute_hmac(video_id: str, expiry: int) -> str:
    payload = f"yt_shorts:{video_id}:{expiry}".encode("utf-8")
    secret = _resolve_secret().encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:_TOKEN_HMAC_LENGTH]


def generate_yt_shorts_publish_token(
    video_id: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: int | float | None = None,
) -> str:
    vid = str(video_id or "").strip()
    if not is_valid_video_id(vid) or ttl_seconds <= 0:
        return ""
    current = int(now if now is not None else time.time())
    expiry = current + int(ttl_seconds)
    return f"{expiry}.{_compute_hmac(vid, expiry)}"


def verify_yt_shorts_publish_token(
    video_id: str,
    token: str,
    *,
    now: int | float | None = None,
) -> bool:
    vid = str(video_id or "").strip()
    raw_token = str(token or "").strip()
    if not is_valid_video_id(vid) or "." not in raw_token:
        return False
    expiry_part, _, hmac_part = raw_token.partition(".")
    if not expiry_part or not hmac_part:
        return False
    try:
        expiry = int(expiry_part)
    except (TypeError, ValueError):
        return False
    current = int(now if now is not None else time.time())
    if expiry <= current:
        return False
    expected = _compute_hmac(vid, expiry)
    return hmac.compare_digest(expected, hmac_part)


def build_yt_shorts_publish_url(
    video_id: str,
    fetcher_base_url: str | None,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: int | float | None = None,
) -> str | None:
    vid = str(video_id or "").strip()
    base = str(fetcher_base_url or "").strip().rstrip("/")
    if not is_valid_video_id(vid) or not base:
        return None
    token = generate_yt_shorts_publish_token(vid, ttl_seconds=ttl_seconds, now=now)
    if not token:
        return None
    return f"{base}/yt-shorts-publish?{urlencode({'video_id': vid, 'token': token})}"


__all__ = [
    "build_yt_shorts_publish_url",
    "generate_yt_shorts_publish_token",
    "is_valid_video_id",
    "verify_yt_shorts_publish_token",
]
