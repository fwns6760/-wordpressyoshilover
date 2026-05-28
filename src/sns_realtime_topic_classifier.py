"""sns_realtime_topic_classifier — 一軍/二軍/三軍 分類 + roster alias mention counter.

ticket 445: SNS リアルタイム話題 (巨人 1軍/2軍/3軍) daily aggregation.

- 三軍 = 投稿に 育成/三軍/3軍 keyword、 または roster で role=='ikusei' alias match
- 二軍 = 投稿に ファーム/二軍/2軍/イースタン keyword、 または roster position に 二軍/ファーム
- 一軍 = default
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

ROSTER_JSON = Path(__file__).resolve().parent.parent / "config" / "giants_roster.json"

FARM_KEYWORDS = ("ファーム", "二軍", "2軍", "イースタン")
IKUSEI_KEYWORDS = ("育成", "三軍", "3軍")

# (alias, canonical_name, role, position)
RosterAlias = Tuple[str, str, str, str]


def load_roster_aliases(path: Path = ROSTER_JSON) -> List[RosterAlias]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[RosterAlias] = []
    for entry in data:
        if not entry.get("active", True):
            continue
        name = (entry.get("name") or "").strip()
        role = entry.get("role") or ""
        position = entry.get("position") or ""
        for alias in entry.get("aliases") or []:
            alias = (alias or "").strip()
            if alias:
                out.append((alias, name, role, position))
    # 長い alias 優先で match (例: 「阿部慎之助監督」 を 「阿部」 より先に取る)
    out.sort(key=lambda t: len(t[0]), reverse=True)
    return out


def classify_team_level(post_text: str, roster_aliases: List[RosterAlias]) -> str:
    text = post_text or ""
    if any(kw in text for kw in IKUSEI_KEYWORDS):
        return "三軍"
    if any(kw in text for kw in FARM_KEYWORDS):
        return "二軍"
    for alias, _canonical, role, position in roster_aliases:
        if alias in text:
            if role == "ikusei":
                return "三軍"
            if "二軍" in position or "ファーム" in position:
                return "二軍"
            return "一軍"
    return "一軍"


def count_mentions(
    posts_texts: List[str],
    roster_aliases: List[RosterAlias],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for text in posts_texts:
        if not text:
            continue
        seen_in_post = set()
        for alias, canonical, _role, _position in roster_aliases:
            if alias in text:
                seen_in_post.add(canonical)
        for canonical in seen_in_post:
            counts[canonical] = counts.get(canonical, 0) + 1
    return counts
