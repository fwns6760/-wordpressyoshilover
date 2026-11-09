"""Refresh only official Giants draft selections; preserve historical sections."""
from __future__ import annotations

import copy
import re
from html.parser import HTMLParser

import requests


class _DraftParser(HTMLParser):
    """The job image only needs the Python standard library for HTML parsing."""

    def __init__(self):
        super().__init__()
        self.text = []
        self.sections = {}
        self.heading = None
        self.section = None
        self.active = False
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4"):
            self.section = None
            self.heading = [] if tag == "h4" else None
        elif tag == "table":
            self.active = self.section is not None and self.section not in self.sections
            if self.active:
                self.sections[self.section] = []
        elif self.active and tag == "tr":
            self.row = []
        elif self.active and tag in ("td", "th"):
            self.cell = []

    def handle_data(self, data):
        self.text.append(data)
        if self.heading is not None:
            self.heading.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "h4" and self.heading is not None:
            label = "".join(self.heading).strip()
            self.section = label if label in ("新人選手選択会議", "育成選手選択会議") else None
            self.heading = None
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.active:
            self.sections[self.section].append(self.row)
        elif tag == "table":
            self.active = False


def parse_draft(html: str, year: int) -> dict:
    parser = _DraftParser()
    parser.feed(html)
    parser.close()
    text = " ".join(parser.text)
    if not re.search(rf"{year}年\s*読売ジャイアンツ", text):
        raise ValueError("draft year/team mismatch")
    result = {}
    for heading, key, prefix in (
        ("新人選手選択会議", "draft_picks", ""),
        ("育成選手選択会議", "ikusei_picks", "育成"),
    ):
        if heading not in parser.sections:
            raise ValueError(f"missing {heading}")
        rows = []
        for cells in parser.sections[heading]:
            if len(cells) != 4:
                raise ValueError("incomplete draft row")
            rank, name, pos, origin = cells
            if rank != f"{len(rows) + 1}位" or not all((name, pos, origin)):
                raise ValueError("invalid draft row/rank")
            rows.append({"year": year, "round": prefix + rank,
                         "name": re.sub(r"\s+", "", name), "pos": pos,
                         "from": origin, "note": ""})
        if not rows or len({r["name"] for r in rows}) != len(rows):
            raise ValueError("empty/duplicate selections")
        result[key] = rows
    result["source_url"] = f"https://draft.npb.jp/draft/{year}/draftlist_g.html"
    return result


def fetch_draft(year: int) -> dict:
    response = requests.get(f"https://draft.npb.jp/draft/{year}/draftlist_g.html", timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    return parse_draft(response.text, year)


def refresh_history(baked: dict, year: int) -> dict:
    """Fail closed on any missing year, so a failed fetch never removes picks.

    Before the current draft is published this raises; callers leave WP intact.
    Fetch every year after the baked history to survive annual rollover.
    """
    latest = max((int(r["year"]) for r in baked.get("draft_picks", [])), default=year)
    data = copy.deepcopy(baked)
    for target in range(min(latest + 1, year), year + 1):
        fresh = fetch_draft(target)
        for key in ("draft_picks", "ikusei_picks"):
            previous = {r["round"]: r for r in data.get(key, []) if int(r["year"]) == target}
            merged = []
            for row in fresh[key]:
                old = previous.get(row["round"], {})
                # Keep verified notes/lottery flags for the same player only.
                keep = old if old.get("name") == row["name"] else {}
                merged.append({**keep, **{k: v for k, v in row.items() if k != "note"},
                               "note": keep.get("note", "")})
            data[key] = merged + [r for r in data.get(key, []) if int(r["year"]) != target]
        sources = data.setdefault("official_sources", {})
        sources[str(target)] = fresh["source_url"]
    data["updated"] = f"{year}年ドラフト指名結果反映"
    return data
