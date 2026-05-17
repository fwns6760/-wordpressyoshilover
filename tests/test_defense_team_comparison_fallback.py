"""Tests for issue #44 B-2: UZR / 守備率 fallback path に team_comparison
を挟む.

Bug: ``render_defense_uzr_article`` / ``render_defense_fielding_pct_article``
は ``_render_defense_player_comparison_article`` が None を返す (focal 選手が
ポジションに 1 人しかいない 等) と直接 ``_render_simple_data_article`` 経由で
1 選手分の key-value table のみ生成し、 他チームとの比較が完全に欠落していた。

Fix: player_comparison が None を返した場合、 次に
``_render_defense_team_comparison_article`` (セ・リーグ 6 球団 ranking 表) を
fallback として挟む。 team_comparison も None なら従来通り simple_data。

これにより「セ・リーグ選手と比較した表」を全ての defense 記事に出すという
2026-05-17 user 指示を満たす。
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


def _seed_game(conn: sqlite3.Connection, game_id: str, game_date: str) -> None:
    insight_etl.seed_teams(conn)
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-15T00:00:00Z')",
        (game_id, game_date),
    )
    conn.commit()


# ─── UZR fallback chain ────────────────────────────────────────────────────


def test_defense_uzr_falls_back_to_team_comparison_when_player_comparison_empty(tmp_path):
    """player_comparison が None (focal player 単独) の時、
    team_comparison が fallback として fire し、 セ・リーグ球団別ranking が出る.
    """
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game(conn, game_id="def-g1", game_date="2026-05-16")
        # Giants 投手 only 1 名 at position (player_comparison は >= 2 必要で fail)
        conn.execute(
            "INSERT INTO defense_opportunities "
            "(game_id, team_code, position, player_canonical, opportunities, "
            "converted_outs, hits_allowed, errors) "
            "VALUES ('def-g1', 'g', '投', '巨人投手', 30, 22, 0, 1)",
        )
        # team-level data for 6 teams (player NULL) → team_comparison が拾える
        for team, opps, outs, errors in [
            ("g", 30, 22, 1),
            ("t", 28, 24, 0),
            ("s", 27, 18, 1),
            ("c", 29, 21, 0),
            ("db", 26, 17, 1),
            ("d", 28, 19, 0),
        ]:
            conn.execute(
                "INSERT INTO defense_opportunities "
                "(game_id, team_code, position, player_canonical, opportunities, "
                "converted_outs, hits_allowed, errors) "
                "VALUES ('def-g1', ?, '投', NULL, ?, ?, 0, ?)",
                (team, opps, outs, errors),
            )
        conn.commit()

        article = aap.render_defense_uzr_article(conn, {
            "player_canonical": "巨人投手",
            "magnitude": 0.050,
            "notes": "position=投 metric=UZR_proxy",
            "current_value": "RF_proxy=0.733 opportunities=30 converted_outs=22 errors=1",
            "baseline_value": "position=投 league_RF_baseline=0.700",
        })

        # team_comparison が fire したことを示す marker
        assert "セ・リーグ球団別ランキング" in article["body_md"], (
            f"team_comparison fallback が fire していない: body=\n{article['body_md'][:500]}"
        )
        assert "| 順位 | 球団 |" in article["body_md"], (
            f"球団 ranking table header が無い: body=\n{article['body_md'][:500]}"
        )
        # team_comparison が出す title は「巨人は ... でセ・リーグ N/M 位」を含む
        assert "セ・リーグ" in article["title"]
        assert "/6位" in article["title"]
    finally:
        conn.close()


def test_defense_fielding_pct_falls_back_to_team_comparison_when_player_comparison_empty(tmp_path):
    """守備率 も同じく team_comparison fallback が fire する."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game(conn, game_id="def-g2", game_date="2026-05-16")
        conn.execute(
            "INSERT INTO defense_opportunities "
            "(game_id, team_code, position, player_canonical, opportunities, "
            "converted_outs, hits_allowed, errors) "
            "VALUES ('def-g2', 'g', '中', '巨人外野手', 25, 24, 0, 0)",
        )
        for team, opps, outs, errors in [
            ("g", 25, 24, 0),
            ("t", 24, 23, 0),
            ("s", 26, 24, 1),
            ("c", 25, 23, 1),
            ("db", 23, 22, 0),
            ("d", 24, 22, 1),
        ]:
            conn.execute(
                "INSERT INTO defense_opportunities "
                "(game_id, team_code, position, player_canonical, opportunities, "
                "converted_outs, hits_allowed, errors) "
                "VALUES ('def-g2', ?, '中', NULL, ?, ?, 0, ?)",
                (team, opps, outs, errors),
            )
        conn.commit()

        article = aap.render_defense_fielding_pct_article(conn, {
            "player_canonical": "巨人外野手",
            "magnitude": 0.020,
            "notes": "position=中 metric=FIELDING_PCT",
            "current_value": "fielding_pct=1.000 converted_outs=24 errors=0",
            "baseline_value": "position=中 league_fpct_baseline=0.980",
        })

        assert "セ・リーグ球団別ランキング" in article["body_md"], (
            f"team_comparison fallback が fire していない: body=\n{article['body_md'][:500]}"
        )
        assert "| 順位 | 球団 |" in article["body_md"]
        assert "セ・リーグ" in article["title"]
        assert "/6位" in article["title"]
    finally:
        conn.close()


# ─── backward compat ──────────────────────────────────────────────────────


def test_defense_uzr_no_conn_keeps_existing_title():
    """conn=None の場合は既存 simple_data fallback title を維持する (backward
    compat、 既存 test test_defense_titles_are_reader_friendly と同じ期待)。
    """
    article = aap.render_defense_uzr_article(None, {
        "player_canonical": "吉川尚輝",
        "magnitude": 0.052,
        "notes": "position=二 守備平均超え",
        "current_value": "RF_proxy=0.985 opportunities=40 converted_outs=39 errors=0",
        "baseline_value": "position=二 league_RF_baseline=0.933",
    })
    assert article["title"] == (
        "【巨人データ】吉川尚輝、二塁守備の簡易UZRが守備位置平均を上回る（直近30日）"
    )


def test_defense_fielding_pct_no_conn_keeps_existing_title():
    """守備率 conn=None backward compat."""
    article = aap.render_defense_fielding_pct_article(None, {
        "player_canonical": "吉川尚輝",
        "magnitude": 0.052,
        "notes": "position=二 守備率高",
        "current_value": "fielding_pct=0.985 converted_outs=39 errors=0",
        "baseline_value": "position=二 league_fpct_baseline=0.933",
    })
    assert article["title"] == (
        "【巨人データ】吉川尚輝、二塁守備率0.985が守備位置平均を上回る（直近30日）"
    )
