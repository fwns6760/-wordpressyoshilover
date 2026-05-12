"""Unit tests for ``src/source_postgame_extractor.py``.

NOMOTOKE-LINEUP-FROM-POSTGAME-001 Phase 2D-A regression coverage.
"""

from __future__ import annotations

import unittest

from src.source_postgame_extractor import (
    POSTGAME_SOURCE_NAMES,
    is_postgame_source,
    parse_postgame_facts,
)


FARM_TITLE = "【巨人】\"スミ１\"の完封勝利で貯金６　又木鉄平が５回無失点で３勝目…２軍・ＤｅＮＡ戦"
FARM_SUMMARY = "巨人２軍はＤｅＮＡに１―０で勝利した。又木鉄平が５回無失点で３勝目を挙げた。"

FIRST_TITLE = "【巨人】戸郷翔征が８回１失点の力投で４勝目　巨人が中日に５―１で快勝"
FIRST_SUMMARY = "巨人は中日に５―１で勝利した。戸郷翔征が８回１失点で４勝目を挙げ、エースの仕事を果たした。"


class IsPostgameSourceTests(unittest.TestCase):
    def test_known_names_recognised(self):
        for name in POSTGAME_SOURCE_NAMES:
            with self.subTest(name=name):
                self.assertTrue(is_postgame_source(source_name=name))

    def test_substring_match(self):
        self.assertTrue(is_postgame_source(source_name="スポーツ報知 巨人 編集部"))
        self.assertTrue(is_postgame_source(source_name="スポニチ大阪本社"))
        self.assertTrue(is_postgame_source(source_name="巨人公式 / 巨人公式X"))

    def test_url_substring(self):
        self.assertTrue(
            is_postgame_source(
                source_name="",
                source_url="https://hochi.news/articles/20260512.html",
            )
        )

    def test_unknown_rejected(self):
        self.assertFalse(is_postgame_source(source_name="Yahoo!プロ野球"))
        self.assertFalse(is_postgame_source(source_name=""))


class ParsePostgameFactsTests(unittest.TestCase):
    def test_farm_fixture(self):
        r = parse_postgame_facts(
            title=FARM_TITLE,
            summary=FARM_SUMMARY,
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        self.assertEqual(r["score"], "1-0")
        self.assertEqual(r["winning_pitcher"], "又木鉄平")
        self.assertEqual(r["result_type"], "勝利")
        self.assertEqual(r["league_level"], "farm")
        self.assertEqual(r["opponent_team_name"], "DeNA")

    def test_first_team_fixture(self):
        r = parse_postgame_facts(
            title=FIRST_TITLE,
            summary=FIRST_SUMMARY,
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        self.assertEqual(r["score"], "5-1")
        self.assertEqual(r["winning_pitcher"], "戸郷翔征")
        self.assertEqual(r["league_level"], "first")

    def test_no_result_keyword_returns_none(self):
        r = parse_postgame_facts(
            title="巨人・吉川尚輝が主将としての成長語る",
            summary="巨人の吉川尚輝が主将としての心構えを語った。",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNone(r)

    def test_no_score_returns_none(self):
        """勝利 keyword あるが score 無し → None。"""
        r = parse_postgame_facts(
            title="巨人 又木鉄平が勝利の感想語る",
            summary="巨人の又木鉄平が試合後に勝利の感想を語った。",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNone(r)

    def test_non_giants_postgame_returns_none(self):
        """巨人 mention 無し → None(他球団 postgame 除外)。"""
        r = parse_postgame_facts(
            title="中日が阪神に3-1で勝利",
            summary="中日が阪神に3-1で勝利した。柳裕也が好投。",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNone(r)

    def test_non_allowed_source_returns_none(self):
        r = parse_postgame_facts(
            title=FIRST_TITLE,
            summary=FIRST_SUMMARY,
            source_name="Yahoo!プロ野球",
        )
        self.assertIsNone(r)

    def test_winning_pitcher_outside_roster_yields_empty(self):
        """勝利投手 candidate が roster 不在 → winning_pitcher 空文字、ただし他 facts は返す。"""
        r = parse_postgame_facts(
            title="巨人が広島に7-2で勝利 山田太郎が好投",
            summary="巨人が広島に7-2で勝利した。山田太郎が好投して勝利投手に。",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        self.assertEqual(r["score"], "7-2")
        self.assertEqual(r["winning_pitcher"], "")  # 山田太郎 は roster 不在

    def test_draw_result(self):
        r = parse_postgame_facts(
            title="巨人 - 阪神 3-3で引き分け",
            summary="巨人は阪神と3-3で引き分けた。",
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        self.assertEqual(r["score"], "3-3")
        self.assertEqual(r["result_type"], "引き分け")

    def test_returned_keys(self):
        r = parse_postgame_facts(
            title=FARM_TITLE,
            summary=FARM_SUMMARY,
            source_name="スポーツ報知 巨人 tag",
        )
        self.assertIsNotNone(r)
        self.assertEqual(
            set(r.keys()),
            {"score", "winning_pitcher", "result_type", "league_level", "opponent_team_name"},
        )


if __name__ == "__main__":
    unittest.main()
