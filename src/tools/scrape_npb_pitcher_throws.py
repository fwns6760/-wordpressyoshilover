"""415 (vs 左右投手 split): NPB 公式 roster page から全 12 球団投手の throws 取得。

URL: https://npb.jp/bis/teams/rst_{team}.html
team codes: g / t / db / s / c / d / h / l / m / e / b / f

HTML 構造 (verified 2026-05-20):
- pitchers セクション: <a name="pit">投手</a> 以降の <tr class="rosterPlayer">
- 各 row: <td>No</td><td class="rosterRegister"><a>name</a></td><td>birthday</td>
         <td>height</td><td>weight</td><td>投</td><td>打</td><td>備考</td>
- 6 番目 td = throws (右 / 左 / 両)

出力: config/npb_pitcher_throws.json
  { "<player_name>": { "team": "<code>", "throws": "R|L|S" } }

throws 値:
- "右" → "R"
- "左" → "L"
- "両" → "S" (switch / 両投)

usage: `python3 -m src.tools.scrape_npb_pitcher_throws`

冪等: 既存 config/npb_pitcher_throws.json を上書き (run 都度 full refresh)。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "config" / "npb_pitcher_throws.json"

TEAM_CODES = ("g", "t", "db", "s", "c", "d", "h", "l", "m", "e", "b", "f")
NPB_ROSTER_URL = "https://npb.jp/bis/teams/rst_{team}.html"

USER_AGENT = "Mozilla/5.0 (yoshilover-data-pipeline; +https://yoshilover.com)"


def _fetch_roster_html(team: str, timeout: float = 30.0) -> str:
    url = NPB_ROSTER_URL.format(team=team)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    # NPB uses Shift-JIS but recent pages are UTF-8; try UTF-8 first
    for enc in ("utf-8", "shift_jis", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# pitchers セクション: <a name="pit"> から次の <a name=...> (cat / inf / out) まで
_PIT_SECTION_RE = re.compile(
    r'<a name="pit">投手</a>(.*?)(?:<a name="(?:cat|inf|out)">|<div class="rosterSub">)',
    re.DOTALL,
)

# 各 pitcher row: tr.rosterPlayer 内 — td 順 [No, Register-with-a, birthday,
# height, weight, throws, bats, note]
_PITCHER_ROW_RE = re.compile(
    r'<tr class="rosterPlayer">'
    r'<td>\s*(?P<no>\d+)\s*</td>'
    r'<td class="rosterRegister">(?:<a[^>]*>)?\s*(?P<name>[^<]+?)\s*(?:</a>)?</td>'
    r'<td>\s*(?P<birth>\d{4}\.\d{2}\.\d{2})\s*</td>'
    r'<td>\s*(?P<height>\d+)\s*</td>'
    r'<td>\s*(?P<weight>\d+)\s*</td>'
    r'<td>\s*(?P<throws>[右左両])\s*</td>'
    r'<td>\s*(?P<bats>[右左両])\s*</td>',
    re.DOTALL,
)

_THROWS_MAP = {"右": "R", "左": "L", "両": "S"}


def _normalize_name(name: str) -> str:
    """Roster JSON 内 name と整合させるため、 全角 space や middle dot を統一。"""
    # 「田中　将大」 → 「田中将大」 (全角 space 除去)
    n = name.replace("　", "").replace("　", "").strip()
    return n


def parse_pitcher_throws(html: str, team_code: str) -> list[dict]:
    """指定 team の HTML を parse して pitchers の (name, throws, team_code) list を返す。"""
    section_m = _PIT_SECTION_RE.search(html)
    if not section_m:
        LOG.warning("pitchers section not found for team=%s", team_code)
        return []
    section = section_m.group(1)
    out: list[dict] = []
    for m in _PITCHER_ROW_RE.finditer(section):
        name = _normalize_name(m.group("name"))
        throws_jp = m.group("throws")
        throws = _THROWS_MAP.get(throws_jp)
        if not name or not throws:
            continue
        out.append({"name": name, "throws": throws, "team": team_code})
    return out


def fetch_all_npb_pitchers() -> dict[str, dict]:
    """全 12 球団投手の {name: {team, throws}} dict を返す。"""
    result: dict[str, dict] = {}
    for team in TEAM_CODES:
        try:
            html = _fetch_roster_html(team)
        except (URLError, TimeoutError) as exc:
            LOG.warning("fetch failed team=%s err=%r", team, exc)
            continue
        pitchers = parse_pitcher_throws(html, team)
        LOG.info("team=%s pitchers=%d", team, len(pitchers))
        for p in pitchers:
            # 同 name 衝突時は first wins (両球団 hopping は記録順)
            key = p["name"]
            if key not in result:
                result[key] = {"team": p["team"], "throws": p["throws"]}
    return result


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = fetch_all_npb_pitchers()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    LOG.info("wrote %d pitchers → %s", len(data), OUTPUT_PATH)


if __name__ == "__main__":
    main()
