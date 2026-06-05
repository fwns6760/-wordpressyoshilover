"""巨人トレード/移籍データ scraper（config/giants_trades.json を生成）。

ソース: my-favorite-giants.net/giants_data/trading/ の all.htm（入退団一覧）/ change.htm（交換トレード）。
事実テーブルのみ抽出。HTML/文章はコピーしない。OUR テンプレ（data_site_template_trade.py）でレンダリング。

複数選手セル（"高橋　礼 泉　圭輔" / pos "投手 投手"）は半角空白で分割、選手名内の全角空白は詰める。

usage:
    python3 -m src.tools.scrape_giants_trades            # config/giants_trades.json を上書き
    python3 -m src.tools.scrape_giants_trades --dry
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

BASE = "https://www.my-favorite-giants.net/giants_data/trading/"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "config", "giants_trades.json")

_WS_ALL = re.compile(r"[\s　]+")
# 選手区切りは ASCII 空白のみ（<br>由来）。姓名間の全角空白(　)では分割しない。
_HALF_SPLIT = re.compile(r"[ \t\r\n]+")


def _norm_name(s: str) -> str:
    return _WS_ALL.sub("", (s or "").strip())


def _txt(s: str) -> str:
    return _WS_ALL.sub(" ", (s or "").strip()).strip()


def _players(name_cell: str, pos_cell: str) -> list[dict]:
    names = [n for n in _HALF_SPLIT.split((name_cell or "").strip()) if n.strip()]
    poss = [p for p in _HALF_SPLIT.split((pos_cell or "").strip()) if p.strip()]
    out = []
    for i, n in enumerate(names):
        nm = _norm_name(n)
        if not nm:
            continue
        out.append({"name": nm, "pos": poss[i] if i < len(poss) else ""})
    return out


def _fetch_big_table(page: str):
    r = requests.get(BASE + page, timeout=30)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return []
    big = max(tables, key=lambda t: len(t.find_all("tr")))
    return [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            for tr in big.find_all("tr")]


def _parse(page: str) -> list[dict]:
    rows = _fetch_big_table(page)
    out, season = [], ""
    for c in rows:
        if len(c) < 7:
            # season セクション見出し（年オフ-..）は他セルが空
            head = _txt(c[0]) if c else ""
            if head and ("オフ" in head or re.search(r"\d{4}", head)):
                season = head
            continue
        if "日付" in c[0] or "獲得選手" in "".join(c):
            continue
        date = _txt(c[0])
        rest = "".join(_txt(x) for x in c[1:])
        if date and not rest and ("オフ" in date or re.fullmatch(r"\d{4}年.*", date)):
            season = date
            continue
        in_p = _players(c[1], c[2])
        out_p = _players(c[4], c[5])
        partner = _txt(c[3])
        note = _txt(c[6])
        if not (in_p or out_p):
            continue
        out.append({
            "date": date, "season": season,
            "in_players": in_p, "out_players": out_p,
            "partner": partner, "note": note,
        })
    return out


def build() -> dict:
    return {
        "_schema": {
            "note": "巨人トレード/入退団データ正本。出典=公開資料の事実テーブルのみ抽出。HTML/文章はコピーしない。",
            "source": "https://www.my-favorite-giants.net/giants_data/trading/ (all.htm / change.htm)",
            "generator": "src/tools/scrape_giants_trades.py",
            "fields": "date / season(年オフ区切り) / in_players[{name,pos}] / out_players[{name,pos}] / partner(相手球団) / note(備考=交換/FA移籍/現役ドラフト 等)",
        },
        "updated": "2026-06-05",
        "trades_exchange": _parse("change.htm"),
        "transactions_all": _parse("all.htm"),
    }


def main() -> int:
    data = build()
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    print("counts:", json.dumps(counts, ensure_ascii=False))
    if "--dry" in sys.argv[1:]:
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("wrote", os.path.abspath(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
