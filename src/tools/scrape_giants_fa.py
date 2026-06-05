"""巨人FAデータ scraper（config/giants_fa.json を生成）。

ソース: my-favorite-giants.net/giants_data/player/ の fa.htm（FA獲得選手）/ fa-right.htm（FA有資格選手）。
事実テーブルのみ抽出。HTML/文章はコピーしない。OUR テンプレ（data_site_template_fa.py）でレンダリング。

usage:
    python3 -m src.tools.scrape_giants_fa            # config/giants_fa.json を上書き
    python3 -m src.tools.scrape_giants_fa --dry      # 件数だけ表示
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

BASE = "https://www.my-favorite-giants.net/giants_data/player/"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "config", "giants_fa.json")

_WS = re.compile(r"[\s　]+")
_GROUP = re.compile(r"【(.+?)】")


def _norm_name(s: str) -> str:
    return _WS.sub("", (s or "").strip())


def _txt(s: str) -> str:
    return _WS.sub(" ", (s or "").strip()).strip()


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


def scrape_fa_acquisitions() -> list[dict]:
    rows = _fetch_big_table("fa.htm")
    out = []
    for c in rows:
        if len(c) < 7 or "選手名" in "".join(c) or "FA年" in "".join(c):
            continue
        name = _norm_name(c[3])
        if not name:
            continue
        out.append({
            "fa_year": _txt(c[0]),
            "join_year": _txt(c[1]),
            "name": name,
            "pos": _txt(c[4]),
            "prev_team": _txt(c[5]),
            "period": _txt(c[6]),
            "titles": _txt(c[-1]),
        })
    return out


def scrape_fa_eligible() -> dict:
    rows = _fetch_big_table("fa-right.htm")
    asof = ""
    players, cur_group = [], ""
    for c in rows:
        joined = "".join(c)
        if not asof:
            m = re.search(r"(\d{4})年", joined)
            if m:
                asof = m.group(1)
        g = _GROUP.search(joined)
        if g and len(_txt(joined)) <= 8:
            cur_group = g.group(1)
            continue
        if "選手名" in joined or "背" in c[0]:
            continue
        if len(c) < 7:
            continue
        name = _norm_name(c[2])
        if not name:
            continue
        players.append({
            "group": cur_group,
            "back_no": _txt(c[0]),
            "name": name,
            "age": _txt(c[3]),
            "tenure_years": _txt(c[4]),
            "right_type": _txt(c[5]),
            "status": _txt(c[6]),
            "note": _txt(c[-1]),
        })
    return {"asof": asof, "players": players}


def build() -> dict:
    elig = scrape_fa_eligible()
    return {
        "_schema": {
            "note": "巨人FAデータ正本。出典=公開資料の事実テーブルのみ抽出。HTML/文章はコピーしない。"
                    "FA有資格選手は出典の最新スナップショット（asof 年を併記）。",
            "source": "https://www.my-favorite-giants.net/giants_data/player/fa.htm / fa-right.htm",
            "generator": "src/tools/scrape_giants_fa.py",
        },
        "updated": "2026-06-05",
        "fa_eligible_asof": elig["asof"],
        "fa_acquisitions": scrape_fa_acquisitions(),
        "fa_eligible": elig["players"],
    }


def main() -> int:
    data = build()
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    print("counts:", json.dumps(counts, ensure_ascii=False), "asof:", data.get("fa_eligible_asof"))
    if "--dry" in sys.argv[1:]:
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("wrote", os.path.abspath(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
