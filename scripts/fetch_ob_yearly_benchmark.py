#!/usr/bin/env python3
"""OB の年度別成績を my-favorite-giants.net(ベンチマーク)から抽出する。

user 指示(2026-06-04): 年度別データの源はベンチマークサイト(スクレイピングOK)。
- 全選手が config/giants_all_players_roster.json の ``rival_slug`` で直接引ける
  (例 'player1/egawa-suguru.htm')。 Wikipedia で漏れる助っ人外国人も網羅。
- ベンチマークは 打撃【1軍】(OPS/出塁率/長打率…) / 投手【1軍】(防御率/WHIP…) を持つ。
  本 script は **1軍 の年度別+計** を renderer 互換の npb_career 形式で出力する。
- 事実のみ(数字)を取得。 体系的全量取得につき低レート(0.7s/req)+ UA 明示。
- 事実誤認NG: テーブルが無い/壊れている選手は skip(空で埋めない)。

使い方:
  python3 scripts/fetch_ob_yearly_benchmark.py --slugs player1/egawa-suguru.htm
  python3 scripts/fetch_ob_yearly_benchmark.py --names 長嶋茂雄 別所毅彦 --dump
  python3 scripts/fetch_ob_yearly_benchmark.py --build
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.my-favorite-giants.net/giants_data/player/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 出力する打撃列(ベンチマーク header の正規化名 → そのまま採用。 詳しさ重視)。
BAT_OUT = [
    "年度", "所属", "試合", "打席", "打数", "得点", "安打", "二塁打", "三塁打",
    "本塁打", "塁打", "打点", "盗塁", "盗塁刺", "犠打", "犠飛", "四球", "死球",
    "三振", "併殺打", "打率", "出塁率", "長打率", "OPS",
]
# 投手列。
PIT_OUT = [
    "年度", "所属", "登板", "完投", "勝利", "敗北", "セーブ", "ホールド", "勝率",
    "打者", "投球回", "被安打", "被本塁打", "与四球", "奪三振", "失点", "自責点",
    "防御率", "被打率", "WHIP",
]
# ベンチマーク header(空白除去)→ 出力列名の別名吸収。
HEADER_NORM = {
    "セ｜ブ": "セーブ", "ホ｜ルド": "ホールド", "打者数": "打者",
    "被安打": "被安打", "与四球": "与四球", "与死球": "与死球",
}


def _norm(s: str) -> str:
    return s.replace(" ", "").replace("　", "")


def _fetch(slug: str, timeout: float = 20.0) -> Optional[str]:
    url = BASE + slug.lstrip("/")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def _cells(tr: str) -> list[str]:
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S):
        t = html.unescape(re.sub(r"<[^>]+>", " ", c))
        out.append(re.sub(r"\s+", " ", t).strip())
    return out


def _tables(htmltext: str) -> list[str]:
    return re.findall(r"<table[^>]*>(.*?)</table>", htmltext, re.S)


def _is_year(s: str) -> bool:
    return bool(re.match(r"^\s*(19|20)\d{2}\s*$", (s or "").replace(" ", "")))


def _parse(table: str, out_cols: list[str], signature: str) -> Optional[dict]:
    rows = [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)]
    rows = [r for r in rows if r]
    if not rows:
        return None
    header = [HEADER_NORM.get(_norm(c), _norm(c)) for c in rows[0]]
    if signature not in header:
        return None
    hmap = {h: i for i, h in enumerate(header)}

    def pick(cells: list[str], year: str, team: str) -> dict:
        row = {c: "" for c in out_cols}
        row["年度"] = year
        row["所属"] = team
        for col in out_cols:
            if col in ("年度", "所属"):
                continue
            idx = hmap.get(col)
            if idx is not None and idx < len(cells):
                row[col] = _norm(cells[idx])
        return row

    years, total = [], None
    for cs in rows[1:]:
        c0 = _norm(cs[0]) if cs else ""
        team = cs[1].strip() if len(cs) > 1 else ""
        if _is_year(cs[0]):
            years.append(pick(cs, c0, team))
        elif c0 == "計" or (len(cs) > 1 and _norm(cs[1]) == "計"):
            total = pick(cs, "通算", "")
    if not years and not total:
        return None
    return {"columns": out_cols, "years": years, "total": total}


def extract(slug: str) -> Optional[dict]:
    htmltext = _fetch(slug)
    if not htmltext:
        return None
    bat = pit = None
    for tbl in _tables(htmltext):
        head = _norm(" ".join(_cells(tbl)[:40]))
        if pit is None and "防御率" in head:
            pit = _parse(tbl, PIT_OUT, "防御率")
        if bat is None and ("OPS" in head or "出塁率" in head) and "打率" in head:
            bat = _parse(tbl, BAT_OUT, "打率")
        if bat and pit:
            break
    if not bat and not pit:
        return None
    bat_y = len(bat["years"]) if bat else 0
    pit_y = len(pit["years"]) if pit else 0
    return {
        "is_pitcher": pit_y > 0 and pit_y >= bat_y,
        "batting": bat,
        "pitching": pit,
        "source_url": BASE + slug.lstrip("/"),
    }


def _roster() -> list[dict]:
    return json.loads((ROOT / "config" / "giants_all_players_roster.json").read_text(encoding="utf-8"))["players"]


def _slug_for(name: str) -> Optional[str]:
    for p in _roster():
        if p["name"].replace(" ", "") == name.replace(" ", ""):
            return p["rival_slug"]
    return None


def _summ(label: str, e: Optional[dict]) -> str:
    if not e:
        return f"  MISS {label}"
    blk = e["pitching"] if e["is_pitcher"] else e["batting"]
    n = len(blk["years"]) if blk else 0
    return f"  OK  {label} (is_pitcher={e['is_pitcher']}) {n}年 列{len(blk['columns']) if blk else 0} total={'有' if blk and blk['total'] else '無'}"


def _build() -> int:
    roster = _roster()
    targets = [p for p in roster if p.get("year_end") and p["year_end"] <= 2024]
    cache_path = ROOT / ".ob_bench_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    print(f"benchmark targets: {len(targets)} (cache {len(cache)})")
    done = hit = miss = 0
    for p in targets:
        slug = p["rival_slug"]
        if cache.get(slug, "__a__") != "__a__":
            done += 1
            continue
        e = extract(slug)
        time.sleep(0.7)
        done += 1
        if e:
            e["display_name"] = p["name"]
            e["slug"] = slug.rsplit("/", 1)[-1].replace(".htm", "")
            cache[slug] = e
            hit += 1
        else:
            cache[slug] = None
            miss += 1
        if done % 25 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  {done}/{len(targets)} hit={hit} miss={miss}")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    out = {v["slug"]: v for v in cache.values() if v}
    out_path = ROOT / "config" / "ob_career_yearly_full.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nDONE: {len(out)} players -> {out_path} (hit={hit} miss={miss})")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--build" in args:
        return _build()
    if "--slugs" in args:
        for slug in args[args.index("--slugs") + 1:]:
            print(_summ(slug, extract(slug)))
            time.sleep(0.7)
        return 0
    if "--names" in args:
        names = [a for a in args[args.index("--names") + 1:] if not a.startswith("--")]
        for name in names:
            slug = _slug_for(name)
            if not slug:
                print(f"  ?? {name}: roster に slug なし")
                continue
            e = extract(slug)
            print(_summ(name, e))
            if e and "--dump" in args:
                blk = e["pitching"] if e["is_pitcher"] else e["batting"]
                if blk and blk["years"]:
                    print("   cols :", blk["columns"])
                    print("   first:", json.dumps(blk["years"][0], ensure_ascii=False))
                    print("   total:", json.dumps(blk["total"], ensure_ascii=False))
            time.sleep(0.7)
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
