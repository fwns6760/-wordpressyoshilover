"""NOMOTOKE-LINEUP-FROM-POSTGAME-001 Phase 2I — pure offline parser for
NPB公式 ``/scores/<YYYY>/<MMDD>/<away>-<home>-<N>/playbyplay.html``.

Where ``box.html`` (Phase 2F) gives the per-batter season-line + per-
pitcher line, ``playbyplay.html`` gives the **at-bat by at-bat
timeline**: each plate appearance with outs / batter / count / result
("空振り三振", "左中間ソロホームラン（打点1）", "右前安打", …).

This module surfaces a list of dicts, plus a convenience helper that
filters down to the **scoring plays** only — the highlight reel
yoshilover postgame articles need without bloating the body with every
single ground-out.

Pure text-in / dict-out, no I/O.

Page layout (verified against the 2026-05-10 中日 vs 巨人 fixture):

  <h5 name="com1-1" id="com1-1">1回表（巨人の攻撃）</h5>
  <table>
    <tr><td colspan="5" class="w2">（先発投手） <a>櫻井</a></td></tr>
    <tr>
      <td class="w1">0アウト</td>     <!-- outs -->
      <td class="w1">&nbsp;</td>      <!-- runner state -->
      <td class="w1"><a>吉川</a></td> <!-- batter -->
      <td class="w1">3-2より</td>     <!-- count -->
      <td class="w2">空振り三振</td>  <!-- result -->
    </tr>
    ...
  </table>
  <table> ... </table>  <!-- next event sequence -->
  <h5 ...>1回裏（中日の攻撃）</h5>
  ...
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional


_HALF_INNING_RE = re.compile(
    r'<h5\s+name="com(?P<n>\d+)-(?P<half>\d+)"[^>]*>'
    r'\s*(?P<num>\d+)回(?P<top_bottom>表|裏)（(?P<team>[^）]+?)の攻撃）\s*</h5>',
    re.DOTALL,
)

_TABLE_RE = re.compile(r"<table\b[^>]*>(?P<body>.*?)</table\s*>", re.DOTALL)
_TR_RE = re.compile(r"<tr\b[^>]*>(?P<row>.+?)</tr\s*>", re.DOTALL)
_TD_RE = re.compile(r"<td\b[^>]*>(?P<cell>.*?)</td\s*>", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NBSP_RE = re.compile(r"&nbsp;| ")

GIANTS_TEAM_TOKENS = ("読売ジャイアンツ", "巨人")

# Keywords that mark a plate appearance as a scoring / impact play.
_SCORING_KEYWORDS = (
    "本塁打", "ホームラン",
    "適時", "タイムリー",
    "犠飛", "犠打",
    "押し出し",
    "スクイズ",
    "打点",
)


def _clean(value: str) -> str:
    if not isinstance(value, str):
        return ""
    text = _NBSP_RE.sub(" ", value)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def parse_npb_playbyplay_html(html: str) -> Optional[List[Dict[str, Any]]]:
    """Return a flat list of plate-appearance events.

    Each event dict has:
      ``inning_no``  int  (1-9 typical)
      ``half``       "表" or "裏"
      ``team``       attacking team name e.g. "巨人"
      ``outs``       e.g. "0アウト"
      ``batter``     e.g. "吉川"
      ``count``      e.g. "3-2より"
      ``result``     e.g. "空振り三振" / "左中間ソロホームラン（打点1）"

    Returns ``None`` when no half-inning headers are found at all.
    """
    if not isinstance(html, str) or not html:
        return None

    half_innings = list(_HALF_INNING_RE.finditer(html))
    if not half_innings:
        return None

    events: List[Dict[str, Any]] = []
    for idx, m in enumerate(half_innings):
        inning_no = int(m.group("num"))
        half = m.group("top_bottom")
        team = m.group("team").strip()
        start = m.end()
        end = half_innings[idx + 1].start() if idx + 1 < len(half_innings) else len(html)
        segment = html[start:end]

        for t in _TABLE_RE.finditer(segment):
            for r in _TR_RE.finditer(t.group("body")):
                cells = [_clean(c.group("cell")) for c in _TD_RE.finditer(r.group("row"))]
                # Skip the pitcher-change row (single colspan cell)
                if len(cells) != 5:
                    continue
                outs, _runner, batter, count, result = cells
                if not batter or not result:
                    continue
                events.append(
                    {
                        "inning_no": inning_no,
                        "half": half,
                        "team": team,
                        "outs": outs,
                        "batter": batter,
                        "count": count,
                        "result": result,
                    }
                )
    return events


def extract_scoring_plays(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter to the highlight-reel plays only.

    Includes anything where the ``result`` contains a scoring marker
    (本塁打 / 適時 / 押し出し / 犠飛 / スクイズ / 打点). The "打点"
    keyword in particular catches NPB's parenthesised RBI annotation
    (e.g. ``（打点2）``) that they append to RBI hits.
    """
    if not events:
        return []
    out: List[Dict[str, Any]] = []
    for ev in events:
        result = ev.get("result") or ""
        if any(kw in result for kw in _SCORING_KEYWORDS):
            out.append(ev)
    return out


def extract_giants_scoring_plays(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Same as ``extract_scoring_plays`` but filtered to 巨人 attacking
    half-innings only (when 巨人 was the batting team)."""
    return [
        ev
        for ev in extract_scoring_plays(events)
        if any(tok in (ev.get("team") or "") for tok in GIANTS_TEAM_TOKENS)
    ]


# ─── 405 / 415 (b) Phase 1: full per-PA detail parser ──────────────────────
#
# parse_npb_playbyplay_html は scoring highlight 用に runner_state / pitcher
# tracking を捨てている。 405 (走者状況別 / 打席内カウント別) と 415 (b strict
# = per-PA 投手追跡) には全 field 必要。 parse_npb_playbyplay_full_detail で
# 拡張 dict を返す。
#
# 追加 field:
#   ``runner_state``    走者状況 ("&nbsp;"=無走者 / "1塁" / "2塁" / "3塁" /
#                       "1・2塁" / "1・3塁" / "2・3塁" / "満塁")
#   ``count_balls``     int (count "3-2より" の 1 番目)
#   ``count_strikes``   int (count "3-2より" の 2 番目)
#   ``current_pitcher`` 当該 PA 時の対戦投手 (先発投手 marker +
#                       投手交代 marker で track)

_PITCHER_CELL_RE = re.compile(
    r'<td\b[^>]*\bcolspan\s*=\s*["\']?5["\']?[^>]*>(?P<cell>.*?)</td\s*>',
    re.DOTALL,
)
_PITCHER_NAME_RE = re.compile(
    r"(?:先発投手|投手交代)(?:）|\))?\s*(?P<name>[^\s（(]+)"
)
_COUNT_BALLS_STRIKES_RE = re.compile(r"(?P<b>\d+)-(?P<s>\d+)")
_RUNNER_STATE_NORMALIZE_RE = re.compile(r"[ 　]+")


def _normalize_runner_state(value: str) -> str:
    """Normalize runner state cell text.

    Empty / nbsp-only → "" (= no runners).
    Otherwise return stripped string ("1塁" / "1・2塁" / "満塁" 等)。"""
    text = _RUNNER_STATE_NORMALIZE_RE.sub(" ", value or "").strip()
    if not text or text == "&nbsp;":
        return ""
    return text


def _parse_count(value: str) -> tuple[Optional[int], Optional[int]]:
    """Parse count text "3-2より" into (balls, strikes).

    Returns (None, None) when the format doesn't match.
    """
    if not value:
        return (None, None)
    m = _COUNT_BALLS_STRIKES_RE.search(value)
    if not m:
        return (None, None)
    try:
        return (int(m.group("b")), int(m.group("s")))
    except (TypeError, ValueError):
        return (None, None)


def parse_npb_playbyplay_full_detail(html: str) -> Optional[List[Dict[str, Any]]]:
    """Return per-PA events with full detail for 405 / 415 (b).

    Each event dict has the ``parse_npb_playbyplay_html`` keys plus:
      ``runner_state``    e.g. "" (無走者) / "1塁" / "1・2塁" / "満塁"
      ``count_balls``     0-3 (None if unparsable)
      ``count_strikes``   0-2 (None if unparsable)
      ``current_pitcher`` 当該 PA の対戦投手名

    Returns ``None`` when no half-inning headers are found at all.
    """
    if not isinstance(html, str) or not html:
        return None

    half_innings = list(_HALF_INNING_RE.finditer(html))
    if not half_innings:
        return None

    events: List[Dict[str, Any]] = []
    for idx, m in enumerate(half_innings):
        inning_no = int(m.group("num"))
        half = m.group("top_bottom")
        team = m.group("team").strip()
        start = m.end()
        end = half_innings[idx + 1].start() if idx + 1 < len(half_innings) else len(html)
        segment = html[start:end]

        # 投手 marker は table 開始の colspan=5 行 / table 途中の投手交代行 で
        # 出る。 segment 全体を順に走査して current_pitcher を track。
        current_pitcher: str = ""

        for t in _TABLE_RE.finditer(segment):
            for r in _TR_RE.finditer(t.group("body")):
                row_html = r.group("row")
                # 投手 marker 行 (colspan=5 単一 cell) 検出
                pm = _PITCHER_CELL_RE.search(row_html)
                if pm:
                    cell_text = _clean(pm.group("cell"))
                    name_m = _PITCHER_NAME_RE.search(cell_text)
                    if name_m:
                        current_pitcher = name_m.group("name").strip()
                    continue
                cells = [_clean(c.group("cell")) for c in _TD_RE.finditer(row_html)]
                if len(cells) != 5:
                    continue
                outs, runner_raw, batter, count, result = cells
                if not batter or not result:
                    continue
                balls, strikes = _parse_count(count)
                events.append(
                    {
                        "inning_no": inning_no,
                        "half": half,
                        "team": team,
                        "outs": outs,
                        "runner_state": _normalize_runner_state(runner_raw),
                        "batter": batter,
                        "count": count,
                        "count_balls": balls,
                        "count_strikes": strikes,
                        "result": result,
                        "current_pitcher": current_pitcher,
                    }
                )
    return events


# 405 走者状況別 cut helpers
RUNNER_STATE_BASES_LOADED = "満塁"
RUNNER_STATE_NO_RUNNERS = ""


def extract_pa_with_runners_state(
    events: List[Dict[str, Any]], runner_state: str
) -> List[Dict[str, Any]]:
    """Filter events to those with a specific ``runner_state`` value.

    Use the literal value parser produced (e.g. "" for no-runners,
    "1塁" / "1・2塁" / "満塁")."""
    if not events:
        return []
    return [ev for ev in events if (ev.get("runner_state") or "") == runner_state]


# 405 打席内カウント別 cut helpers
def extract_pa_first_pitch_decision(
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """初球打ち decision: count_balls=0 かつ count_strikes=0 の PA。

    NPB の count は「決着時点」 の値なので、 0-0 のまま結果が出ている =
    1 球目で決着した PA。"""
    if not events:
        return []
    return [
        ev
        for ev in events
        if ev.get("count_balls") == 0 and ev.get("count_strikes") == 0
    ]


def extract_pa_two_strike(
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """2 ストライク後 decision: count_strikes == 2 の PA。"""
    if not events:
        return []
    return [ev for ev in events if ev.get("count_strikes") == 2]
