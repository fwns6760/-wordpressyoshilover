"""
media_xpost_selector.py — 記事本文に差し込むマスコミ/公式Xポストの選定

Phase B.5-a では social_news 記事の source_url をそのまま返すだけに絞る。
将来は news 記事向けの候補探索もここに集約する。
"""

from __future__ import annotations

import re
from typing import Any


_TWEET_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/([^/]+)/status/", re.IGNORECASE)


def _extract_handle(tweet_url: str) -> str:
    match = _TWEET_URL_RE.search(tweet_url or "")
    if not match:
        return ""
    handle = match.group(1).strip()
    if not handle or handle in {"i", "home", "search", "explore"}:
        return ""
    return "@" + handle


def select_media_quotes(entry: dict[str, Any], max_count: int = 1) -> list[dict[str, str]]:
    """
    記事本文に埋め込む primary media quote を返す。

    現段階の仕様:
    - source_type == social_news の記事だけ対象
    - source_url / post_url を最大1件返す
    - 非 social 記事は空リスト
    """
    if max_count <= 0:
        return []

    source_type = (entry.get("source_type") or "").strip()
    if source_type != "social_news":
        return []

    media_url = (
        (entry.get("source_url") or "").strip()
        or (entry.get("post_url") or "").strip()
        or (entry.get("url") or "").strip()
    )
    if not media_url:
        return []

    return [
        {
            "url": media_url,
            "handle": _extract_handle(media_url),
            "source_name": (entry.get("source_name") or "").strip(),
            "created_at": (entry.get("created_at") or "").strip(),
            "quote_type": "source_tweet",
        }
    ][:max_count]
