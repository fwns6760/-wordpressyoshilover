import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class ManagerBodyTemplateTests(unittest.TestCase):
    def test_manager_body_fixture_uses_required_sections(self):
        with open(FIXTURE_DIR / "manager_body_template_golden.json", encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                        blocks, ai_body = rss_fetcher.build_news_block(
                            title=case["title"],
                            summary=case["summary"],
                            url="https://example.com/post",
                            source_name="報知 巨人",
                            category="首脳陣",
                            has_game=False,
                        )

                self.assertEqual(rss_fetcher._manager_section_count(ai_body), 4)
                self.assertIn("【発言の要旨】", ai_body)
                self.assertIn("【発言内容】", ai_body)
                self.assertIn("【文脈と背景】", ai_body)
                self.assertIn("【次の注目】", ai_body)
                self.assertIn('<h2>【発言の要旨】</h2>', blocks)
                self.assertIn('<h3>【発言内容】</h3>', blocks)
                self.assertIn('<h3>【文脈と背景】</h3>', blocks)
                self.assertIn('<h3>【次の注目】</h3>', blocks)
                self.assertEqual(
                    rss_fetcher._manager_quote_count(case["title"], case["summary"]),
                    case["expected_quote_count"],
                )
                for required in case["required_strings"]:
                    self.assertIn(required, ai_body)

    def test_manager_generic_ai_output_is_replaced_with_manager_template(self):
        generic_ai_body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が起用方針について語った。",
                "【コメントのポイント】",
                "次の起用にも注目したい。",
            ]
        )
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=generic_ai_body):
                _, ai_body = rss_fetcher.build_news_block(
                    title="【巨人】阿部監督が起用方針を説明",
                    summary="阿部監督がスタメン起用の意図について説明した。今後の起用方針にも触れた。",
                    url="https://example.com/post",
                    source_name="報知 巨人",
                    category="首脳陣",
                    has_game=False,
                )

        self.assertEqual(rss_fetcher._manager_section_count(ai_body), 4)
        self.assertNotIn("【ニュースの整理】", ai_body)
        self.assertIn("【発言の要旨】", ai_body)
        self.assertIn("【発言内容】", ai_body)

    def test_manager_body_template_applied_log_payload(self):
        logger = logging.getLogger("rss_fetcher")
        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_manager_body_template_applied(
                logger,
                post_id=321,
                title="阿部監督「結果残せば使います」 ベンチの狙いはどこか",
                quote_count=1,
                section_count=4,
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "manager_body_template_applied")
        self.assertEqual(payload["post_id"], 321)
        self.assertEqual(payload["quote_count"], 1)
        self.assertEqual(payload["section_count"], 4)
        self.assertEqual(payload["template_version"], rss_fetcher.MANAGER_BODY_TEMPLATE_VERSION)


if __name__ == "__main__":
    unittest.main()
