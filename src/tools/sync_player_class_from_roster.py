"""giants_roster.json の登録ポジションを data_site_player_class.json へ同期する。

背景
----
``config/data_site_player_class.json`` は data-site の登録ポジション分類
(支配下/育成 × 投手/捕手/内野手/外野手)の正本だが、自動供給経路が無く、
新加入選手を手で追記しないと Cluster ページ等に出ない (stale 化する) という穴
があった。本ツールは ``config/giants_roster.json`` (NPB live + expand_roster_from_npb
+ 手動が混ざる名簿正本) を権威に、player_class へ **未登録選手を追加するだけ** で
この穴を塞ぐ。

安全契約
--------
- 既存エントリは一切変更/削除/再分類しない (追加のみ)。
- 追加するのは position が 投手/捕手/内野手/外野手 に明確に対応する選手のみ。
- position が ``打者`` / 空 (育成は NPB 名簿に position が無い) / 不明 の現役選手は
  推測で内野/外野へ振り分けず、``unresolved`` として報告するだけ。
- 既に player_class に居る選手は canonical 名 または alias の正規化一致で除外
  (例: ``Ｆ．ウィットリー`` は alias ``ウィットリー`` が既登録なので二重追加しない)。
- 二度走らせても差分ゼロ (idempotent)。
- LLM 不使用。書き込む名前は必ず giants_roster.json 内の literal。

usage:
    python3 -m src.tools.sync_player_class_from_roster --check          # 報告のみ (drift あれば exit 1)
    python3 -m src.tools.sync_player_class_from_roster --write          # 反映
    python3 -m src.tools.sync_player_class_from_roster --write --updated 2026-06-18
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
ROSTER_PATH = ROOT / "config" / "giants_roster.json"
CLASS_PATH = ROOT / "config" / "data_site_player_class.json"

# giants_roster.json の position 値 -> player_class のポジション bucket
_POSITION_MAP = {
    "投手": "投手",
    "捕手": "捕手",
    "内野手": "内野手",
    "外野手": "外野手",
}
# role -> player_class の group
_ROLE_GROUP = {
    "player": "shihai",
    "ikusei": "ikusei",
}
_GROUPS = ("shihai", "ikusei")
_POSITIONS = ("投手", "捕手", "内野手", "外野手")


def _norm(name: str) -> str:
    """data_site_query._norm_name と同じ正規化 (空白除去 + 先頭 * 除去)。"""
    return (name or "").replace(" ", "").replace("　", "").lstrip("*").strip()


def _dump(obj: Dict[str, Any]) -> str:
    """data_site_player_class.json の既存整形 (object=indent2 / leaf array=inline) を
    バイト一致で再現する。標準 ``json.dumps(indent=2)`` は配列を縦展開して全行が
    差分化するため使わない。末尾改行 1 つ付き。"""
    lines = ["{"]
    items = list(obj.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if isinstance(v, dict):
            lines.append(f"  {json.dumps(k, ensure_ascii=False)}: {{")
            sub = list(v.items())
            for j, (sk, sv) in enumerate(sub):
                scomma = "," if j < len(sub) - 1 else ""
                lines.append(f"    {json.dumps(sk, ensure_ascii=False)}: {json.dumps(sv, ensure_ascii=False)}{scomma}")
            lines.append(f"  }}{comma}")
        else:
            lines.append(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _is_active(entry: Dict[str, Any]) -> bool:
    return bool(entry.get("active", True))


def _existing_names(player_class: Dict[str, Any]) -> set:
    names = set()
    for group in _GROUPS:
        bucket = player_class.get(group, {})
        for pos in _POSITIONS:
            for n in bucket.get(pos, []):
                names.add(_norm(n))
    return names


def plan(
    roster: List[Dict[str, Any]],
    player_class: Dict[str, Any],
) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    """Return (additions, unresolved).

    additions: list of (canonical_name, group, position)
    unresolved: list of (canonical_name, reason) — 現役だが position 不明で手動要
    """
    existing = _existing_names(player_class)
    additions: List[Tuple[str, str, str]] = []
    unresolved: List[Tuple[str, str]] = []
    seen_new: set = set()

    for entry in roster:
        role = entry.get("role", "")
        group = _ROLE_GROUP.get(role)
        if group is None:
            continue  # manager / coach / shihaikako 等は分類対象外
        if not _is_active(entry):
            continue
        canonical = _norm(str(entry.get("name") or ""))
        if not canonical:
            continue
        # 既存判定: canonical または alias のいずれかが既に分類済みなら skip
        aliases = [canonical] + [_norm(a) for a in (entry.get("aliases") or [])]
        if any(a in existing for a in aliases):
            continue
        if canonical in seen_new:
            continue
        seen_new.add(canonical)

        position = _POSITION_MAP.get(str(entry.get("position") or "").strip())
        if position is None:
            unresolved.append((canonical, f"position='{entry.get('position') or ''}' (内野/外野 不明)"))
            continue
        additions.append((canonical, group, position))

    return additions, unresolved


def apply_additions(
    player_class: Dict[str, Any],
    additions: List[Tuple[str, str, str]],
    updated: str | None = None,
) -> None:
    for canonical, group, position in additions:
        player_class.setdefault(group, {}).setdefault(position, []).append(canonical)
    if updated:
        player_class["_updated"] = updated


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="報告のみ。drift があれば exit 1")
    mode.add_argument("--write", action="store_true", help="player_class.json へ反映")
    ap.add_argument("--updated", default=None, help="書き込み時に _updated を更新 (YYYY-MM-DD)")
    args = ap.parse_args(argv)

    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    player_class = json.loads(CLASS_PATH.read_text(encoding="utf-8"))

    additions, unresolved = plan(roster, player_class)

    if additions:
        print(f"[additions] {len(additions)} 名を分類追加可能:")
        for canonical, group, position in additions:
            print(f"  + {canonical}  ->  {group}.{position}")
    else:
        print("[additions] なし (player_class は名簿に追従済み)")

    if unresolved:
        print(f"[unresolved] {len(unresolved)} 名は position 不明 → 手動分類が必要:")
        for canonical, reason in unresolved:
            print(f"  ? {canonical}  ({reason})")

    if args.check:
        # drift = 追加可能 or 未解決の現役がある状態
        return 1 if (additions or unresolved) else 0

    if not additions:
        print("[write] 変更なし。")
        return 0

    apply_additions(player_class, additions, updated=args.updated)
    CLASS_PATH.write_text(_dump(player_class), encoding="utf-8")
    print(f"[write] {len(additions)} 名を追加して {CLASS_PATH.name} を更新した。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
