"""Regression tests for source body excerpt block in the auto RSS path.

These guard the gap that 2026-05-12_source-body-excerpt-auto-rss-permanent-fix
closes: ``_maybe_insert_source_body_excerpt`` is the manual_intake helper that
inserts the ``<aside class="nomotoke-source-excerpt">`` block. Before this fix
the auto RSS path (``_create_draft_with_same_fire_guard``) never invoked it, so
hochi/nikkan/sponichi/daily automatic drafts shipped without any source body
excerpt. After the fix the same helper runs inside the auto path under a
narrow gate (raw_html available, source_type in {"news", "tag_scrape"}, no
existing excerpt block in the rendered HTML).
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src import rss_fetcher


_HOCHI_PAGE_HTML = """
<html><head>
<meta property="og:image" content="https://hochi.news/images/foo.jpg">
</head><body>
<article>
<p>巨人・岡本和真が１２日の練習で気合の入った打撃を披露した。</p>
<p>岡本は試合前のフリー打撃でスタンドへ運ぶ豪快なスイングを連発。</p>
<p>「いい感覚がある。明日も同じ準備をしたい」と笑顔で振り返った。</p>
<p>このオフの自主トレで磨いた下半身の使い方が安定した打撃を支えている。</p>
<p>チームは岐阜での広島戦を控え、岡本の状態の良さが４番として頼もしい。</p>
</article>
</body></html>
""".strip()


class AutoRssSourceBodyExcerptInsertTests(unittest.TestCase):
    @patch("src.rss_fetcher.WPClient")
    def test_news_path_inserts_source_body_excerpt_block(self, _wp_cls):
        wp = _wp_cls.return_value
        wp.create_post.return_value = 9100

        rendered_body_html = (
            '<div class="article-body">'
            '<h2>岡本和真</h2><p>本文の AI 生成テキスト。</p>'
            '</div>'
        )

        post_id = rss_fetcher._create_draft_with_same_fire_guard(
            wp,
            __import__("logging").getLogger("rss_fetcher.test"),
            set(),
            {},
            "【巨人】岡本和真がフリー打撃でスタンドへ豪快弾",
            rendered_body_html,
            [663],
            "https://hochi.news/articles/test-okamoto.html",
            featured_media=None,
            enrichment_summary="岡本和真がフリー打撃で快音を響かせた。",
            enrichment_category="選手情報",
            enrichment_template_key="",
            enrichment_source_name="報知新聞",
            enrichment_raw_html=_HOCHI_PAGE_HTML,
            enrichment_source_type="news",
        )

        self.assertEqual(post_id, 9100)
        sent_content = wp.create_post.call_args.args[1]
        self.assertIn("nomotoke-source-excerpt", sent_content)
        # 元の本文も保持されていること
        self.assertIn("本文の AI 生成テキスト。", sent_content)

    @patch("src.rss_fetcher.WPClient")
    def test_news_path_idempotent_when_excerpt_already_present(self, _wp_cls):
        wp = _wp_cls.return_value
        wp.create_post.return_value = 9101

        body_with_excerpt = (
            '<div class="article-body">'
            '<p>本文</p>'
            '<aside class="nomotoke-source-excerpt">既存</aside>'
            '</div>'
        )

        rss_fetcher._create_draft_with_same_fire_guard(
            wp,
            __import__("logging").getLogger("rss_fetcher.test"),
            set(),
            {},
            "【巨人】岡本和真がフリー打撃でスタンドへ豪快弾",
            body_with_excerpt,
            [663],
            "https://hochi.news/articles/test-idempotent.html",
            featured_media=None,
            enrichment_summary="",
            enrichment_category="選手情報",
            enrichment_template_key="",
            enrichment_source_name="報知新聞",
            enrichment_raw_html=_HOCHI_PAGE_HTML,
            enrichment_source_type="news",
        )

        sent_content = wp.create_post.call_args.args[1]
        # 既存 aside が 1 つだけで、二重挿入されていないこと
        self.assertEqual(sent_content.count('class="nomotoke-source-excerpt"'), 1)

    @patch("src.rss_fetcher.WPClient")
    def test_social_news_path_skips_excerpt_insertion(self, _wp_cls):
        wp = _wp_cls.return_value
        wp.create_post.return_value = 9102

        rss_fetcher._create_draft_with_same_fire_guard(
            wp,
            __import__("logging").getLogger("rss_fetcher.test"),
            set(),
            {},
            "話題「メジャーのキャッチャーみたいなミットの音がする」",
            '<div class="article-body"><p>X tweet 由来の本文。</p></div>',
            [663],
            "https://x.com/foo/status/1",
            featured_media=None,
            enrichment_summary="",
            enrichment_category="選手情報",
            enrichment_template_key="",
            enrichment_source_name="X",
            enrichment_raw_html=_HOCHI_PAGE_HTML,
            enrichment_source_type="social_news",
        )

        sent_content = wp.create_post.call_args.args[1]
        self.assertNotIn("nomotoke-source-excerpt", sent_content)

    @patch("src.rss_fetcher.WPClient")
    def test_empty_raw_html_skips_excerpt_insertion(self, _wp_cls):
        wp = _wp_cls.return_value
        wp.create_post.return_value = 9103

        rss_fetcher._create_draft_with_same_fire_guard(
            wp,
            __import__("logging").getLogger("rss_fetcher.test"),
            set(),
            {},
            "【巨人】岡本和真がフリー打撃でスタンドへ豪快弾",
            '<div class="article-body"><p>本文。</p></div>',
            [663],
            "https://hochi.news/articles/test-no-html.html",
            featured_media=None,
            enrichment_summary="",
            enrichment_category="選手情報",
            enrichment_template_key="",
            enrichment_source_name="報知新聞",
            enrichment_raw_html="",
            enrichment_source_type="news",
        )

        sent_content = wp.create_post.call_args.args[1]
        self.assertNotIn("nomotoke-source-excerpt", sent_content)

    @patch("src.rss_fetcher.WPClient")
    def test_context_drift_excerpt_is_rejected(self, _wp_cls):
        """guard が title に一致しない excerpt を弾くこと。"""
        wp = _wp_cls.return_value
        wp.create_post.return_value = 9104

        polluted_html = """
<html><head>
<meta property="og:image" content="https://hochi.news/images/foo.jpg">
</head><body>
<article>
<p>中日の高橋宏斗が完投勝利を挙げた。中日ファンが盛り上がっている。</p>
<p>高橋は７回まで無失点の好投を見せ、中日ファンの期待に応えた。</p>
</article>
</body></html>
""".strip()

        rss_fetcher._create_draft_with_same_fire_guard(
            wp,
            __import__("logging").getLogger("rss_fetcher.test"),
            set(),
            {},
            "【巨人】岡本和真がフリー打撃でスタンドへ豪快弾",
            '<div class="article-body"><p>本文。</p></div>',
            [663],
            "https://hochi.news/articles/test-drift.html",
            featured_media=None,
            enrichment_summary="岡本和真がフリー打撃で快音を響かせた。",
            enrichment_category="選手情報",
            enrichment_template_key="",
            enrichment_source_name="報知新聞",
            enrichment_raw_html=polluted_html,
            enrichment_source_type="news",
        )

        sent_content = wp.create_post.call_args.args[1]
        self.assertNotIn("nomotoke-source-excerpt", sent_content)


if __name__ == "__main__":
    unittest.main()
