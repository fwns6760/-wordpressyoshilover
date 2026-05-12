"""Unit tests for ``src/source_emoji_lineup_extractor.py``.

NOMOTOKE-LINEUP-FROM-EMOJI-001 Phase 2B regression coverage for the
emoji-form lineup parser used by 巨人公式X 2軍 / sponichi tweets.
"""

from __future__ import annotations

import unittest

from src.source_emoji_lineup_extractor import (
    EMOJI_LINEUP_SOURCE_NAMES,
    is_emoji_lineup_source,
    parse_emoji_lineup,
)


# Production-shaped fixture (verified 2026-05-12 against id=65900).
EMOJI_FARM_LINEUP = (
    "【二軍】巨人 vs ロッテ オーエンススタジアム江戸川🏟️ 13時試合開始⚾ "
    "1️⃣ 三塚(D) 2️⃣ 小濱⑹ 3️⃣ 皆川⑼ 4️⃣ 萩尾⑺ 5️⃣ 荒巻⑶ 6️⃣ 浅野⑻ "
    "7️⃣ 山瀬⑵ 8️⃣ 郡⑸ 9️⃣ 湯浅⑷ 🅿️ マタ"
)


class IsEmojiLineupSourceTests(unittest.TestCase):
    def test_known_names_recognised(self):
        for name in EMOJI_LINEUP_SOURCE_NAMES:
            with self.subTest(name=name):
                self.assertTrue(is_emoji_lineup_source(source_name=name))

    def test_substring_match_for_japanese_aliases(self):
        self.assertTrue(is_emoji_lineup_source(source_name="巨人公式 / 巨人公式X"))
        self.assertTrue(is_emoji_lineup_source(source_name="スポニチ大阪本社"))

    def test_url_substring_match(self):
        self.assertTrue(
            is_emoji_lineup_source(
                source_name="",
                source_url="https://twitter.com/TokyoGiants/status/123",
            )
        )
        self.assertTrue(
            is_emoji_lineup_source(
                source_name="",
                source_url="https://twitter.com/SponichiYakyu/status/123",
            )
        )

    def test_unknown_sources_rejected(self):
        self.assertFalse(is_emoji_lineup_source(source_name="スポーツ報知巨人班X"))
        self.assertFalse(is_emoji_lineup_source(source_name="Yahoo!プロ野球"))
        self.assertFalse(is_emoji_lineup_source(source_name=""))


class ParseEmojiLineupTests(unittest.TestCase):
    def test_emoji_fixture_extracts_ten_rows(self):
        """9 batters + 1 pitcher = 10 rows."""
        result = parse_emoji_lineup(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result["lineup"]), 10)

    def test_position_mapping_complete(self):
        """All 9 defensive positions + DH mapped from circled emoji / paren digits."""
        result = parse_emoji_lineup(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result)
        # Map by name -> position
        by_name = {r["name"]: r["position"] for r in result["lineup"]}
        self.assertEqual(by_name["三塚"], "指")  # (D)
        self.assertEqual(by_name["小濱"], "遊")  # ⑹ -> (6)
        self.assertEqual(by_name["皆川"], "右")  # ⑼ -> (9)
        self.assertEqual(by_name["萩尾"], "左")  # ⑺ -> (7)
        self.assertEqual(by_name["荒巻"], "一")  # ⑶ -> (3)
        self.assertEqual(by_name["浅野"], "中")  # ⑻ -> (8)
        self.assertEqual(by_name["山瀬"], "捕")  # ⑵ -> (2)
        self.assertEqual(by_name["郡"], "三")    # ⑸ -> (5)
        self.assertEqual(by_name["湯浅"], "二")  # ⑷ -> (4)
        self.assertEqual(by_name["マタ"], "投")  # 🅿️

    def test_opponent_team_extracted_from_vs_pattern(self):
        """``巨人 vs ロッテ`` prose form → opponent_team_name = 'ロッテ'."""
        result = parse_emoji_lineup(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["opponent_team_name"], "ロッテ")

    def test_team_field_present_on_each_row(self):
        result = parse_emoji_lineup(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result)
        for row in result["lineup"]:
            self.assertIn("team", row)
            self.assertIn(row["team"], ("巨人", "相手"))

    def test_clean_form_returns_none(self):
        """``1番（中）...`` clean form → defer to source_x_lineup_extractor (return None)."""
        clean = (
            "本日のスタメンが発表されました "
            "1番（中）丸 2番（二）吉川 3番（一）岡本 4番（指）ダルベック "
            "5番（左）キャベッジ 6番（三）増田 7番（右）萩尾 8番（捕）大城 "
            "9番（投）戸郷"
        )
        result = parse_emoji_lineup(
            title=clean, summary=clean, source_name="巨人公式X"
        )
        self.assertIsNone(result)

    def test_non_emoji_source_returns_none(self):
        result = parse_emoji_lineup(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            source_name="スポーツ報知巨人班X",  # hochi family, not emoji
        )
        self.assertIsNone(result)

    def test_empty_input_returns_none(self):
        for value in ("", "  "):
            with self.subTest(value=repr(value)):
                self.assertIsNone(
                    parse_emoji_lineup(
                        title=value, summary=value, source_name="巨人公式X"
                    )
                )

    def test_too_few_keycap_emojis_returns_none(self):
        """Density gate: < 5 distinct keycaps → not a lineup."""
        text = "巨人 vs ロッテ 1️⃣ 三塚 2️⃣ 小濱 (試合は明日)"
        result = parse_emoji_lineup(
            title=text, summary=text, source_name="巨人公式X"
        )
        self.assertIsNone(result)

    def test_returned_keys_and_types(self):
        result = parse_emoji_lineup(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result)
        self.assertIn("lineup", result)
        self.assertIn("keyword", result)
        self.assertIn("raw_position_count", result)
        self.assertIn("opponent_team_name", result)
        for row in result["lineup"]:
            self.assertEqual(set(row.keys()), {"order", "position", "name", "team"})


if __name__ == "__main__":
    unittest.main()
