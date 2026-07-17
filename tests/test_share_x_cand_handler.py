"""tests for share-x-cand handlers in src/share_x_handler.py (437 Phase 8).

handle_share_cand_get + handle_share_cand_image_proxy の test。
"""

from __future__ import annotations

import unittest

from src.share_x_cand_token import generate_share_x_cand_token
from src.share_x_handler import (
    handle_share_cand_get,
    handle_share_cand_image_proxy,
)


_NOW = 1_700_000_000
_BLOB_KEY = "share_x_cand/20260526-120000/cand-01.png"
_TOKEN = generate_share_x_cand_token(_BLOB_KEY, ttl_seconds=3600, now=_NOW)
_VERIFY_NOW = _NOW + 100


# --- handle_share_cand_get -------------------------------------------------


class HandleShareCandGetTests(unittest.TestCase):
    def test_missing_blob_key_returns_400(self):
        code, body, _ = handle_share_cand_get(
            blob_key="", token=_TOKEN, text="post", post_url="https://example",
        )
        self.assertEqual(code, 400)
        self.assertIn("blob key", body)

    def test_invalid_blob_key_prefix_returns_400(self):
        code, body, _ = handle_share_cand_get(
            blob_key="../etc/passwd",
            token=_TOKEN,
            text="post",
            post_url="",
        )
        self.assertEqual(code, 400)

    def test_blob_key_with_double_dots_returns_400(self):
        code, _, _ = handle_share_cand_get(
            blob_key="share_x_cand/../secret.png",
            token=_TOKEN,
            text="post",
            post_url="",
        )
        self.assertEqual(code, 400)

    def test_missing_token_returns_400(self):
        code, body, _ = handle_share_cand_get(
            blob_key=_BLOB_KEY, token="", text="post", post_url="",
        )
        self.assertEqual(code, 400)
        self.assertIn("token", body)

    def test_invalid_token_returns_403(self):
        code, body, _ = handle_share_cand_get(
            blob_key=_BLOB_KEY,
            token="bogus.token",
            text="post",
            post_url="",
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 403)

    def test_expired_token_returns_403(self):
        old_token = generate_share_x_cand_token(_BLOB_KEY, ttl_seconds=60, now=1)
        code, _, _ = handle_share_cand_get(
            blob_key=_BLOB_KEY,
            token=old_token,
            text="post",
            post_url="",
            now=9_999_999_999,
        )
        self.assertEqual(code, 403)

    def test_valid_token_returns_share_page(self):
        code, body, _ = handle_share_cand_get(
            blob_key=_BLOB_KEY,
            token=_TOKEN,
            text="坂本勇人 OPS 1.234",
            post_url="",
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 200)
        self.assertIn("画像つきで X に投稿", body)
        # JS embed で text が含まれる
        self.assertIn("坂本勇人", body)
        # image proxy URL が埋め込まれる
        self.assertIn("/share-x-cand-image-proxy?", body)
        # fallback X intent URL も埋め込まれる
        self.assertIn("x.com/intent/post", body)
        self.assertIn("navigator.share", body)

    def test_valid_token_includes_android_fallback_controls(self):
        code, body, _ = handle_share_cand_get(
            blob_key=_BLOB_KEY,
            token=_TOKEN,
            text="坂本勇人 OPS 1.234",
            post_url="",
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 200)
        self.assertIn("画像つき投稿を試す", body)
        self.assertIn("share-x-cand-status", body)
        self.assertIn("share-x-cand-intent-link", body)
        self.assertIn("Xアプリを開く（テキストのみ）", body)
        self.assertIn("share-x-cand-copy-btn", body)
        self.assertIn("本文をコピー", body)
        # 2026-07-17: 失敗時に X intent へ自動遷移しない (X app 側の intent 破損時に
        # 手詰まりになる + ページを離れると画像の長押し保存ができないため)。
        self.assertNotIn("copyPostText().then(openXIntent, openXIntent)", body)
        self.assertNotIn(".finally(openXIntent)", body)
        self.assertIn("画像を長押し保存", body)

    def test_fetcher_base_url_makes_image_proxy_absolute(self):
        code, body, _ = handle_share_cand_get(
            blob_key=_BLOB_KEY,
            token=_TOKEN,
            text="post",
            post_url="",
            now=_VERIFY_NOW,
            fetcher_base_url="https://fetcher.example.com",
        )
        self.assertEqual(code, 200)
        self.assertIn("https://fetcher.example.com/share-x-cand-image-proxy?", body)


# --- handle_share_cand_image_proxy ----------------------------------------


class HandleShareCandImageProxyTests(unittest.TestCase):
    def test_missing_blob_key_returns_400(self):
        code, body, ct, _ = handle_share_cand_image_proxy(
            blob_key="",
            token=_TOKEN,
            fetch_blob_bytes=lambda k: (b"x", "image/png"),
        )
        self.assertEqual(code, 400)
        self.assertTrue(ct.startswith("text/plain"))

    def test_invalid_token_returns_403(self):
        code, _, _, _ = handle_share_cand_image_proxy(
            blob_key=_BLOB_KEY,
            token="bogus.token",
            fetch_blob_bytes=lambda k: (b"x", "image/png"),
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 403)

    def test_blob_not_found_returns_404(self):
        code, _, _, _ = handle_share_cand_image_proxy(
            blob_key=_BLOB_KEY,
            token=_TOKEN,
            fetch_blob_bytes=lambda k: None,
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 404)

    def test_blob_fetch_exception_returns_502(self):
        def _boom(k):
            raise RuntimeError("gcs explode")

        code, body, _, _ = handle_share_cand_image_proxy(
            blob_key=_BLOB_KEY,
            token=_TOKEN,
            fetch_blob_bytes=_boom,
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 502)
        self.assertIn(b"fetch blob failed", body)

    def test_too_large_returns_413(self):
        big = b"x" * (5 * 1024 * 1024 + 1)
        code, _, _, _ = handle_share_cand_image_proxy(
            blob_key=_BLOB_KEY,
            token=_TOKEN,
            fetch_blob_bytes=lambda k: (big, "image/png"),
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 413)

    def test_valid_returns_bytes(self):
        png = b"\x89PNG fake content"
        code, body, ct, headers = handle_share_cand_image_proxy(
            blob_key=_BLOB_KEY,
            token=_TOKEN,
            fetch_blob_bytes=lambda k: (png, "image/png"),
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 200)
        self.assertEqual(body, png)
        self.assertEqual(ct, "image/png")
        self.assertIn("Cache-Control", headers)

    def test_blob_key_mismatch_with_token_returns_403(self):
        code, _, _, _ = handle_share_cand_image_proxy(
            blob_key="share_x_cand/20260526-120000/cand-02.png",
            token=_TOKEN,  # token は cand-01 用
            fetch_blob_bytes=lambda k: (b"x", "image/png"),
            now=_VERIFY_NOW,
        )
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
