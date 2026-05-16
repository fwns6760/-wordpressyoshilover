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
        assert second["reason"] == "cooldown_active"
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
