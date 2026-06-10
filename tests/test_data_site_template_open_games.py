"""Tests for the /data/open-games page template (オープン戦結果)."""

from __future__ import annotations

from src.data_site_template_open_games import (
    load_open_games_data,
    render_open_games_excerpt,
    render_open_games_html,
    render_open_games_title,
)

SAMPLE = {
    "years": [
        {"year": 2026, "games": [
            {"no": "1", "date": "2月21日", "opp": "東京ヤクルト", "home": "H",
             "stadium": "沖縄", "result": "●", "score": "1-3",
             "pitchers": "山﨑－西舘", "hits": "3", "hr": ""},
            {"no": "2", "date": "2月22日", "opp": "中日", "home": "",
             "stadium": "北谷", "result": "○", "score": "3-0",
             "pitchers": "○則本", "hits": "10", "hr": ""},
            {"no": "3", "date": "2月23日", "opp": "楽天", "home": "H",
             "stadium": "那覇", "result": "△", "score": "2-2",
             "pitchers": "竹丸", "hits": "7", "hr": ""},
        ]},
        {"year": 2025, "games": [
            {"no": "1", "date": "2月20日", "opp": "広島", "home": "", "stadium": "由宇",
             "result": "○", "score": "5-2", "pitchers": "○戸郷", "hits": "9", "hr": "岡本1号"},
        ]},
    ]
}


def test_data_file_loads_all_years() -> None:
    data = load_open_games_data()
    years = [int(y["year"]) for y in data.get("years") or []]
    assert years and 2026 in years and 2001 in years


def test_render_year_sections_and_summary() -> None:
    h = render_open_games_html(SAMPLE)
    assert 'id="og-year-2026"' in h and 'id="og-year-2025"' in h
    assert "1勝1敗1分" in h  # 2026 サマリー (○1 ●1 △1)
    assert "勝率" in h
    assert "東京ヤクルト" in h and "山﨑" in h


def test_result_color_coding_and_jump_nav() -> None:
    h = render_open_games_html(SAMPLE)
    assert "background:#e6f4ea" in h  # 勝=緑
    assert "background:#fce8e6" in h  # 負=赤
    assert 'href="#og-year-2026"' in h


def test_no_source_or_external_links() -> None:
    h = render_open_games_html(SAMPLE)
    assert "出典" not in h
    assert "my-favorite" not in h
    assert 'target="_blank"' not in h


def test_recent_year_open_by_default() -> None:
    h = render_open_games_html(SAMPLE)
    assert '<details id="og-year-2026" open' in h


def test_title_and_excerpt() -> None:
    assert "オープン戦" in render_open_games_title(SAMPLE)
    assert "2025〜2026年" in render_open_games_excerpt(SAMPLE)
