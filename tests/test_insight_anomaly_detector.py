"""Tests for insight_anomaly_detector + anomaly_article_publisher
(DATA-INSIGHT-continuous Iteration B)."""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis import insight_anomaly_detector as det  # noqa: E402
from src.analysis import anomaly_article_publisher as pub  # noqa: E402

TODAY = dt.date.today().isoformat()


def _seed_snapshots(conn, *, snapshot_date, scope, metric, ranking):
    """ranking = list of (player, team, value, sample, rank, total)"""
    for player, team, value, sample, rank, total in ranking:
        conn.execute(
            "INSERT INTO advanced_metric_snapshots "
            "(snapshot_date, scope, player_canonical, team_code, "
            "metric_name, metric_value, sample_size, league_rank, league_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_date, scope, player, team, metric, value, sample, rank, total),
        )
    conn.commit()


def _seed_player_table(conn, players):
    insight_etl.seed_teams(conn)
    for canonical, team_code, role in players:
        conn.execute(
            "INSERT OR IGNORE INTO players (player_canonical, team_code, role, active) "
            "VALUES (?, ?, ?, 1)",
            (canonical, team_code, role),
        )
    conn.commit()


def _insert_candidate(
    conn,
    *,
    signal_type,
    player="巨人A",
    current_value="OPS=1.000 rank=1",
    baseline_value="league_mean=0.700",
    window_label="last_30d_2026-05-16",
    notes="metric=OPS scope=last_30d",
    priority=1,
    created_at="2026-05-16T00:00:00+00:00",
):
    conn.execute(
        "INSERT OR IGNORE INTO insight_runs "
        "(run_id, run_ts, window_start, window_end, n_candidates, notes) "
        "VALUES (?, ?, NULL, NULL, 0, ?)",
        ("test-run", created_at, "test"),
    )
    cur = conn.execute(
        "INSERT INTO article_candidates (run_id, game_id, player_canonical, "
        "player_display, signal_type, magnitude, baseline_value, current_value, "
        "window_label, comparison_target, evidence_json, priority, status, "
        "created_at, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "test-run",
            None,
            player,
            player,
            signal_type,
            0.1,
            baseline_value,
            current_value,
            window_label,
            "league",
            "{}",
            priority,
            "NEW",
            created_at,
            notes,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _central_zscore_ranking():
    return [
        ("阪神A", "t", 0.700, 50, 2, 6),
        ("広島A", "c", 0.700, 50, 3, 6),
        ("DeNAA", "db", 0.700, 50, 4, 6),
        ("中日A", "d", 0.700, 50, 5, 6),
        ("ヤクルトA", "s", 0.700, 50, 6, 6),
        ("巨人A", "g", 1.500, 100, 1, 6),
    ]


def test_zscore_batter_detects_outlier(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        # 5 average + 1 outlier (+3σ程度)
        ranking = [(f"avg_{i}", "t", 0.700 + i * 0.005, 50, i + 2, 6) for i in range(5)]
        ranking.append(("巨人A", "g", 1.500, 100, 1, 6))
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d",
                        metric="OPS", ranking=ranking)
        ids = det.detect_zscore_batter_outliers(
            conn, snapshot_date="2026-05-14", threshold_sigma=2.0,
        )
        assert len(ids) >= 1
        rows = conn.execute(
            "SELECT signal_type, player_canonical FROM article_candidates "
            "WHERE candidate_id IN (" + ",".join("?" * len(ids)) + ")", ids,
        ).fetchall()
        assert any("巨人A" == r[1] for r in rows)
        assert all(r[0] == det.SIGNAL_ZSCORE_BATTER for r in rows)
    finally:
        conn.close()


def test_zscore_pitcher_detects_lower_is_better_outlier(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        # ERA は lower is better、平均 3.5、巨人エース 0.8 (平均から -2σ 以上)
        ranking = [(f"avg_p{i}", "t", 3.5 + i * 0.1, 30, i + 2, 6) for i in range(5)]
        ranking.append(("巨人E", "g", 0.500, 50, 1, 6))
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="season",
                        metric="ERA", ranking=ranking)
        ids = det.detect_zscore_pitcher_outliers(
            conn, snapshot_date="2026-05-14", metric_name="ERA",
            threshold_sigma=2.0,
        )
        assert len(ids) >= 1
        rows = conn.execute(
            "SELECT player_canonical FROM article_candidates "
            "WHERE candidate_id IN (" + ",".join("?" * len(ids)) + ")", ids,
        ).fetchall()
        assert any("巨人E" == r[0] for r in rows)
    finally:
        conn.close()


def test_babip_divergence_is_blocked_by_whitelist(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="AVG",
                        ranking=[("luck", "t", 0.300, 60, 1, 1)])
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d", metric="BABIP",
                        ranking=[("luck", "t", 0.420, 60, 1, 1)])  # +0.120 over AVG
        ids = det.detect_babip_divergence(conn, snapshot_date="2026-05-14")
        assert ids == []
        cnt = conn.execute(
            "SELECT COUNT(*) FROM article_candidates "
            "WHERE signal_type = ?", (det.SIGNAL_BABIP_DIVERGENCE,),
        ).fetchone()[0]
        assert cnt == 0
    finally:
        conn.close()


def test_fip_era_divergence_is_blocked_by_whitelist(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="season", metric="ERA",
                        ranking=[("lucky_pitcher", "t", 1.500, 30, 1, 1)])
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="season", metric="FIP",
                        ranking=[("lucky_pitcher", "t", 4.500, 30, 1, 1)])  # +3.0 vs ERA
        ids = det.detect_fip_era_divergence(conn, snapshot_date="2026-05-14")
        assert ids == []
        cnt = conn.execute(
            "SELECT COUNT(*) FROM article_candidates "
            "WHERE signal_type = ?", (det.SIGNAL_FIP_ERA_DIVERGENCE,),
        ).fetchone()[0]
        assert cnt == 0
    finally:
        conn.close()


def test_giants_top_outliers(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        ranking = [
            ("巨人A", "g", 0.95, 90, 2, 100),  # top 2/100 = 2% in top 5%
            ("巨人B", "g", 0.85, 80, 30, 100),  # top 30/100 = 30%, not in top 5%
        ]
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d",
                        metric="OPS", ranking=ranking)
        ids = det.detect_giants_top_outliers(
            conn, snapshot_date="2026-05-14", top_pct=0.05,
        )
        assert len(ids) == 1  # 巨人A only
        row = conn.execute(
            "SELECT player_canonical FROM article_candidates "
            "WHERE candidate_id = ?", (ids[0],),
        ).fetchone()
        assert row[0] == "巨人A"
    finally:
        conn.close()


def test_run_all_anomaly_detectors_handles_empty_db(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        result = det.run_all_anomaly_detectors(conn)
        assert isinstance(result, dict)
        # all detectors return [] on empty data
        for sig in det.ALL_ANOMALY_SIGNALS:
            assert result.get(sig) == []
    finally:
        conn.close()


def test_run_all_anomaly_detectors_reports_partial_failures(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(det, "detect_game_hero_batter", boom)
    try:
        result = det.run_all_anomaly_detectors(conn)
        assert result.get(det.SIGNAL_GAME_HERO_BATTER) == []
        errors = result.get(det.DETECTOR_ERROR_KEY, [])
        assert any(
            det.SIGNAL_GAME_HERO_BATTER in e and "RuntimeError:boom" in e
            for e in errors
        )
    finally:
        conn.close()


def test_dedup_within_7days(tmp_path):
    """同 player + 同 signal_type + 同 window_label を 7 日以内で再 insert しない."""
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        ranking = [(f"avg_{i}", "t", 0.700, 50, i + 2, 6) for i in range(5)]
        ranking.append(("巨人A", "g", 1.500, 100, 1, 6))
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d",
                        metric="OPS", ranking=ranking)
        ids1 = det.detect_zscore_batter_outliers(conn, snapshot_date="2026-05-14")
        ids2 = det.detect_zscore_batter_outliers(conn, snapshot_date="2026-05-14")
        # 2 回目は dedup で 0
        assert len(ids1) >= 1
        assert len(ids2) == 0
    finally:
        conn.close()


def test_zscore_dedup_same_player_metric_across_periods(tmp_path):
    """同じ player + metric は last_30d / season の期間違いを 7日内で重ねない。"""
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        for scope in ("last_30d", "season"):
            ranking = [(f"avg_{scope}_{i}", "t", 0.700 + i * 0.005, 50, i + 2, 6)
                       for i in range(5)]
            ranking.append(("巨人A", "g", 1.500, 100, 1, 6))
            _seed_snapshots(
                conn,
                snapshot_date="2026-05-14",
                scope=scope,
                metric="OPS",
                ranking=ranking,
            )
        ids1 = det.detect_zscore_batter_outliers(
            conn, snapshot_date="2026-05-14", scope="last_30d",
        )
        ids2 = det.detect_zscore_batter_outliers(
            conn, snapshot_date="2026-05-14", scope="season",
        )
        assert len(ids1) >= 1
        assert ids2 == []
    finally:
        conn.close()


def test_render_anomaly_article_zscore_batter(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_player_table(conn, [("巨人A", "g", "player")])
        cand = {
            "signal_type": det.SIGNAL_ZSCORE_BATTER,
            "player_canonical": "巨人A",
            "magnitude": 2.5,
            "baseline_value": "league_mean=0.700 std=0.050 n=20",
            "current_value": "OPS=1.200 sample=90",
            "notes": "team=g metric=OPS",
        }
        result = pub.render_anomaly_article(conn, cand)
        assert result is not None
        assert "巨人A" in result["title"]
        assert "OPS" in result["title"]
        assert "<table>" in result["body_html"]
        assert "<svg" not in result["body_html"]
    finally:
        conn.close()


def test_direct_fip_babip_renderers_are_blocked(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_player_table(conn, [("巨人A", "g", "player")])
        babip = {
            "signal_type": det.SIGNAL_BABIP_DIVERGENCE,
            "player_canonical": "巨人A",
            "magnitude": 0.120,
            "baseline_value": "AVG=0.300",
            "current_value": "BABIP=0.420",
        }
        fip = {
            "signal_type": det.SIGNAL_FIP_ERA_DIVERGENCE,
            "player_canonical": "巨人A",
            "magnitude": 1.500,
            "baseline_value": "ERA=2.000",
            "current_value": "FIP=3.500",
        }
        assert pub.render_babip_divergence_article(conn, babip) is None
        assert pub.render_fip_era_divergence_article(conn, fip) is None
    finally:
        conn.close()


def test_publish_anomaly_drafts_dry_run(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_player_table(conn, [("巨人A", "g", "player")])
        # candidate を直接 insert
        _seed_snapshots(conn, snapshot_date=TODAY, scope="last_30d",
                        metric="OPS", ranking=_central_zscore_ranking())
        det.detect_zscore_batter_outliers(conn, snapshot_date=TODAY)

        wp_mock = MagicMock()
        results = pub.publish_anomaly_drafts(
            conn, wp_mock, max_per_run=2, dry_run=True,
        )
        assert any(r.get("status") == "dry_run" for r in results)
        # WP method は dry_run で呼ばれない
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()


def test_publish_anomaly_drafts_marks_drafted(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_player_table(conn, [("巨人A", "g", "player")])
        _seed_snapshots(conn, snapshot_date=TODAY, scope="last_30d",
                        metric="OPS", ranking=_central_zscore_ranking())
        det.detect_zscore_batter_outliers(conn, snapshot_date=TODAY)

        wp_mock = MagicMock()
        wp_mock.create_category.return_value = 675
        wp_mock.create_post.return_value = 12345
        results = pub.publish_anomaly_drafts(conn, wp_mock, max_per_run=2)
        published = [r for r in results if r.get("status") == "published_draft"]
        assert len(published) >= 1
        # status が DRAFTED に更新されたか
        statuses = [r[0] for r in conn.execute(
            "SELECT status FROM article_candidates WHERE signal_type = ?",
            (det.SIGNAL_ZSCORE_BATTER,),
        )]
        assert any(s == "DRAFTED" for s in statuses)
        # status='draft' で投稿されたか
        for c in wp_mock.create_post.call_args_list:
            assert c.kwargs.get("status") == "draft"
    finally:
        conn.close()


def test_cleanup_anomaly_queue_expires_stale_and_drops_disabled_signals(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    now = dt.datetime(2026, 5, 16, 12, 0, tzinfo=dt.timezone.utc)
    try:
        expired_id = _insert_candidate(
            conn,
            signal_type=det.SIGNAL_DEFENSE_UZR_OUTLIER,
            player="古い巨人",
            current_value="RF_proxy=0.900",
            notes="position=遊 metric=UZR_proxy scope=last_30d",
            created_at="2026-05-13T12:00:00+00:00",
        )
        disabled_id = _insert_candidate(
            conn,
            signal_type="pitcher_workload_warning",
            player="対象外巨人",
            created_at="2026-05-16T11:00:00+00:00",
        )
        kept_id = _insert_candidate(
            conn,
            signal_type=det.SIGNAL_DEFENSE_FIELDING_PCT,
            player="残す巨人",
            current_value="fielding_pct=0.990",
            notes="position=遊 metric=FIELDING_PCT scope=last_30d",
            created_at="2026-05-16T11:00:00+00:00",
        )

        summary = pub.cleanup_anomaly_queue(conn, ttl_hours=48, now=now)

        statuses = dict(conn.execute(
            "SELECT candidate_id, status FROM article_candidates"
        ).fetchall())
        assert summary["expired"] == 1
        assert summary["disabled_signal"] == 1
        assert statuses[expired_id] == pub.QUEUE_STATUS_EXPIRED
        assert statuses[disabled_id] == pub.QUEUE_STATUS_DROPPED_DISABLED_SIGNAL
        assert statuses[kept_id] == "NEW"
    finally:
        conn.close()


def test_publish_anomaly_drafts_caps_same_metric_per_run(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        first_id = _insert_candidate(
            conn,
            signal_type=det.SIGNAL_DEFENSE_UZR_OUTLIER,
            player="泉口友汰",
            current_value="RF_proxy=0.912",
            baseline_value="position_avg=1.000",
            notes="position=遊 metric=UZR_proxy scope=last_30d",
            created_at="2026-05-16T11:00:00+00:00",
        )
        second_id = _insert_candidate(
            conn,
            signal_type=det.SIGNAL_DEFENSE_UZR_OUTLIER,
            player="中山礼都",
            current_value="RF_proxy=0.901",
            baseline_value="position_avg=1.000",
            notes="position=遊 metric=UZR_proxy scope=last_30d",
            created_at="2026-05-16T10:59:00+00:00",
        )

        wp_mock = MagicMock()
        wp_mock.create_category.return_value = 675
        wp_mock.create_post.return_value = 12345

        results = pub.publish_anomaly_drafts(
            conn,
            wp_mock,
            max_per_run=3,
            cleanup_queue=False,
            metric_max_per_run=1,
        )

        assert [r["status"] for r in results].count("published_draft") == 1
        skipped = [r for r in results if r.get("status") == "skip_metric_run_cap"]
        assert len(skipped) == 1
        assert skipped[0]["metric_name"] == "UZR_proxy"
        wp_mock.create_post.assert_called_once()
        statuses = dict(conn.execute(
            "SELECT candidate_id, status FROM article_candidates"
        ).fetchall())
        assert statuses[first_id] == "DRAFTED"
        assert statuses[second_id] == pub.QUEUE_STATUS_DROPPED_METRIC_RUN_CAP
    finally:
        conn.close()


def test_publish_anomaly_drafts_dry_run_does_not_cleanup_or_mutate_status(tmp_path):
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        disabled_id = _insert_candidate(
            conn,
            signal_type="pitcher_workload_warning",
            player="対象外巨人",
            created_at="2026-05-13T12:00:00+00:00",
        )
        publishable_id = _insert_candidate(
            conn,
            signal_type=det.SIGNAL_DEFENSE_UZR_OUTLIER,
            player="泉口友汰",
            current_value="RF_proxy=0.912",
            baseline_value="position_avg=1.000",
            notes="position=遊 metric=UZR_proxy scope=last_30d",
            created_at="2026-05-13T12:00:00+00:00",
        )

        wp_mock = MagicMock()
        pub.publish_anomaly_drafts(
            conn,
            wp_mock,
            max_per_run=3,
            dry_run=True,
            cleanup_queue=True,
        )

        statuses = dict(conn.execute(
            "SELECT candidate_id, status FROM article_candidates"
        ).fetchall())
        assert statuses[disabled_id] == "NEW"
        assert statuses[publishable_id] == "NEW"
        wp_mock.create_post.assert_not_called()
    finally:
        conn.close()
