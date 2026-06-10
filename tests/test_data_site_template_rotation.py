"""Tests for the /data/rotation page template (先発ローテ一覧 2007-2026)."""

from __future__ import annotations

from src.data_site_template_rotation import (
    load_rotation_data,
    render_rotation_excerpt,
    render_rotation_html,
    render_rotation_title,
)

SAMPLE = {
    "years": [
        {
            "year": 2026,
            "games": [
                {
                    "game_no": "1", "date": "03月27日", "opp": "阪神",
                    "stadium": "東京ドーム", "pitcher": "竹丸", "decision": "○",
                    "ip": "6", "pitches": "79", "hits": "3", "so": "5",
                    "runs": "1", "qs": "QS",
                }
            ],
            "pitchers": [{"name": "竹丸", "starts": 9}, {"name": "戸郷", "starts": 5}],
        },
        {
            "year": 2025,
            "games": [
                {
                    "game_no": "1", "date": "03月28日", "opp": "DeNA",
                    "stadium": "横浜", "pitcher": "戸郷", "decision": "●",
                    "ip": "5", "pitches": "88", "hits": "6", "so": "4",
                    "runs": "3", "qs": "",
                }
            ],
            "pitchers": [{"name": "戸郷", "starts": 26}],
        },
    ]
}


def test_data_file_loads_with_all_years() -> None:
    data = load_rotation_data()
    years = [int(y["year"]) for y in data.get("years") or []]
    assert years, "rotation data file should load"
    assert 2026 in years and 2007 in years
    assert len(years) == 20


def test_render_has_year_anchors_and_jump_nav() -> None:
    html = render_rotation_html(SAMPLE)
    assert 'id="year-2026"' in html
    assert 'id="year-2025"' in html
    assert 'href="#year-2026"' in html
    assert "竹丸" in html and "戸郷" in html
    assert "全1試合" in html


def test_render_has_no_source_or_external_links() -> None:
    # user 方針: 出典 (取得元) を載せない / 外部リンクを張らない
    html = render_rotation_html(SAMPLE)
    assert "出典" not in html
    assert "my-favorite-giants" not in html
    assert "my favorite giants" not in html
    assert 'target="_blank"' not in html
    assert "http://" not in html.replace("http://www.w3.org", "")  # jsonld schema URL のみ許容


def test_pitcher_names_not_linked_to_player_pages() -> None:
    # 姓のみデータの誤リンク (事実誤認) を避けるためプレーン表記
    html = render_rotation_html(SAMPLE)
    assert 'href="/data/take' not in html  # 投手 slug への誤リンクなし
    # footer の正規リンクは存在
    assert 'href="https://yoshilover.com/data"' in html


def test_recent_two_years_open_by_default() -> None:
    html = render_rotation_html(SAMPLE)
    assert '<details id="year-2026" open' in html
    assert '<details id="year-2025" open' in html


def test_title_and_excerpt() -> None:
    assert "先発ローテ" in render_rotation_title()
    exc = render_rotation_excerpt(SAMPLE)
    assert "2025〜2026年" in exc
