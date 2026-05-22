"""Tests for DATA-INSIGHT duplicate cooldown gate (349)."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_dedup_gate as gate  # noqa: E402
from src.analysis import insight_etl  # noqa: E402
from src.analysis import insight_whitelist as wl  # noqa: E402


def _open_db(tmp_path):
    return insight_etl.open_db(db_path=tmp_path / "t.db", schema_path=insight_etl.DEFAULT_SCHEMA)


def setup_function():
    wl.reset_cache()


def teardown_function():
    wl.reset_cache()


def test_metric_cooldown_blocks_same_player_metric_within_7_days(tmp_path):
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 16, 0, 0, tzinfo=dt.timezone.utc)
    try:
        first = gate.evaluate_metric_cooldown(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.800,
            rank=7,
            total=60,
            now=now,
        )
        assert first["allowed"] is True
        gate.record_metric_publish(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.800,
            rank=7,
            total=60,
            title="大城 OPS",
            post_id=1,
            wp_status="publish",
            now=now,
        )
        second = gate.evaluate_metric_cooldown(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="season",
            value=0.805,
            rank=8,
            total=60,
            now=now + dt.timedelta(hours=3),
        )
        assert second["allowed"] is False
        # same JST calendar day → same_day_block (overrides value/band bypass).
        assert second["reason"] == "same_day_block"
        assert second["scope_family"] == "metric_all_periods"
    finally:
        conn.close()


def test_metric_cooldown_allows_after_7_days(tmp_path):
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 16, 0, 0, tzinfo=dt.timezone.utc)
    try:
        gate.record_metric_publish(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.800,
            rank=6,
            total=60,
            title="大城 OPS",
            post_id=1,
            wp_status="publish",
            now=now,
        )
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.805,
            rank=7,
            total=60,
            now=now + dt.timedelta(days=8),
        )
        assert decision["allowed"] is True
        assert decision["reason"] == "cooldown_expired"
    finally:
        conn.close()


def test_metric_cooldown_allows_large_value_delta(tmp_path):
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 16, 0, 0, tzinfo=dt.timezone.utc)
    try:
        gate.record_metric_publish(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.800,
            rank=6,
            total=60,
            title="大城 OPS",
            post_id=1,
            wp_status="publish",
            now=now,
        )
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.850,
            rank=6,
            total=60,
            now=now + dt.timedelta(days=1),
        )
        assert decision["allowed"] is True
        assert decision["reason"] == "value_delta"
    finally:
        conn.close()


def test_metric_cooldown_allows_rank_band_change(tmp_path):
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 16, 0, 0, tzinfo=dt.timezone.utc)
    try:
        gate.record_metric_publish(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.800,
            rank=20,
            total=60,
            title="大城 OPS",
            post_id=1,
            wp_status="publish",
            now=now,
        )
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="大城卓三",
            metric_name="OPS",
            scope="last_7d",
            value=0.805,
            rank=5,
            total=60,
            now=now + dt.timedelta(days=1),
        )
        assert decision["allowed"] is True
        assert decision["reason"] == "rank_band_changed"
    finally:
        conn.close()


# ── same-day block (Type A + Type C 撲滅) ──────────────────────────────────


def test_same_day_block_overrides_large_value_delta(tmp_path):
    """同日に同 player×同 metric を再 publish しようとすると、 value_delta が
    大きくても same_day_block で弾く (前: value_delta bypass で通っていた)。"""
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 21, 0, 6, tzinfo=dt.timezone.utc)  # JST 09:06
    try:
        gate.record_metric_publish(
            conn,
            subject_key="大勢",
            metric_name="ERA_8回登板",
            scope="last_5_games",
            value=3.0,
            rank=13,
            total=30,
            title="大勢 防御率 3.0",
            post_id=1,
            wp_status="publish",
            now=now,
        )
        # 8 hours later (同 JST 日付) — value 0.0 (差 3.0 = huge) でも block
        later = now + dt.timedelta(hours=8)
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="大勢",
            metric_name="ERA_8回登板",
            scope="last_5_games",
            value=0.0,
            rank=8,
            total=30,
            now=later,
        )
        assert decision["allowed"] is False
        assert decision["reason"] == "same_day_block"
    finally:
        conn.close()


def test_same_day_block_for_team_ranking(tmp_path):
    """team:g + TEAM_ERA を同日 2 回 publish しようとすると弾く (Type C)。"""
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 21, 0, 6, tzinfo=dt.timezone.utc)
    try:
        gate.record_metric_publish(
            conn,
            subject_key="team:g",
            metric_name="TEAM_ERA",
            scope="last_5_games",
            value=0.938,
            rank=1,
            total=6,
            title="球団防御率 1/6 0.938",
            post_id=1,
            wp_status="publish",
            now=now,
        )
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="team:g",
            metric_name="TEAM_ERA",
            scope="last_5_games",
            value=1.286,
            rank=1,
            total=6,
            now=now + dt.timedelta(hours=3),
        )
        assert decision["allowed"] is False
        assert decision["reason"] == "same_day_block"
    finally:
        conn.close()


def test_team_ranking_different_metric_same_day_passes(tmp_path):
    """team:g の TEAM_ERA を出した後、 同日に TEAM_HR は通る (cap B 対象外)。"""
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 21, 0, 6, tzinfo=dt.timezone.utc)
    try:
        gate.record_metric_publish(
            conn,
            subject_key="team:g",
            metric_name="TEAM_ERA",
            scope="last_5_games",
            value=0.938,
            rank=1,
            total=6,
            title="球団防御率",
            post_id=1,
            wp_status="publish",
            now=now,
        )
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="team:g",
            metric_name="TEAM_HR",
            scope="last_5_games",
            value=3,
            rank=2,
            total=6,
            now=now + dt.timedelta(hours=2),
        )
        assert decision["allowed"] is True
        assert decision["reason"] == "no_history"
    finally:
        conn.close()


# ── player daily cap (Type B 撲滅) ────────────────────────────────────────


def test_player_daily_cap_blocks_third_metric_same_day(tmp_path):
    """同 player を 1 日 cap=2 件 publish 済の後、 3 件目 (別 metric) は block。"""
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 21, 0, 6, tzinfo=dt.timezone.utc)
    try:
        for i, metric in enumerate(["OPS", "AVG"]):
            gate.record_metric_publish(
                conn,
                subject_key="ダルベック",
                metric_name=metric,
                scope="last_5_games",
                value=0.800 + i * 0.01,
                rank=5,
                total=60,
                title=f"ダルベック {metric}",
                post_id=10 + i,
                wp_status="publish",
                now=now + dt.timedelta(minutes=i),
            )
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="ダルベック",
            metric_name="SLG",
            scope="last_5_games",
            value=0.450,
            rank=3,
            total=60,
            now=now + dt.timedelta(hours=2),
        )
        assert decision["allowed"] is False
        assert decision["reason"] == "player_daily_cap"
        assert decision["today_count"] == 2
        assert decision["cap"] == 2
    finally:
        conn.close()


def test_player_daily_cap_resets_next_day(tmp_path):
    """cap=2 達成後、 翌 JST 日付に持ち越せば reset され通る。"""
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 21, 0, 6, tzinfo=dt.timezone.utc)
    try:
        for i, metric in enumerate(["OPS", "AVG"]):
            gate.record_metric_publish(
                conn,
                subject_key="ダルベック",
                metric_name=metric,
                scope="last_5_games",
                value=0.800 + i * 0.01,
                rank=5,
                total=60,
                title=f"ダルベック {metric}",
                post_id=20 + i,
                wp_status="publish",
                now=now + dt.timedelta(minutes=i),
            )
        next_day_jst = now + dt.timedelta(days=1)
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="ダルベック",
            metric_name="SLG",
            scope="last_5_games",
            value=0.450,
            rank=3,
            total=60,
            now=next_day_jst,
        )
        assert decision["allowed"] is True
        # past history for SLG: no_history (この (player, metric) は初出)
        assert decision["reason"] == "no_history"
    finally:
        conn.close()


def test_team_subject_exempt_from_player_daily_cap(tmp_path):
    """team:g は cap=2 から除外、 6 metric 全部出せる。"""
    conn = _open_db(tmp_path)
    now = dt.datetime(2026, 5, 21, 0, 6, tzinfo=dt.timezone.utc)
    try:
        for i, metric in enumerate(["TEAM_ERA", "TEAM_HR", "TEAM_AVG"]):
            gate.record_metric_publish(
                conn,
                subject_key="team:g",
                metric_name=metric,
                scope="last_5_games",
                value=1.0,
                rank=1,
                total=6,
                title=metric,
                post_id=30 + i,
                wp_status="publish",
                now=now + dt.timedelta(minutes=i),
            )
        # 4 個目 (別 metric) も通る — team:g は cap 対象外
        decision = gate.evaluate_metric_cooldown(
            conn,
            subject_key="team:g",
            metric_name="TEAM_RUN_DIFF",
            scope="last_5_games",
            value=4,
            rank=2,
            total=6,
            now=now + dt.timedelta(hours=2),
        )
        assert decision["allowed"] is True
        assert decision["reason"] == "no_history"
    finally:
        conn.close()
