import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class RecoveryBodyTemplateTests(unittest.TestCase):
    def test_recovery_body_fixture_uses_required_sections(self):
        with open(FIXTURE_DIR / "recovery_body_template_golden.json", encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                        blocks, ai_body = rss_fetcher.build_news_block(
                            title=case["title"],
                            summary=case["summary"],
                            url="https://example.com/post",
                            source_name="スポニチ 巨人",
                            category="選手情報",
                            has_game=False,
                            source_day_label=case.get("source_day_label", ""),
                        )

                self.assertEqual(rss_fetcher._recovery_section_count(ai_body), 4)
                self.assertTrue(rss_fetcher._recovery_body_has_required_structure(ai_body))
                self.assertIn('<h2>【故障・復帰の要旨】</h2>', blocks)
                self.assertIn('<h3>【故障の詳細】</h3>', blocks)
                self.assertIn('<h3>【リハビリ状況・復帰見通し】</h3>', blocks)
                self.assertIn('<h3>【チームへの影響と今後の注目点】</h3>', blocks)
                for required in case["required_strings"]:
                    self.assertIn(required, ai_body)

                injury_part = rss_fetcher._extract_recovery_injury_part(case["title"], case["summary"])
                return_timing = rss_fetcher._extract_recovery_return_timing(case["title"], case["summary"])
                if case["expected_injury_part"]:
                    self.assertIn(case["expected_injury_part"], injury_part)
                if case["expected_return_timing"]:
                    self.assertIn(case["expected_return_timing"], return_timing)

    def test_recovery_generic_ai_output_is_replaced_with_recovery_template(self):
        generic_ai_body = "\n".join(
            [
                "【ニュースの整理】",
                "山崎伊織が復帰へ前進した。",
                "【次の注目】",
                "今後の状態に注目です。",
            ]
        )
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=generic_ai_body):
                _, ai_body = rss_fetcher.build_news_block(
                    title="【巨人】山崎伊織が復帰へ前進",
                    summary="山崎伊織投手が故障離脱からの復帰へ前進した。ブルペンで投球練習を再開した。",
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="選手情報",
                    has_game=False,
                    source_day_label="4月15日",
                )

        self.assertIn("【故障・復帰の要旨】", ai_body)
        self.assertIn("【故障の詳細】", ai_body)
        self.assertIn("【リハビリ状況・復帰見通し】", ai_body)
        self.assertIn("【チームへの影響と今後の注目点】", ai_body)
        self.assertNotIn("【ニュースの整理】", ai_body)

    def test_recovery_body_template_applied_log_payload(self):
        logger = logging.getLogger("rss_fetcher")
        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_recovery_body_template_applied(
                logger,
                post_id=63000,
                title="山崎伊織、復帰へ前進",
                injury_part="右肩",
                return_timing="今月中の実戦復帰を目指す",
                section_count=4,
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "recovery_body_template_applied")
        self.assertEqual(payload["post_id"], 63000)
        self.assertEqual(payload["injury_part"], "右肩")
        self.assertEqual(payload["return_timing"], "今月中の実戦復帰を目指す")
        self.assertEqual(payload["section_count"], 4)
        self.assertEqual(payload["template_version"], rss_fetcher.RECOVERY_BODY_TEMPLATE_VERSION)

    def test_recovery_has_priority_over_notice_for_injury_return_story(self):
        title = "【巨人】西舘勇陽がコンディション不良からの復帰へ向けてブルペン投球再開"
        summary = "西舘勇陽投手がコンディション不良からの復帰へ向けてブルペンで投球練習を再開した。"

        self.assertEqual(rss_fetcher._detect_player_special_template_kind(title, summary), "player_recovery")
        self.assertTrue(rss_fetcher._is_recovery_template_story(title, summary, "選手情報"))
        self.assertFalse(rss_fetcher._is_notice_template_story(title, summary, "選手情報"))

    def test_public_notice_keeps_notice_priority(self):
        title = "◇セ・リーグ公示（１６日） 【出場選手登録】 ＤｅＮＡ・Ｊ．デュプランティエ投手（ＮＰＢ感染症特例から復帰） 巨人・皆川岳飛外野手 【同抹消】 ＤｅＮＡ・..."
        summary = "皆川岳飛外野手が4月16日に出場選手登録された。今季二軍で打率.261、2本塁打を記録している。"

        self.assertEqual(rss_fetcher._detect_player_special_template_kind(title, summary), "player_notice")
        self.assertFalse(rss_fetcher._is_recovery_template_story(title, summary, "選手情報"))
        self.assertTrue(rss_fetcher._is_notice_template_story(title, summary, "選手情報"))


if __name__ == "__main__":
    unittest.main()
