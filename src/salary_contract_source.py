"""Bounded, non-LLM contract-renewal extraction and two-source verification."""
from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html.parser import HTMLParser

import requests

MFG_URL = "https://www.my-favorite-giants.net/giants_data/contract/{year}.htm"
YAHOO_URL = "https://baseball.yahoo.co.jp/npb/contract/?date={week}"


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"\([^)]*\)|（[^）]*）", "", name)
    name = re.sub(r"^[A-Z][.・]", "", name)
    return re.sub(r"\s+", "", name).replace("﨑", "崎").replace("髙", "高")


def salary_year(day: date) -> int:
    return day.year + (day.month >= 10)


class _Tables(HTMLParser):
    """Only selected salary tables; rowspan metadata and preceding day are retained."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.heading = None
        self.day = ""
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "h3":
            self.heading = []
        if tag == "table" and (
            (self.source == "mfg" and attrs.get("id") == "example") or
            (self.source == "yahoo" and "bb-contractTable" in attrs.get("class", "").split())
        ):
            if self.table is not None:
                raise ValueError("nested salary table")
            self.table = {"day": self.day, "rows": []}
        if self.table is not None:
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.cell = {"text": [], "rowspan": int(attrs.get("rowspan", "1")), "tag": tag}

    def handle_data(self, text):
        if self.in_title:
            self.title.append(text)
        if self.heading is not None:
            self.heading.append(text)
        if self.cell is not None:
            self.cell["text"].append(text)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "h3" and self.heading is not None:
            self.day = "".join(self.heading).strip()
            self.heading = None
        if tag in ("td", "th") and self.cell is not None:
            self.cell["text"] = " ".join("".join(self.cell["text"]).split())
            self.row.append(self.cell)
            self.cell = None
        if tag == "tr" and self.row is not None and self.table is not None:
            self.table["rows"].append(self.row)
            self.row = None
        if tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def _amount(text):
    value = re.sub(r"[,\s]", "", text)
    if not re.fullmatch(r"\d+", value):
        return None
    amount = int(value)
    return amount if 1 <= amount <= 300000 else None


def parse_mfg(html: str, target_year: int, today: date) -> dict:
    parser = _Tables("mfg")
    parser.feed(html)
    parser.close()
    if f"契約更改{target_year - 1}年" not in "".join(parser.title) or len(parser.tables) != 1:
        raise ValueError("contract source year/table mismatch")
    rows = parser.tables[0]["rows"]
    head = [re.sub(r"\s+", "", c["text"]) for c in rows[0]]
    if len(head) != 7 or head[1:3] != ["選手名", f"{target_year-1}年俸"] or head[4:6] != [f"{target_year}年俸", "更改日"]:
        raise ValueError("contract table columns changed")
    records = {}
    roster = set()
    for row in rows[1:]:
        if len(row) != 7 or row[1]["tag"] != "td":
            continue
        name = normalize_name(row[1]["text"])
        if not name or name in roster:
            raise ValueError("duplicate/empty contract player")
        roster.add(name)
        amount = _amount(row[4]["text"])
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", row[5]["text"])
        if amount is None or not m:
            continue  # Unannounced values and multi-year totals are not estimates.
        month, day = map(int, m.groups())
        reported = date(target_year-1 if month >= 10 else target_year, month, day)
        if reported > today or salary_year(reported) != target_year:
            continue
        records[name] = {"salary_man": amount, "reported_on": reported.isoformat(),
                         "previous_salary_man": _amount(row[2]["text"])}
    if len(roster) < 40:
        raise ValueError("incomplete Giants contract roster")
    return {"records": records, "roster": sorted(roster), "target_year": target_year}


def parse_yahoo(html: str, week: date, target_year: int) -> dict:
    year_label = re.search(r'class=["\']bb-scheduleNavi__item["\'][^>]*>\s*(\d{4})年', html)
    if not year_label or int(year_label[1]) != week.year:
        raise ValueError("contract calendar year mismatch")
    parser = _Tables("yahoo")
    parser.feed(html)
    parser.close()
    if "契約更改" not in "".join(parser.title):
        raise ValueError("not a contract page")
    records = {}
    in_week_tables = 0
    for table in parser.tables:
        m = re.search(r"(\d{1,2})月(\d{1,2})日", table["day"])
        if not m:
            raise ValueError("missing contract day")
        month, day = map(int, m.groups())
        dates = []
        for year in (week.year-1, week.year, week.year+1):
            try:
                dates.append(date(year, month, day))
            except ValueError:
                continue
        reported = next((d for d in dates if week <= d < week + timedelta(days=7)), None)
        if reported is None:
            raise ValueError("contract page returned the wrong week")
        in_week_tables += 1
        team, remaining = None, 0
        for row in table["rows"]:
            if not row or row[0]["tag"] == "th":
                continue
            if len(row) == 1 and row[0]["text"] == "契約更改情報はありません":
                continue
            if len(row) == 4:
                if remaining:
                    raise ValueError("invalid team rowspan")
                team, remaining = row[0]["text"], row[0]["rowspan"]
                cells = row[1:]
            elif len(row) == 3 and remaining:
                cells = row
            else:
                raise ValueError("invalid contract row")
            remaining -= 1
            if team != "巨人" or salary_year(reported) != target_year:
                continue
            name = normalize_name(cells[0]["text"])
            amount = _amount(cells[1]["text"])
            if not name or amount is None or name in records:
                raise ValueError("ambiguous contract value")
            records[name] = {"salary_man": amount, "reported_on": reported.isoformat()}
    if not in_week_tables:
        raise ValueError("missing weekly contract tables")
    return records


def fetch_html(url):
    r = requests.get(url, headers={"User-Agent": "YoshiloverData/1.0", "Accept-Encoding": "gzip, deflate"}, timeout=20)
    r.raise_for_status()
    if len(r.content) > 3 * 1024 * 1024:
        raise ValueError("oversized contract response")
    return r.content.decode("utf-8", errors="strict")


def collect_contracts(today: date, fetch=fetch_html) -> dict:
    year = salary_year(today)
    source = MFG_URL.format(year=year-1)
    mfg = parse_mfg(fetch(source), year, today)
    weeks = sorted({date.fromisoformat(r["reported_on"]) - timedelta(days=date.fromisoformat(r["reported_on"]).weekday())
                    for r in mfg["records"].values()})
    if len(weeks) > 26:
        raise ValueError("too many contract weeks")

    def read_week(week):
        url = YAHOO_URL.format(week=week.isoformat())
        records = parse_yahoo(fetch(url), week, year)
        return {name: {**value, "source_url": url} for name, value in records.items()}

    corroboration = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for rows in pool.map(read_week, weeks):
            for name, record in rows.items():
                if name in corroboration and corroboration[name]["salary_man"] != record["salary_man"]:
                    raise ValueError("conflicting weekly values")
                corroboration[name] = record
    verified, held = {}, {}
    for name, first in mfg["records"].items():
        second = corroboration.get(name)
        if second is not None and date.fromisoformat(second["reported_on"]) > today:
            second = None
        if second is None or first["salary_man"] != second["salary_man"]:
            held[name] = {"reason": "source_disagreement" if second else "second_source_missing",
                          "mfg": first["salary_man"], "yahoo": second["salary_man"] if second else None}
            continue
        verified[name] = {"year": year, "team": "巨人", "league": "NPB", "salary_man": first["salary_man"],
            "reported_on": second["reported_on"], "sources": [
                {"url": source, "salary_man": first["salary_man"], "reported_on": first["reported_on"]},
                {"url": second["source_url"], "salary_man": second["salary_man"], "reported_on": second["reported_on"]}]}
    return {"target_year": year, "checked_on": today.isoformat(), "verified": verified,
            "held": held, "roster": mfg["roster"], "source_requests": 1 + len(weeks)}
