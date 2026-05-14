"""mail unpublish 1-click 機能用 token gen / verify (2026-05-14 user request).

mail に「→ 非公開にする」link を入れて user が 1 click で publish 済記事を
draft (status=draft) に flip できるようにする。token は post_id を HMAC で
sign、推測不能。

secret は env `UNPUBLISH_TOKEN_SECRET` で override 可、未設定時は default
constant (yoshilover noindex 環境用、外部攻撃面狭い前提)。
"""

from __future__ import annotations

import hashlib
import hmac
import os


_DEFAULT_SECRET = "yoshilover_unpublish_default_2026_05_14"
_TOKEN_LENGTH = 24


def _resolve_secret() -> str:
    env_secret = os.getenv("UNPUBLISH_TOKEN_SECRET", "").strip()
    return env_secret or _DEFAULT_SECRET


def generate_unpublish_token(post_id: int | str) -> str:
    """post_id に紐付いた HMAC token を返す (16進、24 char)。"""
    pid = str(post_id).strip()
    if not pid:
        return ""
    secret = _resolve_secret().encode("utf-8")
    digest = hmac.new(secret, pid.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:_TOKEN_LENGTH]


def verify_unpublish_token(post_id: int | str, token: str) -> bool:
    """token が post_id に紐付いた HMAC と一致するか constant-time 比較。"""
    if not post_id or not token:
        return False
    expected = generate_unpublish_token(post_id)
    if not expected:
        return False
    return hmac.compare_digest(expected, str(token).strip())
