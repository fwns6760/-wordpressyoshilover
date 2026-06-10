"""Tests for /data/farm topic cluster."""

from __future__ import annotations

from src.data_site_farm_source import (
    FarmGenericRow,
    FarmPlayerStat,
    parse_farm_game_rows,
)
from src.data_site_template_farm import (
    render_farm_championship_html,
    render_farm_education_html,
    render_farm_hub_html,
    render_farm_players_html,
    render_farm_schedule_html,
    render_farm_team_html,
    render_farm_titles_html,
)


def _sample_rows():
    table = [
        [["春季教育リーグ"]],
        [["3月7日", "土", "オイシックス新潟", "H", "ジャイアンツタウン", "●6-9", "", "泉－●田村－富田－平内", "15", "平山①、②"]],
        [["ファーム公式戦"]],
        [["4月14日", "火", "ハヤテ静岡", "", "静岡草薙", "○4-0", "10-9", "○園田（1勝1敗）－石川－宮原", "7", "ティマ2号①"]],
        [["4月15日", "水", "ハヤテ静岡", "", "静岡草薙", "○3-1", "11-9", "山城－○堀田（1勝）－S泉（1S）", "6", "三塚1号②"]],
        [["秋季教育リーグ"]],
        [["10月6日", "火", "オリックス", "", "宮崎SOKKEN", "○9-5", "", "○戸郷－横川－S富田", "13", "ヘルナンデス②"]],
    ]
    return parse_farm_game_rows(table)


def _batting():
    return [
        FarmPlayerStat(name="浅野翔吾", role="batting", games="38", hits="39", hr="3", rbi="20", sb="3", avg=".336"),
        FarmPlayerStat(name="小濱佑斗", role="batting", games="44", hits="35", hr="2", rbi="20", sb="15", avg=".233"),
    ]


def _pitching():
    return [
        FarmPlayerStat(name="森田駿哉", role="pitching", games="8", wins="5", losses="1", saves="0", innings="43.2", strikeouts="23", era="1.65"),
        FarmPlayerStat(name="山田龍聖", role="pitching", games="16", wins="2", losses="3", saves="2", innings="46", strikeouts="29", era="3.52"),
    ]


def test_parse_farm_game_rows_tracks_competition() -> None:
    rows = _sample_rows()
    assert len(rows) == 4
    assert rows[0].competition == "春季教育リーグ"
    assert rows[1].competition == "ファーム公式戦"
    assert rows[-1].competition == "秋季教育リーグ"
    assert rows[1].opponent == "ハヤテ静岡"
    assert rows[1].score == "○4-0"


def test_farm_hub_links_all_child_pages() -> None:
    html = render_farm_hub_html(_sample_rows(), _batting(), _pitching())
    assert "巨人 2軍ファームデータ" in html
    for path in [
        "/data/farm/schedule",
        "/data/farm/spring-education",
        "/data/farm/autumn-education",
        "/data/farm/team",
        "/data/farm/players",
        "/data/farm/titles",
        "/data/farm/championship",
    ]:
        assert path in html
    assert "giants-sns-realtime-farm" in html


def test_schedule_and_education_pages_are_split() -> None:
    rows = _sample_rows()
    schedule = render_farm_schedule_html(rows)
    spring = render_farm_education_html(rows, kind="spring")
    autumn = render_farm_education_html(rows, kind="autumn")
    assert "巨人 2軍試合日程・結果 2026" in schedule
    assert "ファーム公式戦" in schedule
    assert "春季教育リーグ" in spring
    assert "秋季教育リーグ" in autumn


def test_players_page_has_search_and_links() -> None:
    html = render_farm_players_html(_batting(), _pitching())
    assert 'id="ys-farm-player-search"' in html
    assert "浅野翔吾" in html
    assert "/data/asano-shogo" in html
    assert "森田駿哉" in html


def test_team_titles_championship_pages_render_generic_rows() -> None:
    rows = _sample_rows()
    generic = [FarmGenericRow(("2025", "①", "126", "80-44-2", ".645", ".271 / 2.88"))]
    assert "2軍年度別チーム成績" in render_farm_team_html(rows, generic)
    assert "2軍タイトルホルダー" in render_farm_titles_html(_batting(), _pitching(), generic)
    assert "ファーム日本選手権" in render_farm_championship_html(generic)
