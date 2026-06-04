#!/usr/bin/env python3
"""ob_legends_full.json に、 年度別データ (benchmark) はあるが名鑑未収録の在籍選手
(助っ人外国人含む) を追加する。

背景: 旧 Wikipedia 由来の ob_legends_full.json は助っ人を取れず684名。 一方
ob_career_yearly_full.json (benchmark) は助っ人137名含む866名の年度別+通算を持つ。
名鑑 (load_ob_names→個別ページ生成 / load_ob_legend_entries→名鑑表示) を benchmark
網羅に合わせ、 助っ人も個別ページ生成 + 名鑑掲載されるようにする。

通算 npb は benchmark の通算行から派生 (打者 試合/打率/安打/本/打点、 投手 登板/勝/防御率/奪三振)。
kana/years は giants_all_players_roster.json から。 honors は付けない (curated のみ)。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGENDS = ROOT / "config" / "ob_legends_full.json"
YEARLY = ROOT / "config" / "ob_career_yearly_full.json"
ROSTER = ROOT / "config" / "giants_all_players_roster.json"


def _norm(name: str) -> str:
    return (name or "").replace(" ", "").replace("　", "").strip()


def _npb_from_total(v: dict) -> dict:
    blk = (v.get("pitching") if v.get("is_pitcher") else v.get("batting")) or {}
    t = blk.get("total") or {}
    def n(x):
        s = str(t.get(x, "")).replace(",", "")
        try:
            return int(s)
        except Exception:
            return None
    if v.get("is_pitcher"):
        out = {"games": n("登板"), "w": n("勝利"), "era": t.get("防御率") or None, "k": n("奪三振")}
    else:
        out = {"games": n("試合"), "avg": t.get("打率") or None, "hits": n("安打"),
               "hr": n("本塁打"), "rbi": n("打点")}
    return {k: val for k, val in out.items() if val not in (None, "")}


def main() -> int:
    legends = json.loads(LEGENDS.read_text(encoding="utf-8"))
    yearly = json.loads(YEARLY.read_text(encoding="utf-8"))
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))["players"]

    have_slugs = {e.get("slug") for e in legends["stats"].values() if e.get("slug")}
    rmeta = {}
    for p in roster:
        slug = (p.get("rival_slug") or "").rsplit("/", 1)[-1].replace(".htm", "")
        if slug:
            ys, ye = p.get("year_start"), p.get("year_end")
            rmeta[slug] = {"kana": p.get("kana") or "",
                           "years": (f"{ys}-{ye}" if ye else (f"{ys}-" if ys else "")),
                           "name": p.get("name") or ""}

    added = 0
    for slug, v in yearly.items():
        if slug in have_slugs:
            continue
        npb = _npb_from_total(v)
        if not npb:
            continue
        m = rmeta.get(slug, {})
        name = v.get("display_name") or m.get("name") or slug
        key = _norm(name)
        if key in legends["stats"]:
            continue
        legends["stats"][key] = {
            "slug": slug,
            "type": "pitcher" if v.get("is_pitcher") else "batter",
            "years": m.get("years", ""),
            "teams": "読売ジャイアンツ",
            "npb": npb,
            "kana": m.get("kana", ""),
            "display_name": name,
        }
        legends["order"].append(name)
        have_slugs.add(slug)
        added += 1

    legends["_note"] = (legends.get("_note", "") +
                        " / 助っ人含む benchmark 網羅を augment (augment_ob_legends_foreign)")
    LEGENDS.write_text(json.dumps(legends, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"added {added} players -> stats={len(legends['stats'])} order={len(legends['order'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
