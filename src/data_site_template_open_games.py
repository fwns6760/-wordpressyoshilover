"""data/open-games page template (巨人 年度別オープン戦 結果 2001-2026).

データは config/giants_open_games.json (src/open_games_scraper.py 生成) を読む。
年別の全オープン戦結果 + 年間成績 (勝敗・勝率) を、勝=緑/負=赤で色分け。
出典・外部リンクは載せない。
"""
from __future__ import annotations

import html as _html
import json as _json
import os as _os

from src.data_site_internal_link import breadcrumb_jsonld
from src.data_site_related_links import dataset_jsonld, related_data_links_html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SLUG = "open-games"
_DATA_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "config", "giants_open_games.json"
)

_GAME_COLS = [
    ("no", "試合"),
    ("date", "日付"),
    ("opp", "対戦相手"),
    ("home", "H/V"),
    ("stadium", "球場"),
    ("result", "勝敗"),
    ("score", "スコア"),
    ("pitchers", "継投"),
    ("hits", "安打"),
    ("hr", "本塁打"),
]
_LEFT = {"opp", "stadium", "pitchers", "hr"}
_RESULT_STYLE = {
    "○": "background:#e6f4ea;color:#137333;font-weight:800;",
    "◯": "background:#e6f4ea;color:#137333;font-weight:800;",
    "●": "background:#fce8e6;color:#c5221f;font-weight:800;",
    "△": "background:#f1f3f4;color:#5f6368;font-weight:700;",
}
_PAGE_STYLE = (
    "<style>"
    ".ys-og{font-family:sans-serif;max-width:980px;}"
    ".ys-og__jump{position:sticky;top:0;z-index:5;background:#fff;padding:8px 0;margin:0 0 14px;"
    "border-bottom:1px solid #eee;line-height:2;}"
    ".ys-og table{width:100%;border-collapse:collapse;font-size:13px;}"
    ".ys-og thead th{position:sticky;top:0;z-index:2;background:#fff6ec;color:#7a2d00;"
    "font-size:12px;white-space:nowrap;}"
    ".ys-og th,.ys-og td{padding:6px 8px;border-bottom:1px solid #f0e6db;text-align:center;"
    "vertical-align:top;}"
    ".ys-og td.ys-l{text-align:left;}"
    ".ys-og tbody tr:nth-child(even) td{background:#fcfbf9;}"
    ".ys-og__scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #f0e6db;"
    "border-radius:8px;}"
    "@media(max-width:600px){.ys-og table{font-size:12px;min-width:820px;}"
    ".ys-og th,.ys-og td{padding:5px 6px;}}"
    "</style>"
)


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_open_games_data() -> dict:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def render_open_games_title(data: dict | None = None) -> str:
    data = data if data is not None else load_open_games_data()
    years = data.get("years") or []
    span = f"{years[-1].get('year')}〜{years[0].get('year')}年" if years else ""
    return f"巨人 オープン戦 成績【{span}・年度別の結果一覧】 | 巨人データ"


def render_open_games_excerpt(data: dict | None = None) -> str:
    data = data if data is not None else load_open_games_data()
    years = data.get("years") or []
    span = f"{years[-1].get('year')}〜{years[0].get('year')}年" if years else ""
    return (
        f"読売ジャイアンツ（巨人）のオープン戦（プレシーズン）結果を{span}まで年度別に一覧化。"
        "各試合の対戦相手・球場・勝敗・スコア・継投・安打・本塁打と、年ごとの勝敗・勝率をまとめた巨人データです。"
    )


def _summary(games: list[dict]) -> dict:
    win = loss = draw = 0
    for g in games:
        r = str(g.get("result") or "").strip()
        if r in ("○", "◯"):
            win += 1
        elif r == "●":
            loss += 1
        elif r == "△":
            draw += 1
    decided = win + loss
    pct = f"{win / decided:.3f}".lstrip("0") if decided else "―"
    return {"win": win, "loss": loss, "draw": draw, "pct": pct, "games": len(games)}


def _stat_pill(label: str, value: str, accent: str = "#e25400") -> str:
    return (
        '<span style="display:inline-flex;flex-direction:column;align-items:center;'
        'padding:6px 12px;margin:3px;border:1px solid #ffe0cc;border-radius:10px;background:#fff8f3;">'
        f'<b style="font-size:16px;color:{accent};line-height:1.1;">{_esc(value)}</b>'
        f'<em style="font-style:normal;font-size:10px;color:#888;margin-top:2px;">{_esc(label)}</em>'
        "</span>"
    )


def _result_cell(val: str) -> str:
    return f'<td style="{_RESULT_STYLE.get(val, "")}">{_esc(val)}</td>'


def _game_table(games: list[dict]) -> str:
    head = "".join(f"<th>{_esc(label)}</th>" for _k, label in _GAME_COLS)
    rows = []
    for g in games:
        cells = []
        for key, _label in _GAME_COLS:
            val = str(g.get(key) or "").strip()
            if key == "result":
                cells.append(_result_cell(val))
            elif key == "home":
                cells.append(f"<td>{'本拠地' if val == 'H' else '―'}</td>")
            elif key in _LEFT:
                cells.append(f'<td class="ys-l">{_esc(val)}</td>')
            else:
                cells.append(f"<td>{_esc(val)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<div class="ys-og__scroll"><table>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _year_jump_nav(years: list[dict]) -> str:
    chips = []
    for y in years:
        yr = int(y.get("year") or 0)
        if yr:
            chips.append(
                f'<a href="#og-year-{yr}" style="display:inline-block;padding:4px 9px;margin:2px;'
                f'border:1px solid #ffd9bf;border-radius:14px;color:#e25400;text-decoration:none;'
                f'font-size:12px;font-weight:700;">{yr}</a>'
            )
    return (
        '<div class="ys-og__jump">'
        '<span style="font-size:11px;color:#999;margin-right:6px;">年度へジャンプ:</span>'
        + "".join(chips)
        + "</div>"
    )


def _render_year(entry: dict, *, default_open: bool) -> str:
    yr = int(entry.get("year") or 0)
    games = entry.get("games") or []
    s = _summary(games)
    note = "（実施中）" if yr == 2026 else ""
    open_attr = " open" if default_open else ""
    pills = _stat_pill("成績", f"{s['win']}勝{s['loss']}敗{s['draw']}分", "#137333")
    pills += _stat_pill("勝率", s["pct"])
    pills += _stat_pill("試合数", f"{s['games']}試合", "#1565c0")
    return (
        f'<details id="og-year-{yr}"{open_attr} style="margin:0 0 14px;border:1px solid #ffe0cc;'
        'border-radius:10px;overflow:hidden;scroll-margin-top:64px;">'
        '<summary style="cursor:pointer;list-style:revert;padding:11px 14px;background:#fff6ec;'
        'font-size:16px;font-weight:800;color:#7a2d00;">'
        f"{yr}年 オープン戦 成績{note}"
        f'<span style="font-size:12px;color:#999;font-weight:400;">　{s["win"]}勝{s["loss"]}敗{s["draw"]}分'
        f"（{s['games']}試合）</span></summary>"
        '<div style="padding:12px 14px 14px;">'
        f'<div style="margin:0 0 12px;">{pills}</div>'
        + _game_table(games)
        + '<p style="margin:8px 0 0;font-size:11px;"><a href="#top" style="color:#999;">'
        "↑ 年度一覧へ戻る</a></p>"
        "</div></details>"
    )


def render_open_games_html(data: dict | None = None) -> str:
    data = data if data is not None else load_open_games_data()
    years = data.get("years") or []
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>オープン戦結果</span></nav>'
    )
    span = f"{years[-1].get('year')}〜{years[0].get('year')}年" if years else ""
    intro = (
        '<h1 id="top" style="font-size:21px;margin:0 0 4px;">巨人 オープン戦 成績（年度別 結果一覧）</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 12px;line-height:1.7;">'
        f"読売ジャイアンツ（巨人）の{span}のオープン戦（プレシーズン）結果を年度別にまとめた一覧です。"
        "各試合の対戦相手・球場・勝敗・スコア・継投・安打・本塁打に加え、年ごとの勝敗・勝率も掲載。"
        "見たい年度は上部のボタンからジャンプできます。</p>"
    )
    if not years:
        body = '<p style="color:#999;">オープン戦データを準備中です。</p>'
    else:
        body = _year_jump_nav(years) + "".join(
            _render_year(y, default_open=(idx < 1)) for idx, y in enumerate(years)
        )
    return (
        breadcrumb_jsonld("巨人 オープン戦成績", SLUG)
        + dataset_jsonld(
            name="巨人 オープン戦成績（年度別 2001〜2026年）",
            description=render_open_games_excerpt(data), slug=SLUG,
            temporal="2001/2026",
            keywords=["巨人", "読売ジャイアンツ", "オープン戦", "成績", "結果"],
        )
        + _PAGE_STYLE
        + '<div class="ys-og">'
        + intro
        + nav
        + body
        + related_data_links_html(SLUG)
        + "</div>"
    )


if __name__ == "__main__":
    import sys as _sys

    _sys.stdout.write(render_open_games_html())
