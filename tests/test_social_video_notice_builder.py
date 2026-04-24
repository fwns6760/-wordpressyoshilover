from __future__ import annotations

import unittest
from dataclasses import replace

from src.social_video_notice_builder import build_social_video_notice_article
from src.social_video_notice_contract import SocialVideoNoticePayload


class SocialVideoNoticeBuilderTests(unittest.TestCase):
    def _instagram_payload(self, **overrides) -> SocialVideoNoticePayload:
        payload = SocialVideoNoticePayload(
            source_platform="instagram",
            source_url="https://www.instagram.com/p/ABC123/",
            source_account_name="巨人公式",
            source_account_type="official",
            media_kind="video",
            caption_or_title="練習動画を公開した",
            published_at="2026-04-24T09:00:00+09:00",
            supplement_note="東京ドームでの調整場面が確認できる",
        )
        return replace(payload, **overrides)

    def _youtube_payload(self, **overrides) -> SocialVideoNoticePayload:
        payload = SocialVideoNoticePayload(
            source_platform="youtube",
            source_url="https://www.youtube.com/watch?v=abc123",
            source_account_name="GIANTS TV",
            source_account_type="official",
            media_kind="short",
            caption_or_title="試合前映像を公開した",
            published_at="2026-04-24T10:30:00+09:00",
            supplement_note=None,
        )
        return replace(payload, **overrides)

    def test_builder_creates_article_for_instagram_payload(self):
        article = build_social_video_notice_article(self._instagram_payload())

        self.assertEqual(article.title, "巨人公式 練習動画を公開した")
        self.assertIn("出典:", article.body_html)
        self.assertEqual(article.badge, {"platform": "instagram", "media_kind": "video"})
        self.assertEqual(article.nucleus_subject, "巨人公式")
        self.assertEqual(article.nucleus_event, "練習動画を公開した")

    def test_builder_creates_article_for_youtube_payload(self):
        article = build_social_video_notice_article(self._youtube_payload())

        self.assertEqual(article.title, "GIANTS TV 試合前映像を公開した")
        self.assertIn("YouTube @GIANTS TV", article.body_html)
        self.assertEqual(article.badge, {"platform": "youtube", "media_kind": "short"})
        self.assertEqual(article.nucleus_subject, "GIANTS TV")
        self.assertEqual(article.nucleus_event, "試合前映像を公開した")

    def test_body_first_line_always_contains_source_marker(self):
        article = build_social_video_notice_article(self._instagram_payload())

        self.assertIn("出典:", article.body_html.splitlines()[0])

    def test_body_first_line_contains_source_url_in_anchor_href(self):
        article = build_social_video_notice_article(self._instagram_payload())

        self.assertIn('href="https://www.instagram.com/p/ABC123/"', article.body_html.splitlines()[0])

    def test_body_first_line_contains_source_account_name(self):
        article = build_social_video_notice_article(self._instagram_payload())

        self.assertIn("巨人公式", article.body_html.splitlines()[0])

    def test_body_second_line_contains_caption_summary(self):
        article = build_social_video_notice_article(self._instagram_payload())

        self.assertEqual(article.body_html.splitlines()[1], "<p>練習動画を公開した。</p>")

    def test_builder_includes_supplement_note_as_third_line_when_present(self):
        article = build_social_video_notice_article(self._instagram_payload())

        self.assertEqual(article.body_html.splitlines()[2], "<p>東京ドームでの調整場面が確認できる。</p>")

    def test_builder_omits_third_line_when_supplement_note_is_absent(self):
        article = build_social_video_notice_article(self._instagram_payload(supplement_note=None))

        self.assertEqual(len(article.body_html.splitlines()), 2)

    def test_builder_sets_subtype_to_social_video_notice(self):
        article = build_social_video_notice_article(self._youtube_payload())

        self.assertEqual(article.subtype, "social_video_notice")

    def test_builder_returns_badge_dict_with_platform_and_media_kind(self):
        article = build_social_video_notice_article(self._instagram_payload())

        self.assertEqual(article.badge, {"platform": "instagram", "media_kind": "video"})

    def test_builder_trims_title_to_maximum_48_characters(self):
        article = build_social_video_notice_article(
            self._instagram_payload(caption_or_title="キャンプ初日のロングティー映像を公開したキャンプ初日のロングティー映像を公開した")
        )

        self.assertLessEqual(len(article.title), 48)
        self.assertTrue(article.title.startswith("巨人公式 "))


if __name__ == "__main__":
    unittest.main()
