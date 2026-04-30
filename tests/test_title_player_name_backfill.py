import logging
import unittest

from src import rss_fetcher
from src.title_player_name_backfiller import backfill_title_player_name


class TitlePlayerNameBackfillTests(unittest.TestCase):
    def test_lineup_title_backfills_name_from_source_body(self):
        result = backfill_title_player_name(
            existing_title='巨人スタメン が「2番・二塁」で今季初先発',
            source_title='巨人スタメン が「2番・二塁」で今季初先発',
            body="吉川尚輝が「2番・二塁」で今季初先発となった。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, '吉川尚輝選手が「2番・二塁」で今季初先発')
        self.assertTrue(result.changed)
        self.assertEqual(result.review_reason, "")

    def test_comment_title_backfills_speaker_and_quote(self):
        result = backfill_title_player_name(
            existing_title="投手コメント整理",
            source_title='山田太郎投手「真っすぐで押せた」試合後コメント',
            body='山田太郎投手が試合後に「真っすぐで押せた」と振り返った。',
            metadata={"speaker": "山田太郎"},
        )

        self.assertEqual(result.title, '山田太郎投手「真っすぐで押せた」試合後コメント')
        self.assertEqual(result.review_reason, "")

    def test_unresolved_title_returns_source_title_and_review_reason(self):
        result = backfill_title_player_name(
            existing_title="選手、登録抹消 関連情報",
            source_title="選手、登録抹消 関連情報",
            body="球団が登録抹消を発表した。",
        )

        self.assertEqual(result.title, "選手、登録抹消 関連情報")
        self.assertEqual(result.review_reason, "title_player_name_unresolved")

    def test_generic_one_word_titles_backfill_or_emit_review_reason(self):
        cases = [
            {
                "title": "選手",
                "body": "吉川尚輝選手がスタメン入りした。",
                "metadata": {},
                "expected_title": "吉川尚輝選手",
                "expected_reason": "",
            },
            {
                "title": "投手",
                "body": "山田太郎投手がブルペン入りした。",
                "metadata": {"speaker": "山田太郎"},
                "expected_title": "山田太郎投手",
                "expected_reason": "",
            },
            {
                "title": "チーム",
                "body": "球団がコメントを発表した。",
                "metadata": {},
                "expected_title": "チーム",
                "expected_reason": "title_player_name_unresolved",
            },
        ]

        for case in cases:
            with self.subTest(title=case["title"]):
                result = backfill_title_player_name(
                    existing_title=case["title"],
                    source_title=case["title"],
                    body=case["body"],
                    metadata=case["metadata"],
                )
                self.assertEqual(result.title, case["expected_title"])
                self.assertEqual(result.review_reason, case["expected_reason"])

    def test_multiple_candidates_choose_first_without_joining_names(self):
        result = backfill_title_player_name(
            existing_title='巨人スタメン が「2番・二塁」で今季初先発',
            source_title='巨人スタメン が「2番・二塁」で今季初先発',
            body="吉川尚輝と門脇誠がスタメン入りし、吉川尚輝が2番二塁で今季初先発となった。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, '吉川尚輝選手が「2番・二塁」で今季初先発')
        self.assertNotIn("門脇誠", result.title)

    def test_fetcher_adapter_uses_comparison_title_for_unresolved_case(self):
        final_title, comparison_title = rss_fetcher._apply_title_player_name_backfill(
            rewritten_title="投手コメント整理",
            source_title="投手コメント整理",
            source_body="投手の談話を整理した。",
            summary="投手の談話を整理した。",
            category="選手情報",
            article_subtype="player",
            logger=logging.getLogger("rss_fetcher"),
            source_name="報知 巨人",
            source_url="https://example.com/story",
        )

        fallback = rss_fetcher._maybe_route_weak_subject_title_review(
            article_subtype="player",
            rewritten_title=final_title,
            original_title=comparison_title,
            source_name="報知 巨人",
            logger=logging.getLogger("rss_fetcher"),
        )

        self.assertEqual(final_title, "投手コメント整理")
        self.assertEqual(comparison_title, "投手コメント整理")
        self.assertIsNone(fallback)


if __name__ == "__main__":
    unittest.main()
