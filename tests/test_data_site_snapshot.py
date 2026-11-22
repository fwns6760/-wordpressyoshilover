from __future__ import annotations

import sqlite3

from src.data_site_snapshot import build_compact_snapshot


def _source_db(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE games (game_id TEXT PRIMARY KEY, game_date TEXT);
            CREATE TABLE batting_logs (
                game_id TEXT, player_canonical TEXT, team_name TEXT
            );
            CREATE TABLE pitching_logs (
                game_id TEXT, player_canonical TEXT, team_name TEXT
            );
            CREATE TABLE advanced_metric_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT,
                scope TEXT,
                player_canonical TEXT,
                metric_name TEXT,
                metric_value REAL
            );
            CREATE TABLE article_candidates (
                candidate_id INTEGER PRIMARY KEY, body TEXT
            );
            CREATE INDEX idx_snap_scope
                ON advanced_metric_snapshots(scope, snapshot_date);
            """
        )
        conn.execute("INSERT INTO games VALUES ('g-1','2026-07-29')")
        conn.execute("INSERT INTO batting_logs VALUES ('g-1','選手A','巨人')")
        conn.execute("INSERT INTO pitching_logs VALUES ('g-1','投手A','巨人')")
        conn.executemany(
            "INSERT INTO advanced_metric_snapshots "
            "(snapshot_date,scope,player_canonical,metric_name,metric_value) "
            "VALUES (?,?,?,?,?)",
            [
                ("2026-07-28", "season", "選手A", "OPS", 0.8),
                ("2026-07-29", "season", "選手A", "OPS", 0.9),
                ("2026-07-28", "last_5_games", "選手A", "OPS", 1.0),
                ("2026-07-29", "last_5_games", "選手A", "OPS", 1.1),
            ],
        )
        conn.executemany(
            "INSERT INTO article_candidates VALUES (?,?)",
            [(n, "x" * 2_000) for n in range(200)],
        )


def test_build_compact_snapshot_excludes_candidates_and_old_metrics(tmp_path):
    source = tmp_path / "insight.db"
    target = tmp_path / "data_site.db"
    _source_db(source)

    summary = build_compact_snapshot(source, target)

    assert summary["latest_game_date"] == "2026-07-29"
    assert summary["target_size"] < summary["source_size"]
    with sqlite3.connect(target) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "article_candidates" not in tables
        assert "games" in tables
        assert conn.execute(
            "SELECT COUNT(*) FROM advanced_metric_snapshots"
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM advanced_metric_snapshots "
            "WHERE snapshot_date='2026-07-28'"
        ).fetchone()[0] == 0
