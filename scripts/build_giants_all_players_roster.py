#!/usr/bin/env python3
"""Tier 0 — 巨人 歴代全選手 名簿ビルダー(網羅ターゲットの正本)。

target set = ライバル `my-favorite-giants.net` の歴代在籍選手一覧(user 確定 2026-06-03)。
このスクリプトはライバル一覧の **名前リスト(事実)のみ** を抽出して網羅ターゲットを定義する。
career 本体データはライバルから取らない(Wikipedia / NPB を別途使う)。

入力: allplayer.htm(五十音一括ページ) の保存 HTML
出力: config/giants_all_players_roster.json
  各 entry: {name, kana, rival_slug, romaji, years_raw, year_start, year_end, marks}

使い方:
  curl -s -A "yoshilover-research" \
    https://www.my-favorite-giants.net/giants_data/player/allplayer.htm > /tmp/allp.html
  python3 scripts/build_giants_all_players_roster.py /tmp/allp.html
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROW_RE = re.compile(
    r'<a href="((?:\.\./)?player[0-9]*/([a-z0-9_-]+)\.htm)">([^<]+)</a>([#*]*)\s*'
    r'</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>',
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"(\d{4})")


def _clean(s: str) -> str:
    return s.replace("　", " ").strip()


def parse(html: str) -> list[dict]:
    out: dict[str, dict] = {}
    for href, romaji, name, marks, kana, years in ROW_RE.findall(html):
        years_raw = _clean(years)
        yrs = YEAR_RE.findall(years_raw)
        # 末尾が「－」(在籍中・終了年なし)なら year_end=None。
        # 例 '2006H①－' は year_start=2006 / year_end=None(現役)。閉じた範囲のみ end を持つ。
        ongoing = bool(re.search(r"[－\-]\s*$", years_raw))
        year_start = int(yrs[0]) if yrs else None
        if ongoing:
            year_end = None
        else:
            year_end = int(yrs[-1]) if len(yrs) >= 2 else (int(yrs[0]) if yrs else None)
        entry = {
            "name": _clean(name),
            "kana": _clean(kana),
            "rival_slug": href.lstrip("./"),
            "romaji": romaji,
            "years_raw": years_raw,
            "year_start": year_start,
            "year_end": year_end,
            "marks": marks,  # '#'=一軍主力級 等の凡例記号(ライバル定義)
        }
        out[romaji] = entry  # romaji slug を一意キーに
    return sorted(out.values(), key=lambda e: (e["kana"] or e["romaji"]))


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/allp.html")
    html = src.read_text(encoding="utf-8", errors="replace")
    players = parse(html)
    if not players:
        print("ERROR: 0 players parsed — HTML 構造が変わった可能性", file=sys.stderr)
        return 1
    active = [p for p in players if (p["year_end"] or 0) >= 2024]
    out_path = Path(__file__).resolve().parents[1] / "config" / "giants_all_players_roster.json"
    payload = {
        "_meta": {
            "source": "my-favorite-giants.net/giants_data/player/allplayer.htm",
            "purpose": "Tier0 網羅ターゲット定義(巨人個人データNo.1)。career本体はWikipedia/NPB。",
            "total": len(players),
            "active_2024plus": len(active),
        },
        "players": players,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(players)} players -> {out_path}")
    print(f"  現役級(2024+在籍): {len(active)}  / OBギャップ目安: {len(players) - len(active)}")
    print("  sample:", ", ".join(p["name"] for p in players[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
