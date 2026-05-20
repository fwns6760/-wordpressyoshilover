"""Tests for 411 fix: wp_client.create_category term_exists fallback via RuntimeError.

`_raise_for_status` が requests.HTTPError → RuntimeError に wrap するため、
create_category の except 節は RuntimeError も catch して term_exists 既存
カテゴリ ID を search fallback で返す必要がある。

2026-05-20 21:00 fire (insight-nightly-v22bx) で publish_giants_centric_ranking_draft
4 件失敗の根本原因 fix。
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

import requests

from src.wp_client import WPClient


class TestCreateCategoryTermExists(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    def test_create_category_returns_existing_id_when_runtime_error_term_exists(self):
        """_raise_for_status が wrap した RuntimeError でも term_exists fallback 動作."""
        runtime_msg = (
            "[WP] HTTPエラー（カテゴリ作成）: 400 Client Error: Bad Request for url: "
            "https://example.com/wp-json/wp/v2/categories\n"
            "レスポンス: {\"code\":\"term_exists\",\"message\":\"既存\","
            "\"data\":{\"status\":400,\"term_id\":675}}"
        )

        def fake_request_with_retry(*args, **kwargs):
            raise RuntimeError(runtime_msg)

        with patch.object(self.wp, "_request_with_retry", side_effect=fake_request_with_retry):
            with patch.object(self.wp, "get_categories", return_value=[
                {"id": 675, "name": "データで見る巨人"},
                {"id": 999, "name": "別カテゴリ"},
            ]):
                result = self.wp.create_category("データで見る巨人")
        self.assertEqual(result, 675)

    def test_create_category_returns_zero_when_runtime_error_no_term_exists(self):
        """term_exists を含まない RuntimeError (別エラー) は 0 を返す (既存挙動維持)。"""
        runtime_msg = "[WP] request failed after 3 attempts (カテゴリ作成): ConnectionError"

        def fake_request_with_retry(*args, **kwargs):
            raise RuntimeError(runtime_msg)

        with patch.object(self.wp, "_request_with_retry", side_effect=fake_request_with_retry):
            with patch.object(self.wp, "get_categories", return_value=[]):
                result = self.wp.create_category("新カテゴリ")
        self.assertEqual(result, 0)

    def test_create_category_returns_existing_id_when_http_error_term_exists(self):
        """raw HTTPError 経路でも term_exists fallback (既存パス互換維持)."""
        mock_resp = Mock(status_code=400)
        mock_resp.json = Mock(return_value={
            "code": "term_exists",
            "data": {"status": 400, "term_id": 675},
        })
        http_error = requests.HTTPError("400 Bad Request")
        http_error.response = mock_resp

        def fake_request_with_retry(*args, **kwargs):
            raise http_error

        with patch.object(self.wp, "_request_with_retry", side_effect=fake_request_with_retry):
            with patch.object(self.wp, "get_categories", return_value=[
                {"id": 675, "name": "既存"},
            ]):
                result = self.wp.create_category("既存")
        self.assertEqual(result, 675)

    def test_create_category_returns_new_id_on_success(self):
        """正常系: 新規 category 作成成功時は新 ID を返す (既存挙動維持)."""
        mock_resp = Mock(status_code=200)
        mock_resp.json = Mock(return_value={"id": 1234})

        def fake_request_with_retry(*args, **kwargs):
            return mock_resp

        with patch.object(self.wp, "_request_with_retry", side_effect=fake_request_with_retry):
            result = self.wp.create_category("新カテゴリ")
        self.assertEqual(result, 1234)


if __name__ == "__main__":
    unittest.main()
