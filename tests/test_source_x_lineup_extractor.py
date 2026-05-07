"""Tests for src/source_x_lineup_extractor.py — NOMOTOKE-LINEUP-FROM-X-001."""

from __future__ import annotations

import unittest

from src.source_x_lineup_extractor import (
    LINEUP_KEYWORDS,
    parse_x_lineup_tweet,
)


class XLineupParserTests(unittest.TestCase):
    def test_full_9_row_tweet(self):
        title = "本日のスタメン"
        summary = (
            "本日のスタメンが発表されました⚾<br />"
            "1番（中）ヘルナンデス<br />"
            "2番（二）吉川尚輝<br />"
            "3番（一）岡本和真<br />"
            "4番（左）キャベッジ<br />"
            "5番（右）佐々木俊輔<br />"
            "6番（三）増田陸<br />"
            "7番（遊）泉口友汰<br />"
            "8番（捕）大城卓三<br />"
            "9番（投）戸郷翔征"
        )
        result = parse_x_lineup_tweet(title, summary)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["lineup"]), 9)
        self.assertEqual(result["lineup"][0]["order"], "1")
        self.assertEqual(result["lineup"][0]["position"], "中")
        self.assertEqual(result["lineup"][0]["player_name"], "ヘルナンデス")
        self.assertEqual(result["lineup"][8]["order"], "9")
        self.assertEqual(result["lineup"][8]["position"], "投")
        self.assertEqual(result["lineup"][8]["player_name"], "戸郷翔征")

    def test_condensed_lineup_with_half_width_parens(self):
        result = parse_x_lineup_tweet(
            "【スタメン発表】",
            "【スタメン発表】1番(中)ヘルナンデス、2番(二)吉川尚輝、3番(一)岡本和真、"
            "4番(左)キャベッジ、5番(右)佐々木俊輔、6番(三)増田陸、"
            "7番(遊)泉口友汰、8番(捕)大城卓三、9番(投)戸郷翔征",
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result["lineup"]), 9)
        # Order is canonical 1→9 even though regex hits left-to-right.
        for i, row in enumerate(result["lineup"], start=1):
            self.assertEqual(row["order"], str(i))

    def test_dh_lineup_8_rows_passes(self):
        # DH lineup uses 指 instead of 投 at 9番; 9 rows total.
        # Or some weekend games drop pitcher → 8 rows. The parser's
        # lower bound is 7 rows.
        summary = (
            "本日のスタメン<br />"
            "1番（中）ヘルナンデス<br />"
            "2番（二）吉川尚輝<br />"
            "3番（一）岡本和真<br />"
            "4番（指）キャベッジ<br />"
            "5番（左）佐々木俊輔<br />"
            "6番（三）増田陸<br />"
            "7番（遊）泉口友汰<br />"
            "8番（捕）大城卓三"
        )
        result = parse_x_lineup_tweet("本日のスタメン", summary)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["lineup"]), 8)

    def test_too_few_rows_returns_none(self):
        # 6 rows should fail the ≥7 threshold.
        summary = (
            "本日のスタメン<br />"
            "1番（中）ヘルナンデス<br />"
            "2番（二）吉川尚輝<br />"
            "3番（一）岡本和真<br />"
            "4番（指）キャベッジ<br />"
            "5番（左）佐々木俊輔<br />"
            "6番（三）増田陸"
        )
        self.assertIsNone(parse_x_lineup_tweet("本日のスタメン", summary))

    def test_no_keyword_returns_none(self):
        # 9-row pattern but no スタメン keyword.
        summary = (
            "1番（中）ヘルナンデス<br />2番（二）吉川尚輝<br />"
            "3番（一）岡本和真<br />4番（左）キャベッジ<br />"
            "5番（右）佐々木俊輔<br />6番（三）増田陸<br />"
            "7番（遊）泉口友汰<br />8番（捕）大城卓三<br />"
            "9番（投）戸郷翔征"
        )
        self.assertIsNone(parse_x_lineup_tweet("ヤクルト戦の予想", summary))

    def test_unrelated_tweet_returns_none(self):
        for title, summary in (
            (
                "吉川選手「NAOKI IS BACK」記念グッズ発売",
                "本日5/7から受注販売します",
            ),
            (
                "【試合終了】巨人 0-5 ヤクルト",
                "9回は走者を出すことが出来ず試合終了",
            ),
            ("", ""),
        ):
            with self.subTest(title=title):
                self.assertIsNone(parse_x_lineup_tweet(title, summary))

    def test_keyword_taxonomy_exposed(self):
        self.assertIn("スタメン", LINEUP_KEYWORDS)
        self.assertIn("先発オーダー", LINEUP_KEYWORDS)

    def test_long_helper_name_not_truncated(self):
        # 13+ char names (中黒入りの助っ人名) should pass the parser.
        summary = (
            "本日のスタメン<br />"
            "1番（中）スターリン・ヘルナンデス<br />"
            "2番（二）吉川尚輝<br />3番（一）岡本和真<br />"
            "4番（左）キャベッジ<br />5番（右）佐々木俊輔<br />"
            "6番（三）増田陸<br />7番（遊）泉口友汰<br />"
            "8番（捕）大城卓三<br />9番（投）戸郷翔征"
        )
        result = parse_x_lineup_tweet("本日のスタメン", summary)
        self.assertIsNotNone(result)
        # 中黒 stops the name capture, but the 13-char Hernández prefix
        # is preserved up to the 中黒 boundary.
        self.assertEqual(result["lineup"][0]["player_name"], "スターリン")

    def test_fullwidth_comma_separated_inline(self):
        # Some operators post the lineup on one line with 全角 commas.
        summary = (
            "【スタメン発表】"
            "1番（中）ヘルナンデス，"
            "2番（二）吉川尚輝，"
            "3番（一）岡本和真，"
            "4番（左）キャベッジ，"
            "5番（右）佐々木俊輔，"
            "6番（三）増田陸，"
            "7番（遊）泉口友汰，"
            "8番（捕）大城卓三，"
            "9番（投）戸郷翔征"
        )
        result = parse_x_lineup_tweet("【スタメン発表】", summary)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["lineup"]), 9)


class XLineupRendererIntegrationTests(unittest.TestCase):
    def test_parsed_lineup_renders_via_lineup_card(self):
        import os

        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import render_lineup_card

        result = parse_x_lineup_tweet(
            "本日のスタメン",
            "本日のスタメンが発表されました<br />"
            "1番（中）ヘルナンデス<br />2番（二）吉川尚輝<br />"
            "3番（一）岡本和真<br />4番（左）キャベッジ<br />"
            "5番（右）佐々木俊輔<br />6番（三）増田陸<br />"
            "7番（遊）泉口友汰<br />8番（捕）大城卓三<br />"
            "9番（投）戸郷翔征",
        )
        payload = {
            "team_name": "巨人",
            "own_lineup": result["lineup"],
            "date_label": "2026年5月8日",
            "league_label": "セ・リーグ 公式戦",
            "home": "巨人",
            "away": "中日",
            "opponent_name": "中日",
            "source_url": "https://x.com/TokyoGiants/status/1",
            "source_name": "巨人公式X",
            "source_label": "巨人公式X",
        }
        rendered = render_lineup_card(payload)
        self.assertTrue(rendered["validation_ok"])
        body = rendered["content_html"]
        self.assertIn("ヘルナンデス", body)
        self.assertIn("戸郷翔征", body)
        self.assertIn("打順", body)


if __name__ == "__main__":
    unittest.main()
