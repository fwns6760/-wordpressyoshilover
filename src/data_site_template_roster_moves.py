"""data/roster-moves page template (巨人 出場選手登録・抹消 2021-2026).

データは config/giants_roster_moves.json (src/roster_moves_scraper.py が生成) を読む。
2 部構成:
- 現在の1軍登録メンバー (最新年度の roster、位置別)
- 登録・抹消の動き (年別タイムライン、登録=緑 / 抹消=赤)

ベンチマークより「詳しく・使いやすく」: 位置別グルーピング+人数、色分けチップ、
年度ジャンプ追従、年ごと折りたたみ、モバイル対応。出典・外部リンクは載せない。
"""
from __future__ import annotations

import html as _html
import json as _json
import os as _os

from src.data_site_internal_link import breadcrumb_jsonld
from src.data_site_related_links import dataset_jsonld, related_data_links_html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SLUG = "roster-moves"
_DATA_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "config", "giants_roster_moves.json"
)
_POSITIONS = ("投手", "捕手", "内野手", "外野手")
_POS_ICON = {"投手": "⚾", "捕手": "🧤", "内野手": "🔶", "外野手": "🟢"}

_PAGE_STYLE = (
    "<style>"
    ".ys-rm{font-family:sans-serif;max-width:960px;}"
    ".ys-rm__jump{position:sticky;top:0;z-index:5;background:#fff;padding:8px 0;margin:0 0 14px;"
    "border-bottom:1px solid #eee;line-height:2;}"
    ".ys-rm table{width:100%;border-collapse:collapse;font-size:13px;}"
    ".ys-rm thead th{position:sticky;top:0;z-index:2;background:#eef3fb;color:#1a3a5c;"
    "font-size:12px;white-space:nowrap;}"
    ".ys-rm th,.ys-rm td{padding:7px 9px;border-bottom:1px solid #eef0f3;vertical-align:top;}"
    ".ys-rm__scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #eef0f3;"
    "border-radius:8px;}"
    ".ys-rm__date{white-space:nowrap;font-weight:700;color:#444;width:64px;}"
    ".ys-rm__chip{display:inline-block;padding:3px 9px;margin:2px;border-radius:999px;"
    "font-size:12px;font-weight:700;white-space:nowrap;}"
    ".ys-rm__in{background:#e6f4ea;color:#137333;border:1px solid #b7e1c3;}"
    ".ys-rm__out{background:#fce8e6;color:#c5221f;border:1px solid #f3c2bd;}"
    ".ys-rm__rosgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:0 0 8px;}"
    ".ys-rm__poscard{border:1px solid #e3e8ef;border-radius:10px;padding:10px 12px;background:#fbfcfe;}"
    ".ys-rm__poshd{font-size:14px;font-weight:800;color:#1a3a5c;margin:0 0 6px;}"
    ".ys-rm__player{display:inline-flex;align-items:baseline;gap:5px;margin:2px 8px 2px 0;font-size:13px;}"
    ".ys-rm__no{display:inline-block;min-width:24px;text-align:center;font-weight:800;color:#1565c0;"
    "font-variant-numeric:tabular-nums;}"
    "@media(max-width:600px){.ys-rm__rosgrid{grid-template-columns:1fr;}"
    ".ys-rm table{font-size:12px;}.ys-rm th,.ys-rm td{padding:6px 7px;}}"
    "</style>"
)


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def _name(s: str) -> str:
    return _esc(str(s or "").replace("　", " ").strip())


def load_roster_moves_data() -> dict:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def render_roster_moves_title(data: dict | None = None) -> str:
    data = data if data is not None else load_roster_moves_data()
    years = data.get("years") or []
    span = f"{years[-1].get('year')}〜{years[0].get('year')}年" if years else ""
    return f"巨人 出場選手登録・抹消【{span}・1軍登録の動き】 | 巨人データ"


def render_roster_moves_excerpt(data: dict | None = None) -> str:
    data = data if data is not None else load_roster_moves_data()
    years = data.get("years") or []
    span = ""
    if years:
        span = f"{years[-1].get('year')}〜{years[0].get('year')}年"
    return (
        f"読売ジャイアンツの出場選手登録・登録抹消（1軍登録の動き）を{span}まで日付順に一覧化。"
        "現在の1軍登録メンバーを位置別に、登録＝緑・抹消＝赤で分かりやすくまとめた巨人データです。"
    )


def _latest_roster(years: list[dict]) -> tuple[int, list[dict]]:
    for y in years:
        if y.get("roster"):
            return int(y.get("year") or 0), y["roster"]
    return 0, []


def _current_roster_section(years: list[dict]) -> str:
    yr, roster = _latest_roster(years)
    if not roster:
        return ""
    by_pos: dict[str, list[dict]] = {p: [] for p in _POSITIONS}
    for r in roster:
        by_pos.setdefault(r.get("pos", ""), []).append(r)
    cards = ""
    for pos in _POSITIONS:
        members = by_pos.get(pos) or []
        if not members:
            continue
        players = "".join(
            f'<span class="ys-rm__player"><b class="ys-rm__no">{_esc(m.get("no"))}</b>'
            f'{_name(m.get("name"))}</span>'
            for m in members
        )
        cards += (
            '<div class="ys-rm__poscard">'
            f'<div class="ys-rm__poshd">{_POS_ICON.get(pos, "")} {_esc(pos)}'
            f'<span style="font-size:11px;color:#999;font-weight:600;">（{len(members)}人）</span></div>'
            f"{players}</div>"
        )
    return (
        f'<section style="margin:0 0 22px;">'
        f'<h2 style="font-size:17px;margin:0 0 4px;">🟧 現在の1軍登録メンバー（{yr}年・{len(roster)}人）</h2>'
        '<p style="font-size:12px;color:#777;margin:0 0 10px;">'
        "いま一軍に登録されている支配下選手を位置別にまとめています。</p>"
        f'<div class="ys-rm__rosgrid">{cards}</div></section>'
    )


def _chips(names: list[str], cls: str) -> str:
    if not names:
        return '<span style="color:#ccc;">―</span>'
    return "".join(f'<span class="ys-rm__chip {cls}">{_name(n)}</span>' for n in names)


def _moves_table(moves: list[dict]) -> str:
    body = []
    for m in moves:
        body.append(
            f'<tr><td class="ys-rm__date">{_esc(m.get("date"))}</td>'
            f'<td>{_chips(m.get("reg") or [], "ys-rm__in")}</td>'
            f'<td>{_chips(m.get("out") or [], "ys-rm__out")}</td></tr>'
        )
    return (
        '<div class="ys-rm__scroll"><table>'
        '<thead><tr><th>日付</th><th>🟢 登録</th><th>🔴 抹消</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def _year_jump_nav(years: list[dict]) -> str:
    chips = []
    for y in years:
        yr = int(y.get("year") or 0)
        if yr:
            chips.append(
                f'<a href="#rm-year-{yr}" style="display:inline-block;padding:4px 9px;margin:2px;'
                f'border:1px solid #cfe0f5;border-radius:14px;color:#1565c0;text-decoration:none;'
                f'font-size:12px;font-weight:700;">{yr}</a>'
            )
    return (
        '<div class="ys-rm__jump">'
        '<span style="font-size:11px;color:#999;margin-right:6px;">年度へジャンプ:</span>'
        + "".join(chips)
        + "</div>"
    )


def _render_year(entry: dict, *, default_open: bool) -> str:
    yr = int(entry.get("year") or 0)
    moves = entry.get("moves") or []
    reg_total = sum(len(m.get("reg") or []) for m in moves)
    out_total = sum(len(m.get("out") or []) for m in moves)
    note = "（シーズン進行中）" if yr == 2026 else ""
    open_attr = " open" if default_open else ""
    return (
        f'<details id="rm-year-{yr}"{open_attr} style="margin:0 0 14px;border:1px solid #dce6f2;'
        'border-radius:10px;overflow:hidden;scroll-margin-top:64px;">'
        '<summary style="cursor:pointer;list-style:revert;padding:11px 14px;background:#eef3fb;'
        'font-size:16px;font-weight:800;color:#1a3a5c;">'
        f"{yr}年 登録・抹消{note}"
        f'<span style="font-size:12px;color:#888;font-weight:400;">　登録{reg_total}・抹消{out_total}'
        f"（{len(moves)}日）</span></summary>"
        '<div style="padding:12px 14px 14px;">'
        + _moves_table(moves)
        + '<p style="margin:8px 0 0;font-size:11px;"><a href="#top" style="color:#999;">'
        "↑ 年度一覧へ戻る</a></p>"
        "</div></details>"
    )


def render_roster_moves_html(data: dict | None = None) -> str:
    data = data if data is not None else load_roster_moves_data()
    years = data.get("years") or []
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>出場選手登録・抹消</span></nav>'
    )
    span = f"{years[-1].get('year')}〜{years[0].get('year')}年" if years else ""
    intro = (
        '<h1 id="top" style="font-size:21px;margin:0 0 4px;">巨人 出場選手登録・抹消</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 12px;line-height:1.7;">'
        f"読売ジャイアンツの一軍（出場選手）登録・登録抹消の動きを{span}まで日付順にまとめた一覧です。"
        "いま誰が一軍にいるか（現在の登録メンバー）と、いつ誰が上がり・下がったか（登録＝緑／抹消＝赤）を"
        "ひと目で確認できます。見たい年度は上部のボタンからジャンプできます。</p>"
    )
    if not years:
        body = '<p style="color:#999;">登録・抹消のデータを準備中です。</p>'
    else:
        body = (
            _current_roster_section(years)
            + '<h2 style="font-size:17px;margin:18px 0 8px;">🔁 登録・抹消の動き</h2>'
            + _year_jump_nav(years)
            + "".join(
                _render_year(y, default_open=(idx < 1)) for idx, y in enumerate(years)
            )
        )
    return (
        breadcrumb_jsonld("巨人 出場選手登録・抹消", SLUG)
        + dataset_jsonld(
            name="巨人 出場選手登録・抹消（1軍登録の動き 2001〜2026年）",
            description=render_roster_moves_excerpt(data), slug=SLUG,
            temporal="2001/2026",
            keywords=["巨人", "読売ジャイアンツ", "出場選手登録", "登録抹消", "1軍登録"],
        )
        + _PAGE_STYLE
        + '<div class="ys-rm">'
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

    _sys.stdout.write(render_roster_moves_html())
