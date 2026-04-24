from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from src.social_video_notice_builder import build_social_video_notice_article
from src.social_video_notice_contract import SocialVideoNoticeArticle, SocialVideoNoticePayload
from src.social_video_notice_validator import validate_social_video_notice_article


class SocialVideoNoticeValidatorTests(unittest.TestCase):
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

    def _instagram_article(self, **overrides) -> SocialVideoNoticeArticle:
        article = build_social_video_notice_article(self._instagram_payload())
        return replace(article, **overrides)

    def _youtube_article(self, **overrides) -> SocialVideoNoticeArticle:
        article = build_social_video_notice_article(self._youtube_payload())
        return replace(article, **overrides)

    def test_valid_instagram_article_passes_validation(self):
        result = validate_social_video_notice_article(self._instagram_article())

        self.assertTrue(result.ok)
        self.assertIsNone(result.reason_code)

    def test_valid_youtube_article_passes_validation(self):
        result = validate_social_video_notice_article(self._youtube_article())

        self.assertTrue(result.ok)
        self.assertIsNone(result.reason_code)

    def test_empty_source_url_fails_with_source_missing(self):
        result = validate_social_video_notice_article(self._instagram_article(source_url=""))

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_MISSING")

    def test_empty_source_account_name_fails_with_source_missing(self):
        result = validate_social_video_notice_article(self._instagram_article(source_account_name=""))

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_MISSING")

    def test_empty_source_account_type_fails_with_source_missing(self):
        result = validate_social_video_notice_article(self._instagram_article(source_account_type=""))

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_MISSING")

    def test_platform_x_fails_with_unsupported_platform(self):
        result = validate_social_video_notice_article(self._instagram_article(source_platform="x"))

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "UNSUPPORTED_PLATFORM")

    def test_platform_twitter_fails_with_unsupported_platform(self):
        result = validate_social_video_notice_article(self._instagram_article(source_platform="twitter"))

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "UNSUPPORTED_PLATFORM")

    def test_platform_tiktok_fails_with_unsupported_platform(self):
        result = validate_social_video_notice_article(self._instagram_article(source_platform="tiktok"))

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "UNSUPPORTED_PLATFORM")

    def test_missing_source_url_in_body_fails_with_source_body_mismatch(self):
        article = self._instagram_article(body_html="<p>出典: <a href=\"#\">Instagram @巨人公式</a></p>\n<p>練習動画を公開した。</p>")

        result = validate_social_video_notice_article(article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_BODY_MISMATCH")

    def test_missing_source_account_name_in_body_fails_with_source_body_mismatch(self):
        article = self._instagram_article(
            body_html='<p>出典: <a href="https://www.instagram.com/p/ABC123/">Instagram @公式</a></p>\n<p>練習動画を公開した。</p>'
        )

        result = validate_social_video_notice_article(article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "SOURCE_BODY_MISMATCH")

    def test_opinion_leak_darou_fails_validation(self):
        article = self._instagram_article(
            body_html='<p>出典: <a href="https://www.instagram.com/p/ABC123/">Instagram @巨人公式</a></p>\n<p>練習動画を公開しただろう。</p>'
        )

        result = validate_social_video_notice_article(article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "OPINION_LEAK")

    def test_opinion_leak_rashii_fails_validation(self):
        article = self._instagram_article(
            body_html='<p>出典: <a href="https://www.instagram.com/p/ABC123/">Instagram @巨人公式</a></p>\n<p>練習動画を公開したらしい。</p>'
        )

        result = validate_social_video_notice_article(article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "OPINION_LEAK")

    def test_opinion_leak_uwasa_fails_validation(self):
        article = self._instagram_article(
            body_html='<p>出典: <a href="https://www.instagram.com/p/ABC123/">Instagram @巨人公式</a></p>\n<p>練習動画に関する噂が広がっている。</p>'
        )

        result = validate_social_video_notice_article(article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "OPINION_LEAK")

    def test_subject_absent_from_body_maps_to_title_body_mismatch(self):
        article = self._instagram_article(
            title="坂本勇人が打撃練習を公開した",
            body_html='<p>出典: <a href="https://www.instagram.com/p/ABC123/">Instagram @巨人公式</a></p>\n<p>岡本和真が打撃練習を公開した。</p>',
            nucleus_subject="巨人公式",
        )

        result = validate_social_video_notice_article(article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "TITLE_BODY_MISMATCH")
        self.assertIn("SUBJECT_ABSENT", result.detail or "")

    def test_multiple_nuclei_from_body_maps_to_multiple_nuclei(self):
        article = self._instagram_article(
            title="巨人公式 練習場面を公開した",
            body_html=(
                '<p>出典: <a href="https://www.instagram.com/p/ABC123/">Instagram @巨人公式</a></p>\n'
                "<p>坂本勇人は打撃練習をした。岡本和真は守備練習をした。</p>"
            ),
        )

        result = validate_social_video_notice_article(article)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason_code, "MULTIPLE_NUCLEI")

    def test_cli_round_trip_from_fixture_returns_json_and_exit_zero(self):
        payload = asdict(self._instagram_payload())
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "payload.json"
            fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "src.tools.run_social_video_notice_dry_run", "--fixture", str(fixture_path)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["validation"]["ok"])
        self.assertEqual(report["article"]["subtype"], "social_video_notice")

    def test_cli_round_trip_from_stdin_returns_exit_one_on_validation_fail(self):
        payload = asdict(self._instagram_payload(source_platform="tiktok"))
        completed = subprocess.run(
            [sys.executable, "-m", "src.tools.run_social_video_notice_dry_run", "--stdin"],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 1)
        report = json.loads(completed.stdout)
        self.assertFalse(report["validation"]["ok"])
        self.assertEqual(report["validation"]["reason_code"], "UNSUPPORTED_PLATFORM")


if __name__ == "__main__":
    unittest.main()
