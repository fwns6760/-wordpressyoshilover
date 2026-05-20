"""414 axis C8 tests: is_first_team_active helper.

user 報告 「山瀬 (2軍中心) が 1軍 ranking に出る」 への fix を検証。
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from src.analysis.active_roster_filter import (
    filter_first_team_active_players,
    is_first_team_active,
)


JST = timezone(timedelta(hours=9))


class IsFirstTeamActiveTests(unittest.TestCase):
    """直近 14 日で 1軍 games に 3 試合以上出場した player のみ True."""

    def _seed_db(
        self,
        db_path: str,
        *,
        batting_games: list[tuple[str, str]] | None = None,
        pitching_games: list[tuple[str, str]] | None = None,
    ) -> None:
        """batting_games / pitching_games: list of (game_id, game_date YYYY-MM-DD)."""
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS games ("
                "game_id TEXT PRIMARY KEY, game_date TEXT NOT NULL, opponent TEXT, "
                "home_away TEXT, giants_score INTEGER, opp_score INTEGER, "
                "result TEXT, league_label TEXT, one_line_summary TEXT, "
                "winning_pitcher TEXT, losing_pitcher TEXT, save_pitcher TEXT, "
                "source_url TEXT, source_kind TEXT, ingested_at TEXT NOT NULL)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS batting_logs ("
                "game_id TEXT, team_role TEXT, slot_order INTEGER, position TEXT, "
                "player_display TEXT, player_canonical TEXT, is_sub INTEGER, "
                "AB INTEGER, R INTEGER, H INTEGER, RBI INTEGER, SB INTEGER, "
                "atbats_json TEXT, team_name TEXT, "
                "PRIMARY KEY (game_id, team_role, slot_order, player_display))"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS pitching_logs ("
                "game_id TEXT, team_role TEXT, appearance_order INTEGER, "
                "player_display TEXT, player_canonical TEXT, result_mark TEXT, "
                "pitches INTEGER, BF INTEGER, IP REAL, H_allowed INTEGER, "
                "HR_allowed INTEGER, BB INTEGER, HBP INTEGER, K INTEGER, "
                "WP INTEGER, BK INTEGER, R INTEGER, ER INTEGER, team_name TEXT, "
                "PRIMARY KEY (game_id, team_role, appearance_order, player_display))"
            )
            seen_games: set[str] = set()
            for game_id, game_date in (batting_games or []) + (pitching_games or []):
                if game_id in seen_games:
                    continue
                cur.execute(
                    "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (game_id, game_date, "DeNA", "home", 5, 4, "win", "セ", "", "", "", "", "", "npb_box", "2026-05-20T22:00:00"),
                )
                seen_games.add(game_id)
            for i, (game_id, _date) in enumerate(batting_games or []):
                cur.execute(
                    "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
                    "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json, team_name) "
                    "VALUES (?, 'giants', ?, '中', '対象選手', '対象選手', 0, 4, 1, 2, 1, 0, '[]', '巨人')",
                    (game_id, i + 1),
                )
            for i, (game_id, _date) in enumerate(pitching_games or []):
                cur.execute(
                    "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
                    "player_display, player_canonical, result_mark, pitches, BF, IP, "
                    "H_allowed, HR_allowed, BB, HBP, K, WP, BK, R, ER, team_name) "
                    "VALUES (?, 'giants', ?, '対象選手', '対象選手', '勝', 100, 25, 7.0, "
                    "5, 0, 1, 0, 8, 0, 0, 1, 1, '巨人')",
                    (game_id, i + 1),
                )
            con.commit()
        finally:
            con.close()

    def _now(self, days_ago: int = 0) -> datetime:
        return datetime(2026, 5, 20, 19, 0, tzinfo=JST) - timedelta(days=days_ago)

    def test_returns_true_when_batter_played_3_recent_games(self) -> None:
        now = self._now()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(
                db,
                batting_games=[
                    ("g1", "2026-05-18"),
                    ("g2", "2026-05-17"),
                    ("g3", "2026-05-16"),
                ],
            )
            self.assertTrue(
                is_first_team_active("対象選手", db, window_days=14, min_games=3, now_jst=now)
            )

    def test_returns_false_when_only_2_recent_games(self) -> None:
        now = self._now()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(
                db,
                batting_games=[
                    ("g1", "2026-05-18"),
                    ("g2", "2026-05-17"),
                ],
            )
            self.assertFalse(
                is_first_team_active("対象選手", db, window_days=14, min_games=3, now_jst=now)
            )

    def test_returns_false_when_games_older_than_window(self) -> None:
        now = self._now()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            # all games > 14 days ago
            self._seed_db(
                db,
                batting_games=[
                    ("g1", "2026-04-01"),
                    ("g2", "2026-04-02"),
                    ("g3", "2026-04-03"),
                ],
            )
            self.assertFalse(
                is_first_team_active("対象選手", db, window_days=14, min_games=3, now_jst=now)
            )

    def test_returns_true_when_pitcher_played_3_recent_games(self) -> None:
        now = self._now()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(
                db,
                pitching_games=[
                    ("p1", "2026-05-18"),
                    ("p2", "2026-05-17"),
                    ("p3", "2026-05-16"),
                ],
            )
            self.assertTrue(
                is_first_team_active("対象選手", db, window_days=14, min_games=3, now_jst=now)
            )

    def test_returns_true_when_db_path_empty_silent_fallback(self) -> None:
        # silent fallback: filter で消さない = 既存挙動維持
        self.assertTrue(is_first_team_active("対象選手", ""))

    def test_returns_true_when_player_empty(self) -> None:
        self.assertTrue(is_first_team_active("", "/anywhere.db"))

    def test_returns_true_when_db_not_exist_silent_fallback(self) -> None:
        # 例外時 silent fallback
        self.assertTrue(
            is_first_team_active("対象選手", "/nonexistent/db.sqlite")
        )

    def test_other_team_player_does_not_count(self) -> None:
        # team_name != '巨人' は count 外
        now = self._now()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            con = sqlite3.connect(db)
            try:
                cur = con.cursor()
                cur.execute(
                    "CREATE TABLE games (game_id TEXT PRIMARY KEY, game_date TEXT NOT NULL, "
                    "ingested_at TEXT NOT NULL)"
                )
                cur.execute(
                    "CREATE TABLE batting_logs (game_id TEXT, team_role TEXT, slot_order INTEGER, "
                    "player_display TEXT, player_canonical TEXT, team_name TEXT, "
                    "PRIMARY KEY (game_id, team_role, slot_order, player_display))"
                )
                cur.execute(
                    "CREATE TABLE pitching_logs (game_id TEXT, team_role TEXT, appearance_order INTEGER, "
                    "player_display TEXT, player_canonical TEXT, team_name TEXT, "
                    "PRIMARY KEY (game_id, team_role, appearance_order, player_display))"
                )
                for i, date_str in enumerate(["2026-05-18", "2026-05-17", "2026-05-16"]):
                    cur.execute(
                        "INSERT INTO games VALUES (?, ?, ?)",
                        (f"g{i}", date_str, "2026-05-20"),
                    )
                    cur.execute(
                        "INSERT INTO batting_logs VALUES (?, 'opponent', ?, '対象選手', '対象選手', '中日')",
                        (f"g{i}", i + 1),
                    )
                con.commit()
            finally:
                con.close()
            # batting あるが team_name != '巨人' → False
            self.assertFalse(
                is_first_team_active("対象選手", db, window_days=14, min_games=3, now_jst=now)
            )


class FilterFirstTeamActivePlayersTests(unittest.TestCase):
    def test_returns_empty_when_input_empty(self) -> None:
        self.assertEqual(filter_first_team_active_players([], "/anywhere.db"), [])

    def test_preserves_order_for_active_players(self) -> None:
        # silent fallback で全 True、 順序維持
        names = ["A", "B", "C"]
        result = filter_first_team_active_players(names, "")
        self.assertEqual(result, names)


if __name__ == "__main__":
    unittest.main()
