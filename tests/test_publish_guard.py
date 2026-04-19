import unittest

from src import rss_fetcher


def _content_html(body_text: str) -> str:
    return (
        '<div class="yoshilover-related-posts"><div>【関連記事】</div><ul><li>関連記事</li></ul></div>'
        f"<p>{body_text}</p>"
    )


class PublishQualityGuardTests(unittest.TestCase):
    def test_core_body_text_excludes_related_posts_block(self):
        core_text = rss_fetcher._core_body_text(
            "<p>巨人が競り勝った。</p>"
            '<div class="yoshilover-related-posts"><div>【関連記事】</div><ul><li>関連記事</li></ul></div>'
            "<p>次の起用にも目線が向く。</p>"
        )

        self.assertIn("巨人が競り勝った。", core_text)
        self.assertIn("次の起用にも目線が向く。", core_text)
        self.assertNotIn("【関連記事】", core_text)
        self.assertNotIn("関連記事", core_text)

    def test_publish_quality_guard_rejects_thin_lineup_body(self):
        quality_guard = rss_fetcher._evaluate_publish_quality_guard(
            content_html=_content_html("あ" * 279),
            article_subtype="lineup",
        )

        self.assertFalse(quality_guard["ok"])
        self.assertIn("quality_guard_thin", quality_guard["reasons"])
        self.assertEqual(quality_guard["min_chars"], 280)

    def test_publish_quality_guard_rejects_prompt_leak_marker(self):
        body_text = (
            "巨人が終盤まで粘った。"
            "打席ごとの反応と継投の意図を順に振り返る。"
            * 20
        ) + "試合前後の流れ、スタメン、先発、スコアなど、試合文脈があれば必ず整理する。"

        quality_guard = rss_fetcher._evaluate_publish_quality_guard(
            content_html=_content_html(body_text),
            article_subtype="postgame",
        )

        self.assertFalse(quality_guard["ok"])
        self.assertIn("quality_guard_leak", quality_guard["reasons"])
        self.assertIn("があれば必ず整理する", quality_guard["leak_markers"])

    def test_publish_quality_guard_accepts_long_clean_body(self):
        body_text = "巨人が流れを引き寄せた。打席ごとの変化も整理できる。次の起用にも目線が向く。" * 12

        quality_guard = rss_fetcher._evaluate_publish_quality_guard(
            content_html=_content_html(body_text),
            article_subtype="manager",
        )

        self.assertTrue(quality_guard["ok"])
        self.assertEqual(quality_guard["reasons"], [])
        self.assertEqual(quality_guard["leak_markers"], [])
        self.assertGreaterEqual(quality_guard["core_char_count"], 350)


class ThinSourceFactBlockTests(unittest.TestCase):
    def test_source_fact_block_metrics_detects_thin_source(self):
        source_fact_block, source_fact_block_length = rss_fetcher._source_fact_block_metrics(
            "巨人が勝利",
            "巨人が勝った。",
        )

        self.assertIn("巨人が勝利", source_fact_block)
        self.assertLess(source_fact_block_length, rss_fetcher.THIN_SOURCE_FACT_BLOCK_MIN_CHARS_DEFAULT)

    def test_source_fact_block_metrics_accepts_rich_source(self):
        source_fact_block, source_fact_block_length = rss_fetcher._source_fact_block_metrics(
            "巨人がヤクルトに3-2で勝利 戸郷翔征が7回1失点 岡本和真が勝ち越し打",
            "巨人がヤクルトに3-2で勝利した。戸郷翔征が7回1失点で試合をつくり、岡本和真が八回に勝ち越し打を放った。"
            "大勢が九回を締め、連敗を止めた。",
        )

        self.assertIn("戸郷翔征", source_fact_block)
        self.assertGreaterEqual(source_fact_block_length, rss_fetcher.THIN_SOURCE_FACT_BLOCK_MIN_CHARS_DEFAULT)

    def test_social_news_threshold_allows_length_50(self):
        self.assertEqual(rss_fetcher._thin_source_fact_block_min_chars("social_news"), 50)
        self.assertFalse(rss_fetcher._is_thin_source_fact_block("social_news", 50))

    def test_social_news_threshold_skips_length_49(self):
        threshold = rss_fetcher._thin_source_fact_block_min_chars("social_news")
        self.assertEqual(threshold, 50)
        self.assertTrue(rss_fetcher._is_thin_source_fact_block("social_news", 49))

    def test_default_news_threshold_keeps_99_thin(self):
        threshold = rss_fetcher._thin_source_fact_block_min_chars("news")
        self.assertEqual(threshold, 100)
        self.assertTrue(rss_fetcher._is_thin_source_fact_block("news", 99))


if __name__ == "__main__":
    unittest.main()
