"""437 Phase 2A: Pillow-based v2 image generator unit tests.

scope: CJK tofu ゼロ verify + 1080x1080 size + < 500KB + 巨人 row highlight。
Phase 1 cairosvg path (e90fcfa で廃止) は別 file (test_x_post_image_gen.py)。
"""
from __future__ import annotations

import io
import struct

import pytest

from src.x_post_image_gen_v2 import (
    PNG_MAX_BYTES,
    _find_font,
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
