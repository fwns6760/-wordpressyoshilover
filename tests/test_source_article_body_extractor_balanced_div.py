"""Tests for _extract_balanced_div_inner + sanspo integration (#16 / 337-INGEST Phase 3)."""

from __future__ import annotations

import re
import unittest

from src.source_article_body_extractor import (
    _extract_balanced_div_inner,
    _extract_via_site_selectors,
    extract_article_body_excerpt,
)


_SANSPO_OPEN_RE = re.compile(
    r'<div[^>]+class="[^"]*\barticle-body\b[^"]*"[^>]*>',
    re.IGNORECASE,
)


class ExtractBalancedDivInnerTests(unittest.TestCase):
    def test_simple_one_level_div_returns_inner(self):
        html = '<html><body><div class="article-body"><p>本文テキスト</p></div></body></html>'
        result = _extract_balanced_div_inner(html, _SANSPO_OPEN_RE)
        self.assertIn("<p>本文テキスト</p>", result)

    def test_nested_div_balances_correctly(self):
        html = (
            '<div class="article-body">'
            '<figure><div class="image-wrap"><img src="x.jpg"/></div></figure>'
            '<p>巨人・坂本が逆転サヨナラ３ラン。</p>'
            '<div class="related"><div class="inner">関連記事</div></div>'
            '<p>「一生忘れない」</p>'
            '</div>'
        )
        result = _extract_balanced_div_inner(html, _SANSPO_OPEN_RE)
        self.assertIn("巨人・坂本が逆転サヨナラ３ラン", result)
        self.assertIn("一生忘れない", result)
        self.assertIn("関連記事", result)

    def test_no_opening_returns_empty(self):
        html = '<div class="other-body"><p>x</p></div>'
        self.assertEqual(_extract_balanced_div_inner(html, _SANSPO_OPEN_RE), "")

    def test_unbalanced_closing_returns_empty(self):
        html = '<div class="article-body"><p>本文</p>'
        self.assertEqual(_extract_balanced_div_inner(html, _SANSPO_OPEN_RE), "")


class SanspoSiteSelectorIntegrationTests(unittest.TestCase):
    def test_sanspo_nested_html_extracts_via_balanced(self):
        html = (
            '<html><body>'
            '<div class="article-body">'
            '<figure><div><img src="x.jpg"/></div></figure>'
            '<p>巨人・坂本勇人が逆転サヨナラ３ラン。「一生忘れない」と語った。</p>'
            '<div class="ad"><div>関連</div></div>'
            '<p>通算３００号のメモリアル弾。</p>'
            '</div>'
            '</body></html>'
        )
        result = _extract_via_site_selectors(html, "www.sanspo.com")
        self.assertIn("逆転サヨナラ３ラン", result)
        self.assertIn("通算３００号", result)

    def test_sanspo_excerpt_returns_plain_text(self):
        html = (
            '<html><body>'
            '<div class="article-body">'
            '<figure><div><img src="x.jpg"/></div></figure>'
            '<p>巨人・坂本勇人が逆転サヨナラ３ラン。「一生忘れない」と語った。</p>'
            '<p>通算３００号のメモリアル弾で、２試合連続のサヨナラ勝ちとなった。</p>'
            '</div>'
            '</body></html>'
        )
        excerpt = extract_article_body_excerpt(
            html,
            source_url="https://www.sanspo.com/article/20260514-XXXXXX/",
            max_chars=240,
        )
        self.assertIn("逆転サヨナラ", excerpt)
        self.assertNotIn("<p>", excerpt)
        self.assertNotIn("<div", excerpt)

    def test_non_sanspo_unaffected(self):
        html = (
            '<div class="article__body">'
            '<p>巨人・坂本勇人が逆転サヨナラ３ラン。「一生忘れない」と語った。</p>'
            '</div>'
        )
        result = _extract_via_site_selectors(html, "hochi.news")
        self.assertIn("逆転サヨナラ", result)


if __name__ == "__main__":
    unittest.main()
