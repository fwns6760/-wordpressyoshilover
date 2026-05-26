"""437 Phase 2A-ext (2026-05-26): x-post-mail-lane の候補ごと share-x button 用 HMAC + expiry token.

publish-notice 側の ``publish_button_token`` (379-OPS) は WP post_id を sign するが、
こちらは GCS blob_key を sign する。 x-post-mail-lane の候補ごと ranking PNG を GCS に
upload し、 そのオブジェクトキーで /share-x-cand から取得する経路で使う。

token format: ``{expiry_unix_seconds}.{hmac_hex24}``
- ``expiry_unix_seconds``: token 有効期限 (UTC unix timestamp、 整数)
- ``hmac_hex24``: ``HMAC-SHA256(secret, f"{blob_key}:{expiry}").hexdigest()[:24]``

secret は env ``SHARE_X_CAND_TOKEN_SECRET`` を優先、 未設定時は
``PUBLISH_BUTTON_TOKEN_SECRET`` (publish-notice と同じ)、 さらに未設定なら default constant。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

_DEFAULT_SECRET = "yoshilover_share_x_cand_default_2026_05_26"
_TOKEN_HMAC_LENGTH = 24
_DEFAULT_TTL_SECONDS = 86400  # 24 時間


def _resolve_secret() -> str:
    env_secret = os.getenv("SHARE_X_CAND_TOKEN_SECRET", "").strip()
    if env_secret:
        return env_secret
    fallback = os.getenv("PUBLISH_BUTTON_TOKEN_SECRET", "").strip()
    return fallback or _DEFAULT_SECRET


def _compute_hmac(blob_key: str, expiry: int) -> str:
    secret = _resolve_secret().encode("utf-8")
    payload = f"{blob_key}:{expiry}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:_TOKEN_HMAC_LENGTH]


def generate_share_x_cand_token(
    blob_key: str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: int | float | None = None,
) -> str:
    if not blob_key:
        return ""
    key = str(blob_key).strip()
    if not key or ttl_seconds <= 0:
        return ""
    current = int(now if now is not None else time.time())
    expiry = current + int(ttl_seconds)
    digest = _compute_hmac(key, expiry)
    return f"{expiry}.{digest}"


def verify_share_x_cand_token(
    blob_key: str,
    token: str,
    *,
    now: int | float | None = None,
) -> bool:
    if not blob_key or not token:
        return False
    key = str(blob_key).strip()
    raw_token = str(token).strip()
    if not key or "." not in raw_token:
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
    expected = _compute_hmac(key, expiry)
    return hmac.compare_digest(expected, hmac_part)


__all__ = [
    "generate_share_x_cand_token",
    "verify_share_x_cand_token",
]
