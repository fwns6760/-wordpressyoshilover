from __future__ import annotations

import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from src.title_body_nucleus_validator import validate_title_body_nucleus
from src.x_source_notice_builder import build_x_source_notice_article
from src.x_source_notice_contract import XSourceNoticePayload
from src.x_source_notice_validator import validate_x_source_notice


class XSourceNoticeValidatorTests(unittest.TestCase):
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

    def _article(self, *, topic_recheck_passed: bool = False, **payload_overrides):
        payload = self._payload(**payload_overrides)
        article = build_x_source_notice_article(payload, topic_recheck_passed=topic_recheck_passed)
        return payload, article

    def test_valid_fact_article_passes_validation(self):
        payload, article = self._article()

        result = validate_x_source_notice(payload, article)

        self.assertTrue(result.ok)
        self.assertIsNone(result.reason_code)

    def test_source_missing_empty_source_url_fails(self):
        payload, article = self._article(source_url="")

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_MISSING")

    def test_source_missing_empty_source_account_name_fails(self):
        payload, article = self._article(source_account_name="")

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_MISSING")

    def test_source_missing_empty_post_text_fails(self):
        payload, article = self._article(post_text="")

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_MISSING")

    def test_unsupported_platform_fails(self):
        payload, article = self._article(source_platform="instagram")

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "UNSUPPORTED_PLATFORM")

    def test_unsupported_tier_fails(self):
        payload, article = self._article(source_tier="reaction")

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "UNSUPPORTED_TIER")

    def test_unsupported_post_kind_fails(self):
        payload, article = self._article(post_kind="repost")

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "UNSUPPORTED_POST_KIND")

    def test_source_body_mismatch_missing_source_url_fails(self):
        payload, article = self._article()
        article = replace(
            article,
            body_html='<p>出典: 読売ジャイアンツ [fact] <a href="https://x.com/giants/status/other">https://x.com/giants/status/other</a></p>\n<p>「坂本勇人を出場選手登録した」という投稿。</p>',
        )

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_BODY_MISMATCH")

    def test_source_body_mismatch_missing_source_account_name_fails(self):
        payload, article = self._article()
        article = replace(
            article,
            body_html='<p>出典: 巨人公式 [fact] <a href="https://x.com/giants/status/1001">https://x.com/giants/status/1001</a></p>\n<p>「坂本勇人を出場選手登録した」という投稿。</p>',
        )

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_BODY_MISMATCH")

    def test_multiple_nuclei_is_preserved_from_071(self):
        payload, article = self._article(
            source_account_name="報知プロ野球担当",
            source_account_type="press_reporter",
            post_text="報知プロ野球担当が登録を報じた",
        )
        article = replace(
            article,
            title="報知プロ野球担当、登録を報じる",
            body_html=(
                '<p>出典: 報知プロ野球担当 [fact] <a href="https://x.com/giants/status/1001">https://x.com/giants/status/1001</a></p>\n'
                "<p>坂本勇人は登録された。岡本和真は抹消された。</p>"
            ),
        )

        nucleus_result = validate_title_body_nucleus(
            article.title,
            article.body_html,
            subtype="x_source_notice",
            known_subjects=[payload.source_account_name],
        )
        result = validate_x_source_notice(payload, article)

        self.assertEqual(nucleus_result.reason_code, "MULTIPLE_NUCLEI")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "MULTIPLE_NUCLEI")

    def test_subject_absent_maps_to_title_body_mismatch(self):
        payload, article = self._article(source_account_name="報知プロ野球担当", source_account_type="press_reporter")
        article = replace(
            article,
            title="坂本勇人が登録",
            body_html=(
                '<p>出典: 報知プロ野球担当 [fact] <a href="https://x.com/giants/status/1001">https://x.com/giants/status/1001</a></p>\n'
                "<p>岡本和真が登録された。</p>"
            ),
        )

        nucleus_result = validate_title_body_nucleus(
            article.title,
            article.body_html,
            subtype="x_source_notice",
            known_subjects=[payload.source_account_name],
        )
        result = validate_x_source_notice(payload, article)

        self.assertEqual(nucleus_result.reason_code, "SUBJECT_ABSENT")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "TITLE_BODY_MISMATCH")
        self.assertIn("SUBJECT_ABSENT", result.detail or "")

    def test_event_diverge_maps_to_title_body_mismatch(self):
        payload, article = self._article()
        article = replace(
            article,
            title="巨人、出場選手登録を発表",
            body_html=(
                '<p>出典: 読売ジャイアンツ [fact] <a href="https://x.com/giants/status/1001">https://x.com/giants/status/1001</a></p>\n'
                "<p>巨人は抹消を発表した。</p>"
            ),
        )

        nucleus_result = validate_title_body_nucleus(
            article.title,
            article.body_html,
            subtype="x_source_notice",
            known_subjects=[payload.source_account_name],
        )
        result = validate_x_source_notice(payload, article)

        self.assertEqual(nucleus_result.reason_code, "EVENT_DIVERGE")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "TITLE_BODY_MISMATCH")
        self.assertIn("EVENT_DIVERGE", result.detail or "")

    def test_opinion_leak_in_title_fails(self):
        payload, article = self._article()
        article = replace(article, title="読売ジャイアンツの本音をどう見る")

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "OPINION_LEAK")

    def test_opinion_leak_in_body_fails(self):
        payload, article = self._article()
        article = replace(
            article,
            body_html=(
                '<p>出典: 読売ジャイアンツ [fact] <a href="https://x.com/giants/status/1001">https://x.com/giants/status/1001</a></p>\n'
                "<p>この投稿をどう見るかが話題になっている。</p>"
            ),
        )

        result = validate_x_source_notice(payload, article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "OPINION_LEAK")

    def test_topic_tier_fact_style_title_without_recheck_fails(self):
        payload, article = self._article(
            source_account_name="報知プロ野球担当",
            source_account_type="press_reporter",
            source_tier="topic",
            post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
        )
        article = replace(article, title="報知プロ野球担当、阿部監督が坂本勇人の一軍復帰を示唆した")

        result = validate_x_source_notice(payload, article, topic_recheck_passed=False)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "TOPIC_TIER_AS_FACT")

    def test_topic_tier_fact_style_title_with_recheck_passes(self):
        payload, article = self._article(
            topic_recheck_passed=True,
            source_account_name="報知プロ野球担当",
            source_account_type="press_reporter",
            source_tier="topic",
            post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
        )
        article = replace(article, title="報知プロ野球担当、阿部監督が坂本勇人の一軍復帰を示唆した")

        result = validate_x_source_notice(payload, article, topic_recheck_passed=True)

        self.assertTrue(result.ok)
        self.assertIsNone(result.reason_code)

    def test_topic_candidate_title_without_recheck_passes(self):
        payload, article = self._article(
            source_account_name="報知プロ野球担当",
            source_account_type="press_reporter",
            source_tier="topic",
            post_text="阿部監督が坂本勇人の一軍復帰を示唆した",
        )

        result = validate_x_source_notice(payload, article, topic_recheck_passed=False)

        self.assertTrue(result.ok)
        self.assertIsNone(result.reason_code)

    def test_dry_run_cli_prints_expected_ok_and_reject_mix(self):
        completed = subprocess.run(
            [sys.executable, "-m", "src.tools.run_x_source_notice_dry_run"],
            capture_output=True,
            text=True,
            check=False,
        )

        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(lines), 6)
        self.assertEqual(sum(line.startswith("[OK]") for line in lines), 3)
        self.assertEqual(sum(line.startswith("[REJECT") for line in lines), 3)


if __name__ == "__main__":
    unittest.main()
