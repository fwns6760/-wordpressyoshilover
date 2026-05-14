"""Tests for config/giants_roster.json data quality (343 dedupe regression guard).

duplicate base name 0 / role-position 整合 / aliases 完備 / canonical 解決
の回帰防止。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.analysis import insight_etl


ROSTER_PATH = Path(__file__).resolve().parents[1] / "config" / "giants_roster.json"


def _base_key(name: str) -> str:
    return (name or "").replace(" ", "").replace("　", "").replace("*", "").strip()


def test_roster_loads_as_list():
    """JSON valid + list 型。"""
    data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0


def test_no_duplicate_base_names():
    """同一 base name (空白 / asterisk 除去後 一致) が複数 entry にまたがらないこと。

    2026-05-14 dedupe (343-INSIGHT-007 followup) で 29 group を統合。
    再 pollute 防止。
    """
    data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    groups: dict[str, list[str]] = {}
    for entry in data:
        key = _base_key(entry.get("name") or "")
        if not key:
            continue
        groups.setdefault(key, []).append(entry.get("name"))
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    assert duplicates == {}, f"duplicate base names found: {duplicates}"


def test_norimoto_kodai_position_is_pitcher():
    """則本昂大 は投手 (343 で dedupe 時に index 62 の position=打者 を修正)。

    regression 防止: data entry error が再混入しないこと。
    """
    data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    norimoto = next((e for e in data if _base_key(e.get("name") or "") == "則本昂大"), None)
    assert norimoto is not None
    assert norimoto.get("position") == "投手", \
        f"則本昂大 position should be 投手, got {norimoto.get('position')!r}"
    assert norimoto.get("role") == "player"


def test_load_roster_aliases_resolves_norimoto_variants():
    """則本 surname + 各 alias variant が全部「則本昂大」に resolve できること。"""
    aliases = insight_etl._load_roster_aliases()
    for variant in ("則本", "則本昂大", "則本 昂大", "*則本 昂大"):
        assert insight_etl.resolve_canonical(variant, aliases) == "則本昂大", \
            f"{variant!r} should resolve to 則本昂大"


def test_all_entries_have_canonical_name():
    """name が空 / null の entry がないこと。"""
    data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    bad = [e for e in data if not (e.get("name") or "").strip()]
    assert bad == [], f"entries with missing name: {bad}"


def test_aliases_include_canonical_name():
    """各 entry の aliases に name 自身が含まれること (resolve_canonical の前提)。"""
    data = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    missing: list[str] = []
    for entry in data:
        name = (entry.get("name") or "").strip()
        aliases = entry.get("aliases") or []
        if name and name not in aliases:
            missing.append(name)
    assert missing == [], f"entries with name not in aliases: {missing}"
