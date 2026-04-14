import os
import unittest
from unittest.mock import Mock, patch

from src.wp_client import WPClient


class TestWPClientDedup(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

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


if __name__ == "__main__":
    unittest.main()
