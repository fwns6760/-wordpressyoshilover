"""tests for src/share_x_handler.py (437 Phase 2A / 2026-05-26).

share-x endpoint (Web Share API for Pixel + Android Gmail) の handler test。
publish_button_handler.py test と同 pattern で書く (HMAC token + fetch mock 注入)。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.publish_button_token import generate_publish_button_token
from src.share_x_handler import (
    handle_image_proxy,
    handle_share_get,
)


_TOKEN_TEST_NOW = 1_700_000_000
_TOKEN = generate_publish_button_token(123, ttl_seconds=3600, now=_TOKEN_TEST_NOW)
_VERIFY_NOW = _TOKEN_TEST_NOW + 100


def _wp_post(post_id: int = 123, *, featured_media: int = 444, status: str = "publish") -> dict:
    return {
        "id": post_id,
        "title": {"rendered": "巨人 3-1 阪神 岡本 2 試合連続 HR"},
        "link": "https://yoshilover.com/post-123/",
        "status": status,
        "featured_media": featured_media,
    }


# --- handle_share_get ------------------------------------------------------


class HandleShareGetTests(unittest.TestCase):
    def test_handle_share_get_invalid_post_id_returns_400(self):
        code, body, headers = handle_share_get(
            post_id_raw="abc",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(),
        )
        assert code == 400
        assert "post_id" in body
        assert headers == {}

    def test_handle_share_get_missing_token_returns_400(self):
        code, body, _ = handle_share_get(
            post_id_raw="123",
            token="",
            fetch_post=lambda pid: _wp_post(),
        )
        assert code == 400
        assert "token" in body

    def test_handle_share_get_invalid_token_returns_403(self):
        code, body, _ = handle_share_get(
            post_id_raw="123",
            token="invalid.token",
            fetch_post=lambda pid: _wp_post(),
            now=_VERIFY_NOW,
        )
        assert code == 403
        assert "改ざん" in body or "期限切れ" in body

    def test_handle_share_get_expired_token_returns_403(self):
        old_token = generate_publish_button_token(123, ttl_seconds=60, now=1)
        code, _, _ = handle_share_get(
            post_id_raw="123",
            token=old_token,
            fetch_post=lambda pid: _wp_post(),
            now=9_999_999_999,
        )
        assert code == 403

    def test_handle_share_get_post_not_found_returns_404(self):
        code, body, _ = handle_share_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: None,
            now=_VERIFY_NOW,
        )
        assert code == 404
        assert "存在しない" in body

    def test_handle_share_get_success_returns_html_with_image_and_button(self):
        code, body, _ = handle_share_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(featured_media=444),
            now=_VERIFY_NOW,
        )
        assert code == 200
        # 記事 title
        assert "巨人 3-1 阪神" in body
        # 画像 preview tag
        assert "<img" in body
        # image proxy URL (default relative)
        assert "/share-x-image-proxy?" in body
        assert "post_id=123" in body
        # 共有 button
        assert "画像つきで X に共有" in body
        # navigator.share JS が embedded
        assert "navigator.share" in body
        # form action は /publish-and-tweet (fallback flow)
        assert 'action="/publish-and-tweet"' in body

    def test_handle_share_get_no_featured_media_omits_img_tag(self):
        code, body, _ = handle_share_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(featured_media=0),
            now=_VERIFY_NOW,
        )
        assert code == 200
        # featured_media なしのときは <img tag を出さない
        assert "<img" not in body
        # share button は出す
        assert "画像つきで X に共有" in body

    def test_handle_share_get_absolute_image_proxy_url_when_fetcher_base_set(self):
        code, body, _ = handle_share_get(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(featured_media=444),
            now=_VERIFY_NOW,
            fetcher_base_url="https://yoshilover-fetcher-xxx.run.app",
        )
        assert code == 200
        assert "https://yoshilover-fetcher-xxx.run.app/share-x-image-proxy?" in body


# --- handle_image_proxy ----------------------------------------------------


class HandleImageProxyTests(unittest.TestCase):
    def test_handle_image_proxy_invalid_token_returns_403(self):
        code, body, content_type, _ = handle_image_proxy(
            post_id_raw="123",
            token="invalid.token",
            fetch_post=lambda pid: _wp_post(),
            fetch_media_bytes=MagicMock(return_value=(b"x", "image/png")),
            now=_VERIFY_NOW,
        )
        assert code == 403
        assert content_type.startswith("text/plain")
        assert isinstance(body, bytes)

    def test_handle_image_proxy_invalid_post_id_returns_400(self):
        code, body, content_type, _ = handle_image_proxy(
            post_id_raw="abc",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(),
            fetch_media_bytes=MagicMock(return_value=(b"x", "image/png")),
        )
        assert code == 400
        assert content_type.startswith("text/plain")

    def test_handle_image_proxy_post_not_found_returns_404(self):
        code, body, content_type, _ = handle_image_proxy(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: None,
            fetch_media_bytes=MagicMock(return_value=(b"x", "image/png")),
            now=_VERIFY_NOW,
        )
        assert code == 404

    def test_handle_image_proxy_no_featured_media_returns_404(self):
        code, body, content_type, _ = handle_image_proxy(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(featured_media=0),
            fetch_media_bytes=MagicMock(return_value=(b"x", "image/png")),
            now=_VERIFY_NOW,
        )
        assert code == 404
        assert b"featured_media" in body

    def test_handle_image_proxy_success_returns_image_bytes(self):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        fetch_media = MagicMock(return_value=(png_bytes, "image/png"))
        code, body, content_type, extra_headers = handle_image_proxy(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(featured_media=444),
            fetch_media_bytes=fetch_media,
            now=_VERIFY_NOW,
        )
        assert code == 200
        assert body == png_bytes
        assert content_type == "image/png"
        assert extra_headers.get("Cache-Control") == "private, max-age=600"
        fetch_media.assert_called_once_with(444)

    def test_handle_image_proxy_fetch_media_failed_returns_502(self):
        code, body, content_type, _ = handle_image_proxy(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(featured_media=444),
            fetch_media_bytes=lambda mid: None,
            now=_VERIFY_NOW,
        )
        assert code == 502
        assert content_type.startswith("text/plain")
        assert b"empty" in body or b"failed" in body or b"invalid" in body

    def test_handle_image_proxy_fetch_media_raises_returns_502(self):
        def boom(_):
            raise RuntimeError("network down")

        code, body, content_type, _ = handle_image_proxy(
            post_id_raw="123",
            token=_TOKEN,
            fetch_post=lambda pid: _wp_post(featured_media=444),
            fetch_media_bytes=boom,
            now=_VERIFY_NOW,
        )
        assert code == 502
        assert b"network down" in body or b"failed" in body


if __name__ == "__main__":
    unittest.main()
