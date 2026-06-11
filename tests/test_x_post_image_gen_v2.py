"""437 Phase 2A: Pillow-based v2 image generator unit tests.

scope: CJK tofu ゼロ verify + 1080x1080 size + < 500KB + 巨人 row highlight。
Phase 1 cairosvg path (e90fcfa で廃止) は別 file (test_x_post_image_gen.py)。
"""
from __future__ import annotations

import io
import struct

import pytest

from src.x_post_image_gen_v2 import (
    EMOJI_CODEPOINT_THRESHOLD,
    FONT_CANDIDATES_BOLD,
    PNG_MAX_BYTES,
    _find_emoji_font,
    _find_font,
    _is_bold_font_path,
    _split_text_by_emoji,
    build_ranking_data,
    generate_png,
)


def _sample_rows():
    return [
        {"rank": 1, "name": "佐藤輝明", "team": "阪神", "value": ".961", "is_giants": False},
        {"rank": 2, "name": "坂倉将吾", "team": "広島", "value": ".882", "is_giants": False},
        {"rank": 3, "name": "坂本勇人", "team": "巨人", "value": ".867", "is_giants": True},
        {"rank": 4, "name": "村松開人", "team": "中日", "value": ".831", "is_giants": False},
        {"rank": 5, "name": "武岡龍世", "team": "ヤクルト", "value": ".812", "is_giants": False},
        {"rank": 6, "name": "大山悠輔", "team": "阪神", "value": ".798", "is_giants": False},
        {"rank": 7, "name": "森下翔太", "team": "阪神", "value": ".785", "is_giants": False},
        {"rank": 8, "name": "岡本和真", "team": "巨人", "value": ".772", "is_giants": True},
    ]


def _sample_data():
    return build_ranking_data(
        title="セ・リーグ OPS ランキング",
        subtitle="直近 10 試合 / 規定打席 20 以上",
        hook_line="★ 巨人 2 名 トップ 10 入り ★",
        rows=_sample_rows(),
    )


def _png_size_from_bytes(png_bytes: bytes) -> tuple[int, int]:
    """PNG header から width/height を抜く (IHDR chunk = bytes 16-24)。"""
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    w, h = struct.unpack(">II", png_bytes[16:24])
    return w, h


# ---------- font resolution ----------


def test_find_font_returns_cjk_capable():
    """system に CJK font が install されていれば _find_font は raise しない。

    Cloud Run image (Phase 2D) で fonts-ipafont-gothic install を保証する gate も
    兼ねる: image build が font 抜けで上がっても、 deploy 後の起動 smoke でここが
    raise すれば即検知できる。
    """
    font, path = _find_font(size=42)
    assert font is not None
    assert path.endswith((".ttf", ".ttc", ".otf"))


def test_find_font_cjk_glyph_non_zero_bbox():
    """選手名 / 漢字 / 数値 / ★ が tofu (zero-width) しないことを bbox で検証。

    Phase 1 cairosvg tofu 事故 (post 72079 / 72076) の再発防止 gate。
    """
    from PIL import Image, ImageDraw

    font, _ = _find_font(size=48)
    img = Image.new("RGB", (1080, 200), "white")
    draw = ImageDraw.Draw(img)
    test_strings = [
        "坂本勇人",
        "岡本和真",
        "戸郷翔征",
        "巨人",
        "セ・リーグ",
        "順位",
        "本塁打",
        "★",
        "あいうえお",
        "漢字日本語表示",
        "0123456789",
        ".320",
    ]
    failures = []
    for s in test_strings:
        bbox = draw.textbbox((0, 0), s, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= 0 or h <= 0:
            failures.append((s, w, h))
    assert not failures, f"CJK tofu detected (zero-width bbox): {failures}"


# ---------- generate_png ----------


def test_generate_png_returns_bytes():
    png = generate_png("ranking_table", _sample_data())
    assert png is not None
    assert isinstance(png, bytes)
    assert len(png) > 0


def test_generate_png_size_is_1080x1080():
    png = generate_png("ranking_table", _sample_data())
    assert png is not None
    w, h = _png_size_from_bytes(png)
    assert (w, h) == (1080, 1080)


def test_generate_png_under_500kb():
    png = generate_png("ranking_table", _sample_data())
    assert png is not None
    assert len(png) <= PNG_MAX_BYTES, f"PNG size {len(png)} > {PNG_MAX_BYTES}"


def test_generate_png_unknown_template_returns_none(caplog):
    """Phase 2A scope 外の template_key は None + WARN log を返す。"""
    import logging

    caplog.set_level(logging.WARNING)
    png = generate_png("unknown_template_key_xxx", _sample_data())
    assert png is None
    assert any("unknown template_key" in m for m in caplog.messages)


def test_generate_png_handles_empty_rows():
    """rows=[] でも fallback で None ではなく header 含む PNG を返す
    (publish 自体を止めない設計)。"""
    data = build_ranking_data(
        title="dummy",
        subtitle="dummy",
        hook_line="dummy",
        rows=[],
    )
    png = generate_png("ranking_table", data)
    assert png is not None
    w, h = _png_size_from_bytes(png)
    assert (w, h) == (1080, 1080)


def test_generate_png_renders_when_all_rows_giants():
    """全 row が is_giants=True でも layout が崩れず PNG が生成される。"""
    rows = [
        {"rank": i + 1, "name": f"巨人選手{i+1}", "team": "巨人", "value": f".{900 - i*10}", "is_giants": True}
        for i in range(8)
    ]
    data = build_ranking_data(
        title="巨人内 OPS ランキング",
        subtitle="全員 巨人",
        hook_line="★ 巨人 8 名 ★",
        rows=rows,
    )
    png = generate_png("ranking_table", data)
    assert png is not None
    w, h = _png_size_from_bytes(png)
    assert (w, h) == (1080, 1080)


# ---------- build_ranking_data ----------


def test_build_ranking_data_passes_through_fields():
    data = build_ranking_data(
        title="t",
        subtitle="s",
        hook_line="h",
        rows=[{"rank": 1}],
        footer_handle="@foo",
        footer_meta="bar",
    )
    assert data["title"] == "t"
    assert data["subtitle"] == "s"
    assert data["hook_line"] == "h"
    assert data["rows"] == [{"rank": 1}]
    assert data["footer_handle"] == "@foo"
    assert data["footer_meta"] == "bar"


def test_build_ranking_data_defaults_footer():
    data = build_ranking_data(title="t", subtitle="s", hook_line="h", rows=[])
    assert data["footer_handle"].startswith("@")
    assert data["footer_meta"]


# ---------- emoji fallback ----------


def test_split_text_by_emoji_separates_runs():
    """🔥 / 🏆 等は emoji run、 ★ / 巨人 / 数値 は main font run に分かれる。"""
    runs = _split_text_by_emoji("🔥 巨人 2 名 🏆")
    assert runs == [
        ("🔥", True),
        (" 巨人 2 名 ", False),
        ("🏆", True),
    ]


def test_split_text_by_emoji_keeps_star_in_main_font():
    """★ (U+2605) は EMOJI_CODEPOINT_THRESHOLD 未満なので main font run のまま。"""
    runs = _split_text_by_emoji("★ 巨人 2 名 ★")
    assert all(not is_e for _, is_e in runs)
    assert ord("★") < EMOJI_CODEPOINT_THRESHOLD


def test_split_text_by_emoji_no_emoji_single_run():
    runs = _split_text_by_emoji("セ・リーグ OPS ランキング")
    assert len(runs) == 1
    assert runs[0] == ("セ・リーグ OPS ランキング", False)


def test_split_text_by_emoji_empty_input():
    assert _split_text_by_emoji("") == []


def test_is_bold_font_path_recognizes_noto_bold():
    """Noto Sans CJK Bold path は bold 認定、 IPAGothic は false。"""
    assert _is_bold_font_path(FONT_CANDIDATES_BOLD[0]) is True
    assert _is_bold_font_path("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf") is False


def test_generate_png_handles_emoji_in_hook_line():
    """hook_line に 🔥 / 🏆 等が混ざっても tofu せず PNG が生成される。

    Noto Color Emoji が install 済の環境では emoji が color 描画され、
    install されていない環境では fallback して main font で描く (tofu の可能性
    はあるが PNG 自体は生成される)。 どちらでも generate_png は None を返さない。
    """
    data = build_ranking_data(
        title="セ・リーグ OPS ランキング",
        subtitle="直近 10 試合",
        hook_line="🔥 巨人 2 名 トップ 10 入り 🏆",
        rows=_sample_rows(),
    )
    png = generate_png("ranking_table", data)
    assert png is not None
    w, h = _png_size_from_bytes(png)
    assert (w, h) == (1080, 1080)


def test_emoji_font_lookup_finds_if_installed():
    """Noto Color Emoji が system に install 済なら _find_emoji_font は font を返す。

    Cloud Run image (Phase 2D) で fonts-noto-color-emoji が抜けたケースを
    検知する gate。 install されていない CI 環境では None が返るが、 generate_png
    自体は通る (上の test と同じ理由)。
    """
    font, path = _find_emoji_font(0)
    # 環境依存: install 済なら font / path 共に non-None、 未 install なら None
    if font is not None:
        assert path.endswith(".ttf") or path.endswith(".ttc")


# ---------- 2026-06-11 variation templates ----------


@pytest.mark.parametrize("template_key", ["podium_top3", "focus_duel", "dark_hero"])
def test_variation_templates_render_valid_png(template_key):
    """新 variation 3 種が ranking rows 共通 schema で 1080x1080 PNG を返す。"""
    png = generate_png(template_key, _sample_data())
    assert png is not None
    w, h = _png_size_from_bytes(png)
    assert (w, h) == (1080, 1080)
    assert len(png) <= PNG_MAX_BYTES


@pytest.mark.parametrize("template_key", ["podium_top3", "focus_duel", "dark_hero"])
def test_variation_templates_render_without_giants_rows(template_key):
    """巨人 row ゼロでも fallback (1位 hero / leader duel) で描画が通る。"""
    rows = [dict(r, is_giants=False) for r in _sample_rows()]
    data = build_ranking_data(
        title="セ・リーグ OPS ランキング", subtitle="直近 10 試合",
        hook_line="★ セ・リーグ OPS ★", rows=rows,
    )
    png = generate_png(template_key, data)
    assert png is not None


def test_podium_top3_renders_with_two_rows():
    """rows が 2 件 (3位なし) でも表彰台が描ける。"""
    data = build_ranking_data(
        title="t", subtitle="s", hook_line="h", rows=_sample_rows()[:2],
    )
    png = generate_png("podium_top3", data)
    assert png is not None


def test_focus_duel_single_row_renders_header_only():
    """rows 1 件では対決が組めないが、 PNG 自体は生成される (None にしない)。"""
    data = build_ranking_data(
        title="t", subtitle="s", hook_line="h", rows=_sample_rows()[:1],
    )
    png = generate_png("focus_duel", data)
    assert png is not None


def test_focus_duel_picks_giants_vs_better_neighbor():
    """巨人 focus (3位) の rival は 1 つ上の 2位 — 描画が通り giants 色が乗る。"""
    png = generate_png("focus_duel", _sample_data())
    assert png is not None
    # 巨人 gradient (orange) が左 card に乗っている = orange 系 pixel が存在
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = img.size
    sample = img.getpixel((w // 4, h // 2))
    assert sample[0] > 150 and sample[0] > sample[2], f"left card not orange: {sample}"


def test_dark_hero_canvas_is_dark():
    """dark_hero は下地が dark (中央下部寄り pixel の輝度が低い)。"""
    png = generate_png("dark_hero", _sample_data())
    assert png is not None
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    # 左端 (card / glow が無い領域) の pixel
    sample = img.getpixel((30, 600))
    assert sum(sample) < 240, f"canvas not dark: {sample}"


def test_win_split_template_renders_valid_png():
    """勝利相関 (win_split) template が 1080x1080 PNG を返す。"""
    from src.x_post_image_gen_v2 import build_win_split_data
    data = build_win_split_data(
        title="キャベッジ 勝利相関", subtitle="今季42試合", hook_line="★ 打点を挙げた試合、巨人は強い ★",
        player_name="キャベッジ", cond_label="打点を挙げた試合",
        a_record="9勝2敗", a_rate=".818", b_record="14勝17敗", b_rate=".452",
        diff_label="勝率差 +.367",
    )
    png = generate_png("win_split", data)
    assert png is not None
    w, h = _png_size_from_bytes(png)
    assert (w, h) == (1080, 1080)
    assert len(png) <= PNG_MAX_BYTES


def test_build_win_split_data_passthrough():
    from src.x_post_image_gen_v2 import build_win_split_data
    d = build_win_split_data(
        title="t", subtitle="s", hook_line="h", player_name="p",
        cond_label="c", a_record="1勝0敗", a_rate="1.000",
        b_record="0勝1敗", b_rate=".000", diff_label="差 1.000",
    )
    assert d["player_name"] == "p" and d["a_rate"] == "1.000"
    assert d["footer_handle"]  # default 充填
