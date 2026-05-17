"""Tests for issue #44 A: milestone 記事の body に他チーム選手込み ranking 表を入れる.

Bug: ``render_milestone_crossed_article`` の lower_is_better milestone path
は ``_render_simple_data_article`` を呼んで 1 選手分の data sheet table
(項目 / 数値) しか出さない。 他チーム選手の ranking が見えず、 user 不満:
「則本の記事には表が無い、 他チーム選手も入れて」(2026-05-17 lock)。

Fix: milestone 記事の body に「## データ」section の ranking 表として
セ・リーグ規定到達者 top 10 + (focal 選手が圏外なら) 周辺 ranks を含める。
focal 選手は ★ で赤太字 highlight。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.analysis import anomaly_article_publisher as aap
from src.analysis import insight_etl


REPO = Path(__file__).resolve().parents[1]


def _open_seed_db(tmp_path: Path) -> sqlite3.Connection:
    return insight_etl.open_db(
        db_path=tmp_path / "insight.db",
        schema_path=insight_etl.DEFAULT_SCHEMA,
    )


def _seed_snapshot_rows(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
    scope: str,
    metric_name: str,
    rows: list[tuple[str, str, float, int, int, int]],
) -> None:
    """rows = [(player_canonical, team_code, metric_value, sample_size,
    league_rank, league_total), ...] を直接 insert."""
    insight_etl.seed_teams(conn)
    for player, team, value, sample, rank, total in rows:
        conn.execute(
            "INSERT OR REPLACE INTO players (player_canonical, team_code, active) "
            "VALUES (?, ?, 1)",
            (player, team),
        )
        conn.execute(
            "INSERT INTO advanced_metric_snapshots "
            "(snapshot_date, scope, metric_name, player_canonical, team_code, "
            "metric_value, sample_size, league_rank, league_total) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (snapshot_date, scope, metric_name, player, team,
             value, sample, rank, total),
        )
    conn.commit()


# ─── milestone (lower_is_better = ERA) ───────────────────────────────────────


def test_milestone_era_article_includes_ranking_table_with_other_teams(tmp_path):
    """高梨雄平 ERA milestone 記事に セ ERA top 10 (他チーム選手込み) の
    ranking 表が含まれること.
    """
    conn = _open_seed_db(tmp_path)
    try:
        # セ ERA season 規定到達者 12 人を seed (5/17 時点想定値ベース)
        ranking_rows = [
            ("髙橋遥人", "t", 0.375, 48, 1, 12),
            ("栗林良吏", "c", 0.777, 46, 2, 12),
            ("大野雄大", "d", 1.174, 46, 3, 12),
            ("東克樹", "db", 1.636, 44, 4, 12),
            ("柳裕也", "d", 2.104, 51, 5, 12),
            ("村上頌樹", "t", 2.180, 53, 6, 12),
            ("山野太一", "s", 2.267, 43, 7, 12),
            ("大竹寛", "t", 2.357, 42, 8, 12),
            ("金丸夢斗", "d", 2.436, 44, 9, 12),
            ("高梨雄平", "g", 2.600, 44, 10, 12),  # focal
            ("床田寛樹", "c", 3.108, 46, 11, 12),
            ("才木浩人", "t", 3.293, 41, 12, 12),
        ]
        _seed_snapshot_rows(
            conn, snapshot_date="2026-05-17", scope="season",
            metric_name="ERA", rows=ranking_rows,
        )

        candidate = {
            "candidate_id": 99999,
            "signal_type": "anomaly_milestone_crossed",
            "player_canonical": "高梨雄平",
            "notes": "metric=ERA threshold=3.0 value=2.600",
        }
        article = aap.render_milestone_crossed_article(conn, candidate)
        body = article["body_md"]

        # ranking 表ヘッダーが存在
        assert "| 順位 | 選手 | チーム |" in body, (
            f"ranking 表 header が無い: body=\n{body}"
        )
        # 複数行 (top 10 想定なので 5 行以上は最低)
        # ranking table の行数を粗 count
        ranking_rows_in_body = [
            l for l in body.split("\n")
            if l.startswith("|") and "順位" not in l and "---" not in l
        ]
        # 「## データ」と「## このデータについて」両方が table を出すので、
        # 単純な行 count は使えない。 ranking table の特徴 (1 行目に "1 |"
        # を含む) で判定
        ranking_data_rows = [
            l for l in body.split("\n")
            if l.startswith("|") and l.replace(" ", "").startswith("|1|")
        ]
        assert ranking_data_rows, f"ranking table 1 位行が無い: body=\n{body}"

        # 他チーム選手 (髙橋遥人 = 阪神) が body に含まれる
        assert "髙橋遥人" in body, "他チーム選手 (髙橋遥人) が ranking 表に無い"
        # 高梨が ranking 表に含まれる
        assert "高梨雄平" in body
    finally:
        conn.close()


def test_milestone_focal_player_highlighted_in_ranking_table(tmp_path):
    """focal 選手 (ranking 内) が ★ + 赤太字 で highlight される."""
    conn = _open_seed_db(tmp_path)
    try:
        ranking_rows = [
            ("髙橋遥人", "t", 0.375, 48, 1, 12),
            ("高梨雄平", "g", 2.600, 44, 10, 12),
        ]
        _seed_snapshot_rows(
            conn, snapshot_date="2026-05-17", scope="season",
            metric_name="ERA", rows=ranking_rows,
        )
        candidate = {
            "candidate_id": 99998,
            "signal_type": "anomaly_milestone_crossed",
            "player_canonical": "高梨雄平",
            "notes": "metric=ERA threshold=3.0 value=2.600",
        }
        article = aap.render_milestone_crossed_article(conn, candidate)
        body = article["body_md"]
        # 高梨雄平 の行は ★ marker を含む
        assert "高梨雄平 ★" in body or "高梨雄平★" in body, (
            f"focal 高梨雄平 が ★ で highlight されていない: body=\n{body}"
        )
        # 赤太字 wrapper
        assert "color:#c0392b" in body, "赤太字 wrapper が無い"
    finally:
        conn.close()
