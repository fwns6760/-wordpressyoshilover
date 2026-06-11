"""巨人 セ・パ交流戦 当年成績 scraper (再利用モジュール)。

取得元: NPB公式 順位表 https://npb.jp/bis/{year}/stats/std_c.html / std_p.html。
各ページの2つ目のテーブル(ヘッダーに「ホーム」あり・「差」なし)が交流戦成績表。
交流戦期間外(表なし・ページなし)は None を返し、baked data のみで描画する。
出典は JSON / 表示には載せない (user 方針)。
"""
from __future__ import annotations

import html as _html
import re
import urllib.request

SOURCE_TMPL = "https://npb.jp/bis/{year}/stats/std_{league}.html"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_TEAM_SHORT = {
    "読売ジャイアンツ": "巨人", "阪神タイガース": "阪神",
    "東京ヤクルトスワローズ": "ヤクルト", "横浜DeNAベイスターズ": "DeNA",
    "広島東洋カープ": "広島", "中日ドラゴンズ": "中日",
    "北海道日本ハムファイターズ": "日本ハム", "東北楽天ゴールデンイーグルス": "楽天",
    "埼玉西武ライオンズ": "西武", "千葉ロッテマリーンズ": "ロッテ",
    "オリックス・バファローズ": "オリックス", "福岡ソフトバンクホークス": "ソフトバンク",
}
# NPB「対X」列 → config/giants_interleague.json の vs キー
_VS_KEY = {"対日": "f", "対楽": "e", "対西": "l", "対ロ": "m", "対オ": "b", "対ソ": "h"}


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "shift_jis", "euc-jp", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_standings_html(year: int, league: str, *, timeout: int = 30) -> str:
    req = urllib.request.Request(
        SOURCE_TMPL.format(year=year, league=league), headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _decode(resp.read())


def _clean(raw_cell: str) -> str:
    s = _html.unescape(re.sub(r"<[^>]+>", "", raw_cell))
    return s.replace("\xa0", " ").strip()


def parse_wdl(cell: str) -> list[int] | None:
    """'5-2(2)' -> [5,2,2] / '4-1' -> [4,1,0] / '--' '***' -> None (未対戦)。"""
    s = (cell or "").strip()
    m = re.match(r"^(\d+)-(\d+)(?:\((\d+)\))?$", s)
    if not m:
        return None
    return [int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)]


def parse_interleague_table(html_text: str) -> list[dict]:
    """std_c / std_p HTML から交流戦成績表の行を返す (表なしは [])。

    行: {team, g, w, l, t, pct, home, road, vs:{f/e/l/m/b/h:[勝,敗,分]|None}}
    交流戦表の判定: ヘッダーが「チーム」始まりで「ホーム」を含み「差」を含まない。
    """
    out: list[dict] = []
    for table in re.findall(r"<table[^>]*>(.*?)</table>", html_text, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        header: list[str] | None = None
        for tr in rows:
            cells = [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
            if not cells:
                continue
            if cells[0] == "チーム":
                header = cells if ("ホーム" in cells and "差" not in cells) else None
                continue
            if header is None or cells[0] not in _TEAM_SHORT or len(cells) < len(header):
                continue
            row: dict = {"team": _TEAM_SHORT[cells[0]], "vs": {}}
            for label, val in zip(header[1:], cells[1:]):
                if label == "試合":
                    row["g"] = int(val)
                elif label == "勝利":
                    row["w"] = int(val)
                elif label == "敗北":
                    row["l"] = int(val)
                elif label == "引分":
                    row["t"] = int(val)
                elif label == "勝率":
                    row["pct"] = val
                elif label == "ホーム":
                    row["home"] = parse_wdl(val)
                elif label == "ロード":
                    row["road"] = parse_wdl(val)
                elif label in _VS_KEY:
                    row["vs"][_VS_KEY[label]] = parse_wdl(val)
            if {"g", "w", "l", "t", "pct"} <= set(row):
                out.append(row)
        if out:
            return out
    return out


def merge_standings(cl_rows: list[dict], pa_rows: list[dict]) -> list[dict]:
    """セ・パ12球団を勝率順に並べた交流戦順位表 (同率は同順位)。"""
    merged = [{**r, "league": "セ"} for r in cl_rows] + [{**r, "league": "パ"} for r in pa_rows]
    merged.sort(key=lambda r: (-float(r["pct"] or 0), -(r["w"] - r["l"])))
    prev_pct, prev_rank = None, 0
    for i, r in enumerate(merged, start=1):
        rank = prev_rank if r["pct"] == prev_pct else i
        r["rank"] = rank
        prev_pct, prev_rank = r["pct"], rank
    return merged


def _format_gb(leader: dict, team: dict) -> str:
    gb = ((leader["w"] - leader["l"]) - (team["w"] - team["l"])) / 2
    if gb <= 0:
        return "―"
    return f"+{gb:.1f}"


def scrape_current(year: int) -> dict | None:
    """当年の交流戦成績。{"year","standings","giants"} / 期間外・取得失敗は None。"""
    try:
        cl = parse_interleague_table(fetch_standings_html(year, "c"))
        pa = parse_interleague_table(fetch_standings_html(year, "p"))
    except Exception:
        return None
    if len(cl) != 6 or len(pa) != 6:
        return None
    standings = merge_standings(cl, pa)
    giants_rows = [r for r in standings if r["team"] == "巨人"]
    if not giants_rows:
        return None
    g = giants_rows[0]
    giants = {
        "year": int(year), "final": False,
        "rank": g["rank"], "g": g["g"], "w": g["w"], "l": g["l"], "d": g["t"],
        "pct": g["pct"],
        "champion": standings[0]["team"] if standings else "",
        "gb": _format_gb(standings[0], g) if standings else "",
        "home": g.get("home"), "visitor": g.get("road"),
        "vs": g.get("vs") or {},
    }
    return {"year": int(year), "standings": standings, "giants": giants}
