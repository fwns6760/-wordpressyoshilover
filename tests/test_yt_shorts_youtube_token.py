import os
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from src.yt_shorts_youtube_token import (
    build_yt_shorts_publish_url,
    generate_yt_shorts_publish_token,
    is_valid_video_id,
    verify_yt_shorts_publish_token,
)


class YtShortsYoutubeTokenTests(unittest.TestCase):
    def test_generates_and_verifies_video_token(self):
        token = generate_yt_shorts_publish_token("abc123_DEF-4", ttl_seconds=3600, now=1_000)

        self.assertTrue(verify_yt_shorts_publish_token("abc123_DEF-4", token, now=1_100))
        self.assertFalse(verify_yt_shorts_publish_token("abc123_DEF-5", token, now=1_100))
        self.assertFalse(verify_yt_shorts_publish_token("abc123_DEF-4", token, now=9_999))

    def test_rejects_invalid_video_ids(self):
        self.assertFalse(is_valid_video_id(""))
        self.assertFalse(is_valid_video_id("bad/id"))
        self.assertFalse(is_valid_video_id("bad id"))
        self.assertTrue(is_valid_video_id("abc123_DEF-4"))

    def test_secret_change_invalidates_token(self):
        token = generate_yt_shorts_publish_token("abc123_DEF-4", ttl_seconds=3600, now=1_000)
        with patch.dict(os.environ, {"YT_SHORTS_APPROVAL_TOKEN_SECRET": "alt"}, clear=False):
            self.assertFalse(verify_yt_shorts_publish_token("abc123_DEF-4", token, now=1_100))

    def test_builds_publish_url(self):
        url = build_yt_shorts_publish_url(
            "abc123_DEF-4",
            "https://fetcher.example.com/",
            ttl_seconds=3600,
            now=1_000,
        )

        self.assertIsNotNone(url)
        parsed = urlparse(url or "")
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "fetcher.example.com")
        self.assertEqual(parsed.path, "/yt-shorts-publish")
        qs = parse_qs(parsed.query)
        self.assertEqual(qs["video_id"], ["abc123_DEF-4"])
        self.assertTrue(verify_yt_shorts_publish_token("abc123_DEF-4", qs["token"][0], now=1_100))

    def test_missing_base_or_bad_video_returns_none(self):
        self.assertIsNone(build_yt_shorts_publish_url("abc123_DEF-4", ""))
        self.assertIsNone(build_yt_shorts_publish_url("bad/id", "https://fetcher.example.com"))


if __name__ == "__main__":
    unittest.main()
