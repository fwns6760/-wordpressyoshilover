"""464 / issue #44 B 再活性化 (2026-06-02, user「読者にわかりやすい角度を優先」).

旧: ``run_all_anomaly_detectors`` が ``detect_game_hero_batter`` /
``detect_game_pitcher_performance`` を skip (issue#44 B、 1 試合 postgame data
記事の乱発を止めるため 2026-05-17 完全 off)。

新: 「今日のヒーロー」「今日の好投」 は読者に一目でわかる最有力角度なので再活性化。
ただし乱発の真因 (緩い gate) を断つため detector 側の閾値を厳格化:
  - hero: H>=3 / HR+RBI2 / RBI3 / マルチ HR のみ (旧 H>=2&RBI1 / 単発 HR 撤去)
  - 好投: 真 QS (IP>=6 ER<=2) / 救援無失点 S/H/勝 のみ (旧 IP>=5 準 QS と不調撤去)

本 test は「強い活躍は emit / 平凡な活躍は除外」を両面 lock する。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.analysis import insight_anomaly_detector as det
from src.analysis import insight_etl


REPO = Path(__file__).resolve().parents[1]


def _open_seed_db(tmp_path: Path) -> sqlite3.Connection:
    conn = insight_etl.open_db(
        db_path=tmp_path / "insight.db",
        schema_path=insight_etl.DEFAULT_SCHEMA,
    )
    insight_etl.seed_teams(conn)
    return conn


def _seed_game(conn: sqlite3.Connection, snapshot_date: str, suffix: str) -> str:
    game_id = f"{snapshot_date}:test-g-{suffix}"
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (game_id, snapshot_date, "DeNA", "home", 5, 2, "win", "test://",
         "test", "2026-06-02T00:00:00Z"),
    )
    return game_id


def _add_batter(conn, game_id, name, ab, r, h, rbi, atbats_json="[]"):
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, player_display, "
        "player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json, team_name) "
        "VALUES (?, 'giants', 1, ?, ?, 0, ?, ?, ?, ?, 0, ?, '巨人')",
        (game_id, name, name, ab, r, h, rbi, atbats_json),
    )


def _add_pitcher(conn, game_id, name, ip, er, k, mark):
    conn.execute(
        "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
        "player_display, player_canonical, result_mark, IP, BF, H_allowed, "
        "HR_allowed, BB, HBP, K, R, ER, team_name) "
        "VALUES (?, 'giants', 1, ?, ?, ?, ?, 20, 5, 0, 1, 0, ?, ?, ?, '巨人')",
        (game_id, name, name, mark, ip, k, er, er),
    )


# ── hero 打者: 強い活躍は emit ──────────────────────────────────────────────

def test_hero_strong_line_is_emitted(tmp_path):
    """3 安打 (固め打ち) は再活性化後 emit される。"""
    conn = _open_seed_db(tmp_path)
    try:
        gid = _seed_game(conn, "2026-06-01", "hero")
        _add_batter(conn, gid, "固め打ち選手", ab=4, r=1, h=3, rbi=1)
        conn.commit()
        out = det.run_all_anomaly_detectors(conn, snapshot_date="2026-06-01")
        assert det.SIGNAL_GAME_HERO_BATTER in out
        assert len(out[det.SIGNAL_GAME_HERO_BATTER]) >= 1, "強い活躍が emit されていない"
    finally:
        conn.close()


def test_hero_marginal_line_is_excluded(tmp_path):
    """2 安打 1 打点 (旧 gate で拾っていた平凡な活躍) は厳格化で除外。"""
    conn = _open_seed_db(tmp_path)
    try:
        gid = _seed_game(conn, "2026-06-01", "marg")
        _add_batter(conn, gid, "平凡選手", ab=4, r=0, h=2, rbi=1)
        conn.commit()
        out = det.run_all_anomaly_detectors(conn, snapshot_date="2026-06-01")
        assert out.get(det.SIGNAL_GAME_HERO_BATTER) == [], (
            f"平凡な 2 安打 1 打点が除外されていない: {out.get(det.SIGNAL_GAME_HERO_BATTER)}"
        )
    finally:
        conn.close()


# ── 好投 投手: 真 QS は emit、 準 QS / 不調は除外 ──────────────────────────

def test_pitcher_true_qs_is_emitted(tmp_path):
    """6 回 2 自責 (真 QS) は emit。"""
    conn = _open_seed_db(tmp_path)
    try:
        gid = _seed_game(conn, "2026-06-01", "qs")
        _add_pitcher(conn, gid, "好投先発", ip=6.0, er=2, k=7, mark="勝")
        conn.commit()
        out = det.run_all_anomaly_detectors(conn, snapshot_date="2026-06-01")
        assert len(out.get(det.SIGNAL_GAME_PITCHER_PERF, [])) >= 1, "真 QS が emit されていない"
    finally:
        conn.close()


def test_pitcher_sub_qs_and_blowup_excluded(tmp_path):
    """5 回 2 自責 (準 QS) と 4 回 4 自責 (不調) はどちらも除外。"""
    conn = _open_seed_db(tmp_path)
    try:
        gid = _seed_game(conn, "2026-06-01", "weak")
        _add_pitcher(conn, gid, "準QS先発", ip=5.0, er=2, k=4, mark="")
        gid2 = _seed_game(conn, "2026-06-01", "ko")
        _add_pitcher(conn, gid2, "炎上先発", ip=4.0, er=4, k=2, mark="敗")
        conn.commit()
        out = det.run_all_anomaly_detectors(conn, snapshot_date="2026-06-01")
        assert out.get(det.SIGNAL_GAME_PITCHER_PERF) == [], (
            f"準 QS / 不調が除外されていない: {out.get(det.SIGNAL_GAME_PITCHER_PERF)}"
        )
    finally:
        conn.close()


# ── team code resolver 配線 (464 NameError 回帰防止) ────────────────────────

def test_team_code_resolver_is_wired():
    """本塁打ペース / 連続多安打 が使う team 名→code resolver が import 済 (NameError 防止)。

    これらは作成以来 dormant だったため ``_resolve_team_code_from_name`` 未 import の
    NameError が顕在化しておらず、 464 再活性化で初めて露呈した。 12 球団網羅を lock。
    """
    assert det._resolve_team_code_from_name("読売ジャイアンツ") == "g"
    assert det._resolve_team_code_from_name("阪神タイガース") == "t"
    assert det._resolve_team_code_from_name("") == "unknown"


# ── サバメ / 変化率 はわかりにくいため OFF 維持 (回帰防止) ──────────────────

def test_confusing_signals_remain_off(tmp_path):
    """BABIP / FIP-ERA / 規定外好調 / 変化率 は据え置き (空) であること。"""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_game(conn, "2026-06-01", "off")
        conn.commit()
        out = det.run_all_anomaly_detectors(conn, snapshot_date="2026-06-01")
        for sig in (
            det.SIGNAL_BABIP_DIVERGENCE,
            det.SIGNAL_FIP_ERA_DIVERGENCE,
            det.SIGNAL_HIDDEN_OPS_LIMIT,
            det.SIGNAL_STAT_DELTA,
        ):
            assert out.get(sig) == [], f"{sig} が OFF 維持されていない: {out.get(sig)}"
    finally:
        conn.close()
