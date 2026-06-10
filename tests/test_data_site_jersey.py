"""Tests for /data/jersey-numbers topic cluster."""

from __future__ import annotations

from src.data_site_jersey_source import JerseyNumberRow, parse_jersey_rows
from src.data_site_template_jersey import (
    render_jersey_numbers_excerpt,
    render_jersey_numbers_html,
    render_jersey_numbers_title,
)


def _rows() -> list[JerseyNumberRow]:
    return [
        JerseyNumberRow("0", "増田大輝（－2020）", "←吉川尚輝（－2017）←木村拓也（－2007）"),
        JerseyNumberRow("1", "永久欠番・王貞治", "王貞治（1980－1959）←南村不可止", True),
        JerseyNumberRow("3", "永久欠番・長嶋茂雄", "長嶋茂雄（1974－1958）", True),
        JerseyNumberRow("6", "坂本勇人（－2007）", "←小久保裕紀←落合博満←川相昌弘"),
        JerseyNumberRow("55", "秋広優人（－2022）", "←松井秀喜←大田泰示"),
        JerseyNumberRow("101", "育成選手A", "←育成選手B"),
    ]


def test_parse_jersey_rows_extracts_number_current_and_history() -> None:
    tables = [[
        ["背番号", "現在", "過去の推移"],
        ["g1g", "Image", "永久欠番・王 貞治", "[1989.3.16 制定]王 貞治（1988－1981）←王 貞治（1980－1959）"],
        ["g6g", "坂本 勇人（－2007）←小久保 裕紀←落合 博満"],
        ["g55g", "秋広 優人（－2022）←松井 秀喜←大田 泰示"],
    ]]
    rows = parse_jersey_rows(tables)
    assert [r.number for r in rows] == ["1", "6", "55"]
    assert rows[0].is_retired is True
    assert rows[0].current.startswith("永久欠番・王")
    assert rows[1].current.startswith("坂本")
    assert "小久保" in rows[1].history


def test_render_jersey_numbers_page_has_search_retired_and_topic_links() -> None:
    html = render_jersey_numbers_html(_rows())
    assert "巨人 歴代背番号一覧・変遷" in html
    assert 'id="ys-jersey-search"' in html
    assert html.count('id="ys-jersey-search"') == 1
    assert "永久欠番" in html
    assert "支配下・永久欠番 背番号" in html
    assert "育成背番号（3桁）" in html
    assert "王貞治" in html
    assert "長嶋茂雄" in html
    assert "#55" in html
    assert "#101" in html
    assert "/data/legends" in html
    assert "/data/draft" in html
    assert "/data/farm" in html
    assert "my favorite giants" in html


def test_title_and_excerpt() -> None:
    assert "歴代背番号" in render_jersey_numbers_title()
    assert "育成" in render_jersey_numbers_title()
    ex = render_jersey_numbers_excerpt(_rows())
    assert "育成背番号" in ex
    assert "掲載背番号6件" in ex
