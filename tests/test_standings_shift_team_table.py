"""Tests for issue #44 B-6: render_standings_shift_article の本文に
セ・リーグ 6 球団順位表 + title を case D 寄りに refit.

Bug: ``render_standings_shift_article`` は ``_render_simple_data_article``
経由で巨人 1 球団分の key-value table のみ生成し、 6 球団順位表が無かった。
title も「【巨人データ】巨人、順位 P→N (方向)」で case D spec (球団主語
``チーム`` prefix、 期間末尾括弧) に不揃いだった。

Fix:
- ``standings_snapshots`` の latest snapshot から セ・リーグ 6 球団の
  順位 / 勝 / 負 / 引分 / ゲーム差 を取得し、 markdown 順位表を本文に出す
- title を case D に refit:
  ``【巨人データ】チーム 順位 {prev}→{new}（今シーズン進行中）``
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


def _seed_standings(
    conn: sqlite3.Connection,
    *,
    snap_date: str,
    rows: list[tuple[str, int, int, int, int, float]],
) -> None:
    """rows = [(team, rank, W, L, T, GB), ...]"""
    insight_etl.seed_teams(conn)
    for team, rank, w, l, t, gb in rows:
        conn.execute(
            "INSERT INTO standings_snapshots "
            "(snap_date, team, rank, W, L, T, games_behind) "
            "VALUES (?,?,?,?,?,?,?)",
            (snap_date, team, rank, w, l, t, gb),
        )
    conn.commit()


def test_standings_shift_body_contains_central_6_team_table(tmp_path):
    """本文に セ・リーグ 6 球団 順位表 (勝/負/引分/GB 含む) が出る."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_standings(
            conn,
            snap_date="2026-05-17",
            rows=[
                ("t", 1, 25, 18, 1, 0.0),
                ("g", 2, 23, 20, 0, 2.0),
                ("db", 3, 22, 21, 1, 3.0),
                ("c", 4, 20, 22, 2, 4.5),
                ("d", 5, 19, 23, 1, 5.5),
                ("s", 6, 17, 25, 0, 7.5),
            ],
        )

        article = aap.render_standings_shift_article(conn, {
            "player_canonical": "巨人",
            "current_value": "current_rank=2 W=23 L=20 T=0 GB=2.0",
            "baseline_value": "prev_rank=3 prev_W=22 prev_L=20",
            "notes": "direction=上昇 prev_date=2026-05-16 latest_date=2026-05-17",
        })
        body = article["body_md"]

        # 6 球団順位表 header
        assert "| 順位 | 球団 |" in body, (
            f"6 球団順位表 header が無い: body=\n{body[:600]}"
        )
        # 6 球団全て含まれる (略称ではなく 日本語球団名)
        for team_jp in ["阪神", "DeNA", "広島", "中日", "ヤクルト"]:
            assert team_jp in body, (
                f"球団名 {team_jp} が無い: body=\n{body[:800]}"
            )
        # 巨人が ★ marker / 赤太字 で highlight される
        assert "巨人 ★" in body or "巨人★" in body, (
            f"巨人 highlight (★) が無い: body=\n{body[:800]}"
        )
    finally:
        conn.close()


def test_standings_shift_title_case_d():
    """title が case D 形 (「チーム」prefix + 期間末尾括弧) になる."""
    article = aap.render_standings_shift_article(None, {
        "player_canonical": "巨人",
        "current_value": "current_rank=2 W=23 L=20 T=0 GB=2.0",
        "baseline_value": "prev_rank=3 prev_W=22 prev_L=20",
        "notes": "direction=上昇 prev_date=2026-05-16 latest_date=2026-05-17",
    })
    title = article["title"]
    assert title.startswith("【巨人データ】"), (
        f"prefix 欠落: title={title!r}"
    )
    # case D: team subject「チーム」prefix を使う
    assert "チーム" in title, (
        f"case D の team subject「チーム」が無い: title={title!r}"
    )
    # 旧 title の「巨人、順位」を使わない
    assert "巨人、順位" not in title, (
        f"旧 title pattern が残っている: title={title!r}"
    )
    # 期間末尾括弧
    assert title.endswith("）"), f"末尾括弧で閉じていない: title={title!r}"
    # 順位変動情報は維持
    assert "3" in title and "2" in title, (
        f"順位変動情報 (3→2) が無い: title={title!r}"
    )
