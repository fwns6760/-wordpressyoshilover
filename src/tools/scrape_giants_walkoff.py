"""巨人サヨナラ本塁打データ scraper（config/giants_walkoff_homerun.json を生成）。

ソース: my-favorite-giants.net/giants_data/walkoff_homerun.htm。
事実テーブルのみ抽出。HTML/文章はコピーしない。OUR テンプレ
(data_site_template_walkoff.py)でレンダリングする。

main table(13列): # / 選手名 / 回数 / 試合日 / 対戦相手 / 試合 / 球場 / 種別 /
本塁打前スコア / 本塁打後スコア / 延長回 / 相手投手 / 備考。
先頭の記録テーブルからチーム通算最多/シーズン最多等も拾う。

usage:
    python3 -m src.tools.scrape_giants_walkoff          # config 上書き
    python3 -m src.tools.scrape_giants_walkoff --dry
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

_URL = "https://www.my-favorite-giants.net/giants_data/walkoff_homerun.htm"
_UA = "yoshilover-fetcher (+https://yoshilover.com)"
_OUT = os.path.join(os.path.dirname(__file__), "..", "..", "config", "giants_walkoff_homerun.json")

_TABLE_RE = re.compile(r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)


def _decode(raw: bytes) -> str:
    for enc in ("cp932", "shift_jis", "utf-8", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean(frag: str) -> str:
    import html as _h
    s = _h.unescape(re.sub(r"<[^>]+>", " ", frag or ""))
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def _cells(row: str) -> list:
    return [_clean(m.group(1)) for m in _CELL_RE.finditer(row)]


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _decode(resp.read())


_KEYS = ["no", "player", "count", "date", "opponent", "game_no", "stadium",
         "type", "score_before", "score_after", "extra_inning", "pitcher", "note"]


def parse(html: str) -> dict:
    tables = _TABLE_RE.findall(html)
    homeruns: list[dict] = []
    records: list[dict] = []
    for t in tables:
        rows = [_cells(r) for r in _ROW_RE.findall(t)]
        rows = [r for r in rows if r]
        # main table: 13 列、 1 列目が連番(数字) の data 行を採用
        data = [r for r in rows if len(r) == 13 and r[0].isdigit()]
        if len(data) > 50:
            for r in data:
                homeruns.append({k: r[i] for i, k in enumerate(_KEYS)})
            continue
        # records table: 「最多」を含む行を best-effort で拾う
        for r in rows:
            joined = " ".join(r)
            if "最多" in joined and len(r) >= 3:
                records.append({"category": r[0], "player": r[1], "value": r[2],
                                "note": r[3] if len(r) > 3 else ""})
    return {"records": records, "homeruns": homeruns}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dry = "--dry" in argv
    parsed = parse(_fetch(_URL))
    out = {
        "_source": "my-favorite-giants.net/giants_data/walkoff_homerun.htm（事実データのみ参照）",
        "records": parsed["records"],
        "homeruns": parsed["homeruns"],
        "total": len(parsed["homeruns"]),
    }
    print(f"parsed: homeruns={len(out['homeruns'])} records={len(out['records'])}")
    if out["homeruns"]:
        print("first:", json.dumps(out["homeruns"][0], ensure_ascii=False))
        print("last :", json.dumps(out["homeruns"][-1], ensure_ascii=False))
    if dry:
        print("[dry] no write")
        return 0
    with open(_OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"[write] {os.path.abspath(_OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
