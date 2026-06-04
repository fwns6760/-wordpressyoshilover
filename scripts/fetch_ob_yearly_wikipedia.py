#!/usr/bin/env python3
"""OB の「年度別成績」を ja.wikipedia から npb_career 形式で抽出する。

背景:
- ``fetch_ob_career_wikipedia.py`` は **通算行のみ** を取る (thin な OB ページの素)。
- 本 script は **全年度行 + 通算行** を、 renderer (``_build_career_history_html``)
  が期待する npb_career 形式 ``{is_pitcher, batting:{columns,years,total}, pitching:{...}}``
  で出力する。 これにより OB ページがベンチマーク (my-favorite-giants) 級の
  年度別フル表 (23-24列) になる。
- 列スキーマは ``npb_career_scraper`` の BATTING_COLUMNS / PITCHING_COLUMNS に合わせ、
  現役 (NPB公式由来) と OB (Wikipedia由来) で表の見た目を完全統一する。
- 事実誤認NG: 年度別表が取れない/曖昧な選手は skip (空欄で埋めない)。

使い方:
  python3 scripts/fetch_ob_yearly_wikipedia.py --names 別所毅彦 青田昇 千葉茂   # 実証
  python3 scripts/fetch_ob_yearly_wikipedia.py --build                          # 全OB batch
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.npb_career_scraper import BATTING_COLUMNS, PITCHING_COLUMNS  # noqa: E402

API = "https://ja.wikipedia.org/w/api.php"
UA = "yoshilover-research (+https://yoshilover.com; OB yearly coverage)"

# Wikipedia 年度別表のヘッダ表記 -> npb_career 標準列名(差異吸収)。
HEADER_ALIASES = {
    "球団": "所属球団", "チーム": "所属球団", "所属": "所属球団",
    "勝": "勝利", "敗": "敗北", "S": "セーブ", "防御率": "防御率",
    "本": "本塁打", "点": "打点",
}


def _api_parse_html(title: str, timeout: float = 15.0) -> Optional[str]:
    q = urllib.parse.urlencode(
        {"action": "parse", "page": title, "prop": "text", "format": "json", "redirects": "1", "disabletoc": "1"}
    )
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if "error" in data:
        return None
    return (((data.get("parse") or {}).get("text") or {}).get("*")) or None


def _cell_text(inner: str) -> str:
    txt = html.unescape(re.sub(r"<[^>]+>", " ", inner))
    return re.sub(r"\s+", " ", txt).strip()


def _tables(htmltext: str) -> list[str]:
    return re.findall(r"<table[^>]*>(.*?)</table>", htmltext, re.S)


def _rows(table: str) -> list[list[str]]:
    """rowspan / colspan を展開した 2D グリッドを返す。

    Wikipedia の年度別表は同一球団の連続年を rowspan で結合し、 通算行は
    年度+球団を colspan で結合する。 展開せず <td> を素朴に数えると継続行・
    通算行で列がずれて **事実誤認** になるため、 ここでグリッド化して全行を
    ヘッダと同じ列数に揃える。
    """
    tr_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
    grid: list[dict] = []
    carry: dict[int, list] = {}  # col_index -> [text, remaining_rowspan]
    width = 0
    for tr in tr_blocks:
        raw_cells = re.findall(r"<(t[dh])([^>]*)>(.*?)</\1>", tr, re.S)
        row: dict[int, str] = {}
        col = 0
        ci = 0
        while ci < len(raw_cells) or col in carry:
            if col in carry:  # 上の行から rowspan で降りてきたセル
                text, rem = carry[col]
                row[col] = text
                if rem - 1 <= 0:
                    del carry[col]
                else:
                    carry[col] = [text, rem - 1]
                col += 1
                continue
            _, attrs, inner = raw_cells[ci]
            ci += 1
            text = _cell_text(inner)
            rs = int((re.search(r'rowspan="?(\d+)', attrs) or [0, 1])[1]) if "rowspan" in attrs else 1
            cs = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1]) if "colspan" in attrs else 1
            for _k in range(cs):
                row[col] = text
                if rs > 1:
                    carry[col] = [text, rs - 1]
                col += 1
        width = max(width, col)
        grid.append(row)
    return [[r.get(i, "") for i in range(width)] for r in grid]


def _norm_header(cells: list[str]) -> list[str]:
    out = []
    for c in cells:
        h = c.replace(" ", "").replace("　", "")
        out.append(HEADER_ALIASES.get(h, h))
    return out


def _is_year(cell: str) -> Optional[str]:
    m = re.match(r"^\s*(\d{4})", cell or "")
    return m.group(1) if m else None


def _zip_to_schema(header: list[str], cells: list[str], columns: list[str], year: str, team: str) -> dict:
    """Wikipedia の (header, cells) を npb_career 標準 columns の dict に詰め替える。"""
    hmap = {h: i for i, h in enumerate(header)}
    row = {c: "" for c in columns}
    row["年度"] = year
    row["所属球団"] = team
    for col in columns:
        if col in ("年度", "所属球団"):
            continue
        idx = hmap.get(col)
        if idx is not None and idx < len(cells):
            row[col] = cells[idx].replace(" ", "")
    return row


def _parse_table(table: str, kind: str) -> Optional[dict]:
    """1 つの年度別表を npb_career の 1 stat block に。 kind='bat'|'pitch'。"""
    columns = PITCHING_COLUMNS if kind == "pitch" else BATTING_COLUMNS
    signature = "防御率" if kind == "pitch" else "出塁率"
    rows = _rows(table)
    # header = signature を含む最初の行
    header = None
    h_idx = -1
    for i, cs in enumerate(rows):
        nh = _norm_header(cs)
        if signature in nh:
            header, h_idx = nh, i
            break
    if header is None:
        return None
    years: list[dict] = []
    total = None
    for cs in rows[h_idx + 1:]:
        if not cs:
            continue
        c0 = (cs[0] or "").replace(" ", "")
        y = _is_year(cs[0])
        if y:
            team = cs[1].replace(" ", "") if len(cs) > 1 else ""
            years.append(_zip_to_schema(header, cs, columns, y, team))
        elif c0.startswith("通算") or c0.startswith("NPB"):
            total = _zip_to_schema(header, cs, columns, "通算", "")
    if not years and not total:
        return None
    return {"kind": kind, "columns": columns, "years": years, "total": total}


def _wiki_title(name: str) -> str:
    t = re.sub(r"[（(][^）)]*[）)]", "", name)
    return t.replace(" ", "").replace("　", "").strip()


def extract_yearly(name: str) -> Optional[dict]:
    """name -> npb_career 形式 {is_pitcher, batting, pitching, source_url} または None。"""
    title = _wiki_title(name)
    htmltext = _api_parse_html(title)
    if not htmltext or "年度別成績" not in htmltext:
        for suffix in ("(プロ野球選手)", "(野球)", "(野球選手)"):
            alt = _api_parse_html(f"{title} {suffix}")
            if alt and "年度別成績" in alt:
                htmltext = alt
                break
    if not htmltext:
        return None
    batting = pitching = None
    for tbl in _tables(htmltext):
        if pitching is None and "防御率" in tbl:
            pitching = _parse_table(tbl, "pitch")
        if batting is None and "出塁率" in tbl:
            batting = _parse_table(tbl, "bat")
    if not batting and not pitching:
        return None
    pit_years = len(pitching["years"]) if pitching else 0
    bat_years = len(batting["years"]) if batting else 0
    is_pitcher = pit_years > 0 and pit_years >= bat_years
    out = {
        "is_pitcher": is_pitcher,
        "batting": batting,
        "pitching": pitching,
        "source_url": f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(title)}",
    }
    return out


def _summarize(name: str, e: Optional[dict]) -> str:
    if not e:
        return f"  MISS {name}"
    parts = []
    if e.get("batting"):
        b = e["batting"]
        parts.append(f"打撃 {len(b['years'])}年 列{len(b['columns'])} total={'有' if b['total'] else '無'}")
    if e.get("pitching"):
        p = e["pitching"]
        parts.append(f"投手 {len(p['years'])}年 列{len(p['columns'])} total={'有' if p['total'] else '無'}")
    return f"  OK  {name} (is_pitcher={e['is_pitcher']}) " + " / ".join(parts)


def _norm_key(name: str) -> str:
    return _wiki_title(name)


def _build() -> int:
    """全OB(引退済ロスター)を Wikipedia 年度別抽出 → config/ob_career_yearly_full.json。

    resume-safe(.ob_yearly_cache.json に逐次保存、 再実行で未取得のみ fetch)。
    miss(None)は再試行しない。 事実誤認NG: 取れない選手は載せない。
    """
    roster = json.loads((ROOT / "config" / "giants_all_players_roster.json").read_text(encoding="utf-8"))["players"]
    targets = [p for p in roster if p.get("year_end") and p["year_end"] <= 2024]
    cache_path = ROOT / ".ob_yearly_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    print(f"OB yearly targets: {len(targets)} / roster {len(roster)} (cache {len(cache)})")

    done = hit = miss = 0
    for p in targets:
        key = _norm_key(p["name"])
        if cache.get(key, "__absent__") != "__absent__":
            done += 1
            continue
        e = extract_yearly(p["name"])
        time.sleep(0.5)
        done += 1
        if e:
            e["slug"] = p["rival_slug"].rsplit("/", 1)[-1].replace(".htm", "")
            e["display_name"] = p["name"]
            cache[key] = e
            hit += 1
        else:
            cache[key] = None
            miss += 1
        if done % 25 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  progress {done}/{len(targets)} hit={hit} miss={miss}")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    out = {k: v for k, v in cache.items() if v}
    out_path = ROOT / "config" / "ob_career_yearly_full.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nDONE: yearly={len(out)} / targets {len(targets)} -> {out_path}")
    print(f"  この回: hit={hit} miss={miss}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--build" in args:
        return _build()
    if "--names" in args:
        names = args[args.index("--names") + 1:]
        for name in names:
            e = extract_yearly(name)
            print(_summarize(name, e))
            if e and "--dump" in args:
                blk = e["pitching"] if e["is_pitcher"] else e["batting"]
                if blk and blk["years"]:
                    print("   columns:", blk["columns"])
                    print("   first  :", json.dumps(blk["years"][0], ensure_ascii=False))
                    print("   last   :", json.dumps(blk["years"][-1], ensure_ascii=False))
                    print("   total  :", json.dumps(blk["total"], ensure_ascii=False))
            time.sleep(0.5)
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
