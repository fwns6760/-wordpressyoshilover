"""379-OPS: mail 内「公開してX投稿画面へ」ボタン用の HMAC + expiry token (GH #53).

mail に WP draft post を 1-click で publish して X intent URL に redirect する
endpoint /publish-and-tweet を作るための token。 ``unpublish_token`` 同様に
HMAC で post_id を sign するが、 publish (state change + 不可逆寄り) のため
expiry も持たせる。

token format: ``{expiry_unix_seconds}.{hmac_hex24}``
- ``expiry_unix_seconds``: token 有効期限 (UTC unix timestamp、 整数)
- ``hmac_hex24``: ``HMAC-SHA256(secret, f"{post_id}:{expiry}").hexdigest()[:24]``

secret は env ``PUBLISH_BUTTON_TOKEN_SECRET`` で override 可、 未設定時は default
constant (yoshilover noindex 環境用、 外部攻撃面狭い前提)。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

_DEFAULT_SECRET = "yoshilover_publish_button_default_2026_05_18"
_TOKEN_HMAC_LENGTH = 24
_DEFAULT_TTL_SECONDS = 86400  # 24 時間


def _resolve_secret() -> str:
    env_secret = os.getenv("PUBLISH_BUTTON_TOKEN_SECRET", "").strip()
    return env_secret or _DEFAULT_SECRET


def _compute_hmac(post_id: str, expiry: int) -> str:
    secret = _resolve_secret().encode("utf-8")
    payload = f"{post_id}:{expiry}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()[:_TOKEN_HMAC_LENGTH]


def generate_publish_button_token(
    post_id: int | str,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: int | float | None = None,
) -> str:
    """post_id + expiry に紐付いた token を返す。

    Why: mail 内ボタンの URL `?post_id=X&token=Y` 用。 expiry で漏洩リスクを
    24 時間に制限する。 ``ttl_seconds<=0`` は invalid とみなし空文字を返す
    (caller は link を出さない fail-open)。
    """
    if post_id is None:
        return ""
    pid = str(post_id).strip()
    if not pid or ttl_seconds <= 0:
        return ""
    current = int(now if now is not None else time.time())
    expiry = current + int(ttl_seconds)
    digest = _compute_hmac(pid, expiry)
    return f"{expiry}.{digest}"


def verify_publish_button_token(
    post_id: int | str,
    token: str,
    *,
    now: int | float | None = None,
) -> bool:
    """token の HMAC + expiry を constant-time 比較で検証する。

    Returns True only when 全 condition pass:
      - token が ``{expiry}.{hmac}`` の形式
      - expiry が int に parse 可能
      - expiry > now (期限内)
      - 再計算した HMAC が一致
    """
    if not post_id or not token:
        return False
    pid = str(post_id).strip()
    raw_token = str(token).strip()
    if not pid or "." not in raw_token:
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
    expected = _compute_hmac(pid, expiry)
    return hmac.compare_digest(expected, hmac_part)


def build_publish_button_url(
    post_id: int | str,
    fetcher_base_url: str | None,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: int | float | None = None,
) -> str | None:
    """mail に出す ``/publish-and-tweet?post_id=X&token=Y`` URL を組み立てる。

    Why: 379-OPS mail 内ボタンの href 用。 token は HMAC + 24h 期限。

    Returns ``None`` for invalid input (post_id None / 0 / 非数値 / fetcher_base_url 不存在)、
    caller は None なら link を出さず本文不変 (fail-open)。
    """
    if post_id is None:
        return None
    try:
        pid = int(str(post_id).strip())
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    base = (fetcher_base_url or "").strip().rstrip("/")
    if not base:
        return None
    token = generate_publish_button_token(pid, ttl_seconds=ttl_seconds, now=now)
    if not token:
        return None
    return f"{base}/publish-and-tweet?post_id={pid}&token={token}"


__all__ = [
    "build_publish_button_url",
    "generate_publish_button_token",
    "verify_publish_button_token",
]
