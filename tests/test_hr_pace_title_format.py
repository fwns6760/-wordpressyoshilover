"""Tests for issue #44 B-3: render_hr_pace_article の title を case A 寄りに refit.

Bug: ``render_hr_pace_article`` の title は
``【巨人データ】{player}、直近 30 日 HR ペースを 143 試合換算で約 {N} 本ペース``
の 1 sentence 形で、 期間が title 中盤に embed されており case A spec
(2026-05-15 user lock) の「期間は末尾括弧」rule に反する。

Fix: title を ``【巨人データ】{player}、本塁打ペース 143 試合換算 約 {N} 本（直近30日）``
形に refit。 期間を末尾括弧へ移動、 短く読める形へ。

Note: HR ranking infrastructure (advanced_metric_snapshots に HR row 無し、
2026-05-17 commit 4f4a603 で counting_metrics から HR 除外) のため、
ranking 表 wire は別 ticket。 本 commit は title refit のみ。
"""

from __future__ import annotations

from src.analysis import anomaly_article_publisher as aap


def test_hr_pace_title_uses_period_suffix():
    """HR ペース title が期間末尾括弧 (case A 形) を使う."""
    article = aap.render_hr_pace_article(None, {
        "player_canonical": "巨人選手",
        "magnitude": 28.0,
        "current_value": "season換算HR=28.0本",
    })

    assert article["title"].startswith("【巨人データ】"), (
        f"prefix 【巨人データ】 欠落: title={article['title']!r}"
    )
    assert article["title"].endswith("（直近30日）"), (
        f"period suffix が末尾括弧で無い: title={article['title']!r}"
    )
    # title 中盤に「直近 30 日」が出ない (末尾の 1 回だけ)
    assert article["title"].count("直近") == 1, (
        f"期間表記が複数出ている: title={article['title']!r}"
    )
    # 数値は title に含まれる
    assert "28.0" in article["title"] or "28本" in article["title"], (
        f"projection 数値が無い: title={article['title']!r}"
    )
    # 「本塁打」(日本語) を使う、 raw "HR" は使わない (memory: OPS/UZR/WAR のみ英語 OK)
    assert "本塁打" in article["title"], (
        f"日本語表記 (本塁打) が無い: title={article['title']!r}"
    )
