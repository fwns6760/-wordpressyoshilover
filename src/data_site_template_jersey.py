"""Template for /data/jersey-numbers/ historical jersey-number page."""

from __future__ import annotations

import html as _html
import json as _json
import re as _re

from src.data_site_internal_link import breadcrumb_jsonld, linkify
from src.data_site_jersey_source import (
    JerseyNumberRow,
    RETIRED_NUMBERS,
    RETIRED_SOURCE_URL,
    SOURCE_URL,
)


SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SLUG = "jersey-numbers"
_PAREN = _re.compile(r"[（(].*?[）)]")


def _esc(text) -> str:
    return _html.escape(str(text if text is not None else ""), quote=True)


def _number_sort_key(number: str) -> tuple[int, str]:
    try:
        return (int(number), number)
    except ValueError:
        return (9999, number)


def _is_development_number(number: str) -> bool:
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    if len(digits) >= 3:
        return True
    try:
        return int(digits or "0") >= 100
    except ValueError:
        return False


def _clean_player_name(text: str) -> str:
    s = str(text or "").strip()
    s = s.replace("永久欠番・", "")
    s = s.split("←", 1)[0].split("／", 1)[0]
    s = _PAREN.sub("", s).strip()
    # Keep only the first likely name when a note follows.
    for sep in ("[", "・永久欠番", " "):
        if sep in s and sep != " ":
            s = s.split(sep, 1)[0].strip()
    return s


def _current_html(row: JerseyNumberRow) -> str:
    name = _clean_player_name(row.current)
    if row.is_retired and name:
        return f'<span style="font-weight:800;color:#8a4a00;">永久欠番</span> {linkify(name)}'
    if name and name != row.current:
        return f'{linkify(name)} <span style="font-size:11px;color:#888;">{_esc(row.current.replace(name, "").strip())}</span>'
    return linkify(row.current)


def _history_nav(current: str = SLUG) -> str:
    links = [
        ("record", "記録室"),
        ("ranking", "ランキング"),
        ("legends", "歴代在籍選手"),
        ("cleanup-hitters", "歴代4番打者"),
        ("jersey-numbers", "歴代背番号"),
    ]
    chips = []
    for slug, label in links:
        if slug == current:
            chips.append(
                '<span style="display:inline-block;padding:5px 12px;margin:2px;border-radius:14px;'
                'background:#5d4037;color:#fff;font-size:12px;font-weight:700;">'
                f'{_esc(label)}</span>'
            )
        else:
            chips.append(
                f'<a href="/data/{slug}" style="display:inline-block;padding:5px 12px;margin:2px;'
                'border-radius:14px;border:1px solid #5d4037;color:#5d4037;text-decoration:none;'
                f'font-size:12px;font-weight:600;">{_esc(label)}</a>'
            )
    return (
        '<div style="margin:0 0 14px;padding:8px 0;border-bottom:1px solid #eee;">'
        '<span style="font-size:11px;color:#999;margin-right:6px;">歴史データ:</span>'
        + "".join(chips)
        + "</div>"
    )


def _topic_links() -> str:
    links = [
        ("/data", "選手データ", "現役選手の背番号・成績へ"),
        ("/data/legends", "歴代在籍選手", "OB個別ページへ"),
        ("/data/draft", "歴代ドラフト", "入団年・指名順位へ"),
        ("/data/farm", "2軍ファーム", "若手の番号と現在地へ"),
    ]
    cards = []
    for href, title, lead in links:
        cards.append(
            f'<a href="{href}" style="display:block;border:1px solid #eee;border-radius:8px;'
            'padding:10px 12px;background:#fff;text-decoration:none;color:#1a1a1a;">'
            f'<strong style="display:block;font-size:13px;color:#e65100;margin-bottom:3px;">{_esc(title)}</strong>'
            f'<span style="font-size:12px;color:#666;">{_esc(lead)}</span></a>'
        )
    return (
        '<section style="margin:0 0 18px;">'
        '<h2 style="font-size:16px;margin:0 0 8px;">関連トピック</h2>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;">'
        + "".join(cards)
        + "</div></section>"
    )


def _retired_cards() -> str:
    cards = []
    for r in RETIRED_NUMBERS:
        cards.append(
            '<article style="background:#fff8e1;border:1px solid #ffecb3;border-radius:8px;padding:11px 12px;">'
            f'<div style="font-size:24px;font-weight:900;color:#e65100;line-height:1;">#{_esc(r["number"])}</div>'
            f'<div style="font-size:14px;font-weight:800;margin:5px 0 2px;">{linkify(r["name"])}</div>'
            f'<div style="font-size:11px;color:#8d6e63;">{_esc(r["label"])}</div>'
            '</article>'
        )
    return (
        '<section id="retired-numbers" style="margin:0 0 18px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;border-left:4px solid #5d4037;padding-left:8px;">永久欠番</h2>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;">'
        + "".join(cards)
        + "</div></section>"
    )


def _metric_cards(rows: list[JerseyNumberRow]) -> str:
    retired = sum(1 for r in rows if r.is_retired)
    active_like = sum(1 for r in rows if r.current and not r.is_retired)
    development = sum(1 for r in rows if _is_development_number(r.number))
    regular = max(0, len(rows) - development)
    cards = [
        ("支配下背番号", f"{regular}", "0・00・永久欠番を含む"),
        ("育成背番号", f"{development}", "3桁番号を分離"),
        ("永久欠番", f"{retired or len(RETIRED_NUMBERS)}", "球団史の象徴"),
        ("現役/現保持者", f"{active_like}", "検索対象"),
    ]
    return (
        '<section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:0 0 18px;">'
        + "".join(
            '<div style="background:#fff;border:1px solid #eee;border-radius:8px;padding:10px 12px;">'
            f'<div style="font-size:11px;color:#777;">{_esc(label)}</div>'
            f'<div style="font-size:24px;font-weight:900;color:#e65100;line-height:1.2;">{_esc(value)}</div>'
            f'<div style="font-size:11px;color:#888;">{_esc(note)}</div></div>'
            for label, value, note in cards
        )
        + "</section>"
    )


def _jump_nav() -> str:
    return (
        '<div style="margin:0 0 14px;">'
        '<a href="#retired-numbers" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
        'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">永久欠番</a>'
        '<a href="#regular-number-history" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
        'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">支配下背番号</a>'
        '<a href="#development-number-history" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
        'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">育成背番号</a>'
        '<a href="#topic-links" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
        'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">関連データ</a>'
        '</div>'
    )


def _history_table(
    rows: list[JerseyNumberRow],
    *,
    section_id: str,
    title: str,
    lead: str,
) -> str:
    trs = []
    for row in sorted(rows, key=lambda r: _number_sort_key(r.number)):
        bg = "#fff8e1" if row.is_retired else ("#fff" if len(trs) % 2 == 0 else "#fcf9f4")
        search = f"{row.number} {row.current} {row.history}"
        trs.append(
            f'<tr data-jersey-row="{_esc(search)}" style="background:{bg};border-bottom:1px solid #eee;">'
            f'<td style="padding:8px 10px;font-size:17px;font-weight:900;color:#5d4037;white-space:nowrap;">#{_esc(row.number)}</td>'
            f'<td style="padding:8px 10px;font-size:13px;vertical-align:top;min-width:130px;">{_current_html(row)}</td>'
            f'<td style="padding:8px 10px;font-size:12px;color:#555;line-height:1.55;vertical-align:top;">{_esc(row.history or "—")}</td>'
            '</tr>'
        )
    if not trs:
        trs.append(
            '<tr data-jersey-row="" style="background:#fff;border-bottom:1px solid #eee;">'
            '<td colspan="3" style="padding:12px 10px;font-size:12px;color:#888;">該当データがありません。</td>'
            '</tr>'
        )
    return (
        f'<section id="{_esc(section_id)}" style="margin:0 0 18px;">'
        f'<h3 style="font-size:16px;margin:0 0 6px;border-left:4px solid #5d4037;padding-left:8px;">{_esc(title)}</h3>'
        f'<p style="font-size:12px;color:#666;margin:0 0 8px;line-height:1.6;">{_esc(lead)}</p>'
        '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;min-width:640px;background:#fff;border:1px solid #eee;">'
        '<thead><tr style="background:#fafafa;">'
        '<th style="padding:9px 10px;text-align:left;font-size:12px;">背番号</th>'
        '<th style="padding:9px 10px;text-align:left;font-size:12px;">現在/代表的保持者</th>'
        '<th style="padding:9px 10px;text-align:left;font-size:12px;">過去の変遷</th>'
        '</tr></thead><tbody>'
        + "".join(trs)
        + '</tbody></table></div>'
        '</section>'
    )


def _history_tables(rows: list[JerseyNumberRow]) -> str:
    regular_rows = [r for r in rows if not _is_development_number(r.number)]
    development_rows = [r for r in rows if _is_development_number(r.number)]
    return (
        '<section id="number-history" style="margin:0 0 18px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;border-left:4px solid #5d4037;padding-left:8px;">番号別 背番号変遷</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 10px;line-height:1.6;">'
        '支配下・永久欠番と、3桁の育成背番号を分けて確認できます。</p>'
        '<input type="search" id="ys-jersey-search" autocomplete="off" '
        'placeholder="背番号・選手名で検索（例: 3 / 坂本 / 松井 / 001）" '
        'style="width:100%;box-sizing:border-box;padding:11px 12px;border:2px solid #ffd9bf;border-radius:8px;margin:0 0 10px;">'
        '<p id="ys-jersey-empty" hidden style="font-size:12px;color:#888;margin:0 0 10px;">該当する背番号・選手名が見つかりません。</p>'
        '</section>'
        + _history_table(
            regular_rows,
            section_id="regular-number-history",
            title="支配下・永久欠番 背番号",
            lead="0・00・1〜99番を中心に、現役選手とOBの背番号変遷をまとめています。",
        )
        + _history_table(
            development_rows,
            section_id="development-number-history",
            title="育成背番号（3桁）",
            lead="育成選手の3桁番号を支配下番号と分けて表示しています。",
        )
        + '<script>(function(){var q=document.getElementById("ys-jersey-search");if(!q)return;'
        'var empty=document.getElementById("ys-jersey-empty");var rows=[].slice.call(document.querySelectorAll("[data-jersey-row]"));'
        'function norm(s){return(s||"").replace(/\\s+/g,"").toLowerCase();}'
        'q.addEventListener("input",function(){var s=norm(q.value);var n=0;rows.forEach(function(r){'
        'var hit=!s||norm(r.getAttribute("data-jersey-row")).indexOf(s)>=0;'
        'r.style.display=hit?"":"none";if(hit)n++;});if(empty)empty.hidden=!(s&&n===0);});})();</script>'
    )


def render_jersey_numbers_html(rows: list[JerseyNumberRow]) -> str:
    rows = rows or []
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>歴代背番号</span></nav>'
    )
    source = (
        '<p style="font-size:11px;color:#999;margin:0 0 14px;line-height:1.6;">'
        f'参考: <a href="{SOURCE_URL}" rel="nofollow noopener" target="_blank">my favorite giants 背番号変遷</a> / '
        f'<a href="{RETIRED_SOURCE_URL}" rel="nofollow noopener" target="_blank">永久欠番</a>。'
        '事実データを検索しやすい構成に再整理しています。</p>'
    )
    return (
        breadcrumb_jsonld("巨人 歴代背番号", SLUG)
        + '<div style="font-family:sans-serif;max-width:860px;">'
        + nav
        + _history_nav()
        + '<h1 style="font-size:20px;margin:0 0 4px;">巨人 歴代背番号一覧・変遷</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 12px;line-height:1.7;">'
        '読売ジャイアンツの背番号を番号別にたどるページです。永久欠番、支配下背番号、育成背番号、OBの番号変遷を検索でき、'
        '選手データ・レジェンド・ドラフト・2軍ファームへ回遊できます。</p>'
        + source
        + _metric_cards(rows)
        + _jump_nav()
        + _retired_cards()
        + _history_tables(rows)
        + '<section id="topic-links">'
        + _topic_links()
        + '</section>'
        + f'<p style="margin-top:20px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a> ／ '
        '<a href="/data/legends">歴代在籍選手へ</a> ／ <a href="/data/record">記録室へ</a></p>'
        + "</div>"
    )


def render_jersey_numbers_title() -> str:
    return "巨人 歴代背番号一覧・変遷【支配下・育成・永久欠番】 | 巨人データ"


def render_jersey_numbers_excerpt(rows: list[JerseyNumberRow]) -> str:
    return (
        f"読売ジャイアンツの歴代背番号一覧。支配下背番号、育成背番号、永久欠番、OBの背番号変遷を番号・選手名で検索。"
        f"掲載背番号{len(rows)}件。"
    )


__all__ = [
    "render_jersey_numbers_excerpt",
    "render_jersey_numbers_html",
    "render_jersey_numbers_title",
]
