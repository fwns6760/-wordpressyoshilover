from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from src.x_source_notice_contract import (
    BANNED_OPINION_PHRASES,
    SUBTYPE,
    SUPPORTED_ACCOUNT_TYPES,
    SUPPORTED_PLATFORMS,
    SUPPORTED_POST_KINDS,
    SUPPORTED_TIERS,
    XSourceNoticeArticle,
    XSourceNoticePayload,
)


class XSourceNoticeContractTests(unittest.TestCase):
    def test_supported_platforms_only_include_x(self):
        self.assertEqual(SUPPORTED_PLATFORMS, ("x",))
        self.assertNotIn("instagram", SUPPORTED_PLATFORMS)
        self.assertNotIn("youtube", SUPPORTED_PLATFORMS)

    def test_supported_tiers_only_include_fact_and_topic(self):
        self.assertEqual(SUPPORTED_TIERS, ("fact", "topic"))
        self.assertNotIn("reaction", SUPPORTED_TIERS)

    def test_supported_post_kinds_exclude_repost(self):
        self.assertEqual(SUPPORTED_POST_KINDS, ("post", "quote", "reply"))
        self.assertNotIn("repost", SUPPORTED_POST_KINDS)

    def test_supported_account_types_match_x_lane_contract(self):
        self.assertEqual(
            SUPPORTED_ACCOUNT_TYPES,
            ("team_official", "league_official", "press_major", "press_reporter", "press_misc"),
        )

    def test_subtype_constant_is_x_source_notice(self):
        self.assertEqual(SUBTYPE, "x_source_notice")

    def test_banned_opinion_phrases_include_067_aligned_literals(self):
        expected = {
            "どう見る",
            "本音",
            "思い",
            "語る",
            "コメントまとめ",
            "試合後コメント",
            "注目したい",
            "振り返りたい",
        }
        self.assertTrue(expected.issubset(set(BANNED_OPINION_PHRASES)))

    def test_payload_is_frozen_dataclass(self):
        payload = XSourceNoticePayload(
            source_platform="x",
            source_url="https://x.com/giants/status/1",
            source_account_name="読売ジャイアンツ",
            source_account_type="team_official",
            source_tier="fact",
            post_kind="post",
            post_text="巨人は坂本勇人を出場選手登録した",
            published_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
            supplement_note=None,
        )

        self.assertEqual(payload.source_platform, "x")
        self.assertEqual(payload.post_kind, "post")
        with self.assertRaises(FrozenInstanceError):
            payload.post_kind = "reply"  # type: ignore[misc]

    def test_article_is_frozen_dataclass(self):
        article = XSourceNoticeArticle(
            title="読売ジャイアンツ、坂本勇人を出場選手登録した",
            body_html='<p>出典: 読売ジャイアンツ [fact] <a href="https://x.com/giants/status/1">https://x.com/giants/status/1</a></p>\n<p>「坂本勇人を出場選手登録した」という投稿。</p>',
            badge={
                "platform": "x",
                "source_tier": "fact",
                "post_kind": "post",
                "account_type": "team_official",
            },
            nucleus_subject="球団",
            nucleus_event="坂本勇人を出場選手登録した",
            source_platform="x",
            source_url="https://x.com/giants/status/1",
            source_account_name="読売ジャイアンツ",
            source_account_type="team_official",
            source_tier="fact",
            post_kind="post",
            published_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(article.subtype, "x_source_notice")
        self.assertEqual(article.badge["platform"], "x")
        with self.assertRaises(FrozenInstanceError):
            article.title = "別タイトル"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
