"""Tests for src.analysis.insight_article_generator."""

from __future__ import annotations

import pytest

from src.analysis import insight_article_generator as gen


def _row(player, rank, total, value, team="g", sample=50):
    return gen.RankRow(
        player_canonical=player,
        team_code=team,
        metric_value=value,
        sample_size=sample,
        rank=rank,
        total=total,
    )


# ─── render returns required keys ─────────────────────────────────────────


def test_render_returns_keys():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[_row("吉川尚輝", 4, 12, 0.812)],
        focus_player="吉川尚輝",
    )
    out = gen.render_article(ctx)
    assert set(out.keys()) >= {"title", "body_md", "suggested_tags", "meta"}
    assert out["body_md"].startswith("# ")
    assert "## データで見ると" in out["body_md"]
    assert "## 解釈" in out["body_md"]


def test_focus_player_appears_in_title_and_lead():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[_row("吉川尚輝", 4, 12, 0.812)],
        focus_player="吉川尚輝",
        position_filter="二",
    )
    out = gen.render_article(ctx)
    assert "吉川尚輝" in out["title"]
    assert "二" in out["title"]
    assert "吉川尚輝" in out["body_md"]


def test_table_marks_focus_row():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[
            _row("A", 1, 3, 0.900),
            _row("吉川尚輝", 2, 3, 0.812),
            _row("B", 3, 3, 0.700),
        ],
        focus_player="吉川尚輝",
    )
    out = gen.render_article(ctx)
    # focus row carries the ★ marker in the markdown table
    assert "吉川尚輝 ★" in out["body_md"]


# ─── interpretation reflects rank position ─────────────────────────────────


def test_interpretation_top_is_positive():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[_row("X", 1, 12, 0.950)],
        focus_player="X",
    )
    out = gen.render_article(ctx)
    body = out["body_md"]
    assert "上位" in body or "平均より明確に上" in body


def test_interpretation_bottom_is_critical():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[
            _row("top", 1, 12, 0.999),
            _row("X", 11, 12, 0.4),
        ],
        focus_player="X",
    )
    out = gen.render_article(ctx)
    assert "下位" in out["body_md"] or "改善余地" in out["body_md"]


def test_pitching_metric_uses_lower_is_better_logic():
    """ERA は低い方が良い、rank 1 は positive verdict"""
    ctx = gen.ArticleContext(
        metric_name="ERA",
        rows=[_row("ace", 1, 20, 1.85)],
        focus_player="ace",
    )
    out = gen.render_article(ctx)
    # rank 1 should still be evaluated positively for ERA
    assert "上位" in out["body_md"] or "明確に上" in out["body_md"]


# ─── disclaimers ──────────────────────────────────────────────────────────


def test_defense_disclaimer_mentions_uzr_is_proxy():
    ctx = gen.ArticleContext(
        metric_name="RF_proxy",
        rows=[_row("吉川尚輝", 2, 8, 0.85)],
        focus_player="吉川尚輝",
        position_filter="二",
    )
    out = gen.render_article(ctx)
    body = out["body_md"]
    assert "UZR" in body
    assert "代理" in body or "近似" in body


def test_non_defense_uses_default_disclaimer():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[_row("X", 1, 12, 0.9)],
    )
    out = gen.render_article(ctx)
    assert "サンプル数" in out["body_md"]


# ─── suggested tags ───────────────────────────────────────────────────────


def test_tags_include_metric_label_and_player():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[_row("吉川尚輝", 1, 12, 0.9)],
        focus_player="吉川尚輝",
        position_filter="二",
    )
    out = gen.render_article(ctx)
    tags = out["suggested_tags"]
    assert "巨人" in tags
    assert "吉川尚輝" in tags
    assert "OPS" in tags
    assert "二手" in tags


def test_tags_include_defense_label_for_defense_metric():
    ctx = gen.ArticleContext(
        metric_name="RF_proxy",
        rows=[_row("X", 1, 8, 0.9)],
        focus_player="X",
        position_filter="遊",
    )
    tags = gen.render_article(ctx)["suggested_tags"]
    assert "守備" in tags


# ─── empty / edge cases ───────────────────────────────────────────────────


def test_no_focus_player_still_renders():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[_row("A", 1, 3, 0.9), _row("B", 2, 3, 0.7)],
    )
    out = gen.render_article(ctx)
    assert "OPS" in out["title"]
    assert "A" in out["body_md"]


def test_empty_rows_returns_no_data_marker():
    ctx = gen.ArticleContext(metric_name="OPS", rows=[])
    out = gen.render_article(ctx)
    assert "該当データなし" in out["body_md"]


def test_meta_footer_uses_japanese_metric_label():
    ctx = gen.ArticleContext(
        metric_name="FIP",
        rows=[_row("X", 1, 5, 2.5)],
    )
    body = gen.render_article(ctx)["body_md"]
    assert "指標: 守備非依存防御率" in body
    assert "metric: FIP" not in body
    assert "生成日時" in body


def test_top_n_caps_table_rows():
    ctx = gen.ArticleContext(
        metric_name="OPS",
        rows=[_row(f"P{i}", i + 1, 30, 0.9 - 0.01 * i) for i in range(30)],
    )
    out = gen.render_article(ctx, top_n=5)
    # Data rows in the markdown table start with "| <rank>/<total>"
    data_rows = [l for l in out["body_md"].splitlines() if l.startswith("| ") and "/30 " in l]
    assert len(data_rows) == 5
