"""NPB公式 個人成績ランキング(打撃/投手)を取得・パースする。

source:
- ``https://npb.jp/bis/<year>/stats/bat_<league>.html``  (打撃: 打率ランキング)
- ``https://npb.jp/bis/<year>/stats/pit_<league>.html``  (投手: 防御率ランキング)

公式テーブルの列をそのまま (headers, rows) で返す。マッピングや指標の再計算は
しない = NPB が出している数字をそのまま描画する(捏造ゼロ・最大の忠実度)。

``parse_leaders_table(html) -> (headers: list[str], rows: list[list[str]])``
"""

from __future__ import annotations

import html as _html
import re
import urllib.request
from typing import List, Optional, Tuple

_UA = "yoshilover-fetcher (+https://yoshilover.com)"
_TMPL = "https://npb.jp/bis/{year}/stats/{kind}_{league}.html"

_TABLE_RE = re.compile(r"<table\b[^>]*>(?P<body>.+?)</table>", re.DOTALL | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr\b[^>]*>(?P<body>.+?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(?P<body>.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean(fragment: str) -> str:
    s = _html.unescape(re.sub(r"<[^>]+>", "", fragment or ""))
    return s.replace("　", " ").replace("\xa0", " ").strip()


def _cells(row_html: str) -> List[str]:
    return [_clean(m.group("body")) for m in _CELL_RE.finditer(row_html)]


def fetch_leaders_html(year: int, kind: str, league: str = "c", *, timeout: int = 30) -> str:
    """kind = 'bat' | 'pit', league = 'c' | 'p'。"""
    url = _TMPL.format(year=year, kind=kind, league=league)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _decode(resp.read())


def parse_leaders_table(html: str, *, max_rows: int = 12) -> Optional[Tuple[List[str], List[List[str]]]]:
    """先頭テーブルから (headers, rows) を返す。最初の行を header とみなす。

    header の 1 列目が '順位' で始まるテーブルだけを採用(ランキング表の判定)。
    rows は最大 max_rows 件。列数が header と一致する行のみ採用。
    """
    for m in _TABLE_RE.finditer(html):
        rows = [_cells(r.group("body")) for r in _ROW_RE.finditer(m.group("body"))]
        rows = [r for r in rows if r]
        if not rows:
            continue
        headers = rows[0]
        if not headers or "順位" not in headers[0]:
            continue
        data = [r for r in rows[1:] if len(r) == len(headers)]
        return headers, data[:max_rows]
    return None
