import os
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest.mock import Mock, call, patch

import requests

from src.wp_client import WPClient, WP_PUBLISH_STATUS_GUARD_ENV


def _mock_response(
    status_code: int,
    *,
    json_data=None,
    text: str = "",
    headers: dict | None = None,
):
    resp = Mock(status_code=status_code, text=text, headers=headers or {})
    resp.json = Mock(return_value=json_data)
    resp.raise_for_status = Mock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    return resp


class TestWPClientDedup(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_reused_draft_backfills_featured_media(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 456,
                    "title": {"raw": "田中将大「打線を線にしない」 関連発言"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )

        post_id = self.wp.create_draft(
            "田中将大「打線を線にしない」 関連発言",
            "<p>body</p>",
            categories=[663],
            featured_media=62100,
        )

        self.assertEqual(post_id, 456)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(456, featured_media=62100)

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_draft_request_does_not_reuse_published_post(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 321,
                    "categories": [673],
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 789})

        post_id = self.wp.create_draft(
            "巨人戦 試合の流れを分けたポイント",
            "<p>body</p>",
            categories=[673],
            featured_media=654,
        )

        self.assertEqual(post_id, 789)
        mock_update.assert_not_called()
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["featured_media"], 654)

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_publish_request_promotes_reused_draft(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 654,
                    "title": {"raw": "阿部監督「粘り勝った」 ベンチ関連発言"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )

        post_id = self.wp.create_post(
            "阿部監督「粘り勝った」 ベンチ関連発言",
            "<p>body</p>",
            categories=[673, 663],
            status="publish",
            featured_media=777,
        )

        self.assertEqual(post_id, 654)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(
            654,
            featured_media=777,
            categories=[673, 663],
            status="publish",
        )

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_contract_wp_api_403_search_falls_back_to_relaxed_query(self, mock_get, mock_post):
        forbidden = Mock(status_code=403, text='{"code":"rest_forbidden_context"}')
        ok = Mock(status_code=200, json=lambda: [])
        mock_get.side_effect = [forbidden, ok]
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 987})

        post_id = self.wp.create_post(
            "松本剛「甘いところを絞って打ちに行こう」 関連発言",
            "<p>body</p>",
            status="draft",
        )

        self.assertEqual(post_id, 987)
        self.assertEqual(mock_get.call_count, 2)
        first_params = mock_get.call_args_list[0].kwargs["params"]
        second_params = mock_get.call_args_list[1].kwargs["params"]
        self.assertEqual(first_params["context"], "edit")
        self.assertNotIn("context", second_params)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_reuses_recent_same_title(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか",
            "<p>body</p>",
            status="publish",
        )

        self.assertEqual(post_id, 123)
        mock_post.assert_not_called()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_reuses_existing_draft_when_source_url_matches(self, mock_get, mock_post, mock_update):
        source_url = "https://example.com/source/a"
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 333,
                    "title": {"raw": "巨人戦 試合前にどこを見たいか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [673],
                    "meta": {WPClient.SOURCE_URL_META_KEY: source_url},
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人戦 試合前にどこを見たいか",
            "<p>body</p>",
            status="draft",
            source_url=source_url,
        )

        self.assertEqual(post_id, 333)
        mock_post.assert_not_called()
        mock_update.assert_not_called()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_creates_new_when_source_url_differs(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 334,
                    "title": {"raw": "巨人戦 試合前にどこを見たいか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "meta": {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/a"},
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 335})

        post_id = self.wp.create_post(
            "巨人戦 試合前にどこを見たいか",
            "<p>body</p>",
            status="draft",
            source_url="https://example.com/source/b",
        )

        self.assertEqual(post_id, 335)
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["meta"],
            {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/b"},
        )

    @patch("src.wp_client.requests.get")
    def test_find_recent_post_by_title_allows_title_only_reuse_when_enabled(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 336,
                    "title": {"raw": "巨人戦 試合前にどこを見たいか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "meta": {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/a"},
                }
            ],
        )

        post = self.wp.find_recent_post_by_title(
            "巨人戦 試合前にどこを見たいか",
            reusable_statuses={"draft"},
            source_url="https://example.com/source/b",
            allow_title_only_reuse=True,
        )

        self.assertIsNotNone(post)
        self.assertEqual(post["id"], 336)
        self.assertEqual(post["_yoshilover_reuse_reason"], "title_fallback")

    @patch("src.wp_client.requests.get")
    def test_find_recent_post_by_title_uses_24_hour_window_by_default(self, mock_get):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                base = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
                if tz:
                    return base.astimezone(tz)
                return base.replace(tzinfo=None)

        mock_get.return_value = Mock(status_code=200, json=lambda: [])

        with patch("src.wp_client.datetime", FixedDateTime):
            self.wp.find_recent_post_by_title("巨人戦 試合の流れを分けたポイント")

        first_params = mock_get.call_args_list[0].kwargs["params"]
        self.assertEqual(first_params["after"], "2026-04-15T12:00:00+00:00")

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_does_not_reuse_old_same_title(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか"},
                    "status": "publish",
                    "date": "2026-04-14T10:00:00",
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 999})

        post_id = self.wp.create_post(
            "巨人の先週MVPと今週の注目 泉口友汰と則本昂大をどう見るか",
            "<p>body</p>",
            status="publish",
        )

        self.assertEqual(post_id, 999)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_draft_creates_when_no_recent_same_title(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 456})

        post_id = self.wp.create_draft("新しい記事", "<p>body</p>")

        self.assertEqual(post_id, 456)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_draft_saves_source_url_meta_on_new_post(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 457})

        post_id = self.wp.create_draft(
            "新しい記事",
            "<p>body</p>",
            source_url="https://example.com/source/new",
        )

        self.assertEqual(post_id, 457)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["meta"],
            {WPClient.SOURCE_URL_META_KEY: "https://example.com/source/new"},
        )

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_draft_does_not_reuse_published_post(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 789})

        post_id = self.wp.create_draft("巨人戦 試合の流れを分けたポイント", "<p>body</p>")

        self.assertEqual(post_id, 789)
        mock_post.assert_called_once()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_in_draft_mode_does_not_reuse_published_post(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 123,
                    "title": {"raw": "巨人戦 試合の流れを分けたポイント"},
                    "status": "publish",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 790})

        post_id = self.wp.create_post(
            "巨人戦 試合の流れを分けたポイント",
            "<p>body</p>",
            status="draft",
            featured_media=88,
        )

        self.assertEqual(post_id, 790)
        mock_update.assert_not_called()
        mock_post.assert_called_once()

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_backfills_featured_media_on_reused_draft(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 456,
                    "title": {"raw": "巨人が阪神に3-2で勝利　岡田が決勝打"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [673, 663],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人が阪神に3-2で勝利　岡田が決勝打",
            "<p>body</p>",
            categories=[673, 663],
            status="draft",
            featured_media=321,
        )

        self.assertEqual(post_id, 456)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(456, featured_media=321)

    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_promotes_reused_draft_when_publish_requested(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 654,
                    "title": {"raw": "巨人の新外国人右腕をどう見るか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [676],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の新外国人右腕をどう見るか",
            "<p>body</p>",
            categories=[676],
            status="publish",
            featured_media=99,
        )

        self.assertEqual(post_id, 654)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(654, featured_media=99, status="publish")

    @patch.dict(os.environ, {WP_PUBLISH_STATUS_GUARD_ENV: "1"}, clear=False)
    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_blocks_reused_draft_promotion_without_explicit_opt_in(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 655,
                    "title": {"raw": "巨人の新外国人右腕をどう見るか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [676],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の新外国人右腕をどう見るか",
            "<p>body</p>",
            categories=[676],
            status="publish",
            featured_media=99,
        )

        self.assertEqual(post_id, 655)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(655, featured_media=99)

    @patch.dict(os.environ, {WP_PUBLISH_STATUS_GUARD_ENV: "1"}, clear=False)
    @patch.object(WPClient, "update_post_fields")
    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_allows_reused_draft_promotion_with_explicit_opt_in_when_guard_enabled(self, mock_get, mock_post, mock_update):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: [
                {
                    "id": 656,
                    "title": {"raw": "巨人の新外国人右腕をどう見るか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [676],
                }
            ],
        )

        post_id = self.wp.create_post(
            "巨人の新外国人右腕をどう見るか",
            "<p>body</p>",
            categories=[676],
            status="publish",
            featured_media=99,
            allow_status_upgrade=True,
            caller="test.explicit_opt_in",
            source_lane="tests",
        )

        self.assertEqual(post_id, 656)
        mock_post.assert_not_called()
        mock_update.assert_called_once_with(656, featured_media=99, status="publish")

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_create_post_falls_back_when_privileged_search_is_forbidden(self, mock_get, mock_post):
        forbidden = Mock(status_code=400, text='{"code":"rest_forbidden_status"}')
        ok = Mock(
            status_code=200,
            json=lambda: [],
        )
        mock_get.side_effect = [forbidden, ok]
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 789})

        post_id = self.wp.create_post("巨人戦 試合前にどこを見たいか", "<p>body</p>")

        self.assertEqual(post_id, 789)
        self.assertEqual(mock_get.call_count, 2)
        mock_post.assert_called_once()

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_upload_image_from_url_falls_back_to_curl_when_requests_get_fails(self, mock_get, mock_post):
        mock_get.side_effect = OSError("dns failure")
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 321})
        header_result = Mock(stdout=b"HTTP/2 200\r\ncontent-type: image/webp\r\n\r\n")
        body_result = Mock(stdout=b"fake-image-bytes")

        with patch("src.wp_client.subprocess.run", side_effect=[header_result, body_result]) as mock_run:
            media_id = self.wp.upload_image_from_url("https://example.com/image.webp")

        self.assertEqual(media_id, 321)
        self.assertEqual(mock_run.call_count, 2)
        post_headers = mock_post.call_args.kwargs["headers"]
        self.assertEqual(post_headers["Content-Type"], "image/webp")

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def test_upload_image_from_url_skips_unsupported_content_types(self, mock_get, mock_post):
        for content_type in ("text/html; charset=utf-8", "application/octet-stream"):
            with self.subTest(content_type=content_type):
                mock_get.return_value = Mock(
                    status_code=200,
                    headers={"Content-Type": content_type},
                    content=b"not-an-allowed-image",
                )
                mock_get.return_value.raise_for_status = Mock()

                media_id = self.wp.upload_image_from_url("https://example.com/not-image")

                self.assertEqual(media_id, 0)
                mock_post.assert_not_called()
                mock_get.reset_mock()

    @patch("src.wp_client.requests.get")
    def test_list_posts_uses_edit_context_when_available(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=lambda: [{"id": 1}])

        rows = self.wp.list_posts(status="draft", per_page=5, fields=["id", "title"])

        self.assertEqual(rows, [{"id": 1}])
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["status"], "draft")
        self.assertEqual(params["per_page"], 5)
        self.assertEqual(params["context"], "edit")
        self.assertEqual(params["_fields"], "id,title")

    @patch("src.wp_client.requests.get")
    def test_list_posts_retries_without_context(self, mock_get):
        forbidden = Mock(status_code=400, text='{"code":"rest_forbidden_context"}')
        forbidden.raise_for_status.side_effect = requests.HTTPError("bad request")
        ok = Mock(status_code=200, json=lambda: [{"id": 2}])
        mock_get.side_effect = [forbidden, ok]

        rows = self.wp.list_posts(status="draft")

        self.assertEqual(rows, [{"id": 2}])
        self.assertEqual(mock_get.call_count, 2)
        first_params = mock_get.call_args_list[0].kwargs["params"]
        second_params = mock_get.call_args_list[1].kwargs["params"]
        self.assertIn("context", first_params)
        self.assertNotIn("context", second_params)

    def test_get_image_candidate_exclusion_reason_rejects_twimg_emoji_hosts(self):
        for image_url in (
            "https://abs-0.twimg.com/emoji/v2/svg/26a0.svg",
            "https://abs.twimg.com/emoji/v2/svg/26a0.svg",
        ):
            with self.subTest(image_url=image_url):
                self.assertEqual(
                    self.wp._get_image_candidate_exclusion_reason(image_url),
                    "emoji_svg_url",
                )

    def test_get_image_candidate_exclusion_reason_allows_regular_images(self):
        self.assertEqual(
            self.wp._get_image_candidate_exclusion_reason("https://example.com/foo.jpg"),
            "",
        )


class TestWPClientRetryHandling(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch("src.wp_client.requests.get")
    def test_get_post_retries_429_retry_after_then_succeeds(self, mock_get):
        mock_get.side_effect = [
            _mock_response(
                429,
                headers={"Retry-After": "Fri, 01 Jan 2021 00:00:07 GMT"},
                text="too many requests",
            ),
            _mock_response(200, json_data={"id": 42}),
        ]

        with patch("src.wp_client.time.time", return_value=1609459200.0), \
             patch("src.wp_client.time.sleep") as mock_sleep:
            post = self.wp.get_post(42)

        self.assertEqual(post, {"id": 42})
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(7.0)

    @patch("src.wp_client.requests.get")
    def test_get_post_retries_5xx_with_backoff_then_fails(self, mock_get):
        mock_get.return_value = _mock_response(503, text="service unavailable")

        with patch("src.wp_client.random.uniform", return_value=0.25), \
             patch("src.wp_client.time.sleep") as mock_sleep:
            with self.assertRaises(RuntimeError) as ctx:
                self.wp.get_post(99)

        self.assertIn("HTTPエラー", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 4)
        self.assertEqual(mock_sleep.call_args_list, [call(1.25), call(2.25), call(4.25)])

    @patch("src.wp_client.requests.get")
    def test_get_post_4xx_non_429_fails_without_retry(self, mock_get):
        mock_get.return_value = _mock_response(404, text="missing")

        with patch("src.wp_client.time.sleep") as mock_sleep:
            with self.assertRaises(RuntimeError) as ctx:
                self.wp.get_post(100)

        self.assertIn("HTTPエラー", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("src.wp_client.requests.get")
    def test_get_post_retries_urlerror_then_succeeds(self, mock_get):
        mock_get.side_effect = [
            urllib.error.URLError("temporary outage"),
            _mock_response(200, json_data={"id": 55}),
        ]

        with patch("src.wp_client.random.uniform", return_value=0.5), \
             patch("src.wp_client.time.sleep") as mock_sleep:
            post = self.wp.get_post(55)

        self.assertEqual(post, {"id": 55})
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(1.5)


if __name__ == "__main__":
    unittest.main()
