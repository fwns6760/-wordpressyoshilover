import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.x_published_poster import (
    HARD_FAIL_CANONICAL_MISSING,
    HARD_FAIL_CANONICAL_PREVIEW,
    HARD_FAIL_DUPLICATE_24H,
    HARD_FAIL_POST_STATUS,
    HARD_FAIL_PUBLISHED_AT_RANGE,
    HARD_FAIL_TEASER_BANNED,
    HARD_FAIL_TEASER_GENERIC,
    HARD_FAIL_TEASER_LENGTH,
    PostPayload,
    PublishedArticle,
    build_post,
    find_banned_phrases,
    generate_teaser,
    load_post_history,
    record_post_history,
    validate_post,
)


NOW = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)


class XPublishedPosterTests(unittest.TestCase):
    def _article(self, **overrides) -> PublishedArticle:
        article = PublishedArticle(
            article_id=123,
            title="巨人、延長12回サヨナラで連敗ストップ",
            excerpt="巨人が延長12回サヨナラで連敗を止めた試合を振り返る。救援陣が踏ん張り、終盤の粘りが勝利につながった。",
            body_first_paragraph=(
                "<p>巨人が延長12回サヨナラで連敗を止めた。救援陣が踏ん張り、終盤の粘りが勝利につながった試合だった。</p>"
            ),
            canonical_url="https://yoshilover.com/giants-win-20260423/",
            published_at=(NOW - timedelta(hours=2)).isoformat(),
            post_status="publish",
        )
        return PublishedArticle(**{**article.__dict__, **overrides})

    def test_generate_teaser_uses_excerpt_when_in_range(self):
        article = self._article(
            excerpt="<p>巨人が延長12回サヨナラで連敗を止めた試合を振り返る。救援陣が踏ん張り、終盤の粘りが勝利につながった。</p>",
            body_first_paragraph="<p>本文の別要約。</p>",
        )

        teaser = generate_teaser(article)

        self.assertEqual(
            teaser,
            "巨人が延長12回サヨナラで連敗を止めた試合を振り返る。救援陣が踏ん張り、終盤の粘りが勝利につながった。",
        )

    def test_generate_teaser_uses_first_paragraph_when_excerpt_fails(self):
        article = self._article(
            excerpt="短い要約",
            body_first_paragraph=(
                "<p>巨人が延長12回サヨナラで連敗を止めた。救援陣が踏ん張り、終盤の粘りが勝利につながった試合だった。"
                "この日の東京ドームは最後まで緊張感が続き、ベンチワークも含めて勝負どころを逃さなかった。</p>"
            ),
        )

        teaser = generate_teaser(article)

        self.assertIsNotNone(teaser)
        self.assertTrue(teaser.endswith("。"))
        self.assertGreaterEqual(len(teaser), 40)
        self.assertLessEqual(len(teaser), 120)

    def test_generate_teaser_uses_title_when_other_paths_fail(self):
        article = self._article(
            excerpt="短い",
            body_first_paragraph="<p>短い本文</p>",
            title="巨人、延長12回サヨナラで連敗ストップ",
        )

        teaser = generate_teaser(article)

        self.assertEqual(teaser, "巨人、延長12回サヨナラで連敗ストップ")

    def test_build_post_returns_none_when_all_teaser_paths_fail(self):
        article = self._article(
            excerpt="短い",
            body_first_paragraph="<p>短い</p>",
            title="短い題",
        )

        teaser = generate_teaser(article)
        validation = validate_post(article, teaser, article.canonical_url, now=NOW)

        self.assertIsNone(build_post(article, now=NOW))
        self.assertIsNone(teaser)
        self.assertEqual(validation.hard_fail_code, HARD_FAIL_TEASER_GENERIC)

    def test_validate_post_rejects_non_publish_status(self):
        article = self._article(post_status="draft")

        result = validate_post(article, generate_teaser(article), article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_POST_STATUS)

    def test_validate_post_rejects_missing_canonical_url(self):
        article = self._article(canonical_url="")

        result = validate_post(article, generate_teaser(article), article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_CANONICAL_MISSING)

    def test_validate_post_rejects_preview_and_private_canonical_patterns(self):
        for url in (
            "https://yoshilover.com/?preview=true",
            "https://yoshilover.com/?p=123",
            "http://yoshilover.com/giants-win-20260423/",
            "https://localhost/internal-post",
        ):
            with self.subTest(url=url):
                article = self._article(canonical_url=url)
                result = validate_post(article, generate_teaser(article), article.canonical_url, now=NOW)
                self.assertEqual(result.hard_fail_code, HARD_FAIL_CANONICAL_PREVIEW)

    def test_validate_post_rejects_banned_official_voice_phrase(self):
        article = self._article(title="巨人の試合後コメントをどう見る")

        result = validate_post(article, "巨人の試合後コメントをどう見る", article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_TEASER_BANNED)
        self.assertIn("どう見る", result.matched_banned_phrases)

    def test_validate_post_rejects_banned_exaggeration_phrase(self):
        article = self._article(title="巨人が圧倒的で史上最高の勝利")

        result = validate_post(article, "巨人が圧倒的で史上最高の勝利", article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_TEASER_BANNED)
        self.assertIn("圧倒的", result.matched_banned_phrases)

    def test_validate_post_rejects_too_short_teaser(self):
        article = self._article()

        result = validate_post(article, "あ" * 9, article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_TEASER_LENGTH)

    def test_validate_post_rejects_too_long_teaser(self):
        article = self._article()

        result = validate_post(article, "あ" * 121, article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_TEASER_LENGTH)

    def test_validate_post_rejects_future_published_at(self):
        article = self._article(published_at=(NOW + timedelta(minutes=5)).isoformat())

        result = validate_post(article, generate_teaser(article), article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_PUBLISHED_AT_RANGE)

    def test_validate_post_rejects_stale_published_at(self):
        article = self._article(published_at=(NOW - timedelta(days=731)).isoformat())

        result = validate_post(article, generate_teaser(article), article.canonical_url, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_PUBLISHED_AT_RANGE)

    def test_validate_post_rejects_recent_duplicate(self):
        article = self._article(article_id=999)
        history = {"999": (NOW - timedelta(hours=3)).isoformat()}

        result = validate_post(article, generate_teaser(article), article.canonical_url, post_history=history, now=NOW)

        self.assertEqual(result.hard_fail_code, HARD_FAIL_DUPLICATE_24H)

    def test_build_post_returns_payload_for_valid_article(self):
        article = self._article()

        payload = build_post(article, now=NOW)

        self.assertIsInstance(payload, PostPayload)
        self.assertEqual(payload.article_id, 123)
        self.assertEqual(payload.text, f"{payload.teaser}\n{payload.canonical_url}")

    def test_find_banned_phrases_detects_assertive_and_question_patterns(self):
        self.assertIn("〜が確定", find_banned_phrases("巨人の先発が確定"))
        self.assertIn("煽り疑問形", find_banned_phrases("巨人はこの流れを変えられるのか?"))

    def test_history_helpers_round_trip_json_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "posted_history.json"
            history = load_post_history(history_path)

            record_post_history(history_path, history, 321, posted_at=NOW)
            loaded = load_post_history(history_path)

            self.assertIn("321", loaded)
            self.assertEqual(loaded["321"], NOW.isoformat())


if __name__ == "__main__":
    unittest.main()
