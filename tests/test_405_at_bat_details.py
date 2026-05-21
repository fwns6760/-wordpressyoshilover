"""Tests for 405 / 415 (b) Phase 2a-3a: at_bat_details schema + ingest + 走者状況別 aggregator.

Phase 2a: data/insight/schema.sql に at_bat_details 追加
Phase 2b: src/analysis/insight_etl.py upsert_at_bat_details
Phase 3a: src/analysis/ranking_article_publisher.py
          aggregate_giants_batter_runner_state / runner_state_label
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis.ranking_article_publisher import (  # noqa: E402
    aggregate_giants_batter_runner_state,
    runner_state_label,
)


SCHEMA_PATH = ROOT / "data" / "insight" / "schema.sql"


def _open_seeded_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


class AtBatDetailsSchemaTests(unittest.TestCase):
    def test_table_and_indexes_exist(self):
        conn = _open_seeded_db()
        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='at_bat_details'"
        )
        self.assertIsNotNone(cur.fetchone())
        # 16 columns
        cols = conn.execute("PRAGMA table_info(at_bat_details)").fetchall()
        self.assertEqual(len(cols), 16)
        col_names = {c[1] for c in cols}
        for expected in (
            "game_id", "inning_no", "half", "team", "pa_index",
            "outs", "runner_state", "batter", "count_balls",
            "count_strikes", "result_text", "current_pitcher",
        ):
            self.assertIn(expected, col_names)
        # 4 indexes
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='at_bat_details' AND name LIKE 'idx_pa_%'"
        ).fetchall()
        self.assertGreaterEqual(len(idx), 4)


class ParseRbiFromResultTextTests(unittest.TestCase):
    def test_parses_rbi_from_homerun_annotation(self):
        self.assertEqual(
            insight_etl.parse_rbi_from_result_text("左中間ソロホームラン（打点1）"),
            1,
        )

    def test_parses_rbi_from_timely_double(self):
        self.assertEqual(
            insight_etl.parse_rbi_from_result_text("中前タイムリーツーベース（打点2）"),
            2,
        )

    def test_parses_grand_slam(self):
        self.assertEqual(
            insight_etl.parse_rbi_from_result_text("右翼席満塁ホームラン（打点4）"),
            4,
        )

    def test_returns_zero_for_non_rbi_play(self):
        self.assertEqual(insight_etl.parse_rbi_from_result_text("空振り三振"), 0)
        self.assertEqual(insight_etl.parse_rbi_from_result_text("投ゴロ"), 0)

    def test_returns_zero_for_empty(self):
        self.assertEqual(insight_etl.parse_rbi_from_result_text(""), 0)
        self.assertEqual(insight_etl.parse_rbi_from_result_text(None), 0)


class UpsertAtBatDetailsTests(unittest.TestCase):
    def _seed_game(self, conn: sqlite3.Connection, game_id: str, date: str):
        conn.execute(
            "INSERT INTO games (game_id, game_date, opponent, home_away, "
            "giants_score, opp_score, result, source_url, source_kind, "
            "ingested_at) VALUES (?, ?, 'ヤクルト', 'home', 5, 3, '勝利', '', "
            "'test', '2026-05-19T22:00:00Z')",
            (game_id, date),
        )

    def test_upsert_inserts_pa_rows_with_pa_index_assigned(self):
        conn = _open_seeded_db()
        self._seed_game(conn, "2026-05-19:s-g-10", "2026-05-19")
        events = [
            {"inning_no": 1, "half": "裏", "team": "巨人", "outs": "0アウト",
             "runner_state": "", "batter": "吉川", "count_balls": 0,
             "count_strikes": 0, "result": "中前安打", "current_pitcher": "小川"},
            {"inning_no": 1, "half": "裏", "team": "巨人", "outs": "0アウト",
             "runner_state": "1塁", "batter": "岡本", "count_balls": 3,
             "count_strikes": 2, "result": "左中間ソロホームラン（打点2）",
             "current_pitcher": "小川"},
        ]
        n = insight_etl.upsert_at_bat_details(
            conn, game_id="2026-05-19:s-g-10",
            source_url="https://npb.jp/scores/2026/0519/s-g-10/playbyplay.html",
            events=events,
            ingested_at="2026-05-19T22:30:00Z",
        )
        self.assertEqual(n, 2)
        rows = conn.execute(
            "SELECT pa_index, batter, runner_state, current_pitcher "
            "FROM at_bat_details ORDER BY pa_index"
        ).fetchall()
        self.assertEqual(rows[0], (0, "吉川", "", "小川"))
        self.assertEqual(rows[1], (1, "岡本", "1塁", "小川"))

    def test_upsert_is_idempotent_via_primary_key(self):
        conn = _open_seeded_db()
        self._seed_game(conn, "2026-05-19:s-g-10", "2026-05-19")
        events = [
            {"inning_no": 1, "half": "裏", "team": "巨人", "outs": "0アウト",
             "runner_state": "", "batter": "吉川", "count_balls": 0,
             "count_strikes": 0, "result": "中前安打", "current_pitcher": "小川"},
        ]
        insight_etl.upsert_at_bat_details(
            conn, game_id="2026-05-19:s-g-10",
            source_url="https://npb.jp/scores/2026/0519/s-g-10/playbyplay.html",
            events=events,
            ingested_at="2026-05-19T22:30:00Z",
        )
        # second upsert with same events
        insight_etl.upsert_at_bat_details(
            conn, game_id="2026-05-19:s-g-10",
            source_url="https://npb.jp/scores/2026/0519/s-g-10/playbyplay.html",
            events=events,
            ingested_at="2026-05-19T23:00:00Z",
        )
        count = conn.execute("SELECT COUNT(*) FROM at_bat_details").fetchone()[0]
        self.assertEqual(count, 1, "PK (game_id, inning_no, half, pa_index) で重複なし")

    def test_upsert_empty_events_returns_zero(self):
        conn = _open_seeded_db()
        n = insight_etl.upsert_at_bat_details(
            conn, game_id="2026-05-19:s-g-10",
            source_url="", events=[],
            ingested_at="2026-05-19T22:00:00Z",
        )
        self.assertEqual(n, 0)


class AggregateGiantsBatterRunnerStateTests(unittest.TestCase):
    def _seed_game(self, conn: sqlite3.Connection, game_id: str, date: str):
        conn.execute(
            "INSERT INTO games (game_id, game_date, opponent, home_away, "
            "giants_score, opp_score, result, source_url, source_kind, "
            "ingested_at) VALUES (?, ?, 'ヤクルト', 'home', 5, 3, '勝利', '', "
            "'test', '2026-05-19T22:00:00Z')",
            (game_id, date),
        )

    def test_aggregate_basics(self):
        conn = _open_seeded_db()
        self._seed_game(conn, "2026-05-19:s-g-10", "2026-05-19")
        events = [
            {"inning_no": 1, "half": "裏", "team": "巨人", "outs": "0アウト",
             "runner_state": "満塁", "batter": "岡本", "count_balls": 3,
             "count_strikes": 2, "result": "中前タイムリーツーベース（打点2）",
             "current_pitcher": "小川"},
            {"inning_no": 3, "half": "裏", "team": "巨人", "outs": "1アウト",
             "runner_state": "満塁", "batter": "吉川", "count_balls": 0,
             "count_strikes": 0, "result": "中犠飛（打点1）", "current_pitcher": "小川"},
            {"inning_no": 5, "half": "裏", "team": "巨人", "outs": "2アウト",
             "runner_state": "", "batter": "岡本", "count_balls": 1,
             "count_strikes": 2, "result": "空振り三振", "current_pitcher": "清水"},
        ]
        insight_etl.upsert_at_bat_details(
            conn, game_id="2026-05-19:s-g-10",
            source_url="", events=events,
            ingested_at="2026-05-19T22:30:00Z",
        )
        result = aggregate_giants_batter_runner_state(
            conn, runner_state="満塁", last_n_games=10,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["batter"], "岡本")
        self.assertEqual(result[0]["pa_count"], 1)
        self.assertEqual(result[0]["rbi_sum"], 2)
        self.assertEqual(result[1]["batter"], "吉川")
        self.assertEqual(result[1]["pa_count"], 1)
        self.assertEqual(result[1]["rbi_sum"], 1)

    def test_aggregate_no_runner_state_filters_correctly(self):
        conn = _open_seeded_db()
        self._seed_game(conn, "2026-05-19:s-g-10", "2026-05-19")
        events = [
            {"inning_no": 1, "half": "裏", "team": "巨人", "outs": "0アウト",
             "runner_state": "", "batter": "吉川", "count_balls": 0,
             "count_strikes": 0, "result": "右前安打", "current_pitcher": "小川"},
            {"inning_no": 3, "half": "裏", "team": "巨人", "outs": "0アウト",
             "runner_state": "満塁", "batter": "岡本", "count_balls": 3,
             "count_strikes": 2, "result": "中前安打（打点2）",
             "current_pitcher": "小川"},
        ]
        insight_etl.upsert_at_bat_details(
            conn, game_id="2026-05-19:s-g-10",
            source_url="", events=events,
            ingested_at="2026-05-19T22:30:00Z",
        )
        no_runner = aggregate_giants_batter_runner_state(
            conn, runner_state="", last_n_games=10,
        )
        self.assertEqual(len(no_runner), 1)
        self.assertEqual(no_runner[0]["batter"], "吉川")

    def test_aggregate_returns_empty_when_no_giants_games(self):
        conn = _open_seeded_db()
        # No games seeded
        result = aggregate_giants_batter_runner_state(
            conn, runner_state="満塁", last_n_games=10,
        )
        self.assertEqual(result, [])

    def test_aggregate_filters_non_giants_team(self):
        conn = _open_seeded_db()
        self._seed_game(conn, "2026-05-19:s-g-10", "2026-05-19")
        events = [
            {"inning_no": 1, "half": "表", "team": "ヤクルト", "outs": "0アウト",
             "runner_state": "満塁", "batter": "サンタナ", "count_balls": 0,
             "count_strikes": 0, "result": "中前タイムリー（打点2）",
             "current_pitcher": "戸郷"},
            {"inning_no": 1, "half": "裏", "team": "巨人", "outs": "0アウト",
             "runner_state": "満塁", "batter": "岡本", "count_balls": 1,
             "count_strikes": 1, "result": "中犠飛（打点1）", "current_pitcher": "小川"},
        ]
        insight_etl.upsert_at_bat_details(
            conn, game_id="2026-05-19:s-g-10",
            source_url="", events=events,
            ingested_at="2026-05-19T22:30:00Z",
        )
        result = aggregate_giants_batter_runner_state(
            conn, runner_state="満塁", last_n_games=10,
        )
        # サンタナ (ヤクルト) は除外、 巨人 岡本のみ
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["batter"], "岡本")


class RunnerStateLabelTests(unittest.TestCase):
    def test_known_labels(self):
        self.assertEqual(runner_state_label("満塁"), "満塁")
        self.assertEqual(runner_state_label(""), "無走者")
        self.assertEqual(runner_state_label("1塁"), "1塁")
        self.assertEqual(runner_state_label("1・2塁"), "1・2塁")

    def test_unknown_state_returns_input(self):
        self.assertEqual(runner_state_label("謎"), "謎")

    def test_none_returns_no_runners_label(self):
        # 空文字相当として扱う
        self.assertEqual(runner_state_label(None or ""), "無走者")


if __name__ == "__main__":
    unittest.main()
