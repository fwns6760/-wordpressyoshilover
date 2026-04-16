import os
import unittest
from unittest.mock import Mock, patch

import requests

from src.wp_client import WPClient


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
                    "title": {"raw": "田中将大「打線を線にしない」 実戦で何を見せるか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )

        post_id = self.wp.create_draft(
            "田中将大「打線を線にしない」 実戦で何を見せるか",
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
                    "title": {"raw": "阿部監督「粘り勝った」 ベンチの狙いはどこか"},
                    "status": "draft",
                    "date": "2099-04-14T17:39:28",
                    "featured_media": 0,
                    "categories": [663],
                }
            ],
        )

        post_id = self.wp.create_post(
            "阿部監督「粘り勝った」 ベンチの狙いはどこか",
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
            "松本剛「甘いところを絞って打ちに行こう」 実戦で何を見せるか",
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


if __name__ == "__main__":
    unittest.main()
