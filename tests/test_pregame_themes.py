"""414 axis E tests: 試合前 7 テーマ自動セット."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from src.analysis.pregame_themes import (
    build_pregame_themes,
    format_pregame_themes_for_prompt,
)


JST = timezone(timedelta(hours=9))


class BuildPregameThemesTests(unittest.TestCase):
    def _seed_yesterday_game(self, db_path: str, yesterday: str) -> None:
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            cur.execute(
                "CREATE TABLE games ("
                "game_id TEXT PRIMARY KEY, game_date TEXT NOT NULL, opponent TEXT, "
                "home_away TEXT, giants_score INTEGER, opp_score INTEGER, "
                "result TEXT, league_label TEXT, one_line_summary TEXT, "
                "winning_pitcher TEXT, losing_pitcher TEXT, save_pitcher TEXT, "
                "source_url TEXT, source_kind TEXT, ingested_at TEXT NOT NULL)"
            )
            cur.execute(
                "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("g1", yesterday, "DeNA", "home", 5, 4, "win", "セ", "サヨナラ勝ち",
                 "戸郷", None, "大勢", "", "npb_box", "2026-05-20T22:00:00"),
            )
            con.commit()
        finally:
            con.close()

    def test_yesterday_summary_filled_when_db_has_game(self) -> None:
        from datetime import datetime as _dt
        now = _dt(2026, 5, 20, 15, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_yesterday_game(db, "2026-05-19")
            themes = build_pregame_themes(db, now_jst=now)
            self.assertIn("巨人 vs DeNA", themes["yesterday_summary"])
            self.assertIn("5-4", themes["yesterday_summary"])
            self.assertIn("勝利", themes["yesterday_summary"])
            self.assertIn("勝: 戸郷", themes["yesterday_summary"])

    def test_yesterday_summary_empty_when_no_game(self) -> None:
        from datetime import datetime as _dt
        now = _dt(2026, 5, 20, 15, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_yesterday_game(db, "2026-04-01")  # 違う日
            themes = build_pregame_themes(db, now_jst=now)
            self.assertEqual(themes["yesterday_summary"], "")

    def test_caller_supplied_themes_passed_through(self) -> None:
        from datetime import datetime as _dt
        now = _dt(2026, 5, 20, 15, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            themes = build_pregame_themes(
                db,
                now_jst=now,
                starting_pitcher_today="戸郷翔征",
                focused_players=["岡本和真", "坂本勇人"],
                lineup_change_summary="3番に泉口",
                promotion_summary="松浦慶斗 昇格",
                fan_voice_snippet="戸郷さんに期待",
            )
            self.assertEqual(themes["starting_pitcher"], "戸郷翔征")
            self.assertEqual(themes["focused_players"], "岡本和真, 坂本勇人")
            self.assertEqual(themes["lineup_change"], "3番に泉口")
            self.assertEqual(themes["promotion"], "松浦慶斗 昇格")
            self.assertEqual(themes["fan_voice"], "戸郷さんに期待")

    def test_empty_db_path_returns_themes_with_empty_db_fields(self) -> None:
        from datetime import datetime as _dt
        now = _dt(2026, 5, 20, 15, 0, tzinfo=JST)
        themes = build_pregame_themes("", now_jst=now, starting_pitcher_today="戸郷")
        self.assertEqual(themes["yesterday_summary"], "")
        self.assertEqual(themes["opponent_matchup"], "")
        self.assertEqual(themes["starting_pitcher"], "戸郷")

    def test_opponent_matchup_empty_when_no_pitcher_specified(self) -> None:
        from datetime import datetime as _dt
        now = _dt(2026, 5, 20, 15, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            themes = build_pregame_themes(db, now_jst=now)
            self.assertEqual(themes["opponent_matchup"], "")


class FormatPregameThemesForPromptTests(unittest.TestCase):
    def test_returns_empty_when_all_empty(self) -> None:
        result = format_pregame_themes_for_prompt(
            {"starting_pitcher": "", "yesterday_summary": ""}
        )
        self.assertEqual(result, "")

    def test_includes_header_and_filled_themes(self) -> None:
        themes = {
            "starting_pitcher": "戸郷翔征",
            "yesterday_summary": "昨日 (2026-05-19) 巨人 vs DeNA 5-4 (勝利)",
            "focused_players": "岡本和真",
            "lineup_change": "",
            "promotion": "",
            "opponent_matchup": "",
            "fan_voice": "",
        }
        result = format_pregame_themes_for_prompt(themes)
        self.assertIn("【今日の注目テーマ", result)
        self.assertIn("今日の先発: 戸郷翔征", result)
        self.assertIn("昨日の流れ:", result)
        self.assertIn("注目選手: 岡本和真", result)
        self.assertNotIn("打順変更:", result)  # 空 entry は skip

    def test_skips_empty_entries(self) -> None:
        themes = {
            "starting_pitcher": "戸郷",
            "yesterday_summary": "",
            "focused_players": "",
            "lineup_change": "3番に泉口",
            "promotion": "",
            "opponent_matchup": "",
            "fan_voice": "",
        }
        result = format_pregame_themes_for_prompt(themes)
        self.assertIn("今日の先発: 戸郷", result)
        self.assertIn("打順変更: 3番に泉口", result)
        # skip された keys
        self.assertNotIn("昨日の流れ:", result)
        self.assertNotIn("注目選手:", result)


if __name__ == "__main__":
    unittest.main()
