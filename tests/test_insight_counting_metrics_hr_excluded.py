"""Tests for issue #44 G (initial) + G follow-up: HR 列 → atbats_json 集計移行.

Bug 履歴:
- batting_logs schema は AB / R / H / RBI / SB のみで HR 列が無く、
  SUM(bl.HR) は毎 nightly run で 8 件 OperationalError を出していた
- commit 4f4a603 (初期 fix) で HR を COUNTING_METRICS から除外 → error は止まったが
  HR ranking 記事 publish も止まる side effect

G follow-up (本 test を反転):
- ``ranking_article_publisher.aggregate_player_counting_stat`` が stat_col="HR"
  を検出して ``aggregate_player_hr_from_atbats`` に dispatch する仕様に変更
- HR entry を COUNTING_METRICS に再追加、 SQL error 出さず本塁打数 ranking 記事を
  publish する
"""

from __future__ import annotations

from src.analysis import insight_nightly


def test_counting_metrics_includes_hr_for_atbats_dispatch():
    """COUNTING_METRICS に batting_logs.HR の entry が含まれること.

    issue #44 G follow-up: aggregate_player_counting_stat が stat_col="HR" 検出時に
    atbats_json 経由の集計に dispatch するため、 HR entry を維持する。
    """
    metrics = insight_nightly.COUNTING_METRICS
    assert isinstance(metrics, (list, tuple))
    hr_entries = [
        m for m in metrics
        if m.get("stat_col") == "HR" and m.get("table") == "batting_logs"
    ]
    assert hr_entries, (
        "HR entry が COUNTING_METRICS に含まれていない (本塁打数 ranking 記事が publish されない)"
    )
    assert hr_entries[0].get("metric_label_jp") == "本塁打数", (
        f"HR の label が「本塁打数」でない: {hr_entries[0]}"
    )


def test_counting_metrics_still_has_expected_active_metrics():
    """既存 4 metric (H / RBI / SB batter + K pitcher) は維持される (退行防止)."""
    metrics = insight_nightly.COUNTING_METRICS
    keys = {(m["stat_col"], m["table"]) for m in metrics}
    expected_required = {
        ("H", "batting_logs"),
        ("HR", "batting_logs"),
        ("RBI", "batting_logs"),
        ("SB", "batting_logs"),
        ("K", "pitching_logs"),
    }
    missing = expected_required - keys
    assert not missing, (
        f"必要な counting metric が消えている: {missing} (current: {keys})"
    )
