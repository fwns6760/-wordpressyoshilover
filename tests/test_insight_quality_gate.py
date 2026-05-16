"""Tests for 356 data-insight publish-time quality gate."""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis import insight_quality_gate as qg  # noqa: E402
from src.analysis import ranking_article_publisher as rap  # noqa: E402
from src.analysis import team_ranking_publisher as trp  # noqa: E402


TODAY = dt.date.today()
TODAY_TEXT = TODAY.isoformat()
YESTERDAY_TEXT = (TODAY - dt.timedelta(days=1)).isoformat()


def _open_db(tmp_path):
    return insight_etl.open_db(db_path=tmp_path / "t.db", schema_path=insight_etl.DEFAULT_SCHEMA)


def _seed_snapshots(conn, *, snapshot_date: str, scope: str, metric: str, ranking):
    for player, team, value, sample, rank, total in ranking:
        conn.execute(
            "INSERT INTO advanced_metric_snapshots "
            "(snapshot_date, scope, player_canonical, team_code, "
            "metric_name, metric_value, sample_size, league_rank, league_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_date, scope, player, team, metric, value, sample, rank, total),
        )
    conn.commit()


def _central_ranking(*, sample: int = 50, total: int = 30):
    return [
        ("巨人A", "g", 0.920, sample, 1, total),
        ("阪神A", "t", 0.910, 50, 2, total),
        ("広島A", "c", 0.900, 50, 3, total),
        ("DeNAA", "db", 0.890, 50, 4, total),
        ("中日A", "d", 0.880, 50, 5, total),
        ("ヤクルトA", "s", 0.870, 50, 6, total),
    ]


def _seed_game(conn, *, game_id: str, game_date: str = TODAY_TEXT):
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', ?)",
        (game_id, game_date, f"{game_date}T00:00:00Z"),
    )


def _seed_team_avg_row(conn, *, team_name: str, ab: int, h: int):
    game_id = f"team-{team_name}"
    _seed_game(conn, game_id=game_id)
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, "
        "position, player_display, player_canonical, is_sub, AB, R, "
        "H, RBI, SB, atbats_json, team_name) "
        "VALUES (?, 'home', 1, '中', ?, ?, 0, ?, 0, ?, 0, 0, '[]', ?)",
        (game_id, team_name, team_name, ab, h, team_name),
    )


def test_body_evidence_missing_formula_is_blocked():
    decision = qg.validate_body_evidence(
        "| データ元 | NPB 公式 |\n| 集計期間 | 今日 |\n| 比較 | セ・リーグ |",
        require_sample=False,
        require_comparison=True,
    )
    assert decision.allowed is False
    assert decision.status == qg.STATUS_EVIDENCE
    assert "formula" in decision.details["missing"]


def test_publish_ranking_skips_insufficient_focus_sample(tmp_path):
    conn = _open_db(tmp_path)
    try:
        _seed_snapshots(
            conn,
            snapshot_date=TODAY_TEXT,
            scope="last_30d",
            metric="OPS",
            ranking=_central_ranking(sample=5),
        )
        wp_mock = MagicMock()
        result = rap.publish_giants_centric_ranking_draft(
            conn,
            wp_mock,
            metric_name="OPS",
            scope="last_30d",
            snapshot_date=TODAY_TEXT,
        )
        assert result["status"] == qg.STATUS_SAMPLE
        assert result["reason"] == "insufficient_sample"
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()


def test_publish_ranking_skips_insufficient_team_coverage(tmp_path):
    conn = _open_db(tmp_path)
    try:
        _seed_snapshots(
            conn,
            snapshot_date=TODAY_TEXT,
            scope="last_30d",
            metric="OPS",
            ranking=_central_ranking()[:4],
        )
        wp_mock = MagicMock()
        result = rap.publish_giants_centric_ranking_draft(
            conn,
            wp_mock,
            metric_name="OPS",
            scope="last_30d",
            snapshot_date=TODAY_TEXT,
        )
        assert result["status"] == qg.STATUS_COVERAGE
        assert result["reason"] == "insufficient_team_coverage"
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()


def test_publish_ranking_skips_not_latest_snapshot(tmp_path):
    conn = _open_db(tmp_path)
    try:
        _seed_snapshots(
            conn,
            snapshot_date=YESTERDAY_TEXT,
            scope="last_30d",
            metric="OPS",
            ranking=_central_ranking(sample=50),
        )
        _seed_snapshots(
            conn,
            snapshot_date=TODAY_TEXT,
            scope="last_30d",
            metric="OPS",
            ranking=_central_ranking(sample=50),
        )
        wp_mock = MagicMock()
        result = rap.publish_giants_centric_ranking_draft(
            conn,
            wp_mock,
            metric_name="OPS",
            scope="last_30d",
            snapshot_date=YESTERDAY_TEXT,
        )
        assert result["status"] == qg.STATUS_STALE
        assert result["reason"] == "not_latest_snapshot"
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()


def test_publish_team_metric_skips_when_not_all_central_teams_present(tmp_path):
    conn = _open_db(tmp_path)
    try:
        for team, ab, h in [
            ("巨人", 100, 31),
            ("阪神", 100, 30),
            ("広島", 100, 29),
            ("DeNA", 100, 28),
        ]:
            _seed_team_avg_row(conn, team_name=team, ab=ab, h=h)
        conn.commit()
        wp_mock = MagicMock()
        result = trp.publish_team_metric_draft(
            conn,
            wp_mock,
            metric="AVG",
            scope="season",
        )
        assert result["status"] == qg.STATUS_COVERAGE
        assert result["reason"] == "insufficient_team_coverage"
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()
