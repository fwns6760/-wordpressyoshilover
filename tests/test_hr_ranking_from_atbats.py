"""Tests for issue #44 G follow-up: HR player ranking を atbats_json から集計.

issue #44 G で「HR 列が batting_logs に無い」 SQL error は止めたが、
HR ranking 記事自体が一切 publish されなかった (commit 4f4a603 で
COUNTING_METRICS から HR row 除外)。

本 fix: ``aggregate_player_hr_from_atbats`` を追加し、
``aggregate_player_counting_stat`` が ``stat_col="HR"`` を検出した時に
dispatch する。 ``COUNTING_METRICS`` に HR row を再追加。
``team_ranking_publisher.aggregate_team_hr`` と同じ pattern
(``insight_atbats_parser.parse_atbat(ab).get("is_hr")``) を player level に拡張。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.analysis import insight_etl, ranking_article_publisher as rap


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
        "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-17T00:00:00Z')",
        (game_id, game_date),
    )


def _seed_batting(conn, *, game_id, player, team_name, atbats):
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, "
        "atbats_json, team_name) "
        "VALUES (?, 'home', 1, '中', ?, ?, 0, ?, 0, ?, 0, 0, ?, ?)",
        (game_id, player, player, len(atbats),
         sum(1 for ab in atbats if "本" in ab or "中本" in ab or "右本" in ab or "左本" in ab),
         json.dumps(atbats), team_name),
    )


def test_aggregate_hr_counts_central_players_from_atbats(tmp_path):
    """セ・リーグ league filter で巨人 + 他 5 球団の HR 数を集計."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game(conn, game_id="g-hr-1", game_date="2026-05-17")
        # 巨人 player A: 中本 + 右本 (2 HR)
        _seed_batting(conn, game_id="g-hr-1", player="巨人A", team_name="巨人",
                      atbats=["中本", "右本", "中安"])
        # 巨人 player B: 左本 (1 HR)
        _seed_batting(conn, game_id="g-hr-1", player="巨人B", team_name="巨人",
                      atbats=["左本", "三振"])
        # 阪神 player C: 中本 (1 HR)
        _seed_batting(conn, game_id="g-hr-1", player="阪神C", team_name="阪神",
                      atbats=["中本"])
        # ヤクルト player D: no HR
        _seed_batting(conn, game_id="g-hr-1", player="ヤクD", team_name="ヤクルト",
                      atbats=["三振", "四球"])
        # パ player (filter で除外)
        _seed_batting(conn, game_id="g-hr-1", player="ソフトE", team_name="ソフトバンク",
                      atbats=["中本", "中本"])
        conn.commit()

        import datetime as _dt
        rows = rap.aggregate_player_hr_from_atbats(
            conn, scope="last_7d", today=_dt.date(2026, 5, 17),
            top_n=10, league="central",
        )

        # 順位: 巨人A(2) > 巨人B(1) = 阪神C(1) > (no HR は除外)
        assert len(rows) == 3, f"got rows={rows}"
        assert rows[0]["player"] == "巨人A"
        assert rows[0]["value"] == 2
        # 残り 2 件は player order 任意 (value 同値)
        rest_names = {r["player"] for r in rows[1:]}
        assert rest_names == {"巨人B", "阪神C"}
        # パ player はリーグ filter で除外
        assert not any(r["player"] == "ソフトE" for r in rows)
        # team_code 解決確認
        teams = {r["player"]: r["team"] for r in rows}
        assert teams["巨人A"] == "g"
        assert teams["阪神C"] == "t"
    finally:
        conn.close()


def test_aggregate_player_counting_stat_dispatches_hr_to_atbats(tmp_path):
    """aggregate_player_counting_stat に stat_col='HR' を渡すと SQL SUM(bl.HR) を
    発行せず、 atbats_json 経由の集計に dispatch する."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game(conn, game_id="g-disp-1", game_date="2026-05-17")
        _seed_batting(conn, game_id="g-disp-1", player="巨人HR王", team_name="巨人",
                      atbats=["中本", "右本", "左本"])
        conn.commit()

        import datetime as _dt
        # stat_col='HR' で SQL OperationalError が出ない、 結果が返る
        rows = rap.aggregate_player_counting_stat(
            conn, stat_col="HR", table="batting_logs",
            scope="last_7d", today=_dt.date(2026, 5, 17),
            top_n=10, league="central",
        )
        assert len(rows) == 1
        assert rows[0]["player"] == "巨人HR王"
        assert rows[0]["value"] == 3
        assert rows[0]["team"] == "g"
    finally:
        conn.close()


def test_aggregate_hr_no_central_player_returns_empty(tmp_path):
    """巨人を含むセ・リーグに HR 0 件 → empty list."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game(conn, game_id="g-no-hr", game_date="2026-05-17")
        _seed_batting(conn, game_id="g-no-hr", player="無HR選手", team_name="巨人",
                      atbats=["三振", "四球", "中安"])
        conn.commit()

        import datetime as _dt
        rows = rap.aggregate_player_hr_from_atbats(
            conn, scope="last_7d", today=_dt.date(2026, 5, 17),
            top_n=10, league="central",
        )
        assert rows == []
    finally:
        conn.close()


# ─── 406 fix: split 経路の HR dispatch ──────────────────────────────────────


def _seed_game_with_split(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    game_date: str,
    opponent: str = "t",
    home_away: str = "home",
) -> None:
    insight_etl.seed_teams(conn)
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, ?, ?, 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
        (game_id, game_date, opponent, home_away),
    )


def test_aggregate_hr_from_atbats_split_home_filters_correctly(tmp_path):
    """home_away=home filter で home 試合の HR のみ集計、 away 試合は除外."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game_with_split(conn, game_id="g-h-1", game_date="2026-05-17",
                              opponent="t", home_away="home")
        _seed_game_with_split(conn, game_id="g-a-1", game_date="2026-05-18",
                              opponent="s", home_away="away")
        # 巨人A: home で 2 HR
        _seed_batting(conn, game_id="g-h-1", player="巨人A", team_name="巨人",
                      atbats=["中本", "右本"])
        # 巨人A: away で 1 HR (除外されるべき)
        _seed_batting(conn, game_id="g-a-1", player="巨人A", team_name="巨人",
                      atbats=["左本", "三振"])
        conn.commit()

        import datetime as _dt
        rows = rap.aggregate_player_hr_from_atbats_split(
            conn, scope="last_7d", split_field="home_away", split_value="home",
            today=_dt.date(2026, 5, 18), top_n=10, league="central",
        )
        assert len(rows) == 1
        assert rows[0]["player"] == "巨人A"
        assert rows[0]["value"] == 2  # away の 1 HR は除外
    finally:
        conn.close()


def test_aggregate_hr_from_atbats_split_opponent_filters_correctly(tmp_path):
    """opponent=t filter で vs 阪神試合の HR のみ集計、 vs ヤクルトは除外."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game_with_split(conn, game_id="g-vs-t", game_date="2026-05-17",
                              opponent="t", home_away="home")
        _seed_game_with_split(conn, game_id="g-vs-s", game_date="2026-05-18",
                              opponent="s", home_away="home")
        # 巨人A: vs 阪神で 2 HR
        _seed_batting(conn, game_id="g-vs-t", player="巨人A", team_name="巨人",
                      atbats=["中本", "右本"])
        # 巨人A: vs ヤクルトで 3 HR (除外)
        _seed_batting(conn, game_id="g-vs-s", player="巨人A", team_name="巨人",
                      atbats=["中本", "中本", "中本"])
        conn.commit()

        import datetime as _dt
        rows = rap.aggregate_player_hr_from_atbats_split(
            conn, scope="last_7d", split_field="opponent", split_value="t",
            today=_dt.date(2026, 5, 18), top_n=10, league="central",
        )
        assert len(rows) == 1
        assert rows[0]["player"] == "巨人A"
        assert rows[0]["value"] == 2  # vs ヤクルトの 3 HR は除外


    finally:
        conn.close()


def test_aggregate_player_counting_stat_split_dispatches_hr_to_atbats(tmp_path):
    """aggregate_player_counting_stat_split に stat_col='HR' を渡すと
    SQL SUM(bl.HR) を発行せず、 split 対応 atbats 集計に dispatch する (406 fix)."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game_with_split(conn, game_id="g-split-disp", game_date="2026-05-17",
                              opponent="t", home_away="home")
        _seed_batting(conn, game_id="g-split-disp", player="巨人HR王",
                      team_name="巨人",
                      atbats=["中本", "右本", "左本"])
        conn.commit()

        import datetime as _dt
        # stat_col='HR' で OperationalError 出ない、 split 経路でも結果が返る
        rows = rap.aggregate_player_counting_stat_split(
            conn, stat_col="HR", table="batting_logs",
            scope="last_7d", split_field="home_away", split_value="home",
            today=_dt.date(2026, 5, 17), top_n=10, league="central",
        )
        assert len(rows) == 1
        assert rows[0]["player"] == "巨人HR王"
        assert rows[0]["value"] == 3
        assert rows[0]["team"] == "g"
    finally:
        conn.close()
