"""465 contrast-title builder unit tests (no-AI, literal, capped)."""

from src.analysis.insight_contrast_title import (
    MAX_TITLE_LEN,
    build_contrast_title,
)


def test_higher_better_strong_ratio_emits_top_label():
    t = build_contrast_title(
        player="坂本勇人", metric_label="OPS", player_value=0.912,
        league_mean=0.701, scope_label="直近30日",
    )
    assert t is not None
    assert "OPS0.912" in t
    assert "リーグ平均0.701" in t
    assert "1.3倍" in t
    assert "リーグ屈指" in t
    assert t.startswith("【巨人データ】坂本勇人、")
    assert t.endswith("（直近30日）")


def test_higher_better_mid_ratio_emits_mid_label():
    t = build_contrast_title(
        player="吉川尚輝", metric_label="打率", player_value=0.300,
        league_mean=0.260, scope_label="直近30日",
    )
    assert t is not None
    assert "好調" in t
    assert "リーグ屈指" not in t


def test_below_surface_ratio_falls_back_to_none():
    # 0.270 / 0.260 = 1.038 < MIN_SURFACE_RATIO
    assert build_contrast_title(
        player="増田大輝", metric_label="OPS", player_value=0.270,
        league_mean=0.260, scope_label="直近30日",
    ) is None


def test_lower_better_uses_direct_comparison_no_baix():
    t = build_contrast_title(
        player="山崎伊織", metric_label="防御率", player_value=1.80,
        league_mean=3.50, scope_label="今シーズン", lower_is_better=True,
    )
    assert t is not None
    assert "防御率1.800" in t
    assert "リーグ平均3.500" in t
    assert "倍" not in t  # lower-is-better never uses the 倍 framing
    assert "リーグ屈指の安定感" in t


def test_lower_better_below_surface_is_none():
    # mean/value = 3.50/3.30 = 1.06 < surface
    assert build_contrast_title(
        player="某投手", metric_label="防御率", player_value=3.30,
        league_mean=3.50, scope_label="今シーズン", lower_is_better=True,
    ) is None


def test_missing_or_nonpositive_inputs_return_none():
    assert build_contrast_title(
        player="x", metric_label="OPS", player_value=None,
        league_mean=0.7, scope_label="直近30日",
    ) is None
    assert build_contrast_title(
        player="x", metric_label="OPS", player_value=0.9,
        league_mean=None, scope_label="直近30日",
    ) is None
    assert build_contrast_title(
        player="x", metric_label="OPS", player_value=0.0,
        league_mean=0.7, scope_label="直近30日",
    ) is None


def test_title_never_exceeds_cap():
    # long player name + long label must still respect the 60-char cap.
    t = build_contrast_title(
        player="ロングネームテスト選手", metric_label="OPS",
        player_value=0.999, league_mean=0.700, scope_label="直近30日",
    )
    if t is not None:
        assert len(t) <= MAX_TITLE_LEN
        # when over cap the label is dropped but the literal numbers remain
        assert "リーグ平均0.700" in t


def test_no_ellipsis_truncation():
    t = build_contrast_title(
        player="坂本勇人", metric_label="OPS", player_value=0.912,
        league_mean=0.701, scope_label="直近30日",
    )
    assert t is not None
    assert "…" not in t and "..." not in t
