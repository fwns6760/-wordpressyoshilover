"""data/interleague page template (巨人 セ・パ交流戦 成績 2005-).

データは config/giants_interleague.json (検証済み baked 履歴) を読み、
当年分は src/interleague_scraper.py (NPB公式 順位表) で daily refresh が注入する。
年度別一覧 / 当年12球団順位表 / 球団別通算 / 年度×球団マトリクス / 優勝・受賞歴。
出典・外部リンクは載せない (user 方針、データ出典は JSON 側に記録)。
"""
from __future__ import annotations

import html as _html
import json as _json
import os as _os

from src.data_site_internal_link import breadcrumb_jsonld
from src.data_site_related_links import dataset_jsonld, related_data_links_html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SLUG = "interleague"
_DATA_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "config", "giants_interleague.json"
)

_TEAM_ORDER = ["f", "e", "l", "m", "b", "h"]
_TEAM_LABELS = {
    "f": "日本ハム", "e": "楽天", "l": "西武",
    "m": "ロッテ", "b": "オリックス", "h": "ソフトバンク",
}

_PAGE_STYLE = (
    "<style>"
    ".ys-il{font-family:sans-serif;max-width:980px;}"
    ".ys-il table{width:100%;border-collapse:collapse;font-size:13px;}"
    ".ys-il thead th{position:sticky;top:0;z-index:2;background:#fff6ec;color:#7a2d00;"
    "font-size:12px;white-space:nowrap;}"
    ".ys-il th,.ys-il td{padding:6px 8px;border-bottom:1px solid #f0e6db;text-align:center;"
    "vertical-align:top;white-space:nowrap;}"
    ".ys-il tbody tr:nth-child(even) td{background:#fcfbf9;}"
    ".ys-il tr.ys-champ td{background:#fff4d6;font-weight:700;}"
    ".ys-il tr.ys-live td{background:#eef6ff;}"
    ".ys-il tr.ys-giants td{background:#ffe9d6;font-weight:700;}"
    ".ys-il__scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #f0e6db;"
    "border-radius:8px;margin:0 0 8px;}"
    ".ys-il h2{font-size:17px;margin:26px 0 6px;color:#333;border-left:4px solid #e25400;"
    "padding-left:8px;scroll-margin-top:64px;}"
    ".ys-il__bar{display:inline-block;height:9px;border-radius:5px;background:#f0a36b;"
    "vertical-align:middle;}"
    "@media(max-width:600px){.ys-il table{font-size:12px;}.ys-il th,.ys-il td{padding:5px 6px;}}"
    "</style>"
)

_WIN_STYLE = "color:#137333;font-weight:700;"
_LOSE_STYLE = "color:#c5221f;font-weight:700;"


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_interleague_data() -> dict:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _final_years(data: dict) -> list[dict]:
    return [y for y in (data.get("years") or []) if y.get("final")]


def _all_giants_entries(data: dict) -> list[dict]:
    """通算計算用: baked final + 当年 live (あれば)。"""
    out = list(_final_years(data))
    live = (data.get("live") or {}).get("giants")
    if live and not any(int(y.get("year") or 0) == int(live["year"]) for y in out):
        out.append(live)
    return out


def _totals(entries: list[dict]) -> dict:
    w = sum(int(e.get("w") or 0) for e in entries)
    l = sum(int(e.get("l") or 0) for e in entries)
    d = sum(int(e.get("d") or 0) for e in entries)
    g = sum(int(e.get("g") or 0) for e in entries)
    pct = f"{w / (w + l):.3f}".lstrip("0") if (w + l) else "―"
    return {"g": g, "w": w, "l": l, "d": d, "pct": pct}


def _vs_totals(entries: list[dict]) -> dict[str, list[int]]:
    out = {k: [0, 0, 0] for k in _TEAM_ORDER}
    for e in entries:
        for k, wdl in (e.get("vs") or {}).items():
            if wdl and k in out:
                out[k][0] += int(wdl[0]); out[k][1] += int(wdl[1]); out[k][2] += int(wdl[2])
    return out


def _span_label(data: dict) -> str:
    entries = _all_giants_entries(data)
    if not entries:
        return ""
    ys = [int(e["year"]) for e in entries]
    return f"2005〜{max(ys)}年"


def render_interleague_title(data: dict | None = None) -> str:
    data = data if data is not None else load_interleague_data()
    return f"巨人 交流戦 成績一覧【{_span_label(data)}・年度別勝敗と歴代優勝】 | 巨人データ"


def render_interleague_excerpt(data: dict | None = None) -> str:
    data = data if data is not None else load_interleague_data()
    t = _totals(_all_giants_entries(data))
    return (
        f"読売ジャイアンツ（巨人）のセ・パ交流戦成績を{_span_label(data)}まで年度別に一覧化。"
        f"通算{t['g']}試合{t['w']}勝{t['l']}敗{t['d']}分（勝率{t['pct']}）。"
        "年度別の順位・勝敗・打率・防御率・優勝チームに加え、当年の12球団順位表、"
        "パ・リーグ球団別の通算対戦成績、交流戦優勝・MVP受賞歴をまとめた巨人データです。"
    )


def _stat_pill(label: str, value: str, accent: str = "#e25400") -> str:
    return (
        '<span style="display:inline-flex;flex-direction:column;align-items:center;'
        'padding:6px 12px;margin:3px;border:1px solid #ffe0cc;border-radius:10px;background:#fff8f3;">'
        f'<b style="font-size:16px;color:{accent};line-height:1.1;">{_esc(value)}</b>'
        f'<em style="font-style:normal;font-size:10px;color:#888;margin-top:2px;">{_esc(label)}</em>'
        "</span>"
    )


def _wdl_text(wdl) -> str:
    if not wdl:
        return "―"
    w, l, d = int(wdl[0]), int(wdl[1]), int(wdl[2])
    return f"{w}勝{l}敗" + (f"{d}分" if d else "")


def _vs_cell(wdl) -> str:
    if not wdl:
        return "<td>―</td>"
    w, l, d = int(wdl[0]), int(wdl[1]), int(wdl[2])
    style = _WIN_STYLE if w > l else (_LOSE_STYLE if l > w else "")
    txt = f"{w}-{l}" + (f"-{d}" if d else "")
    return f'<td style="{style}">{_esc(txt)}</td>'


def _summary_pills(data: dict) -> str:
    entries = _all_giants_entries(data)
    t = _totals(entries)
    champs = [str(y["year"]) for y in _final_years(data) if y.get("champion") == "巨人"]
    best = max(_final_years(data), key=lambda y: float(y.get("pct") or 0), default=None)
    pills = _stat_pill("交流戦通算", f"{t['w']}勝{t['l']}敗{t['d']}分", "#137333")
    pills += _stat_pill("通算勝率", t["pct"])
    pills += _stat_pill("交流戦優勝", f"{len(champs)}回（{'・'.join(champs)}年）", "#b8860b")
    if best:
        pills += _stat_pill("最高勝率", f"{best['pct']}（{best['year']}年）", "#1565c0")
    live = (data.get("live") or {}).get("giants")
    if live:
        pills += _stat_pill(
            f"{live['year']}年（開催中）",
            f"{live['w']}勝{live['l']}敗{live['d']}分・暫定{live['rank']}位", "#c5221f",
        )
    return f'<div style="margin:0 0 14px;">{pills}</div>'


def _jump_nav(data: dict) -> str:
    items = []
    if data.get("live"):
        items.append(("#il-now", "今年の交流戦"))
    items += [
        ("#il-yearly", "年度別成績一覧"),
        ("#il-vs", "球団別通算成績"),
        ("#il-matrix", "年度×球団 勝敗表"),
        ("#il-awards", "優勝・受賞歴"),
    ]
    chips = "".join(
        f'<a href="{anchor}" style="display:inline-block;padding:4px 10px;margin:2px;'
        'border:1px solid #ffd9bf;border-radius:14px;color:#e25400;text-decoration:none;'
        f'font-size:12px;font-weight:700;">{label}</a>'
        for anchor, label in items
    )
    return f'<div style="margin:0 0 16px;line-height:2;">{chips}</div>'


def _live_section(data: dict) -> str:
    live = data.get("live") or {}
    standings = live.get("standings") or []
    giants = live.get("giants")
    if not (standings and giants):
        return ""
    year = live.get("year")
    rows = []
    for r in standings:
        cls = ' class="ys-giants"' if r.get("team") == "巨人" else ""
        league_tag = (
            '<span style="font-size:10px;padding:1px 5px;border-radius:8px;'
            + ("background:#e8f0fe;color:#1a56b0;" if r.get("league") == "セ"
               else "background:#fde8ec;color:#b00040;")
            + f'">{_esc(r.get("league"))}</span>'
        )
        rows.append(
            f"<tr{cls}><td>{int(r.get('rank') or 0)}</td>"
            f'<td style="text-align:left;">{_esc(r.get("team"))} {league_tag}</td>'
            f"<td>{int(r.get('g') or 0)}</td><td>{int(r.get('w') or 0)}</td>"
            f"<td>{int(r.get('l') or 0)}</td><td>{int(r.get('t') or 0)}</td>"
            f"<td>{_esc(r.get('pct'))}</td></tr>"
        )
    vs_head = "".join(f"<th>{_esc(_TEAM_LABELS[k])}</th>" for k in _TEAM_ORDER)
    vs_cells = "".join(_vs_cell((giants.get("vs") or {}).get(k)) for k in _TEAM_ORDER)
    return (
        f'<h2 id="il-now">{_esc(year)}年 交流戦（開催中）12球団順位表</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 8px;">'
        f"巨人は{giants['w']}勝{giants['l']}敗{giants['d']}分（勝率{_esc(giants['pct'])}）で"
        f"暫定{giants['rank']}位。ホーム{_wdl_text(giants.get('home'))}・"
        f"ビジター{_wdl_text(giants.get('visitor'))}。</p>"
        '<div class="ys-il__scroll"><table><thead><tr>'
        "<th>順位</th><th>チーム</th><th>試合</th><th>勝</th><th>敗</th><th>分</th><th>勝率</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        '<h3 style="font-size:14px;margin:14px 0 6px;">巨人のパ・リーグ球団別成績（'
        f"{_esc(year)}年）</h3>"
        f'<div class="ys-il__scroll"><table><thead><tr>{vs_head}</tr></thead>'
        f"<tbody><tr>{vs_cells}</tr></tbody></table></div>"
    )


def _yearly_row(entry: dict, *, live: bool = False) -> str:
    y = int(entry.get("year") or 0)
    wareki = entry.get("wareki") or ""
    if entry.get("cancelled"):
        return (
            f'<tr><td>{y}年<br><span style="font-size:10px;color:#999;">{_esc(wareki)}</span></td>'
            f'<td colspan="14" style="color:#999;text-align:left;">{_esc(entry.get("note") or "中止")}</td></tr>'
        )
    cls = []
    if entry.get("champion") == "巨人":
        cls.append("ys-champ")
    if live:
        cls.append("ys-live")
    cls_attr = f' class="{" ".join(cls)}"' if cls else ""
    champ = _esc(entry.get("champion") or "―")
    if entry.get("champion") == "巨人":
        champ = "🏆 巨人"
    elif entry.get("champion_rec"):
        champ += (
            f'<br><span style="font-size:10px;color:#999;">{_esc(entry.get("champion_rec"))}</span>'
        )
    rank = f"{entry.get('rank')}位" + ("（暫定）" if live else "")
    cells = [
        f'<td>{y}年<br><span style="font-size:10px;color:#999;">{_esc(wareki)}</span></td>',
        f"<td>{_esc(rank)}</td>",
        f"<td>{int(entry.get('g') or 0)}</td>",
        f'<td style="{_WIN_STYLE}">{int(entry.get("w") or 0)}</td>',
        f'<td style="{_LOSE_STYLE}">{int(entry.get("l") or 0)}</td>',
        f"<td>{int(entry.get('d') or 0)}</td>",
        f"<td><b>{_esc(entry.get('pct'))}</b></td>",
        f"<td>{_esc(entry.get('avg') or '―')}</td>",
        f"<td>{_esc(entry.get('hr') if entry.get('hr') is not None else '―')}</td>",
        f"<td>{_esc(entry.get('sb') if entry.get('sb') is not None else '―')}</td>",
        f"<td>{_esc(entry.get('era') or '―')}</td>",
        f'<td style="text-align:left;">{champ}</td>',
        f"<td>{_esc(entry.get('gb') or '―')}</td>",
        f"<td>{_wdl_text(entry.get('home'))}</td>",
        f"<td>{_wdl_text(entry.get('visitor'))}</td>",
    ]
    return f"<tr{cls_attr}>{''.join(cells)}</tr>"


def _yearly_section(data: dict) -> str:
    years = data.get("years") or []
    live = (data.get("live") or {}).get("giants")
    rows = []
    if live and not any(int(y.get("year") or 0) == int(live["year"]) for y in years):
        rows.append(_yearly_row({**live, "wareki": ""}, live=True))
    rows += [_yearly_row(y) for y in years]
    totals = _totals(_all_giants_entries(data))
    total_row = (
        '<tr style="border-top:2px solid #e0d4c4;"><td><b>通算</b></td><td>―</td>'
        f"<td><b>{totals['g']}</b></td>"
        f'<td style="{_WIN_STYLE}">{totals["w"]}</td>'
        f'<td style="{_LOSE_STYLE}">{totals["l"]}</td>'
        f"<td>{totals['d']}</td><td><b>{_esc(totals['pct'])}</b></td>"
        '<td colspan="8"></td></tr>'
    )
    return (
        '<h2 id="il-yearly">年度別 交流戦成績一覧</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 8px;">'
        "金色の行は巨人が交流戦優勝した年。打率・本塁打・盗塁・防御率は交流戦期間のチーム成績。"
        "ゲーム差は優勝チームとの差（勝差÷2）。2020年は中止。</p>"
        '<div class="ys-il__scroll"><table><thead><tr>'
        "<th>年度</th><th>順位</th><th>試合</th><th>勝</th><th>敗</th><th>分</th><th>勝率</th>"
        "<th>打率</th><th>本塁打</th><th>盗塁</th><th>防御率</th><th>優勝チーム</th>"
        "<th>首位差</th><th>ホーム</th><th>ビジター</th>"
        f"</tr></thead><tbody>{''.join(rows)}{total_row}</tbody></table></div>"
    )


def _vs_section(data: dict) -> str:
    entries = _all_giants_entries(data)
    vs = _vs_totals(entries)
    span = _span_label(data)
    ranked = []
    for k in _TEAM_ORDER:
        w, l, d = vs[k]
        pct = w / (w + l) if (w + l) else 0.0
        ranked.append((k, w, l, d, pct))
    ranked.sort(key=lambda r: -r[4])
    rows = []
    for k, w, l, d, pct in ranked:
        pct_txt = f"{pct:.3f}".lstrip("0") if (w + l) else "―"
        bar = f'<span class="ys-il__bar" style="width:{int(pct * 120)}px;"></span>'
        mark = "◎ 得意" if pct >= 0.550 else ("△ 苦手" if pct <= 0.450 else "")
        style = _WIN_STYLE if w > l else (_LOSE_STYLE if l > w else "")
        rows.append(
            f'<tr><td style="text-align:left;">{_esc(_TEAM_LABELS[k])}</td>'
            f"<td>{w + l + d}</td>"
            f'<td style="{style}">{w}勝{l}敗{d}分</td>'
            f"<td><b>{_esc(pct_txt)}</b></td>"
            f'<td style="text-align:left;">{bar}</td>'
            f'<td style="font-size:12px;">{mark}</td></tr>'
        )
    return (
        '<h2 id="il-vs">パ・リーグ球団別 通算対戦成績</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 8px;">'
        f"{span}の通算。勝率順。◎=勝率.550以上、△=.450以下。</p>"
        '<div class="ys-il__scroll"><table><thead><tr>'
        "<th>球団</th><th>試合</th><th>通算勝敗</th><th>勝率</th><th></th><th></th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _matrix_section(data: dict) -> str:
    years = [y for y in (data.get("years") or []) if not y.get("cancelled")]
    live = (data.get("live") or {}).get("giants")
    head = "".join(f"<th>{_esc(_TEAM_LABELS[k])}</th>" for k in _TEAM_ORDER)
    rows = []
    if live and not any(int(y.get("year") or 0) == int(live["year"]) for y in years):
        cells = "".join(_vs_cell((live.get("vs") or {}).get(k)) for k in _TEAM_ORDER)
        rows.append(f'<tr class="ys-live"><td>{int(live["year"])}年</td>{cells}</tr>')
    for y in years:
        cells = "".join(_vs_cell((y.get("vs") or {}).get(k)) for k in _TEAM_ORDER)
        cls = ' class="ys-champ"' if y.get("champion") == "巨人" else ""
        rows.append(f"<tr{cls}><td>{int(y['year'])}年</td>{cells}</tr>")
    return (
        '<h2 id="il-matrix">年度×球団 勝敗マトリクス</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 8px;">'
        "各年度のパ・リーグ6球団との勝敗（勝-敗-分）。緑=勝ち越し、赤=負け越し。</p>"
        '<div class="ys-il__scroll"><table><thead><tr><th>年度</th>'
        f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _awards_section(data: dict) -> str:
    awards = data.get("giants_awards") or {}
    champs = [y for y in _final_years(data) if y.get("champion") == "巨人"]
    champ_cards = "".join(
        '<span style="display:inline-block;padding:8px 14px;margin:3px;border:1px solid #f0d890;'
        'border-radius:10px;background:#fffbea;font-size:13px;">'
        f"🏆 <b>{int(y['year'])}年 交流戦優勝</b>"
        f'<span style="color:#888;">（{int(y["w"])}勝{int(y["l"])}敗{int(y["d"])}分・勝率{_esc(y["pct"])}）</span></span>'
        for y in sorted(champs, key=lambda e: int(e["year"]))
    )
    mvp = "・".join(
        f"{int(a['year'])}年 {a['player']}" for a in (awards.get("mvp") or [])
    )
    nissay = "・".join(
        f"{int(a['year'])}年 {a['player']}" for a in (awards.get("nissay_award") or [])
    )
    lines = []
    if mvp:
        lines.append(f"<li><b>交流戦MVP（最優秀選手）</b>: {_esc(mvp)}</li>")
    if nissay:
        lines.append(f"<li><b>優秀選手賞（日本生命賞）</b>: {_esc(nissay)}</li>")
    return (
        '<h2 id="il-awards">巨人の交流戦優勝・受賞歴</h2>'
        f'<div style="margin:0 0 10px;">{champ_cards}</div>'
        f'<ul style="font-size:13px;line-height:1.9;margin:0 0 8px;">{"".join(lines)}</ul>'
    )


def render_interleague_html(data: dict | None = None) -> str:
    data = data if data is not None else load_interleague_data()
    years = data.get("years") or []
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>交流戦成績</span></nav>'
    )
    span = _span_label(data)
    live_phrase = "開催中シーズンの12球団順位表、" if data.get("live") else ""
    intro = (
        '<h1 id="top" style="font-size:21px;margin:0 0 4px;">巨人 交流戦 成績一覧（年度別・歴代）</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 12px;line-height:1.7;">'
        f"読売ジャイアンツ（巨人）のセ・パ交流戦成績を{span}まで年度別にまとめた一覧です。"
        f"各年の順位・勝敗・勝率・打率・防御率・優勝チームに加え、{live_phrase}"
        "パ・リーグ球団別の通算対戦成績、年度×球団の勝敗マトリクス、交流戦優勝・MVP受賞歴も掲載。</p>"
    )
    if not years:
        body = '<p style="color:#999;">交流戦データを準備中です。</p>'
    else:
        body = (
            _summary_pills(data)
            + _jump_nav(data)
            + _live_section(data)
            + _yearly_section(data)
            + _vs_section(data)
            + _matrix_section(data)
            + _awards_section(data)
        )
    return (
        breadcrumb_jsonld("巨人 交流戦成績", SLUG)
        + dataset_jsonld(
            name=f"巨人 セ・パ交流戦成績（年度別 {span}）",
            description=render_interleague_excerpt(data), slug=SLUG,
            temporal="2005/2026",
            keywords=["巨人", "読売ジャイアンツ", "交流戦", "セ・パ交流戦", "成績", "順位"],
        )
        + _PAGE_STYLE
        + '<div class="ys-il">'
        + intro
        + nav
        + body
        + related_data_links_html(SLUG)
        + "</div>"
    )


if __name__ == "__main__":
    import sys as _sys

    _sys.stdout.write(render_interleague_html())
