"""Farm(2gun) source adapters for /data/farm topic cluster.

Primary public reference:
https://www.my-favorite-giants.net/giants_game/{year}/result_farm.htm

The pages on yoshilover should not mirror the reference site layout.  This
module extracts factual rows and lets our templates reorganize them into a
smaller, mobile-first topic cluster.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable

import requests

from src.data_site_farm_stats import giants_farm_map


LOG = logging.getLogger(__name__)

BASE = "https://www.my-favorite-giants.net"
UA = {"User-Agent": "yoshilover-data-site (+https://yoshilover.com)"}
SEASON_YEAR = 2026

FARM_SOURCE_URLS = {
    "hub": f"{BASE}/",
    "schedule": f"{BASE}/giants_game/{SEASON_YEAR}/result_farm.htm",
    "calendar": f"{BASE}/giants_game/{SEASON_YEAR}/top_farm.htm",
    "players": f"{BASE}/giants_data/result_player/farm/{SEASON_YEAR}.htm",
    "players_archive": f"{BASE}/giants_data/result_player/farm/top.htm",
    "team_history": f"{BASE}/giants_data/farm/result-year.htm",
    "team_record": f"{BASE}/giants_data/farm/result-year_team.htm",
    "year_results": f"{BASE}/giants_data/farm/result_year/top.htm",
    "spring": f"{BASE}/giants_game/{SEASON_YEAR}/result_farm.htm",
    "spring_archive": f"{BASE}/giants_data/farm/result_year/pre_spring/top.htm",
    "autumn": f"{BASE}/giants_data/farm/result_year/pre_autumn/2025.htm",
    "autumn_archive": f"{BASE}/giants_data/farm/result_year/pre_autumn/top.htm",
    "titles": f"{BASE}/giants_data/farm/titleholder.htm",
    "titles_pitcher": f"{BASE}/giants_data/farm/titleholder_pitcher.htm",
    "titles_batter": f"{BASE}/giants_data/farm/titleholder_batter.htm",
    "championship": f"{BASE}/giants_data/farm/series.htm",
}


@dataclass(frozen=True)
class FarmGameRow:
    competition: str
    date_label: str
    weekday: str
    opponent: str
    home_away: str
    venue: str
    score: str
    record: str
    pitchers: str
    hits: str
    homers: str


@dataclass(frozen=True)
class FarmPlayerStat:
    name: str
    role: str
    games: str = ""
    avg: str = ""
    hits: str = ""
    hr: str = ""
    rbi: str = ""
    sb: str = ""
    wins: str = ""
    losses: str = ""
    saves: str = ""
    innings: str = ""
    strikeouts: str = ""
    era: str = ""


@dataclass(frozen=True)
class FarmGenericRow:
    cells: tuple[str, ...]


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
            txt = _clean("".join(self._cell))
            if self._stack[-1]["row"] is not None:
                self._stack[-1]["row"].append(txt)
            self._cell = None
        elif tag == "tr" and self._stack and self._stack[-1]["row"] is not None:
            row = [c for c in self._stack[-1]["row"]]
            if any(row):
                self._stack[-1]["rows"].append(row)
            self._stack[-1]["row"] = None
        elif tag == "table" and self._stack:
            rows = self._stack.pop()["rows"]
            if rows:
                self.tables.append(rows)


_WS = re.compile(r"[\s　]+")
_DATE = re.compile(r"^\d{1,2}月\d{1,2}日$")


def _clean(text: str) -> str:
    return _WS.sub(" ", str(text or "").replace("\xa0", " ")).strip()


def _fetch_tables(url: str) -> list[list[list[str]]]:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("farm source fetch failed url=%s err=%r", url, exc)
        return []
    enc = r.encoding or r.apparent_encoding or "utf-8"
    try:
        html = r.content.decode(enc, errors="replace")
    except Exception:  # noqa: BLE001
        html = r.text
    parser = _TableExtractor()
    parser.feed(html)
    return parser.tables


def parse_farm_game_rows(tables: Iterable[list[list[str]]]) -> list[FarmGameRow]:
    rows: list[FarmGameRow] = []
    competition = ""
    for table in tables:
        for raw in table:
            cells = [_clean(c) for c in raw]
            if not cells:
                continue
            joined = " ".join(cells)
            if "春季教育" in joined:
                competition = "春季教育リーグ"
                continue
            if "ファーム公式戦" in joined:
                competition = "ファーム公式戦"
                continue
            if "秋季教育" in joined or "フェニックス" in joined:
                competition = "秋季教育リーグ"
                continue
            if "ファーム日本選手権" in joined:
                competition = "ファーム日本選手権"
                continue
            if not _DATE.match(cells[0]):
                continue
            padded = cells + [""] * 10
            # result_farm.htm: date, weekday, opponent, H, venue, score, record, relay, hits, HR
            opponent = padded[2]
            score = padded[5]
            if not opponent and not score:
                continue
            rows.append(
                FarmGameRow(
                    competition=competition or "ファーム",
                    date_label=padded[0],
                    weekday=padded[1],
                    opponent=opponent,
                    home_away=padded[3],
                    venue=padded[4],
                    score=score,
                    record=padded[6],
                    pitchers=padded[7],
                    hits=padded[8],
                    homers=padded[9],
                )
            )
    return rows


def fetch_farm_game_rows(year: int = SEASON_YEAR) -> list[FarmGameRow]:
    url = FARM_SOURCE_URLS["schedule"].replace(str(SEASON_YEAR), str(year))
    return parse_farm_game_rows(_fetch_tables(url))


def fetch_farm_generic_rows(url_key: str, *, limit: int = 24) -> list[FarmGenericRow]:
    tables = _fetch_tables(FARM_SOURCE_URLS[url_key])
    candidates: list[FarmGenericRow] = []
    for table in tables:
        for row in table:
            cells = tuple(_clean(c) for c in row if _clean(c))
            if len(cells) < 3:
                continue
            if any("西暦" in c or "選手" in c or "日付" in c for c in cells):
                continue
            candidates.append(FarmGenericRow(cells=cells))
            if len(candidates) >= limit:
                return candidates
    return candidates


def farm_player_stats(year: int = SEASON_YEAR) -> tuple[list[FarmPlayerStat], list[FarmPlayerStat]]:
    """Return current Giants farm batting/pitching rows.

    The site already has an NPB official parser for current farm stats.  Use it
    here as the stable data source and keep my-favorite-giants as the UX/source
    map for the broader farm cluster.
    """
    data = giants_farm_map(year)
    batting: list[FarmPlayerStat] = []
    pitching: list[FarmPlayerStat] = []
    for name, rec in data.items():
        b = rec.get("batting") or {}
        if b:
            batting.append(
                FarmPlayerStat(
                    name=name,
                    role="batting",
                    games=b.get("試合", ""),
                    hits=b.get("安打", ""),
                    hr=b.get("本", ""),
                    rbi=b.get("打点", ""),
                    sb=b.get("盗塁", ""),
                    avg=b.get("打率", ""),
                )
            )
        p = rec.get("pitching") or {}
        if p:
            pitching.append(
                FarmPlayerStat(
                    name=name,
                    role="pitching",
                    games=p.get("登板", ""),
                    wins=p.get("勝", ""),
                    losses=p.get("敗", ""),
                    saves=p.get("S", ""),
                    innings=p.get("投球回", ""),
                    strikeouts=p.get("奪三", ""),
                    era=p.get("防御率", ""),
                )
            )
    batting.sort(key=lambda r: _rate_sort(r.avg), reverse=True)
    pitching.sort(key=lambda r: _rate_sort(r.era, high=False))
    return batting, pitching


def _rate_sort(value: str, *, high: bool = True) -> float:
    try:
        v = float(str(value).replace("-", "").strip() or ("-999" if high else "999"))
    except ValueError:
        v = -999 if high else 999
    return v


__all__ = [
    "FARM_SOURCE_URLS",
    "FarmGameRow",
    "FarmGenericRow",
    "FarmPlayerStat",
    "fetch_farm_game_rows",
    "fetch_farm_generic_rows",
    "farm_player_stats",
    "parse_farm_game_rows",
]
