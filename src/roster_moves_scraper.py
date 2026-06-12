"""巨人 出場選手登録・抹消 scraper (再利用モジュール)。

取得元: my-favorite-giants の年別 major ページ (/giants_data/major/<year>.htm)。
ページ構成:
1. 現在の1軍登録メンバー (位置 / 背番号 / 選手名)
2. 登録・抹消の動き (日付 / 登録 / 抹消、セル内は <br> 区切りで複数選手)

出典は JSON / 表示には載せない (user 方針)。選手名・日付は事実データ。
"""
from __future__ import annotations

import html as _html
import re
import urllib.request

SOURCE_TMPL = "https://www.my-favorite-giants.net/giants_data/major/{year}.htm"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
POSITIONS = ("投手", "捕手", "内野手", "外野手")
_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}$")


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


def _text(raw_cell: str) -> str:
    s = _html.unescape(re.sub(r"<[^>]+>", "", raw_cell))
    return re.sub(r"[ \t]+", " ", s).strip()


def _players(raw_cell: str) -> list[str]:
    """<br> 区切りで複数選手に分割。各選手は姓名 (全角スペース) + 故障理由カッコ。"""
    out = []
    for part in re.split(r"<br\s*/?>", raw_cell, flags=re.I):
        name = _html.unescape(re.sub(r"<[^>]+>", "", part)).strip()
        name = re.sub(r"\s+", " ", name).replace("　", "　").strip()
        if name:
            out.append(name)
    return out


def _raw_cells(tr_html: str) -> list[str]:
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_html, re.S | re.I)


def _norm_date(s: str) -> str:
    """'09/30' / '10.21' / '6/8' を 'M/D' に正規化。"""
    s = s.replace(".", "/").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", s)
    if not m:
        return s
    return f"{int(m.group(1))}/{int(m.group(2))}"


def parse_year(html_text: str) -> dict | None:
    """新旧 2 形式に対応。
    新 (2015-): 現在ロスター(位置/背番号/選手名) + [日付 | 登録 | 抹消]
    旧 (2001-2014): [日付 | 投手登録 | 投手抹消 | 野手登録 | 野手抹消] (ロスターは別形式 → skip)
    """
    rows = re.findall(r"<tr.*?</tr>", html_text, re.S | re.I)
    roster: list[dict] = []
    moves: list[dict] = []
    mode = "roster"  # roster -> (new|old) timeline
    for tr in rows:
        raw = _raw_cells(tr)
        cells = [_text(c) for c in raw]
        if len(cells) < 2:
            continue
        # 新形式タイムライン header
        if len(cells) >= 3 and cells[0] == "日付" and "登録" in cells[1] and "抹消" in cells[2]:
            mode = "new"
            continue
        # 旧形式タイムライン header (登録/抹消/登録/抹消、直前に 日付/投手/野手)
        if len(cells) == 4 and cells[0] == "登録" and cells[1] == "抹消" \
                and cells[2] == "登録" and cells[3] == "抹消":
            mode = "old"
            continue
        if mode == "roster":
            # 現在ロスター: 位置 / 背番号 / 選手名 (新形式・当年のみ)
            if len(cells) >= 3 and cells[0] in POSITIONS \
                    and re.match(r"^\d+$", cells[1]) and cells[2]:
                roster.append({"pos": cells[0], "no": cells[1], "name": cells[2]})
        elif mode == "new":
            if _DATE_RE.match(cells[0]):
                reg = _players(raw[1]) if len(raw) > 1 else []
                out = _players(raw[2]) if len(raw) > 2 else []
                if reg or out:
                    moves.append({"date": _norm_date(cells[0]), "reg": reg, "out": out})
        elif mode == "old":
            # [日付, 投手登録, 投手抹消, 野手登録, 野手抹消]
            if re.match(r"^\d{1,2}[./]\d{1,2}$", cells[0]) and len(raw) >= 5:
                reg = _players(raw[1]) + _players(raw[3])
                out = _players(raw[2]) + _players(raw[4])
                if reg or out:
                    moves.append({"date": _norm_date(cells[0]), "reg": reg, "out": out})
    if not roster and not moves:
        return None
    return {"roster": roster, "moves": moves}


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
