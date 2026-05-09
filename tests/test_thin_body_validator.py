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


if __name__ == "__main__":
    unittest.main()
