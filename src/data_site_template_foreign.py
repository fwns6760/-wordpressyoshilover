"""data/foreign-players ページ template（巨人 歴代外国人選手 hub）。

ベンチ: my-favorite-giants.net/giants_data/player/foreign-year.htm（年度×ポジションの matrix）。
本 hub はユーザビリティ改善版:
  1. 選手名インクリメンタル検索（client-side、JS 無効でも全表表示）
  2. 現役外国人選手（支配下/育成 badge、個別データページへ link）
  3. 年代別一覧（在籍開始年 decade、通算成績つき、新しい年代が先）
  4. 年度別在籍早見表（1934-現在、投手/野手 2 列、空白年は圧縮）
データ正本は config/giants_foreign_players.json（事実のみ・推測で埋めない、
generator: scripts/build_foreign_players_config.py）。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os
import re as _re

from src.data_site_internal_link import roster_moves_nav

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = f"{SITE_BASE}/data/"
PAGE_SLUG = "foreign-players"

_DATA_PATH = _os.path.join(_os.path.dirname(__file__), "..", "config", "giants_foreign_players.json")


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_foreign_players_data() -> dict:
    """config/giants_foreign_players.json を読む。失敗時は空 dict。"""
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _start_year(e: dict) -> int:
    m = _re.match(r"(\d{4})", str(e.get("years") or ""))
    return int(m.group(1)) if m else 0


def _end_year(e: dict) -> int:
    m = _re.fullmatch(r"(\d{4})-(\d{4})", str(e.get("years") or ""))
    return int(m.group(2)) if m else _start_year(e)


def _npb_summary(e: dict) -> str:
    """通算成績の 1 行 summary。 batter: 試合/打率/本塁打/打点、 pitcher: 登板/勝/防御率/奪三振。"""
    npb = e.get("npb") or {}
    if not npb:
        return "—"
    if e.get("type") == "pitcher":
        parts = []
        if npb.get("games") is not None:
            parts.append(f'{npb["games"]}登板')
        if npb.get("w") is not None:
            parts.append(f'{npb["w"]}勝')
        if npb.get("era"):
            parts.append(f'防{npb["era"]}')
        if npb.get("k") is not None:
            parts.append(f'{npb["k"]}奪三振')
        return "・".join(parts) or "—"
    parts = []
    if npb.get("games") is not None:
        parts.append(f'{npb["games"]}試合')
    if npb.get("avg"):
        parts.append(f'打率{npb["avg"]}')
    if npb.get("hr") is not None:
        parts.append(f'{npb["hr"]}本')
    if npb.get("rbi") is not None:
        parts.append(f'{npb["rbi"]}打点')
    return "・".join(parts) or "—"


def _player_link(name: str, slug: str) -> str:
    if slug:
        return (f'<a href="/data/{_esc(slug)}/" '
                f'style="color:#1976d2;text-decoration:none;font-weight:600;">{_esc(name)}</a>')
    return f'<span style="font-weight:600;color:#5d4037;">{_esc(name)}</span>'


def _type_badge(t: str) -> str:
    label = "投手" if t == "pitcher" else "野手"
    color = "#1565c0" if t == "pitcher" else "#e65100"
    return (f'<span style="display:inline-block;padding:1px 7px;border-radius:9px;'
            f'border:1px solid {color};color:{color};font-size:11px;">{label}</span>')


# ---- sections ----

def _build_search_html() -> str:
    """選手名インクリメンタル検索（progressive enhancement、JS 無効でも劣化しない）。"""
    return (
        '<section class="ys-foreign-search" style="margin:0 0 16px;">'
        '<input type="search" id="ys-foreign-search" autocomplete="off" '
        'placeholder="🔍 選手名で検索（例: クロマティ / マイコラス / 与那嶺）" '
        'style="width:100%;box-sizing:border-box;padding:12px 14px;font-size:15px;'
        'border:2px solid #ffd9bf;border-radius:10px;outline:none;color:#1a1a1a;" '
        'aria-label="選手名で検索">'
        '<p id="ys-foreign-empty" hidden '
        'style="font-size:13px;color:#888;margin:8px 2px 0;">該当する選手が見つかりません。</p>'
        '</section>'
        '<script>(function(){'
        'var box=document.getElementById("ys-foreign-search");if(!box)return;'
        'var empty=document.getElementById("ys-foreign-empty");'
        'var rows=[].slice.call(document.querySelectorAll("table.ys-foreign-list tbody tr"));'
        'var items=rows.map(function(r){return{el:r,nm:(r.textContent||"").replace(/\\s+/g,"")};});'
        'function norm(s){return(s||"").replace(/\\s+/g,"");}'
        'box.addEventListener("input",function(){'
        'var q=norm(this.value);var vis=0;'
        'items.forEach(function(it){'
        'var hit=!q||it.nm.indexOf(q)>=0;'
        'it.el.style.display=hit?"":"none";if(hit)vis++;});'
        'if(empty)empty.hidden=!(q&&vis===0);});'
        '})();</script>'
    )


def _build_intro_html(data: dict) -> str:
    ob = data.get("ob") or []
    active = data.get("active") or []
    seasons = [y for y in (_start_year(e) for e in ob) if y]
    y_min = min(seasons) if seasons else 1934
    season = data.get("season") or ""
    pitchers = sum(1 for e in ob if e.get("type") == "pitcher")
    batters = len(ob) - pitchers
    return (
        '<section class="ys-foreign-intro" '
        'style="background:#fff8e1;border-left:3px solid #f57f17;'
        'padding:14px 18px;margin:0 0 16px;border-radius:4px;">'
        '<p style="font-size:13px;line-height:1.7;margin:0;color:#444;">'
        f'読売ジャイアンツに在籍した歴代外国人選手のデータベースです。 {y_min}年の球団創設期から'
        f'{season}年現在まで、 OB {len(ob)}名（投手{pitchers}・野手{batters}）と現役{len(active)}名を、 '
        '在籍年・通算成績つきで一覧化。 選手名から各個人の年度別成績ページへ移動できます。'
        '</p>'
        '<p style="font-size:13px;margin:10px 0 0;">'
        '<a href="#ys-foreign-active" style="color:#e25400;font-weight:600;text-decoration:none;">⚾ 現役</a>'
        '　/　'
        '<a href="#ys-foreign-decades" style="color:#e25400;font-weight:600;text-decoration:none;">📚 年代別一覧</a>'
        '　/　'
        '<a href="#ys-foreign-years" style="color:#e25400;font-weight:600;text-decoration:none;">📅 年度別在籍早見表</a>'
        '</p></section>'
    )


def _build_active_html(data: dict) -> str:
    active = data.get("active") or []
    if not active:
        return ""
    season = data.get("season") or ""
    rows = []
    for p in active:
        badge_color = "#2e7d32" if p.get("status") == "支配下" else "#9e9e9e"
        rows.append(
            '<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:8px 10px;">{_player_link(p.get("name"), p.get("slug") or "")}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{_esc(p.get("group"))}</td>'
            f'<td style="padding:8px 10px;text-align:center;">'
            f'<span style="display:inline-block;padding:1px 8px;border-radius:9px;background:{badge_color};'
            f'color:#fff;font-size:11px;">{_esc(p.get("status"))}</span></td>'
            '</tr>'
        )
    return (
        '<section class="ys-foreign-active-table" id="ys-foreign-active" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">⚾ 現役外国人選手 ({len(active)} 名 / {_esc(season)}年)</h2>'
        '<div style="overflow-x:auto;">'
        '<table class="ys-foreign-list" style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:left;">'
        '<th style="padding:10px;">名前</th>'
        '<th style="padding:10px;text-align:center;">ポジション</th>'
        '<th style="padding:10px;text-align:center;">登録</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table></div></section>'
    )


def _decade_label(y: int) -> str:
    return f"{y // 10 * 10}年代"


def _build_decades_html(data: dict) -> str:
    ob = data.get("ob") or []
    if not ob:
        return '<p style="font-size:13px;color:#888;">データを準備中です。</p>'
    by_decade: dict[int, list[dict]] = {}
    for e in ob:
        y = _start_year(e)
        if y:
            by_decade.setdefault(y // 10 * 10, []).append(e)
    blocks = []
    for dec in sorted(by_decade, reverse=True):
        members = sorted(by_decade[dec], key=lambda e: (_start_year(e), str(e.get("display_name"))))
        rows = []
        for e in members:
            note = e.get("note") or ""
            name_cell = _player_link(e.get("display_name"), e.get("slug") or "")
            if note:
                name_cell += (f'<div style="font-size:11px;color:#888;margin-top:2px;">{_esc(note)}</div>')
            roman = e.get("roman") or ""
            rows.append(
                '<tr style="border-bottom:1px solid #eee;">'
                f'<td style="padding:8px 10px;white-space:nowrap;color:#555;">{_esc(e.get("years"))}</td>'
                f'<td style="padding:8px 10px;">{name_cell}</td>'
                f'<td style="padding:8px 10px;font-size:11px;color:#999;">{_esc(roman)}</td>'
                f'<td style="padding:8px 10px;text-align:center;">{_type_badge(e.get("type"))}</td>'
                f'<td style="padding:8px 10px;font-size:12px;color:#555;">{_esc(_npb_summary(e))}</td>'
                '</tr>'
            )
        blocks.append(
            f'<h3 id="ys-foreign-{dec}s" style="font-size:15px;margin:18px 0 6px;color:#5d4037;">'
            f'{dec}年代 ({len(members)} 名)</h3>'
            '<div style="overflow-x:auto;">'
            '<table class="ys-foreign-list" style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="background:#fafafa;text-align:left;">'
            '<th style="padding:8px 10px;">在籍</th>'
            '<th style="padding:8px 10px;">名前</th>'
            '<th style="padding:8px 10px;">現地名</th>'
            '<th style="padding:8px 10px;text-align:center;">区分</th>'
            '<th style="padding:8px 10px;">NPB通算</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
        )
    chips = "".join(
        f'<a href="#ys-foreign-{dec}s" style="display:inline-block;padding:4px 10px;margin:2px;'
        'border-radius:12px;border:1px solid #e65100;color:#e65100;text-decoration:none;'
        f'font-size:12px;font-weight:600;">{dec}年代</a>'
        for dec in sorted(by_decade, reverse=True)
    )
    return (
        '<section class="ys-foreign-decades-table" id="ys-foreign-decades" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 8px;">📚 年代別一覧 (OB {sum(len(v) for v in by_decade.values())} 名)</h2>'
        f'<div style="margin:0 0 6px;">{chips}</div>'
        '<p style="font-size:12px;color:#777;margin:0 0 4px;">在籍は読売ジャイアンツでの期間。NPB通算は全球団合算。</p>'
        f'{"".join(blocks)}'
        '</section>'
    )


def _build_year_matrix_html(data: dict) -> str:
    """年度別在籍早見表。 行=年 (新→旧)、 列=投手/野手。 掲載選手のいない連続年は 1 行に圧縮。"""
    ob = data.get("ob") or []
    if not ob:
        return ""
    # 上端は OB の最終在籍年。 現役分は加入年未整備のため本表に出さない (現役一覧へ誘導)。
    season = max((_end_year(e) for e in ob), default=1934)
    by_year: dict[int, dict[str, list[dict]]] = {}
    for e in ob:
        y0, y1 = _start_year(e), _end_year(e)
        if not y0:
            continue
        for y in range(y0, y1 + 1):
            kind = "pitcher" if e.get("type") == "pitcher" else "batter"
            by_year.setdefault(y, {"pitcher": [], "batter": []})[kind].append(e)
    if not by_year:
        return ""
    y_min = min(by_year)

    def names_cell(entries: list[dict]) -> str:
        if not entries:
            return '<span style="color:#ccc;">—</span>'
        return "、".join(
            _player_link(e.get("display_name"), e.get("slug") or "")
            for e in sorted(entries, key=lambda e: str(e.get("display_name")))
        )

    rows = []
    y = season
    while y >= y_min:
        if y in by_year:
            rows.append(
                '<tr style="border-bottom:1px solid #eee;">'
                f'<td style="padding:6px 10px;text-align:center;font-weight:700;color:#5d4037;'
                f'white-space:nowrap;">{y}</td>'
                f'<td style="padding:6px 10px;font-size:12px;line-height:1.9;">{names_cell(by_year[y]["pitcher"])}</td>'
                f'<td style="padding:6px 10px;font-size:12px;line-height:1.9;">{names_cell(by_year[y]["batter"])}</td>'
                '</tr>'
            )
            y -= 1
        else:
            gap_end = y
            while y >= y_min and y not in by_year:
                y -= 1
            gap_start = y + 1
            label = f"{gap_start}" if gap_start == gap_end else f"{gap_start}-{gap_end}"
            rows.append(
                '<tr style="border-bottom:1px solid #eee;background:#fafafa;">'
                f'<td style="padding:6px 10px;text-align:center;color:#999;white-space:nowrap;">{label}</td>'
                '<td colspan="2" style="padding:6px 10px;font-size:12px;color:#999;">掲載選手なし</td>'
                '</tr>'
            )
    return (
        '<section class="ys-foreign-years-table" id="ys-foreign-years" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 8px;">📅 年度別在籍早見表 ({y_min}-{season})</h2>'
        '<p style="font-size:12px;color:#777;margin:0 0 8px;">各年に在籍していた外国人選手 (OB 分)。 '
        '現役選手の加入年は整備中のため、 本表には未反映 (上の現役一覧を参照)。</p>'
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:left;">'
        '<th style="padding:8px 10px;text-align:center;">年</th>'
        '<th style="padding:8px 10px;">投手</th>'
        '<th style="padding:8px 10px;">野手</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table></div></section>'
    )


def _build_footnote_html(data: dict) -> str:
    pending = data.get("pending") or []
    pend = "".join(f'<li style="margin:2px 0;">{_esc(p)}</li>' for p in pending)
    return (
        '<section class="ys-foreign-note" '
        'style="background:#fafafa;border:1px solid #eee;padding:12px 16px;margin:0 0 16px;border-radius:4px;">'
        '<p style="font-size:11px;color:#999;margin:0 0 6px;">'
        '※ 外国籍として NPB 登録された選手 (韓国・台湾出身、ハワイ出身の日系米国人を含む) を掲載。 '
        '砂川リチャードは沖縄出身の日本人のため対象外。 '
        '在籍年・通算成績は NPB 公式記録・Wikipedia 検証済み台帳に基づく。</p>'
        + (f'<ul style="font-size:11px;color:#999;margin:0;padding-left:18px;">{pend}</ul>' if pend else "")
        + '</section>'
    )


def _breadcrumb_jsonld() -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ホーム", "item": f"{SITE_BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "巨人選手データ", "item": CLUSTER_URL},
            {"@type": "ListItem", "position": 3, "name": "歴代外国人選手",
             "item": f"{SITE_BASE}/data/{PAGE_SLUG}/"},
        ],
    }
    return ('<script type="application/ld+json">'
            + _json.dumps(payload, ensure_ascii=False)
            + '</script>')


# ---- public API ----

def render_foreign_players_title() -> str:
    return "巨人 歴代外国人選手一覧【年度別在籍・通算成績】 | 巨人データ"


def render_foreign_players_excerpt(data: dict | None = None) -> str:
    data = data if data is not None else load_foreign_players_data()
    ob = data.get("ob") or []
    active = data.get("active") or []
    return (f"読売ジャイアンツの歴代外国人選手 {len(ob) + len(active)}名を一覧化。"
            "スタルヒン・クロマティからマイコラス、現役助っ人まで、年度別在籍と NPB 通算成績、"
            "個人成績ページへのリンクつき。年代別・年度別の早見表で検索も可能。")


def render_foreign_players_html(data: dict | None = None) -> str:
    data = data if data is not None else load_foreign_players_data()
    nav = ('<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
           f'<a href="/" style="color:#1976d2;text-decoration:none;">ホーム</a> › '
           f'<a href="/data/" style="color:#1976d2;text-decoration:none;">巨人選手データ</a> › '
           '歴代外国人選手</nav>')
    return (
        nav
        + roster_moves_nav(PAGE_SLUG)
        + _build_intro_html(data)
        + _build_search_html()
        + _build_active_html(data)
        + _build_decades_html(data)
        + _build_year_matrix_html(data)
        + _build_footnote_html(data)
        + _breadcrumb_jsonld()
    )
