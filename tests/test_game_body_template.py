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

    def test_game_body_template_v2_demotes_auxiliary_heading(self):
        cases = [
            (
                "lineup",
                "【巨人】今日のスタメン発表　1番丸、4番岡田",
                "巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。予告先発は田中将大投手。",
                "【先発投手】",
            ),
            (
                "postgame",
                "【巨人】阪神に3-2で勝利　岡田が決勝打",
                "巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
                "【選手成績】",
            ),
        ]
        for subtype, title, summary, demoted_heading in cases:
            with self.subTest(subtype=subtype):
                with patch.dict("os.environ", {"ENABLE_BODY_TEMPLATE_V2": "1"}, clear=False):
                    with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                        with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[]):
                            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                                blocks, ai_body = rss_fetcher.build_news_block(
                                    title=title,
                                    summary=summary,
                                    url="https://example.com/post",
                                    source_name="スポーツ報知",
                                    category="試合速報",
                                    has_game=True,
                                )

                self.assertIn(demoted_heading, ai_body)
                self.assertIn(f"<h4>{demoted_heading}</h4>", blocks)
                self.assertLessEqual(blocks.count("<h3>"), 2)

    def test_postgame_safe_fallback_avoids_repeating_stat_fact_in_flow(self):
        ai_body = rss_fetcher._build_game_safe_fallback(
            "【巨人】阪神に3-2で勝利　岡田が決勝打",
            "巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。田中将大投手は7回2失点だった。",
            "postgame",
        )

        self.assertIn("【試合結果】", ai_body)
        self.assertIn("【ハイライト】", ai_body)
        self.assertIn("【選手成績】", ai_body)
        self.assertIn("【試合展開】", ai_body)
        self.assertEqual(ai_body.count("田中将大投手は7回2失点だった。"), 1)
        self.assertIn("3-2で決まるまで、どこで流れが動いたかを見ておきたい試合でした。", ai_body)

    def test_pregame_safe_fallback_surfaces_starter_when_summary_is_thin(self):
        ai_body = rss_fetcher._build_game_safe_fallback(
            "【巨人】雨天中止で先発予定だった田中将大は16日にスライド登板",
            "先発予定だった15日の阪神戦（甲子園）が雨天中止となり、16日の同戦にスライドすることになった。",
            "pregame",
        )

        self.assertIn("【変更情報の要旨】", ai_body)
        self.assertIn("【具体的な変更内容】", ai_body)
        self.assertIn("予告先発は田中将大です。", ai_body)
        self.assertNotIn("元記事にある日程や先発情報を、そのまま押さえておきたい変更です。", ai_body)

    def test_lineup_safe_fallback_dedupes_starter_line(self):
        ai_body = rss_fetcher._build_game_safe_fallback(
            "【巨人】今日のスタメン発表　1番丸、4番岡田",
            "巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。予告先発は田中将大投手。",
            "lineup",
        )

        self.assertIn("【先発投手】", ai_body)
        self.assertIn("予告先発は田中将大です。", ai_body)
        self.assertEqual(ai_body.count("予告先発は"), 1)
        self.assertNotIn("予告先発は田中将大投手。", ai_body)

    def test_live_update_safe_fallback_uses_live_update_headings(self):
        ai_body = rss_fetcher._build_game_safe_fallback(
            "【巨人】7回終了で2-2の同点",
            "巨人と阪神は7回終了で2-2の同点。浅野翔吾が適時打を放った。",
            "live_update",
        )

        self.assertIn("【いま起きていること】", ai_body)
        self.assertIn("【流れが動いた場面】", ai_body)
        self.assertIn("【次にどこを見るか】", ai_body)
        self.assertNotIn("【変更情報の要旨】", ai_body)
        self.assertNotIn("【具体的な変更内容】", ai_body)
        self.assertNotIn("【この変更が意味すること】", ai_body)


if __name__ == "__main__":
    unittest.main()
