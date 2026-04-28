from __future__ import annotations

import re
from typing import Any


OTHER_TEAM_PLAYER_ROSTER: dict[str, str] = {
    "則本昂大": "楽天",
    "山本由伸": "ドジャース",
    "佐々木朗希": "ドジャース",
    "村上宗隆": "ヤクルト",
    "近藤健介": "ソフトバンク",
    "柳田悠岐": "ソフトバンク",
    "山川穂高": "ソフトバンク",
}
GIANTS_TEAM_PREFIX_RE = re.compile(r"(?P<team>巨人|読売|ジャイアンツ)[\s:：]+(?P<name>[一-龥々ァ-ヴーA-Za-z]{2,10})")
OPPONENT_CONTEXT_MARKERS = ("対戦", "vs", "VS", "ｖｓ", "戦展望", " 戦", "を相手", "の打席", "を抑え", "から本塁打")
TITLE_OPPONENT_RE = re.compile(r"(対|vs|ＶＳ|VS)(楽天|ヤクルト|中日|阪神|広島|DeNA|ロッテ|オリックス|ソフトバンク|日ハム|西武|ドジャース)")
WINDOW_RADIUS = 50


def _has_opponent_context(text: str, start: int, end: int) -> bool:
    window_start = max(0, start - WINDOW_RADIUS)
    window_end = min(len(text), end + WINDOW_RADIUS)
    window = text[window_start:window_end]
    return any(marker in window for marker in OPPONENT_CONTEXT_MARKERS)


def detect_other_team_player_in_giants_article(title: str, body_text: str) -> list[dict[str, Any]]:
    title_text = str(title or "")
    if TITLE_OPPONENT_RE.search(title_text):
        return []

    matches: list[dict[str, Any]] = []
    text = str(body_text or "")
    for match in GIANTS_TEAM_PREFIX_RE.finditer(text):
        name = match.group("name")
        owning_team = OTHER_TEAM_PLAYER_ROSTER.get(name)
        if owning_team is None:
            continue
        if _has_opponent_context(text, match.start("name"), match.end("name")):
            continue
        matches.append(
            {
                "team_prefix": match.group("team"),
                "name": name,
                "owning_team": owning_team,
                "position": match.start(),
            }
        )
    return matches
