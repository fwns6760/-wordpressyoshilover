"""Tests for data_site_query venue split (ticket 447 Phase 1.0c venue)."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest

from src.data_site_query import (
    giants_venue_from_game_id,
    fetch_inning_split_stats,
    _classify_atbat,
)


class GiantsVenueFromGameIdTests(unittest.TestCase):
    """game_id (NPB.jp box score code `{home}-{away}-{no}`) → 巨人視点 home/away。"""

    def test_giants_home_left_code(self) -> None:
        # 巨人 code 'g' が左 (home) = 本拠地
        self.assertEqual(giants_venue_from_game_id("2026-03-27:g-t-01"), "home")
        self.assertEqual(giants_venue_from_game_id("2026-04-03:g-db-01"), "home")

    def test_giants_away_right_code(self) -> None:
        # 巨人 code 'g' が右 (away) = ビジター
        self.assertEqual(giants_venue_from_game_id("2026-03-31:d-g-01"), "away")
        self.assertEqual(giants_venue_from_game_id("2026-04-07:c-g-01"), "away")

    def test_non_giants_game_returns_none(self) -> None:
        # 巨人が含まれない試合 (リーグ全体 ingest 分) は None
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:db-s-01"))
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:c-d-01"))

    def test_malformed_returns_none(self) -> None:
        self.assertIsNone(giants_venue_from_game_id(""))
        self.assertIsNone(giants_venue_from_game_id("no-colon-here"))
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:g"))


class ClassifyAtbatTests(unittest.TestCase):
    """NPB box score 打席結果 → (is_ab, is_hit) 分類 (metric pack #5 inning)。"""

    def test_hits(self) -> None:
        for cell in ["右前安", "中前安", "遊安", "投安"]:  # 単打
            self.assertEqual(_classify_atbat(cell), (True, True), cell)
        for cell in ["右越本", "左中本①", "中越本"]:  # 本塁打 (circled num 付き含む)
            self.assertEqual(_classify_atbat(cell), (True, True), cell)
        for cell in ["左線２", "右中２", "左越２"]:  # 二塁打
            self.assertEqual(_classify_atbat(cell), (True, True), cell)

    def test_outs_are_ab_not_hit(self) -> None:
        for cell in ["三 振", "二ゴロ", "遊ゴロ", "中飛", "左飛", "三邪飛",
                     "遊併打", "二直", "三ゴ失", "遊ゴ失"]:
            self.assertEqual(_classify_atbat(cell), (True, False), cell)

    def test_non_ab_outcomes(self) -> None:
        for cell in ["四 球", "敬遠四", "死球", "投犠打", "中犠飛", "一犠打"]:
            self.assertEqual(_classify_atbat(cell), (False, False), cell)

    def test_empty_and_dash(self) -> None:
        self.assertEqual(_classify_atbat("-"), (False, False))
        self.assertEqual(_classify_atbat(""), (False, False))
        self.assertEqual(_classify_atbat("   "), (False, False))


class FetchInningSplitStatsTests(unittest.TestCase):
    """batting_logs.atbats_json (index=イニング) → 序盤/中盤/終盤 集計。"""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.execute(
            "CREATE TABLE batting_logs (player_canonical TEXT, atbats_json TEXT)"
        )
        # 2 試合分。 序盤(idx0-2) 中盤(idx3-5) 終盤(idx6-8)。
        games = [
            # game1: 1回 安 / 4回 三振 / 7回 二塁打 / 9回 四球
            ["右前安", "-", "-", "三振", "-", "-", "左線２", "-", "四球"],
            # game2: 2回 ゴロ / 5回 安 / 8回 本塁打
            ["-", "遊ゴロ", "-", "-", "中前安", "-", "-", "右越本", "-"],
        ]
        for g in games:
            conn.execute(
                "INSERT INTO batting_logs VALUES (?, ?)",
                ("吉川尚輝", json.dumps(g, ensure_ascii=False)),
            )
        conn.commit()
        conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_buckets_and_avg(self) -> None:
        stats = {s.phase: s for s in fetch_inning_split_stats("吉川尚輝")}
        # 序盤: 安 + ゴロ = 2 AB, 1 H
        self.assertEqual((stats["序盤"].ab, stats["序盤"].hits), (2, 1))
        # 中盤: 三振 + 安 = 2 AB, 1 H
        self.assertEqual((stats["中盤"].ab, stats["中盤"].hits), (2, 1))
        # 終盤: 二塁打 + 本塁打 = 2 AB, 2 H (四球は非 AB)
        self.assertEqual((stats["終盤"].ab, stats["終盤"].hits), (2, 2))
        self.assertAlmostEqual(stats["終盤"].avg, 1.0)

    def test_unknown_player_empty(self) -> None:
        self.assertEqual(fetch_inning_split_stats("存在しない選手"), [])


if __name__ == "__main__":
    unittest.main()
