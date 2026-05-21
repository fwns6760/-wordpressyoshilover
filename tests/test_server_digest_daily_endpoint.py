"""Tests for /run mode=digest_daily endpoint (server._run_digest_daily + _parse_mode).

DIGEST-DAILY-MORNING-2026-05-21 Phase 2 wire."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock

from src.server import _parse_mode, _run_digest_daily


class ParseModeTests(unittest.TestCase):
    def test_empty_body_returns_rss_default(self):
        self.assertEqual(_parse_mode(""), "rss")

    def test_explicit_default_returns_rss(self):
        self.assertEqual(_parse_mode("mode=default"), "rss")
        self.assertEqual(_parse_mode("mode=rss"), "rss")

    def test_digest_daily_from_form(self):
        self.assertEqual(_parse_mode("mode=digest_daily"), "digest_daily")

    def test_digest_daily_from_json(self):
        body = json.dumps({"mode": "digest_daily"})
        self.assertEqual(
            _parse_mode(body, "application/json"), "digest_daily"
        )

    def test_uppercase_normalized(self):
        self.assertEqual(_parse_mode("mode=DIGEST_DAILY"), "digest_daily")

    def test_limit_field_ignored(self):
        self.assertEqual(_parse_mode("limit=10"), "rss")

    def test_json_with_both_fields_picks_mode(self):
        body = json.dumps({"limit": 5, "mode": "digest_daily"})
        self.assertEqual(
            _parse_mode(body, "application/json"), "digest_daily"
        )


class RunDigestDailyTests(unittest.TestCase):
    def test_skip_when_already_published(self):
        with (
            patch("src.tools.digest_daily_morning.is_digest_already_published_today",
                  return_value=True),
            patch("src.tools.digest_daily_morning.build_digest_slug",
                  return_value="morning-digest-2026-05-21"),
            patch("src.wp_client.WPClient") as mock_wp_cls,
        ):
            mock_wp = MagicMock()
            mock_wp_cls.return_value = mock_wp
            code, body = _run_digest_daily()
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(payload["reason"], "already_published_today")
        mock_wp.create_post.assert_not_called()

    def test_creates_draft_even_when_draft_only_disabled(self):
        with (
            patch("src.server.RUN_DRAFT_ONLY", False),
            patch("src.tools.digest_daily_morning.is_digest_already_published_today",
                  return_value=False),
            patch("src.tools.digest_daily_morning.build_digest_slug",
                  return_value="morning-digest-2026-05-21"),
            patch("src.tools.digest_daily_morning.build_digest_title",
                  return_value="📰 朝まとめ 5月21日"),
            patch("src.tools.digest_daily_morning.build_digest_body",
                  return_value='<div class="nomotoke-card-digest-daily-morning">body</div>'),
            patch("src.server._send_digest_daily_draft_notice",
                  return_value={"sent": 1, "suppressed": 0, "errors": 0}) as mock_notice,
            patch("src.wp_client.WPClient") as mock_wp_cls,
        ):
            mock_wp = MagicMock()
            mock_wp.create_post.return_value = 71000
            mock_wp.get_post.return_value = {"status": "draft", "link": "https://yoshilover.com/?p=71000"}
            mock_wp_cls.return_value = mock_wp
            code, body = _run_digest_daily()
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["post_id"], 71000)
        self.assertEqual(payload["slug"], "morning-digest-2026-05-21")
        mock_wp.create_post.assert_called_once()
        call_kwargs = mock_wp.create_post.call_args.kwargs
        self.assertEqual(call_kwargs["status"], "draft")
        self.assertIn(670, call_kwargs["categories"])
        self.assertEqual(call_kwargs["caller"], "digest_daily_morning")
        mock_notice.assert_called_once()

    def test_creates_draft_and_sends_notice_when_draft_only_enabled(self):
        with (
            patch("src.server.RUN_DRAFT_ONLY", True),
            patch("src.tools.digest_daily_morning.is_digest_already_published_today",
                  return_value=False),
            patch("src.tools.digest_daily_morning.build_digest_slug",
                  return_value="morning-digest-2026-05-21"),
            patch("src.tools.digest_daily_morning.build_digest_title",
                  return_value="📰 朝まとめ 5月21日"),
            patch("src.tools.digest_daily_morning.build_digest_body",
                  return_value='<div class="nomotoke-card-digest-daily-morning">body</div>'),
            patch("src.server._send_digest_daily_draft_notice",
                  return_value={"sent": 1, "suppressed": 0, "errors": 0}) as mock_notice,
            patch("src.wp_client.WPClient") as mock_wp_cls,
        ):
            mock_wp = MagicMock()
            mock_wp.create_post.return_value = 71002
            mock_wp.get_post.return_value = {
                "status": "draft",
                "link": "https://yoshilover.com/?p=71002",
            }
            mock_wp_cls.return_value = mock_wp
            code, body = _run_digest_daily()
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["post_id"], 71002)
        self.assertEqual(payload["notice"], {"sent": 1, "suppressed": 0, "errors": 0})
        call_kwargs = mock_wp.create_post.call_args.kwargs
        self.assertEqual(call_kwargs["status"], "draft")
        mock_notice.assert_called_once()
        notice_kwargs = mock_notice.call_args.kwargs
        self.assertEqual(notice_kwargs["post_id"], 71002)
        self.assertEqual(notice_kwargs["canonical_url"], "https://yoshilover.com/?p=71002")

    def test_force_bypasses_idempotency_check(self):
        with (
            patch("src.server.RUN_DRAFT_ONLY", False),
            patch("src.tools.digest_daily_morning.is_digest_already_published_today",
                  return_value=True),
            patch("src.tools.digest_daily_morning.build_digest_slug",
                  return_value="morning-digest-2026-05-21"),
            patch("src.tools.digest_daily_morning.build_digest_title",
                  return_value="📰 朝まとめ 5月21日"),
            patch("src.tools.digest_daily_morning.build_digest_body",
                  return_value='<div>body</div>'),
            patch("src.server._send_digest_daily_draft_notice",
                  return_value={"sent": 1, "suppressed": 0, "errors": 0}),
            patch("src.wp_client.WPClient") as mock_wp_cls,
        ):
            mock_wp = MagicMock()
            mock_wp.create_post.return_value = 71001
            mock_wp.get_post.return_value = {"status": "draft", "link": "https://yoshilover.com/?p=71001"}
            mock_wp_cls.return_value = mock_wp
            code, body = _run_digest_daily(force=True)
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "draft")
        # force=True で is_already_published check は call されるが結果無視
        mock_wp.create_post.assert_called_once()

    def test_create_post_failure_returns_500(self):
        with (
            patch("src.tools.digest_daily_morning.is_digest_already_published_today",
                  return_value=False),
            patch("src.tools.digest_daily_morning.build_digest_slug",
                  return_value="morning-digest-2026-05-21"),
            patch("src.tools.digest_daily_morning.build_digest_title",
                  return_value="title"),
            patch("src.tools.digest_daily_morning.build_digest_body",
                  return_value="body"),
            patch("src.wp_client.WPClient") as mock_wp_cls,
        ):
            mock_wp = MagicMock()
            mock_wp.create_post.side_effect = RuntimeError("WP create_post boom")
            mock_wp_cls.return_value = mock_wp
            code, body = _run_digest_daily()
        self.assertEqual(code, 500)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "error")
        self.assertIn("create_post_failed", payload["error"])


if __name__ == "__main__":
    unittest.main()
