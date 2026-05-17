"""
media_xpost_selector.py — 記事本文に差し込むマスコミ/公式Xポストの選定

Phase B.5-a では social_news 記事の source_url をそのまま返すだけに絞る。
将来は news 記事向けの候補探索もここに集約する。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


_TWEET_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/([^/]+)/status/", re.IGNORECASE)
# 2026-05-14 PM tightened: was 48h; baseball relevance ~24h. Pre-game-day
# tweets beyond 24h are now rejected outright.
_NOTICE_TWEET_WINDOW_HOURS = 24
_NPB_HANDLES = {"@npb"}
_OFFICIAL_HANDLES = {"@tokyogiants", "@yomiuri_giants"}
_MEDIA_HANDLES = {"@hochi_giants", "@sportshochi", "@hochi_baseball", "@sponichiyakyu", "@sanspo_giants", "@nikkansports"}

# 2026-05-14 PM: event keyword match + game-time step bonus tuning so the
# pool ranks tweets that share the article's specific event (HR / サヨナラ /
# 完投 等) and that fired within the actual real-time reaction window.

# Event tokens scanned in BOTH article title (or text) AND candidate text.
# A shared token grants ``_EVENT_KEYWORD_BONUS`` once (only one shared event
# is rewarded — prevents double-stacking when both tokens appear).
_EVENT_TOKENS: tuple[str, ...] = (
    "サヨナラ", "逆転", "ホームラン", "本塁打", "ＨＲ", "HR", "弾",
    "決勝打", "決勝", "先制", "猛打賞", "完封", "完投", "完投勝利",
    "セーブ", "好投", "好救援", "ノーヒッター", "完投負け", "登板",
    "初安打", "初打席", "初登板", "初勝利", "初本塁打", "1号", "２号",
    "勝利投手", "セーブ失敗",
)
_EVENT_KEYWORD_BONUS = 20
_TIME_STEP_BONUS = 30
_SOCIAL_SECONDARY_DETAIL_BONUS = 25
# Article publish in JST hours 17:00–23:59 → game / immediate-post-game zone.
# Inside this zone, fan reactions fire within ~3h of the article. Outside
# (morning roundup / next-day retrospective at 00:00–16:59 JST), relevant
# tweets can be up to ~10h older (= previous evening's game).
_GAME_TIME_HOUR_START_JST = 17
_GAME_TIME_HOUR_END_JST = 23
_GAME_TIME_STEP_DELTA_HOURS = 3
_NON_GAME_TIME_STEP_DELTA_HOURS = 10
_JST = timezone(timedelta(hours=9))
_SOCIAL_SECONDARY_STRONG_TERMS: tuple[str, ...] = (
    "キャッチボール",
    "チームメート",
    "昆陽里",
    "こやのさと",
    "伊丹",
    "合流",
    "昇格",
    "登録",
    "抹消",
    "復帰",
    "負傷",
    "交代",
    "スタメン",
    "先発",
    "ブルペン",
    "ノック",
    "サヨナラ",
    "ホームラン",
    "本塁打",
    "完封",
    "完投",
)
_SOCIAL_SECONDARY_GENERIC_FRAGMENTS: tuple[str, ...] = (
    "巨人",
    "ジャイアンツ",
    "選手",
    "投手",
    "監督",
    "コーチ",
    "内野手",
    "外野手",
    "捕手",
    "東京ドーム",
    "ジャイアンツ球場",
    "スポーツ報知",
    "サンスポ",
    "スポニチ",
    "日刊スポーツ",
    "報知新聞",
    "巨人班",
    "関連情報",
    "投稿",
    "ポスト",
)


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


def _shared_event_token(article_text: str, candidate_text: str) -> str:
    """Return the first ``_EVENT_TOKENS`` element appearing in BOTH the
    article text and the candidate text, else ``""``.

    Used to award ``_EVENT_KEYWORD_BONUS`` exactly once per pair (no
    stacking even when multiple tokens overlap)."""
    if not article_text or not candidate_text:
        return ""
    for token in _EVENT_TOKENS:
        if token and token in article_text and token in candidate_text:
            return token
    return ""


def _compact_social_detail_text(value: str, aliases: list[str]) -> str:
    clean = re.sub(r"https?://\S+|pic\.twitter\.com/\S+|@\w+", "", value or "")
    clean = _normalize_name(clean)
    for alias in aliases:
        normalized_alias = _normalize_name(alias)
        if normalized_alias:
            clean = clean.replace(normalized_alias, "")
    for fragment in _SOCIAL_SECONDARY_GENERIC_FRAGMENTS:
        normalized_fragment = _normalize_name(fragment)
        if normalized_fragment:
            clean = clean.replace(normalized_fragment, "")
    clean = re.sub(r"[^\w一-龥ぁ-んァ-ヴー]", "", clean)
    return clean


def _shared_social_detail_token(article_text: str, candidate_text: str, aliases: list[str]) -> str:
    """Return a concrete shared detail for social-news secondary embeds.

    Player-name overlap alone is too broad for X posts. A second media tweet
    must share a concrete event/detail token with the source tweet; otherwise
    unrelated posts about the same player get rendered as one article.
    """
    event_token = _shared_event_token(article_text, candidate_text)
    if event_token:
        return event_token

    compact_article = _compact_social_detail_text(article_text, aliases)
    compact_candidate = _compact_social_detail_text(candidate_text, aliases)
    if not compact_article or not compact_candidate:
        return ""

    for term in _SOCIAL_SECONDARY_STRONG_TERMS:
        normalized = _normalize_name(term)
        if normalized and normalized in compact_article and normalized in compact_candidate:
            return normalized

    # Final deterministic fallback for unusual but literal same-topic phrases.
    # Four Japanese chars is intentionally narrow after alias/generic stripping.
    if len(compact_article) <= len(compact_candidate):
        shorter = compact_article
        longer = compact_candidate
    else:
        shorter = compact_candidate
        longer = compact_article
    for size in (8, 7, 6, 5, 4):
        if len(shorter) < size:
            continue
        for index in range(0, len(shorter) - size + 1):
            token = shorter[index : index + size]
            if token.isdigit():
                continue
            if token in longer:
                return token
    return ""


def _is_game_time_article(article_time: datetime | None) -> bool:
    """Article published in JST 17:00–23:59 = game / immediate post-game
    reaction window. Outside this zone (morning roundup, retrospective)
    fans tweeted hours earlier, so a wider step-bonus delta applies."""
    if article_time is None:
        return False
    jst_hour = article_time.astimezone(_JST).hour
    return _GAME_TIME_HOUR_START_JST <= jst_hour <= _GAME_TIME_HOUR_END_JST


def _time_step_bonus(
    article_time: datetime | None,
    candidate_time: datetime | None,
    delta_hours: float,
) -> int:
    """Step bonus added on top of the linear ``time_score``. Returns
    ``_TIME_STEP_BONUS`` when the article-to-candidate delta is within the
    realtime reaction tier for that article's publish time, else 0.

    - Game-time article (JST 17–23): tier = ±3h
    - Other (morning / retrospective): tier = ±10h
    """
    if article_time is None or candidate_time is None:
        return 0
    threshold = (
        _GAME_TIME_STEP_DELTA_HOURS
        if _is_game_time_article(article_time)
        else _NON_GAME_TIME_STEP_DELTA_HOURS
    )
    return _TIME_STEP_BONUS if delta_hours <= threshold else 0


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


def _selector_type(entry: dict[str, Any]) -> str:
    source_type = (entry.get("source_type") or "").strip()
    if source_type == "social_news":
        return "own_source"

    story_kind = (entry.get("story_kind") or "").strip()
    if story_kind == "player_notice":
        return "npb_notice"
    if story_kind == "manager_quote":
        return "manager_media"
    return "none"


def _effective_social_max_count(entry: dict[str, Any], max_count: int) -> int:
    social_max_count = min(max_count, 1)
    if (entry.get("category") or "").strip() in {"試合速報", "選手情報", "首脳陣"}:
        social_max_count = max_count
    return social_max_count


def _candidate_media_url(candidate: dict[str, Any]) -> str:
    return (
        (candidate.get("source_url") or "").strip()
        or (candidate.get("post_url") or "").strip()
        or (candidate.get("url") or "").strip()
    )


def _candidate_display_handle(candidate: dict[str, Any]) -> str:
    media_url = _candidate_media_url(candidate)
    return _extract_handle(media_url) or (candidate.get("source_name") or "").strip()


def _candidate_age_hours(article_time: datetime | None, candidate_time: datetime | None) -> float | None:
    if not article_time or not candidate_time:
        return None
    return round(abs((article_time - candidate_time).total_seconds()) / 3600.0, 2)


def _candidate_within_window(article_time: datetime | None, candidate_time: datetime | None) -> bool:
    age_hours = _candidate_age_hours(article_time, candidate_time)
    if age_hours is None:
        return True
    return age_hours <= _NOTICE_TWEET_WINDOW_HOURS


def _prepare_route_candidates(
    media_quote_pool: list[dict[str, Any]],
    route: str,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for candidate in media_quote_pool:
        media_url = _candidate_media_url(candidate)
        if not media_url:
            continue
        source_class = _candidate_source_class(candidate)
        priority_score = _candidate_priority(route, source_class)
        if priority_score <= 0:
            continue
        prepared.append(
            {
                "candidate": candidate,
                "media_url": media_url,
                "source_class": source_class,
                "priority_score": priority_score,
                "candidate_text": _normalize_name(
                    f"{candidate.get('title', '')} {candidate.get('summary', '')}"
                ),
                "candidate_time": _parse_datetime(candidate.get("created_at")),
            }
        )
    return prepared


def _best_candidate_snapshot(
    prepared_candidates: list[dict[str, Any]],
    aliases: list[str],
    article_time: datetime | None,
    notice_type: str = "",
) -> dict[str, Any]:
    best_score = None
    best_handle = ""
    best_age_hours = None

    for item in prepared_candidates:
        score = int(item["priority_score"])
        matched_alias = _match_alias(item["candidate_text"], aliases) if aliases else ""
        if matched_alias:
            score += 100
        age_hours = _candidate_age_hours(article_time, item["candidate_time"])
        if age_hours is not None and age_hours <= _NOTICE_TWEET_WINDOW_HOURS:
            score += max(0, int(_NOTICE_TWEET_WINDOW_HOURS - age_hours))
        if notice_type and notice_type in item["candidate_text"]:
            score += 10

        if best_score is None or score > best_score:
            best_score = score
            best_handle = _candidate_display_handle(item["candidate"])
            best_age_hours = age_hours

    return {
        "best_candidate_score": best_score,
        "best_candidate_handle": best_handle,
        "best_candidate_age_hours": best_age_hours,
    }


def _build_skip_meta(
    skip_reason: str,
    prepared_candidates: list[dict[str, Any]],
    aliases: list[str],
    article_time: datetime | None,
    notice_type: str = "",
) -> dict[str, Any]:
    payload = {
        "skip_reason": skip_reason,
        "pool_size_checked": len(prepared_candidates),
        "best_candidate_score": None,
        "best_candidate_handle": "",
        "best_candidate_age_hours": None,
    }
    payload.update(
        _best_candidate_snapshot(
            prepared_candidates,
            aliases,
            article_time,
            notice_type=notice_type,
        )
    )
    return payload


def _aliases_for_notice(entry: dict[str, Any]) -> list[str]:
    aliases = [
        _normalize_name(alias)
        for alias in entry.get("player_aliases", [])
        if _normalize_name(alias)
    ]
    if aliases:
        return aliases
    player_name = _normalize_name(entry.get("player_name", ""))
    return [player_name] if player_name else []


def _aliases_for_manager(entry: dict[str, Any]) -> list[str]:
    aliases = [
        _normalize_name(alias)
        for alias in entry.get("manager_aliases", [])
        if _normalize_name(alias)
    ]
    if aliases:
        return aliases
    manager_name = _normalize_name(entry.get("manager_name", ""))
    return [manager_name] if manager_name else []


def _aliases_for_social(entry: dict[str, Any]) -> list[str]:
    return [
        _normalize_name(alias)
        for alias in entry.get("topic_aliases", [])
        if _normalize_name(alias)
    ]


def _second_quote_skip_meta(
    prepared_candidates: list[dict[str, Any]],
    aliases: list[str],
    article_time: datetime | None,
    first_quote: dict[str, str],
    allowed_source_classes: set[str],
    notice_type: str = "",
) -> dict[str, Any]:
    if not allowed_source_classes:
        return _build_skip_meta("other", [], aliases, article_time, notice_type=notice_type)

    allowed_candidates = [
        item for item in prepared_candidates if item.get("source_class") in allowed_source_classes
    ]
    if not allowed_candidates:
        return _build_skip_meta("pool_empty", [], aliases, article_time, notice_type=notice_type)

    valid_candidates = []
    if aliases:
        valid_candidates = [
            item
            for item in allowed_candidates
            if _match_alias(item["candidate_text"], aliases)
            and _candidate_within_window(article_time, item["candidate_time"])
        ]
    same_account_candidates = []
    used_handles = {
        (first_quote.get("handle") or "").lower(),
        (first_quote.get("quote_account") or "").lower(),
    }
    for item in valid_candidates:
        quote_handle = _candidate_display_handle(item["candidate"]).lower()
        if item["media_url"] == first_quote.get("url"):
            same_account_candidates.append(item)
            continue
        if quote_handle and quote_handle in used_handles:
            same_account_candidates.append(item)
    if valid_candidates and len(same_account_candidates) == len(valid_candidates):
        return _build_skip_meta(
            "same_account_excluded",
            same_account_candidates,
            aliases,
            article_time,
            notice_type=notice_type,
        )

    if aliases:
        alias_matches = [
            item for item in allowed_candidates if _match_alias(item["candidate_text"], aliases)
        ]
        if alias_matches and not any(
            _candidate_within_window(article_time, item["candidate_time"])
            for item in alias_matches
        ):
            return _build_skip_meta(
                "time_window_exceeded",
                alias_matches,
                aliases,
                article_time,
                notice_type=notice_type,
            )

    return _build_skip_meta(
        "score_below_threshold",
        allowed_candidates,
        aliases,
        article_time,
        notice_type=notice_type,
    )


def _social_second_quote_skip_meta(
    prepared_candidates: list[dict[str, Any]],
    aliases: list[str],
    article_time: datetime | None,
    first_quote: dict[str, str],
) -> dict[str, Any]:
    base_meta = _second_quote_skip_meta(
        prepared_candidates,
        aliases,
        article_time,
        first_quote,
        {"media"},
    )
    if base_meta.get("skip_reason") != "score_below_threshold":
        return base_meta

    article_text = _normalize_name(
        " ".join(
            str(first_quote.get(field) or "")
            for field in ("source_title", "source_summary")
        )
    )
    if not article_text:
        return base_meta

    alias_matches = [
        item
        for item in prepared_candidates
        if item.get("source_class") == "media"
        and _match_alias(str(item.get("candidate_text") or ""), aliases)
        and _candidate_within_window(article_time, item.get("candidate_time"))
    ]
    if not alias_matches:
        return base_meta
    if any(
        _shared_social_detail_token(
            article_text,
            str(item.get("candidate_text") or ""),
            aliases,
        )
        for item in alias_matches
    ):
        return base_meta
    updated = dict(base_meta)
    updated["skip_reason"] = "topic_detail_mismatch"
    return updated


def _primary_quote_skip_meta(
    prepared_candidates: list[dict[str, Any]],
    aliases: list[str],
    article_time: datetime | None,
    notice_type: str = "",
) -> dict[str, Any]:
    if not prepared_candidates:
        return _build_skip_meta("pool_empty", [], aliases, article_time, notice_type=notice_type)
    if not aliases:
        return _build_skip_meta("other", prepared_candidates, aliases, article_time, notice_type=notice_type)

    alias_matches = [item for item in prepared_candidates if _match_alias(item["candidate_text"], aliases)]
    if alias_matches and not any(
        _candidate_within_window(article_time, item["candidate_time"])
        for item in alias_matches
    ):
        return _build_skip_meta(
            "time_window_exceeded",
            alias_matches,
            aliases,
            article_time,
            notice_type=notice_type,
        )
    return _build_skip_meta(
        "score_below_threshold",
        prepared_candidates,
        aliases,
        article_time,
        notice_type=notice_type,
    )


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
    # Article-side text used for event keyword overlap detection (B).
    # Falls back through fields likely to carry the headline event.
    article_event_text = _normalize_name(
        " ".join(
            str(entry.get(field) or "")
            for field in ("title", "summary", "notice_type", "story_kind")
        )
    )
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

        social_detail_token = ""
        if route == "social_secondary":
            social_detail_token = _shared_social_detail_token(
                article_event_text,
                candidate_text,
                aliases,
            )
            if not social_detail_token:
                continue

        candidate_time = _parse_datetime(candidate.get("created_at"))
        time_step = 0
        if article_time and candidate_time:
            delta_hours = abs((article_time - candidate_time).total_seconds()) / 3600.0
            if delta_hours > _NOTICE_TWEET_WINDOW_HOURS:
                continue
            time_score = max(0, int(_NOTICE_TWEET_WINDOW_HOURS - delta_hours))
            time_step = _time_step_bonus(article_time, candidate_time, delta_hours)
            match_reason = "composite"
        else:
            time_score = 0
            match_reason = "player_name_match"

        notice_bonus = 0
        if notice_type and notice_type in candidate_text:
            notice_bonus = 10

        event_bonus = (
            _EVENT_KEYWORD_BONUS
            if _shared_event_token(article_event_text, candidate_text)
            else 0
        )
        detail_bonus = _SOCIAL_SECONDARY_DETAIL_BONUS if social_detail_token else 0

        ranked_quotes.append(
            _build_matched_quote(
                candidate,
                source_class,
                section_label,
                quote_type,
                "topic_detail_overlap" if social_detail_token else match_reason,
                priority_score
                + 100
                + time_score
                + notice_bonus
                + event_bonus
                + detail_bonus
                + time_step,
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
        "source_title": (entry.get("title") or "").strip(),
        "source_summary": (entry.get("summary") or "").strip(),
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
    # issue #44 follow-up (2026-05-17 user lock): merge bug 観察 log。
    # post 68872 (title=ノック話 / source_url=SANSPO 父300HR) のように
    # entry.title と source_url の content が不一致な状態 (= upstream で
    # fan-voice cluster と media tweet が merge された結果) を診断する。
    # source_class=="media" の場合に entry 構造を構造化 log で出力し、
    # 翌日の prod log で merge 発生 path を pinpoint する。 挙動変更なし。
    try:
        source_class = source_quote.get("source_class") or _candidate_source_class({
            "source_url": source_quote.get("url") or "",
            "source_name": source_quote.get("source_name") or "",
        })
        if source_class == "media":
            import json as _json_log
            import logging as _logging_log
            _logger = _logging_log.getLogger("media_xpost_selector")
            _logger.info(_json_log.dumps({
                "event": "media_primary_attach_decision",
                "source_url": source_quote.get("url") or "",
                "source_class": source_class,
                "source_handle": source_quote.get("handle") or "",
                "entry_title_head": (str(entry.get("title") or "")[:80]),
                "entry_summary_head": (str(entry.get("summary") or "")[:80]),
                "entry_source_type": str(entry.get("source_type") or ""),
                "entry_story_kind": str(entry.get("story_kind") or ""),
                "entry_topic_aliases_count": len(entry.get("topic_aliases") or []),
                "media_quote_pool_size": len(media_quote_pool or []),
                "decision": "attach_primary",
            }, ensure_ascii=False))
    except Exception:
        pass
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


def evaluate_media_quote_selection(
    entry: dict[str, Any],
    max_count: int = 1,
    media_quote_pool: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selector_type = _selector_type(entry)
    is_target = selector_type != "none"
    if max_count <= 0:
        return {
            "quotes": [],
            "selector_type": selector_type,
            "is_target": is_target,
            "skip_meta": None,
        }

    media_quote_pool = media_quote_pool or []
    article_time = _parse_datetime(entry.get("created_at"))
    source_type = (entry.get("source_type") or "").strip()
    story_kind = (entry.get("story_kind") or "").strip()

    if source_type == "social_news":
        effective_max_count = _effective_social_max_count(entry, max_count)
        quotes = _select_social_source_quotes(entry, media_quote_pool, effective_max_count)
        skip_meta = None
        if not quotes:
            skip_meta = {
                "skip_reason": "other",
                "pool_size_checked": 0,
                "best_candidate_score": None,
                "best_candidate_handle": "",
                "best_candidate_age_hours": None,
            }
        elif effective_max_count > len(quotes):
            topic_aliases = _aliases_for_social(entry)
            prepared_candidates = _prepare_route_candidates(media_quote_pool, "social_secondary")
            if not topic_aliases:
                skip_meta = _build_skip_meta("other", prepared_candidates, topic_aliases, article_time)
            else:
                skip_meta = _second_quote_skip_meta(
                    prepared_candidates,
                    topic_aliases,
                    article_time,
                    quotes[0],
                    {"media"},
                )
                if skip_meta and skip_meta.get("skip_reason") == "score_below_threshold":
                    quotes[0]["source_title"] = str(entry.get("title") or "").strip()
                    quotes[0]["source_summary"] = str(entry.get("summary") or "").strip()
                    skip_meta = _social_second_quote_skip_meta(
                        prepared_candidates,
                        topic_aliases,
                        article_time,
                        quotes[0],
                    )
        return {
            "quotes": quotes,
            "selector_type": selector_type,
            "is_target": is_target,
            "skip_meta": skip_meta,
        }

    if story_kind == "player_notice":
        notice_aliases = _aliases_for_notice(entry)
        notice_type = (entry.get("notice_type") or "").strip()
        quotes = _select_notice_quote(entry, media_quote_pool, max_count) if media_quote_pool else []
        skip_meta = None
        if len(quotes) < max_count:
            prepared_candidates = _prepare_route_candidates(media_quote_pool, "notice")
            if not quotes:
                skip_meta = _primary_quote_skip_meta(
                    prepared_candidates,
                    notice_aliases,
                    article_time,
                    notice_type=notice_type,
                )
            else:
                allowed_second_classes = {
                    "npb": {"official", "media"},
                    "official": {"media"},
                    "media": set(),
                }.get(quotes[0].get("source_class"), set())
                skip_meta = _second_quote_skip_meta(
                    prepared_candidates,
                    notice_aliases,
                    article_time,
                    quotes[0],
                    allowed_second_classes,
                    notice_type=notice_type,
                )
        return {
            "quotes": quotes,
            "selector_type": selector_type,
            "is_target": is_target,
            "skip_meta": skip_meta,
        }

    if story_kind == "manager_quote":
        manager_aliases = _aliases_for_manager(entry)
        quotes = _select_manager_quote(entry, media_quote_pool, max_count) if media_quote_pool else []
        skip_meta = None
        if len(quotes) < max_count:
            prepared_candidates = _prepare_route_candidates(media_quote_pool, "manager")
            if not quotes:
                skip_meta = _primary_quote_skip_meta(prepared_candidates, manager_aliases, article_time)
            else:
                allowed_second_classes = {
                    "official": {"media"},
                    "media": set(),
                }.get(quotes[0].get("source_class"), set())
                skip_meta = _second_quote_skip_meta(
                    prepared_candidates,
                    manager_aliases,
                    article_time,
                    quotes[0],
                    allowed_second_classes,
                )
        return {
            "quotes": quotes,
            "selector_type": selector_type,
            "is_target": is_target,
            "skip_meta": skip_meta,
        }

    return {
        "quotes": [],
        "selector_type": selector_type,
        "is_target": is_target,
        "skip_meta": None,
    }


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
    return evaluate_media_quote_selection(
        entry,
        max_count=max_count,
        media_quote_pool=media_quote_pool,
    )["quotes"]
