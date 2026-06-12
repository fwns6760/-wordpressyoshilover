"""巨人 先発ローテ scraper (再利用モジュール)。

scripts/scrape_starter_rotation.py (全年バッチ) と
src/tools/rotation_auto_update.py (毎朝 当年だけ更新) の両方から使う共通ロジック。

取得元: my-favorite-giants の年別 rotation ページ。
出典は JSON / 表示には載せない (user 方針 2026-06-09)。
"""
from __future__ import annotations

import re
import urllib.request

SOURCE_TMPL = "https://www.my-favorite-giants.net/giants_data/rotation/{year}.htm"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# ヘッダ ラベル (空白除去後) -> 出力 key
LABEL_MAP = {
    "試合数": "game_no",
    "日付": "date",
    "曜日": "weekday",
    "対戦相手": "opp",
    "球場": "stadium",
    "チ｜ム勝敗": "team_result",
    "先発投手": "pitcher",
    "勝敗": "decision",
    "投球回数": "ip",
    "球数": "pitches",
    "打者": "batters",
    "被安打": "hits",
    "被本塁打": "hr",
    "奪三振": "so",
    "与四球": "bb",
    "与死球": "hbp",
    "失点": "runs",
    "自責点": "er",
    "QS": "qs",
}
PLACEHOLDER_PITCHER = re.compile(r"^(先発投手|投手|[-－ー―]+|)$")


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"\s+", "", text)
    return text.strip()


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


def _row_cells(tr_html: str) -> list[str]:
    return [
        _clean(c)
        for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_html, re.S | re.I)
    ]


def parse_year(html: str) -> dict | None:
    """1 年分の HTML を {games, pitchers} に。失敗時 None。"""
    rows = re.findall(r"<tr.*?</tr>", html, re.S | re.I)
    header_idx = None
    col_map: dict[str, int] = {}
    for i, tr in enumerate(rows):
        cells = _row_cells(tr)
        if "先発投手" in cells and "日付" in cells:
            for idx, label in enumerate(cells):
                key = LABEL_MAP.get(label)
                if key and key not in col_map:
                    col_map[key] = idx
            header_idx = i
            break
    if header_idx is None or "pitcher" not in col_map or "game_no" not in col_map:
        return None

    games: list[dict] = []
    counts: dict[str, int] = {}
    for tr in rows[header_idx + 1:]:
        cells = _row_cells(tr)
        if not cells:
            continue
        gno = cells[col_map["game_no"]] if col_map["game_no"] < len(cells) else ""
        if not re.match(r"^\d+$", gno):
            continue
        pidx = col_map["pitcher"]
        pitcher = cells[pidx].strip() if pidx < len(cells) else ""
        if PLACEHOLDER_PITCHER.match(pitcher):
            continue
        game = {key: (cells[idx].strip() if idx < len(cells) else "")
                for key, idx in col_map.items()}
        games.append(game)
        counts[pitcher] = counts.get(pitcher, 0) + 1

    if not games:
        return None

    pitchers = [
        {"name": name, "starts": n}
        for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {"games": games, "pitchers": pitchers}


def scrape_year(year: int) -> dict | None:
    """1 年分を取得・parse。{year, games, pitchers} か None。"""
    try:
        parsed = parse_year(fetch_year_html(year))
    except Exception:
        return None
    if not parsed:
        return None
    return {"year": int(year), **parsed}


def upsert_year(years: list[dict], entry: dict) -> list[dict]:
    """years リスト内の同一 year を entry で置換 (無ければ追加)、新しい年から降順。"""
    out = [y for y in years if int(y.get("year") or 0) != int(entry["year"])]
    out.append(entry)
    out.sort(key=lambda y: int(y.get("year") or 0), reverse=True)
    return out
