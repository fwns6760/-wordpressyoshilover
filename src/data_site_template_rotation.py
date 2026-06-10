"""data/rotation page template (先発ローテ一覧 2007-2026).

巨人の年別・試合ごとの先発投手ログを一枚にまとめた history spoke。
データは config/starter_rotation_2007_2026.json (scripts/scrape_starter_rotation.py
が事前生成) を読む。フロント表示時の外部 fetch は行わない。

ベンチマーク (年別の生テーブル羅列) より「詳しく・使いやすく」:
- 年ごとのシーズン要約 (チーム勝敗 / QS率 / 起用投手数 / 最多先発)
- 勝敗の色分け・ゼブラ・見出し固定・モバイル対応・年度ジャンプ追従・年ごと折りたたみ

user 方針 (2026-06-09): 出典 (取得元) リンク・表記は載せない。
先発投手・試合結果は事実データのため、名前と数値のみを独自構成で再掲載する。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os
import re as _re

from src.data_site_internal_link import breadcrumb_jsonld
from src.data_site_related_links import dataset_jsonld, related_data_links_html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SLUG = "rotation"
_DATA_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "config", "starter_rotation_2007_2026.json"
)

# 試合ログで見せる列 (key, 見出し)。JSON game dict の key に対応。
_GAME_COLS = [
    ("game_no", "試合"),
    ("date", "日付"),
    ("weekday", "曜"),
    ("opp", "対戦"),
    ("stadium", "球場"),
    ("team_result", "チーム"),
    ("pitcher", "先発投手"),
    ("decision", "勝敗"),
    ("ip", "投球回"),
    ("pitches", "球数"),
    ("hits", "被安打"),
    ("so", "奪三振"),
    ("runs", "失点"),
    ("qs", "QS"),
]
_RESULT_COLS = {"team_result", "decision"}

# 結果記号 → 背景/文字色 (inline。<style> が剥がれても色は残す)
_RESULT_STYLE = {
    "○": "background:#e6f4ea;color:#137333;font-weight:800;",
    "◯": "background:#e6f4ea;color:#137333;font-weight:800;",
    "●": "background:#fce8e6;color:#c5221f;font-weight:800;",
    "△": "background:#f1f3f4;color:#5f6368;font-weight:700;",
}

_PAGE_STYLE = (
    "<style>"
    ".ys-rot{font-family:sans-serif;max-width:960px;}"
    ".ys-rot table{width:100%;border-collapse:collapse;font-size:13px;}"
    ".ys-rot thead th{position:sticky;top:0;z-index:2;background:#fff6ec;color:#7a2d00;"
    "font-size:12px;white-space:nowrap;}"
    ".ys-rot th,.ys-rot td{padding:6px 8px;border-bottom:1px solid #f0e6db;text-align:center;}"
    ".ys-rot td.ys-l{text-align:left;}"
    ".ys-rot tbody tr:nth-child(even) td{background:#fcfbf9;}"
    ".ys-rot tbody tr:hover td{background:#fff3e8;}"
    ".ys-rot__scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #f0e6db;"
    "border-radius:8px;}"
    ".ys-rot__jump{position:sticky;top:0;z-index:5;background:#fff;padding:8px 0;margin:0 0 14px;"
    "border-bottom:1px solid #eee;line-height:2;}"
    "@media(max-width:600px){.ys-rot table{font-size:12px;min-width:760px;}"
    ".ys-rot th,.ys-rot td{padding:5px 6px;}}"
    "</style>"
)


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_rotation_data() -> dict:
    """config/starter_rotation_2007_2026.json を読む。失敗時は空 dict。"""
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _pitcher_link(name: str) -> str:
    # 投手名は姓のみ (例: 戸郷 / 高橋尚) で、prefix 一致で選手ページに繋ぐと
    # 歴史データで別人に誤リンクする恐れがある (事実誤認 NG)。プレーン表記に留める。
    return _esc(name)


def render_rotation_title() -> str:
    return "巨人 先発ローテーション 成績【2007〜2026年・試合ごとの先発投手成績一覧】 | 巨人データ"


def render_rotation_excerpt(data: dict | None = None) -> str:
    data = data if data is not None else load_rotation_data()
    years = data.get("years") or []
    span = ""
    if years:
        span = f"{years[-1].get('year')}〜{years[0].get('year')}年"
    return (
        f"読売ジャイアンツの先発ローテーションを{span}まで年別・試合ごとに一覧化。"
        "各試合の先発投手・対戦相手・球場・投球回・勝敗・QSに加え、"
        "年ごとのシーズン要約（勝敗・QS率・最多先発）も掲載した巨人データの一覧です。"
    )


def _season_summary(entry: dict) -> dict:
    """その年の要約指標を計算 (チーム勝敗 / QS数・率 / 起用投手数 / 最多先発)。"""
    games = entry.get("games") or []
    win = loss = draw = qs = 0
    for g in games:
        tr = str(g.get("team_result") or "").strip()
        if tr in ("○", "◯"):
            win += 1
        elif tr == "●":
            loss += 1
        elif tr == "△":
            draw += 1
        if str(g.get("qs") or "").strip().upper() == "QS":
            qs += 1
    pitchers = entry.get("pitchers") or []
    leader = pitchers[0] if pitchers else {}
    qs_rate = round(qs * 100 / len(games)) if games else 0
    return {
        "games": len(games),
        "win": win, "loss": loss, "draw": draw,
        "qs": qs, "qs_rate": qs_rate,
        "pitchers_used": len(pitchers),
        "leader_name": str(leader.get("name") or ""),
        "leader_starts": int(leader.get("starts") or 0),
    }


def _stat_pill(label: str, value: str, accent: str = "#e25400") -> str:
    return (
        '<span style="display:inline-flex;flex-direction:column;align-items:center;'
        'padding:6px 12px;margin:3px;border:1px solid #ffe0cc;border-radius:10px;background:#fff8f3;">'
        f'<b style="font-size:16px;color:{accent};line-height:1.1;">{_esc(value)}</b>'
        f'<em style="font-style:normal;font-size:10px;color:#888;margin-top:2px;">{_esc(label)}</em>'
        "</span>"
    )


def _year_jump_nav(years: list[dict]) -> str:
    chips = []
    for y in years:
        yr = int(y.get("year") or 0)
        if not yr:
            continue
        chips.append(
            f'<a href="#year-{yr}" style="display:inline-block;padding:4px 9px;margin:2px;'
            f'border:1px solid #ffd9bf;border-radius:14px;color:#e25400;text-decoration:none;'
            f'font-size:12px;font-weight:700;">{yr}</a>'
        )
    return (
        '<div class="ys-rot__jump">'
        '<span style="font-size:11px;color:#999;margin-right:6px;">年度へジャンプ:</span>'
        + "".join(chips)
        + "</div>"
    )


def _pitcher_summary(pitchers: list[dict]) -> str:
    chips = []
    for p in pitchers:
        name = str(p.get("name") or "").strip()
        starts = int(p.get("starts") or 0)
        if not name or starts <= 0:
            continue
        chips.append(
            '<span style="display:inline-flex;align-items:center;gap:5px;padding:4px 9px;margin:2px;'
            'border:1px solid #ffd9bf;border-radius:999px;background:#fff8f3;font-size:12px;">'
            f'<b style="color:#222;">{_pitcher_link(name)}</b>'
            f'<em style="font-style:normal;font-weight:800;color:#e25400;">{starts}</em></span>'
        )
    if not chips:
        return ""
    return (
        '<div style="margin:0 0 10px;">'
        '<span style="font-size:12px;color:#666;margin-right:4px;">先発数:</span>'
        + "".join(chips)
        + "</div>"
    )


def _result_cell(val: str) -> str:
    style = _RESULT_STYLE.get(val, "")
    return f'<td style="{style}">{_esc(val)}</td>'


def _game_table(games: list[dict]) -> str:
    head = "".join(f"<th>{_esc(label)}</th>" for _key, label in _GAME_COLS)
    body_rows = []
    for g in games:
        cells = []
        for key, _label in _GAME_COLS:
            val = str(g.get(key) or "").strip()
            if key in _RESULT_COLS:
                cells.append(_result_cell(val))
            elif key == "pitcher":
                cells.append(f'<td class="ys-l"><b>{_pitcher_link(val)}</b></td>')
            elif key in ("opp", "stadium"):
                cells.append(f'<td class="ys-l">{_esc(val)}</td>')
            else:
                cells.append(f"<td>{_esc(val)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<div class="ys-rot__scroll"><table>'
        f"<thead><tr>{head}</tr></thead>"
        "<tbody>" + "".join(body_rows) + "</tbody></table></div>"
    )


def _render_year(entry: dict, *, default_open: bool) -> str:
    yr = int(entry.get("year") or 0)
    games = entry.get("games") or []
    pitchers = entry.get("pitchers") or []
    s = _season_summary(entry)
    note = "（シーズン進行中）" if yr == 2026 else ""
    open_attr = " open" if default_open else ""

    pills = _stat_pill("チーム成績", f"{s['win']}勝{s['loss']}敗{s['draw']}分", "#137333")
    pills += _stat_pill("QS", f"{s['qs']}（{s['qs_rate']}%）")
    pills += _stat_pill("起用先発", f"{s['pitchers_used']}人", "#1565c0")
    if s["leader_name"]:
        pills += _stat_pill("最多先発", f"{s['leader_name']} {s['leader_starts']}")

    summary_meta = f"　全{len(games)}試合"
    if s["leader_name"]:
        summary_meta += f"　最多 {_esc(s['leader_name'])} {s['leader_starts']}"

    return (
        f'<details id="year-{yr}"{open_attr} style="margin:0 0 14px;border:1px solid #ffe0cc;'
        'border-radius:10px;overflow:hidden;scroll-margin-top:64px;">'
        '<summary style="cursor:pointer;list-style:revert;padding:11px 14px;background:#fff6ec;'
        'font-size:16px;font-weight:800;color:#7a2d00;">'
        f"{yr}年 先発ローテ 成績{note}"
        f'<span style="font-size:12px;color:#999;font-weight:400;">{summary_meta}</span></summary>'
        '<div style="padding:12px 14px 14px;">'
        f'<div style="margin:0 0 12px;">{pills}</div>'
        + _pitcher_summary(pitchers)
        + _game_table(games)
        + '<p style="margin:8px 0 0;font-size:11px;"><a href="#top" style="color:#999;">'
        "↑ 年度一覧へ戻る</a></p>"
        "</div></details>"
    )


def render_rotation_html(data: dict | None = None) -> str:
    data = data if data is not None else load_rotation_data()
    years = data.get("years") or []
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>先発ローテ一覧</span></nav>'
    )
    span = ""
    total_games = sum(len(y.get("games") or []) for y in years)
    if years:
        span = f"{years[-1].get('year')}〜{years[0].get('year')}年"
    intro = (
        '<h1 id="top" style="font-size:21px;margin:0 0 4px;">巨人 先発ローテーション 成績（試合ごとの先発投手）</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 12px;line-height:1.7;">'
        f"読売ジャイアンツの{span}（全{total_games:,}試合）の先発ローテーションを、"
        "1試合ずつ年別にまとめた一覧です。各試合の先発投手・対戦相手・球場・チーム/投手の勝敗・"
        "投球回・球数・被安打・奪三振・失点・QSに加え、年ごとのシーズン要約も掲載。"
        "見たい年度は上部のボタンからいつでもジャンプできます。</p>"
    )
    if not years:
        body = '<p style="color:#999;">先発ローテのデータを準備中です。</p>'
    else:
        body = _year_jump_nav(years) + "".join(
            _render_year(y, default_open=(idx < 2)) for idx, y in enumerate(years)
        )
    return (
        breadcrumb_jsonld("巨人 先発ローテ成績", SLUG)
        + dataset_jsonld(
            name="巨人 先発ローテーション成績（2007〜2026年）",
            description=render_rotation_excerpt(data), slug=SLUG,
            temporal="2007/2026",
            keywords=["巨人", "読売ジャイアンツ", "先発ローテーション", "先発投手", "成績"],
        )
        + _PAGE_STYLE
        + '<div class="ys-rot">'
        # SEO: meta description は本文先頭から自動生成されるため、h1+リード文を先に置き
        # パンくず (Home › …) を後ろに回してスニペットを綺麗にする
        + intro
        + nav
        + body
        + related_data_links_html(SLUG)
        + "</div>"
    )


if __name__ == "__main__":
    import sys as _sys

    _sys.stdout.write(render_rotation_html())
