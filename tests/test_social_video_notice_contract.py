from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from src.social_video_notice_contract import (
    OPINION_LEAK_PATTERNS,
    SUBTYPE,
    SUPPORTED_MEDIA_KINDS,
    SUPPORTED_PLATFORMS,
    SocialVideoNoticeArticle,
    SocialVideoNoticePayload,
)


class SocialVideoNoticeContractTests(unittest.TestCase):
    def test_supported_platforms_only_include_instagram_and_youtube(self):
        self.assertEqual(SUPPORTED_PLATFORMS, frozenset({"instagram", "youtube"}))
        self.assertNotIn("x", SUPPORTED_PLATFORMS)
        self.assertNotIn("twitter", SUPPORTED_PLATFORMS)

    def test_supported_media_kinds_include_video_image_and_short(self):
        self.assertEqual(SUPPORTED_MEDIA_KINDS, frozenset({"video", "image", "short"}))

    def test_subtype_constant_is_social_video_notice(self):
        self.assertEqual(SUBTYPE, "social_video_notice")

    def test_opinion_leak_patterns_include_expected_heuristics(self):
        expected = {"だろう", "と思う", "らしい", "噂", "推測", "かもしれない", "期待される", "見られる"}
        self.assertGreaterEqual(len(OPINION_LEAK_PATTERNS), 8)
        self.assertTrue(expected.issubset(set(OPINION_LEAK_PATTERNS)))

    def test_payload_is_frozen_dataclass_with_required_fields(self):
        payload = SocialVideoNoticePayload(
            source_platform="instagram",
            source_url="https://www.instagram.com/p/ABC123/",
            source_account_name="巨人公式",
            source_account_type="official",
            media_kind="video",
            caption_or_title="練習動画を公開した",
            published_at=None,
            supplement_note=None,
        )

        self.assertEqual(payload.source_platform, "instagram")
        self.assertEqual(payload.media_kind, "video")
        with self.assertRaises(FrozenInstanceError):
            payload.media_kind = "image"  # type: ignore[misc]

    def test_article_is_frozen_dataclass_with_required_fields(self):
        article = SocialVideoNoticeArticle(
            subtype="social_video_notice",
            title="巨人公式 練習動画を公開した",
            body_html='<p>出典: <a href="https://www.instagram.com/p/ABC123/">Instagram @巨人公式</a></p>\n<p>練習動画を公開した。</p>',
            badge={"platform": "instagram", "media_kind": "video"},
            nucleus_subject="巨人公式",
            nucleus_event="練習動画を公開した",
            source_platform="instagram",
            source_url="https://www.instagram.com/p/ABC123/",
            source_account_name="巨人公式",
            source_account_type="official",
            media_kind="video",
            published_at=None,
        )

        self.assertEqual(article.subtype, "social_video_notice")
        self.assertEqual(article.badge["platform"], "instagram")
        with self.assertRaises(FrozenInstanceError):
            article.title = "別タイトル"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
