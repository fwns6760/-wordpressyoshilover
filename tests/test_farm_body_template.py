import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class FarmBodyTemplateTests(unittest.TestCase):
    def test_farm_body_fixture_uses_required_sections(self):
        with open(FIXTURE_DIR / "farm_body_template_golden.json", encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                        blocks, ai_body = rss_fetcher.build_news_block(
                            title=case["title"],
                            summary=case["summary"],
                            url="https://example.com/post",
                            source_name="巨人公式X",
                            category="ドラフト・育成",
                            has_game=True,
                        )

                required_headings = rss_fetcher._farm_required_headings(case["subtype"])
                self.assertEqual(rss_fetcher._farm_section_count(ai_body, case["subtype"]), len(required_headings))
                self.assertTrue(rss_fetcher._farm_body_has_required_structure(ai_body, case["subtype"]))
                self.assertIn(f"<h2>{required_headings[0]}</h2>", blocks)
                for heading in required_headings[1:]:
                    self.assertIn(f"<h3>{heading}</h3>", blocks)
                for expected in case["required_strings"]:
                    self.assertIn(expected, ai_body)
                self.assertEqual(
                    rss_fetcher._farm_is_drafted_player_story(case["title"], case["summary"]),
                    case["expected_is_drafted_player"],
                )

    def test_farm_generic_ai_output_is_replaced_with_template(self):
        generic_ai_body = "\n".join(
            [
                "【ニュースの整理】",
                "巨人二軍が4-1で勝利した。",
                "【次の注目】",
                "若手の内容を次も見たい。",
            ]
        )

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=generic_ai_body):
                _, ai_body = rss_fetcher.build_news_block(
                    title="【二軍】巨人 4-1 ロッテ　ティマが2安打3打点",
                    summary="巨人二軍がロッテとの二軍戦に4-1で勝利した。ティマが2安打3打点を記録した。",
                    url="https://example.com/post",
                    source_name="巨人公式X",
                    category="ドラフト・育成",
                    has_game=True,
                )

        self.assertIn("【二軍結果・活躍の要旨】", ai_body)
        self.assertIn("【ファームのハイライト】", ai_body)
        self.assertIn("【二軍個別選手成績】", ai_body)
        self.assertIn("【一軍への示唆】", ai_body)
        self.assertNotIn("【ニュースの整理】", ai_body)

    def test_farm_lineup_does_not_fall_back_to_first_team_headings(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                _, ai_body = rss_fetcher.build_news_block(
                    title="【二軍】巨人 vs DeNA 18:00試合開始　1番浅野、4番ティマでスタメン",
                    summary="巨人二軍がDeNA戦のスタメンを発表した。1番浅野翔吾、4番ティマ、先発は西舘勇陽投手。",
                    url="https://example.com/post",
                    source_name="巨人公式X",
                    category="ドラフト・育成",
                    has_game=True,
                )

        self.assertIn("【二軍試合概要】", ai_body)
        self.assertIn("【二軍スタメン一覧】", ai_body)
        self.assertIn("【注目選手】", ai_body)
        self.assertNotIn("【試合概要】", ai_body)
        self.assertNotIn("【先発投手】", ai_body)

    def test_farm_body_template_applied_log_payload(self):
        logger = logging.getLogger("rss_fetcher")
        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_farm_body_template_applied(
                logger,
                post_id=62421,
                title="巨人二軍 1-1 結果のポイント",
                article_subtype="farm",
                section_count=4,
                numeric_count=3,
                is_drafted_player=False,
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "farm_body_template_applied")
        self.assertEqual(payload["post_id"], 62421)
        self.assertEqual(payload["subtype"], "farm")
        self.assertEqual(payload["section_count"], 4)
        self.assertEqual(payload["numeric_count"], 3)
        self.assertFalse(payload["is_drafted_player"])
        self.assertEqual(payload["template_version"], rss_fetcher.FARM_BODY_TEMPLATE_VERSION)


if __name__ == "__main__":
    unittest.main()
