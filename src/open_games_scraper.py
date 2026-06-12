"""巨人 年度別オープン戦 結果 scraper (再利用モジュール)。

取得元: my-favorite-giants /giants_data/result_year/open/<year>.htm (2001-2026)。
10 列テーブル: 試合数 / 日付 / 対戦相手 / H / 球場 / 勝敗 / スコア / 継投 / 安打 / 本塁打。
出典は JSON / 表示には載せない (user 方針)。
"""
from __future__ import annotations

import html as _html
import re
import urllib.request

SOURCE_TMPL = "https://www.my-favorite-giants.net/giants_data/result_year/open/{year}.htm"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
LABEL_MAP = {
    "日付": "date",
    "対戦相手": "opp",
    "H": "home",
    "球場": "stadium",
    "勝敗": "result",
    "スコア": "score",
    "継投": "pitchers",
    "安打": "hits",
    "本塁打": "hr",
}


def _clean(raw_cell: str) -> str:
    s = _html.unescape(re.sub(r"<[^>]+>", "", raw_cell))
    return re.sub(r"\s+", "", s).strip()


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "shift_jis", "euc-jp", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_year_html(year: int, *, timeout: int = 30) -> str:
    req = urllib.request.Request(
        SOURCE_TMPL.format(year=year), headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _decode(resp.read())


def _cells(tr_html: str) -> list[str]:
    return [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_html, re.S | re.I)]


def parse_year(html_text: str) -> dict | None:
    rows = re.findall(r"<tr.*?</tr>", html_text, re.S | re.I)
    header_idx = None
    col_map: dict[str, int] = {}
    date_idx = None
    for i, tr in enumerate(rows):
        cells = _cells(tr)
        if "日付" in cells and "対戦相手" in cells and "スコア" in cells:
            for idx, label in enumerate(cells):
                key = LABEL_MAP.get(label)
                if key and key not in col_map:
                    col_map[key] = idx
            date_idx = cells.index("日付")
            header_idx = i
            break
    if header_idx is None or "date" not in col_map or "result" not in col_map:
        return None

    game_no_idx = max(0, date_idx - 1)
    games: list[dict] = []
    for tr in rows[header_idx + 1:]:
        cells = _cells(tr)
        if not cells:
            continue
        gno = cells[game_no_idx] if game_no_idx < len(cells) else ""
        if not re.match(r"^\d+$", gno):
            continue
        game = {"no": gno}
        for key, idx in col_map.items():
            game[key] = cells[idx] if idx < len(cells) else ""
        # 日付が空 (中止行など) は除外
        if not game.get("date"):
            continue
        games.append(game)

    if not games:
        return None
    return {"games": games}


def scrape_year(year: int) -> dict | None:
    try:
        parsed = parse_year(fetch_year_html(year))
    except Exception:
        return None
    if not parsed:
        return None
    return {"year": int(year), **parsed}


def upsert_year(years: list[dict], entry: dict) -> list[dict]:
    out = [y for y in years if int(y.get("year") or 0) != int(entry["year"])]
    out.append(entry)
    out.sort(key=lambda y: int(y.get("year") or 0), reverse=True)
    return out
