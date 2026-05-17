"""Tests for issue #44 B-4: render_hidden_below_qualifier_article の title を
case A 寄りに refit.

Bug: ``render_hidden_below_qualifier_article`` の title は
``【巨人データ】今シーズン {player}、規定打席未満ながら OPS .850 の好調``
で「今シーズン」が title 冒頭に prefix されており case A spec
(2026-05-15 user lock) の「期間は末尾括弧、 冒頭 prefix 禁止」rule に反する。

Fix: title を ``【巨人データ】{player}、OPS .850 の好調（規定打席未満・今シーズン）``
へ refit。 期間は末尾括弧、 「規定打席未満」は context として括弧内へ移動。

Note: 規定未到達者は (2f0a06f 後) 公式 ranking 外、 ranking 表 wire は
そもそも対象外。 title refit のみ。
"""

from __future__ import annotations

from src.analysis import anomaly_article_publisher as aap


def test_hidden_below_qualifier_title_uses_period_suffix():
    """「今シーズン」 prefix を廃止し、 末尾括弧へ移動."""
    article = aap.render_hidden_below_qualifier_article(None, {
        "player_canonical": "巨人選手",
        "magnitude": 0.850,
        "current_value": "OPS=0.850 PA=80",
    })

    title = article["title"]
    assert title.startswith("【巨人データ】"), (
        f"prefix 【巨人データ】 欠落: title={title!r}"
    )
    # 旧 prefix 「今シーズン {player}」を使わない
    assert not title.startswith("【巨人データ】今シーズン"), (
        f"「今シーズン」prefix 違反: title={title!r}"
    )
    # 主語 (player) が prefix 直後に来る
    assert title.startswith("【巨人データ】巨人選手"), (
        f"主語 prefix 直後でない: title={title!r}"
    )
    # 期間は末尾括弧で出る
    assert "今シーズン" in title, f"期間表記が無い: title={title!r}"
    assert title.endswith("）"), f"末尾括弧で閉じていない: title={title!r}"
    # 「規定打席未満」context は維持
    assert "規定打席未満" in title, f"context 「規定打席未満」が無い: title={title!r}"
    # 数値は title に含まれる
    assert "0.850" in title or ".850" in title, (
        f"OPS 数値が無い: title={title!r}"
    )
