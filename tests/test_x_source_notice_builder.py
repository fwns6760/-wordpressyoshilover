from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone

from src.x_source_notice_builder import build_x_source_notice_article
from src.x_source_notice_contract import XSourceNoticePayload


class XSourceNoticeBuilderTests(unittest.TestCase):
    def _payload(self, **overrides) -> XSourceNoticePayload:
        payload = XSourceNoticePayload(
            source_platform="x",
            source_url="https://x.com/giants/status/1001",
            source_account_name="読売ジャイアンツ",
            source_account_type="team_official",
            source_tier="fact",
            post_kind="post",
            post_text="巨人は坂本勇人を出場選手登録した",
            published_at=datetime(2026, 4, 24, 9, 0, tzinfo=timezone.utc),
            supplement_note="球団公式アカウントの告知",
        )
        return replace(payload, **overrides)

    def test_fact_tier_builds_fact_style_title(self):
        article = build_x_source_notice_article(self._payload())

        self.assertEqual(article.title, "読売ジャイアンツ、坂本勇人を出場選手登録した")

    def test_topic_tier_without_recheck_builds_candidate_title(self):
        article = build_x_source_notice_article(
            self._payload(
                source_account_name="報知プロ野球担当",
                source_account_type="press_reporter",
                source_tier="topic",
                post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
            ),
            topic_recheck_passed=False,
        )

        self.assertEqual(article.title, "報知プロ野球担当が報じる: 阿部監督が坂本勇人の一軍復帰を示唆した")

    def test_topic_tier_with_recheck_builds_fact_style_title(self):
        article = build_x_source_notice_article(
            self._payload(
                source_account_name="スポーツ報知 巨人担当",
                source_account_type="press_major",
                source_tier="topic",
                post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
            ),
            topic_recheck_passed=True,
        )

        self.assertEqual(article.title, "スポーツ報知 巨人担当、阿部監督が坂本勇人の一軍復帰を示唆した")

    def test_body_first_line_contains_source_account_tier_and_url(self):
        article = build_x_source_notice_article(self._payload())

        self.assertEqual(
            article.body_html.splitlines()[0],
            '<p>出典: 読売ジャイアンツ [fact] <a href="https://x.com/giants/status/1001">https://x.com/giants/status/1001</a></p>',
        )

    def test_body_second_line_quotes_post_text_summary(self):
        article = build_x_source_notice_article(self._payload())

        self.assertEqual(article.body_html.splitlines()[1], "<p>「坂本勇人を出場選手登録した」という投稿。</p>")

    def test_body_includes_supplement_line_when_present(self):
        article = build_x_source_notice_article(self._payload())

        self.assertEqual(article.body_html.splitlines()[2], "<p>補足: 球団公式アカウントの告知。</p>")

    def test_body_omits_supplement_line_when_absent(self):
        article = build_x_source_notice_article(self._payload(supplement_note=None))

        self.assertEqual(len(article.body_html.splitlines()), 2)

    def test_badge_contains_platform_tier_post_kind_and_account_type(self):
        article = build_x_source_notice_article(self._payload())

        self.assertEqual(
            article.badge,
            {
                "platform": "x",
                "source_tier": "fact",
                "post_kind": "post",
                "account_type": "team_official",
            },
        )

    def test_team_official_nucleus_subject_is_team_bucket(self):
        article = build_x_source_notice_article(self._payload())

        self.assertEqual(article.nucleus_subject, "球団")

    def test_league_official_nucleus_subject_is_npb(self):
        article = build_x_source_notice_article(
            self._payload(
                source_account_name="NPB",
                source_account_type="league_official",
                post_text="セ・リーグ公式戦の日程を告知した",
            )
        )

        self.assertEqual(article.nucleus_subject, "NPB")

    def test_press_account_nucleus_subject_is_account_name(self):
        article = build_x_source_notice_article(
            self._payload(
                source_account_name="報知プロ野球担当",
                source_account_type="press_misc",
                source_tier="topic",
                post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
            )
        )

        self.assertEqual(article.nucleus_subject, "報知プロ野球担当")

    def test_builder_normalizes_twitter_domain_to_x_domain(self):
        article = build_x_source_notice_article(self._payload(source_url="https://twitter.com/giants/status/1001?ref=twsrc"))

        self.assertEqual(article.source_url, "https://x.com/giants/status/1001")
        self.assertIn("https://x.com/giants/status/1001", article.body_html)


if __name__ == "__main__":
    unittest.main()
