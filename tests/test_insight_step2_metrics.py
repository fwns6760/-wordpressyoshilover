"""Tests for 348 step 2: 勝率 / 守備率 / publisher 日本語 label。

検証軸:
  1. PitchingLine に W/L が追加され、 win_pct() = W / (W + L)
  2. all_pitcher_metrics に WIN_PCT が含まれる
  3. FieldingLine + fielding_pct() = (PO + A) / (PO + A + E)
  4. all_fielding_metrics に FIELDING_PCT が含まれる
  5. ETL _aggregate_pitching_line が result_mark から W/L をカウント
  6. ETL _aggregate_fielding_line が PO/A/E を集計
  7. publisher _human_metric_label が K_per_9 → 奪三振率、 WIN_PCT → 勝率
  8. config 不在 (FieldingLine 全 0) で fielding_pct=None (safe)
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis import insight_advanced_metrics as adv  # noqa: E402
from src.analysis import insight_whitelist as wl  # noqa: E402
from src.analysis import anomaly_article_publisher as pub  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_whitelist_cache():
    wl.reset_cache()
    yield
    wl.reset_cache()


# ─── PitchingLine W/L + win_pct ──────────────────────────────────────────


def test_pitching_line_has_w_l_fields():
    """PitchingLine に W, L が default=0 で追加された。"""
    line = adv.PitchingLine()
    assert line.W == 0
    assert line.L == 0


def test_win_pct_basic():
    """15 勝 5 敗 → 勝率 0.750。"""
    line = adv.PitchingLine(W=15, L=5)
    assert adv.win_pct(line) == 0.750


def test_win_pct_perfect():
    """10 勝 0 敗 → 勝率 1.000。"""
    line = adv.PitchingLine(W=10, L=0)
    assert adv.win_pct(line) == 1.000


def test_win_pct_no_decisions():
    """W + L = 0 → None (no-decision のみ救援投手等)。"""
    line = adv.PitchingLine(W=0, L=0)
    assert adv.win_pct(line) is None


def test_win_pct_all_losses():
    """0 勝 10 敗 → 0.000。"""
    line = adv.PitchingLine(W=0, L=10)
    assert adv.win_pct(line) == 0.000


def test_all_pitcher_metrics_includes_win_pct():
    """all_pitcher_metrics dict に WIN_PCT key が含まれる。"""
    line = adv.PitchingLine(IP=100.0, W=8, L=4, H=80, ER=40, BB=20, SO=70)
    metrics = adv.all_pitcher_metrics(line)
    assert "WIN_PCT" in metrics
    assert metrics["WIN_PCT"] == round(8 / 12, 3)
    # ERA / WHIP も regression なしで残っている
    assert "ERA" in metrics
    assert "WHIP" in metrics


# ─── FieldingLine + fielding_pct ─────────────────────────────────────────


def test_fielding_line_defaults():
    """FieldingLine 全 0 default。"""
    line = adv.FieldingLine()
    assert line.PO == 0
    assert line.A == 0
    assert line.E == 0
    assert line.DP == 0


def test_fielding_pct_basic():
    """20 PO + 5 A + 1 E → 守備率 25/26 ≈ 0.9615。"""
    line = adv.FieldingLine(PO=20, A=5, E=1)
    expected = round(25 / 26, 4)
    assert adv.fielding_pct(line) == expected


def test_fielding_pct_no_errors():
    """E = 0 → 守備率 1.000。"""
    line = adv.FieldingLine(PO=50, A=10, E=0)
    assert adv.fielding_pct(line) == 1.0


def test_fielding_pct_no_chances():
    """機会 0 (PO=A=E=0) → None (空 fielding_logs safe)。"""
    line = adv.FieldingLine()
    assert adv.fielding_pct(line) is None


def test_all_fielding_metrics_has_fielding_pct():
    line = adv.FieldingLine(PO=30, A=15, E=2)
    metrics = adv.all_fielding_metrics(line)
    assert "FIELDING_PCT" in metrics
    assert metrics["FIELDING_PCT"] == round(45 / 47, 4)


# ─── ETL aggregation: W/L from result_mark ──────────────────────────────


def _open_db(tmp_path):
    db = tmp_path / "t.db"
    return insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)


def _seed_game(conn, *, game_id, game_date, opponent="t", home_away="home"):
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, ?, ?, 0, 0, '', '', 'test', ?)",
        (game_id, game_date, opponent, home_away, "2026-05-15T00:00:00Z"),
    )


def _seed_pitching(conn, *, game_id, player_canonical, IP, result_mark, H_allowed=0, K=0):
    conn.execute(
        "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
        "player_display, player_canonical, result_mark, pitches, BF, IP, "
        "H_allowed, HR_allowed, BB, HBP, K, R, ER) "
        "VALUES (?, 'home', 1, ?, ?, ?, 100, 30, ?, ?, 0, 0, 0, ?, 0, 0)",
        (game_id, player_canonical, player_canonical, result_mark, IP, H_allowed, K),
    )


def _seed_fielding(conn, *, game_id, player_canonical, PO, A, E, position="P", innings=9.0):
    conn.execute(
        "INSERT INTO fielding_logs (game_id, team_role, player_display, "
        "player_canonical, position, innings, PO, A, E, DP) "
        "VALUES (?, 'home', ?, ?, ?, ?, ?, ?, ?, 0)",
        (game_id, player_canonical, player_canonical, position, innings, PO, A, E),
    )


def test_aggregate_pitching_line_counts_w_l(tmp_path):
    """result_mark='勝'/'敗' から W/L が集計される。"""
    conn = _open_db(tmp_path)
    try:
        for i, mark in enumerate(["勝", "勝", "勝", "敗", ""]):
            gid = f"g{i}"
            _seed_game(conn, game_id=gid, game_date="2026-05-10")
            _seed_pitching(conn, game_id=gid, player_canonical="エース", IP=7.0,
                           result_mark=mark, K=5)
        conn.commit()
        line = insight_etl._aggregate_pitching_line(
            conn, "エース", "2026-05-01", "2026-05-31",
        )
        assert line.W == 3
        assert line.L == 1
        assert adv.win_pct(line) == 0.750
    finally:
        conn.close()


def test_aggregate_fielding_line_sums_po_a_e(tmp_path):
    """fielding_logs の PO/A/E が集計される。"""
    conn = _open_db(tmp_path)
    try:
        for i, (po, a, e) in enumerate([(10, 3, 0), (12, 4, 1), (8, 2, 0)]):
            gid = f"f{i}"
            _seed_game(conn, game_id=gid, game_date="2026-05-10")
            _seed_fielding(conn, game_id=gid, player_canonical="一塁手",
                           PO=po, A=a, E=e, position="1B")
        conn.commit()
        line = insight_etl._aggregate_fielding_line(
            conn, "一塁手", "2026-05-01", "2026-05-31",
        )
        assert line.PO == 30
        assert line.A == 9
        assert line.E == 1
        assert adv.fielding_pct(line) == round(39 / 40, 4)
    finally:
        conn.close()


def test_aggregate_fielding_line_empty_is_safe(tmp_path):
    """fielding_logs 空 (NPB 公式 box 未取得時) でも safe に 0 を返す。"""
    conn = _open_db(tmp_path)
    try:
        line = insight_etl._aggregate_fielding_line(
            conn, "誰でもない", "2026-05-01", "2026-05-31",
        )
        assert line.PO == 0
        assert adv.fielding_pct(line) is None
    finally:
        conn.close()


# ─── publisher 日本語 label mapping ──────────────────────────────────────


def test_human_metric_label_japanese():
    """K_per_9 → 奪三振率、 WIN_PCT → 勝率 等。"""
    assert pub._human_metric_label("K_per_9") == "奪三振率"
    assert pub._human_metric_label("BB_per_9") == "与四球率"
    assert pub._human_metric_label("HR_per_9") == "被本塁打率"
    assert pub._human_metric_label("WIN_PCT") == "勝率"
    assert pub._human_metric_label("FIELDING_PCT") == "守備率"
    assert pub._human_metric_label("RISP") == "得点圏打率"
    assert pub._human_metric_label("AVG") == "打率"
    assert pub._human_metric_label("ERA") == "防御率"


def test_human_metric_label_keeps_english_for_ops_only():
    """OPS だけ spec 例外で英略号のまま。"""
    assert pub._human_metric_label("OPS") == "OPS"
    assert pub._human_metric_label("WAR") == "総合貢献度"


def test_human_metric_label_unknown_fallback():
    """mapping 不在の metric は原文 fallback。"""
    assert pub._human_metric_label("UNKNOWN_METRIC") == "UNKNOWN_METRIC"


def test_human_metric_label_x_metric_internal_display():
    """× metric が漏れても user-facing label は日本語に寄せる。"""
    assert pub._human_metric_label("wOBA") == "加重出塁率"
    assert pub._human_metric_label("FIP") == "守備非依存防御率"
    assert pub._human_metric_label("WHIP") == "1イニングあたり被出塁数"
