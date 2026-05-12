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
