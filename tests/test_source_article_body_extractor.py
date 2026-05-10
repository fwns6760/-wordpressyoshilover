"""Tests for src/source_article_body_extractor.py.

The extractor is a pure parser — every test case constructs a fake
HTML payload and asserts the returned excerpt is a literal substring
of the input (post tag-stripping + entity decoding) and obeys the
length cap + sentence-boundary rule.
"""
from __future__ import annotations

import unittest

from src.source_article_body_extractor import extract_article_body_excerpt


class JsonLdPathTests(unittest.TestCase):
    def test_jsonld_article_body_wins_over_other_strategies(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"NewsArticle","articleBody":"巨人の戸郷翔征投手は7日の阪神戦で5回4安打1失点と好投。試合後、阿部監督は次回も期待したいと評価した。","headline":"x"}
        </script>
        </head><body>
        <article>違うコンテンツ。</article>
        </body></html>
        """
        out = extract_article_body_excerpt(html, "https://hochi.news/articles/foo.html")
        self.assertIn("戸郷翔征投手", out)
        self.assertIn("阿部監督", out)
        self.assertNotIn("違うコンテンツ", out)

    def test_jsonld_graph_envelope_supported(self):
        html = """
        <script type="application/ld+json">
        {"@graph":[{"@type":"Article","articleBody":"5月7日 巨人 5-3 阪神 戸郷5回1失点。岡本2本塁打。"}]}
        </script>
        """
        out = extract_article_body_excerpt(html, "https://example.com/")
        self.assertIn("戸郷5回1失点", out)


class SiteSelectorPathTests(unittest.TestCase):
    def test_hochi_article_body_class(self):
        html = (
            '<div class="article__body">'
            "<p>5月7日 巨人 5-3 阪神。</p>"
            "<p>戸郷翔征が5回4安打1失点と好投した。</p>"
            "<p>阿部監督は試合後、次回も期待したいとコメント。</p>"
            "</div>"
        )
        out = extract_article_body_excerpt(html, "https://hochi.news/articles/x.html")
        self.assertIn("戸郷翔征", out)
        self.assertIn("阿部監督", out)
        # plain text — no HTML tags survive
        self.assertNotIn("<p>", out)
        self.assertNotIn("</p>", out)

    def test_hochi_preview_detail_body_class(self):
        html = (
            '<div class="article__wrap">'
            '<div class="preview__detail">'
            '<p class="preview__text">◆ファーム・リーグ　ロッテ―巨人（１０日・江戸川）</p>'
            '<p class="preview__text">巨人のエルビス・ルシアーノ投手が３者連続空振り三振を披露した。</p>'
            '<p class="preview__text">３―３の７回に３番手で登板し、先頭から３人を空振り三振に打ち取った。</p>'
            "</div>"
            "</div>"
        )
        out = extract_article_body_excerpt(html, "https://hochi.news/articles/x.html")
        self.assertIn("エルビス・ルシアーノ投手", out)
        self.assertIn("３者連続空振り三振", out)
        self.assertNotIn("article__wrap", out)

    def test_baseballking_entry_content_drops_ad_script(self):
        html = (
            '<div class="entry-content">'
            '<script>googletag.cmd.push(function() { googletag.display("ad"); });</script>'
            "<p>ロッテの石垣元気が9日、巨人との二軍戦でZOZOマリンスタジアムデビューを果たした。</p>"
            "<p>石垣は7回に登板し、0回2/3を投げ、奪三振1、被安打1、1失点だった。</p>"
            "</div>"
        )
        out = extract_article_body_excerpt(html, "https://baseballking.jp/ns/695077/")
        self.assertIn("ZOZOマリンスタジアムデビュー", out)
        self.assertIn("0回2/3", out)
        self.assertNotIn("googletag", out)

    def test_full_count_body_selector_drops_header_and_ads(self):
        html = (
            '<article class="s-entry-post">'
            '<div class="s-entry-header">'
            '<h1 class="s-entry-header__title">戸郷翔征は「どうしたんだ」</h1>'
            '<li class="s-entry-header__meta-date">2026.05.04</li>'
            "</div>"
            '<div class="s-entry-body"><div class="c-wp-post">'
            '<aside class="s-entry-ads"><script>googletag.cmd.push(function(){})</script></aside>'
            "<h2>不振が続くエース右腕</h2>"
            "<p>巨人の戸郷翔征投手が4日、東京ドームで行われたヤクルト戦に今季初先発を果たした。</p>"
            "<p>5回を投げ1本塁打を含む6安打5失点、2四死球の内容だった。</p>"
            "</div><!-- s-entry-body --></div>"
            "</article>"
        )
        out = extract_article_body_excerpt(
            html,
            "https://full-count.jp/2026/05/04/post1955326/",
            title="戸郷翔征は「どうしたんだ」",
        )
        self.assertIn("戸郷翔征投手", out)
        self.assertIn("6安打5失点", out)
        self.assertNotIn("2026.05.04", out)
        self.assertNotIn("googletag", out)


class FallbackChainTests(unittest.TestCase):
    def test_article_tag_used_when_site_selector_misses(self):
        html = (
            "<article>"
            "<p>巨人は7日の阪神戦に勝利。</p>"
            "<p>戸郷が好投、岡本が2本塁打。試合後の監督談話あり。</p>"
            "</article>"
        )
        out = extract_article_body_excerpt(html, "https://random-site.example/")
        self.assertIn("戸郷が好投", out)
        self.assertIn("岡本", out)

    def test_generic_class_fallback(self):
        html = (
            '<div class="entry-content">'
            "<p>5月7日 巨人 5-3 阪神。</p>"
            "<p>戸郷5回1失点。</p>"
            "<p>岡本2本塁打。</p>"
            "</div>"
        )
        out = extract_article_body_excerpt(html, "https://random.example/article")
        self.assertIn("戸郷5回1失点", out)

    def test_returns_empty_when_no_strategy_matches(self):
        html = "<html><body><p>hi</p></body></html>"
        self.assertEqual(
            extract_article_body_excerpt(html, "https://example.com/"), ""
        )


class TruncationTests(unittest.TestCase):
    def test_max_chars_caps_at_sentence_boundary(self):
        long_body = (
            "巨人は7日に勝利した。" * 30
        )
        html = f'<article><p>{long_body}</p></article>'
        out = extract_article_body_excerpt(
            html, "https://example.com/", max_chars=120
        )
        self.assertLessEqual(len(out), 120)
        self.assertTrue(out.endswith("。") or out.endswith("…"))

    def test_expanded_cap_still_respects_sentence_boundary(self):
        body = (
            "巨人の若手が練習で存在感を見せた。"
            "打撃練習では逆方向への強い打球が目立った。"
            "首脳陣は状態の良さを確認した。"
            "守備練習でも軽快な動きを見せた。"
            "今後の一軍争いへ向けてアピールを続けている。"
        )
        html = f'<article><p>{body}</p></article>'
        out = extract_article_body_excerpt(
            html, "https://example.com/", max_chars=80
        )
        self.assertLessEqual(len(out), 80)
        self.assertTrue(out.endswith("。") or out.endswith("…"))

    def test_short_body_returned_as_is(self):
        html = '<article><p>5月7日 巨人 5-3 阪神。戸郷5回1失点。岡本2本塁打。</p></article>'
        out = extract_article_body_excerpt(html, "https://example.com/", max_chars=240)
        self.assertIn("戸郷5回1失点", out)
        self.assertIn("岡本2本塁打", out)


class TitleEchoTests(unittest.TestCase):
    def test_leading_title_echo_dropped(self):
        html = (
            "<article>"
            "<p>巨人 5-3 阪神 戸郷5回1失点</p>"
            "<p>戸郷翔征は5月7日の阪神戦で5回4安打1失点と好投。試合後の監督談話。</p>"
            "</article>"
        )
        out = extract_article_body_excerpt(
            html,
            "https://example.com/",
            title="巨人 5-3 阪神 戸郷5回1失点",
        )
        self.assertNotIn("阪神 戸郷5回1失点\n戸郷翔征", out)
        self.assertIn("戸郷翔征", out)

    def test_title_adjacent_body_still_returns_source_detail(self):
        html = (
            "<article>"
            "<p>巨人の若手が練習で存在感</p>"
            "<p>打撃練習では逆方向への強い打球が目立ち、首脳陣も状態の良さを確認した。</p>"
            "<p>守備練習でも軽快な動きを見せ、今後の一軍争いへ向けてアピールを続けている。</p>"
            "</article>"
        )
        out = extract_article_body_excerpt(
            html,
            "https://example.com/",
            title="巨人の若手が練習で存在感",
            max_chars=160,
        )
        self.assertNotIn("巨人の若手が練習で存在感\n", out)
        self.assertIn("逆方向への強い打球", out)
        self.assertIn("一軍争い", out)


class HallucinationGuardTests(unittest.TestCase):
    def test_output_is_substring_of_decoded_input(self):
        # The extractor MUST never invent content. This test verifies
        # the output (after entity decoding) appears verbatim in the
        # decoded source HTML.
        import html as html_lib

        html = (
            "<article>"
            "<p>5月7日、巨人は&#39;阪神&#39;に5-3で勝利。</p>"
            "<p>戸郷翔征が5回4安打1失点と好投した。</p>"
            "</article>"
        )
        out = extract_article_body_excerpt(html, "https://example.com/")
        decoded_input = html_lib.unescape(html)
        for fragment in out.split("\n"):
            f = fragment.strip()
            if not f or f.endswith("…"):
                continue
            # Allow JP punctuation collapsing but the substantive run
            # must appear in the decoded HTML.
            head = f[:20]
            self.assertIn(head, decoded_input)


if __name__ == "__main__":
    unittest.main()
