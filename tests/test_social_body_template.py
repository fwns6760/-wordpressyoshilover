import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class SocialBodyTemplateTests(unittest.TestCase):
    def test_social_body_fixture_uses_required_sections(self):
        with open(FIXTURE_DIR / "social_body_template_golden.json", encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                        blocks, ai_body = rss_fetcher.build_news_block(
                            title=case["title"],
                            summary=case["summary"],
                            url="https://twitter.com/example/status/1",
                            source_name=case["source_name"],
                            category=case["category"],
                            has_game=False,
                            source_type="social_news",
                        )

                self.assertEqual(rss_fetcher._social_section_count(ai_body), 4)
                self.assertTrue(rss_fetcher._social_body_has_required_structure(ai_body))
                self.assertIn("<h2>【話題の要旨】</h2>", blocks)
                self.assertIn("<h3>【発信内容の要約】</h3>", blocks)
                self.assertIn("<h3>【文脈と背景】</h3>", blocks)
                self.assertIn("<h3>【ファンの関心ポイント】</h3>", blocks)
                for required in case["required_strings"]:
                    self.assertIn(required, ai_body)
                self.assertEqual(
                    rss_fetcher._infer_social_source_indicator(case["source_name"], "https://twitter.com/example/status/1"),
                    case["expected_indicator"],
                )

    def test_social_news_overrides_category_specific_headings(self):
        generic_social_body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督の発言がXで話題になった。",
                "【次の注目】",
                "次の起用も見たい。",
            ]
        )
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=generic_social_body):
                _, ai_body = rss_fetcher.build_news_block(
                    title="阿部監督が起用方針を説明",
                    summary="スポーツ報知巨人班Xが阿部監督の起用方針を伝えた。",
                    url="https://twitter.com/hochi_giants/status/1",
                    source_name="スポーツ報知巨人班X",
                    category="首脳陣",
                    has_game=False,
                    source_type="social_news",
                )

        self.assertIn("【話題の要旨】", ai_body)
        self.assertIn("【発信内容の要約】", ai_body)
        self.assertIn("【文脈と背景】", ai_body)
        self.assertIn("【ファンの関心ポイント】", ai_body)
        self.assertNotIn("【発言の要旨】", ai_body)
        self.assertNotIn("【ニュースの整理】", ai_body)

    def test_social_body_template_applied_log_payload(self):
        logger = logging.getLogger("rss_fetcher")
        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_social_body_template_applied(
                logger,
                post_id=62510,
                title="阿部監督のX発言をどう見るか",
                final_category="首脳陣",
                source_type_indicator="media",
                section_count=4,
                quote_count=2,
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "social_body_template_applied")
        self.assertEqual(payload["post_id"], 62510)
        self.assertEqual(payload["final_category"], "首脳陣")
        self.assertEqual(payload["source_type_indicator"], "media")
        self.assertEqual(payload["section_count"], 4)
        self.assertEqual(payload["quote_count"], 2)
        self.assertEqual(payload["template_version"], rss_fetcher.SOCIAL_BODY_TEMPLATE_VERSION)

    def test_social_safe_fallback_avoids_publish_quality_leak_markers(self):
        body = rss_fetcher._build_social_safe_fallback(
            title="阿部監督が起用方針を説明",
            summary="スポーツ報知巨人班Xが阿部監督の起用方針を伝えた。",
            category="首脳陣",
            source_name="スポーツ報知巨人班X",
            tweet_url="https://twitter.com/hochi_giants/status/1",
            source_day_label="4月19日",
            real_reactions=[],
        )

        for marker in rss_fetcher.PUBLISH_QUALITY_LEAK_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, body)


if __name__ == "__main__":
    unittest.main()
