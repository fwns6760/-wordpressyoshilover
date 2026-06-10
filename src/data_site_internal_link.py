"""トピッククラスター内部リンク用ヘルパ。

- linkify(name): 選手名を、ページが存在する選手だけ /data/<slug>/ へリンク（無ければただのテキスト）。
- roster_moves_nav(current): 編成クラスタ（ドラフト/FA/トレード）の横リンクバー。
- breadcrumb_jsonld(name, slug): BreadcrumbList 構造化データ（親=巨人選手データ /data/）。

slug マップ正本: config/data_site_player_slugs.json（src/tools/build_player_slug_map.py で生成）。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os
import re as _re

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"

_SLUG_PATH = _os.path.join(_os.path.dirname(__file__), "..", "config", "data_site_player_slugs.json")
_WS = _re.compile(r"[\s　]+")
_PAREN = _re.compile(r"[（(].*?[）)]")
_SLUG_MAP: dict | None = None


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_slug_map() -> dict:
    global _SLUG_MAP
    if _SLUG_MAP is None:
        try:
            with open(_SLUG_PATH, encoding="utf-8") as fh:
                _SLUG_MAP = _json.load(fh)
        except Exception:
            _SLUG_MAP = {}
    return _SLUG_MAP


def _keys(name: str) -> list[str]:
    base = _WS.sub("", (name or "").strip())
    out = [base]
    stripped = _WS.sub("", _PAREN.sub("", name or ""))
    if stripped and stripped != base:
        out.append(stripped)
    return [k for k in out if k]


def linkify(name: str, slug_map: dict | None = None) -> str:
    """選手名 HTML を返す。ページがあれば <a>、無ければ escape したテキスト。"""
    disp = _esc(name)
    if not name:
        return disp
    m = slug_map if slug_map is not None else load_slug_map()
    for k in _keys(name):
        slug = m.get(k)
        if slug:
            return (f'<a href="/data/{_esc(slug)}/" '
                    f'style="color:#1565c0;text-decoration:none;">{disp}</a>')
    return disp


# 編成クラスタ（ドラフト/FA/トレード）の相互リンク。トピッククラスターの横の辺。
_ROSTER_MOVES = [
    ("draft", "📋 歴代ドラフト"),
    ("fa", "🤝 FA選手"),
    ("trade", "🔄 トレード/移籍"),
    ("foreign-players", "🌍 歴代外国人"),
]


def roster_moves_nav(current: str) -> str:
    chips = []
    for slug, label in _ROSTER_MOVES:
        if slug == current:
            chips.append(f'<span style="display:inline-block;padding:5px 12px;margin:2px;'
                         f'border-radius:14px;background:#5d4037;color:#fff;font-size:12px;'
                         f'font-weight:700;">{_esc(label)}</span>')
        else:
            chips.append(f'<a href="/data/{slug}/" style="display:inline-block;padding:5px 12px;'
                         f'margin:2px;border-radius:14px;border:1px solid #5d4037;color:#5d4037;'
                         f'text-decoration:none;font-size:12px;font-weight:600;">{_esc(label)}</a>')
    return ('<div style="margin:0 0 14px;padding:8px 0;border-bottom:1px solid #eee;">'
            '<span style="font-size:11px;color:#999;margin-right:6px;">編成データ:</span>'
            + "".join(chips) + '</div>')


def breadcrumb_jsonld(name: str, slug: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ホーム", "item": f"{SITE_BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "巨人選手データ", "item": CLUSTER_URL},
            {"@type": "ListItem", "position": 3, "name": name, "item": f"{SITE_BASE}/data/{slug}/"},
        ],
    }
    return ('<script type="application/ld+json">'
            + _json.dumps(data, ensure_ascii=False) + '</script>')
