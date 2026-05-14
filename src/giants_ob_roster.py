"""344-INGEST: 元巨人 OB roster loader + lookup.

元巨人 OB 名前 list を `config/giants_ob_roster.json` から load し、
text 内 OB 言及検出を提供する pure 関数。

LLM / AI 不使用、純 Python。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence


_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "giants_ob_roster.json"
)


def load_giants_ob_roster(path: str | Path | None = None) -> list[dict]:
    """JSON file を読んで OB entry list を返す。

    各 entry: {"name": str, "aliases": [str, ...], "era": str, "note": str}
    file 不在 / 不正 JSON で例外。
    """
    target = Path(path) if path else _DEFAULT_CONFIG_PATH
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"giants_ob_roster.json must be a list, got {type(data).__name__}"
        )
    return data


def _ob_alias_index(roster: Sequence[Mapping]) -> list[tuple[str, str]]:
    """全 OB alias を (alias, canonical_name) tuple list 化 (lookup 用)。
    alias 長さ降順 sort で longest match 優先 (短姓「原」が「原監督」「原辰徳」より先に hit しないよう)。"""
    index: list[tuple[str, str]] = []
    for entry in roster:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        aliases = entry.get("aliases") or []
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            alias_s = str(alias or "").strip()
            if alias_s:
                index.append((alias_s, name))
    index.sort(key=lambda x: -len(x[0]))
    return index


def matching_ob_names(text: str, roster: Sequence[Mapping] | None = None) -> list[str]:
    """text 内に含まれる元巨人 OB の canonical name list を返す (重複除去、登場順)。

    短姓 ambiguity ("原" は監督 / OB / 一般単語) を避けるため:
      - 2 文字未満 alias は match しない
      - longest match 優先 (alias index sort で実装)
    """
    if not text:
        return []
    if roster is None:
        roster = load_giants_ob_roster()
    index = _ob_alias_index(roster)
    seen: set[str] = set()
    result: list[str] = []
    for alias, canonical in index:
        if len(alias) < 2:
            continue
        if alias in text and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def is_giants_ob(text: str, roster: Sequence[Mapping] | None = None) -> bool:
    """text 内に元巨人 OB の言及があるか boolean で返す (matching_ob_names の short cut)。"""
    return bool(matching_ob_names(text, roster))
