"""344-INGEST Phase 1a: YouTube 動画 title filter (巨人 relevance gate).

YouTube 動画 title に以下のいずれか 1 つでも含まれれば pass、それ以外 skip:
  1. 巨人 keyword (巨人 / ジャイアンツ / 読売 / Giants 等)
  2. 現役 巨人選手名 (config/giants_roster.json)
  3. 元巨人 OB 名 (config/giants_ob_roster.json)

LLM 不使用、純 Python rule-based。
"""

from __future__ import annotations

from typing import Mapping, Sequence

from src.giants_ob_roster import matching_ob_names


_GIANTS_KEYWORDS: tuple[str, ...] = (
    "巨人",
    "ジャイアンツ",
    "読売ジャイアンツ",
    "読売",
    "Giants",
    "GIANTS",
    "TokyoGiants",
    "Tokyo Giants",
    "yomiurigiants",
    "YOMIURIGIANTS",
)


def youtube_title_passes_giants_filter(
    title: str,
    *,
    giants_roster_matcher=None,
    ob_roster: Sequence[Mapping] | None = None,
) -> tuple[bool, str]:
    """title が 巨人 relevance を持つか判定。pass=True/False と reason を返す。

    args:
      title: 動画 title text
      giants_roster_matcher: callable(text)->list[str] (現役 player 検出、
        通常 src.rss_fetcher._matching_giants_roster_names を渡す)
      ob_roster: 元巨人 OB roster (None なら giants_ob_roster.load を使用)

    returns: (pass, reason)
      reason は "giants_keyword" / "giants_player" / "giants_ob" / "no_match" の
      いずれか。Logging / observation 用。
    """
    if not title:
        return (False, "no_match")
    text = str(title)

    for kw in _GIANTS_KEYWORDS:
        if kw in text:
            return (True, "giants_keyword")

    if giants_roster_matcher is not None:
        try:
            roster_hits = giants_roster_matcher(text)
        except Exception:  # noqa: BLE001
            roster_hits = []
        if roster_hits:
            return (True, "giants_player")

    ob_hits = matching_ob_names(text, ob_roster)
    if ob_hits:
        return (True, "giants_ob")

    return (False, "no_match")
