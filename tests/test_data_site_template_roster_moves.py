"""Tests for the /data/roster-moves page template (出場選手登録・抹消)."""

from __future__ import annotations

from src.data_site_template_roster_moves import (
    load_roster_moves_data,
    render_roster_moves_excerpt,
    render_roster_moves_html,
    render_roster_moves_title,
)

SAMPLE = {
    "years": [
        {
            "year": 2026,
            "roster": [
                {"pos": "投手", "no": "20", "name": "戸郷　翔征"},
                {"pos": "捕手", "no": "27", "name": "岸田　行倫"},
                {"pos": "内野手", "no": "6", "name": "坂本　勇人"},
                {"pos": "外野手", "no": "8", "name": "丸　佳浩"},
            ],
            "moves": [
                {"date": "5/28", "reg": ["増田 大輝", "中山 礼都"],
                 "out": ["増田 陸", "浅野 翔吾"]},
                {"date": "5/26", "reg": ["則本 昂大"], "out": []},
            ],
        },
        {"year": 2025, "roster": [], "moves": [
            {"date": "9/1", "reg": ["山崎 伊織"], "out": []},
        ]},
    ]
}


def test_data_file_loads() -> None:
    data = load_roster_moves_data()
    years = [int(y["year"]) for y in data.get("years") or []]
    assert years, "roster moves data file should load"
    assert 2026 in years


def test_current_roster_section_grouped_by_position() -> None:
    h = render_roster_moves_html(SAMPLE)
    assert "現在の1軍登録メンバー" in h
    for pos in ("投手", "捕手", "内野手", "外野手"):
        assert pos in h
    # full-width space normalized for display
    assert "戸郷 翔征" in h


def test_moves_color_chips_and_year_sections() -> None:
    h = render_roster_moves_html(SAMPLE)
    assert "ys-rm__in" in h and "ys-rm__out" in h  # 登録=緑 / 抹消=赤
    assert 'id="rm-year-2026"' in h and 'id="rm-year-2025"' in h
    assert "増田 大輝" in h and "中山 礼都" in h
    assert 'href="#rm-year-2026"' in h


def test_no_source_or_external_links() -> None:
    h = render_roster_moves_html(SAMPLE)
    assert "出典" not in h
    assert "my-favorite" not in h
    assert 'target="_blank"' not in h


def test_recent_year_open_by_default() -> None:
    h = render_roster_moves_html(SAMPLE)
    assert '<details id="rm-year-2026" open' in h


def test_title_and_excerpt() -> None:
    assert "出場選手登録・抹消" in render_roster_moves_title()
    assert "2025〜2026年" in render_roster_moves_excerpt(SAMPLE)


def test_popular_player_links_block() -> None:
    # GSC で伸びている選手ページへの内部リンク (2026-07-24 SEO 施策)
    h = render_roster_moves_html(SAMPLE)
    assert "検索で人気の巨人選手データ" in h
    assert "/data/matsumoto-tsuyoshi" in h
    assert "松本剛 成績" in h
