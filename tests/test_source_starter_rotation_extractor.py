"""Unit tests for ``src/source_starter_rotation_extractor.py``.

NOMOTOKE-LINEUP-FROM-STARTER-ROTATION-001 Phase 2C regression coverage.
"""

from __future__ import annotations

import unittest

from src.source_starter_rotation_extractor import (
    STARTER_ROTATION_SOURCE_NAMES,
    is_starter_rotation_source,
    parse_starter_rotation,
)


# Production-shaped fixture (verified 2026-05-12 against id=66418).
ROTATION_TITLE = (
    "巨人が先発ローテ再編　１５日からのＤｅＮＡ３連戦は"
    "井上温大→ウィットリー→竹丸和幸　フレッシュ布陣で貯金アップ"
)


class IsStarterRotationSourceTests(unittest.TestCase):
    def test_known_names_recognised(self):
        for name in STARTER_ROTATION_SOURCE_NAMES:
            with self.subTest(name=name):
                self.assertTrue(is_starter_rotation_source(source_name=name))

    def test_substring_match_for_japanese_aliases(self):
        self.assertTrue(is_starter_rotation_source(source_name="スポーツ報知 巨人 編集部"))
        self.assertTrue(is_starter_rotation_source(source_name="スポニチ大阪本社"))
        self.assertTrue(is_starter_rotation_source(source_name="巨人公式 / 巨人公式X"))

    def test_url_substring_match(self):
        self.assertTrue(
            is_starter_rotation_source(
                source_name="",
                source_url="https://hochi.news/articles/20260511.html",
            )
        )
        self.assertTrue(
            is_starter_rotation_source(
                source_name="",
                source_url="https://twitter.com/TokyoGiants/status/123",
            )
        )

    def test_unknown_sources_rejected(self):
        self.assertFalse(is_starter_rotation_source(source_name="Yahoo!プロ野球"))
        self.assertFalse(is_starter_rotation_source(source_name=""))


class ParseStarterRotationTests(unittest.TestCase):
    def test_production_fixture_extracts_three_pitchers(self):
        r = parse_starter_rotation(
            title=ROTATION_TITLE,
            summary=ROTATION_TITLE,
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        names = [row["pitcher"] for row in r["rotation"]]
        self.assertEqual(names, ["井上温大", "ウィットリー", "竹丸和幸"])
        self.assertEqual(r["raw_chain_length"], 3)
        self.assertEqual(r["keyword"], "先発ローテ")

    def test_no_arrow_chain_returns_none(self):
        r = parse_starter_rotation(
            title="巨人・吉川尚輝が逆転打 主将らしい一打で延長制す",
            summary="巨人の吉川尚輝が延長戦で逆転打を放った。",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNone(r)

    def test_no_rotation_keyword_returns_none(self):
        """arrow chain あるが ローテ keyword 無し → None。"""
        r = parse_starter_rotation(
            title="巨人 逆転2点三塁打→ダメ押し2点二塁打 浦田大爆発",
            summary="巨人 逆転2点三塁打→ダメ押し2点二塁打 浦田大爆発",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNone(r)

    def test_no_giants_pitcher_returns_none(self):
        """ローテ keyword + arrow chain あるが 巨人 roster 0 マッチ → None。"""
        r = parse_starter_rotation(
            title="セ・リーグ予告先発 中日: 高橋宏斗→大野雄大→金丸夢斗",
            summary="セ・リーグ予告先発 中日: 高橋宏斗→大野雄大→金丸夢斗",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNone(r)

    def test_non_allowed_source_returns_none(self):
        r = parse_starter_rotation(
            title=ROTATION_TITLE,
            summary=ROTATION_TITLE,
            source_name="Yahoo!プロ野球",
        )
        self.assertIsNone(r)

    def test_two_pitcher_chain_accepted(self):
        """2 投手 chain でも MIN_ROTATION_LEN を満たせば accept。"""
        r = parse_starter_rotation(
            title="巨人 予告先発 戸郷翔征→田中将大 連勝へ",
            summary="巨人 予告先発 戸郷翔征→田中将大 連勝へ",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        names = [row["pitcher"] for row in r["rotation"]]
        self.assertEqual(len(names), 2)

    def test_empty_input_returns_none(self):
        self.assertIsNone(parse_starter_rotation("", "", "スポーツ報知 巨人 tag"))

    def test_returned_keys_and_types(self):
        r = parse_starter_rotation(
            title=ROTATION_TITLE,
            summary=ROTATION_TITLE,
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        self.assertIn("rotation", r)
        self.assertIn("keyword", r)
        self.assertIn("raw_chain_length", r)
        self.assertIn("opponent_team_name", r)
        for row in r["rotation"]:
            self.assertEqual(set(row.keys()), {"order", "pitcher"})


if __name__ == "__main__":
    unittest.main()
