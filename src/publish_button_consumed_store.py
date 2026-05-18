"""379-OPS: token 1 回限り (one-shot) 用 GCS-backed consume store (GH #53).

publish-and-tweet button の token は HMAC + 24h expiry を持つが、 同じ token を
何度も使えてしまう (replay 攻撃の余地)。 本 module は GCS object として
「消費済 token」 を記録し、 2 回目以降の使用を拒否することで one-shot 化する。

bucket = ``baseballsite-yoshilover-state`` (既存)
object path = ``publish-button-consumed/{token_hash[:32]}.json``

GCS が unreachable / 認証 fail の場合は fail-open: 「消費済でない」 とみなす
(infrastructure 故障で publish 完全停止 を避ける、 idempotency は handler 側の
status check で 2 重 publish 防止される)。

token そのものは GCS に保存しない (SHA-256 hash のみ)。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

_log = logging.getLogger("publish_button.consumed_store")

_DEFAULT_BUCKET = "baseballsite-yoshilover-state"
_OBJECT_PREFIX = "publish-button-consumed/"
_HASH_PREFIX_LEN = 32


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:_HASH_PREFIX_LEN]


def _gcs_blob(bucket_name: str, object_name: str):
    """Return a Blob handle or None if GCS unreachable."""
    try:
        from google.cloud import storage  # noqa: WPS433

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        return bucket.blob(object_name)
    except Exception as exc:  # noqa: BLE001
        _log.warning("publish_button_consumed_store_gcs_init_failed err=%s", exc)
        return None


def is_consumed(token: str, *, bucket_name: str = _DEFAULT_BUCKET) -> bool:
    """token が GCS の consume ledger に存在するか確認する。

    GCS fail (network / auth / permission) 時は ``False`` (fail-open):
    handler 側で publish 実行に進む。 status check で 2 重 publish 防止される。
    """
    if not token:
        return False
    blob = _gcs_blob(bucket_name, _OBJECT_PREFIX + _hash_token(token) + ".json")
    if blob is None:
        return False
    try:
        return bool(blob.exists())
    except Exception as exc:  # noqa: BLE001
        _log.warning("publish_button_consumed_store_exists_failed err=%s", exc)
        return False


def mark_consumed(
    token: str,
    *,
    post_id: int | str | None = None,
    bucket_name: str = _DEFAULT_BUCKET,
    now: int | float | None = None,
) -> bool:
    """token を consume ledger に記録する。

    Returns:
        True = 新規に mark できた (= この caller が token を最初に消費)
        False = 既に存在した、 もしくは GCS 失敗

    Atomicity: ``if_generation_match=0`` で「存在しない時のみ create」 する。
    レース時 (同時 click で複数 instance が同時 mark) は 1 つだけ成功、 残りは False。
    handler 側は False 受信時に「既に消費済扱い」 として handle する。
    """
    if not token:
        return False
    blob = _gcs_blob(bucket_name, _OBJECT_PREFIX + _hash_token(token) + ".json")
    if blob is None:
        return False
    payload = json.dumps(
        {
            "post_id": post_id,
            "consumed_at_unix": int(now if now is not None else time.time()),
        },
        ensure_ascii=False,
    )
    try:
        blob.upload_from_string(
            payload,
            content_type="application/json",
            if_generation_match=0,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        # 412 Precondition Failed (既存) or その他 → False。 レース or 既消費。
        _log.info("publish_button_consumed_store_upload_failed err=%s", exc)
        return False


__all__ = ["is_consumed", "mark_consumed"]
