"""Unit tests for ``src/source_hochi_compact_lineup_extractor.py``.

NOMOTOKE-LINEUP-FROM-HOCHI-COMPACT-001 Phase 2A regression coverage.

Conservative parser tests:
- 1軍 / 2軍 fixtures covering both single-team and dual-team compact tweets
- DH (``D``) and explicit pitcher (``P``) shorthand recognition
- Defer to ``source_x_lineup_extractor`` when 巨人公式X clean format is present
- Source allowlist (only 報知 / スポニチ family parses)
- Min row gate (< 8 -> ``None``)
- Edge cases: empty / whitespace-only / HTML-stripped / NFKC half/full-width
- ``DeNA`` team-name fragment must NOT mis-parse as ``D + eNA``
"""

from __future__ import annotations

import unittest

from src.source_hochi_compact_lineup_extractor import (
    HOCHI_SPONICHI_SOURCE_NAMES,
    is_hochi_sponichi_source,
    parse_hochi_compact_lineup,
)


# Production-shaped fixtures (verified 2026-05-12 against id=66442 source).
HOCHI_FARM_BOTH_TEAMS = (
    "ファーム・リーグ（Ｇタウン） スタメン 【DeNA】 【巨人】 "
    "D東妻 7萩尾 3加藤 9皆川 6石上 6小濱 5宮下 5藤井 7井上 3三塚 "
    "4小田 8浅野 9梶原 Dティマ 2古市 2山瀬 8濱 4湯浅 P片山 P又木"
)
HOCHI_FIRST_TEAM_SOLO = (
    "巨人スタメン 中日戦(バンテリンD、13:30) "
    "4吉川 7キャベッジ 9丸 5ダルベック 2大城 3増田 8平山 6浦田 1森田"
)
OFFICIAL_X_CLEAN_FORMAT = (
    "本日のスタメン "
    "1番（中）ヘルナンデス 2番（二）吉川 3番（一）岡本 4番（指）丸 "
    "5番（左）キャベッジ 6番（三）増田 7番（右）萩尾 8番（捕）大城 "
    "9番（投）戸郷"
)


class IsHochiSponichiSourceTests(unittest.TestCase):
    def test_known_names_recognised(self):
        for name in HOCHI_SPONICHI_SOURCE_NAMES:
            with self.subTest(name=name):
                self.assertTrue(is_hochi_sponichi_source(source_name=name))

    def test_substring_match_for_japanese_aliases(self):
        self.assertTrue(is_hochi_sponichi_source(source_name="スポーツ報知 巨人 編集部"))
        self.assertTrue(is_hochi_sponichi_source(source_name="スポニチ大阪本社"))

    def test_url_substring_match(self):
        self.assertTrue(
            is_hochi_sponichi_source(
                source_name="",
                source_url="https://hochi.news/articles/20260511-OHT1T51280.html",
            )
        )
        self.assertTrue(
            is_hochi_sponichi_source(
                source_name="",
                source_url="https://twitter.com/hochi_giants/status/12345",
            )
        )
        self.assertTrue(
            is_hochi_sponichi_source(
                source_name="",
                source_url="https://www.sponichi.co.jp/baseball/",
            )
        )

    def test_unknown_sources_rejected(self):
        self.assertFalse(is_hochi_sponichi_source(source_name="巨人公式X"))
        self.assertFalse(is_hochi_sponichi_source(source_name="Yahoo!プロ野球"))
        self.assertFalse(is_hochi_sponichi_source(source_name=""))
        self.assertFalse(
            is_hochi_sponichi_source(
                source_name="ベースボールキング",
                source_url="https://www.baseballking.jp/article/123",
            )
        )


class ParseHochiCompactLineupTests(unittest.TestCase):
    def test_2gun_both_teams_extracts_all_unique_rows(self):
        result = parse_hochi_compact_lineup(
            title=HOCHI_FARM_BOTH_TEAMS,
            summary=HOCHI_FARM_BOTH_TEAMS,
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(result)
        rows = result["lineup"]
        # 20 unique (position, name) pairs from 2 teams concatenated.
        self.assertEqual(len(rows), 20, f"expected 20 unique rows, got {len(rows)}")
        # First row is DH 東妻 (DeNA leadoff in this source convention).
        self.assertEqual(rows[0]["position"], "指")
        self.assertEqual(rows[0]["name"], "東妻")
        # Pitchers (P-prefix) mapped to 投.
        pitchers = [r for r in rows if r["position"] == "投"]
        self.assertGreaterEqual(len(pitchers), 2)
        pitcher_names = {r["name"] for r in pitchers}
        self.assertIn("片山", pitcher_names)
        self.assertIn("又木", pitcher_names)

    def test_2gun_does_not_misparse_dena_team_label(self):
        """``DeNA`` must NOT be mis-extracted as ``D`` + ``eNA``.

        Lower-case Latin is intentionally excluded from the name char
        class so team-name fragments inside ``【DeNA】`` are skipped.
        """
        result = parse_hochi_compact_lineup(
            title=HOCHI_FARM_BOTH_TEAMS,
            summary=HOCHI_FARM_BOTH_TEAMS,
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(result)
        names = [r["name"] for r in result["lineup"]]
        self.assertNotIn("eNA", names)
        # No row name contains lower-case latin from team labels.
        for n in names:
            self.assertFalse(
                any(c.islower() and c.isascii() for c in n),
                f"row name '{n}' contains lower-case latin",
            )

    def test_1gun_solo_team_extracts_nine_rows(self):
        result = parse_hochi_compact_lineup(
            title=HOCHI_FIRST_TEAM_SOLO,
            summary=HOCHI_FIRST_TEAM_SOLO,
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(result)
        rows = result["lineup"]
        # 9 batters; title==summary doubles raw matches but dedupe leaves 9.
        self.assertEqual(len(rows), 9)
        # Position digit -> kanji mapping is correct for each slot.
        expected = [
            ("1", "二", "吉川"),
            ("2", "左", "キャベッジ"),
            ("3", "右", "丸"),
            ("4", "三", "ダルベック"),
            ("5", "捕", "大城"),
            ("6", "一", "増田"),
            ("7", "中", "平山"),
            ("8", "遊", "浦田"),
            ("9", "投", "森田"),
        ]
        for row, (order, position, name) in zip(rows, expected):
            self.assertEqual(row["order"], order)
            self.assertEqual(row["position"], position)
            self.assertEqual(row["name"], name)

    def test_dh_letter_d_maps_to_kanji_shi(self):
        text = "ファームスタメン D東妻 7萩尾 3加藤 9皆川 6石上 5宮下 4湯浅 8浅野 1又木"
        result = parse_hochi_compact_lineup(
            title=text, summary=text, source_name="スポーツ報知巨人班X"
        )
        self.assertIsNotNone(result)
        rows = result["lineup"]
        dh_rows = [r for r in rows if r["position"] == "指"]
        self.assertEqual(len(dh_rows), 1)
        self.assertEqual(dh_rows[0]["name"], "東妻")

    def test_official_x_clean_format_returns_none(self):
        """巨人公式X 形式 → 既存 source_x_lineup_extractor に委ねる(None)。"""
        result = parse_hochi_compact_lineup(
            title=OFFICIAL_X_CLEAN_FORMAT,
            summary=OFFICIAL_X_CLEAN_FORMAT,
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNone(result)

    def test_non_hochi_source_returns_none(self):
        """Source allowlist 外(Yahoo / 巨人公式X 等)は parse 対象外。"""
        result = parse_hochi_compact_lineup(
            title=HOCHI_FIRST_TEAM_SOLO,
            summary=HOCHI_FIRST_TEAM_SOLO,
            source_name="Yahoo!プロ野球",
        )
        self.assertIsNone(result)
        result2 = parse_hochi_compact_lineup(
            title=HOCHI_FIRST_TEAM_SOLO,
            summary=HOCHI_FIRST_TEAM_SOLO,
            source_name="巨人公式X",
        )
        self.assertIsNone(result2)

    def test_keyword_missing_returns_none(self):
        """``スタメン`` / ``オーダー`` / ``ファーム`` 等のキーワードが無ければ skip。"""
        text = "巨人 4吉川 7キャベッジ 9丸 5ダルベック 2大城 3増田 8平山 6浦田 1森田"
        result = parse_hochi_compact_lineup(
            title=text, summary=text, source_name="スポーツ報知巨人班X"
        )
        self.assertIsNone(result)

    def test_too_few_tokens_returns_none(self):
        """row 数 < 8 → None(silent skip ではなく明示的 None)。"""
        text = "本日のスタメン 1吉川 2大城 3増田"
        result = parse_hochi_compact_lineup(
            title=text, summary=text, source_name="スポーツ報知巨人班X"
        )
        self.assertIsNone(result)

    def test_empty_or_whitespace_returns_none(self):
        for text in ("", "   ", "\n\n\n", "　　　"):
            with self.subTest(text=repr(text)):
                self.assertIsNone(
                    parse_hochi_compact_lineup(
                        title=text, summary=text, source_name="スポーツ報知巨人班X"
                    )
                )

    def test_html_tags_stripped_before_parse(self):
        text = (
            "<p>本日のスタメン</p><br/>"
            "<span>4吉川 7キャベッジ 9丸 5ダルベック 2大城 3増田 8平山 6浦田 1森田</span>"
        )
        result = parse_hochi_compact_lineup(
            title=text, summary=text, source_name="スポーツ報知巨人班X"
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result["lineup"]), 9)

    def test_full_width_digits_normalised(self):
        text = "本日のスタメン ４吉川 ７キャベッジ ９丸 ５ダルベック ２大城 ３増田 ８平山 ６浦田 １森田"
        result = parse_hochi_compact_lineup(
            title=text, summary=text, source_name="スポーツ報知巨人班X"
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result["lineup"]), 9)
        # NFKC normalised the full-width digit, so position mapping works.
        self.assertEqual(result["lineup"][0]["position"], "二")
        self.assertEqual(result["lineup"][0]["name"], "吉川")

    def test_url_only_admit_when_name_missing(self):
        """source_name 空でも source_url が hochi なら admit。"""
        result = parse_hochi_compact_lineup(
            title=HOCHI_FIRST_TEAM_SOLO,
            summary=HOCHI_FIRST_TEAM_SOLO,
            source_name="",
            source_url="https://twitter.com/hochi_giants/status/123",
        )
        self.assertIsNotNone(result)

    def test_rows_are_deduped_by_position_and_name(self):
        """同一 (position, name) は重複しない。異なる name は同 position でも残る。"""
        # title==summary で同じ lineup が 2 回出現
        text = "本日のスタメン 4吉川 7キャベッジ 9丸 5ダルベック 2大城 3増田 8平山 6浦田 1森田"
        result = parse_hochi_compact_lineup(
            title=text, summary=text, source_name="スポーツ報知巨人班X"
        )
        self.assertIsNotNone(result)
        keys = [(r["position"], r["name"]) for r in result["lineup"]]
        self.assertEqual(len(keys), len(set(keys)), "duplicate (position, name) rows present")

    def test_returned_keys_and_types(self):
        result = parse_hochi_compact_lineup(
            title=HOCHI_FIRST_TEAM_SOLO,
            summary=HOCHI_FIRST_TEAM_SOLO,
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(result)
        self.assertIn("lineup", result)
        self.assertIn("keyword", result)
        self.assertIn("raw_position_count", result)
        self.assertIsInstance(result["lineup"], list)
        self.assertIsInstance(result["keyword"], str)
        self.assertIsInstance(result["raw_position_count"], int)
        for row in result["lineup"]:
            self.assertIn("order", row)
            self.assertIn("position", row)
            self.assertIn("name", row)


if __name__ == "__main__":
    unittest.main()
