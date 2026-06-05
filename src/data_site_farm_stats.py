"""巨人ファーム（二軍/イースタン）今季個人成績の取得（NPB公式）。

選手ページに「二軍（今季）」ブロックを足すための source。
NPB 公式: https://npb.jp/bis/{year}/stats/idb1_g.html（打）/ idp1_g.html（投）。

giants_farm_map() -> { 正規化名: {"batting": {stat:val}, "pitching": {stat:val}} }
ネットワーク失敗時は空 dict（選手ページは二軍ブロックを出さないだけ）。

依存は stdlib のみ（本番ジョブ image に bs4 は無いため html.parser を使う）。
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

import requests

LOG = logging.getLogger(__name__)

_UA = {"User-Agent": "yoshilover-fetcher (+https://yoshilover.com)"}
_BAT_URL = "https://npb.jp/bis/{year}/stats/idb1_g.html"
_PIT_URL = "https://npb.jp/bis/{year}/stats/idp1_g.html"
_WS = re.compile(r"[\s　]+")
_LEAD = re.compile(r"^[\*＊\+\s　]+")

# 表示する打撃 stat（NPB ヘッダ名 -> 表示ラベル）。
_BAT_COLS = [("試合", "試合"), ("打席", "打席"), ("打数", "打数"), ("安打", "安打"),
             ("本塁打", "本"), ("打点", "打点"), ("盗塁", "盗塁"), ("打率", "打率")]
_PIT_COLS = [("登板", "登板"), ("勝利", "勝"), ("敗北", "敗"), ("セーブ", "S"),
             ("ホールド", "H"), ("投球回", "投球回"), ("奪三振", "奪三"),
             ("三振", "奪三"), ("防御率", "防御率")]

_CACHE: dict | None = None
_CACHE_YEAR: int | None = None


class _TableExtractor(HTMLParser):
    """stdlib のみで <table> 群を [rows[cells]] として抽出（ネスト対応）。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[dict] = []
        self._cell: list | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append({"rows": [], "row": None})
        elif tag == "tr" and self._stack:
            self._stack[-1]["row"] = []
        elif tag in ("td", "th") and self._stack and self._stack[-1]["row"] is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack:
            txt = " ".join("".join(self._cell).split())
            if self._stack[-1]["row"] is not None:
                self._stack[-1]["row"].append(txt)
            self._cell = None
        elif tag == "tr" and self._stack and self._stack[-1]["row"] is not None:
            self._stack[-1]["rows"].append(self._stack[-1]["row"])
            self._stack[-1]["row"] = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop()["rows"])


def _norm(name: str) -> str:
    return _WS.sub("", _LEAD.sub("", name or "").strip())


def _num(s: str) -> str:
    """'21 .2' のような分割表記を詰めて返す（表示用 string）。"""
    return _WS.sub("", (s or "").strip())


def _fetch_table(url: str):
    r = requests.get(url, headers=_UA, timeout=15)
    if r.status_code != 200:
        return [], []
    try:
        html = r.content.decode("utf-8")
    except UnicodeDecodeError:
        html = r.text
    parser = _TableExtractor()
    parser.feed(html)
    if not parser.tables:
        return [], []
    big = max(parser.tables, key=len)
    if not big:
        return [], []
    return big[0], big[1:]


def _parse(url: str, cols) -> dict:
    header, rows = _fetch_table(url)
    if not header:
        return {}
    idx = {h.strip(): i for i, h in enumerate(header)}
    out: dict[str, dict] = {}
    for r in rows:
        if not r or len(r) < 2:
            continue
        name = _norm(r[0])
        if not name or "選手" in name:
            continue
        rec: dict[str, str] = {}
        for src, label in cols:
            i = idx.get(src)
            if i is not None and i < len(r):
                v = _num(r[i])
                if v:
                    rec[label] = v
        if rec:
            out[name] = rec
    return out


def giants_farm_map(year: int = 2026) -> dict:
    """{正規化名: {batting:{...}, pitching:{...}}}。失敗・空は {}。"""
    global _CACHE, _CACHE_YEAR
    if _CACHE is not None and _CACHE_YEAR == year:
        return _CACHE
    result: dict[str, dict] = {}
    try:
        bat = _parse(_BAT_URL.format(year=year), _BAT_COLS)
        pit = _parse(_PIT_URL.format(year=year), _PIT_COLS)
        for nm, rec in bat.items():
            result.setdefault(nm, {})["batting"] = rec
        for nm, rec in pit.items():
            result.setdefault(nm, {})["pitching"] = rec
    except Exception as exc:  # noqa: BLE001
        LOG.warning("giants_farm_map fetch failed: %r", exc)
        result = {}
    _CACHE, _CACHE_YEAR = result, year
    return result


if __name__ == "__main__":
    m = giants_farm_map()
    print("players:", len(m))
    for nm in ["赤星優志", "井上温大", "浅野翔吾", "石塚裕惺", "山﨑伊織"]:
        print(nm, m.get(nm))
