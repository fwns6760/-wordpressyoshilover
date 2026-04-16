import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class NoticeBodyTemplateTests(unittest.TestCase):
    def test_notice_body_fixture_uses_required_sections(self):
        with open(FIXTURE_DIR / "notice_body_template_golden.json", encoding="utf-8") as f:
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

                self.assertEqual(rss_fetcher._notice_section_count(ai_body), 4)
                self.assertTrue(rss_fetcher._notice_body_has_required_structure(ai_body))
                self.assertTrue(rss_fetcher._notice_has_player_name(ai_body, case["title"], case["summary"]))
                self.assertEqual(rss_fetcher._notice_has_numeric_record(ai_body), case["expect_numeric"])
                self.assertIn('<h2>【公示の要旨】</h2>', blocks)
                self.assertIn('<h3>【対象選手の基本情報】</h3>', blocks)
                self.assertIn('<h3>【公示の背景】</h3>', blocks)
                self.assertIn('<h3>【今後の注目点】</h3>', blocks)
                for required in case["required_strings"]:
                    self.assertIn(required, ai_body)

                notice_type = rss_fetcher._extract_notice_subject_and_type(case["title"], case["summary"])[1]
                self.assertEqual(notice_type or rss_fetcher._extract_notice_type_label(f"{case['title']} {case['summary']}"), case["expected_notice_type"])

    def test_notice_generic_ai_output_is_replaced_with_notice_template(self):
        generic_ai_body = "\n".join(
            [
                "【ニュースの整理】",
                "皆川岳飛が出場選手登録された。",
                "【次の注目】",
                "今後の起用に注目です。",
            ]
        )
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=generic_ai_body):
                _, ai_body = rss_fetcher.build_news_block(
                    title="【巨人】皆川岳飛が出場選手登録",
                    summary="皆川岳飛外野手が4月16日に出場選手登録された。今季二軍で打率.261、2本塁打を記録している。",
                    url="https://example.com/post",
                    source_name="スポニチ 巨人",
                    category="選手情報",
                    has_game=False,
                    source_day_label="4月16日",
                )

        self.assertIn("【公示の要旨】", ai_body)
        self.assertIn("【対象選手の基本情報】", ai_body)
        self.assertIn("【公示の背景】", ai_body)
        self.assertIn("【今後の注目点】", ai_body)
        self.assertNotIn("【ニュースの整理】", ai_body)

    def test_notice_body_template_applied_log_payload(self):
        logger = logging.getLogger("rss_fetcher")
        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_notice_body_template_applied(
                logger,
                post_id=62396,
                title="皆川岳飛、一軍登録でどこを見たいか",
                notice_type="一軍登録",
                section_count=4,
                has_player_name=True,
                has_numeric_record=False,
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "notice_body_template_applied")
        self.assertEqual(payload["post_id"], 62396)
        self.assertEqual(payload["notice_type"], "一軍登録")
        self.assertEqual(payload["section_count"], 4)
        self.assertTrue(payload["has_player_name"])
        self.assertFalse(payload["has_numeric_record"])
        self.assertEqual(payload["template_version"], rss_fetcher.NOTICE_BODY_TEMPLATE_VERSION)

    def test_notice_title_rewrite_prefers_giants_player_name_from_public_notice(self):
        title = "◇セ・リーグ公示（１６日） 【出場選手登録】 ＤｅＮＡ・Ｊ．デュプランティエ投手（ＮＰＢ感染症特例から復帰） 巨人・皆川岳飛外野手 【同抹消】 ＤｅＮＡ・..."

        rewritten = rss_fetcher.rewrite_display_title(title, "", "選手情報", False)

        self.assertEqual(rewritten, "皆川岳飛、一軍登録でどこを見たいか")

    def test_notice_position_prefers_giants_subject_over_other_team_player(self):
        title = "◇セ・リーグ公示（１６日） 【出場選手登録】 ＤｅＮＡ・Ｊ．デュプランティエ投手（ＮＰＢ感染症特例から復帰） 巨人・皆川岳飛外野手 【同抹消】 ＤｅＮＡ・..."

        position = rss_fetcher._extract_notice_player_position(title, "")

        self.assertEqual(position, "外野手")

    def test_notice_without_valid_images_uses_fallback_image(self):
        title = "【巨人】皆川岳飛が出場選手登録"
        summary = "皆川岳飛外野手が4月16日に出場選手登録された。"

        images = rss_fetcher._ensure_notice_featured_images([], title, summary, "選手情報")

        self.assertEqual(images, [rss_fetcher.get_notice_fallback_image_url()])


if __name__ == "__main__":
    unittest.main()
