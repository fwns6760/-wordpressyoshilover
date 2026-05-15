"""Tests for 348 step 3 part 2: record-milestone detector + team ranking 拡張.

検証軸:
  1. detect_cycle_hits: 1B+2B+3B+HR を同一試合で記録した player を検出
  2. detect_no_hitter: H=0, IP>=9.0 で 完全試合判定でないものを emit
  3. detect_perfect_game: H=0, BB=0, HBP=0, BF<=28, IP>=9.0
  4. team_ranking_publisher.aggregate_team_run_diff (得失点差)
  5. team_ranking_publisher.aggregate_team_winning_streak (連勝/連敗)
  6. team_ranking_publisher.aggregate_team_vs_opponent (対戦相手別)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis import insight_anomaly_detector as det  # noqa: E402
from src.analysis import team_ranking_publisher as trp  # noqa: E402
from src.analysis import insight_whitelist as wl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_whitelist_cache():
    wl.reset_cache()
    yield
    wl.reset_cache()


def _open_db(tmp_path):
    return insight_etl.open_db(db_path=tmp_path / "t.db", schema_path=insight_etl.DEFAULT_SCHEMA)


def _seed_game(conn, *, game_id, game_date, opponent="t",
               giants_score=0, opp_score=0, result=""):
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, ?, 'home', ?, ?, ?, '', 'test', '2026-05-15T00:00:00Z')",
        (game_id, game_date, opponent, giants_score, opp_score, result),
    )


def _seed_batting_atbats(conn, *, game_id, player_canonical, team_name, atbats):
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, "
        "atbats_json, team_name) "
        "VALUES (?, 'home', 1, '中', ?, ?, 0, ?, 0, ?, 0, 0, ?, ?)",
        (game_id, player_canonical, player_canonical, len(atbats),
         sum(1 for ab in atbats if ab[0] in ("単", "二", "三", "本")),
         json.dumps(atbats), team_name),
    )


def _seed_pitching(conn, *, game_id, player_canonical, team_name,
                   IP, H_allowed, BB, HBP, BF, K=5):
    conn.execute(
        "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
        "player_display, player_canonical, result_mark, pitches, BF, IP, "
        "H_allowed, HR_allowed, BB, HBP, K, R, ER, team_name) "
        "VALUES (?, 'home', 1, ?, ?, '勝', 100, ?, ?, ?, 0, ?, ?, ?, 0, 0, ?)",
        (game_id, player_canonical, player_canonical, BF, IP, H_allowed,
         BB, HBP, K, team_name),
    )


# ─── cycle detection ─────────────────────────────────────────────────────


def test_detect_cycle_hits_finds_player_with_full_cycle(tmp_path):
    """1B + 2B + 3B + HR を 1 試合で記録した player を検出。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-15")
        # サイクル: 単打 + 二塁打 + 三塁打 + 本塁打
        _seed_batting_atbats(
            conn, game_id="g1", player_canonical="サイクル男",
            team_name="巨人",
            atbats=["単安", "二塁打", "三塁打", "本塁打"],
        )
        conn.commit()
        ids = det.detect_cycle_hits(conn, snapshot_date="2026-05-15")
        assert len(ids) >= 1
        rows = conn.execute(
            "SELECT player_canonical, comparison_target FROM article_candidates "
            "WHERE candidate_id IN (" + ",".join("?" * len(ids)) + ")", ids,
        ).fetchall()
        players = [r[0] for r in rows]
        assert "サイクル男" in players
        assert any(r[1] == "record_cycle" for r in rows)
    finally:
        conn.close()


def test_detect_cycle_hits_skips_incomplete(tmp_path):
    """1B + 2B + HR のみ (3B 欠) は cycle ではない。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g2", game_date="2026-05-15")
        _seed_batting_atbats(
            conn, game_id="g2", player_canonical="未達者",
            team_name="巨人",
            atbats=["単安", "二塁打", "本塁打", "三振"],
        )
        conn.commit()
        ids = det.detect_cycle_hits(conn, snapshot_date="2026-05-15")
        assert ids == []
    finally:
        conn.close()


# ─── no-hitter detection ─────────────────────────────────────────────────


def test_detect_no_hitter_finds_h0_with_walks(tmp_path):
    """H=0 だが BB>0 で完全試合でない → ノーノー emit。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g3", game_date="2026-05-15")
        _seed_pitching(
            conn, game_id="g3", player_canonical="ノーノー投手",
            team_name="巨人",
            IP=9.0, H_allowed=0, BB=2, HBP=0, BF=29,
        )
        conn.commit()
        ids = det.detect_no_hitter(conn, snapshot_date="2026-05-15")
        assert len(ids) >= 1
        rows = conn.execute(
            "SELECT player_canonical, comparison_target FROM article_candidates "
            "WHERE candidate_id IN (" + ",".join("?" * len(ids)) + ")", ids,
        ).fetchall()
        assert "ノーノー投手" in [r[0] for r in rows]
        assert any(r[1] == "record_no_hitter" for r in rows)
    finally:
        conn.close()


def test_detect_no_hitter_excludes_perfect_game(tmp_path):
    """完全試合 (BB=0, HBP=0, BF<=28) は no_hitter detector では emit しない。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g4", game_date="2026-05-15")
        _seed_pitching(
            conn, game_id="g4", player_canonical="完全試合投手",
            team_name="巨人",
            IP=9.0, H_allowed=0, BB=0, HBP=0, BF=27,
        )
        conn.commit()
        ids = det.detect_no_hitter(conn, snapshot_date="2026-05-15")
        assert ids == []  # perfect game は別 detector
    finally:
        conn.close()


def test_detect_no_hitter_skips_partial_innings(tmp_path):
    """IP < 9.0 はノーノー成立せず。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g5", game_date="2026-05-15")
        _seed_pitching(
            conn, game_id="g5", player_canonical="6回降板",
            team_name="巨人",
            IP=6.0, H_allowed=0, BB=1, HBP=0, BF=20,
        )
        conn.commit()
        ids = det.detect_no_hitter(conn, snapshot_date="2026-05-15")
        assert ids == []
    finally:
        conn.close()


# ─── perfect game detection ──────────────────────────────────────────────


def test_detect_perfect_game(tmp_path):
    """H=0, BB=0, HBP=0, BF<=28, IP>=9.0 → 完全試合 emit。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g6", game_date="2026-05-15")
        _seed_pitching(
            conn, game_id="g6", player_canonical="完全試合男",
            team_name="巨人",
            IP=9.0, H_allowed=0, BB=0, HBP=0, BF=27,
        )
        conn.commit()
        ids = det.detect_perfect_game(conn, snapshot_date="2026-05-15")
        assert len(ids) >= 1
        rows = conn.execute(
            "SELECT player_canonical, comparison_target FROM article_candidates "
            "WHERE candidate_id IN (" + ",".join("?" * len(ids)) + ")", ids,
        ).fetchall()
        assert "完全試合男" in [r[0] for r in rows]
        assert any(r[1] == "record_perfect_game" for r in rows)
    finally:
        conn.close()


def test_detect_perfect_game_excludes_walk(tmp_path):
    """BB=1 は完全試合ではない。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g7", game_date="2026-05-15")
        _seed_pitching(
            conn, game_id="g7", player_canonical="四球許す投手",
            team_name="巨人",
            IP=9.0, H_allowed=0, BB=1, HBP=0, BF=28,
        )
        conn.commit()
        ids = det.detect_perfect_game(conn, snapshot_date="2026-05-15")
        assert ids == []
    finally:
        conn.close()


# ─── team ranking 拡張 ───────────────────────────────────────────────────


def test_aggregate_team_run_diff(tmp_path):
    """得失点差 = SUM(giants_score) - SUM(opp_score)。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="rd1", game_date="2026-05-10",
                   giants_score=5, opp_score=3)
        _seed_game(conn, game_id="rd2", game_date="2026-05-12",
                   giants_score=8, opp_score=1)
        _seed_game(conn, game_id="rd3", game_date="2026-05-14",
                   giants_score=2, opp_score=4)
        conn.commit()
        rows = trp.aggregate_team_run_diff(conn, scope="season")
        giants = [r for r in rows if r["team"] == "g"][0]
        # (5-3) + (8-1) + (2-4) = 2 + 7 - 2 = 7
        assert giants["value"] == 7
    finally:
        conn.close()


def test_aggregate_team_winning_streak_4win(tmp_path):
    """直近 4 試合 win → kind=win, streak=4。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="ws1", game_date="2026-05-10", result="loss")
        _seed_game(conn, game_id="ws2", game_date="2026-05-11", result="win")
        _seed_game(conn, game_id="ws3", game_date="2026-05-12", result="win")
        _seed_game(conn, game_id="ws4", game_date="2026-05-13", result="win")
        _seed_game(conn, game_id="ws5", game_date="2026-05-14", result="win")
        conn.commit()
        result = trp.aggregate_team_winning_streak(conn)
        assert result["kind"] == "win"
        assert result["streak"] == 4
    finally:
        conn.close()


def test_aggregate_team_winning_streak_3loss(tmp_path):
    """直近 3 連敗。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="ls1", game_date="2026-05-12", result="win")
        _seed_game(conn, game_id="ls2", game_date="2026-05-13", result="loss")
        _seed_game(conn, game_id="ls3", game_date="2026-05-14", result="loss")
        _seed_game(conn, game_id="ls4", game_date="2026-05-15", result="loss")
        conn.commit()
        result = trp.aggregate_team_winning_streak(conn)
        assert result["kind"] == "loss"
        assert result["streak"] == 3
    finally:
        conn.close()


def test_aggregate_player_counting_stat_h(tmp_path):
    """counting stat (H 安打数) を player 別に集計、 top N 返す (348 step 3 D-1)。"""
    import datetime as _dt
    from src.analysis import ranking_article_publisher as rap
    conn = _open_db(tmp_path)
    try:
        # 3 player × 複数試合の安打数
        for i, date in enumerate(["2026-05-10", "2026-05-12", "2026-05-14"]):
            _seed_game(conn, game_id=f"c{i}", game_date=date)
        # Player A: 4+3+2 = 9 H
        for i, h in enumerate([4, 3, 2]):
            conn.execute(
                "INSERT INTO batting_logs (game_id, team_role, slot_order, "
                "position, player_display, player_canonical, is_sub, AB, R, "
                "H, RBI, SB, atbats_json, team_name) "
                "VALUES (?, 'home', 1, '中', 'A', 'A', 0, 4, 0, ?, 0, 0, '[]', '巨人')",
                (f"c{i}", h),
            )
        # Player B: 3+1+1 = 5 H
        for i, h in enumerate([3, 1, 1]):
            conn.execute(
                "INSERT INTO batting_logs (game_id, team_role, slot_order, "
                "position, player_display, player_canonical, is_sub, AB, R, "
                "H, RBI, SB, atbats_json, team_name) "
                "VALUES (?, 'home', 2, '一', 'B', 'B', 0, 4, 0, ?, 0, 0, '[]', '巨人')",
                (f"c{i}", h),
            )
        conn.commit()
        rows = rap.aggregate_player_counting_stat(
            conn, stat_col="H", table="batting_logs", scope="season",
            today=_dt.date(2026, 5, 15), top_n=10,
        )
        # A が 1 位 (9 H)、 B が 2 位 (5 H)
        assert len(rows) >= 2
        assert rows[0]["player"] == "A"
        assert rows[0]["value"] == 9
        assert rows[1]["player"] == "B"
        assert rows[1]["value"] == 5
    finally:
        conn.close()


def test_aggregate_player_counting_stat_rejects_sql_injection(tmp_path):
    """unsafe stat_col は ValueError。"""
    from src.analysis import ranking_article_publisher as rap
    conn = _open_db(tmp_path)
    try:
        with pytest.raises(ValueError):
            rap.aggregate_player_counting_stat(
                conn, stat_col="H; DROP TABLE games --",
                table="batting_logs", scope="season",
            )
    finally:
        conn.close()


def test_record_renderer_cycle_title(tmp_path):
    """D-3 renderer: cycle hit candidate を正しい title で render。"""
    from src.analysis import anomaly_article_publisher as pub
    candidate = {
        "player_canonical": "サイクル達成者",
        "current_value": "game=g1 vs=t",
        "baseline_value": "cycle",
        "notes": "record=cycle game=2026-05-15:g-t-1 opponent=t",
        "magnitude": 4.0,
    }
    article = pub.render_milestone_crossed_article(None, candidate)
    assert "サイクル安打" in article["title"]
    assert "サイクル達成者" in article["title"]
    assert "2026-05-15" in article["title"]
    # 旧 path (空 metric/threshold) で生成される壊れ title が出ないこと
    assert "シーズン  到達" not in article["title"]


def test_record_renderer_perfect_game_title(tmp_path):
    """D-3 renderer: perfect game 専用 title。"""
    from src.analysis import anomaly_article_publisher as pub
    candidate = {
        "player_canonical": "完全試合男",
        "current_value": "game=g3 IP=9.0 BF=27",
        "baseline_value": "perfect game (H=0, BB=0, HBP=0, BF<=28)",
        "notes": "record=perfect_game game=2026-05-15:g-t-2 opponent=t",
        "magnitude": 27.0,
    }
    article = pub.render_milestone_crossed_article(None, candidate)
    assert "完全試合" in article["title"]
    assert "完全試合男" in article["title"]


def test_record_renderer_no_hitter_title():
    """D-3 renderer: no-hitter 専用 title。"""
    from src.analysis import anomaly_article_publisher as pub
    candidate = {
        "player_canonical": "ノーノー投手",
        "current_value": "game=g2 IP=9.0",
        "baseline_value": "no-hitter",
        "notes": "record=no_hitter game=2026-05-15:g-t-3 opponent=db",
        "magnitude": 9.0,
    }
    article = pub.render_milestone_crossed_article(None, candidate)
    assert "ノーヒットノーラン" in article["title"]


def test_record_renderer_legacy_milestone_path_preserved():
    """既存 path (数値 threshold milestone) も regression なし。"""
    from src.analysis import anomaly_article_publisher as pub
    candidate = {
        "player_canonical": "30HR男",
        "notes": "metric=HR threshold=30 value=30",
        "current_value": "HR=30",
        "magnitude": 30.0,
    }
    article = pub.render_milestone_crossed_article(None, candidate)
    assert "シーズン HR 30 到達" in article["title"]
    assert "30HR男" in article["title"]


def test_render_team_streak_article_active_winning(tmp_path):
    """D-2: render_team_streak_article で 連勝 article 生成。"""
    from src.analysis import team_ranking_publisher as trp
    conn = _open_db(tmp_path)
    try:
        for i in range(4):
            _seed_game(conn, game_id=f"sw{i}", game_date=f"2026-05-1{1+i}",
                       result="win")
        conn.commit()
        article = trp.render_team_streak_article(conn)
        assert article is not None
        assert "4 連勝" in article["title"]
        assert article["kind"] == "win"
        assert article["streak"] == 4
    finally:
        conn.close()


def test_render_team_streak_article_below_threshold(tmp_path):
    """D-2: streak < 3 は記事化しない (skip None)。"""
    from src.analysis import team_ranking_publisher as trp
    conn = _open_db(tmp_path)
    try:
        for i in range(2):
            _seed_game(conn, game_id=f"sw{i}", game_date=f"2026-05-1{4+i}",
                       result="win")
        conn.commit()
        article = trp.render_team_streak_article(conn)
        assert article is None
    finally:
        conn.close()


def test_render_player_counting_article(tmp_path):
    """D-1: render_player_counting_article で 安打数 ranking 記事生成。"""
    from src.analysis import ranking_article_publisher as rap
    conn = _open_db(tmp_path)
    try:
        # 3 player × 複数試合
        for i, date in enumerate(["2026-05-10", "2026-05-12", "2026-05-14"]):
            _seed_game(conn, game_id=f"pc{i}", game_date=date)
        for i, h in enumerate([4, 3, 3]):  # 巨人選手 (team='巨人')
            conn.execute(
                "INSERT INTO batting_logs (game_id, team_role, slot_order, "
                "position, player_display, player_canonical, is_sub, AB, R, "
                "H, RBI, SB, atbats_json, team_name) "
                "VALUES (?, 'home', 1, '中', '坂本', '坂本', 0, 4, 0, ?, 0, 0, "
                "'[]', '巨人')",
                (f"pc{i}", h),
            )
        for i, h in enumerate([1, 2, 1]):  # 他球団選手 (team='阪神')
            conn.execute(
                "INSERT INTO batting_logs (game_id, team_role, slot_order, "
                "position, player_display, player_canonical, is_sub, AB, R, "
                "H, RBI, SB, atbats_json, team_name) "
                "VALUES (?, 'home', 2, '一', '佐藤', '佐藤', 0, 4, 0, ?, 0, 0, "
                "'[]', '阪神')",
                (f"pc{i}", h),
            )
        conn.commit()
        # season scope で今日 (= 2026-05-15) より前の全試合集計
        import datetime as _dt
        # 坂本 = 10 H, 佐藤 = 4 H → 坂本 1 位、 佐藤 2 位
        rows = rap.aggregate_player_counting_stat(
            conn, stat_col="H", table="batting_logs", scope="season",
            today=_dt.date(2026, 5, 15), top_n=10,
        )
        # まず aggregate が正しい
        assert rows[0]["player"] == "坂本"
        assert rows[0]["value"] == 10
    finally:
        conn.close()


def test_aggregate_team_vs_opponent(tmp_path):
    """対戦相手別 W-L 集計。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="vs1", game_date="2026-05-10",
                   opponent="t", result="win")
        _seed_game(conn, game_id="vs2", game_date="2026-05-12",
                   opponent="t", result="win")
        _seed_game(conn, game_id="vs3", game_date="2026-05-14",
                   opponent="t", result="loss")
        _seed_game(conn, game_id="vs4", game_date="2026-05-11",
                   opponent="db", result="loss")
        conn.commit()
        # 対 阪神
        r = trp.aggregate_team_vs_opponent(conn, opponent="t", scope="season")
        assert r["W"] == 2
        assert r["L"] == 1
        assert r["T"] == 0
        # 対 DeNA
        r2 = trp.aggregate_team_vs_opponent(conn, opponent="db", scope="season")
        assert r2["W"] == 0
        assert r2["L"] == 1
    finally:
        conn.close()
