"""Tests for /unpublish endpoint logic (server._run_unpublish)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

from src.server import _run_unpublish, _unpublish_html
from src.unpublish_token import generate_unpublish_token


class RunUnpublishTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("UNPUBLISH_TOKEN_SECRET", None)

    def tearDown(self):
        os.environ.pop("UNPUBLISH_TOKEN_SECRET", None)

    def test_invalid_post_id_returns_400(self):
        code, html = _run_unpublish("abc", "x" * 24)
        self.assertEqual(code, 400)
        self.assertIn("post_id", html)

    def test_empty_post_id_returns_400(self):
        code, html = _run_unpublish("", "x" * 24)
        self.assertEqual(code, 400)

    def test_missing_token_returns_400(self):
        code, html = _run_unpublish("67372", "")
        self.assertEqual(code, 400)
        self.assertIn("token", html)

    def test_wrong_token_returns_403(self):
        code, html = _run_unpublish("67372", "wrong_token_xxxxxxxxxxxx")
        self.assertEqual(code, 403)
        self.assertIn("token", html)

    def test_correct_token_calls_wp_update_status(self):
        token = generate_unpublish_token(67372)
        with patch("src.wp_client.WPClient") as mock_wp_cls:
            mock_wp = MagicMock()
            mock_wp_cls.return_value = mock_wp
            code, html = _run_unpublish("67372", token)
        self.assertEqual(code, 200)
        self.assertIn("非公開", html)
        self.assertIn("draft", html or "")
        mock_wp.update_post_status.assert_called_once()
        call_args = mock_wp.update_post_status.call_args
        self.assertEqual(call_args[0][0], 67372)
        self.assertEqual(call_args[0][1], "draft")

    def test_blocked_revert_returns_503(self):
        token = generate_unpublish_token(67372)
        with patch("src.wp_client.WPClient") as mock_wp_cls:
            mock_wp = MagicMock()
            mock_wp.update_post_status.side_effect = RuntimeError(
                "[WP] published post status revert blocked"
            )
            mock_wp_cls.return_value = mock_wp
            code, html = _run_unpublish("67372", token)
        self.assertEqual(code, 503)
        self.assertIn("block", html.lower())

    def test_wp_other_exception_returns_500(self):
        token = generate_unpublish_token(67372)
        with patch("src.wp_client.WPClient") as mock_wp_cls:
            mock_wp = MagicMock()
            mock_wp.update_post_status.side_effect = ConnectionError("network down")
            mock_wp_cls.return_value = mock_wp
            code, html = _run_unpublish("67372", token)
        self.assertEqual(code, 500)
        self.assertIn("WP REST 失敗", html)


class UnpublishHtmlTests(unittest.TestCase):
    def test_success_html_contains_admin_link(self):
        html = _unpublish_html("success", "ok", post_id=67372)
        self.assertIn("WP admin", html)
        self.assertIn("post=67372", html)

    def test_error_html_no_admin_link(self):
        html = _unpublish_html("error", "ng")
        self.assertNotIn("WP admin", html)


if __name__ == "__main__":
    unittest.main()
