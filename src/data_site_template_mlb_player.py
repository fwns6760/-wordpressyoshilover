"""data/mlb/<player> ページ template (巨人発メジャーリーガー 選手別)。

メジャー移籍後の全試合ログ (年度別 table) + 直近試合の打席ごと結果 (打者) /
登板詳細 (投手)。データは mlb_alumni_fetch.fetch_mlb_player_detail 由来。
"""

from __future__ import annotations

import html as _html
import json as _json

SITE_BASE = "https://yoshilover.com"
MLB_PATH = "/data/mlb"


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


def _fmt_date(iso: str) -> str:
    parts = str(iso or "").split("-")
    if len(parts) == 3:
        return f"{int(parts[1])}/{int(parts[2])}"
    return str(iso or "")


def _summary_line(detail: dict, summary: dict) -> str:
    if detail.get("group") == "hitting":
        return (f'打率 {summary.get("avg", "")} ・ {summary.get("hr", 0)}本塁打 ・ '
                f'{summary.get("rbi", 0)}打点 ・ OPS {summary.get("ops", "")} ・ {summary.get("games", 0)}試合')
    return (f'{summary.get("wins", 0)}勝{summary.get("losses", 0)}敗 ・ 防御率 {summary.get("era", "")} ・ '
            f'{summary.get("ip", "")}回 ・ {summary.get("so", 0)}奪三振 ・ {summary.get("games", 0)}登板')


def _last_game_box(detail: dict) -> str:
    seasons = detail.get("seasons") or []
    games = (seasons[0].get("games") or []) if seasons else []
    if not games:
        return ""
    g = games[0]
    head = f'現地{_fmt_date(g.get("date", ""))} vs {g.get("opponent", "")}'
    if detail.get("group") == "hitting":
        pa = detail.get("pa_log") or {}
        events = pa.get("events") or []
        if events and pa.get("date") == g.get("date"):
            chips = "".join(
                '<span style="display:inline-block;background:#fff;border:1px solid #ffd9bf;'
                'border-radius:14px;padding:3px 10px;margin:0 5px 5px 0;font-size:12.5px;">'
                f'<span style="color:#999;font-size:11px;">第{i + 1}打席</span> '
                f'<strong style="color:{"#e25400" if ev in ("単打", "二塁打", "三塁打", "本塁打") else "#444"};">'
                f'{_esc(ev)}</strong></span>'
                for i, ev in enumerate(events)
            )
            body = f'<div style="margin:8px 0 0;">{chips}</div>'
        else:
            body = (f'<p style="font-size:13px;margin:8px 0 0;color:#444;">'
                    f'{g.get("ab", 0)}打数{g.get("hits", 0)}安打</p>')
    else:
        body = (
            '<p style="font-size:13px;margin:8px 0 0;color:#444;">'
            f'{_esc(str(g.get("ip", "")))}回 ・ {g.get("hits", 0)}被安打 ・ {g.get("runs", 0)}失点 ・ '
            f'{g.get("bb", 0)}四球 ・ {g.get("so", 0)}奪三振 ・ {g.get("pitches", 0)}球</p>'
        )
    return (
        '<section style="background:#fff;border:1px solid #ffd9bf;border-radius:10px;'
        'padding:12px 14px;margin:0 0 16px;">'
        '<p style="font-size:12px;margin:0;color:#e25400;font-weight:700;">直近試合</p>'
        f'<p style="font-size:15px;font-weight:700;margin:2px 0 0;">{_esc(head)}</p>'
        f'{body}</section>'
    )


def _season_table(detail: dict, season: dict) -> str:
    group = detail.get("group")
    if group == "hitting":
        head_cells = ("日付", "相手", "打数", "安打", "本塁打", "打点")
    else:
        head_cells = ("日付", "相手", "勝敗", "回", "被安打", "失点", "奪三振", "球数")
    rows = []
    for g in season.get("games") or []:
        if group == "hitting":
            cells = (
                _fmt_date(g.get("date", "")), g.get("opponent", ""),
                g.get("ab", 0), g.get("hits", 0), g.get("hr", 0), g.get("rbi", 0),
            )
            hot = int(g.get("hr") or 0) > 0
        else:
            cells = (
                _fmt_date(g.get("date", "")), g.get("opponent", ""), g.get("decision", "－"),
                g.get("ip", ""), g.get("hits", 0), g.get("runs", 0), g.get("so", 0), g.get("pitches", 0),
            )
            hot = g.get("decision") == "○"
        style = "background:#fff8f2;" if hot else ""
        rows.append(
            f'<tr style="{style}">' + "".join(
                f'<td style="padding:5px 8px;border-top:1px solid #f5e6da;'
                f'{"text-align:left;" if i in (0, 1) else "text-align:center;"}'
                f'font-variant-numeric:tabular-nums;">{_esc(str(c))}</td>'
                for i, c in enumerate(cells)
            ) + "</tr>"
        )
    if not rows:
        return ""
    header = "".join(
        f'<th style="padding:6px 8px;{"text-align:left;" if i in (0, 1) else "text-align:center;"}">{_esc(h)}</th>'
        for i, h in enumerate(head_cells)
    )
    return (
        f'<h2 style="font-size:18px;margin:18px 0 4px;color:#e25400;">{season.get("season", "")}年</h2>'
        f'<p style="font-size:12.5px;color:#666;margin:0 0 8px;">{_esc(_summary_line(detail, season.get("summary") or {}))}</p>'
        '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12.5px;'
        'background:#fff;border:1px solid #ffd9bf;border-radius:10px;overflow:hidden;">'
        f'<thead><tr style="background:#fff0e6;color:#5d4037;">{header}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _player_jsonld(detail: dict) -> str:
    url = f'{SITE_BASE}{MLB_PATH}/{detail.get("slug", "")}'
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "巨人発メジャーリーガー", "item": SITE_BASE + MLB_PATH},
            {"@type": "ListItem", "position": 3, "name": str(detail.get("name") or ""), "item": url},
        ],
    }
    return f'<script type="application/ld+json">{_json.dumps(breadcrumb, ensure_ascii=False)}</script>'


def render_mlb_player_html(detail: dict | None) -> str:
    d = detail or {}
    seasons = d.get("seasons") or []
    debut_year = str(d.get("debut") or "")[:4]
    tables = "".join(_season_table(d, s) for s in seasons)
    return (
        '<section class="ys-mlb-player-page" style="background:#fff8f2;border:1px solid #ffd9bf;'
        'border-radius:12px;padding:16px;margin:0 0 18px;">'
        f'<h1 style="font-size:24px;margin:0 0 4px;color:#e25400;">{_esc(d.get("name", ""))} メジャー全成績</h1>'
        '<p style="font-size:12px;color:#999;margin:0 0 12px;">'
        f'{_esc(d.get("team", ""))}{(" ・ " + _esc(debut_year) + "年メジャーデビュー") if debut_year else ""}'
        ' ・ 毎日更新 ・ 出典 MLB公式</p>'
        f'{_last_game_box(d)}'
        f'{tables}'
        '<section class="ys-source" style="font-size:11px;color:#888;margin:14px 0 0;'
        'padding:10px 12px;background:#fff;border:1px solid #eee;border-radius:4px;line-height:1.6;">'
        '📊 データ出典: メジャー成績・試合ログは'
        '<a href="https://www.mlb.com/" rel="nofollow noopener" target="_blank" '
        'style="color:#1565c0;">MLB公式(mlb.com)</a>に基づき毎日更新しています。'
        'NPB時代の通算成績は'
        f'<a href="/data/{_esc(d.get("slug", ""))}" style="color:#1565c0;">選手データページ</a>'
        'を参照。</section>'
        '<p style="font-size:12px;margin:14px 0 0;">'
        f'<a href="{MLB_PATH}" style="color:#1976d2;font-weight:700;text-decoration:none;">巨人発メジャーリーガーへ戻る</a>'
        ' ・ <a href="/data" style="color:#1976d2;font-weight:700;text-decoration:none;">巨人選手データ</a></p>'
        f'{_player_jsonld(d)}'
        '</section>'
    )


def render_mlb_player_title(detail: dict | None) -> str:
    d = detail or {}
    return f'{d.get("name", "")} メジャー全試合成績 - 試合別・打席別を毎日更新 | ヨシラバー'


def render_mlb_player_excerpt(detail: dict | None) -> str:
    d = detail or {}
    total = sum(len(s.get("games") or []) for s in (d.get("seasons") or []))
    return (f'{d.get("name", "")}({d.get("team", "")})のメジャー移籍後全{total}試合の成績と'
            '直近試合の詳細を毎日更新。出典はMLB公式データ。')
