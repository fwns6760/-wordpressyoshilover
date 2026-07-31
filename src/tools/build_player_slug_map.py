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

from src.data_site_slug import _PLAYER_SLUG_MAP

WP = "https://yoshilover.com"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "config", "data_site_player_slugs.json")
_HUBS = {"data", "ranking", "team", "record", "legends", "schedule", "leaders",
         "draft", "fa", "trade"}
_WS = re.compile(r"[\s　]+")
_PAREN = re.compile(r"[（(].*?[）)]")
_SUFFIX = re.compile(
    r"\s*(?:"
    r"20\d{2}年(?:成績(?:・(?:打率|防御率))?)?"
    r"|通算成績"
    r"|プロフィール"
    r"|【"
    r"|\|"
    r").*$"
)


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


def _player_name_from_title(title: str) -> str:
    """WP の SEO title から照合用の選手名部分だけを返す。

    現役ページは ``坂本勇人 2026年成績・打率【...】`` のような title を持つ。
    旧実装は ``【`` 以降しか落とせず、``坂本勇人2026年成績・打率`` が slug map
    の key になって、表中の ``坂本勇人`` と一致しなかった。
    """
    return _SUFFIX.sub("", title or "").strip()


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
    available_slugs: set[str] = set()
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
            available_slugs.add(slug)
            title = (p.get("title") or {}).get("rendered") or ""
            name = _player_name_from_title(title)
            if not name:
                continue
            for k in _name_keys(name):
                mapping.setdefault(k, slug)
        if len(rows) < 100:
            break
        page += 1

    # 同一人物に OB page と現役 staff page が併存する場合、WP の取得順で
    # setdefault すると古い slug を選ぶことがある。現行 data-site が使う
    # hand-authored canonical slug を最後に優先する。
    for name, slug in _PLAYER_SLUG_MAP.items():
        if slug in available_slugs:
            mapping[_norm(name)] = slug
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
