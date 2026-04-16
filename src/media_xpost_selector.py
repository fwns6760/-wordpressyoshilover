"""
media_xpost_selector.py — 記事本文に差し込むマスコミ/公式Xポストの選定

Phase B.5-a では social_news 記事の source_url をそのまま返すだけに絞る。
将来は news 記事向けの候補探索もここに集約する。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


_TWEET_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/([^/]+)/status/", re.IGNORECASE)
_NOTICE_TWEET_WINDOW_HOURS = 48
_NPB_HANDLES = {"@npb"}
_OFFICIAL_HANDLES = {"@tokyogiants", "@yomiuri_giants"}
_MEDIA_HANDLES = {"@hochi_giants", "@sportshochi", "@hochi_baseball", "@sponichiyakyu", "@sanspo_giants", "@nikkansports"}


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s　]", "", value or "")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _stringify_datetime(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return (value or "").strip() if isinstance(value, str) else ""
    return parsed.isoformat()


def _extract_handle(tweet_url: str) -> str:
    match = _TWEET_URL_RE.search(tweet_url or "")
    if not match:
        return ""
    handle = match.group(1).strip()
    if not handle or handle in {"i", "home", "search", "explore"}:
        return ""
    return "@" + handle


def _candidate_source_class(candidate: dict[str, Any]) -> str:
    media_url = (
        (candidate.get("source_url") or "").strip()
        or (candidate.get("post_url") or "").strip()
        or (candidate.get("url") or "").strip()
    )
    handle = _extract_handle(media_url).lower()
    source_name = (candidate.get("source_name") or "").strip().lower()
    if handle in _NPB_HANDLES or "npb" in source_name:
        return "npb"
    if handle in _OFFICIAL_HANDLES or "巨人公式" in source_name:
        return "official"
    if (
        handle in _MEDIA_HANDLES
        or "報知" in source_name
        or "スポニチ" in source_name
        or "サンスポ" in source_name
        or "日刊" in source_name
    ):
        return "media"
    return "other"


def _candidate_priority(route: str, source_class: str) -> int:
    if route == "notice":
        return {"npb": 300, "official": 200, "media": 100}.get(source_class, 0)
    if route == "manager":
        return {"official": 200, "media": 100}.get(source_class, 0)
    if route == "social_secondary":
        return {"media": 100}.get(source_class, 0)
    return 0


def _match_alias(candidate_text: str, aliases: list[str]) -> str:
    return next((alias for alias in aliases if alias and alias in candidate_text), "")


def _build_matched_quote(
    candidate: dict[str, Any],
    source_class: str,
    section_label: str,
    quote_type: str,
    match_reason: str,
    match_score: int,
    matched_alias: str,
) -> dict[str, str]:
    media_url = (
        (candidate.get("source_url") or "").strip()
        or (candidate.get("post_url") or "").strip()
        or (candidate.get("url") or "").strip()
    )
    handle = _extract_handle(media_url)
    return {
        "url": media_url,
        "handle": handle,
        "quote_account": handle or (candidate.get("source_name") or "").strip(),
        "source_name": (candidate.get("source_name") or "").strip(),
        "created_at": _stringify_datetime(candidate.get("created_at")),
        "quote_type": quote_type,
        "section_label": section_label,
        "match_reason": match_reason,
        "match_score": match_score,
        "matched_player": matched_alias,
        "source_class": source_class,
    }


def _rank_pool_candidates(
    entry: dict[str, Any],
    media_quote_pool: list[dict[str, Any]],
    aliases: list[str],
    route: str,
    section_label: str,
    quote_type: str,
    notice_type: str = "",
) -> list[dict[str, str]]:
    article_time = _parse_datetime(entry.get("created_at"))
    ranked_quotes: list[dict[str, str]] = []

    for candidate in media_quote_pool:
        media_url = (
            (candidate.get("source_url") or "").strip()
            or (candidate.get("post_url") or "").strip()
            or (candidate.get("url") or "").strip()
        )
        if not media_url:
            continue

        source_class = _candidate_source_class(candidate)
        priority_score = _candidate_priority(route, source_class)
        if priority_score <= 0:
            continue

        candidate_text = _normalize_name(
            f"{candidate.get('title', '')} {candidate.get('summary', '')}"
        )
        matched_alias = _match_alias(candidate_text, aliases)
        if not matched_alias:
            continue

        candidate_time = _parse_datetime(candidate.get("created_at"))
        if article_time and candidate_time:
            delta_hours = abs((article_time - candidate_time).total_seconds()) / 3600.0
            if delta_hours > _NOTICE_TWEET_WINDOW_HOURS:
                continue
            time_score = max(0, int(_NOTICE_TWEET_WINDOW_HOURS - delta_hours))
            match_reason = "composite"
        else:
            time_score = 0
            match_reason = "player_name_match"

        notice_bonus = 0
        if notice_type and notice_type in candidate_text:
            notice_bonus = 10

        ranked_quotes.append(
            _build_matched_quote(
                candidate,
                source_class,
                section_label,
                quote_type,
                match_reason,
                priority_score + 100 + time_score + notice_bonus,
                matched_alias,
            )
        )

    return sorted(ranked_quotes, key=lambda item: item["match_score"], reverse=True)


def _select_second_distinct_quote(
    ranked_quotes: list[dict[str, str]],
    first_quote: dict[str, str],
    allowed_source_classes: set[str],
) -> dict[str, str] | None:
    used_handles = {
        (first_quote.get("handle") or "").lower(),
        (first_quote.get("quote_account") or "").lower(),
    }
    for quote in ranked_quotes:
        if quote.get("url") == first_quote.get("url"):
            continue
        if quote.get("source_class") not in allowed_source_classes:
            continue
        quote_handle = (quote.get("handle") or quote.get("quote_account") or "").lower()
        if quote_handle and quote_handle in used_handles:
            continue
        return quote
    return None


def _build_source_quote(entry: dict[str, Any]) -> dict[str, str] | None:
    media_url = (
        (entry.get("source_url") or "").strip()
        or (entry.get("post_url") or "").strip()
        or (entry.get("url") or "").strip()
    )
    if not media_url:
        return None

    handle = _extract_handle(media_url)
    return {
        "url": media_url,
        "handle": handle,
        "quote_account": handle or (entry.get("source_name") or "").strip(),
        "source_name": (entry.get("source_name") or "").strip(),
        "created_at": (entry.get("created_at") or "").strip(),
        "quote_type": "source_tweet",
        "section_label": "📌 関連ポスト",
        "match_reason": "own_source",
        "match_score": 100,
    }


def _select_notice_quote(
    entry: dict[str, Any],
    media_quote_pool: list[dict[str, Any]],
    max_count: int,
) -> list[dict[str, str]]:
    player_aliases = [
        _normalize_name(alias)
        for alias in entry.get("player_aliases", [])
        if _normalize_name(alias)
    ]
    if not player_aliases:
        player_name = _normalize_name(entry.get("player_name", ""))
        if player_name:
            player_aliases.append(player_name)
    if not player_aliases:
        return []

    notice_type = (entry.get("notice_type") or "").strip()
    ranked_quotes = _rank_pool_candidates(
        entry,
        media_quote_pool,
        player_aliases,
        "notice",
        "📌 公示ポスト",
        "official_notice_tweet",
        notice_type=notice_type,
    )
    if not ranked_quotes:
        return []
    selected_quotes = [ranked_quotes[0]]
    if max_count <= 1:
        return selected_quotes

    first_source_class = selected_quotes[0].get("source_class")
    allowed_second_classes = {
        "npb": {"official", "media"},
        "official": {"media"},
        "media": set(),
    }.get(first_source_class, set())
    second_quote = _select_second_distinct_quote(ranked_quotes[1:], selected_quotes[0], allowed_second_classes)
    if second_quote:
        selected_quotes.append(second_quote)
    return selected_quotes[:max_count]


def _select_manager_quote(
    entry: dict[str, Any],
    media_quote_pool: list[dict[str, Any]],
    max_count: int,
) -> list[dict[str, str]]:
    manager_aliases = [
        _normalize_name(alias)
        for alias in entry.get("manager_aliases", [])
        if _normalize_name(alias)
    ]
    if not manager_aliases:
        manager_name = _normalize_name(entry.get("manager_name", ""))
        if manager_name:
            manager_aliases.append(manager_name)
    if not manager_aliases:
        return []

    ranked_quotes = _rank_pool_candidates(
        entry,
        media_quote_pool,
        manager_aliases,
        "manager",
        "📢 報道ポスト",
        "manager_media_tweet",
    )
    if not ranked_quotes:
        return []
    selected_quotes = [ranked_quotes[0]]
    if max_count <= 1:
        return selected_quotes

    first_source_class = selected_quotes[0].get("source_class")
    allowed_second_classes = {"official": {"media"}, "media": set()}.get(first_source_class, set())
    second_quote = _select_second_distinct_quote(ranked_quotes[1:], selected_quotes[0], allowed_second_classes)
    if second_quote:
        selected_quotes.append(second_quote)
    return selected_quotes[:max_count]


def _select_social_source_quotes(
    entry: dict[str, Any],
    media_quote_pool: list[dict[str, Any]],
    max_count: int,
) -> list[dict[str, str]]:
    source_quote = _build_source_quote(entry)
    if source_quote is None:
        return []
    selected_quotes = [source_quote]
    if max_count <= 1:
        return selected_quotes

    topic_aliases = [
        _normalize_name(alias)
        for alias in entry.get("topic_aliases", [])
        if _normalize_name(alias)
    ]
    if not topic_aliases:
        return selected_quotes

    ranked_quotes = _rank_pool_candidates(
        entry,
        media_quote_pool,
        topic_aliases,
        "social_secondary",
        "📌 関連ポスト",
        "media_followup_tweet",
    )
    second_quote = _select_second_distinct_quote(ranked_quotes, source_quote, {"media"})
    if second_quote:
        selected_quotes.append(second_quote)
    return selected_quotes[:max_count]


def select_media_quotes(
    entry: dict[str, Any],
    max_count: int = 1,
    media_quote_pool: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """
    記事本文に埋め込む primary media quote を返す。

    現段階の仕様:
    - notice 記事は media_quote_pool から公式公示ポストを最大1件返す
    - source_type == social_news の記事は source_url / post_url を最大1件返す
    - それ以外の記事は空リスト
    """
    if max_count <= 0:
        return []

    media_quote_pool = media_quote_pool or []
    source_type = (entry.get("source_type") or "").strip()
    if source_type == "social_news":
        social_max_count = min(max_count, 1)
        if (entry.get("category") or "").strip() in {"試合速報", "選手情報", "首脳陣"}:
            social_max_count = max_count
        return _select_social_source_quotes(entry, media_quote_pool, social_max_count)

    story_kind = (entry.get("story_kind") or "").strip()
    if story_kind == "player_notice" and media_quote_pool:
        notice_quotes = _select_notice_quote(entry, media_quote_pool, max_count)
        if notice_quotes:
            return notice_quotes
    if story_kind == "manager_quote" and media_quote_pool:
        manager_quotes = _select_manager_quote(entry, media_quote_pool, max_count)
        if manager_quotes:
            return manager_quotes

    return []
