"""Tests for /x-direct-post (mail ボタン → 確認ページ → X API 直投稿)。

2026-07-06 user GO「mailのボタンで該当アカウントに自動で切り替えたい」:
X intent にはアカウント指定が無いため、server 側 API 直投稿で切替自体を無くす。
- token: 原文 + acct + expiry に HMAC バインド
- GET: 確認ページ (textarea 編集可)
- POST: token 検証 → tweepy create_tweet (アカウント別 env key)
"""

from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

from src import x_direct_post_handler as xdp

_BASEBALL_ENV = {
    "X_API_KEY": "k", "X_API_SECRET": "s",
    "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts",
}


class TokenTests(unittest.TestCase):
    def test_roundtrip(self):
        token = xdp.generate_direct_post_token("baseball", "本文", now=1000)
        self.assertTrue(
            xdp.verify_direct_post_token(
                "baseball", xdp._text_digest("本文"), token, now=1000
            )
        )

    def test_expired(self):
        token = xdp.generate_direct_post_token(
            "baseball", "本文", ttl_seconds=10, now=1000
        )
        self.assertFalse(
            xdp.verify_direct_post_token(
                "baseball", xdp._text_digest("本文"), token, now=2000
            )
        )

    def test_text_tamper_rejected(self):
        token = xdp.generate_direct_post_token("baseball", "本文A", now=1000)
        self.assertFalse(
            xdp.verify_direct_post_token(
                "baseball", xdp._text_digest("本文B"), token, now=1000
            )
        )

    def test_account_mismatch_rejected(self):
        token = xdp.generate_direct_post_token("baseball", "本文", now=1000)
        self.assertFalse(
            xdp.verify_direct_post_token(
                "naka", xdp._text_digest("本文"), token, now=1000
            )
        )

    def test_unknown_account_returns_empty(self):
        self.assertEqual(xdp.generate_direct_post_token("hack", "本文"), "")


class BuildUrlTests(unittest.TestCase):
    def test_builds_url_with_token(self):
        url = xdp.build_direct_post_button_url(
            "投稿本文", account="baseball", base_url="https://f.example"
        )
        self.assertIn("https://f.example/x-direct-post?", url)
        self.assertIn("acct=baseball", url)
        self.assertIn("token=", url)

    def test_empty_base_returns_empty(self):
        self.assertEqual(
            xdp.build_direct_post_button_url("t", account="baseball", base_url=""),
            "",
        )

    def test_quote_and_reply_params(self):
        url = xdp.build_direct_post_button_url(
            "t", account="baseball", base_url="https://f.example",
            reply_to_id="123", quote_url="https://x.com/a/status/456",
        )
        self.assertIn("reply_to=123", url)
        self.assertIn("quote=", url)


class GetPageTests(unittest.TestCase):
    def test_renders_editable_page(self):
        text = "井上温大が7回無失点。"
        token = xdp.generate_direct_post_token("baseball", text)
        with patch.dict("os.environ", _BASEBALL_ENV):
            code, body, _ = xdp.handle_direct_post_get("baseball", text, token)
        self.assertEqual(code, 200)
        self.assertIn("textarea", body)
        self.assertIn("井上温大が7回無失点。", body)
        self.assertIn("yoshilover6760", body)

    def test_bad_token_403(self):
        code, body, _ = xdp.handle_direct_post_get("baseball", "本文", "1.bad")
        self.assertEqual(code, 403)

    def test_naka_missing_creds_shows_warning(self):
        text = "FIRE本文"
        token = xdp.generate_direct_post_token("naka", text)
        with patch.dict("os.environ", {}, clear=False):
            for k in list(_BASEBALL_ENV) + [
                "X_NAKA_API_KEY", "X_NAKA_API_SECRET",
                "X_NAKA_ACCESS_TOKEN", "X_NAKA_ACCESS_TOKEN_SECRET",
            ]:
                patch.dict("os.environ", {k: ""}).start()
            code, body, _ = xdp.handle_direct_post_get("naka", text, token)
        self.assertEqual(code, 200)
        self.assertIn("未設定", body)


class PostTests(unittest.TestCase):
    def _token(self, text, acct="baseball"):
        return xdp.generate_direct_post_token(acct, text)

    def test_posts_via_api(self):
        text = "投稿本文です。"
        client = MagicMock()
        client.create_tweet.return_value = types.SimpleNamespace(data={"id": "999"})
        with patch.object(xdp, "_get_client_for", return_value=client):
            code, body, _ = xdp.handle_direct_post_post(
                "baseball", text, self._token(text), xdp._text_digest(text)
            )
        self.assertEqual(code, 200)
        self.assertIn("投稿しました", body)
        self.assertIn("x.com/yoshilover6760/status/999", body)
        client.create_tweet.assert_called_once_with(text=text)

    def test_edited_text_is_posted(self):
        orig = "元の本文。"
        edited = "編集後の本文。"
        client = MagicMock()
        client.create_tweet.return_value = types.SimpleNamespace(data={"id": "1"})
        with patch.object(xdp, "_get_client_for", return_value=client):
            code, _, _ = xdp.handle_direct_post_post(
                "baseball", edited, self._token(orig), xdp._text_digest(orig)
            )
        self.assertEqual(code, 200)
        client.create_tweet.assert_called_once_with(text=edited)

    def test_reply_and_quote_forwarded(self):
        text = "リプ本文。"
        client = MagicMock()
        client.create_tweet.return_value = types.SimpleNamespace(data={"id": "1"})
        with patch.object(xdp, "_get_client_for", return_value=client):
            xdp.handle_direct_post_post(
                "baseball", text, self._token(text), xdp._text_digest(text),
                reply_to="123", quote="https://x.com/a/status/456",
            )
        kwargs = client.create_tweet.call_args.kwargs
        self.assertEqual(kwargs["in_reply_to_tweet_id"], "123")
        self.assertEqual(kwargs["quote_tweet_id"], "456")

    def test_weighted_over_280_rejected(self):
        text = "あ" * 200  # weighted 400
        with patch.object(xdp, "_get_client_for", return_value=MagicMock()) as gc:
            code, body, _ = xdp.handle_direct_post_post(
                "baseball", text, self._token(text), xdp._text_digest(text)
            )
        self.assertEqual(code, 400)
        gc.assert_not_called()

    def test_missing_creds_503(self):
        text = "本文。"
        with patch.object(xdp, "_get_client_for", return_value=None):
            code, body, _ = xdp.handle_direct_post_post(
                "baseball", text, self._token(text), xdp._text_digest(text)
            )
        self.assertEqual(code, 503)
        self.assertIn("API key", body)

    def test_api_error_502(self):
        text = "本文。"
        client = MagicMock()
        client.create_tweet.side_effect = RuntimeError("boom")
        with patch.object(xdp, "_get_client_for", return_value=client):
            code, body, _ = xdp.handle_direct_post_post(
                "baseball", text, self._token(text), xdp._text_digest(text)
            )
        self.assertEqual(code, 502)

    def test_bad_token_403(self):
        code, _, _ = xdp.handle_direct_post_post(
            "baseball", "本文", "1.bad", xdp._text_digest("本文")
        )
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
