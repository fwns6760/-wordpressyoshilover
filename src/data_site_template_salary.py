"""data/salary 年俸ページ template (選手別 推定年俸推移 + 一覧ランキング).

データは config/giants_salary.json (検証済み baked 履歴) を読む。
- 一覧 (/data/salary/): 当年推定年俸の降順ランキング。各行から選手別ページへ。
- 選手別 (/data/salary/<player-slug>/): 入団から当年までの年度別推定年俸を
  棒グラフ (年度別) + 折れ線グラフ (累積=通算) + 年度別テーブルで表示。
  MLB 在籍年はドル契約が一次事実で、円換算は当時レートの推定値。

金額は全てメディア報道に基づく推定値。出典 URL はページに載せず JSON 側に記録する
(interleague と同じ user 方針)。
"""
from __future__ import annotations

import html as _html
import json as _json
import os as _os

from src.data_site_internal_link import breadcrumb_jsonld
from src.data_site_related_links import dataset_jsonld, related_data_links_html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SLUG = "salary"
_DATA_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "config", "giants_salary.json"
)

_PAGE_STYLE = (
    "<style>"
    ".ys-sl{font-family:sans-serif;max-width:980px;}"
    ".ys-sl table{width:100%;border-collapse:collapse;font-size:13px;}"
    ".ys-sl thead th{background:#fff6ec;color:#7a2d00;font-size:12px;white-space:nowrap;}"
    ".ys-sl th,.ys-sl td{padding:6px 8px;border-bottom:1px solid #f0e6db;text-align:center;"
    "vertical-align:top;white-space:nowrap;}"
    ".ys-sl tbody tr:nth-child(even) td{background:#fcfbf9;}"
    ".ys-sl tr.ys-giants td{background:#ffe9d6;font-weight:700;}"
    ".ys-sl tr.ys-mlb td{background:#f2f6fc;}"
    ".ys-sl__scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #f0e6db;"
    "border-radius:8px;margin:0 0 8px;}"
    ".ys-sl h2{font-size:17px;margin:26px 0 6px;color:#333;border-left:4px solid #e25400;"
    "padding-left:8px;scroll-margin-top:64px;}"
    ".ys-sl__chart{border:1px solid #f0e6db;border-radius:8px;background:#fffdfb;"
    "padding:6px;margin:0 0 8px;}"
    "@media(max-width:600px){.ys-sl table{font-size:12px;}.ys-sl th,.ys-sl td{padding:5px 6px;}}"
    "</style>"
)

_UP_STYLE = "color:#137333;font-weight:700;"
_DOWN_STYLE = "color:#c5221f;font-weight:700;"

# 棒グラフの球団色: 巨人=サイトアクセント / MLB=青系 / その他NPB=淡橙
_COLOR_GIANTS = "#e25400"
_COLOR_MLB = "#7da7d9"
_COLOR_NPB = "#f0a36b"


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_salary_data() -> dict:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _fmt_man(man: int) -> str:
    """万円 → 「9億」「4億7500万」「1500万」 (円は付けない)。"""
    man = int(man)
    oku, rest = divmod(man, 10000)
    if oku and rest:
        return f"{oku}億{rest}万"
    if oku:
        return f"{oku}億"
    return f"{rest}万"


def _fmt_man_yen(man: int) -> str:
    return _fmt_man(man) + "円"


def _fmt_usd(usd: int) -> str:
    """ドル → 「2200万ドル」。"""
    return f"{int(usd) // 10000}万ドル"


def _fmt_oku_compact(man: int) -> str:
    """万円 → 億単位の短い数字 (グラフラベル用)。1500万→0.15 / 9億→9 / 26億6200万→26.6"""
    v = man / 10000.0
    if v >= 10:
        s = f"{v:.1f}"
    else:
        s = f"{v:.2f}"
    return s.rstrip("0").rstrip(".")


def _bar_color(entry: dict) -> str:
    if entry.get("team") == "巨人":
        return _COLOR_GIANTS
    if entry.get("league") == "MLB":
        return _COLOR_MLB
    return _COLOR_NPB


def _nice_max(value_oku: float, step: float) -> float:
    import math
    return max(step, math.ceil(value_oku / step) * step)


def _bar_chart_svg(years: list[dict]) -> str:
    """年度別推定年俸の棒グラフ (インラインSVG、単位: 億円)。"""
    if not years:
        return ""
    n = len(years)
    left, right, top, bottom = 46, 10, 16, 46
    width, height = 960, 340
    plot_w, plot_h = width - left - right, height - top - bottom
    max_oku = max(y["salary_man"] for y in years) / 10000.0
    step = 5.0 if max_oku > 12 else (1.0 if max_oku > 2.5 else 0.5)
    ymax = _nice_max(max_oku, step)
    slot = plot_w / n
    bar_w = min(34.0, slot * 0.68)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'style="width:100%;height:auto;display:block;" '
        'aria-label="年度別推定年俸の棒グラフ" xmlns="http://www.w3.org/2000/svg">'
    ]
    # 横グリッド + y軸ラベル
    g = 0.0
    while g <= ymax + 1e-9:
        y_px = top + plot_h * (1 - g / ymax)
        parts.append(
            f'<line x1="{left}" y1="{y_px:.1f}" x2="{width - right}" y2="{y_px:.1f}" '
            'stroke="#f0e6db" stroke-width="1"/>'
            f'<text x="{left - 6}" y="{y_px + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#999">{g:g}億</text>'
        )
        g += step
    # 棒 + 数値 + 年度ラベル
    for i, e in enumerate(years):
        v_oku = e["salary_man"] / 10000.0
        h = plot_h * v_oku / ymax
        x = left + slot * i + (slot - bar_w) / 2
        y_px = top + plot_h - h
        parts.append(
            f'<rect x="{x:.1f}" y="{y_px:.1f}" width="{bar_w:.1f}" height="{max(h, 1.5):.1f}" '
            f'rx="2" fill="{_bar_color(e)}">'
            f"<title>{int(e['year'])}年 {_esc(e.get('team'))} "
            f"{_esc(_fmt_man_yen(e['salary_man']))}</title></rect>"
            f'<text x="{x + bar_w / 2:.1f}" y="{y_px - 4:.1f}" text-anchor="middle" '
            f'font-size="9" fill="#7a2d00">{_fmt_oku_compact(e["salary_man"])}</text>'
            f'<text x="{x + bar_w / 2:.1f}" y="{height - bottom + 14}" text-anchor="middle" '
            f'font-size="9" fill="#666">{int(e["year"])}</text>'
            f'<text x="{x + bar_w / 2:.1f}" y="{height - bottom + 26}" text-anchor="middle" '
            f'font-size="8" fill="#aaa">{_esc(e.get("team"))}</text>'
        )
    # 凡例
    parts.append(
        f'<rect x="{left}" y="{height - 12}" width="10" height="10" fill="{_COLOR_GIANTS}"/>'
        f'<text x="{left + 14}" y="{height - 3}" font-size="10" fill="#666">巨人</text>'
        f'<rect x="{left + 56}" y="{height - 12}" width="10" height="10" fill="{_COLOR_NPB}"/>'
        f'<text x="{left + 70}" y="{height - 3}" font-size="10" fill="#666">NPB他球団</text>'
        f'<rect x="{left + 148}" y="{height - 12}" width="10" height="10" fill="{_COLOR_MLB}"/>'
        f'<text x="{left + 162}" y="{height - 3}" font-size="10" fill="#666">MLB</text>'
        f'<text x="{width - right}" y="{height - 3}" text-anchor="end" font-size="10" '
        'fill="#999">数値ラベル単位: 億円</text>'
    )
    parts.append("</svg>")
    return '<div class="ys-sl__chart">' + "".join(parts) + "</div>"


def _line_chart_svg(years: list[dict]) -> str:
    """通算 (累積) 推定年俸の折れ線グラフ (インラインSVG、単位: 億円)。"""
    if not years:
        return ""
    n = len(years)
    left, right, top, bottom = 52, 14, 16, 34
    width, height = 960, 300
    plot_w, plot_h = width - left - right, height - top - bottom
    cum, total = [], 0
    for e in years:
        total += e["salary_man"]
        cum.append(total)
    max_oku = cum[-1] / 10000.0
    step = 50.0 if max_oku > 120 else (10.0 if max_oku > 25 else 2.0)
    ymax = _nice_max(max_oku, step)
    slot = plot_w / max(n - 1, 1)

    def pt(i: int) -> tuple[float, float]:
        return (left + slot * i, top + plot_h * (1 - (cum[i] / 10000.0) / ymax))

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'style="width:100%;height:auto;display:block;" '
        'aria-label="通算推定年俸の折れ線グラフ" xmlns="http://www.w3.org/2000/svg">'
    ]
    g = 0.0
    while g <= ymax + 1e-9:
        y_px = top + plot_h * (1 - g / ymax)
        parts.append(
            f'<line x1="{left}" y1="{y_px:.1f}" x2="{width - right}" y2="{y_px:.1f}" '
            'stroke="#f0e6db" stroke-width="1"/>'
            f'<text x="{left - 6}" y="{y_px + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#999">{g:g}億</text>'
        )
        g += step
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i) for i in range(n)))
    parts.append(
        f'<polyline points="{pts}" fill="none" stroke="{_COLOR_GIANTS}" stroke-width="2.5"/>'
    )
    label_every = max(1, (n + 9) // 10)
    for i, e in enumerate(years):
        x, y_px = pt(i)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y_px:.1f}" r="3" fill="{_bar_color(e)}" '
            'stroke="#fff" stroke-width="1">'
            f"<title>{int(e['year'])}年まで {_esc(_fmt_man_yen(cum[i]))}</title></circle>"
        )
        if i % label_every == 0 or i == n - 1:
            parts.append(
                f'<text x="{x:.1f}" y="{height - bottom + 14}" text-anchor="middle" '
                f'font-size="9" fill="#666">{int(e["year"])}</text>'
            )
        if i == n - 1:
            parts.append(
                f'<text x="{x - 4:.1f}" y="{y_px - 8:.1f}" text-anchor="end" font-size="11" '
                f'font-weight="700" fill="{_COLOR_GIANTS}">約{_fmt_man(cum[i])}円</text>'
            )
    parts.append("</svg>")
    return '<div class="ys-sl__chart">' + "".join(parts) + "</div>"


def _stat_pill(label: str, value: str, accent: str = "#e25400") -> str:
    return (
        '<span style="display:inline-flex;flex-direction:column;align-items:center;'
        'padding:6px 12px;margin:3px;border:1px solid #ffe0cc;border-radius:10px;background:#fff8f3;">'
        f'<b style="font-size:16px;color:{accent};line-height:1.1;">{_esc(value)}</b>'
        f'<em style="font-style:normal;font-size:10px;color:#888;margin-top:2px;">{_esc(label)}</em>'
        "</span>"
    )


def _total_man(p: dict) -> int:
    return sum(int(y["salary_man"]) for y in (p.get("years") or []))


def _latest(p: dict) -> dict:
    return max(p["years"], key=lambda y: int(y["year"]))


def _peak(p: dict) -> dict:
    return max(p["years"], key=lambda y: int(y["salary_man"]))


def _player_pills(p: dict) -> str:
    latest = _latest(p)
    peak = _peak(p)
    first_label = (
        f"最終年俸（{int(latest['year'])}年）" if p.get("active") is False
        else f"{int(latest['year'])}年 推定年俸"
    )
    pills = _stat_pill(first_label, _fmt_man_yen(latest["salary_man"]))
    pills += _stat_pill("通算推定年俸", f"約{_fmt_man(_total_man(p))}円", "#137333")
    kin = (p.get("draft") or {}).get("keiyakukin_man")
    if kin:
        pills += _stat_pill("契約金", _fmt_man_yen(kin), "#b8860b")
    peak_team = f"（{int(peak['year'])}年・{peak.get('team')}）"
    pills += _stat_pill("最高年俸", _fmt_man_yen(peak["salary_man"]) + peak_team, "#1565c0")
    return f'<div style="margin:0 0 14px;">{pills}</div>'


def _jump_nav() -> str:
    items = [
        ("#sl-bar", "年度別年俸グラフ"),
        ("#sl-line", "通算年俸の推移"),
        ("#sl-table", "年度別一覧表"),
        ("#sl-draft", "契約金・ドラフト"),
        ("#sl-notes", "注記"),
    ]
    chips = "".join(
        f'<a href="{anchor}" style="display:inline-block;padding:4px 10px;margin:2px;'
        'border:1px solid #ffd9bf;border-radius:14px;color:#e25400;text-decoration:none;'
        f'font-size:12px;font-weight:700;">{label}</a>'
        for anchor, label in items
    )
    return f'<div style="margin:0 0 16px;line-height:2;">{chips}</div>'


def _salary_cell(e: dict) -> str:
    if e.get("usd"):
        return (
            f"<b>{_esc(_fmt_usd(e['usd']))}</b>"
            f'<br><span style="font-size:10px;color:#999;">'
            f"約{_esc(_fmt_man(e['salary_man']))}円換算</span>"
        )
    return f"<b>{_esc(_fmt_man_yen(e['salary_man']))}</b>"


def _player_table(p: dict) -> str:
    rows = []
    prev = None
    for e in sorted(p["years"], key=lambda y: int(y["year"])):
        diff_cell = "<td>―</td>"
        if prev is not None:
            d = int(e["salary_man"]) - prev
            if d > 0:
                diff_cell = f'<td style="{_UP_STYLE}">▲{_esc(_fmt_man(d))}</td>'
            elif d < 0:
                diff_cell = f'<td style="{_DOWN_STYLE}">▼{_esc(_fmt_man(-d))}</td>'
            else:
                diff_cell = "<td>現状維持</td>"
        prev = int(e["salary_man"])
        cls = (
            ' class="ys-giants"' if e.get("team") == "巨人"
            else (' class="ys-mlb"' if e.get("league") == "MLB" else "")
        )
        note = e.get("note") or ""
        rows.append(
            f"<tr{cls}><td>{int(e['year'])}年</td>"
            f'<td style="text-align:left;">{_esc(e.get("team"))}</td>'
            f"<td>{_salary_cell(e)}</td>{diff_cell}"
            f'<td style="text-align:left;font-size:11px;color:#777;white-space:normal;">'
            f"{_esc(note)}</td></tr>"
        )
    total_row = (
        '<tr style="border-top:2px solid #e0d4c4;"><td><b>通算</b></td><td></td>'
        f"<td><b>約{_esc(_fmt_man(_total_man(p)))}円</b></td>"
        '<td colspan="2" style="text-align:left;font-size:11px;color:#999;">'
        "MLB在籍年は当時レートの円換算 (推定) を合算</td></tr>"
    )
    return (
        '<h2 id="sl-table">年度別 推定年俸一覧</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 8px;">'
        "オレンジの行は巨人在籍年、青系の行はMLB在籍年。増減は前年比。</p>"
        '<div class="ys-sl__scroll"><table><thead><tr>'
        "<th>年度</th><th>球団</th><th>推定年俸</th><th>増減</th><th>備考</th>"
        f"</tr></thead><tbody>{''.join(rows)}{total_row}</tbody></table></div>"
    )


def _draft_section(p: dict) -> str:
    d = p.get("draft") or {}
    if not d:
        return ""
    rows = [f"<li><b>ドラフト</b>: {_esc(d.get('desc'))}</li>"]
    if d.get("keiyakukin_note"):
        rows.append(f"<li><b>契約金</b>: {_esc(d.get('keiyakukin_note'))}</li>")
    elif d.get("keiyakukin_man"):
        rows.append(f"<li><b>契約金</b>: {_esc(_fmt_man_yen(d['keiyakukin_man']))}</li>")
    return (
        '<h2 id="sl-draft">契約金・ドラフト</h2>'
        f'<ul style="font-size:13px;line-height:1.9;margin:0 0 8px;">{"".join(rows)}</ul>'
    )


def _notes_section(p: dict) -> str:
    has_mlb = any(y.get("league") == "MLB" for y in p["years"])
    items = [
        "金額はいずれもメディア報道に基づく<b>推定値</b>です。球団・選手の公式発表額ではありません。",
        "通算推定年俸は年俸の単純合算で、出来高・ボーナス・スポンサー収入等は含みません。",
    ]
    if has_mlb:
        items.append(
            "MLB在籍年はドル建て契約が一次情報です。円換算は当時の為替レートによる推定値で、"
            "レートの取り方によって金額は前後します。"
        )
    lis = "".join(f"<li>{t}</li>" for t in items)
    return (
        '<h2 id="sl-notes">注記</h2>'
        f'<ul style="font-size:12px;color:#666;line-height:1.9;margin:0 0 8px;">{lis}</ul>'
    )


def _career_span(p: dict) -> str:
    ys = [int(y["year"]) for y in p["years"]]
    return f"{min(ys)}〜{max(ys)}年"


# ──────────────────────────── 選手別ページ ────────────────────────────

def render_salary_player_title(p: dict) -> str:
    if p.get("active") is False:
        return f"{p['name']}の年俸推移【現役時代】契約金・通算年俸 | 巨人データ"
    latest = _latest(p)
    return (
        f"{p['name']}の年俸推移【{int(latest['year'])}年最新】契約金・通算年俸 | 巨人データ"
    )


def render_salary_player_excerpt(p: dict) -> str:
    latest = _latest(p)
    total = _fmt_man(_total_man(p))
    kin = (p.get("draft") or {}).get("keiyakukin_man")
    kin_txt = f"契約金は{_fmt_man_yen(kin)}。" if kin else ""
    if p.get("active") is False:
        peak = _peak(p)
        return (
            f"{p['name']}の現役時代の推定年俸推移（掲載期間 {_career_span(p)}）。"
            f"最高年俸は{_fmt_man_yen(peak['salary_man'])}（{int(peak['year'])}年）、"
            f"通算推定年俸は約{total}円。{kin_txt}"
            "年度別推定年俸を棒グラフ・折れ線グラフと一覧表でまとめた巨人データです。"
        )
    return (
        f"{p['name']}の{int(latest['year'])}年推定年俸は{_fmt_man_yen(latest['salary_man'])}、"
        f"通算推定年俸は約{total}円。{kin_txt}"
        f"入団から現在まで（{_career_span(p)}）の年度別推定年俸を"
        "棒グラフ・折れ線グラフと一覧表でまとめた巨人データです。"
    )


def render_salary_player_html(p: dict) -> str:
    latest = _latest(p)
    years_sorted = sorted(p["years"], key=lambda y: int(y["year"]))
    player_slug = f"{SLUG}/{p['slug']}"
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › '
        f'<a href="{CLUSTER_URL}/{SLUG}" style="color:#666;">年俸ランキング</a> › '
        f"<span>{_esc(p['name'])}の年俸推移</span></nav>"
    )
    is_ob = p.get("active") is False
    prof = "・".join(t for t in (p.get("kana") or "", p.get("position") or "") if t)
    span_phrase = (
        f"現役時代の推定年俸を年度別にまとめました（掲載期間 {_esc(_career_span(p))}）。"
        if is_ob else
        f"推定年俸を入団から{int(latest['year'])}年まで年度別にまとめました。"
    )
    intro = (
        f'<h1 id="top" style="font-size:21px;margin:0 0 4px;">'
        f"{_esc(p['name'])}の年俸推移（{_esc(_career_span(p))}・契約金・通算年俸）</h1>"
        '<p style="font-size:13px;color:#666;margin:0 0 12px;line-height:1.7;">'
        f"{_esc(p['name'])}{f'（{_esc(prof)}）' if prof else ''}の{span_phrase}"
        "年度別の棒グラフ、通算年俸の積み上がりが分かる折れ線グラフ、"
        "前年比付きの一覧表、契約金・ドラフト情報を掲載しています。</p>"
    )
    body = (
        _player_pills(p)
        + _jump_nav()
        + f'<h2 id="sl-bar">年度別 推定年俸（棒グラフ）</h2>'
        + _bar_chart_svg(years_sorted)
        + f'<h2 id="sl-line">通算推定年俸の推移（折れ線グラフ）</h2>'
        + _line_chart_svg(years_sorted)
        + _player_table(p)
        + _draft_section(p)
        + _notes_section(p)
        + (
            f'<p style="margin:14px 0 0;"><a href="{CLUSTER_URL}/{SLUG}" '
            'style="font-size:13px;color:#1565c0;font-weight:700;">'
            "→ 巨人 年俸ランキング一覧へ戻る</a></p>"
        )
    )
    return (
        breadcrumb_jsonld(f"{p['name']}の年俸推移", player_slug)
        + dataset_jsonld(
            name=f"{p['name']} 年度別推定年俸（{_career_span(p)}）",
            description=render_salary_player_excerpt(p), slug=player_slug,
            temporal=_career_span(p).replace("〜", "/").replace("年", ""),
            keywords=[p["name"], "年俸", "推定年俸", "契約金", "通算年俸", "巨人",
                      "読売ジャイアンツ"],
        )
        + _PAGE_STYLE
        + '<div class="ys-sl">'
        + intro
        + nav
        + body
        + related_data_links_html(player_slug)
        + "</div>"
    )


# ──────────────────────────── 一覧ページ ────────────────────────────

def _index_year(data: dict) -> int:
    return max(
        (int(y["year"]) for p in (data.get("players") or []) for y in p["years"]),
        default=0,
    )


def render_salary_index_title(data: dict | None = None) -> str:
    data = data if data is not None else load_salary_data()
    return f"巨人 年俸ランキング【{_index_year(data)}年最新】選手別の推定年俸・通算年俸 | 巨人データ"


def render_salary_index_excerpt(data: dict | None = None) -> str:
    data = data if data is not None else load_salary_data()
    cur = _index_year(data)
    n = len(data.get("players") or [])
    return (
        f"読売ジャイアンツ（巨人）関連選手の{cur}年推定年俸をランキング形式で一覧化。"
        f"現在{n}選手を掲載。各選手のページでは入団からの年度別年俸推移を"
        "棒グラフ・折れ線グラフ付きで、契約金・通算推定年俸とあわせて確認できます。"
    )


def render_salary_index_html(data: dict | None = None) -> str:
    data = data if data is not None else load_salary_data()
    players = list(data.get("players") or [])
    cur = _index_year(data)
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › '
        "<span>年俸ランキング</span></nav>"
    )
    intro = (
        f'<h1 id="top" style="font-size:21px;margin:0 0 4px;">'
        f"巨人 年俸ランキング（{cur}年・選手別推定年俸）</h1>"
        '<p style="font-size:13px;color:#666;margin:0 0 12px;line-height:1.7;">'
        f"読売ジャイアンツ（巨人）関連選手の{cur}年推定年俸ランキングです。"
        "選手名のリンク先で、入団から現在までの年度別年俸推移（棒グラフ・折れ線グラフ）、"
        "契約金、通算推定年俸を確認できます。掲載選手は順次追加中です。</p>"
    )

    def latest_for(p):
        return max(p["years"], key=lambda y: int(y["year"]))

    actives = [p for p in players if p.get("active") is not False]
    obs = [p for p in players if p.get("active") is False]
    actives.sort(key=lambda p: -int(latest_for(p)["salary_man"]))
    rows = []
    for i, p in enumerate(actives, start=1):
        latest = latest_for(p)
        rows.append(
            f"<tr><td>{i}</td>"
            f'<td style="text-align:left;"><a href="{CLUSTER_URL}/{SLUG}/{_esc(p["slug"])}" '
            f'style="color:#1565c0;font-weight:700;">{_esc(p["name"])}</a>'
            f'<span style="font-size:10px;color:#999;"> {_esc(p.get("position") or "")}</span></td>'
            f"<td><b>{_esc(_fmt_man_yen(latest['salary_man']))}</b>"
            + (f'<br><span style="font-size:10px;color:#999;">{int(latest["year"])}年</span>'
               if int(latest["year"]) != cur else "")
            + "</td>"
            f"<td>約{_esc(_fmt_man(_total_man(p)))}円</td>"
            f'<td style="font-size:12px;">{_esc(_career_span(p))}</td>'
            f'<td><a href="{CLUSTER_URL}/{SLUG}/{_esc(p["slug"])}" '
            'style="font-size:12px;color:#e25400;font-weight:700;">推移を見る →</a></td></tr>'
        )
    table = (
        '<h2 id="sl-ranking">推定年俸ランキング（現役）</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 8px;">'
        "金額はメディア報道に基づく推定値。通算はMLB在籍年の円換算（当時レート推定）を含む単純合算。</p>"
        '<div class="ys-sl__scroll"><table><thead><tr>'
        "<th>順位</th><th>選手</th><th>推定年俸</th><th>通算推定年俸</th><th>掲載期間</th><th></th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )
    if obs:
        obs.sort(key=lambda p: -_total_man(p))
        ob_rows = []
        for p in obs:
            peak = _peak(p)
            ob_rows.append(
                f'<tr><td style="text-align:left;">'
                f'<a href="{CLUSTER_URL}/{SLUG}/{_esc(p["slug"])}" '
                f'style="color:#1565c0;font-weight:700;">{_esc(p["name"])}</a></td>'
                f"<td>{_esc(_fmt_man_yen(peak['salary_man']))}"
                f'<br><span style="font-size:10px;color:#999;">{int(peak["year"])}年</span></td>'
                f"<td>約{_esc(_fmt_man(_total_man(p)))}円</td>"
                f'<td style="font-size:12px;">{_esc(_career_span(p))}</td>'
                f'<td><a href="{CLUSTER_URL}/{SLUG}/{_esc(p["slug"])}" '
                'style="font-size:12px;color:#e25400;font-weight:700;">推移を見る →</a></td></tr>'
            )
        table += (
            '<h2 id="sl-ob">OB・歴代選手の年俸推移</h2>'
            '<p style="font-size:12px;color:#666;margin:0 0 8px;">'
            "巨人OB・歴代選手の現役時代の推定年俸。通算推定年俸の多い順。"
            "年俸が公表されていない時代の選手は、確認できた年のみ掲載しています。</p>"
            '<div class="ys-sl__scroll"><table><thead><tr>'
            "<th>選手</th><th>最高年俸</th><th>通算推定年俸</th><th>現役期間</th><th></th>"
            f"</tr></thead><tbody>{''.join(ob_rows)}</tbody></table></div>"
        )
    return (
        breadcrumb_jsonld("巨人 年俸ランキング", SLUG)
        + dataset_jsonld(
            name=f"巨人 選手別推定年俸ランキング（{cur}年）",
            description=render_salary_index_excerpt(data), slug=SLUG,
            keywords=["巨人", "読売ジャイアンツ", "年俸", "年俸ランキング", "推定年俸",
                      "契約金", "通算年俸"],
        )
        + _PAGE_STYLE
        + '<div class="ys-sl">'
        + intro
        + nav
        + table
        + related_data_links_html(SLUG)
        + "</div>"
    )


if __name__ == "__main__":
    import sys as _sys

    data = load_salary_data()
    if len(_sys.argv) > 1 and _sys.argv[1] != "index":
        target = next(p for p in data["players"] if p["slug"] == _sys.argv[1])
        _sys.stdout.write(render_salary_player_html(target))
    else:
        _sys.stdout.write(render_salary_index_html(data))
