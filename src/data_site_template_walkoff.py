"""data/walkoff-homerun ページ template(巨人サヨナラ本塁打 一覧 hub)。

データ正本は config/giants_walkoff_homerun.json(事実のみ)。
ソース: my-favorite-giants.net/giants_data/walkoff_homerun.htm(事実参照のみ)。

トピッククラスター構成: /data/ ハブの子ページ。breadcrumb + cluster nav + 選手名の
内部リンク(linkify)で他の選手データページ・記録ページへ回遊させる。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os

from src.data_site_internal_link import linkify, breadcrumb_jsonld

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"

_DATA_PATH = _os.path.join(_os.path.dirname(__file__), "..", "config", "giants_walkoff_homerun.json")


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_walkoff_data() -> dict:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def render_walkoff_title() -> str:
    return "巨人 サヨナラ本塁打 全記録 一覧｜歴代162本・王貞治の通算最多"


def render_walkoff_excerpt(data: dict | None = None) -> str:
    d = data if data is not None else load_walkoff_data()
    n = d.get("total") or len(d.get("homeruns") or [])
    return f"読売ジャイアンツの歴代サヨナラ本塁打を全{n}本まとめて掲載。選手・試合日・対戦相手・球場・相手投手まで一覧で確認できます。"


def _cell(v) -> str:
    s = _esc(v).strip()
    return s if s else "—"


def _records_html(records) -> str:
    if not records:
        return ""
    items = "".join(
        f'<li style="margin:0 0 4px;"><strong>{_esc(r.get("category"))}</strong>：'
        f'{linkify(r.get("player"))} {_esc(r.get("value"))}'
        + (f'<span style="color:#999;font-size:12px;">（{_esc(r.get("note"))}）</span>' if r.get("note") else "")
        + "</li>"
        for r in records
    )
    return (
        '<div style="background:#fff6e5;border:1px solid #f0d9a8;border-radius:8px;padding:14px 16px;margin:0 0 18px;">'
        '<h2 style="font-size:15px;margin:0 0 8px;color:#5d4037;">🏆 サヨナラ本塁打の記録</h2>'
        f'<ul style="margin:0;padding-left:1.2em;font-size:13px;">{items}</ul></div>'
    )


def _table(homeruns) -> str:
    headers = ["順", "選手", "試合日", "対戦", "球場", "種別", "スコア", "延長", "相手投手", "備考"]
    th = "".join(
        f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #5d4037;'
        f'font-size:12px;color:#5d4037;white-space:nowrap;">{_esc(h)}</th>' for h in headers
    )
    trs = []
    # 新しい順(直近のサヨナラ本塁打を上に)
    for i, r in enumerate(reversed(homeruns)):
        bg = "#fafafa" if i % 2 else "#fff"
        score = f'{_esc(r.get("score_before"))}→{_esc(r.get("score_after"))}'
        cells = [
            _cell(r.get("no")),
            f'<strong>{linkify(r.get("player"))}</strong>',
            _cell(r.get("date")),
            _cell(r.get("opponent")),
            _cell(r.get("stadium")),
            _cell(r.get("type")),
            score,
            _cell(r.get("extra_inning")),
            _cell(r.get("pitcher")),
            _cell(r.get("note")),
        ]
        tds = "".join(
            f'<td style="padding:6px 8px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;">{c}</td>'
            for c in cells
        )
        trs.append(f'<tr style="background:{bg};">{tds}</tr>')
    return (
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;min-width:760px;">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
    )


def _nav_html() -> str:
    links = [
        ("/data/legends", "巨人レジェンド・OB"),
        ("/data/batting-ranking", "打撃ランキング"),
        ("/data/team", "チーム成績・順位"),
        ("/data", "巨人選手データ トップ"),
    ]
    chips = "".join(
        f'<a href="{_esc(u)}" style="display:inline-block;padding:6px 12px;margin:0 6px 6px 0;'
        f'background:#f5f5f5;border-radius:14px;color:#1a1a1a;text-decoration:none;font-size:13px;">{_esc(t)}</a>'
        for u, t in links
    )
    return f'<div style="margin:20px 0 0;">{chips}</div>'


def render_walkoff_html(data: dict | None = None) -> str:
    d = data if data is not None else load_walkoff_data()
    hrs = d.get("homeruns") or []
    n = d.get("total") or len(hrs)
    if not hrs:
        return ""
    latest = hrs[-1]
    intro = (
        f'<p>読売ジャイアンツ(巨人)の歴代<strong>サヨナラ本塁打</strong>を、'
        f'1941年から現在まで<strong>全{n}本</strong>まとめた一覧です。'
        f'通算最多は<strong>{linkify("王 貞治")}の8本</strong>(セ・リーグ記録)。'
        f'直近は{_esc(latest.get("date"))}・対{_esc(latest.get("opponent"))}戦での'
        f'{linkify(latest.get("player"))}({_esc(latest.get("type"))})です。</p>'
    )
    body = (
        f'<h2>巨人 サヨナラ本塁打 全{n}本</h2>'
        + intro
        + _records_html(d.get("records") or [])
        + _table(hrs)
        + _nav_html()
        + '<p style="font-size:12px;color:#888;margin:16px 0 0;">'
        '※選手・試合日・対戦相手・球場・相手投手は公開記録に基づく事実データです。</p>'
    )
    try:
        bc = breadcrumb_jsonld("サヨナラ本塁打 全記録")
    except Exception:
        bc = ""
    return bc + body
