"""Tests for issue #44 C: HR 列 bug 解消.

Bug: ``batting_logs`` schema は ``AB, R, H, RBI, SB`` のみで **HR 列が無い**
(HR は ``atbats_json`` 内に格納)。 にもかかわらず ``insight_nightly.py:524``
は ``{"stat_col": "HR", "table": "batting_logs"}`` を ``counting_metrics``
list に含めており、 ``aggregate_player_counting_stat`` が ``SUM(bl.HR)``
を発行 → 毎 nightly run で 8 件 ``OperationalError: no such column: bl.HR``
を log 出力、 HR ranking 記事は一切 publish されない (commit 21a8e7a 由来)。

Fix (1 段階): ``counting_metrics`` から HR 行を除外。 atbats_json 経由の
HR 集計は別 ticket。
"""

from __future__ import annotations

from src.analysis import insight_nightly


def test_counting_metrics_excludes_hr_from_batting_logs():
    """COUNTING_METRICS 定数に batting_logs.HR の entry が含まれないこと.

    batting_logs schema に HR 列が無いため、 SUM(bl.HR) は
    OperationalError を毎 nightly 8 回発生させていた。
    """
    metrics = insight_nightly.COUNTING_METRICS
    assert isinstance(metrics, (list, tuple))
    bad = [
        m for m in metrics
        if m.get("stat_col") == "HR" and m.get("table") == "batting_logs"
    ]
    assert not bad, (
        f"batting_logs に HR 列は無いのに HR entry が残っている: {bad}"
    )


def test_counting_metrics_still_has_expected_active_metrics():
    """残る 4 metric (H / RBI / SB batter + K pitcher) は維持される."""
    metrics = insight_nightly.COUNTING_METRICS
    keys = {(m["stat_col"], m["table"]) for m in metrics}
    expected_required = {
        ("H", "batting_logs"),
        ("RBI", "batting_logs"),
        ("SB", "batting_logs"),
        ("K", "pitching_logs"),
    }
    missing = expected_required - keys
    assert not missing, (
        f"必要な counting metric が消えている: {missing} (current: {keys})"
    )
