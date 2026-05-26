"""437 Phase 2B: PNG bytes を X (Twitter) にアップロードして media_id_string を返す。

x_post_image_gen_v2.generate_png() の出力を受け取り、 tweepy v1.1 API の
media_upload() で X 側に転送する純粋 wrapper。 X live post への attach は
caller (Phase 2C で x_post_mail_lane.py に統合) が行う。

設計方針:
  - 失敗時は None を返し、 caller は text-only post に fallback する
    (rate limit / network error で X 投稿自体を止めない)
  - 副作用は X 側 media upload のみ (DB / GCS / WP には書かない)
  - api_v1 は引数で受け取り、 テストで MagicMock を差し込める
  - X API tier=Free でも media_upload は使える (memory: reference_x_api_tier_free_writeonly)

env:
  X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET
    (x_api_client.get_client が読む env と同じ)
"""
from __future__ import annotations

import io
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

PNG_MAX_BYTES_X = 5 * 1024 * 1024  # X 側 media upload 上限 (実上限は 5MB、 余裕で OK)
DEFAULT_UPLOAD_FILENAME = "x_post_image.png"


def get_api_v1() -> Any:
    """OAuth1 で tweepy.API (v1.1) を構築する。

    media_upload は v1.1 endpoint なので v2 Client (x_api_client.get_client) では
    扱えない。 同じ OAuth1 credentials を流用する。
    """
    import tweepy

    auth = tweepy.OAuth1UserHandler(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return tweepy.API(auth)


def attach_x_post_image(
    api_v1: Any,
    png_bytes: bytes,
    *,
    filename: str = DEFAULT_UPLOAD_FILENAME,
) -> str | None:
    """PNG bytes を X に upload して media_id_string を返す。

    Args:
        api_v1: tweepy.API instance (test では MagicMock 可)。 None で短絡返却。
        png_bytes: 1080x1080 PNG bytes (x_post_image_gen_v2.generate_png 出力)。
        filename: X 側に渡す filename。 拡張子で MIME 推定されるので .png 必須。

    Returns:
        media_id_string (str) on success、 None on any failure。

    失敗ケース:
        - api_v1 が None
        - png_bytes が空 / 5MB 超
        - tweepy API が例外 (rate limit / network / auth)
        - レスポンスに media_id_string が無い

    すべて WARN log のみ出して None を返す (caller は text-only fallback)。
    """
    if api_v1 is None:
        logger.warning("[437v2] attach_x_post_image: api_v1 is None — skipping")
        return None
    if not png_bytes:
        logger.warning("[437v2] attach_x_post_image: empty png_bytes — skipping")
        return None
    if len(png_bytes) > PNG_MAX_BYTES_X:
        logger.warning(
            "[437v2] attach_x_post_image: png_bytes %d > X upload max %d — skipping",
            len(png_bytes),
            PNG_MAX_BYTES_X,
        )
        return None
    try:
        media = api_v1.media_upload(filename=filename, file=io.BytesIO(png_bytes))
    except Exception as exc:
        logger.warning(
            "[437v2] attach_x_post_image: media_upload failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return None
    media_id_string = getattr(media, "media_id_string", None)
    if not media_id_string:
        # tweepy v1.1 は通常 media_id_string を返すが、 念のため media_id でも fallback
        media_id = getattr(media, "media_id", None)
        if media_id:
            media_id_string = str(media_id)
    if not media_id_string:
        logger.warning("[437v2] attach_x_post_image: response missing media_id_string")
        return None
    logger.info("[437v2] attach_x_post_image: uploaded media_id=%s", media_id_string)
    return media_id_string
