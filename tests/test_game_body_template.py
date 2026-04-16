import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class GameBodyTemplateTests(unittest.TestCase):
    def test_game_body_fixture_uses_required_sections(self):
        with open(FIXTURE_DIR / "game_body_template_golden.json", encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                lineup_rows = case.get("lineup_rows", [])
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=lineup_rows):
                        with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                            blocks, ai_body = rss_fetcher.build_news_block(
                                title=case["title"],
                                summary=case["summary"],
                                url="https://example.com/post",
                                source_name="スポーツ報知",
                                category="試合速報",
                                has_game=True,
                            )

                required_headings = rss_fetcher._game_required_headings(case["subtype"])
                self.assertEqual(rss_fetcher._game_section_count(ai_body, case["subtype"]), len(required_headings))
                for heading in required_headings:
                    self.assertIn(heading, ai_body)
                self.assertIn(f"<h2>{required_headings[0]}</h2>", blocks)
                for heading in required_headings[1:]:
                    self.assertIn(f"<h3>{heading}</h3>", blocks)
                for expected in case["required_strings"]:
                    self.assertIn(expected, ai_body)

    def test_game_generic_ai_output_is_replaced_with_template(self):
        generic_cases = [
            (
                "lineup",
                "【巨人】今日のスタメン発表　1番丸、4番岡田",
                "巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。予告先発は田中将大投手。",
            ),
            (
                "postgame",
                "【巨人】阪神に3-2で勝利　岡田が決勝打",
                "巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
            ),
            (
                "pregame",
                "【巨人】雨天中止で先発予定だった田中将大は16日にスライド登板",
                "巨人田中将大投手が雨天中止にともなってスライド登板することになった。",
            ),
        ]
        for subtype, title, summary in generic_cases:
            with self.subTest(subtype=subtype):
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[]):
                        with patch.object(
                            rss_fetcher,
                            "generate_article_with_gemini",
                            return_value="【ニュースの整理】\n汎用本文\n【次の注目】\n汎用の注目点",
                        ):
                            _, ai_body = rss_fetcher.build_news_block(
                                title=title,
                                summary=summary,
                                url="https://example.com/post",
                                source_name="スポーツ報知",
                                category="試合速報",
                                has_game=True,
                            )

                self.assertEqual(
                    rss_fetcher._game_section_count(ai_body, subtype),
                    len(rss_fetcher._game_required_headings(subtype)),
                )

    def test_game_body_template_applied_log_payload(self):
        logger = logging.getLogger("test_game_body_template_log")
        with self.assertLogs(logger, level="INFO") as cm:
            rss_fetcher._log_game_body_template_applied(
                logger,
                post_id=321,
                title="巨人阪神戦 田中将大先発でどこを見たいか",
                article_subtype="lineup",
                section_count=4,
                numeric_count=3,
                name_count=2,
            )
        payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(payload["event"], "game_body_template_applied")
        self.assertEqual(payload["subtype"], "lineup")
        self.assertEqual(payload["section_count"], 4)
        self.assertEqual(payload["numeric_count"], 3)
        self.assertEqual(payload["name_count"], 2)
        self.assertEqual(payload["template_version"], rss_fetcher.GAME_BODY_TEMPLATE_VERSION)


if __name__ == "__main__":
    unittest.main()
