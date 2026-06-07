"""data/cleanup-hitters page template (468-7 歴代4番打者).

The source table is semi-static. The page uses only public factual records from
config/giants_cleanup_hitters.json and renders a topic-cluster spoke under
/data/: cleanup history -> record room / rankings / legends / player pages.
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os
import re as _re

from src.data_site_internal_link import breadcrumb_jsonld, load_slug_map


SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"
SLUG = "cleanup-hitters"
_DATA_PATH = _os.path.join(_os.path.dirname(__file__), "..", "config", "giants_cleanup_hitters.json")
_WS = _re.compile(r"[\s　]+")
_PAREN = _re.compile(r"[（(].*?[）)]")
_LATIN_INITIAL = _re.compile(r"^[A-Za-z]\.")


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def _norm(t: str) -> str:
    return _WS.sub("", _PAREN.sub("", str(t or "")))


def load_cleanup_hitters_data() -> dict:
    """Read config/giants_cleanup_hitters.json. Failure returns an empty dict."""
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _slug_for(name: str) -> str:
    """Best-effort lookup against generated /data/ player slugs.

    Some active-player slug keys include a suffix such as "2026年成績・打率";
    this page is a history table, so prefix lookup is allowed only when unique.
    """
    m = load_slug_map()
    keys = [_norm(name)]
    stripped_initial = _LATIN_INITIAL.sub("", keys[0])
    if stripped_initial and stripped_initial != keys[0]:
        keys.append(stripped_initial)
    for key in keys:
        if key in m:
            return str(m[key])
        matches = [v for k, v in m.items() if _norm(k).startswith(key)]
        if len(set(matches)) == 1:
            return str(matches[0])
    return ""


def _player(name: str) -> str:
    slug = _slug_for(name)
    if not slug:
        return _esc(name)
    return f'<a href="/data/{_esc(slug)}/" style="color:#1565c0;text-decoration:none;">{_esc(name)}</a>'


def _num(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return _esc(v)


def _cell(v) -> str:
    s = _esc(v).strip()
    return s if s else "—"


def render_cleanup_hitters_title() -> str:
    return "巨人 歴代4番打者 成績一覧【歴代96代・2025年終了時点】 | 巨人データ"


def render_cleanup_hitters_excerpt(data: dict) -> str:
    rows = data.get("alltime") or []
    as_of = data.get("as_of") or "最新確認時点"
    return (
        f"読売ジャイアンツ歴代4番打者{len(rows)}名の成績一覧。{as_of}の試合数・本塁打・打点・打率、"
        "2025年シーズンの4番起用、連続4番先発記録を巨人データのトピッククラスターに整理。"
    )


def _history_nav() -> str:
    links = [
        (SLUG, "4番打者"),
        ("record", "記録室"),
        ("ranking", "ランキング"),
        ("legends", "歴代在籍選手"),
    ]
    chips = []
    for slug, label in links:
        if slug == SLUG:
            chips.append(
                f'<span style="display:inline-block;padding:5px 12px;margin:2px;border-radius:14px;'
                f'background:#5d4037;color:#fff;font-size:12px;font-weight:700;">{_esc(label)}</span>'
            )
        else:
            chips.append(
                f'<a href="/data/{slug}/" style="display:inline-block;padding:5px 12px;margin:2px;'
                f'border-radius:14px;border:1px solid #5d4037;color:#5d4037;text-decoration:none;'
                f'font-size:12px;font-weight:600;">{_esc(label)}</a>'
            )
    return (
        '<div style="margin:0 0 14px;padding:8px 0;border-bottom:1px solid #eee;">'
        '<span style="font-size:11px;color:#999;margin-right:6px;">歴史データ:</span>'
        + "".join(chips)
        + "</div>"
    )


def _metric_cards(rows: list[dict], consecutive: dict) -> str:
    if not rows:
        return ""
    by_games = max(rows, key=lambda r: int(r.get("games") or 0))
    by_hr = max(rows, key=lambda r: int(r.get("hr") or 0))
    by_rbi = max(rows, key=lambda r: int(r.get("rbi") or 0))
    cards = [
        ("最多4番先発", by_games.get("name"), f'{_num(by_games.get("games"))}試合'),
        ("4番時 本塁打", by_hr.get("name"), f'{_num(by_hr.get("hr"))}本'),
        ("4番時 打点", by_rbi.get("name"), f'{_num(by_rbi.get("rbi"))}打点'),
        ("連続4番先発", consecutive.get("name"), f'{_num(consecutive.get("games"))}試合'),
    ]
    return (
        '<section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));'
        'gap:8px;margin:0 0 18px;">'
        + "".join(
            '<div style="background:#fff8e1;border:1px solid #ffecb3;border-radius:8px;padding:10px 12px;">'
            f'<div style="font-size:11px;color:#8d6e63;">{_esc(label)}</div>'
            f'<div style="font-size:15px;font-weight:700;color:#5d4037;">{_player(name or "")}</div>'
            f'<div style="font-size:18px;font-weight:800;color:#e25400;">{_esc(value)}</div></div>'
            for label, name, value in cards
        )
        + "</section>"
    )


def _simple_table(headers: list[str], rows: list[list[str]], *, min_width: int = 640) -> str:
    if not rows:
        return ""
    th = "".join(
        f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #5d4037;'
        f'font-size:12px;color:#5d4037;white-space:nowrap;">{_esc(h)}</th>' for h in headers
    )
    trs = []
    for i, row in enumerate(rows):
        bg = "#fff" if i % 2 == 0 else "#fcf9f4"
        tds = "".join(
            f'<td style="padding:6px 8px;border-bottom:1px solid #eee;font-size:13px;'
            f'white-space:nowrap;vertical-align:top;">{c}</td>' for c in row
        )
        trs.append(f'<tr style="background:{bg};">{tds}</tr>')
    return (
        f'<div style="overflow-x:auto;margin:0 0 8px;"><table style="border-collapse:collapse;'
        f'width:100%;min-width:{min_width}px;">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
    )


def _render_current(data: dict) -> str:
    rows = []
    for e in data.get("current_season") or []:
        rows.append([
            _player(e.get("name", "")),
            _num(e.get("games")),
            _num(e.get("ab")),
            _num(e.get("hits")),
            _num(e.get("hr")),
            _num(e.get("rbi")),
            _cell(e.get("avg")),
        ])
    label = data.get("current_season_label") or "直近シーズン"
    return (
        f'<h2 id="current" style="font-size:17px;margin:24px 0 6px;border-left:4px solid #5d4037;'
        f'padding-left:8px;">{_esc(label)}の4番起用</h2>'
        '<p style="font-size:12px;color:#777;margin:0 0 8px;">直近シーズンに4番で先発した選手の打撃成績。</p>'
        + _simple_table(["選手", "試合", "打数", "安打", "本塁打", "打点", "打率"], rows, min_width=560)
    )


def _render_alltime(rows: list[dict]) -> str:
    table_rows = []
    for e in sorted(rows, key=lambda r: int(r.get("generation") or 0), reverse=True):
        table_rows.append([
            _cell(e.get("generation")),
            _player(e.get("name", "")),
            _cell(e.get("period")),
            _cell(e.get("first_game")),
            _num(e.get("games")),
            _num(e.get("ab")),
            _num(e.get("hits")),
            _num(e.get("hr")),
            _num(e.get("rbi")),
            _cell(e.get("avg")),
        ])
    return (
        '<h2 id="alltime" style="font-size:17px;margin:24px 0 6px;border-left:4px solid #5d4037;'
        'padding-left:8px;">歴代4番打者 全一覧</h2>'
        '<p style="font-size:12px;color:#777;margin:0 0 8px;">「代」は巨人で初めて4番先発した順。成績は4番先発時の集計。</p>'
        + _simple_table(["代", "選手", "期間", "初試合", "試合", "打数", "安打", "本塁打", "打点", "打率"], table_rows, min_width=860)
    )


def render_cleanup_hitters_html(data: dict | None = None) -> str:
    data = data if data is not None else load_cleanup_hitters_data()
    rows = data.get("alltime") or []
    consecutive = data.get("consecutive_starter_record") or {}
    as_of = data.get("as_of") or ""
    updated = data.get("updated") or ""
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>歴代4番打者</span></nav>'
    )
    jump = (
        '<div style="margin:0 0 14px;">'
        '<a href="#current" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
        'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">直近シーズン</a>'
        '<a href="#alltime" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
        'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">全一覧</a>'
        '</div>'
    )
    source = (
        '<p style="font-size:11px;color:#999;margin:0 0 14px;line-height:1.6;">'
        '参考: my favorite giants「巨人 歴代4番打者」の事実テーブル。'
        '選手名・成績のみを整理し、本文/HTMLは独自作成。'
        f'{(" 成績: " + _esc(as_of) + "。" if as_of else "")}'
        f'{(" 最終更新: " + _esc(updated) + "。" if updated else "")}</p>'
    )
    return (
        breadcrumb_jsonld("巨人 歴代4番打者", SLUG)
        + '<div style="font-family:sans-serif;max-width:860px;">'
        + nav
        + _history_nav()
        + '<h1 style="font-size:20px;margin:0 0 4px;">巨人 歴代4番打者 成績一覧</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 12px;">'
        '読売ジャイアンツで4番を任された選手の名前、初4番の試合、4番先発時の試合数・本塁打・打点・打率をまとめた歴史データです。'
        '長嶋茂雄、王貞治、川上哲治から岡本和真まで、選手ページ・記録室・ランキングへ回遊できるよう整理しています。</p>'
        + source
        + _metric_cards(rows, consecutive)
        + jump
        + _render_current(data)
        + _render_alltime(rows)
        + f'<p style="margin-top:20px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a> ／ '
        f'<a href="/data/record/">記録室へ</a> ／ <a href="/data/legends/">歴代在籍選手へ</a></p>'
        + "</div>"
    )


if __name__ == "__main__":
    import sys as _sys

    _sys.stdout.write(render_cleanup_hitters_html())
