"""Tests for issue #44 B-5: render_hit_streak_run_article の title を case C 寄りに refit.

Bug: ``render_hit_streak_run_article`` の title は
``【巨人データ】{player}、{N}試合連続で複数安打`` で「、」「で」が入り、
milestone の consecutive_* record path (``{player} {record_label} {streak}
{unit} 継続中``) と spacing / 接続詞 が不揃い。

Fix: title を milestone consecutive と統一して
``【巨人データ】{player} {N} 試合連続 複数安打 継続中`` 形へ refit。

Note: streak は player 単独指標で Central League ranking infra 無し、
ranking 表 wire は対象外、 title refit のみ。
"""

from __future__ import annotations

from src.analysis import anomaly_article_publisher as aap


def test_hit_streak_run_title_matches_consecutive_record_style():
    """streak title が milestone consecutive_* と統一形になる."""
    article = aap.render_hit_streak_run_article(None, {
        "player_canonical": "巨人選手",
        "magnitude": 5,
    })

    title = article["title"]
    assert title.startswith("【巨人データ】"), (
        f"prefix 欠落: title={title!r}"
    )
    assert "巨人選手" in title, f"主語が無い: title={title!r}"
    # case C 形: 連続 N 試合 継続中
    assert "5 試合連続" in title or "5試合連続" in title, (
        f"連続試合数表記が無い: title={title!r}"
    )
    assert "複数安打" in title, f"event token (複数安打) が無い: title={title!r}"
    assert "継続中" in title, (
        f"milestone consecutive と統一する「継続中」が無い: title={title!r}"
    )
    # 旧 title の冗長な「、 ... で」を使わない
    assert "、" not in title or "、複数" not in title, (
        f"旧 title の句読点 pattern が残っている: title={title!r}"
    )
