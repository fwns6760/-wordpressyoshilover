"""Tests for issue #44 B (stat_delta): SIGNAL_STAT_DELTA 記事の本文に
セ・リーグ ranking 表 + title に case A の rank phrase を入れる.

Bug: ``render_stat_delta_article`` は ``_render_simple_data_article`` を呼んで
1 選手分の key-value table しか出さず、 他チーム選手との比較が欠ける。
title も ``リーグ N 位`` を含まないため case A spec (2026-05-15 user lock)
非準拠。

Fix:
- 本文「## データ」section をセ・リーグ規定到達者 top 10 + (focal 圏外なら)
  周辺 ranks を含む ranking 表に切替。 focal は ★ 赤太字 highlight。
- title を ``【巨人データ】<選手>、<metric_label><value>でセ・リーグ N/M 位（<期間>）``
  に refit (case A 準拠)。
- conn が None または snapshot 不在の場合は fallback (rank phrase 無 + 既存
  key-value table) を維持し既存 test を壊さない。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

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


# ─── 本文 ranking 表 ──────────────────────────────────────────────────────


def test_stat_delta_article_includes_central_league_ranking_table(tmp_path):
    """SIGNAL_STAT_DELTA 記事の本文に セ・リーグ ranking 表 (他チーム選手込み)
    が含まれること.
    """
    conn = _open_seed_db(tmp_path)
    try:
        ranking_rows = [
            ("村上頌樹", "t", 0.850, 50, 1, 10),
            ("大野雄大", "d", 0.820, 48, 2, 10),
            ("東克樹", "db", 0.800, 45, 3, 10),
            ("柳裕也", "d", 0.780, 50, 4, 10),
            ("巨人投手", "g", 0.770, 44, 5, 10),  # focal
            ("床田寛樹", "c", 0.760, 46, 6, 10),
            ("山野太一", "s", 0.740, 43, 7, 10),
            ("才木浩人", "t", 0.720, 41, 8, 10),
            ("金丸夢斗", "d", 0.700, 44, 9, 10),
            ("栗林良吏", "c", 0.680, 46, 10, 10),
        ]
        _seed_snapshot_rows(
            conn, snapshot_date="2026-05-17", scope="last_7d",
            metric_name="OPS", rows=ranking_rows,
        )

        candidate = {
            "candidate_id": 88888,
            "signal_type": "anomaly_stat_delta",
            "player_canonical": "巨人投手",
            "notes": "metric=OPS scope=last_7d delta=+0.040",
            "current_value": "current=0.770 (2026-05-17)",
            "baseline_value": "prev=0.730 (2026-05-10)",
            "magnitude": 0.040,
            "snapshot_date": "2026-05-17",
        }
        article = aap.render_stat_delta_article(conn, candidate)
        body = article["body_md"]

        assert "| 順位 | 選手 | チーム |" in body, (
            f"ranking 表 header が無い: body=\n{body}"
        )
        ranking_data_rows = [
            l for l in body.split("\n")
            if l.startswith("|") and l.replace(" ", "").startswith("|1|")
        ]
        assert ranking_data_rows, f"ranking table 1 位行が無い: body=\n{body}"
        assert "村上頌樹" in body, "他チーム選手 (村上頌樹) が ranking 表に無い"
        assert "大野雄大" in body, "他チーム選手 (大野雄大) が ranking 表に無い"
    finally:
        conn.close()


# ─── title case A 準拠 ────────────────────────────────────────────────────


def test_stat_delta_title_includes_central_rank_phrase(tmp_path):
    """title が case A 形式 ``...でセ・リーグ N/M 位（<期間>）`` を含む."""
    conn = _open_seed_db(tmp_path)
    try:
        ranking_rows = [
            ("村上頌樹", "t", 0.850, 50, 1, 10),
            ("大野雄大", "d", 0.820, 48, 2, 10),
            ("東克樹", "db", 0.800, 45, 3, 10),
            ("柳裕也", "d", 0.780, 50, 4, 10),
            ("巨人投手", "g", 0.770, 44, 5, 10),
            ("床田寛樹", "c", 0.760, 46, 6, 10),
            ("山野太一", "s", 0.740, 43, 7, 10),
            ("才木浩人", "t", 0.720, 41, 8, 10),
            ("金丸夢斗", "d", 0.700, 44, 9, 10),
            ("栗林良吏", "c", 0.680, 46, 10, 10),
        ]
        _seed_snapshot_rows(
            conn, snapshot_date="2026-05-17", scope="last_7d",
            metric_name="OPS", rows=ranking_rows,
        )

        candidate = {
            "candidate_id": 88888,
            "signal_type": "anomaly_stat_delta",
            "player_canonical": "巨人投手",
            "notes": "metric=OPS scope=last_7d delta=+0.040",
            "current_value": "current=0.770 (2026-05-17)",
            "baseline_value": "prev=0.730 (2026-05-10)",
            "magnitude": 0.040,
            "snapshot_date": "2026-05-17",
        }
        article = aap.render_stat_delta_article(conn, candidate)

        assert article["title"].startswith("【巨人データ】"), (
            f"prefix 【巨人データ】 欠落: title={article['title']!r}"
        )
        assert "でセ・リーグ5/10位" in article["title"], (
            f"case A rank phrase が無い: title={article['title']!r}"
        )
        assert "（直近1週間）" in article["title"], (
            f"period suffix が無い: title={article['title']!r}"
        )
    finally:
        conn.close()


# ─── fallback (conn=None or snapshot 不在) ──────────────────────────────────


def test_stat_delta_no_conn_keeps_existing_title():
    """conn=None の場合は既存 title format (rank phrase 無 + period 末尾括弧)
    を維持する (backward compat).
    """
    article = aap.render_stat_delta_article(None, {
        "player_canonical": "巨人投手",
        "notes": "metric=ERA scope=last_7d delta=+0.30",
        "current_value": "current=2.800 (2026-05-15) rank 2→3",
        "baseline_value": "prev=2.500 (2026-05-14)",
        "magnitude": 0.30,
    })
    # 既存 test (test_stat_delta_title_uses_japanese_metric_and_not_delta) と
    # 同じ期待値。 rank phrase は付かない。
    assert article["title"] == "【巨人データ】巨人投手、防御率2.800（直近1週間）"


def test_stat_delta_missing_snapshot_falls_back_gracefully(tmp_path):
    """snapshot 不在の場合は ranking 表 / rank phrase 無で fallback、
    title prefix と period suffix は維持する.
    """
    conn = _open_seed_db(tmp_path)
    try:
        candidate = {
            "candidate_id": 77777,
            "signal_type": "anomaly_stat_delta",
            "player_canonical": "巨人投手",
            "notes": "metric=OPS scope=last_7d delta=+0.040",
            "current_value": "current=0.770 (2026-05-17)",
            "baseline_value": "prev=0.730 (2026-05-10)",
            "magnitude": 0.040,
            "snapshot_date": "2026-05-17",
        }
        article = aap.render_stat_delta_article(conn, candidate)
        assert article["title"].startswith("【巨人データ】"), (
            f"prefix 欠落: title={article['title']!r}"
        )
        assert "でセ・リーグ" not in article["title"], (
            f"snapshot 不在で rank phrase 付与: title={article['title']!r}"
        )
        assert "（直近1週間）" in article["title"]
    finally:
        conn.close()
