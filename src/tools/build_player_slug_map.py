"""選手データページの 名前→slug マップを WP から生成（config/data_site_player_slugs.json）。

内部リンク（トピッククラスター）用。data 表の選手名を、ページが存在する選手だけ
/data/<slug>/ へリンクするために使う。

usage:
    python3 -m src.tools.build_player_slug_map            # config 上書き
    python3 -m src.tools.build_player_slug_map --dry
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests

WP = "https://yoshilover.com"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "config", "data_site_player_slugs.json")
_HUBS = {"data", "ranking", "team", "record", "legends", "schedule", "leaders",
         "draft", "fa", "trade"}
_WS = re.compile(r"[\s　]+")
_PAREN = re.compile(r"[（(].*?[）)]")
_SUFFIX = re.compile(r"\s*(通算成績|プロフィール|【).*$")


def _norm(s: str) -> str:
    return _WS.sub("", (s or "").strip())


def _name_keys(title_name: str) -> list[str]:
    """タイトル先頭の選手名から照合キーを作る（空白除去 + 別名カッコ除去）。"""
    base = _norm(title_name)
    keys = {base}
    stripped = _norm(_PAREN.sub("", title_name))
    if stripped:
        keys.add(stripped)
    return [k for k in keys if k]


def _cluster_id() -> int:
    r = requests.get(f"{WP}/wp-json/wp/v2/pages",
                     params={"slug": "data", "_fields": "id"}, timeout=20)
    j = r.json()
    return int(j[0]["id"]) if j else 0


def build() -> dict:
    cid = _cluster_id()
    if not cid:
        raise RuntimeError("data cluster page not found")
    mapping: dict[str, str] = {}
    page = 1
    while True:
        r = requests.get(f"{WP}/wp-json/wp/v2/pages",
                         params={"parent": cid, "per_page": 100, "page": page,
                                 "_fields": "slug,title"}, timeout=30)
        if r.status_code != 200:
            break
        rows = r.json()
        if not rows:
            break
        for p in rows:
            slug = p.get("slug")
            if not slug or slug in _HUBS:
                continue
            title = (p.get("title") or {}).get("rendered") or ""
            name = _SUFFIX.sub("", title).strip()
            if not name:
                continue
            for k in _name_keys(name):
                mapping.setdefault(k, slug)
        if len(rows) < 100:
            break
        page += 1
    return mapping


def main() -> int:
    mapping = build()
    print("player slug entries:", len(mapping))
    sample = list(mapping.items())[:5]
    print("sample:", sample)
    if "--dry" in sys.argv[1:]:
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, ensure_ascii=False, indent=0, sort_keys=True)
    print("wrote", os.path.abspath(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
