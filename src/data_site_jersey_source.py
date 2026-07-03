"""Giants historical jersey-number source.

Reference:
- https://www.my-favorite-giants.net/giants_data/player/backnumber.htm
- https://www.my-favorite-giants.net/giants_data/player/retired_number.htm

The source site is used only for factual rows. Rendering and UX are owned by
Yoshilover's /data topic cluster.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable

import requests


LOG = logging.getLogger(__name__)

SOURCE_URL = "https://www.my-favorite-giants.net/giants_data/player/backnumber.htm"
RETIRED_SOURCE_URL = "https://www.my-favorite-giants.net/giants_data/player/retired_number.htm"
UA = {"User-Agent": "yoshilover-data-site (+https://yoshilover.com)"}


@dataclass(frozen=True)
class JerseyNumberRow:
    number: str
    current: str
    history: str
    is_retired: bool = False


RETIRED_NUMBERS = [
    {"number": "1", "name": "王貞治", "slug": "oh-sadaharu", "label": "世界の王"},
    {"number": "3", "name": "長嶋茂雄", "slug": "nagashima-shigeo", "label": "ミスタージャイアンツ"},
    {"number": "4", "name": "黒沢俊夫", "slug": "kurosawa-toshio", "label": "戦後の4番"},
    {"number": "14", "name": "沢村栄治", "slug": "sawamura-eiji", "label": "伝説のエース"},
    {"number": "16", "name": "川上哲治", "slug": "kawakami-tetsuharu", "label": "打撃の神様"},
    {"number": "34", "name": "金田正一", "slug": "kaneda-masaichi", "label": "400勝左腕"},
]


class _TableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[dict] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        if tag == "table":
            self._stack.append({"rows": [], "row": None})
        elif tag == "tr" and self._stack:
            self._stack[-1]["row"] = []
        elif tag in ("td", "th") and self._stack and self._stack[-1]["row"] is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._stack:
            cell = _clean("".join(self._cell))
            if self._stack[-1]["row"] is not None:
                self._stack[-1]["row"].append(cell)
            self._cell = None
        elif tag == "tr" and self._stack and self._stack[-1]["row"] is not None:
            row = [c for c in self._stack[-1]["row"] if c]
            if row:
                self._stack[-1]["rows"].append(row)
            self._stack[-1]["row"] = None
        elif tag == "table" and self._stack:
            rows = self._stack.pop()["rows"]
            if rows:
                self.tables.append(rows)


_WS = re.compile(r"[\s　]+")
_MARKER = re.compile(r"g(\d{1,3})g")
_IMG_WORD = re.compile(r"\bImage(?::[^ ]+)?\b")
_FIRST_SPLIT = re.compile(r"(?=←|／)")


def _clean(text: str) -> str:
    s = str(text or "").replace("\xa0", " ")
    s = _IMG_WORD.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _fetch_tables(url: str = SOURCE_URL) -> list[list[list[str]]]:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("jersey source fetch failed url=%s err=%r", url, exc)
        return []
    enc = r.encoding or r.apparent_encoding or "utf-8"
    try:
        html = r.content.decode(enc, errors="replace")
    except Exception:  # noqa: BLE001
        html = r.text
    parser = _TableExtractor()
    parser.feed(html)
    return parser.tables


def _number_sort_key(number: str) -> tuple[int, str]:
    try:
        return (int(number), number)
    except ValueError:
        return (9999, number)


def _split_current_history(text: str) -> tuple[str, str]:
    text = _clean(text)
    if not text:
        return "", ""
    parts = _FIRST_SPLIT.split(text, maxsplit=1)
    current = _clean(parts[0])
    history = _clean(parts[1]) if len(parts) > 1 else ""
    return current, history


def parse_jersey_rows(tables: Iterable[list[list[str]]]) -> list[JerseyNumberRow]:
    """Parse number-order rows from my-favorite-giants backnumber table."""
    parsed: dict[str, JerseyNumberRow] = {}
    for table in tables:
        for cells in table:
            joined = _clean(" ".join(cells))
            marker = _MARKER.search(joined)
            if not marker:
                continue
            number = marker.group(1)
            body = _clean(_MARKER.sub(" ", joined, count=1))
            if not body or body.startswith("背番号"):
                continue
            current, history = _split_current_history(body)
            if not current and not history:
                continue
            row = JerseyNumberRow(
                number=number,
                current=current,
                history=history,
                is_retired=("永久欠番" in current or any(r["number"] == number for r in RETIRED_NUMBERS)),
            )
            parsed[number] = row
    return [parsed[n] for n in sorted(parsed, key=_number_sort_key)]


def fetch_jersey_rows() -> list[JerseyNumberRow]:
    rows = parse_jersey_rows(_fetch_tables(SOURCE_URL))
    if rows:
        return rows
    return fallback_jersey_rows()


def fallback_jersey_rows() -> list[JerseyNumberRow]:
    """Small but useful fallback when the source is temporarily unreachable."""
    rows = [
        JerseyNumberRow("0", "増田大輝", "吉川尚輝 / 木村拓也 / 川相昌弘 など"),
        JerseyNumberRow("1", "永久欠番・王貞治", "南村不可止 / 白石敏男 / 林清一 など", True),
        JerseyNumberRow("2", "吉川尚輝", "陽岱鋼 / 井端弘和 / 小笠原道大 / 元木大介 など"),
        JerseyNumberRow("3", "永久欠番・長嶋茂雄", "田部武雄 / 千葉茂 など", True),
        JerseyNumberRow("4", "永久欠番・黒沢俊夫", "沢村栄治 / 川上哲治 など", True),
        JerseyNumberRow("6", "坂本勇人", "落合博満 / 川相昌弘 / 土井正三 など"),
        JerseyNumberRow("7", "長野久義", "二岡智宏 / 吉村禎章 / 柴田勲 など"),
        JerseyNumberRow("8", "丸佳浩", "谷佳知 / 仁志敏久 / 原辰徳 など"),
        JerseyNumberRow("14", "永久欠番・沢村栄治", "", True),
        JerseyNumberRow("16", "永久欠番・川上哲治", "", True),
        JerseyNumberRow("18", "菅野智之", "桑田真澄 / 堀内恒夫 / 藤田元司 など"),
        JerseyNumberRow("24", "大城卓三", "高橋由伸 / 中畑清 など"),
        JerseyNumberRow("25", "岡本和真", "村田修一 / 李承燁 / 駒田徳広 など"),
        JerseyNumberRow("34", "永久欠番・金田正一", "", True),
        JerseyNumberRow("55", "秋広優人", "松井秀喜 / 大田泰示 など"),
    ]
    return rows


__all__ = [
    "JerseyNumberRow",
    "RETIRED_NUMBERS",
    "RETIRED_SOURCE_URL",
    "SOURCE_URL",
    "fallback_jersey_rows",
    "fetch_jersey_rows",
    "parse_jersey_rows",
]
