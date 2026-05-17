"""Tests for 377-OPS Phase 1: RUN_DRAFT_ONLY=True で全 publish を draft 強制.

user lock (2026-05-17, GH #51): 全 subtype を draft 化して、 mail で本文確認後
user 手動公開フローへ移行する。 wp_client.create_post の publish 要求を全部
draft に downgrade、 status upgrade も止める。

env RUN_DRAFT_ONLY=False (default) では従来通り publish 経路維持 (backward compat)。
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock


class RunDraftOnlyEnforcementTests(unittest.TestCase):
    def _make_client(self):
        with patch.dict(os.environ, {
            "WP_URL": "https://test.example.com",
            "WP_USER": "test", "WP_APP_PASSWORD": "test-pass",
        }, clear=False):
            from src.wp_client import WPClient
            return WPClient()

    def test_run_draft_only_true_forces_publish_to_draft(self):
        """RUN_DRAFT_ONLY=True で publish 要求が draft に降格."""
        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "True"}, clear=False):
            client = self._make_client()
            with patch.object(client, "find_recent_post_by_title", return_value=None), \
                 patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 201
                mock_resp.json.return_value = {"id": 99999, "status": "draft"}
                mock_post.return_value = mock_resp
                client.create_post(
                    title="test", content="<p>body</p>",
                    status="publish",
                )
                # POST payload に status=draft が入っていること
                _, kwargs = mock_post.call_args
                payload = kwargs.get("json") or {}
                self.assertEqual(payload.get("status"), "draft")

    def test_run_draft_only_false_keeps_publish(self):
        """RUN_DRAFT_ONLY=False (default) では publish 要求がそのまま."""
        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "False"}, clear=False):
            client = self._make_client()
            with patch.object(client, "find_recent_post_by_title", return_value=None), \
                 patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 201
                mock_resp.json.return_value = {"id": 99999, "status": "publish"}
                mock_post.return_value = mock_resp
                client.create_post(
                    title="test", content="<p>body</p>",
                    status="publish",
                )
                _, kwargs = mock_post.call_args
                payload = kwargs.get("json") or {}
                self.assertEqual(payload.get("status"), "publish")

    def test_run_draft_only_true_keeps_explicit_draft(self):
        """RUN_DRAFT_ONLY=True で caller が draft 要求 → そのまま draft."""
        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "True"}, clear=False):
            client = self._make_client()
            with patch.object(client, "find_recent_post_by_title", return_value=None), \
                 patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 201
                mock_resp.json.return_value = {"id": 99999, "status": "draft"}
                mock_post.return_value = mock_resp
                client.create_post(
                    title="test", content="<p>body</p>",
                    status="draft",
                )
                _, kwargs = mock_post.call_args
                payload = kwargs.get("json") or {}
                self.assertEqual(payload.get("status"), "draft")

    def test_run_draft_only_off_with_explicit_draft(self):
        """RUN_DRAFT_ONLY=False + draft 要求 → そのまま draft (backward compat)."""
        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "False"}, clear=False):
            client = self._make_client()
            with patch.object(client, "find_recent_post_by_title", return_value=None), \
                 patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 201
                mock_resp.json.return_value = {"id": 99999, "status": "draft"}
                mock_post.return_value = mock_resp
                client.create_post(
                    title="test", content="<p>body</p>",
                    status="draft",
                )
                _, kwargs = mock_post.call_args
                payload = kwargs.get("json") or {}
                self.assertEqual(payload.get("status"), "draft")


if __name__ == "__main__":
    unittest.main()
