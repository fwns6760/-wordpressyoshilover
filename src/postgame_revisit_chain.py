"""Postgame revisit derivative selection for the fixed-lane hook.

This module stays pure on purpose. It only inspects the accepted postgame
context and decides which derivative candidates should be emitted next.
Network calls, WordPress writes, and duplicate checks remain in the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
import re
from typing import Any, Mapping, Sequence

from src.tag_category_guard import normalize_tags


ROUTE_FIXED_PRIMARY_DERIVATIVE = "fixed_primary_derivative"
ROUTE_DEFERRED_PICKUP_DERIVATIVE = "deferred_pickup_derivative"
MAX_DERIVATIVES_PER_GAME = 4
POSTGAME_WINDOW_HOURS = 24
PRIMARY_TRUST_TIER = "T1"
FACT_NOTICE_SUBTYPE = "fact_notice"
FARM_SUBTYPE = "farm"

_WHITESPACE_RE = re.compile(r"[\s\u3000]+")
_STRONG_PLAYER_IMPACTS = {
    "game_deciding",
    "game_winning",
    "win_loss_swing",
    "special_performance",
    "milestone",
}
_STRONG_MANAGER_TOPICS = {
    "tactics",
    "strategy",
    "player_eval",
    "player_evaluation",
    "next_game_plan",
    "next_game",
}
_TRANSACTION_KIND_TAGS = {
    "announcement": "公示",
    "register": "公示",
    "deregister": "公示",
    "injury": "故障",
    "contract": "契約",
}
_DATA_MILESTONE_KINDS = {
    "team_record",
    "personal_milestone",
    "league_rank",
}


@dataclass(frozen=True)
class PostgameDerivativeCandidate:
    family: str
    subtype: str
    route: str
    title: str
    body_html: str
    category: str
    tags: tuple[str, ...]
    candidate_key: str
    source_url: str
    source_kind: str
    trust_tier: str
    discriminator: str
    metadata: dict[str, Any]


def aggregate_postgame_derivatives(
    postgame: Mapping[str, Any],
    *,
    now: datetime | None = None,
    window_hours: int = POSTGAME_WINDOW_HOURS,
) -> list[PostgameDerivativeCandidate]:
    """Return derivative candidates for an accepted postgame context."""

    current_time = _normalize_datetime(now or datetime.now())
    if _is_live_state(postgame):
        return []
    if not _is_within_window(postgame, current_time, window_hours=window_hours):
        return []

    derivatives: list[PostgameDerivativeCandidate] = []
    derivatives.extend(_check_player_highlight(postgame))
    derivatives.extend(_check_manager_comment(postgame))
    derivatives.extend(_check_transaction(postgame, current_time, window_hours=window_hours))
    derivatives.extend(_check_data_milestone(postgame))
    return derivatives[:MAX_DERIVATIVES_PER_GAME]


def _check_player_highlight(postgame: Mapping[str, Any]) -> list[PostgameDerivativeCandidate]:
    player_weights = _extract_records(postgame, "player_weights", "featured_players")
    if not player_weights:
        return []

    weighted = sorted(
        (
            {
                **record,
                "player": str(record.get("player") or record.get("tag") or "").strip(),
                "weight": float(record.get("weight") or 0),
            }
            for record in player_weights
        ),
        key=lambda record: record["weight"],
        reverse=True,
    )
    if not weighted or not weighted[0]["player"]:
        return []

    top = weighted[0]
    second_weight = weighted[1]["weight"] if len(weighted) > 1 else 0.0
    if top["weight"] < 0.5 or (second_weight and top["weight"] - second_weight < 0.15):
        return []
    if not _is_notable_player_record(top):
        return []

    player = str(top["player"]).strip()
    if _recent_player_derivative_count(postgame, player) >= 3:
        return []

    game_id = _game_id(postgame)
    if not game_id:
        return []
    trust_tier = _entry_trust_tier(top, postgame)
    achievement = str(top.get("achievement") or top.get("summary") or "").strip()
    title = str(top.get("title") or f"{player}が主役、試合後に振り返りたい働き").strip()
    body_html = str(top.get("body_html") or _player_body_html(player, achievement, postgame)).strip()
    candidate_key = _build_candidate_key("player", game_id, player, str(top.get("metric_slug") or "highlight"))
    return [
        _build_candidate(
            family="player",
            subtype=str(top.get("subtype") or FACT_NOTICE_SUBTYPE),
            route=_route_for_trust(trust_tier),
            title=title,
            body_html=body_html,
            category="選手情報",
            tags=(player, "試合結果"),
            candidate_key=candidate_key,
            source_url=_entry_source_url(top, postgame),
            source_kind=_entry_source_kind(top, postgame),
            trust_tier=trust_tier,
            discriminator=player,
            metadata={
                "subject": player,
                "game_id": game_id,
                "result_token": _result_token(postgame),
                "achievement": achievement,
                "parent_candidate_key": _parent_candidate_key(postgame),
            },
        )
    ]


def _check_manager_comment(postgame: Mapping[str, Any]) -> list[PostgameDerivativeCandidate]:
    comments = _extract_records(postgame, "manager_comments", "manager_comment")
    for comment in comments:
        quote = str(comment.get("quote") or comment.get("comment") or "").strip()
        topics = {_normalize_token(topic) for topic in _sequence(comment.get("topics"))}
        if len(quote) < 300:
            continue
        if not topics.intersection(_STRONG_MANAGER_TOPICS):
            continue
        speaker = str(comment.get("speaker") or "監督").strip()
        game_id = _game_id(postgame)
        if not game_id:
            continue
        trust_tier = _entry_trust_tier(comment, postgame)
        context_slug = str(comment.get("context_slug") or "postgame").strip()
        title = str(comment.get("title") or f"{speaker}の試合後コメント、次戦へどうつながるか").strip()
        body_html = str(comment.get("body_html") or _manager_body_html(speaker, quote)).strip()
        candidate_key = _build_candidate_key("manager", game_id, speaker, context_slug)
        return [
            _build_candidate(
                family="manager",
                subtype=str(comment.get("subtype") or FACT_NOTICE_SUBTYPE),
                route=_route_for_trust(trust_tier),
                title=title,
                body_html=body_html,
                category="首脳陣",
                tags=(speaker, "コメント"),
                candidate_key=candidate_key,
                source_url=_entry_source_url(comment, postgame),
                source_kind=_entry_source_kind(comment, postgame),
                trust_tier=trust_tier,
                discriminator=context_slug,
                metadata={
                    "speaker": speaker,
                    "context_slug": context_slug,
                    "game_id": game_id,
                    "parent_candidate_key": _parent_candidate_key(postgame),
                },
            )
        ]
    return []


def _check_transaction(
    postgame: Mapping[str, Any],
    now: datetime,
    *,
    window_hours: int,
) -> list[PostgameDerivativeCandidate]:
    game_id = _game_id(postgame)
    if not game_id:
        return []

    accepted_at = _accepted_at(postgame, now)
    derivatives: list[PostgameDerivativeCandidate] = []
    for record in _extract_records(postgame, "transaction_events", "transactions"):
        notice_kind = _normalize_token(
            record.get("notice_kind") or record.get("transaction_type") or record.get("kind")
        )
        if notice_kind not in _TRANSACTION_KIND_TAGS:
            continue
        observed_at = _normalize_datetime(_coerce_datetime(record.get("observed_at")) or accepted_at)
        if abs(observed_at - accepted_at) > timedelta(hours=window_hours):
            continue
        subject = str(record.get("subject") or record.get("player") or "").strip()
        if not subject:
            continue
        trust_tier = _entry_trust_tier(record, postgame)
        title = str(record.get("title") or f"{subject}に関する発表、試合後24時間で追いたい動き").strip()
        body_html = str(record.get("body_html") or _transaction_body_html(subject, notice_kind, record)).strip()
        candidate_key = _build_candidate_key("transaction", game_id, subject, notice_kind)
        derivatives.append(
            _build_candidate(
                family="transaction",
                subtype=str(record.get("subtype") or FACT_NOTICE_SUBTYPE),
                route=_route_for_trust(trust_tier),
                title=title,
                body_html=body_html,
                category="選手情報",
                tags=(subject, _TRANSACTION_KIND_TAGS[notice_kind]),
                candidate_key=candidate_key,
                source_url=_entry_source_url(record, postgame),
                source_kind=_entry_source_kind(record, postgame),
                trust_tier=trust_tier,
                discriminator=notice_kind,
                metadata={
                    "subject": subject,
                    "notice_kind": notice_kind,
                    "game_id": game_id,
                    "parent_candidate_key": _parent_candidate_key(postgame),
                },
            )
        )
    return derivatives


def _check_data_milestone(postgame: Mapping[str, Any]) -> list[PostgameDerivativeCandidate]:
    game_id = _game_id(postgame)
    if not game_id:
        return []

    derivatives: list[PostgameDerivativeCandidate] = []
    for record in _extract_records(postgame, "data_milestones", "data_points"):
        subject = str(record.get("subject") or record.get("player") or "").strip()
        tags = normalize_tags([subject, *list(record.get("tags") or [])])
        milestone_kind = _normalize_token(record.get("milestone_kind") or record.get("kind"))
        if not subject or "野球データ" not in tags:
            continue
        if milestone_kind not in _DATA_MILESTONE_KINDS:
            continue
        if bool(record.get("generic_update")):
            continue
        trust_tier = _entry_trust_tier(record, postgame)
        metric_slug = str(record.get("metric_slug") or milestone_kind).strip()
        title = str(record.get("title") or f"{subject}の到達データを整理、節目の意味を確認").strip()
        body_html = str(record.get("body_html") or _data_body_html(subject, record)).strip()
        candidate_key = _build_candidate_key("data", game_id, subject, metric_slug)
        derivatives.append(
            _build_candidate(
                family="data",
                subtype=str(record.get("subtype") or FACT_NOTICE_SUBTYPE),
                route=_route_for_trust(trust_tier),
                title=title,
                body_html=body_html,
                category="選手情報",
                tags=tuple(tags),
                candidate_key=candidate_key,
                source_url=_entry_source_url(record, postgame),
                source_kind=_entry_source_kind(record, postgame),
                trust_tier=trust_tier,
                discriminator=metric_slug,
                metadata={
                    "subject": subject,
                    "metric_slug": metric_slug,
                    "game_id": game_id,
                    "parent_candidate_key": _parent_candidate_key(postgame),
                },
            )
        )
    return derivatives


def _build_candidate(
    *,
    family: str,
    subtype: str,
    route: str,
    title: str,
    body_html: str,
    category: str,
    tags: Sequence[str],
    candidate_key: str,
    source_url: str,
    source_kind: str,
    trust_tier: str,
    discriminator: str,
    metadata: Mapping[str, Any],
) -> PostgameDerivativeCandidate:
    normalized_tags = tuple(normalize_tags(list(tags)))
    return PostgameDerivativeCandidate(
        family=family,
        subtype=subtype if subtype in {FACT_NOTICE_SUBTYPE, FARM_SUBTYPE} else FACT_NOTICE_SUBTYPE,
        route=route,
        title=title,
        body_html=body_html,
        category=category,
        tags=normalized_tags,
        candidate_key=candidate_key,
        source_url=source_url,
        source_kind=source_kind,
        trust_tier=trust_tier,
        discriminator=discriminator,
        metadata=dict(metadata),
    )


def _player_body_html(player: str, achievement: str, postgame: Mapping[str, Any]) -> str:
    summary = achievement or str(postgame.get("title") or "").strip()
    parts = [
        f"<p>{escape(player)}を主役として切り出す候補です。</p>",
        f"<p>{escape(summary)}</p>" if summary else "",
    ]
    return "".join(part for part in parts if part)


def _manager_body_html(speaker: str, quote: str) -> str:
    return "".join(
        [
            f"<p>{escape(speaker)}のコメントを核に切り出す候補です。</p>",
            f"<blockquote>{escape(quote)}</blockquote>",
        ]
    )


def _transaction_body_html(subject: str, notice_kind: str, record: Mapping[str, Any]) -> str:
    summary = str(record.get("summary") or record.get("detail") or "").strip()
    label = _TRANSACTION_KIND_TAGS.get(notice_kind, notice_kind)
    parts = [f"<p>{escape(subject)}の{escape(label)}を整理する候補です。</p>"]
    if summary:
        parts.append(f"<p>{escape(summary)}</p>")
    return "".join(parts)


def _data_body_html(subject: str, record: Mapping[str, Any]) -> str:
    summary = str(record.get("summary") or record.get("detail") or "").strip()
    parts = [f"<p>{escape(subject)}のデータ節目を整理する候補です。</p>"]
    if summary:
        parts.append(f"<p>{escape(summary)}</p>")
    return "".join(parts)


def _route_for_trust(trust_tier: str) -> str:
    return ROUTE_FIXED_PRIMARY_DERIVATIVE if trust_tier == PRIMARY_TRUST_TIER else ROUTE_DEFERRED_PICKUP_DERIVATIVE


def _is_notable_player_record(record: Mapping[str, Any]) -> bool:
    if bool(record.get("game_deciding")) or bool(record.get("special_performance")):
        return True
    impact = _normalize_token(record.get("impact"))
    if impact in _STRONG_PLAYER_IMPACTS:
        return True
    achievement = str(record.get("achievement") or record.get("summary") or "").strip()
    return bool(achievement)


def _recent_player_derivative_count(postgame: Mapping[str, Any], player: str) -> int:
    metadata = _metadata(postgame)
    recent = metadata.get("recent_player_derivative_games") or postgame.get("recent_player_derivative_games") or {}
    if not isinstance(recent, Mapping):
        return 0
    values = recent.get(player) or recent.get(_normalize_subject(player)) or []
    return len({str(value or "").strip() for value in _sequence(values) if str(value or "").strip()})


def _extract_records(postgame: Mapping[str, Any], *keys: str) -> list[dict[str, Any]]:
    metadata = _metadata(postgame)
    for key in keys:
        if key in postgame:
            return _as_record_list(postgame.get(key))
        if key in metadata:
            return _as_record_list(metadata.get(key))
    return []


def _as_record_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _metadata(postgame: Mapping[str, Any]) -> dict[str, Any]:
    metadata = postgame.get("metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _game_id(postgame: Mapping[str, Any]) -> str:
    metadata = _metadata(postgame)
    return str(postgame.get("game_id") or metadata.get("game_id") or "").strip()


def _result_token(postgame: Mapping[str, Any]) -> str:
    metadata = _metadata(postgame)
    return str(postgame.get("result_token") or metadata.get("result_token") or "").strip()


def _parent_candidate_key(postgame: Mapping[str, Any]) -> str:
    metadata = _metadata(postgame)
    return str(postgame.get("candidate_key") or metadata.get("candidate_key") or "").strip()


def _entry_trust_tier(record: Mapping[str, Any], postgame: Mapping[str, Any]) -> str:
    metadata = _metadata(postgame)
    return str(
        record.get("trust_tier")
        or metadata.get("primary_trust_tier")
        or postgame.get("trust_tier")
        or ""
    ).strip()


def _entry_source_url(record: Mapping[str, Any], postgame: Mapping[str, Any]) -> str:
    metadata = _metadata(postgame)
    return str(record.get("source_url") or postgame.get("source_url") or metadata.get("source_url") or "").strip()


def _entry_source_kind(record: Mapping[str, Any], postgame: Mapping[str, Any]) -> str:
    metadata = _metadata(postgame)
    return str(
        record.get("source_kind")
        or postgame.get("source_kind")
        or metadata.get("pickup_source_kind")
        or ""
    ).strip()


def _accepted_at(postgame: Mapping[str, Any], fallback: datetime) -> datetime:
    metadata = _metadata(postgame)
    accepted_at = _coerce_datetime(
        postgame.get("accepted_at")
        or metadata.get("accepted_at")
        or metadata.get("postgame_accepted_at")
        or metadata.get("observed_at")
        or metadata.get("created_at")
        or ""
    )
    return _normalize_datetime(accepted_at or fallback)


def _is_live_state(postgame: Mapping[str, Any]) -> bool:
    metadata = _metadata(postgame)
    state_values = [
        postgame.get("post_state"),
        postgame.get("game_state"),
        postgame.get("state"),
        postgame.get("subtype"),
        metadata.get("post_state"),
        metadata.get("game_state"),
        metadata.get("state"),
        metadata.get("subtype"),
        metadata.get("article_subtype"),
    ]
    normalized = {_normalize_token(value) for value in state_values if str(value or "").strip()}
    return any(value.startswith("live") or value == "live_anchor" for value in normalized)


def _is_within_window(postgame: Mapping[str, Any], now: datetime, *, window_hours: int) -> bool:
    accepted_at = _accepted_at(postgame, now)
    if now < accepted_at:
        return True
    return now - accepted_at <= timedelta(hours=window_hours)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _build_candidate_key(family: str, game_id: str, subject: str, discriminator: str) -> str:
    normalized_game_id = _normalize_token(game_id)
    normalized_subject = _normalize_subject(subject)
    normalized_discriminator = _normalize_token(discriminator)
    return f"postgame_{family}:{normalized_game_id}:{normalized_subject}:{normalized_discriminator}"


def _normalize_token(value: Any) -> str:
    text = _WHITESPACE_RE.sub("", str(value or ""))
    return text.replace("：", "-").replace(":", "-").strip("-").lower()


def _normalize_subject(value: Any) -> str:
    text = _WHITESPACE_RE.sub("", str(value or ""))
    text = text.replace("：", "-").replace(":", "-")
    text = re.sub(r"[、,/／]+", "+", text)
    text = re.sub(r"\++", "+", text)
    return text.strip("+")


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    if value is None:
        return []
    return [value]
