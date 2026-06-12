"""data/mlb ページ template (巨人発メジャーリーガー、岡本和真・菅野智之)。

元巨人 OB の MLB 今季成績 + 直近試合を notable と同じ「数字中心・文字最小」の
カード形式で表示する。データは mlb_alumni_fetch (MLB 公式 Stats API) 由来。
"""

from __future__ import annotations

import html as _html
import json as _json

SITE_BASE = "https://yoshilover.com"
MLB_PATH = "/data/mlb"
MLB_URL = f"{SITE_BASE}{MLB_PATH}"


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


def _fmt_date(iso: str) -> str:
    parts = str(iso or "").split("-")
    if len(parts) == 3:
        return f"{int(parts[1])}/{int(parts[2])}"
    return str(iso or "")


def _hero(entry: dict) -> tuple[str, str]:
    s = entry.get("season") or {}
    if entry.get("group") == "hitting":
        return ("本塁打", f'{s.get("hr", 0)}本')
    return ("今季", f'{s.get("wins", 0)}勝{s.get("losses", 0)}敗')


def _season_line(entry: dict) -> str:
    s = entry.get("season") or {}
    if entry.get("group") == "hitting":
        return f'打率 {s.get("avg", "")} ・ OPS {s.get("ops", "")} ・ {s.get("rbi", 0)}打点 ・ {s.get("games", 0)}試合'
    return f'防御率 {s.get("era", "")} ・ {s.get("ip", "")}回 ・ {s.get("so", 0)}奪三振 ・ {s.get("games", 0)}登板'


def _last_game_line(entry: dict) -> str:
    g = entry.get("last_game") or {}
    if not g:
        return ""
    head = f'現地{_fmt_date(g.get("date", ""))} vs {g.get("opponent", "")}'
    if entry.get("group") == "hitting":
        body = f'{g.get("ab", 0)}打数{g.get("hits", 0)}安打'
        if g.get("hr"):
            body += f'{g.get("hr")}本塁打'
        if g.get("rbi"):
            body += f'{g.get("rbi")}打点'
    else:
        body = f'{g.get("ip", "")}回{g.get("hits", 0)}被安打{g.get("runs", 0)}失点{g.get("so", 0)}奪三振'
    return f"{head} ・ {body}"


def _player_card(entry: dict) -> str:
    hero_label, hero_value = _hero(entry)
    last_line = _last_game_line(entry)
    last_html = (
        f'<p style="font-size:13px;margin:8px 0 0;color:#444;">'
        f'<span style="background:#fff0e6;border-radius:6px;padding:1px 6px;font-size:11px;'
        f'color:#e25400;font-weight:700;margin-right:6px;">直近</span>{_esc(last_line)}</p>'
        if last_line else ""
    )
    return (
        '<article style="background:#fff;border:1px solid #ffd9bf;border-radius:10px;padding:12px 14px;">'
        f'<p style="font-size:12px;margin:0 0 2px;color:#5d4037;font-weight:600;">{_esc(entry.get("team", ""))}</p>'
        f'<h2 style="font-size:19px;margin:0 0 6px;color:#1a1a1a;">{_esc(entry.get("name", ""))}</h2>'
        f'<div style="font-size:26px;font-weight:900;color:#e25400;font-variant-numeric:tabular-nums;'
        f'line-height:1.2;">{_esc(hero_value)}'
        f'<span style="font-size:12px;font-weight:600;color:#999;margin-left:6px;">{_esc(hero_label)}</span></div>'
        f'<p style="font-size:13px;margin:6px 0 0;color:#444;">{_esc(_season_line(entry))}</p>'
        f'{last_html}'
        '</article>'
    )


def _mlb_jsonld(data: dict) -> str:
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "巨人選手データ", "item": SITE_BASE + "/data"},
            {"@type": "ListItem", "position": 3, "name": "巨人発メジャーリーガー", "item": MLB_URL},
        ],
    }
    return f'<script type="application/ld+json">{_json.dumps(breadcrumb, ensure_ascii=False)}</script>'


def render_mlb_html(data: dict | None) -> str:
    payload = data or {}
    players = list(payload.get("players") or [])
    as_of = str(payload.get("as_of") or "")
    cards = "".join(_player_card(p) for p in players)
    empty = '<p style="font-size:13px;color:#777;margin:12px 0 0;">成績データは集計中です。</p>' if not cards else ""
    return (
        '<section class="ys-mlb-page" style="background:#fff8f2;border:1px solid #ffd9bf;'
        'border-radius:12px;padding:16px;margin:0 0 18px;">'
        '<h1 style="font-size:24px;margin:0 0 4px;color:#e25400;">巨人発メジャーリーガー</h1>'
        '<p style="font-size:12px;color:#999;margin:0 0 12px;">'
        f'{("現地" + _esc(_fmt_date(as_of)) + " 試合終了時点 ・ ") if as_of else ""}毎日更新 ・ 出典 MLB公式</p>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;">'
        f'{cards}</div>{empty}'
        '<p style="font-size:12px;margin:14px 0 0;">'
        '<a href="/data" style="color:#1976d2;font-weight:700;text-decoration:none;">巨人選手データへ戻る</a>'
        ' ・ <a href="/data/notable" style="color:#1976d2;font-weight:700;text-decoration:none;">注目データ</a></p>'
        f'{_mlb_jsonld(payload)}'
        '</section>'
    )


def render_mlb_title() -> str:
    return "巨人発メジャーリーガー 岡本和真・菅野智之の成績 - 毎日更新 | ヨシラバー"


def render_mlb_excerpt(data: dict | None) -> str:
    players = list((data or {}).get("players") or [])
    names = "・".join(str(p.get("name") or "") for p in players) or "岡本和真・菅野智之"
    return f"巨人出身メジャーリーガー({names})の今季成績と直近試合結果を毎日更新。出典はMLB公式データ。"
