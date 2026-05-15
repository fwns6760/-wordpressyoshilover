"""Unit tests for src/giants_news_banner.py.

Verifies:
- byte-for-byte equivalence with the prior rss_fetcher.py:17557-17568 inline
  emission so refactor introduces NO HTML diff for build_news_block path
- HTML escape on title / source label
- category → kicker mapping
- empty source fallback
"""

from __future__ import annotations

import unittest

from src.giants_news_banner import giants_news_banner_html, summary_kicker


def _legacy_emit(safe_title: str, safe_source: str, kicker: str) -> str:
    """Reproduces the exact pre-refactor inline f-string concat at
    rss_fetcher.py:17558-17568. Inputs are already HTML-escaped because
    that is how the legacy site prepared them before interpolation.
    """
    return (
        f'<!-- wp:html -->\n'
        f'<div style="background:linear-gradient(135deg,#001e62 0%,#e8272a 100%);border-radius:10px;padding:18px 20px;margin:0 0 4px 0;">'
          f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            f'<span style="background:rgba(255,255,255,0.2);color:#fff;font-size:0.78em;font-weight:800;padding:4px 10px;border-radius:20px;letter-spacing:0.05em;">📰 {safe_source}</span>'
            f'<span style="color:rgba(255,255,255,0.82);font-size:0.72em;font-weight:700;letter-spacing:0.08em;">⚾ {kicker}</span>'
          f'</div>'
          f'<div style="color:#fff;font-size:1.1em;font-weight:900;line-height:1.4;">{safe_title}</div>'
        f'</div>\n'
        f'<!-- /wp:html -->\n\n'
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class TestSummaryKicker(unittest.TestCase):
    def test_known_categories(self):
        cases = {
            "試合速報": "GIANTS GAME NOTE",
            "選手情報": "GIANTS PLAYER WATCH",
            "首脳陣": "GIANTS MANAGER NOTE",
            "補強・移籍": "GIANTS ROSTER WATCH",
            "球団情報": "GIANTS FRONT NOTE",
            "ドラフト・育成": "GIANTS FARM WATCH",
            "OB・解説者": "GIANTS VOICE CHECK",
        }
        for category, kicker in cases.items():
            self.assertEqual(summary_kicker(category), kicker)

    def test_unknown_category_falls_back(self):
        self.assertEqual(summary_kicker("コラム"), "GIANTS NEWS DIGEST")
        self.assertEqual(summary_kicker(""), "GIANTS NEWS DIGEST")
        self.assertEqual(summary_kicker("未知カテゴリ"), "GIANTS NEWS DIGEST")


class TestBannerByteForByteWithLegacy(unittest.TestCase):
    """The helper output MUST equal the pre-refactor inline emission so
    all currently-published banners look identical after the refactor.
    Any HTML diff here means every post on the site would visibly change.
    """

    def _assert_equal(self, title: str, source_label: str, category: str) -> None:
        kicker = summary_kicker(category)
        legacy = _legacy_emit(_escape(title), _escape(source_label) if source_label else "スポーツニュース", kicker)
        new = giants_news_banner_html(title, source_label, category)
        self.assertEqual(new, legacy, f"mismatch for category={category!r}")

    def test_player_info(self):
        self._assert_equal("阿部監督「投げきって勝つのが一番良い」", "スポーツ報知", "首脳陣")

    def test_postgame(self):
        self._assert_equal("巨人ーDeNA戦", "報知新聞 / スポーツ報知巨人班X", "試合速報")

    def test_unknown_category_fallback(self):
        self._assert_equal("テスト記事", "ヨシラバー巨人ラボ", "コラム")

    def test_empty_source_fallback(self):
        self._assert_equal("テスト記事", "", "選手情報")


class TestBannerHtmlEscaping(unittest.TestCase):
    def test_title_special_chars_escaped(self):
        html = giants_news_banner_html(
            '<script>alert("x")</script>&amp;', "src", "選手情報"
        )
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;amp;", html)  # already-escaped & gets re-escaped

    def test_source_label_special_chars_escaped(self):
        html = giants_news_banner_html("title", "<b>&", "選手情報")
        self.assertIn("&lt;b&gt;&amp;", html)

    def test_empty_source_uses_default(self):
        html = giants_news_banner_html("title", "", "選手情報")
        self.assertIn("📰 スポーツニュース", html)

    def test_kicker_emitted_for_each_category(self):
        html = giants_news_banner_html("t", "s", "試合速報")
        self.assertIn("⚾ GIANTS GAME NOTE", html)


class TestBannerStructure(unittest.TestCase):
    def test_contains_gradient_marker(self):
        html = giants_news_banner_html("t", "s", "選手情報")
        self.assertIn("linear-gradient(135deg,#001e62", html)

    def test_starts_with_wp_html_marker(self):
        html = giants_news_banner_html("t", "s", "選手情報")
        self.assertTrue(html.startswith("<!-- wp:html -->\n"))

    def test_ends_with_wp_html_close(self):
        html = giants_news_banner_html("t", "s", "選手情報")
        self.assertTrue(html.endswith("<!-- /wp:html -->\n\n"))


if __name__ == "__main__":
    unittest.main()
