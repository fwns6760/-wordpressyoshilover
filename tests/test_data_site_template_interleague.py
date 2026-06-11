"""Tests for the /data/interleague page template (セ・パ交流戦成績)。"""

from __future__ import annotations

from src.data_site_template_interleague import (
    load_interleague_data,
    render_interleague_excerpt,
    render_interleague_html,
    render_interleague_title,
)

SAMPLE = {
    "team_order": ["f", "e", "l", "m", "b", "h"],
    "giants_awards": {
        "mvp": [{"year": 2012, "player": "内海哲也"}],
        "nissay_award": [{"year": 2010, "player": "阿部慎之助"}],
    },
    "years": [
        {"year": 2025, "wareki": "令和7", "final": True, "rank": 11,
         "g": 18, "w": 6, "l": 11, "d": 1, "pct": ".353",
         "avg": ".227", "hr": 7, "sb": 8, "era": "2.94",
         "champion": "ソフトバンク", "champion_rec": "12勝5敗1分", "gb": "+6.0",
         "home": [5, 4, 0], "visitor": [1, 7, 1],
         "vs": {"f": [1, 2, 0], "e": [2, 1, 0], "l": [2, 1, 0],
                "m": [0, 3, 0], "b": [0, 3, 0], "h": [1, 1, 1]}},
        {"year": 2020, "wareki": "令和2", "cancelled": True,
         "note": "新型コロナウイルス感染拡大により交流戦中止"},
        {"year": 2012, "wareki": "平成24", "final": True, "rank": 1,
         "g": 24, "w": 17, "l": 7, "d": 0, "pct": ".708",
         "avg": ".269", "hr": 22, "sb": 17, "era": "2.29",
         "champion": "巨人", "champion_rec": "17勝7敗", "gb": "―",
         "home": [9, 3, 0], "visitor": [8, 4, 0],
         "vs": {"f": [2, 2, 0], "e": [3, 1, 0], "l": [3, 1, 0],
                "m": [2, 2, 0], "b": [3, 1, 0], "h": [4, 0, 0]}},
    ],
}

SAMPLE_LIVE = {
    **SAMPLE,
    "live": {
        "year": 2026,
        "standings": [
            {"rank": 1, "team": "ソフトバンク", "league": "パ", "g": 14,
             "w": 12, "l": 2, "t": 0, "pct": ".857"},
            {"rank": 2, "team": "巨人", "league": "セ", "g": 14,
             "w": 9, "l": 3, "t": 2, "pct": ".750"},
        ],
        "giants": {"year": 2026, "final": False, "rank": 2,
                   "g": 14, "w": 9, "l": 3, "d": 2, "pct": ".750",
                   "champion": "ソフトバンク", "gb": "+3.5",
                   "home": [5, 2, 2], "visitor": [4, 1, 0],
                   "vs": {"f": [2, 1, 0], "e": [2, 0, 0], "l": None,
                          "m": [1, 0, 2], "b": [3, 0, 0], "h": [1, 2, 0]}},
    },
}


def test_data_file_loads_verified_history() -> None:
    data = load_interleague_data()
    years = {int(y["year"]): y for y in data.get("years") or []}
    assert 2005 in years and 2025 in years
    assert years[2020].get("cancelled") is True
    # NPB公式照合済の補正値 (ベンチマーク誤記の修正)
    assert years[2025]["d"] == 1
    assert years[2013]["gb"] == "+2.0"
    assert years[2016]["gb"] == "+4.5"
    # 優勝2回
    champs = [y for y in years.values() if y.get("champion") == "巨人"]
    assert sorted(int(c["year"]) for c in champs) == [2012, 2014]
    # 通算 (2005-2025): 444試合 221勝209敗14分
    finals = [y for y in years.values() if y.get("final")]
    assert sum(y["g"] for y in finals) == 444
    assert sum(y["w"] for y in finals) == 221
    assert sum(y["l"] for y in finals) == 209
    assert sum(y["d"] for y in finals) == 14


def test_render_yearly_table_and_totals() -> None:
    h = render_interleague_html(SAMPLE)
    assert "年度別 交流戦成績一覧" in h
    assert "2025年" in h and "2012年" in h
    assert "🏆 巨人" in h  # 2012 優勝行
    assert "中止" in h  # 2020 行
    # 通算 = 42試合 23勝18敗1分
    assert "<b>42</b>" in h
    assert ">.353<" in h and ">.708<" in h


def test_render_vs_and_matrix_and_awards() -> None:
    h = render_interleague_html(SAMPLE)
    assert "パ・リーグ球団別 通算対戦成績" in h
    assert "年度×球団 勝敗マトリクス" in h
    assert "ソフトバンク" in h and "日本ハム" in h
    assert "交流戦MVP" in h and "内海哲也" in h
    assert "阿部慎之助" in h
    assert "2012年 交流戦優勝" in h


def test_render_live_section() -> None:
    h = render_interleague_html(SAMPLE_LIVE)
    assert "2026年 交流戦（開催中）12球団順位表" in h
    assert "暫定2位" in h
    assert "9勝3敗2分" in h
    h_baked = render_interleague_html(SAMPLE)
    assert "開催中" not in h_baked


def test_title_and_excerpt_span() -> None:
    assert "2005〜2025年" in render_interleague_title(SAMPLE)
    assert "2005〜2026年" in render_interleague_title(SAMPLE_LIVE)
    ex = render_interleague_excerpt(SAMPLE)
    assert "交流戦" in ex and "42試合" in ex


def test_no_source_or_external_links() -> None:
    h = render_interleague_html(SAMPLE_LIVE)
    assert "出典" not in h
    assert "my-favorite" not in h
    assert "npb.jp" not in h
    assert 'target="_blank"' not in h
