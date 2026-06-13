import unittest
from types import SimpleNamespace

from src.yt_shorts_publish_handler import handle_get, handle_post
from src.yt_shorts_youtube_token import generate_yt_shorts_publish_token


NOW = 1_700_000_000
VIDEO_ID = "abc123_DEF-4"
TOKEN = generate_yt_shorts_publish_token(VIDEO_ID, ttl_seconds=3600, now=NOW)


class YtShortsPublishHandlerTests(unittest.TestCase):
    def test_get_returns_confirmation_page(self):
        code, body, headers = handle_get(video_id=VIDEO_ID, token=TOKEN, now=NOW + 10)

        self.assertEqual(code, 200)
        self.assertEqual(headers, {})
        self.assertIn("YouTube Shortsを公開", body)
        self.assertIn(VIDEO_ID, body)
        self.assertIn('method="POST"', body)

    def test_get_rejects_bad_token(self):
        code, body, _ = handle_get(video_id=VIDEO_ID, token="bad.token", now=NOW + 10)

        self.assertEqual(code, 403)
        self.assertIn("token", body)

    def test_post_publishes_video(self):
        calls = []

        def publish(video_id):
            calls.append(video_id)
            return SimpleNamespace(privacy_status="public")

        code, body, headers = handle_post(
            video_id=VIDEO_ID,
            token=TOKEN,
            publish_video=publish,
            now=NOW + 10,
        )

        self.assertEqual(code, 200)
        self.assertEqual(headers, {})
        self.assertEqual(calls, [VIDEO_ID])
        self.assertIn("公開完了", body)
        self.assertIn("YouTubeで開く", body)

    def test_post_rejects_invalid_video_id_without_publish_call(self):
        calls = []

        code, _, _ = handle_post(
            video_id="bad/id",
            token=TOKEN,
            publish_video=lambda video_id: calls.append(video_id),
            now=NOW + 10,
        )

        self.assertEqual(code, 400)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
