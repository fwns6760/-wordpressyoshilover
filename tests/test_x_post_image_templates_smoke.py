"""437 全 template smoke tests.

各 template に最小 mock data を流して PNG 生成 / 1080x1080 / < 500KB を確認。
template 個別の render 詳細 (色 / 文字 / 位置) は test_x_post_image_gen.py が ranking_table で網羅、
本 file は全 13 template を grep ベースで 1 回ずつ render 通せることだけ確認する。
"""
from __future__ import annotations

import struct

import pytest

from src.x_post_image_gen import (
    PNG_MAX_BYTES,
    generate_png,
    render_svg,
)


def _ranking_data():
    return {
        "title": "セ・リーグ OPS ランキング",
        "subtitle": "直近 10 試合 / 規定打席 20 以上",
        "hook_line": "🔥 巨人 2 名 トップ 10 入り",
        "rows": [
            {"rank": i + 1, "name": f"選手{i + 1}", "team": "巨人" if i in (2, 7) else "他",
             "value": f".{900 - i * 10}", "is_giants": i in (2, 7)}
            for i in range(8)
        ],
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _spotlight_data():
    return {
        "hook_line": "🔥 直近 10 試合 OPS が球団 1 位",
        "date_str": "2026/05/25",
        "player_name": "坂本勇人",
        "player_team": "巨人",
        "player_position": "内野手",
        "metric_label": "直近 10 試合 OPS",
        "hero_value": ".867",
        "sub1_label": "セ・リーグ順位",
        "sub1_value": "3",
        "sub2_label": "前 10 試合比",
        "sub2_value": "+.082",
        "comment_line": "調子上向き / 3 番起用継続",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _scoreboard_data():
    return {
        "hook_line": "🔥 連勝 3 / 5 月後半 7 勝 3 敗",
        "game_meta": "2026.05.25 (日) 東京ドーム / 18:00",
        "opponent_name": "阪神",
        "opponent_short": "阪神",
        "giants_innings": [0, 2, 0, 0, 3, 1, 0, 0, "X"],
        "opponent_innings": [0, 0, 1, 0, 0, 0, 2, 0, 0],
        "giants_r": 6, "giants_h": 11,
        "opponent_r": 3, "opponent_h": 8,
        "result_line": "巨人 6 - 3 阪神",
        "result_sub": "勝利 / 連勝 3",
        "highlights": [
            {"label": "勝利投手", "player": "戸郷翔征", "detail": "5勝1敗 防2.18"},
            {"label": "本塁打", "player": "岡本和真", "detail": "8号 3ラン"},
            {"label": "決勝打", "player": "坂本勇人", "detail": "5回 適時打"},
        ],
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _lineup_data():
    players = []
    for i in range(9):
        players.append({
            "order": f"{i + 1}番",
            "position": "中",
            "name": f"選手{i + 1}",
            "stat": f".{300 - i * 5}",
            "sub": "OPS .800",
            "is_star": i in (2, 3, 8),
        })
    return {
        "hook_line": "⚾ 主軸 3-4 番 ★ 連続マルチ安打",
        "subtitle": "巨人 vs 阪神 / 2026.05.25 18:00",
        "players": players,
        "starting_pitcher": "戸郷翔征 (5勝1敗 防御率 2.18)",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _standings_data():
    return {
        "hook_line": "📈 巨人 2 位浮上 / 首位まで 3.5 G 差",
        "league_name": "セ・リーグ",
        "subtitle": "2026.05.25 終了時点",
        "rows": [
            {"rank": 1, "team": "阪神",   "record": "32-18-1", "pct": ".640", "gb": "—",   "is_giants": False},
            {"rank": 2, "team": "巨人",   "record": "28-21-2", "pct": ".571", "gb": "3.5", "is_giants": True},
            {"rank": 3, "team": "広島",   "record": "25-23-2", "pct": ".521", "gb": "6.0", "is_giants": False},
            {"rank": 4, "team": "DeNA",   "record": "24-25-1", "pct": ".490", "gb": "7.5", "is_giants": False},
            {"rank": 5, "team": "ヤクルト","record": "20-28-2", "pct": ".417", "gb": "11.0","is_giants": False},
            {"rank": 6, "team": "中日",   "record": "19-30-1", "pct": ".388", "gb": "12.5","is_giants": False},
        ],
        "footer_summary": "巨人 / 2 位 / 首位まで 3.5 ゲーム差",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _pitcher_card_data():
    return {
        "hook_line": "戸郷翔征 完投勝利",
        "player_name": "戸郷翔征",
        "pitch_outcome": "完投勝利",
        "player_team": "巨人",
        "player_throws_bats": "右投右打",
        "game_meta": "2026.05.25 vs 阪神 / 東京ドーム",
        "result_line": "巨人 6 - 3 阪神 (今季 5勝目)",
        "stats": [
            {"label": "投球回", "value": "9.0", "highlight": True},
            {"label": "被安打", "value": "8", "highlight": False},
            {"label": "自責点", "value": "3", "highlight": False},
            {"label": "奪三振", "value": "11", "highlight": True},
            {"label": "与四球", "value": "1", "highlight": False},
            {"label": "球数", "value": "118", "highlight": False},
        ],
        "season_stats": [
            {"label": "今季成績", "value": "5勝1敗"},
            {"label": "防御率", "value": "2.18"},
            {"label": "奪三振", "value": "64"},
        ],
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _monthly_summary_data():
    return {
        "hook_line": "🔥 月間 15 勝 8 敗 / セ・リーグ 1 位ペース",
        "period_label": "5 月",
        "subtitle": "巨人 / 2026.05.01 - 05.25",
        "kpis": [
            {"label": "月間成績", "value": "15勝8敗", "color": "#FF6F00", "stroke": "#000",
             "stroke_width": 2, "font_size": 78, "sub": "勝率 .652"},
            {"label": "チーム打率", "value": ".272", "sub": "セ・リーグ 2 位"},
            {"label": "チーム防御率", "value": "2.84", "sub": "セ・リーグ 1 位"},
        ],
        "mvp_name": "岡本和真",
        "mvp_stats": "打率 .312 / 8HR / 24打点 / OPS .921",
        "top3_title": "月間 OPS TOP 3 (巨人)",
        "top3": [
            {"name": "岡本和真", "bar_width": 650, "value": ".921"},
            {"name": "坂本勇人", "bar_width": 580, "value": ".867"},
            {"name": "丸佳浩",   "bar_width": 480, "value": ".798"},
        ],
        "highlight_line": "月間 MAX: 岡本 5/18 サヨナラ満塁HR",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _crown_data():
    return {
        "hook_line": "12 球団 主要打撃 すべて 1 位",
        "player_name": "岡本和真",
        "player_team": "巨人",
        "player_position": "一塁手",
        "crown_count": 6,
        "tiles": [
            {"label": "打率",   "value": ".312", "rank": 1, "font_size": 120},
            {"label": "本塁打", "value": "8",    "rank": 1, "font_size": 160},
            {"label": "打点",   "value": "24",   "rank": 1, "font_size": 160},
            {"label": "OPS",    "value": ".921", "rank": 1, "font_size": 120},
            {"label": "出塁率", "value": ".398", "rank": 1, "font_size": 120},
            {"label": "長打率", "value": ".523", "rank": 1, "font_size": 120},
        ],
        "subtitle": "2026.05.25 終了時点 / 規定打席到達者 84 名中",
        "footer_summary": "6 冠 独走中 / 球団史上稀有",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _crown_3_data():
    return {
        "hook_line": "12 球団 主要打撃 3 指標 1 位",
        "player_name": "岡本和真",
        "player_team": "巨人",
        "player_position": "一塁手",
        "crown_count": 3,
        "primary_tiles": [
            {"label": "打率",   "value": ".312", "font_size": 150},
            {"label": "本塁打", "value": "8",    "font_size": 200},
            {"label": "OPS",    "value": ".921", "font_size": 150},
        ],
        "secondary_rows": [
            {"label": "打点", "value": "24", "rank": 2},
            {"label": "出塁率", "value": ".398", "rank": 3},
            {"label": "長打率", "value": ".523", "rank": 2},
        ],
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _data_sheet_data():
    players = []
    for i in range(8):
        players.append({
            "name": f"選手{i + 1}",
            "position": "一塁手",
            "stats": [".312", "8", "24", ".921", ".398", ".523"],
            "is_leader": i == 0,
        })
    return {
        "title": "巨人 主力 8 名 最新打撃成績",
        "subtitle": "2026.05.25 終了時点 / 規定打席 20 以上",
        "columns": ["打率", "HR", "打点", "OPS", "出塁率", "長打率"],
        "players": players,
        "footer_summary": "岡本 = 6 項目 全 1 位 (チーム内)",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ / 主要打撃指標 8 名比較",
    }


def _chart_bars_data():
    games = []
    for i, (label, val, is_off, is_win) in enumerate([
        ("5/15", 2, False, True),
        ("5/16", 4, False, True),
        ("5/17", 1, False, True),
        ("5/18", 0, True, False),
        ("5/19", 2, False, True),
        ("5/20", 0, True, False),
        ("5/21", 1, False, False),
        ("5/22", 4, False, False),
        ("5/23", 0, False, False),
        ("5/24", 3, False, False),
    ]):
        games.append({"label": label, "value": val, "is_off": is_off, "is_win": is_win})
    return {
        "title": "巨人 直近 10 試合 得点推移",
        "subtitle": "2026/05/15 〜 2026/05/24",
        "games": games,
        "max_y": 10,
        "summary_line": "直近 10 試合: 4 勝 5 敗 / 阪神戦 3 連敗中",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _12team_bar_data():
    teams = [
        {"name": "阪神",        "value": 0.742, "value_label": ".742", "is_giants": False},
        {"name": "巨人",        "value": 0.738, "value_label": ".738", "is_giants": True},
        {"name": "広島",        "value": 0.710, "value_label": ".710", "is_giants": False},
        {"name": "ロッテ",      "value": 0.705, "value_label": ".705", "is_giants": False},
        {"name": "ソフトバンク","value": 0.695, "value_label": ".695", "is_giants": False},
        {"name": "オリックス",  "value": 0.682, "value_label": ".682", "is_giants": False},
        {"name": "日本ハム",    "value": 0.668, "value_label": ".668", "is_giants": False},
        {"name": "DeNA",        "value": 0.660, "value_label": ".660", "is_giants": False},
        {"name": "西武",        "value": 0.648, "value_label": ".648", "is_giants": False},
        {"name": "ヤクルト",    "value": 0.638, "value_label": ".638", "is_giants": False},
        {"name": "中日",        "value": 0.620, "value_label": ".620", "is_giants": False},
        {"name": "楽天",        "value": 0.605, "value_label": ".605", "is_giants": False},
    ]
    return {
        "hook_line": "⚡ 巨人 .738 / 12 球団 2 位 / 首位まで .004 差",
        "title": "12 球団 チーム OPS",
        "subtitle": "2026.05.25 終了時点 / 全打席",
        "teams": teams,
        "max_value": 0.742,
        "footer_summary": "巨人 / 12 球団 2 位 / 首位阪神まで .004 差",
        "footer_detail": "セ・リーグ 2 位 / パとの比較は OPS で僅差",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


def _spray_chart_data():
    hits = []
    # HR (orange) 3
    for x, y in [(320, 370), (560, 320), (760, 380)]:
        hits.append({"x": x, "y": y, "r": 14, "color": "#FF6F00", "sw": 3})
    # 2B (gold) 4
    for x, y in [(420, 470), (640, 450), (710, 490), (380, 520)]:
        hits.append({"x": x, "y": y, "r": 11, "color": "#FFD700", "sw": 2})
    # singles (red) 5
    for x, y in [(480, 580), (600, 580), (450, 620), (560, 640), (620, 620)]:
        hits.append({"x": x, "y": y, "r": 9, "color": "#D84315", "sw": 2})
    return {
        "player_name": "岡本和真",
        "subtitle": "直近 10 試合 / 安打 12 本 (HR 3 / 二塁打 4)",
        "hits": hits,
        "legend": [
            {"label": "本塁打 3", "color": "#FF6F00", "r": 12},
            {"label": "二塁打 4", "color": "#FFD700", "r": 10},
            {"label": "単打 5",   "color": "#D84315", "r": 8},
        ],
        "legend_total": "合計 12 安打 / 35 打数",
        "stats_panel_title": "直近 10 試合",
        "stats_main_label": "打率",
        "stats_main_value": ".343",
        "stats_sub": "OPS 1.020",
        "footer_summary": "引っ張り傾向 / 左中間 + 右中間に集中",
        "footer_detail": "逆方向打率 .520",
        "footer_handle": "@yoshilover_giants",
        "footer_meta": "巨人データ",
    }


_FIXTURES = [
    ("ranking_table", _ranking_data),
    ("player_spotlight", _spotlight_data),
    ("scoreboard", _scoreboard_data),
    ("starting_lineup", _lineup_data),
    ("standings", _standings_data),
    ("pitcher_card", _pitcher_card_data),
    ("monthly_summary", _monthly_summary_data),
    ("12team_crown", _crown_data),
    ("12team_crown_3", _crown_3_data),
    ("data_sheet", _data_sheet_data),
    ("chart_bars", _chart_bars_data),
    ("12team_bar", _12team_bar_data),
    ("spray_chart", _spray_chart_data),
]


@pytest.mark.parametrize("template_key,build_fn", _FIXTURES,
                          ids=[t for t, _ in _FIXTURES])
def test_template_renders_and_produces_valid_png(template_key, build_fn):
    """各 template が render 成功 + 1080x1080 PNG + size cap 内であること。"""
    data = build_fn()
    svg = render_svg(template_key, data)
    assert svg.startswith("<svg") or svg.startswith("<?xml") or "<svg" in svg[:200]
    png = generate_png(template_key, data)
    assert png is not None, f"PNG generation returned None for {template_key}"
    # PNG magic
    assert png[:8] == b"\x89PNG\r\n\x1a\n", f"invalid PNG signature for {template_key}"
    # 1080x1080
    width = struct.unpack(">I", png[16:20])[0]
    height = struct.unpack(">I", png[20:24])[0]
    assert width == 1080, f"{template_key} width {width} != 1080"
    assert height == 1080, f"{template_key} height {height} != 1080"
    # < 500KB cap
    assert len(png) <= PNG_MAX_BYTES, (
        f"{template_key} PNG size {len(png)} > {PNG_MAX_BYTES}"
    )
