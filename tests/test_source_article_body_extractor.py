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
    def test_daily_main_text_selector_drops_article_chrome(self):
        html = """
        <article class="detailContent">
          <div class="newsHeader">
            <ol class="breadcrumb"><li>ホーム</li><li>野球</li></ol>
            <time datetime="2026-05-11" class="date">2026.05.11</time>
          </div>
          <h1 class="ttl-main">天国の母へ届け　巨人・坂本　追加点につながる一打「打てて良かった」</h1>
          <div class="newsContent">
            <div class="figureLists single"><span class="figureSize">拡大</span></div>
            <div id="NWrelart:Body" class="mainTxt" wovn-enable>
              <p>　「中日４－９巨人」（１０日、バンテリンドーム）</p>
              <p>　巨人・坂本が八回２死一塁で代打起用され、藤嶋のナックルボールに泳ぎながらも左前打を放った。追加点につながる一打に「打てて良かった」と振り返った。</p>
              <p>　母の日に合わせてピンク色のバットなどでグラウンドに立った。２００７年に小腸がんで母・輝美さんを亡くしたが、大切な日に快音を響かせた。</p>
            </div>
            <a href="javascript:DAILY.openNewsDetail();" class="btnShow" hidden>続きを見る</a>
          </div>
          <div class="score">野球スコア速報</div>
          <section class="recommend">編集者のオススメ記事</section>
        </article>
        """
        out = extract_article_body_excerpt(
            html,
            "https://www.daily.co.jp/baseball/2026/05/11/0020341038.shtml",
            title="天国の母へ届け　巨人・坂本　追加点につながる一打「打てて良かった」",
            max_chars=600,
        )
        self.assertIn("巨人・坂本が八回２死一塁", out)
        self.assertIn("母の日に合わせてピンク色", out)
        self.assertNotIn("天国の母へ届け", out)
        self.assertNotIn("2026.05.11", out)
        self.assertNotIn("拡大", out)
        self.assertNotIn("続きを見る", out)
        self.assertNotIn("野球スコア速報", out)
        self.assertNotIn("編集者のオススメ記事", out)
        self.assertLessEqual(len(out), 600)

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

    def test_leading_date_and_notification_lines_are_dropped(self):
        html = (
            "<article>"
            "<h1>【巨人】ヒヤリ…大城卓三のヘルメットにバット直撃</h1>"
            "<p>[2026年5月10日17時26分]</p>"
            "<p>通知ON</p>"
            "<p>通知OFF</p>"
            "<p>巨人大城卓三捕手の頭部にバットが直撃した。</p>"
            "<p>数分後に立ち上がり、プレーを続行した。</p>"
            "</article>"
        )
        out = extract_article_body_excerpt(
            html,
            "https://www.nikkansports.com/baseball/news/202605100001243.html",
            title="【巨人】ヒヤリ…大城卓三のヘルメットにバット直撃",
            max_chars=600,
        )
        self.assertIn("大城卓三捕手", out)
        self.assertIn("プレーを続行", out)
        self.assertNotIn("ヒヤリ", out)
        self.assertNotIn("2026年5月10日", out)
        self.assertNotIn("通知ON", out)
        self.assertNotIn("通知OFF", out)

    def test_share_ui_buttons_dropped_from_react_helmet_body(self):
        # news.ntv.co.jp / 他 React-rendered ニュースサイトは記事
        # container 内に share UI を sibling <p>/<button> として
        # emit する。post 69888 で実際に excerpt に流入していた
        # 「スポーツ / ポスト / 送る / シェア / ブックマーク /
        # URLをコピー」の 6 ラベルを 1 つも残さないことを担保する
        # regression test。本文の prose は維持する。
        html = (
            "<article>"
            "<p>スポーツ</p>"
            "<h1>ナショナルズのウッドが激走で満塁ホームラン</h1>"
            "<p>ポスト</p>"
            "<p>送る</p>"
            "<p>シェア</p>"
            "<p>ブックマーク</p>"
            "<p>URLをコピー</p>"
            "<p>2026年5月20日 12:59</p>"
            "<p>◇MLB ナショナルズ9-6メッツ(日本時間20日、ナショナルズ・パーク)</p>"
            "<p>ナショナルズのジェームズ・ウッド選手が2回にランニング満塁ホームランを記録しました。</p>"
            "</article>"
        )
        out = extract_article_body_excerpt(
            html,
            "https://news.ntv.co.jp/category/sports/5b63a75714734548999c19fbf038d767",
            title="ナショナルズのウッドが激走で満塁ホームラン",
            max_chars=600,
        )
        # 本文は維持
        self.assertIn("ナショナルズ9-6メッツ", out)
        self.assertIn("ウッド選手", out)
        # share UI と breadcrumb は全部剥がれる
        self.assertNotIn("ポスト", out)
        self.assertNotIn("送る", out)
        self.assertNotIn("シェア", out)
        self.assertNotIn("ブックマーク", out)
        self.assertNotIn("URLをコピー", out)
        # title 単独行と breadcrumb も剥がれる
        self.assertNotIn("スポーツ", out)
        self.assertNotIn("ナショナルズのウッドが激走で満塁ホームラン\n", out)
        self.assertNotIn("2026年5月20日", out)

    def test_share_ui_substring_in_prose_preserved(self):
        # share UI labels は exact-line match で剥がす実装なので、
        # 「ポストシーズン」「メールマガジン」「シェアを伸ばす」
        # のような prose 内 substring は本文として残らなければ
        # ならない (false positive を出さないことの担保)。
        html = (
            "<article>"
            "<p>巨人はポストシーズン進出を目指す。</p>"
            "<p>メールマガジンの読者が増えた。</p>"
            "<p>市場シェアを伸ばす戦略を採用した。</p>"
            "</article>"
        )
        out = extract_article_body_excerpt(
            html,
            "https://example.com/news/123",
            title="巨人の戦略",
            max_chars=600,
        )
        self.assertIn("ポストシーズン", out)
        self.assertIn("メールマガジン", out)
        self.assertIn("シェアを伸ばす", out)


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

    def test_publisher_truncated_short_body_backtracks_to_sentence(self):
        """JSON-LD ``articleBody`` already truncated by the publisher
        ends mid-word; the cleaner must drop the dangling fragment."""
        from src.source_article_body_extractor import _truncate_at_sentence

        text = (
            "巨人の大城卓三捕手（33）が、5日のヤクルト戦（東京D）以来の4号ソロを放った。"
            "両軍無得点の2回1死、床田の初球真ん中寄りのストレートを右翼席に運び、"
            "「風に乗ってくれました。先制点が取れたことは大き"
        )
        # max_chars > len(text) so the truncate path is the short-text
        # cleanup branch, not the cap branch.
        out = _truncate_at_sentence(text, max_chars=600)
        self.assertFalse(out.endswith("大き"))
        self.assertTrue(
            out.endswith("。")
            or out.endswith("」")
            or out.endswith("』")
            or out.endswith("…")
        )

    def test_quote_close_used_when_no_period_above_half(self):
        from src.source_article_body_extractor import _truncate_at_sentence

        text = (
            "巨人の岡本選手はインタビューで「" + "今日は本当にいい当たりだった、"
            "次も同じ気持ちで打席に立ちたい、" * 10 + "」と話した"
        )
        out = _truncate_at_sentence(text, max_chars=120)
        self.assertLessEqual(len(out), 120)
        self.assertTrue(
            out.endswith("」")
            or out.endswith("、…")
            or out.endswith("。")
            or out.endswith("…"),
            f"unexpected ending: ...{out[-10:]!r}",
        )

    def test_clause_break_fallback_adds_ellipsis(self):
        from src.source_article_body_extractor import _truncate_at_sentence

        # No 。 / 」 / \n in head; only 、 as boundary
        text = "巨人は7日、" + "新人選手の練習で打球の伸びを見ていた、" * 30
        out = _truncate_at_sentence(text, max_chars=80)
        self.assertLessEqual(len(out), 80)
        self.assertTrue(out.endswith("…"), f"unexpected ending: ...{out[-10:]!r}")


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


class YahooBoilerplateStripTests(unittest.TestCase):
    """Real-world Yahoo!ニュース body opens with delivery date / comment
    count / image caption / 関連リンク marker before the actual article.
    Post 66824 leaked all of these into the rendered excerpt block. The
    extractor must strip them so only paragraph-level body text remains.
    """

    YAHOO_TITLE = (
        "「正直言って困ってしまった」堀内恒夫氏、"
        "巨人・戸郷翔征にまさかのアドバイス"
        "（スポーツ報知） - Yahoo!ニュース"
    )

    def _build_html(self) -> str:
        return (
            '<html><body><div class="articleBody">'
            "<p>「正直言って困ってしまった」堀内恒夫氏、巨人・戸郷翔征にまさかのアドバイス</p>"
            "<p>5/5(火) 5:20配信</p>"
            "<p>160</p>"
            "<p>コメント160件</p>"
            "<p>力投する戸郷翔征（カメラ・清水 武）</p>"
            "<p>◆ＪＥＲＡセ・リーグ 巨人１―５ヤクルト（４日・東京ドーム）</p>"
            "<p>戸郷は投げる腕を今までよりも少し上げて、真っすぐの威力は１５１キロをマークするなど若干アップしたけれど、頼みのフォークの落ちが悪くなってしまった。</p>"
            "<p>【選手名鑑】戸郷翔征の球歴、年俸など…</p>"
            "<p>もともと真っすぐはそれほどコントロールがいいわけでもないし、この日もシュート回転したり、逆球も多かった。</p>"
            "</div></body></html>"
        )

    def test_strips_yahoo_delivery_date_and_comment_count(self):
        out = extract_article_body_excerpt(
            self._build_html(),
            "https://news.yahoo.co.jp/articles/abc",
            title=self.YAHOO_TITLE,
            max_chars=600,
        )
        self.assertNotIn("5/5(火) 5:20配信", out)
        self.assertNotIn("コメント160件", out)
        self.assertNotRegex(out, r"(^|\n)160(\n|$)")

    def test_strips_title_echo_when_wp_title_has_publisher_suffix(self):
        out = extract_article_body_excerpt(
            self._build_html(),
            "https://news.yahoo.co.jp/articles/abc",
            title=self.YAHOO_TITLE,
            max_chars=600,
        )
        self.assertFalse(
            out.startswith(
                "「正直言って困ってしまった」堀内恒夫氏、巨人・戸郷翔征にまさかのアドバイス"
            ),
            "title echo should be stripped even with long WP-stored title",
        )

    def test_strips_image_caption_with_camera_credit(self):
        out = extract_article_body_excerpt(
            self._build_html(),
            "https://news.yahoo.co.jp/articles/abc",
            title=self.YAHOO_TITLE,
            max_chars=600,
        )
        self.assertNotIn("カメラ・清水", out)

    def test_strips_related_link_marker(self):
        out = extract_article_body_excerpt(
            self._build_html(),
            "https://news.yahoo.co.jp/articles/abc",
            title=self.YAHOO_TITLE,
            max_chars=600,
        )
        self.assertNotIn("【選手名鑑】", out)

    def test_keeps_actual_body_paragraphs(self):
        out = extract_article_body_excerpt(
            self._build_html(),
            "https://news.yahoo.co.jp/articles/abc",
            title=self.YAHOO_TITLE,
            max_chars=600,
        )
        self.assertIn("◆ＪＥＲＡセ・リーグ", out)
        self.assertIn("戸郷は投げる腕を", out)
        self.assertIn("もともと真っすぐは", out)

    def test_short_title_in_body_with_long_wp_title_is_stripped(self):
        """The body has the short article title; WP stores it suffixed.
        The asymmetric old check missed this, the new bidirectional
        check catches it."""
        out = extract_article_body_excerpt(
            self._build_html(),
            "https://news.yahoo.co.jp/articles/abc",
            title=self.YAHOO_TITLE,
            max_chars=600,
        )
        first_paragraph = out.split("\n", 1)[0]
        self.assertNotIn("正直言って困ってしまった", first_paragraph)


class ExcerptParagraphFormattingTests(unittest.TestCase):
    """Tests for the A+B+C readability pass helpers:

    - A: ◆/●/■ で始まる行 → "heading"
    - B: 「...」 が大半を占める行 → "quote"
    - C: 長文 (>80 字 + 複数文) → 文末で sentence-split
    """

    # ─── A. heading detection ─────────────────────────────────────

    def test_heading_diamond_marker_classified_as_heading(self):
        from src.source_article_body_extractor import classify_excerpt_paragraph
        self.assertEqual(
            classify_excerpt_paragraph("◆ＪＥＲＡセ・リーグ 巨人１―５ヤクルト"),
            "heading",
        )

    def test_heading_filled_circle_marker(self):
        from src.source_article_body_extractor import classify_excerpt_paragraph
        self.assertEqual(classify_excerpt_paragraph("●スタメン発表"), "heading")

    def test_heading_filled_square_marker(self):
        from src.source_article_body_extractor import classify_excerpt_paragraph
        self.assertEqual(classify_excerpt_paragraph("■試合経過"), "heading")

    def test_regular_paragraph_not_heading(self):
        from src.source_article_body_extractor import classify_excerpt_paragraph
        self.assertEqual(
            classify_excerpt_paragraph("戸郷は投げる腕を今までよりも少し上げて。"),
            "para",
        )

    # ─── B. quote detection ──────────────────────────────────────

    def test_long_japanese_quote_classified_as_quote(self):
        from src.source_article_body_extractor import classify_excerpt_paragraph
        line = "「フォークの握りを考えてみてはどうだろう。握力を強化する手もある。」"
        self.assertEqual(classify_excerpt_paragraph(line), "quote")

    def test_short_quote_in_paragraph_not_quote(self):
        # quote must be substantial (≥30 chars inside 「」). A short
        # in-line quote like 「は」と語った should NOT lift to a
        # blockquote — that would split natural prose.
        from src.source_article_body_extractor import classify_excerpt_paragraph
        line = "監督は「準備していた」と語った。"
        self.assertEqual(classify_excerpt_paragraph(line), "para")

    def test_quote_followed_by_trailing_attribution_not_quote(self):
        # When 「...」 closes but a long trailing description follows
        # (more than ~10 chars after 」), keep as paragraph — splitting
        # would orphan the attribution.
        from src.source_article_body_extractor import classify_excerpt_paragraph
        line = (
            "「フォークの握りを考えてみてはどうだろう。握力を強化する手もある」"
            "と堀内氏は語った上で、首脳陣にも自分で答えを出すべきと示唆した。"
        )
        self.assertEqual(classify_excerpt_paragraph(line), "para")

    # ─── C. sentence split ──────────────────────────────────────

    def test_short_paragraph_not_split(self):
        from src.source_article_body_extractor import split_paragraph_sentences
        self.assertEqual(
            split_paragraph_sentences("戸郷は好投した。"),
            ["戸郷は好投した。"],
        )

    def test_long_paragraph_with_multiple_sentences_splits_at_period(self):
        from src.source_article_body_extractor import split_paragraph_sentences
        text = (
            "戸郷は投げる腕を今までよりも少し上げて、真っすぐの威力は１５１キロをマーク。"
            "初回の武岡こそストライクからボールになるフォークで三振を取れた。"
            "あとはファウルにされたり、見極められたりしてしまう。"
        )
        out = split_paragraph_sentences(text)
        self.assertEqual(len(out), 3)
        self.assertTrue(all(s.endswith("。") for s in out))
        self.assertIn("戸郷は投げる腕", out[0])
        self.assertIn("初回の武岡こそ", out[1])
        self.assertIn("あとはファウル", out[2])

    def test_long_paragraph_single_sentence_not_split(self):
        # >80 chars but only 1 sentence-final char → keep as single line
        from src.source_article_body_extractor import split_paragraph_sentences
        text = "戸郷は投げる腕を今までよりも少し上げて、真っすぐの威力は１５１キロをマークするなど若干アップしたけれど、頼みのフォークの落ちが悪くなってしまった。"
        out = split_paragraph_sentences(text)
        self.assertEqual(len(out), 1)

    def test_split_preserves_exclamation_and_question(self):
        from src.source_article_body_extractor import split_paragraph_sentences
        # Force the threshold low so the test isolates split-character
        # logic from threshold-tuning.
        text = (
            "どうすれば、いいかって？ フォークの握りを考えてみてはどうだろう。"
            "握力を強化する手もある！ 投げるテンポもゆっくりにして丁寧なピッチングを心がける。"
        )
        out = split_paragraph_sentences(text, threshold=20)
        # 4 sentence finals → 4 chunks
        self.assertEqual(len(out), 4)


if __name__ == "__main__":
    unittest.main()
