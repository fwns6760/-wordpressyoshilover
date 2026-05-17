"""Tests for issue #44 H: insight_nightly main() の all_teams summary に
``anomaly_publish_summary`` / ``ranking_publish_summary`` が含まれない
バグの再現テスト。

Bug: ``src/analysis/insight_nightly.py:495,500`` で計算しているのに
``summary`` dict (line 620-) に格納されず、 ``json.dumps`` (line 635)
で stdout に出ない。 結果として gate skip 理由 (``skip_quality_gate`` /
``skip_dedup_cooldown`` / ``skip_metric_run_cap``) が Cloud Logging に
流れない。

Expectation: ENABLE_DATA_INSIGHT_AUTO_DRAFT 未設定 (= default disabled)
でも、 summary に ``anomaly_publish`` / ``ranking_publish`` の key が
入っていて、 default_disabled の reason が見えること。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis import insight_nightly


def test_main_all_teams_emits_anomaly_publish_in_log(monkeypatch, tmp_path, capsys):
    """auto-draft 既定 disabled 時でも anomaly_publish が summary に含まれる。"""
    monkeypatch.setattr(
        insight_nightly, "resolve_all_slugs_auto", lambda **kwargs: []
    )
    monkeypatch.setattr(
        insight_nightly.insight_markdown_summary,
        "write_digest",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        insight_nightly.insight_gcs_sync,
        "upload_state",
        lambda **kwargs: {"skipped": True, "reason": "test_stub"},
    )
    monkeypatch.delenv("ENABLE_DATA_INSIGHT_AUTO_DRAFT", raising=False)

    code = insight_nightly.main([
        "--auto", "--all-teams",
        "--date", "2026-05-16",
        "--db", str(tmp_path / "db.sqlite"),
        "--csv", str(tmp_path / "candidates.csv"),
        "--cache-dir", str(tmp_path / "cache"),
        "--digest-dir", str(tmp_path / "digest"),
    ])
    assert code == 0

    captured = capsys.readouterr()
    json_lines = [
        line for line in captured.out.strip().split("\n")
        if line.startswith("{")
    ]
    assert json_lines, f"no json output captured: {captured.out!r}"
    summary = json.loads(json_lines[-1])
    assert summary.get("status") == "ok"
    assert "anomaly_publish" in summary, (
        f"missing 'anomaly_publish' key; got keys={sorted(summary.keys())}"
    )
    assert summary["anomaly_publish"].get("skipped") is True
    assert summary["anomaly_publish"].get("reason") == "default_disabled"


def test_main_all_teams_emits_ranking_publish_in_log(monkeypatch, tmp_path, capsys):
    """auto-draft 既定 disabled 時でも ranking_publish が summary に含まれる。"""
    monkeypatch.setattr(
        insight_nightly, "resolve_all_slugs_auto", lambda **kwargs: []
    )
    monkeypatch.setattr(
        insight_nightly.insight_markdown_summary,
        "write_digest",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        insight_nightly.insight_gcs_sync,
        "upload_state",
        lambda **kwargs: {"skipped": True, "reason": "test_stub"},
    )
    monkeypatch.delenv("ENABLE_DATA_INSIGHT_AUTO_DRAFT", raising=False)

    code = insight_nightly.main([
        "--auto", "--all-teams",
        "--date", "2026-05-16",
        "--db", str(tmp_path / "db.sqlite"),
        "--csv", str(tmp_path / "candidates.csv"),
        "--cache-dir", str(tmp_path / "cache"),
        "--digest-dir", str(tmp_path / "digest"),
    ])
    assert code == 0

    captured = capsys.readouterr()
    json_lines = [
        line for line in captured.out.strip().split("\n")
        if line.startswith("{")
    ]
    assert json_lines, f"no json output captured: {captured.out!r}"
    summary = json.loads(json_lines[-1])
    assert "ranking_publish" in summary, (
        f"missing 'ranking_publish' key; got keys={sorted(summary.keys())}"
    )
    assert summary["ranking_publish"].get("skipped") is True
    assert summary["ranking_publish"].get("reason") == "default_disabled"
