"""NOMOTOKE-LINEUP-FROM-X-001 — pure offline parser for Giants lineup
tweets posted by 巨人公式X (TokyoGiants) before each game.

Typical tweet shapes
====================

  本日のスタメンが発表されました
  1番（中）ヘルナンデス
  2番（二）吉川尚輝
  3番（一）岡本和真
  ...
  9番（投）戸郷翔征

Or condensed:

  【スタメン発表】1番(中)ヘルナンデス、2番(二)吉川尚輝、3番(一)岡本和真...

Position tokens: 投 / 捕 / 一 / 二 / 三 / 遊 / 左 / 中 / 右 / 指 (DH).

The parser is conservative:
- requires the keyword (スタメン / 先発オーダー / オーダー発表)
- requires ≥7 batting-order rows (8/9 rows + DH variation)
- skips when lineup couldn't be parsed cleanly

Renderer contract: each row dict carries ``order`` (e.g. ``1``),
``position`` (e.g. ``中``), ``player_name`` (e.g. ``ヘルナンデス``).
``batting_average`` / ``starter_era`` are left empty — they would need
NPB stats integration (separate ticket).
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional

LINEUP_KEYWORDS = (
    "スタメン",
    "先発オーダー",
    "オーダー発表",
    "本日のオーダー",
    "本日のメンバー",
    "本日のラインナップ",
)
# Baseball positions: 投 (P), 捕 (C), 一 (1B), 二 (2B), 三 (3B),
# 遊 (SS), 左 (LF), 中 (CF), 右 (RF), 指 (DH).
_POSITION_CHAR_CLASS = "投捕一二三遊左中右指"
_LINEUP_ROW_RE = re.compile(
    r"(?P<order>[1-9])番\s*[（(]\s*(?P<pos>[" + _POSITION_CHAR_CLASS + r"])\s*[)）]\s*"
    r"(?P<name>[^\s　、，,。．\n・]{1,20})"
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]+")


def _normalize_tweet_body(raw: str) -> str:
    """RSS feeds wrap tweet text in HTML <br/> + entity-encoded chars.
    Decode + tag-strip + collapse whitespace before regex parse."""
    if not isinstance(raw, str) or not raw:
        return ""
    text = _BR_RE.sub("\n", raw)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    # Collapse runs of horizontal whitespace; keep newlines so the
    # row regex can anchor on line breaks.
    text = "\n".join(
        _WS_RE.sub(" ", line).strip() for line in text.split("\n")
    )
    return text


def _has_lineup_keyword(text: str) -> bool:
    return any(kw in text for kw in LINEUP_KEYWORDS)


def parse_x_lineup_tweet(title: str, summary: str) -> Optional[Dict[str, Any]]:
    """Parse a Giants lineup tweet. Returns ``{lineup: [...], keyword,
    raw_position_count}`` or ``None`` when the tweet doesn't carry a
    lineup we can extract.

    The lineup row order is preserved as the rows appear in the tweet
    (1番→9番).
    """
    title_n = _normalize_tweet_body(title or "")
    summary_n = _normalize_tweet_body(summary or "")
    combined = f"{title_n}\n{summary_n}"

    if not _has_lineup_keyword(combined):
        return None

    rows: List[Dict[str, str]] = []
    seen_orders: set = set()
    for m in _LINEUP_ROW_RE.finditer(combined):
        order = m.group("order")
        if order in seen_orders:
            continue
        seen_orders.add(order)
        rows.append(
            {
                "order": order,
                "position": m.group("pos").strip(),
                "player_name": m.group("name").strip(),
                "batting_average": "",
                "starter_era": "",
            }
        )

    if len(rows) < 7:
        return None

    # Sort by order to handle out-of-order regex hits (rare).
    rows.sort(key=lambda r: int(r["order"]))

    return {
        "lineup": rows,
        "keyword": next(kw for kw in LINEUP_KEYWORDS if kw in combined),
        "raw_position_count": len(rows),
    }
