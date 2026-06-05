"""巨人ドラフト史データ scraper（config/giants_draft_history.json を生成）。

ソース: my-favorite-giants.net/giants_data/draft/ の各ページ（事実=ドラフト結果）。
出力を OUR テンプレ（src/data_site_template_draft.py）でレンダリングする。HTML/文章はコピーしない。

usage:
    python3 -m src.tools.scrape_giants_draft            # config/giants_draft_history.json を上書き
    python3 -m src.tools.scrape_giants_draft --dry      # 件数だけ表示（書き込まない）
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

BASE = "https://www.my-favorite-giants.net/giants_data/draft/"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "config", "giants_draft_history.json")

_NAME_LEAD = re.compile(r"^\d+\s*")
_WS = re.compile(r"[\s　]+")
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"


def _norm_name(s: str) -> str:
    """先頭の脚注番号を除去し、姓名間の空白を詰める（roster 表記= 空白なし に合わせる）。"""
    s = _NAME_LEAD.sub("", (s or "").strip())
    return _WS.sub("", s)


def _txt(s: str) -> str:
    return _WS.sub(" ", (s or "").strip()).strip()


def _fetch_rows(page: str) -> list[list[str]]:
    r = requests.get(BASE + page, timeout=30)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return []
    big = max(tables, key=lambda t: len(t.find_all("tr")))
    out = []
    for tr in big.find_all("tr"):
        out.append([c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])])
    return out


def _is_header(cells: list[str], *tokens: str) -> bool:
    joined = "".join(cells)
    return any(tok in joined for tok in tokens)


def _year(v: str) -> int | None:
    m = re.search(r"(\d{4})", v or "")
    return int(m.group(1)) if m else None


def _round_label(v: str, prefix: str = "") -> str:
    v = _txt(v)
    m = re.search(r"(\d+)", v)
    return f"{prefix}{m.group(1)}位" if m else (prefix + v if v else "")


def _competitors(v: str) -> list[str]:
    v = _txt(v)
    v = "".join(ch for ch in v if ch not in _CIRCLED)  # 円内数字（競合数）を除去
    parts = re.split(r"[・,、]", v)
    return [p.strip() for p in parts if p.strip()]


def scrape_draft_picks() -> list[dict]:
    rows = _fetch_rows("year.htm")
    out, cur_year = [], None
    for c in rows:
        if len(c) < 6 or _is_header(c, "選手名", "順位"):
            continue
        if _year(c[0]):
            cur_year = _year(c[0])
        bunri = _txt(c[1])
        rnd = _round_label(c[2], prefix=(bunri + " " if bunri else ""))
        name = _norm_name(c[3])
        if not (cur_year and name):
            continue
        out.append({"year": cur_year, "round": rnd, "name": name,
                    "pos": _txt(c[4]), "from": _txt(c[5]),
                    "competed": False, "note": _txt(c[-1])})
    return out


def scrape_ikusei() -> list[dict]:
    rows = _fetch_rows("rearing.htm")
    out, cur_year = [], None
    for c in rows:
        if len(c) < 5 or _is_header(c, "選手名", "順位"):
            continue
        if _year(c[0]):
            cur_year = _year(c[0])
        name = _norm_name(c[2])
        if not (cur_year and name):
            continue
        out.append({"year": cur_year, "round": _round_label(c[1], prefix="育成"),
                    "name": name, "pos": _txt(c[3]), "from": _txt(c[4]),
                    "note": _txt(c[-1])})
    return out


def scrape_non_draft() -> list[dict]:
    rows = _fetch_rows("outside.htm")
    out, cur_year = [], None
    for c in rows:
        if len(c) < 4 or _is_header(c, "選手名", "年度"):
            continue
        if _year(c[0]):
            cur_year = _year(c[0])
        name = _norm_name(c[1])
        if not (cur_year and name):
            continue
        out.append({"year": cur_year, "name": name, "pos": _txt(c[2]),
                    "from": _txt(c[3]), "note": _txt(c[-1])})
    return out


def scrape_lottery() -> list[dict]:
    rows = _fetch_rows("lot.htm")
    out, cur_year, cur_round = [], None, ""
    for c in rows:
        if len(c) < 7 or _is_header(c, "競合チーム", "外れ"):
            continue
        if _year(c[0]):
            cur_year = _year(c[0])
        if _txt(c[1]):
            cur_round = _round_label(c[1])
        name = _norm_name(c[2])
        if not (cur_year and name):
            continue
        miss = _norm_name(c[7]) if len(c) > 7 else ""
        out.append({
            "year": cur_year, "round": cur_round, "name": name,
            "pos": _txt(c[3]), "from": _txt(c[4]),
            "competitors": _competitors(c[5]),
            "result": _txt(c[6]),
            "miss_name": miss,
            "miss_pos": _txt(c[8]) if len(c) > 8 else "",
            "miss_from": _txt(c[9]) if len(c) > 9 else "",
            "note": _txt(c[10]) if len(c) > 10 else "",
        })
    return out


def scrape_scouts() -> list[dict]:
    rows = _fetch_rows("scout.htm")
    out = []
    for c in rows:
        if len(c) < 3 or _is_header(c, "名前", "経歴"):
            continue
        name = _norm_name(c[1])
        if not name:
            continue
        out.append({"name": name, "title": _txt(c[0]), "area": "", "note": _txt(c[2])})
    return out


def scrape_ob_scouts() -> list[dict]:
    rows = _fetch_rows("scout_ob.htm")
    out, cur_area = [], ""
    for c in rows:
        if len(c) < 3 or _is_header(c, "名前", "担当地区"):
            continue
        if _txt(c[0]):
            cur_area = _txt(c[0])
        name = _norm_name(c[1])
        if not name:
            continue
        out.append({"name": name, "ob_career": _txt(c[2]), "title": "",
                    "area": cur_area, "note": ""})
    return out


def scrape_contract_changes() -> list[dict]:
    rows = _fetch_rows("change.htm")
    out = []
    for c in rows:
        if len(c) < 5 or _is_header(c, "契約変更日", "変更前"):
            continue
        y = _year(c[0])
        name = _norm_name(c[2])
        if not (y and name):
            continue
        change = f"{_txt(c[1])}→{_txt(c[4])}".strip("→")
        note = _txt(c[-1])
        out.append({"year": y, "name": name, "change": change,
                    "date": _txt(c[0]), "note": note})
    return out


def build() -> dict:
    picks = scrape_draft_picks()
    lottery = scrape_lottery()
    # competed フラグ: 競合 lottery（結果 ○/×）に出た 1位指名を picks 側にも反映
    competed_keys = {(e["year"], e["name"]) for e in lottery if e.get("result")}
    for p in picks:
        if (p["year"], p["name"]) in competed_keys:
            p["competed"] = True
    data = {
        "_schema": {
            "note": "巨人ドラフト史データ正本。出典=NPB公式ドラフト会議結果ほか公開資料。"
                    "守備位置・所属はドラフト指名時のもの。事実のみ。HTML/文章はコピーせず事実テーブルのみ抽出。",
            "source": "https://www.my-favorite-giants.net/giants_data/draft/ ほか公開資料",
            "benchmark": "https://www.my-favorite-giants.net/giants_data/draft/lot.htm",
            "generator": "src/tools/scrape_giants_draft.py",
        },
        "updated": "2026-06-05",
        "draft_picks": picks,
        "ikusei_picks": scrape_ikusei(),
        "non_draft": scrape_non_draft(),
        "lottery": lottery,
        "scouts": scrape_scouts(),
        "ob_scouts": scrape_ob_scouts(),
        "contract_changes": scrape_contract_changes(),
    }
    return data


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
