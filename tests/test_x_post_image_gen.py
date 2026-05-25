"""437 SVG → PNG image generator unit tests.

Phase 1A scope: ranking_table template の render + cairosvg PNG 化 + fallback。
1080x1080 / < 500KB / 巨人 row highlight / Jinja2 escape / 失敗 fallback を確認。
"""
from __future__ import annotations

import io
import struct
from pathlib import Path

import pytest

from src.x_post_image_gen import (
    PNG_MAX_BYTES,
    build_ranking_data,
    generate_png,
    render_svg,
    svg_to_png,
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
        hook_line="🔥 巨人 2 名 トップ 10 入り",
        rows=_sample_rows(),
    )


# ----- render_svg -----


def test_render_svg_contains_title_and_hook():
    svg = render_svg("ranking_table", _sample_data())
    assert "セ・リーグ OPS ランキング" in svg
    assert "🔥 巨人 2 名 トップ 10 入り" in svg
    assert "直近 10 試合 / 規定打席 20 以上" in svg


def test_render_svg_contains_all_player_names_and_values():
    svg = render_svg("ranking_table", _sample_data())
    for row in _sample_rows():
        assert row["name"] in svg
        assert row["value"] in svg


def test_render_svg_giants_rows_get_orange_gradient():
    svg = render_svg("ranking_table", _sample_data())
    # 2 巨人 row (坂本 / 岡本) → orange highlight 2 つ
    assert svg.count('fill="url(#giantsRow)"') == 2
    # 巨人 row には 金 ★ marker
    assert svg.count('fill="#FFD700">★</tspan>') == 2


def test_render_svg_non_giants_rows_get_thin_dividers():
    svg = render_svg("ranking_table", _sample_data())
    # 非巨人 row 6 件 → 罫線 6 本
    assert svg.count('stroke="#e0e0e0"') == 6


def test_render_svg_escapes_xml_special_chars():
    rows = _sample_rows()
    rows[0]["name"] = "Bad & <test>"
    data = build_ranking_data(
        title="t",
        subtitle="s",
        hook_line="h",
        rows=rows,
    )
    svg = render_svg("ranking_table", data)
    # Jinja2 autoescape → &amp; / &lt; / &gt;
    assert "&amp;" in svg
    assert "&lt;test&gt;" in svg
    # raw < script > 等で SVG 構造を壊さないこと
    assert "<test>" not in svg


# ----- svg_to_png -----


def test_svg_to_png_returns_png_signature():
    svg = render_svg("ranking_table", _sample_data())
    png = svg_to_png(svg)
    # PNG magic number: 89 50 4E 47 0D 0A 1A 0A
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_svg_to_png_dimensions_1080x1080():
    svg = render_svg("ranking_table", _sample_data())
    png = svg_to_png(svg)
    # PNG IHDR chunk at byte 16-23 holds width / height (big-endian uint32)
    width = struct.unpack(">I", png[16:20])[0]
    height = struct.unpack(">I", png[20:24])[0]
    assert width == 1080
    assert height == 1080


# ----- generate_png (entry point + fallback) -----


def test_generate_png_happy_path():
    png = generate_png("ranking_table", _sample_data())
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) <= PNG_MAX_BYTES, f"PNG too large: {len(png)} > {PNG_MAX_BYTES}"


def test_generate_png_returns_none_on_missing_template():
    png = generate_png("does_not_exist_xyz", _sample_data())
    # caller fallback path: None で publish 続行可
    assert png is None


def test_generate_png_returns_none_on_invalid_data():
    # Jinja2 が render 中に attribute error を出すケース (rows が None)
    bad_data = {"title": "t", "subtitle": "s", "hook_line": "h",
                "rows": None, "footer_handle": "@x", "footer_meta": "x"}
    png = generate_png("ranking_table", bad_data)
    assert png is None
