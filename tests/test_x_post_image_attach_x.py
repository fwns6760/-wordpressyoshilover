"""437 Phase 2B: attach_x_post_image helper unit tests.

scope: tweepy v1.1 API.media_upload を MagicMock で差し替え、 成功 / 失敗 /
rate limit / empty bytes / 上限超過 / response 欠損 各 path を網羅する。
X live post には届かない (mock only)。
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from src.x_post_image_attach_x import (
    PNG_MAX_BYTES_X,
    attach_x_post_image,
)


def _make_media_response(media_id_string="1234567890"):
    """tweepy.API.media_upload 返り値を模した object。"""
    m = MagicMock()
    m.media_id_string = media_id_string
    m.media_id = int(media_id_string)
    return m


# ---------- success path ----------


def test_attach_returns_media_id_string():
    api = MagicMock()
    api.media_upload.return_value = _make_media_response("9876543210")
    result = attach_x_post_image(api, b"x" * 100)
    assert result == "9876543210"
    api.media_upload.assert_called_once()


def test_attach_passes_filename_to_media_upload():
    api = MagicMock()
    api.media_upload.return_value = _make_media_response()
    attach_x_post_image(api, b"x" * 100, filename="ranking-2026-05-26.png")
    call_kwargs = api.media_upload.call_args.kwargs
    assert call_kwargs["filename"] == "ranking-2026-05-26.png"


def test_attach_passes_bytes_io_to_media_upload():
    import io as _io

    api = MagicMock()
    api.media_upload.return_value = _make_media_response()
    attach_x_post_image(api, b"abcdef")
    call_kwargs = api.media_upload.call_args.kwargs
    assert isinstance(call_kwargs["file"], _io.BytesIO)
    call_kwargs["file"].seek(0)
    assert call_kwargs["file"].read() == b"abcdef"


def test_attach_fallback_to_media_id_when_string_missing():
    """tweepy が media_id_string を返さなくても media_id があれば str 化して返す。"""
    api = MagicMock()
    media = MagicMock(spec=["media_id"])  # media_id_string 属性なし
    media.media_id = 555444333
    api.media_upload.return_value = media
    result = attach_x_post_image(api, b"x" * 100)
    assert result == "555444333"


# ---------- failure paths (全部 None を返し、 publish は止めない) ----------


def test_attach_returns_none_when_api_is_none():
    assert attach_x_post_image(None, b"x" * 100) is None


def test_attach_returns_none_on_empty_png():
    api = MagicMock()
    assert attach_x_post_image(api, b"") is None
    api.media_upload.assert_not_called()


def test_attach_returns_none_when_png_exceeds_x_upload_limit():
    api = MagicMock()
    big = b"\x00" * (PNG_MAX_BYTES_X + 1)
    assert attach_x_post_image(api, big) is None
    api.media_upload.assert_not_called()


def test_attach_returns_none_on_tweepy_exception(caplog):
    import tweepy

    caplog.set_level(logging.WARNING)
    api = MagicMock()
    api.media_upload.side_effect = tweepy.TweepyException("upload failed")
    result = attach_x_post_image(api, b"x" * 100)
    assert result is None
    assert any("media_upload failed" in m for m in caplog.messages)


def test_attach_returns_none_on_rate_limit(caplog):
    """X API Free tier rate limit (HTTP 429) でも publish を止めない。"""
    import tweepy

    caplog.set_level(logging.WARNING)
    api = MagicMock()
    response = MagicMock()
    response.status_code = 429
    api.media_upload.side_effect = tweepy.TooManyRequests(response)
    result = attach_x_post_image(api, b"x" * 100)
    assert result is None
    assert any("media_upload failed" in m for m in caplog.messages)


def test_attach_returns_none_when_response_lacks_media_id(caplog):
    caplog.set_level(logging.WARNING)
    api = MagicMock()
    media = MagicMock(spec=[])  # 属性なし
    api.media_upload.return_value = media
    result = attach_x_post_image(api, b"x" * 100)
    assert result is None
    assert any("missing media_id_string" in m for m in caplog.messages)


def test_attach_returns_none_on_generic_exception(caplog):
    """tweepy 以外の例外 (network error 等) でも publish を止めない。"""
    caplog.set_level(logging.WARNING)
    api = MagicMock()
    api.media_upload.side_effect = ConnectionError("network down")
    result = attach_x_post_image(api, b"x" * 100)
    assert result is None
    assert any("media_upload failed" in m for m in caplog.messages)
