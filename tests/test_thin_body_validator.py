"""Tests for src/thin_body_validator.py."""

from __future__ import annotations

import unittest

from src.nomotoke_card_renderer import render_postgame_card
from src.thin_body_validator import is_thin_body


def _minimal_postgame_card_html(*, result: str = "loss", opposing_pitcher: str = "") -> str:
    payload = {
        "date_label": "2026年5月6日",
        "league_label": "セ・リーグ",
        "home": "巨人",
        "away": "阪神",
        "team_name": "巨人",
        "score": "5-3",
        "result": result,
        "one_line_summary": "",
        "source_url": "https://example.com/postgame-source",
        "inning_score": [
            {
                "name": "巨人",
                "innings": [0, 1, 0, 0, 0, 2, 0, 2, "x"],
                "total": 5,
            },
            {
                "name": "阪神",
                "innings": [1, 0, 0, 1, 0, 0, 1, 0, 0],
                "total": 3,
            },
        ],
        "atbat_results": [],
        "pitching_results": [],
        "opponent_lineup": [],
        "opposing_pitcher": opposing_pitcher,
    }
    return render_postgame_card(payload)["content_html"]


class TestThinBodyEmptyAndSmall(unittest.TestCase):
    def test_empty_string(self) -> None:
        result = is_thin_body("")
        self.assertTrue(result.is_thin)
        self.assertEqual(result.reason, "empty_body")
        self.assertEqual(result.text_chars, 0)
        self.assertEqual(result.html_chars, 0)

    def test_none(self) -> None:
        result = is_thin_body(None)  # type: ignore[arg-type]
        self.assertTrue(result.is_thin)
        self.assertEqual(result.reason, "empty_body")

    def test_minimal_test_body_passes(self) -> None:
        # ``<p>body</p>`` 等の test infrastructure body は通す。
        # 本 validator は oembed-only incident 専用 narrow gate。
        result = is_thin_body("<p>body</p>")
        self.assertFalse(result.is_thin, msg=f"unexpected: {result.reason}")

    def test_short_p_text_passes(self) -> None:
        # 短い <p> だけの body も oembed_only ではないので通す。
        # (品質 gate は post_gen_validate / body_contract の責務)
        body = "<p>" + ("x" * 10) + "</p>"
        result = is_thin_body(body)
        self.assertFalse(result.is_thin, msg=f"unexpected: {result.reason}")


class TestOembedOnlyDetection(unittest.TestCase):
    """2026-05-08 13:04 incident のような oembed-only body を検出する。"""

    def test_actual_incident_post_65082_body(self) -> None:
        # post 65082 の実 body をそのまま使う。
        body = (
            "\n"
            '<div class="yoshilover-x-embed" '
            'style="margin:24px auto !important;max-width:550px;">\n'
            '  <blockquote class="twitter-tweet" data-dnt="true" data-lang="ja">\n'
            '    <a href="https://hochi.news/articles/20260507-OHT1T51323.html">'
            "https://hochi.news/articles/20260507-OHT1T51323.html</a>\n"
            "  </blockquote>\n"
            "</div>\n"
            "\n"
            "\n"
            '<script async src="https://platform.twitter.com/widgets.js" '
            'charset="utf-8"></script>\n'
            "<!--yl-src:c05f646c333a61ec-->"
        )
        result = is_thin_body(body)
        self.assertTrue(result.is_thin)
        self.assertEqual(result.reason, "oembed_only_no_body")

    def test_oembed_only_no_h3_no_text_p(self) -> None:
        # link text に URL を載せて text 30+ chars にする (実際の post pattern)。
        body = (
            '<div class="yoshilover-x-embed">'
            '<blockquote class="twitter-tweet">'
            '<a href="https://hochi.news/articles/abcdef-12345.html">'
            "https://hochi.news/articles/abcdef-12345.html</a>"
            "</blockquote></div>"
        )
        result = is_thin_body(body)
        self.assertTrue(result.is_thin)
        self.assertEqual(result.reason, "oembed_only_no_body")


class TestNonThinBodies(unittest.TestCase):
    """正常な body は通す。false positive を出さない。"""

    def test_oembed_with_h3_and_p_passes(self) -> None:
        # X embed + actual body (postgame full の典型) は通すべき。
        body = (
            "<h3>📋 事実カード</h3>"
            "<p>巨人 3-2 阪神に勝利。9回サヨナラ本塁打。先発投手は"
            "山崎伊織で 7 回 2 失点。リリーフ陣も無失点で逃げ切った。</p>"
            "<h3>💬 ファンの声(Xより)</h3>"
            '<div class="yoshilover-x-embed">'
            '<blockquote class="twitter-tweet"><a href="https://twitter.com/g/123">tweet</a></blockquote>'
            "</div>"
        )
        result = is_thin_body(body)
        self.assertFalse(result.is_thin, msg=f"unexpected reason: {result.reason}")

    def test_short_article_with_p_text_passes(self) -> None:
        # 300-500 chars の短い記事でも、text を含む <p> があれば通す。
        body = (
            "<p>巨人の岡本和真選手が今季 10 号本塁打を放った。"
            "5 月としては自己最速のペース。チームは現在首位を維持しており、"
            "今後の打撃陣の活躍に期待がかかる。</p>"
            '<p><a href="https://hochi.news/x.html">続きを読む</a></p>'
        )
        result = is_thin_body(body)
        self.assertFalse(result.is_thin, msg=f"unexpected reason: {result.reason}")

    def test_full_postgame_body_passes(self) -> None:
        body = (
            "<h3>📋 事実カード</h3>"
            "<p>" + ("試合の詳細記述。" * 50) + "</p>"
            "<h3>🔗 出典記事</h3>"
            '<p><a href="https://yahoo.co.jp">Yahoo Sportsnavi</a></p>'
        )
        result = is_thin_body(body)
        self.assertFalse(result.is_thin)

    def test_broadcast_template_passes(self) -> None:
        # 中継予定 record のような短いが構造ある body。
        body = (
            "<h3>🎬 中継予定</h3>"
            "<p>2026 年 5 月 9 日 18:00 開始 中日 vs 巨人</p>"
            "<p>NHK BS / DAZN にて中継予定です。</p>"
            "<h3>🔗 出典記事</h3>"
            '<p><a href="https://...">出典</a></p>'
        )
        result = is_thin_body(body)
        self.assertFalse(result.is_thin)


class TestEdgeCases(unittest.TestCase):
    def test_oembed_with_long_html_outside_oembed_passes(self) -> None:
        # script tag が長くて html 600+ chars だと oembed_only の HTML < 600
        # 条件が外れる。本 validator は body_too_small を見ないので false に
        # 落ちる (script 多用の正常 body は通す方針)。
        body = (
            '<div class="yoshilover-x-embed">'
            '<blockquote class="twitter-tweet">'
            '<a href="https://x.com/g/1">tweet</a>'
            "</blockquote></div>"
            "<script>" + ("a" * 600) + "</script>"
        )
        result = is_thin_body(body)
        self.assertFalse(result.is_thin, msg=f"unexpected: {result.reason}")

    def test_only_h3_no_oembed_passes(self) -> None:
        # H3 だけで oembed 無くても、structure があるので通す。
        body = (
            "<h3>📋 事実カード</h3>"
            "<p>" + ("巨人の試合結果情報。" * 5) + "</p>"
        )
        result = is_thin_body(body)
        self.assertFalse(result.is_thin)


class TestScoreboardOnlyPostgameDetection(unittest.TestCase):
    def test_rendered_scoreboard_only_postgame_card_is_thin(self) -> None:
        body = _minimal_postgame_card_html(result="loss")
        result = is_thin_body(body)
        self.assertTrue(result.is_thin)
        self.assertEqual(result.reason, "postgame_scorecard_only")

    def test_rendered_scoreboard_only_postgame_with_only_opposing_pitcher_is_thin(self) -> None:
        body = _minimal_postgame_card_html(result="loss", opposing_pitcher="青柳晃洋")
        result = is_thin_body(body)
        self.assertTrue(result.is_thin)
        self.assertEqual(result.reason, "postgame_scorecard_only")

    def test_rendered_postgame_with_pitcher_result_section_passes(self) -> None:
        body = render_postgame_card(
            {
                "date_label": "2026年5月16日",
                "league_label": "セ・リーグ 8回戦",
                "home": "読売ジャイアンツ",
                "away": "横浜DeNAベイスターズ",
                "team_name": "巨人",
                "score": "4-3",
                "result": "win",
                "one_line_summary": "読売ジャイアンツが4-3で勝利",
                "source_url": "https://baseball.yahoo.co.jp/npb/game/2021038866/index",
                "inning_score": [
                    {"name": "DeNA", "innings": [0, 0, 2, 0, 1, 0, 0, 0, 0], "total": 3},
                    {"name": "巨人", "innings": [0, 1, 0, 1, 0, 1, 1, 0, "x"], "total": 4},
                ],
                "winning_pitcher": {"team": "巨人", "name": "高梨", "record": "1勝0敗0S"},
                "losing_pitcher": {"team": "DeNA", "name": "中川", "record": "0勝1敗0S"},
                "save_pitcher": {"team": "巨人", "name": "マルティネス", "record": "0勝0敗12S"},
            }
        )["content_html"]
        result = is_thin_body(body)
        self.assertFalse(result.is_thin, msg=f"unexpected: {result.reason}")

    def test_rendered_postgame_with_detail_sections_passes(self) -> None:
        payload = {
            "date_label": "2026年5月6日",
            "league_label": "セ・リーグ",
            "home": "巨人",
            "away": "阪神",
            "team_name": "巨人",
            "score": "5-3",
            "result": "win",
            "one_line_summary": "終盤の集中打で勝利",
            "source_url": "https://example.com/postgame-source",
            "inning_score": [
                {
                    "name": "巨人",
                    "innings": [0, 1, 0, 0, 0, 2, 0, 2, "x"],
                    "total": 5,
                },
                {
                    "name": "阪神",
                    "innings": [1, 0, 0, 1, 0, 0, 1, 0, 0],
                    "total": 3,
                },
            ],
            "atbat_results": [
                {"player_name": "丸佳浩", "order": 1, "result": "中安, 三振, 四球, 二塁打"},
            ],
            "pitching_results": [
                {"pitcher_name": "戸郷翔征", "innings": "7", "runs": "2", "summary": "勝利投手"},
            ],
            "opponent_lineup": [
                {
                    "order": 1,
                    "position": "中",
                    "player_name": "近本光司",
                    "batting_average": ".310",
                    "starter_era": "",
                }
            ],
            "opposing_pitcher": "青柳晃洋",
        }
        body = render_postgame_card(payload)["content_html"]
        result = is_thin_body(body)
        self.assertFalse(result.is_thin, msg=f"unexpected: {result.reason}")


class TestThinSourcePaddingDetection(unittest.TestCase):
    """1ツイート水増し: 短いSNSソースをAI scaffolding/質問句/一般論で
    1500-2700字に膨らませた本文を検出する。"""

    @staticmethod
    def _x_embed_block() -> str:
        return (
            '<div class="yoshilover-x-embed" '
            'style="margin:24px auto !important;max-width:550px;">'
            '<blockquote class="twitter-tweet" data-dnt="true" data-lang="ja">'
            '<a href="https://twitter.com/yomiuri_giants/status/12345">'
            "twitter post</a>"
            "</blockquote></div>"
            '<script async src="https://platform.twitter.com/widgets.js"></script>'
        )

    def test_one_tweet_with_scaffolding_padding_is_thin(self) -> None:
        embed = self._x_embed_block()
        # ~1500-2700字 padding pattern: 1 ツイート + AI scaffolding 長文.
        scaffolding_padding = (
            "<p>球団からの発表を受けて、ファンの皆さんはどう感じるでしょうか。"
            "今後の動向に注目が集まります。次の試合に向けて期待が高まりますね。"
            "これからの活躍が楽しみです。皆さんはどう見るでしょうか。"
            "気になるポイントとして、コンディション面が挙げられます。"
            "ご注目ください。次の展開を見守りたいところです。"
            "今シーズンの注目選手として名前が挙がるのではないでしょうか。"
            "ファンの期待は高まる一方です。これからの戦いに期待したいと言えるでしょう。"
            "選手のコメントは「」とだけ伝えられました。"
            "ファンの反応も様々で、楽しみにしたいという声が多いです。"
            "今後の展開に注目したいところです。これからの活躍を見守りたいですね。"
            "球団としては慎重な判断が求められる場面と言えるでしょう。"
            "ファンの皆さんの応援が選手を支える大きな力になっていると考えられます。"
            "今シーズンのチーム力強化に向けて、どのような展開になるのか気になるところです。"
            "これからの展開を皆さんも見守っていただきたいと言えるでしょう。"
            "今後の発表に注目が集まることは間違いありません。"
            "選手のコンディションや起用法についても、これからの動向に注目したいですね。"
            "ファンの皆さんはどう見るのではないでしょうか。"
            "球団からの今後の発表が待たれるところです。"
            "今シーズンの戦いに向けて、どのような展開を見せてくれるのか期待が高まります。"
            "ファンの反応もこれから様々な形で表れてくると思われます。"
            "次の試合に向けて、選手たちのコンディションが気になるところです。"
            "皆さんも今後の動向にぜひ注目してみてください。"
            "これからのチームの戦いに期待したいですね。"
            "ファンの皆さんの期待に応える活躍が見られるのではないかと考えられます。"
            "選手たちのこれからの戦いに、心からエールを送りたいところです。</p>"
        )
        body = embed + scaffolding_padding
        result = is_thin_body(body)
        self.assertTrue(
            result.is_thin,
            msg=f"unexpected reason={result.reason} chars={result.text_chars}",
        )
        self.assertEqual(result.reason, "thin_source_padding")

    def test_short_fact_summary_with_tweet_passes(self) -> None:
        """1ツイート + 400-500字の短い事実整理は padding ではないので通す."""
        embed = self._x_embed_block()
        short_factual = (
            "<p>巨人の岡本和真選手が今季 10 号本塁打を放った。"
            "5 月としては自己最速のペース。チームは現在首位を維持しており、"
            "5 月 13 日の試合では 3-2 で勝利した。"
            "岡本は 4 打数 2 安打 2 打点と好調をキープしている。</p>"
        )
        body = embed + short_factual
        result = is_thin_body(body)
        self.assertFalse(
            result.is_thin,
            msg=f"unexpected reason={result.reason} chars={result.text_chars}",
        )

    def test_postgame_card_with_dense_facts_passes(self) -> None:
        """試合結果/二軍結果/データ記事など短文でも事実密度が高い記事は通す."""
        embed = self._x_embed_block()
        dense_facts = (
            "<h3>📋 事実カード</h3>"
            "<p>巨人 3-2 阪神。先発投手の戸郷翔征は 7 回を投げ 2 失点で勝利投手。"
            "中4日での登板で防御率 2.50。坂本勇人は 4 打数 3 安打 2 打点で第 15 号本塁打を放った。"
            "9 回には岡本和真がタイムリーを放ち決勝点。リリーフ陣は無失点で逃げ切り、"
            "完投はならなかったが見事な勝利。打率 .295 の坂本が打線を牽引した。"
            "ホームランは今季 15 号目で、5 月としては自己最速ペース。"
            "中堅としては安定した守備も見せ、勝利に大きく貢献した。</p>"
        )
        body = embed + dense_facts
        result = is_thin_body(body)
        self.assertFalse(
            result.is_thin,
            msg=f"unexpected reason={result.reason} chars={result.text_chars}",
        )

    def test_long_real_quote_with_tweet_passes(self) -> None:
        """実コメント引用は scaffolding ではない."""
        embed = self._x_embed_block()
        real_quote_body = (
            "<p>戸郷翔征は試合後の取材で「最後まで集中して投げ切れたのが良かった。"
            "次の登板に向けて、しっかり調整したいと思います。チームに勝ちをつけられて"
            "嬉しいです」と語った。中4日での登板だったが、7回2失点でまとめ、"
            "防御率は 2.50 まで下がった。次回登板は中日戦の見込み。</p>"
        )
        body = embed + real_quote_body
        result = is_thin_body(body)
        self.assertFalse(
            result.is_thin,
            msg=f"unexpected reason={result.reason} chars={result.text_chars}",
        )

    def test_no_x_embed_not_flagged(self) -> None:
        """X embed 無し (短文 SNS source signal なし) は本 gate の対象外."""
        # Same scaffolding text as the padded case, but no X embed. 別 gate
        # の責務 (post_gen_validate 等) で扱うべきで thin_source_padding 自体は
        # この shape を flag しない。
        scaffolding_only = (
            "<p>ファンの皆さんはどう感じるでしょうか。今後の動向に注目が集まります。"
            "次の試合に向けて期待が高まりますね。これからの活躍が楽しみです。"
            "皆さんはどう見るでしょうか。気になるポイントとして、コンディション面が"
            "挙げられます。ご注目ください。次の展開を見守りたいところです。"
            "今シーズンの注目選手として名前が挙がるのではないでしょうか。"
            "ファンの期待は高まる一方です。これからの戦いに期待したいと言えるでしょう。"
            "球団としては慎重な判断が求められる場面と言えるでしょう。"
            "ファンの皆さんの応援が選手を支える大きな力になっていると考えられます。"
            "今シーズンのチーム力強化に向けて、どのような展開になるのか気になるところです。"
            "これからの展開を皆さんも見守っていただきたいと言えるでしょう。"
            "今後の発表に注目が集まることは間違いありません。"
            "選手のコンディションや起用法についても、これからの動向に注目したいですね。"
            "今後の展開に注目したいところです。これからの活躍を見守りたいですね。</p>"
        )
        result = is_thin_body(scaffolding_only)
        # X embed が無ければ thin_source_padding は発火しない (別 gate の責務)。
        self.assertNotEqual(result.reason, "thin_source_padding")

    def test_text_too_short_for_padding_passes(self) -> None:
        """1ツイート + 100字以下の事実短文は padding 範囲外."""
        embed = self._x_embed_block()
        body = embed + "<p>ファンの皆さんはどう感じるでしょうか。注目したい。</p>"
        result = is_thin_body(body)
        self.assertNotEqual(result.reason, "thin_source_padding")


if __name__ == "__main__":
    unittest.main()
