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

    article_time = _parse_datetime(entry.get("created_at"))
    notice_type = (entry.get("notice_type") or "").strip()
    best_match = None

    for candidate in media_quote_pool:
        media_url = (
            (candidate.get("source_url") or "").strip()
            or (candidate.get("post_url") or "").strip()
            or (candidate.get("url") or "").strip()
        )
        if not media_url:
            continue
        source_class = _candidate_source_class(candidate)
        priority_score = _candidate_priority("notice", source_class)
        if priority_score <= 0:
            continue

        candidate_text = _normalize_name(
            f"{candidate.get('title', '')} {candidate.get('summary', '')}"
        )
        matched_alias = _match_alias(candidate_text, player_aliases)
        if not matched_alias:
            continue

        candidate_time = _parse_datetime(candidate.get("created_at"))
        if article_time and candidate_time:
            delta_hours = abs((article_time - candidate_time).total_seconds()) / 3600.0
            if delta_hours > _NOTICE_TWEET_WINDOW_HOURS:
                continue
            time_score = max(0, int(_NOTICE_TWEET_WINDOW_HOURS - delta_hours))
        else:
            delta_hours = None
            time_score = 0

        notice_bonus = 0
        if notice_type and notice_type in candidate_text:
            notice_bonus = 10
        score = priority_score + 100 + time_score + notice_bonus
        match_reason = "composite" if delta_hours is not None else "player_name_match"
        quote = _build_matched_quote(
            candidate,
            source_class,
            "📌 公示ポスト",
            "official_notice_tweet",
            match_reason,
            score,
            matched_alias,
        )
        if best_match is None or quote["match_score"] > best_match["match_score"]:
            best_match = quote

    return [best_match][:max_count] if best_match else []


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

    article_time = _parse_datetime(entry.get("created_at"))
    best_match = None
    for candidate in media_quote_pool:
        media_url = (
            (candidate.get("source_url") or "").strip()
            or (candidate.get("post_url") or "").strip()
            or (candidate.get("url") or "").strip()
        )
        if not media_url:
            continue
        source_class = _candidate_source_class(candidate)
        priority_score = _candidate_priority("manager", source_class)
        if priority_score <= 0:
            continue

        candidate_text = _normalize_name(
            f"{candidate.get('title', '')} {candidate.get('summary', '')}"
        )
        matched_alias = _match_alias(candidate_text, manager_aliases)
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

        quote = _build_matched_quote(
            candidate,
            source_class,
            "📢 報道ポスト",
            "manager_media_tweet",
            match_reason,
            priority_score + 100 + time_score,
            matched_alias,
        )
        if best_match is None or quote["match_score"] > best_match["match_score"]:
            best_match = quote

    return [best_match][:max_count] if best_match else []


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

    source_type = (entry.get("source_type") or "").strip()
    if source_type == "social_news":
        media_url = (
            (entry.get("source_url") or "").strip()
            or (entry.get("post_url") or "").strip()
            or (entry.get("url") or "").strip()
        )
        if media_url:
            return [
                {
                    "url": media_url,
                    "handle": _extract_handle(media_url),
                    "quote_account": _extract_handle(media_url) or (entry.get("source_name") or "").strip(),
                    "source_name": (entry.get("source_name") or "").strip(),
                    "created_at": (entry.get("created_at") or "").strip(),
                    "quote_type": "source_tweet",
                    "section_label": "📌 関連ポスト",
                    "match_reason": "own_source",
                    "match_score": 100,
                }
            ][:max_count]

    media_quote_pool = media_quote_pool or []
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
