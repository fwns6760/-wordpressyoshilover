"""Fixed-lane Draft runner with trust-tier routing for MVP + parity pickup.

The default fetch path still targets the NPB roster notice page, while the
routing layer accepts the wider 037 pickup contract. The original 028 MVP
families still own fixed-lane draft creation. Parity-expansion families are
picked up, normalized, de-duplicated, and labeled as deferred until a future
lane consumes them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from html import escape, unescape
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

import requests

from src.eyecatch_fallback import maybe_generate_structured_eyecatch_media
from src.source_id import source_id as build_source_id
from src.source_trust import classify_url
from src.tag_category_guard import normalize_tags
from src.wp_client import WPClient


NPB_NOTICE_URL = "https://npb.jp/announcement/roster/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_CANARY_POSTS = 1

TARGET_SUBTYPE = "fact_notice"
TARGET_ARTICLE_TYPE = "transaction_notice"
TARGET_BATCH_SOURCE = "sync"
TARGET_TEAM = "読売ジャイアンツ"
TARGET_PARENT_CATEGORY_NAME = TARGET_TEAM

TRUST_TIER_T1 = "T1"
TRUST_TIER_T2 = "T2"
TRUST_TIER_T3 = "T3"
TARGET_LANE_FIXED = "fixed_lane"
TARGET_LANE_AI = "ai_lane"
ROUTE_FIXED_PRIMARY = "fixed_primary"
ROUTE_AWAIT_PRIMARY = "await_primary"
ROUTE_DUPLICATE_ABSORBED = "duplicate_absorbed"
ROUTE_AMBIGUOUS_SUBJECT = "ambiguous_subject"
ROUTE_OUT_OF_MVP_FAMILY = "out_of_mvp_family"
ROUTE_DEFERRED_PICKUP = "deferred_pickup"
ROUTE_OUTCOMES = (
    ROUTE_FIXED_PRIMARY,
    ROUTE_AWAIT_PRIMARY,
    ROUTE_DUPLICATE_ABSORBED,
    ROUTE_AMBIGUOUS_SUBJECT,
    ROUTE_OUT_OF_MVP_FAMILY,
    ROUTE_DEFERRED_PICKUP,
)
_SOCIAL_HOSTS = {"x.com", "twitter.com"}

SOURCE_KIND_OFFICIAL_WEB = "official_web"
SOURCE_KIND_NPB = "npb"
SOURCE_KIND_MAJOR_RSS = "major_rss"
SOURCE_KIND_TEAM_X = "team_x"
SOURCE_KIND_REPORTER_X = "reporter_x"
SOURCE_KIND_PROGRAM_TABLE = "program_table"
SOURCE_KIND_FARM_INFO = "farm_info"
SOURCE_KIND_TV_RADIO_COMMENT = "tv_radio_comment"
SOURCE_KIND_COMMENT_QUOTE = "comment_quote"
SOURCE_KIND_PLAYER_STATS_FEED = "player_stats_feed"
PICKUP_SOURCE_KINDS = (
    SOURCE_KIND_OFFICIAL_WEB,
    SOURCE_KIND_NPB,
    SOURCE_KIND_MAJOR_RSS,
    SOURCE_KIND_TEAM_X,
    SOURCE_KIND_REPORTER_X,
    SOURCE_KIND_PROGRAM_TABLE,
    SOURCE_KIND_FARM_INFO,
    SOURCE_KIND_TV_RADIO_COMMENT,
    SOURCE_KIND_COMMENT_QUOTE,
    SOURCE_KIND_PLAYER_STATS_FEED,
)

EXIT_OK = 0
EXIT_WP_POST_DRY_RUN_FAILED = 40
EXIT_WP_POST_FAILED = 41
EXIT_INPUT_ERROR = 42
ENV_INTAKE_FILE = "NOTICE_FIXED_LANE_INTAKE_FILE"
ENV_INTAKE_SOURCE = "NOTICE_FIXED_LANE_INTAKE_SOURCE"
INTAKE_SOURCE_RSS_FETCHER_LOG = "rss_fetcher_log"

_DATE_HEADING_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日の出場選手登録、登録抹消")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?>.*?</\1>")
_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_TAG_RE = re.compile(r"<[^>]+>")
_NUMBER_RE = re.compile(r"\d{1,3}")
_LOG_TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_COMPACT_DATE_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")
_DATE_SLASH_RE = re.compile(r"(?:(\d{4})/)?(\d{1,2})/(\d{1,2})")
_DATE_JP_RE = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日")
_SCORE_TOKEN_RE = re.compile(r"(\d{1,2})\s*[-－–]\s*(\d{1,2})")

_NPB_TEAMS = {
    "阪神タイガース",
    "横浜DeNAベイスターズ",
    "読売ジャイアンツ",
    "中日ドラゴンズ",
    "広島東洋カープ",
    "東京ヤクルトスワローズ",
    "福岡ソフトバンクホークス",
    "北海道日本ハムファイターズ",
    "オリックス・バファローズ",
    "東北楽天ゴールデンイーグルス",
    "埼玉西武ライオンズ",
    "千葉ロッテマリーンズ",
}
_POSITION_LABELS = {"投手", "捕手", "内野手", "外野手"}
_DUPLICATE_LOOKUP_FIELDS = ("id", "status", "slug", "generated_slug", "title", "meta", "date")
_TEAM_CODE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("t", ("阪神", "タイガース", "hanshin", "tigers")),
    ("db", ("dena", "baystars", "ベイスターズ", "横浜")),
    ("c", ("広島", "カープ", "hiroshima", "carp")),
    ("d", ("中日", "ドラゴンズ", "chunichi", "dragons")),
    ("s", ("ヤクルト", "スワローズ", "swallows")),
    ("b", ("オリックス", "バファローズ", "orix", "buffaloes")),
    ("m", ("ロッテ", "マリーンズ", "marines")),
    ("e", ("楽天", "イーグルス", "eagles")),
    ("h", ("ソフトバンク", "ホークス", "hawks")),
    ("f", ("日本ハム", "ファイターズ", "日ハム", "fighters")),
    ("l", ("西武", "ライオンズ", "lions")),
    ("ht", ("ハヤテ", "hayate")),
)


@dataclass(frozen=True)
class FamilySpec:
    family: str
    subtype: str
    category_name: str
    default_tags: tuple[str, ...]
    candidate_id_field: str
    lane_target: str


@dataclass(frozen=True)
class NoticeEntry:
    action: str
    position: str
    number: str
    player_name: str


@dataclass(frozen=True)
class NoticeCandidate:
    source_url: str
    source_id: str
    notice_date: str
    title: str
    body_html: str
    metadata: dict[str, Any]
    candidate_slug: str = ""
    family: str = TARGET_ARTICLE_TYPE
    candidate_key: str = ""
    subject: str = ""
    notice_kind: str = ""
    air_date: str = ""
    program_slug: str = ""
    game_id: str = ""


@dataclass(frozen=True)
class ProcessResult:
    created_post_id: int | None
    duplicate_skip: bool
    route_outcomes: tuple[str, ...] = ()
    error_reason: str = ""
    attempted_create: bool = False


MVP_FAMILY_SPECS: dict[str, FamilySpec] = {
    "program_notice": FamilySpec(
        family="program_notice",
        subtype="fact_notice",
        category_name="球団情報",
        default_tags=("番組",),
        candidate_id_field="air_date",
        lane_target=TARGET_LANE_FIXED,
    ),
    "transaction_notice": FamilySpec(
        family="transaction_notice",
        subtype="fact_notice",
        category_name="選手情報",
        default_tags=("公示",),
        candidate_id_field="notice_date",
        lane_target=TARGET_LANE_FIXED,
    ),
    "probable_pitcher": FamilySpec(
        family="probable_pitcher",
        subtype="pregame",
        category_name="試合速報",
        default_tags=("予告先発",),
        candidate_id_field="game_id",
        lane_target=TARGET_LANE_FIXED,
    ),
    "farm_result": FamilySpec(
        family="farm_result",
        subtype="farm",
        category_name="ドラフト・育成",
        default_tags=("ファーム",),
        candidate_id_field="game_id",
        lane_target=TARGET_LANE_FIXED,
    ),
}

PARITY_FAMILY_SPECS: dict[str, FamilySpec] = {
    "lineup_notice": FamilySpec(
        family="lineup_notice",
        subtype="lineup",
        category_name="試合速報",
        default_tags=("スタメン",),
        candidate_id_field="candidate_key",
        lane_target=TARGET_LANE_AI,
    ),
    "comment_notice": FamilySpec(
        family="comment_notice",
        subtype="manager",
        category_name="首脳陣",
        default_tags=("コメント",),
        candidate_id_field="candidate_key",
        lane_target=TARGET_LANE_AI,
    ),
    "injury_notice": FamilySpec(
        family="injury_notice",
        subtype="fact_notice",
        category_name="選手情報",
        default_tags=("故障",),
        candidate_id_field="candidate_key",
        lane_target=TARGET_LANE_AI,
    ),
    "postgame_result": FamilySpec(
        family="postgame_result",
        subtype="postgame",
        category_name="試合速報",
        default_tags=("試合結果",),
        candidate_id_field="candidate_key",
        lane_target=TARGET_LANE_AI,
    ),
    "player_stat_update": FamilySpec(
        family="player_stat_update",
        subtype="fact_notice",
        category_name="選手情報",
        default_tags=("野球データ",),
        candidate_id_field="candidate_key",
        lane_target=TARGET_LANE_AI,
    ),
}

FAMILY_SPECS: dict[str, FamilySpec] = {**MVP_FAMILY_SPECS, **PARITY_FAMILY_SPECS}


def supported_mvp_families() -> tuple[str, ...]:
    return tuple(MVP_FAMILY_SPECS.keys())


def supported_pickup_families() -> tuple[str, ...]:
    return tuple(FAMILY_SPECS.keys())


def supported_pickup_source_kinds() -> tuple[str, ...]:
    return PICKUP_SOURCE_KINDS


def _emit_event(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _normalize_token(value: str) -> str:
    text = re.sub(r"[\s\u3000]+", "", str(value or ""))
    return text.replace("：", "-").replace(":", "-").strip("-")


def _normalize_subject(value: str) -> str:
    subject = _normalize_token(value)
    subject = re.sub(r"[、,／/]+", "+", subject)
    return re.sub(r"\++", "+", subject).strip("+")


def _candidate_metadata_key(candidate: NoticeCandidate) -> str:
    return str(candidate.metadata.get("candidate_key") or candidate.candidate_key or "").strip()


def _candidate_metadata_family(candidate: NoticeCandidate) -> str:
    return str(candidate.family or candidate.metadata.get("article_type") or "").strip()


def _build_candidate_id(source_url: str, article_type: str, discriminator: str) -> str:
    return f"{build_source_id(source_url)}:{article_type}:{discriminator}"


def _build_candidate_slug(candidate_key: str) -> str:
    family, _, remainder = candidate_key.partition(":")
    family_slug = re.sub(r"[^a-z0-9]+", "-", family.replace("_", "-").lower()).strip("-") or "fixed-lane"
    hint = re.sub(r"[^a-z0-9]+", "-", remainder.lower()).strip("-")[:32].strip("-")
    digest = sha1(candidate_key.encode("utf-8")).hexdigest()[:10]
    return f"{family_slug}-{hint}-{digest}" if hint else f"{family_slug}-{digest}"


def _build_family_candidate_key(
    family: str,
    *,
    notice_date: str = "",
    subject: str = "",
    notice_kind: str = "",
    air_date: str = "",
    program_slug: str = "",
    game_id: str = "",
    lineup_kind: str = "",
    speaker: str = "",
    context_slug: str = "",
    injury_status: str = "",
    result_token: str = "",
    stat_date: str = "",
    metric_slug: str = "",
) -> str:
    if family == "program_notice":
        return f"program_notice:{air_date}:{program_slug}" if air_date and program_slug else ""
    if family == "transaction_notice":
        normalized_subject = _normalize_subject(subject)
        normalized_kind = _normalize_token(notice_kind)
        if not notice_date or not normalized_subject or not normalized_kind:
            return ""
        return f"transaction_notice:{notice_date}:{normalized_subject}:{normalized_kind}"
    if family == "probable_pitcher":
        normalized_game_id = _normalize_token(game_id)
        return f"probable_pitcher:{normalized_game_id}" if normalized_game_id else ""
    if family == "farm_result":
        normalized_game_id = _normalize_token(game_id)
        return f"farm_result:{normalized_game_id}" if normalized_game_id else ""
    if family == "lineup_notice":
        normalized_game_id = _normalize_token(game_id)
        normalized_lineup_kind = _normalize_token(lineup_kind)
        if not normalized_game_id or not normalized_lineup_kind:
            return ""
        return f"lineup_notice:{normalized_game_id}:{normalized_lineup_kind}"
    if family == "comment_notice":
        normalized_speaker = _normalize_subject(speaker)
        normalized_context = _normalize_token(context_slug)
        if not notice_date or not normalized_speaker or not normalized_context:
            return ""
        return f"comment_notice:{notice_date}:{normalized_speaker}:{normalized_context}"
    if family == "injury_notice":
        normalized_subject = _normalize_subject(subject)
        normalized_status = _normalize_token(injury_status)
        if not notice_date or not normalized_subject or not normalized_status:
            return ""
        return f"injury_notice:{notice_date}:{normalized_subject}:{normalized_status}"
    if family == "postgame_result":
        normalized_game_id = _normalize_token(game_id)
        normalized_result = _normalize_token(result_token)
        if not normalized_game_id or not normalized_result:
            return ""
        return f"postgame_result:{normalized_game_id}:{normalized_result}"
    if family == "player_stat_update":
        normalized_subject = _normalize_subject(subject)
        normalized_metric = _normalize_token(metric_slug)
        if not stat_date or not normalized_subject or not normalized_metric:
            return ""
        return f"player_stat_update:{stat_date}:{normalized_subject}:{normalized_metric}"
    return ""


def _family_candidate_discriminator(
    spec: FamilySpec,
    *,
    notice_date: str,
    air_date: str,
    game_id: str,
    candidate_key: str,
) -> str:
    if spec.candidate_id_field == "notice_date":
        return notice_date
    if spec.candidate_id_field == "air_date":
        return air_date
    if spec.candidate_id_field == "candidate_key":
        return candidate_key
    return _normalize_token(game_id)


def _infer_pickup_source_kind(source_url: str, trust_tier: str) -> str:
    parsed = urlsplit(source_url)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()

    if host.endswith("npb.jp"):
        return SOURCE_KIND_NPB
    if host in _SOCIAL_HOSTS:
        if trust_tier == TRUST_TIER_T2:
            return SOURCE_KIND_TEAM_X
        if trust_tier == TRUST_TIER_T3:
            return SOURCE_KIND_REPORTER_X
    if "program" in path or "schedule" in path or "tv" in path:
        return SOURCE_KIND_PROGRAM_TABLE
    if "farm" in path or "2gun" in path or "minor" in path:
        return SOURCE_KIND_FARM_INFO
    if trust_tier == TRUST_TIER_T2:
        return SOURCE_KIND_MAJOR_RSS
    if trust_tier == TRUST_TIER_T1:
        return SOURCE_KIND_OFFICIAL_WEB
    return ""


def _normalize_pickup_source_kind(raw_value: Any, source_url: str, trust_tier: str) -> str:
    normalized = str(raw_value or "").strip().lower().replace("-", "_")
    if normalized in PICKUP_SOURCE_KINDS:
        return normalized
    return _infer_pickup_source_kind(source_url, trust_tier)


def _bundle_entry(source_url: str, trust_tier: str, *, role: str, source_kind: str) -> dict[str, str]:
    return {
        "url": source_url,
        "source_id": build_source_id(source_url),
        "trust_tier": trust_tier,
        "role": role,
        "source_kind": source_kind,
    }


def _dedupe_bundle_entries(entries: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        url = str(entry.get("url") or "").strip()
        source_id = str(entry.get("source_id") or build_source_id(url)).strip()
        trust_tier = str(entry.get("trust_tier") or "").strip()
        role = str(entry.get("role") or "").strip()
        source_kind = _normalize_pickup_source_kind(entry.get("source_kind"), url, trust_tier)
        marker = (source_id, trust_tier, role, source_kind)
        if not url or not source_id or marker in seen:
            continue
        seen.add(marker)
        deduped.append(
            {
                "url": url,
                "source_id": source_id,
                "trust_tier": trust_tier,
                "role": role,
                "source_kind": source_kind,
            }
        )
    return deduped


def _merge_source_lists(*lists: Sequence[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for values in lists:
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _candidate_source_bundle(candidate: NoticeCandidate) -> list[dict[str, str]]:
    bundle = candidate.metadata.get("source_bundle") or []
    return _dedupe_bundle_entries(bundle if isinstance(bundle, list) else [])


def _candidate_trigger_sources(candidate: NoticeCandidate) -> list[dict[str, str]]:
    trigger_sources = candidate.metadata.get("trigger_only_sources") or []
    return _dedupe_bundle_entries(trigger_sources if isinstance(trigger_sources, list) else [])


def _candidate_has_t1_source(candidate: NoticeCandidate) -> bool:
    return any(entry.get("trust_tier") == TRUST_TIER_T1 for entry in _candidate_source_bundle(candidate))


def _candidate_trust_rank(candidate: NoticeCandidate) -> int:
    tiers = {entry.get("trust_tier") for entry in _candidate_source_bundle(candidate)}
    if TRUST_TIER_T1 in tiers:
        return 3
    if TRUST_TIER_T2 in tiers:
        return 2
    if _candidate_trigger_sources(candidate):
        return 1
    return 0


def _merge_candidates(existing: NoticeCandidate, incoming: NoticeCandidate) -> NoticeCandidate:
    preferred = incoming if _candidate_trust_rank(incoming) > _candidate_trust_rank(existing) else existing
    other = existing if preferred is incoming else incoming
    metadata = dict(preferred.metadata)
    metadata["source_urls"] = _merge_source_lists(
        preferred.metadata.get("source_urls") or [],
        other.metadata.get("source_urls") or [],
    )
    metadata["source_bundle"] = _dedupe_bundle_entries(
        _candidate_source_bundle(preferred) + _candidate_source_bundle(other)
    )
    metadata["trigger_only_sources"] = _dedupe_bundle_entries(
        _candidate_trigger_sources(preferred) + _candidate_trigger_sources(other)
    )
    metadata["tags"] = normalize_tags(
        list(preferred.metadata.get("tags") or []) + list(other.metadata.get("tags") or [])
    )
    metadata["pickup_source_kinds"] = _merge_source_lists(
        preferred.metadata.get("pickup_source_kinds") or [],
        other.metadata.get("pickup_source_kinds") or [],
    )
    metadata["source_id"] = preferred.source_id
    metadata[WPClient.SOURCE_URL_META_KEY] = preferred.source_url
    metadata["primary_trust_tier"] = (
        TRUST_TIER_T1
        if _candidate_has_t1_source(preferred)
        else metadata.get("primary_trust_tier") or other.metadata.get("primary_trust_tier")
    )
    return NoticeCandidate(
        source_url=preferred.source_url,
        source_id=preferred.source_id,
        notice_date=preferred.notice_date or other.notice_date,
        title=preferred.title,
        body_html=preferred.body_html,
        metadata=metadata,
        candidate_slug=preferred.candidate_slug or other.candidate_slug,
        family=_candidate_metadata_family(preferred) or _candidate_metadata_family(other),
        candidate_key=_candidate_metadata_key(preferred) or _candidate_metadata_key(other),
        subject=preferred.subject or other.subject,
        notice_kind=preferred.notice_kind or other.notice_kind,
        air_date=preferred.air_date or other.air_date,
        program_slug=preferred.program_slug or other.program_slug,
        game_id=preferred.game_id or other.game_id,
    )


def _infer_trust_tier(source_url: str) -> str:
    host = (urlsplit(source_url).hostname or "").lower()
    trust = classify_url(source_url)
    if trust == "primary" and host not in _SOCIAL_HOSTS:
        return TRUST_TIER_T1
    if trust == "secondary":
        return TRUST_TIER_T2
    if host in _SOCIAL_HOSTS:
        return TRUST_TIER_T2 if trust == "primary" else TRUST_TIER_T3
    return ""


def _normalize_intake_item(item: dict[str, Any]) -> tuple[NoticeCandidate | None, str | None]:
    family = str(item.get("family") or "").strip()
    spec = FAMILY_SPECS.get(family)
    if spec is None:
        return None, ROUTE_OUT_OF_MVP_FAMILY

    source_url = str(item.get("source_url") or "").strip()
    source_id = build_source_id(source_url)
    trust_tier = str(item.get("trust_tier") or "").strip() or _infer_trust_tier(source_url)
    notice_date = str(item.get("notice_date") or "").strip()
    subject = str(item.get("subject") or "").strip()
    notice_kind = str(item.get("notice_kind") or "").strip()
    air_date = str(item.get("air_date") or "").strip()
    program_slug = str(item.get("program_slug") or "").strip()
    game_id = str(item.get("game_id") or "").strip()
    lineup_kind = str(item.get("lineup_kind") or "").strip()
    speaker = str(item.get("speaker") or "").strip()
    context_slug = str(item.get("context_slug") or "").strip()
    injury_status = str(item.get("injury_status") or "").strip()
    result_token = str(item.get("result_token") or "").strip()
    stat_date = str(item.get("stat_date") or "").strip()
    metric_slug = str(item.get("metric_slug") or "").strip()
    source_kind = _normalize_pickup_source_kind(item.get("source_kind"), source_url, trust_tier)
    candidate_key = _build_family_candidate_key(
        family,
        notice_date=notice_date,
        subject=subject,
        notice_kind=notice_kind,
        air_date=air_date,
        program_slug=program_slug,
        game_id=game_id,
        lineup_kind=lineup_kind,
        speaker=speaker,
        context_slug=context_slug,
        injury_status=injury_status,
        result_token=result_token,
        stat_date=stat_date,
        metric_slug=metric_slug,
    )
    if not candidate_key:
        return None, ROUTE_AMBIGUOUS_SUBJECT

    candidate_slug = str(item.get("candidate_slug") or _build_candidate_slug(candidate_key))
    source_bundle = []
    trigger_only_sources = []
    if trust_tier in {TRUST_TIER_T1, TRUST_TIER_T2} and source_url:
        source_bundle = [
            _bundle_entry(
                source_url,
                trust_tier,
                role="primary" if trust_tier == TRUST_TIER_T1 else "bundle",
                source_kind=source_kind,
            )
        ]
    elif trust_tier == TRUST_TIER_T3 and source_url:
        trigger_only_sources = [
            _bundle_entry(
                source_url,
                trust_tier,
                role="trigger",
                source_kind=source_kind,
            )
        ]

    discriminator = _family_candidate_discriminator(
        spec,
        notice_date=notice_date,
        air_date=air_date,
        game_id=game_id,
        candidate_key=candidate_key,
    )
    metadata: dict[str, Any] = {
        "subtype": spec.subtype,
        "article_subtype": spec.subtype,
        "article_type": family,
        "family": family,
        "category": str(item.get("category") or spec.category_name),
        "parent_category": str(item.get("parent_category") or TARGET_PARENT_CATEGORY_NAME),
        "tags": normalize_tags([*spec.default_tags, *list(item.get("tags") or [])]),
        "candidate_id": _build_candidate_id(source_url, family, discriminator),
        "candidate_key": candidate_key,
        "source_trust": "primary" if trust_tier == TRUST_TIER_T1 else "secondary",
        "pickup_mode": "collect_wide_assert_narrow",
        "pickup_source_kind": source_kind,
        "pickup_source_kinds": [source_kind] if source_kind else [],
        "lane_target": spec.lane_target,
        "batch_source": TARGET_BATCH_SOURCE,
        "source_id": source_id,
        "source_urls": [source_url] if source_url else [],
        "source_bundle": source_bundle,
        "trigger_only_sources": trigger_only_sources,
        "primary_trust_tier": trust_tier,
        WPClient.SOURCE_URL_META_KEY: source_url,
    }
    if notice_date:
        metadata["notice_date"] = notice_date
    if subject:
        metadata["subject"] = subject
    if notice_kind:
        metadata["notice_kind"] = notice_kind
    if air_date:
        metadata["air_date"] = air_date
    if program_slug:
        metadata["program_slug"] = program_slug
    if game_id:
        metadata["game_id"] = game_id
    if lineup_kind:
        metadata["lineup_kind"] = lineup_kind
    if speaker:
        metadata["speaker"] = speaker
    if context_slug:
        metadata["context_slug"] = context_slug
    if injury_status:
        metadata["injury_status"] = injury_status
    if result_token:
        metadata["result_token"] = result_token
    if stat_date:
        metadata["stat_date"] = stat_date
    if metric_slug:
        metadata["metric_slug"] = metric_slug
    metadata.update(dict(item.get("metadata") or {}))
    metadata["candidate_key"] = candidate_key
    metadata["source_urls"] = _merge_source_lists(metadata.get("source_urls") or [], [source_url])
    metadata["source_bundle"] = _dedupe_bundle_entries(
        source_bundle + list(metadata.get("source_bundle") or [])
    )
    metadata["trigger_only_sources"] = _dedupe_bundle_entries(
        trigger_only_sources + list(metadata.get("trigger_only_sources") or [])
    )
    metadata["pickup_source_kinds"] = _merge_source_lists(
        metadata.get("pickup_source_kinds") or [],
        [source_kind] if source_kind else [],
    )
    metadata["tags"] = normalize_tags(metadata.get("tags") or [])
    metadata["source_id"] = source_id
    metadata[WPClient.SOURCE_URL_META_KEY] = source_url
    return (
        NoticeCandidate(
            source_url=source_url,
            source_id=source_id,
            notice_date=notice_date,
            title=str(item.get("title") or "").strip(),
            body_html=str(item.get("body_html") or "").strip(),
            metadata=metadata,
            candidate_slug=candidate_slug,
            family=family,
            candidate_key=candidate_key,
            subject=subject,
            notice_kind=notice_kind,
            air_date=air_date,
            program_slug=program_slug,
            game_id=game_id,
        ),
        None,
    )


def _normalize_intake_items(items: Sequence[dict[str, Any]]) -> tuple[list[NoticeCandidate], list[str]]:
    candidates: list[NoticeCandidate] = []
    route_outcomes: list[str] = []
    for item in items:
        candidate, outcome = _normalize_intake_item(dict(item))
        if outcome:
            route_outcomes.append(outcome)
            continue
        if candidate is not None:
            candidates.append(candidate)
    return candidates, route_outcomes


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed-lane notice draft creation")
    parser.add_argument("--intake-file", help="Optional collector artifact path")
    parser.add_argument(
        "--intake-source",
        choices=(INTAKE_SOURCE_RSS_FETCHER_LOG,),
        help="Optional collector artifact type",
    )
    return parser


def _resolve_optional_intake(argv: Sequence[str] | None) -> tuple[str, str]:
    parser = _build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    intake_file = str(args.intake_file or os.getenv(ENV_INTAKE_FILE) or "").strip()
    intake_source = str(args.intake_source or os.getenv(ENV_INTAKE_SOURCE) or "").strip()
    if not intake_file:
        return "", ""
    if not intake_source:
        lowered_name = Path(intake_file).name.lower()
        if lowered_name == "rss_fetcher.log":
            intake_source = INTAKE_SOURCE_RSS_FETCHER_LOG
    if intake_source != INTAKE_SOURCE_RSS_FETCHER_LOG:
        raise ValueError("unsupported_intake_source")
    return intake_file, intake_source


def _log_timestamp(line: str) -> str:
    match = _LOG_TIMESTAMP_RE.match(line)
    return match.group(1) if match else ""


def _extract_json_payload(line: str) -> dict[str, Any] | None:
    start = line.find("{")
    end = line.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(line[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _valid_compact_date(year: str, month: str, day: str) -> str:
    try:
        year_num = int(year)
        month_num = int(month)
        day_num = int(day)
    except ValueError:
        return ""
    if month_num < 1 or month_num > 12 or day_num < 1 or day_num > 31:
        return ""
    return f"{year_num:04d}{month_num:02d}{day_num:02d}"


def _extract_observed_date(text: str, observed_at: str) -> str:
    for pattern in (_DATE_SLASH_RE, _DATE_JP_RE):
        for match in pattern.finditer(text):
            year = match.group(1) or (observed_at[:4] if observed_at else "")
            compact = _valid_compact_date(year, match.group(2), match.group(3))
            if compact:
                return compact
    for match in _COMPACT_DATE_RE.finditer(text):
        compact = _valid_compact_date(match.group(1), match.group(2), match.group(3))
        if compact:
            return compact
    if observed_at:
        return observed_at[:10].replace("-", "")
    return ""


def _extract_opponent_code(text: str) -> str:
    normalized = re.sub(r"[\s\u3000]+", "", unescape(text or "")).lower()
    for code, aliases in _TEAM_CODE_ALIASES:
        for alias in aliases:
            alias_key = re.sub(r"[\s\u3000]+", "", alias).lower()
            if alias_key and alias_key in normalized:
                return code
    return ""


def _build_observed_game_id(text: str, observed_at: str, *, prefix: str = "") -> str:
    observed_date = _extract_observed_date(text, observed_at)
    opponent_code = _extract_opponent_code(text)
    if not observed_date or not opponent_code:
        return ""
    return f"{prefix}{observed_date}-g-{opponent_code}"


def _infer_result_token(text: str) -> str:
    normalized = unescape(text or "")
    if "引き分け" in normalized:
        return "draw"
    match = _SCORE_TOKEN_RE.search(normalized)
    if match:
        first = int(match.group(1))
        second = int(match.group(2))
        if first > second:
            return "win"
        if first < second:
            return "lose"
        return "draw"
    if "勝利" in normalized or "白星" in normalized:
        return "win"
    if "敗戦" in normalized or "黒星" in normalized:
        return "lose"
    return ""


def _build_artifact_body_html(*, intake_source: str, observed_at: str, title: str, original_title: str, template: str) -> str:
    parts = [f"<p>{escape(title)}</p>"]
    if original_title and original_title != title:
        parts.append(f"<p>{escape(original_title)}</p>")
    meta_bits = [f"collector_artifact={intake_source}"]
    if observed_at:
        meta_bits.append(f"observed_at={observed_at}")
    if template:
        meta_bits.append(f"template={template}")
    parts.append(f"<p>{escape(' '.join(meta_bits))}</p>")
    return "".join(parts)


def _rss_fetcher_log_payload_to_intake_item(payload: dict[str, Any], observed_at: str) -> dict[str, Any] | None:
    if str(payload.get("event") or "").strip() != "title_template_selected":
        return None

    source_url = str(payload.get("source_url") or "").strip()
    article_subtype = str(payload.get("article_subtype") or "").strip().lower()
    template = str(payload.get("template") or "").strip().lower()
    original_title = str(payload.get("original_title") or "").strip()
    rewritten_title = str(payload.get("rewritten_title") or "").strip()
    title = rewritten_title or original_title
    if not source_url or not title:
        return None

    observed_text = " ".join(part for part in (original_title, rewritten_title, template, source_url) if part)
    item: dict[str, Any] = {
        "source_url": source_url,
        "trust_tier": _infer_trust_tier(source_url),
        "title": title,
        "body_html": _build_artifact_body_html(
            intake_source=INTAKE_SOURCE_RSS_FETCHER_LOG,
            observed_at=observed_at,
            title=title,
            original_title=original_title,
            template=template,
        ),
    }
    if article_subtype == "pregame":
        game_id = _build_observed_game_id(observed_text, observed_at)
        if not game_id:
            return None
        item.update(
            {
                "family": "probable_pitcher",
                "game_id": game_id,
                "category": "試合速報",
                "tags": ["予告先発"],
            }
        )
        return item
    if article_subtype == "lineup":
        game_id = _build_observed_game_id(observed_text, observed_at)
        if not game_id:
            return None
        item.update(
            {
                "family": "lineup_notice",
                "game_id": game_id,
                "lineup_kind": "starting",
                "category": "試合速報",
                "tags": ["スタメン"],
            }
        )
        return item
    if article_subtype == "postgame":
        game_id = _build_observed_game_id(observed_text, observed_at)
        result_token = _infer_result_token(observed_text)
        if not game_id or not result_token:
            return None
        item.update(
            {
                "family": "postgame_result",
                "game_id": game_id,
                "result_token": result_token,
                "category": "試合速報",
                "tags": ["試合結果"],
            }
        )
        return item
    if article_subtype == "farm" and template.startswith("farm_result"):
        game_id = _build_observed_game_id(observed_text, observed_at, prefix="farm-")
        if not game_id:
            return None
        item.update(
            {
                "family": "farm_result",
                "game_id": game_id,
                "category": "ドラフト・育成",
                "tags": ["ファーム"],
            }
        )
        return item
    return None


def _read_rss_fetcher_log_intake_items(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        payload = _extract_json_payload(line)
        if payload is None:
            continue
        item = _rss_fetcher_log_payload_to_intake_item(payload, _log_timestamp(line))
        if item is not None:
            items.append(item)
    return items


def _load_optional_intake_items(intake_file: str, intake_source: str) -> list[dict[str, Any]]:
    path = Path(intake_file)
    if not path.is_file():
        raise ValueError("intake_file_not_found")
    if intake_source == INTAKE_SOURCE_RSS_FETCHER_LOG:
        return _read_rss_fetcher_log_intake_items(path)
    raise ValueError("unsupported_intake_source")


def _reason_from_response(resp: requests.Response) -> str:
    status = getattr(resp, "status_code", 0)
    if status == 401:
        return "application_password_unauthorized"
    if status == 403:
        return "wp_permission_forbidden"
    if status == 404:
        return "posts_endpoint_not_found"
    if status:
        return f"http_{status}"
    return "unknown_response"


def _request_error_reason(exc: Exception) -> str:
    name = exc.__class__.__name__
    text = str(exc).strip()
    if "NameResolutionError" in text or "Failed to resolve" in text:
        return "dns_resolution_failed"
    if text and text != name:
        normalized = re.sub(r"[^a-zA-Z0-9:_-]+", "_", text).strip("_")
        if normalized:
            return normalized[:120]
    return name


def _response_text(resp: requests.Response) -> str:
    encoding = (resp.encoding or "").lower()
    apparent = (getattr(resp, "apparent_encoding", "") or "").lower()

    # Some NPB pages omit a charset header, so requests falls back to ISO-8859-1
    # even though the body is UTF-8. Prefer the apparent UTF-8-like encoding there.
    if apparent and encoding in {"", "iso-8859-1"} and apparent != encoding:
        try:
            return resp.content.decode(apparent, errors="replace")
        except LookupError:
            pass
    return resp.text


def _notice_date_label(notice_date: str) -> str:
    return f"{int(notice_date[4:6])}月{int(notice_date[6:8])}日"


def _format_name_list(entries: Sequence[NoticeEntry]) -> str:
    names = [entry.player_name for entry in entries]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}と{names[1]}"
    return f"{names[0]}ら{len(names)}人"


def _build_title(notice_date: str, registered: Sequence[NoticeEntry], deregistered: Sequence[NoticeEntry]) -> str:
    date_label = _notice_date_label(notice_date)
    if registered and deregistered:
        return (
            f"【公示】{date_label} 巨人は{_format_name_list(registered)}を登録、"
            f"{_format_name_list(deregistered)}を抹消"
        )
    if registered:
        return f"【公示】{date_label} 巨人は{_format_name_list(registered)}を出場選手登録"
    return f"【公示】{date_label} 巨人は{_format_name_list(deregistered)}を登録抹消"


def _build_summary_line(notice_date: str, registered: Sequence[NoticeEntry], deregistered: Sequence[NoticeEntry]) -> str:
    date_label = _notice_date_label(notice_date)
    if registered and deregistered:
        return (
            f"{date_label}のNPB公示で、巨人は{_format_name_list(registered)}を出場選手登録し、"
            f"{_format_name_list(deregistered)}を登録抹消しました。"
        )
    if registered:
        return f"{date_label}のNPB公示で、巨人は{_format_name_list(registered)}を出場選手登録しました。"
    return f"{date_label}のNPB公示で、巨人は{_format_name_list(deregistered)}を登録抹消しました。"


def _entry_list_html(entries: Sequence[NoticeEntry], label: str) -> str:
    if not entries:
        return f"<li>{label}: なし</li>"
    items = [
        f"<li>{label}: {entry.player_name}（{entry.position} / 背番号{entry.number}）</li>"
        for entry in entries
    ]
    return "".join(items)


def _build_body_html(
    notice_date: str,
    registered: Sequence[NoticeEntry],
    deregistered: Sequence[NoticeEntry],
    source_url: str,
    deregister_note: str = "",
    hidden_marker_html: str = "",
) -> str:
    summary_line = _build_summary_line(notice_date, registered, deregistered)
    note_html = f"<p>{deregister_note}</p>" if deregister_note else ""
    return "".join(
        [
            f'<p>一次情報: <a href="{source_url}" target="_blank" rel="noopener noreferrer">NPB公示</a></p>',
            "<h2>【公示の要旨】</h2>",
            f"<p>{summary_line}</p>",
            "<h3>【対象選手の基本情報】</h3>",
            "<ul>",
            _entry_list_html(registered, "出場選手登録"),
            _entry_list_html(deregistered, "登録抹消"),
            "</ul>",
            "<h3>【公示の背景】</h3>",
            "<p>この固定版Draftは、NPB公示に出ている一次情報だけを先に整理したものです。</p>",
            note_html,
            "<h3>【今後の注目点】</h3>",
            "<p>起用の詳細や次の再登録タイミングは、球団発表と次の試合前情報で確認したいところです。</p>",
            hidden_marker_html,
        ]
    )


def _html_to_lines(html_text: str) -> list[str]:
    text = _SCRIPT_STYLE_RE.sub("\n", html_text or "")
    text = _COMMENT_RE.sub("\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|ul|ol|tr|h1|h2|h3|h4|h5|h6|section|article|main|table|tbody|thead)>", "\n", text)
    text = re.sub(r"(?i)<t[dh][^>]*>", " ", text)
    text = re.sub(r"(?i)</t[dh]>", " ", text)
    text = _TAG_RE.sub("", text)
    raw_lines = unescape(text).splitlines()
    lines = []
    for raw_line in raw_lines:
        normalized = re.sub(r"[\s\u3000]+", " ", raw_line).strip()
        if normalized:
            lines.append(normalized)
    return lines


def _notice_entry_from_tokens(tokens: Sequence[str], action: str) -> NoticeEntry | None:
    if len(tokens) < 4:
        return None
    team, position, number, *name_parts = tokens
    if team != TARGET_TEAM:
        return None
    if position not in _POSITION_LABELS:
        return None
    if not _NUMBER_RE.fullmatch(number):
        return None
    player_name = "".join(name_parts)
    if not player_name:
        return None
    return NoticeEntry(
        action=action,
        position=position,
        number=number,
        player_name=player_name,
    )


def _parse_notice_row(lines: Sequence[str] | str, action: str) -> tuple[NoticeEntry | None, int]:
    if not action:
        return None, 1
    candidate_lines = [lines] if isinstance(lines, str) else list(lines)
    tokens: list[str] = []
    consumed = 0

    for raw_line in candidate_lines[:4]:
        parts = raw_line.split()
        if not parts:
            continue
        if consumed == 0 and parts[0] not in _NPB_TEAMS:
            return None, 1
        if consumed > 0 and parts[0] in _NPB_TEAMS:
            break

        tokens.extend(parts)
        consumed += 1
        entry = _notice_entry_from_tokens(tokens, action)
        if entry is not None:
            return entry, consumed

    return None, max(consumed, 1)


def _build_notice_subject_and_kind(
    registered: Sequence[NoticeEntry],
    deregistered: Sequence[NoticeEntry],
) -> tuple[str, str]:
    names: list[str] = []
    seen: set[str] = set()
    for entry in [*registered, *deregistered]:
        if entry.player_name and entry.player_name not in seen:
            seen.add(entry.player_name)
            names.append(entry.player_name)
    if registered and deregistered:
        return "+".join(names), "register_deregister"
    if registered:
        return "+".join(names), "register"
    return "+".join(names), "deregister"


def _parse_latest_notice_from_html(html_text: str, source_url: str = NPB_NOTICE_URL) -> NoticeCandidate | None:
    lines = _html_to_lines(html_text)
    date_index = -1
    notice_date = ""
    for idx, line in enumerate(lines):
        match = _DATE_HEADING_RE.search(line)
        if not match:
            continue
        year, month, day = match.groups()
        notice_date = f"{int(year):04d}{int(month):02d}{int(day):02d}"
        date_index = idx
        break
    if date_index < 0 or not notice_date:
        raise ValueError("notice_date_not_found")

    league = ""
    current_action = ""
    registered: list[NoticeEntry] = []
    deregistered: list[NoticeEntry] = []
    deregister_note = ""

    body_lines = lines[date_index + 1:]
    idx = 0
    while idx < len(body_lines):
        line = body_lines[idx]
        if line == "セントラル・リーグ":
            league = "central"
            idx += 1
            continue
        if line == "パシフィック・リーグ":
            break
        if "出場選手一覧" in line:
            break
        if league != "central":
            idx += 1
            continue
        if line == "出場選手登録":
            current_action = "register"
            idx += 1
            continue
        if line in {"出場選手登録抹消", "登録抹消"}:
            current_action = "deregister"
            idx += 1
            continue
        if line == "なし":
            idx += 1
            continue
        if line.startswith("※"):
            if current_action == "deregister":
                deregister_note = line
            idx += 1
            continue
        entry, consumed = _parse_notice_row(body_lines[idx:], current_action)
        if entry is None:
            idx += 1
            continue
        if entry.action == "register":
            registered.append(entry)
        elif entry.action == "deregister":
            deregistered.append(entry)
        idx += consumed

    if not registered and not deregistered:
        return None

    family = TARGET_ARTICLE_TYPE
    spec = FAMILY_SPECS[family]
    subject, notice_kind = _build_notice_subject_and_kind(registered, deregistered)
    candidate_key = _build_family_candidate_key(
        family,
        notice_date=notice_date,
        subject=subject,
        notice_kind=notice_kind,
    )
    if not candidate_key:
        raise ValueError(ROUTE_AMBIGUOUS_SUBJECT)
    candidate_slug = _build_candidate_slug(candidate_key)
    candidate_id = _build_candidate_id(source_url, family, notice_date)
    hidden_marker_html = (
        "<!-- yoshilover_notice_meta: "
        + json.dumps(
            {
                "candidate_id": candidate_id,
                "candidate_key": candidate_key,
                "family": family,
                "subtype": spec.subtype,
                "trust_tier": TRUST_TIER_T1,
                "source_id": build_source_id(source_url),
            },
            ensure_ascii=False,
        )
        + " -->"
    )
    title = _build_title(notice_date, registered, deregistered)
    body_html = _build_body_html(
        notice_date=notice_date,
        registered=registered,
        deregistered=deregistered,
        source_url=source_url,
        deregister_note=deregister_note,
        hidden_marker_html=hidden_marker_html,
    )
    metadata: dict[str, Any] = {
        "subtype": spec.subtype,
        "article_subtype": spec.subtype,
        "article_type": family,
        "family": family,
        "category": spec.category_name,
        "parent_category": TARGET_PARENT_CATEGORY_NAME,
        "tags": list(spec.default_tags),
        "candidate_id": candidate_id,
        "candidate_key": candidate_key,
        "source_trust": "primary",
        "batch_source": TARGET_BATCH_SOURCE,
        "source_id": build_source_id(source_url),
        "source_urls": [source_url],
        "source_bundle": [_bundle_entry(source_url, TRUST_TIER_T1, role="primary", source_kind=SOURCE_KIND_NPB)],
        "trigger_only_sources": [],
        "pickup_mode": "collect_wide_assert_narrow",
        "pickup_source_kind": SOURCE_KIND_NPB,
        "pickup_source_kinds": [SOURCE_KIND_NPB],
        "lane_target": spec.lane_target,
        "primary_trust_tier": TRUST_TIER_T1,
        "notice_date": notice_date,
        "subject": subject,
        "notice_kind": notice_kind,
        WPClient.SOURCE_URL_META_KEY: source_url,
    }
    return NoticeCandidate(
        source_url=source_url,
        source_id=build_source_id(source_url),
        notice_date=notice_date,
        title=title,
        body_html=body_html,
        metadata=metadata,
        candidate_slug=candidate_slug,
        family=family,
        candidate_key=candidate_key,
        subject=subject,
        notice_kind=notice_kind,
    )


def _fetch_latest_notice_candidate(source_url: str = NPB_NOTICE_URL) -> NoticeCandidate | None:
    if _infer_trust_tier(source_url) != TRUST_TIER_T1:
        return None
    try:
        resp = requests.get(
            source_url,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(_request_error_reason(exc)) from exc
    return _parse_latest_notice_from_html(_response_text(resp), source_url=source_url)


def _run_wp_post_dry_run(wp: WPClient, *, now: datetime | None = None) -> str:
    probe_now = now or datetime.now()
    probe_title = probe_now.strftime("canary-probe-%Y%m%d-%H%M%S")
    payload = {
        "title": probe_title,
        "content": "<p>canary probe</p>",
        "status": "draft",
    }
    try:
        resp = requests.post(
            f"{wp.api}/posts",
            json=payload,
            auth=wp.auth,
            headers=wp.headers,
            timeout=30,
        )
    except requests.RequestException as exc:
        reason = _request_error_reason(exc)
        _emit_event("wp_post_dry_run_fail", reason=reason)
        return f"fail:{reason}"

    if resp.status_code != 201:
        reason = _reason_from_response(resp)
        _emit_event("wp_post_dry_run_fail", reason=reason, status_code=resp.status_code)
        return f"fail:{reason}"

    post_id = resp.json().get("id")
    if not post_id:
        _emit_event("wp_post_dry_run_fail", reason="missing_post_id")
        return "fail:missing_post_id"

    try:
        delete_resp = requests.delete(
            f"{wp.api}/posts/{post_id}",
            params={"force": "true"},
            auth=wp.auth,
            timeout=30,
        )
        wp._raise_for_status(delete_resp, f"疎通確認後削除 post_id={post_id}")
    except Exception as exc:
        reason = _request_error_reason(exc)
        _emit_event("wp_post_dry_run_fail", reason=f"delete_failed:{reason}", post_id=post_id)
        return f"fail:delete_failed:{reason}"

    _emit_event("wp_post_dry_run_pass", post_id=post_id)
    return "pass"


def _post_candidate_id(post: dict[str, Any]) -> str:
    meta = post.get("meta")
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("candidate_id") or "").strip()


def _post_candidate_key(post: dict[str, Any]) -> str:
    meta = post.get("meta")
    if isinstance(meta, dict):
        candidate_key = str(meta.get("candidate_key") or "").strip()
        if candidate_key:
            return candidate_key
    return str(post.get("slug") or post.get("generated_slug") or "").strip()


def _post_title(post: dict[str, Any]) -> str:
    title = post.get("title")
    if isinstance(title, dict):
        return str(title.get("raw") or title.get("rendered") or "").strip()
    return str(title or "").strip()


def _search_recent_posts_for_duplicate_check(wp: WPClient, title: str) -> list[dict[str, Any]]:
    query_variants = [
        {
            "search": title[:40],
            "per_page": 20,
            "status": "any",
            "context": "edit",
            "_fields": ",".join(_DUPLICATE_LOOKUP_FIELDS),
        },
        {
            "search": title[:40],
            "per_page": 20,
            "_fields": ",".join(_DUPLICATE_LOOKUP_FIELDS),
        },
    ]
    last_error: Exception | None = None
    for params in query_variants:
        try:
            resp = requests.get(
                f"{wp.api}/posts",
                params=params,
                auth=wp.auth,
                timeout=30,
            )
            wp._raise_for_status(resp, "draft重複確認検索")
            rows = resp.json()
            if isinstance(rows, list):
                return rows
        except Exception as exc:  # pragma: no cover - fallback path
            last_error = exc
    if last_error:
        raise last_error
    return []


def _find_duplicate_posts(wp: WPClient, candidate: NoticeCandidate) -> list[dict[str, Any]]:
    normalized_title = WPClient._normalize_title(candidate.title)
    candidate_id = str(candidate.metadata.get("candidate_id") or "").strip()
    candidate_key = _candidate_metadata_key(candidate)
    return [
        post
        for post in _search_recent_posts_for_duplicate_check(wp, candidate.title)
        if str(post.get("status") or "").strip().lower() == "draft"
        and (
            (candidate_key and _post_candidate_key(post) == candidate_key)
            or (candidate_id and _post_candidate_id(post) == candidate_id)
            or (candidate.candidate_slug and _post_candidate_key(post) == candidate.candidate_slug)
            or WPClient._normalize_title(_post_title(post)) == normalized_title
        )
    ]


def _resolve_category_ids(
    wp: WPClient,
    child_category_name: str,
    *,
    parent_category_name: str = TARGET_PARENT_CATEGORY_NAME,
) -> list[int]:
    child_id = wp.resolve_category_id(child_category_name) if child_category_name else 0
    if not child_id:
        return []
    category_ids = [int(child_id)]
    parent_id = wp.resolve_category_id(parent_category_name) if parent_category_name else 0
    if parent_id and int(parent_id) not in category_ids:
        category_ids.append(int(parent_id))
    return category_ids


def _find_or_create_tag_id(wp: WPClient, tag_name: str) -> int:
    resp = requests.get(
        f"{wp.api}/tags",
        params={"search": tag_name, "per_page": 100},
        auth=wp.auth,
        timeout=30,
    )
    wp._raise_for_status(resp, f"tag検索 name={tag_name}")
    for row in resp.json():
        if str(row.get("name") or "").strip() == tag_name:
            return int(row["id"])

    create_resp = requests.post(
        f"{wp.api}/tags",
        json={"name": tag_name},
        auth=wp.auth,
        headers=wp.headers,
        timeout=30,
    )
    if create_resp.status_code == 400:
        try:
            data = create_resp.json()
        except ValueError:
            data = {}
        if data.get("code") == "term_exists":
            term_id = ((data.get("data") or {}).get("term_id")) or 0
            if term_id:
                return int(term_id)
    wp._raise_for_status(create_resp, f"tag作成 name={tag_name}")
    return int(create_resp.json()["id"])


def _resolve_tag_ids(wp: WPClient, tag_names: Sequence[str]) -> list[int]:
    return [_find_or_create_tag_id(wp, tag_name) for tag_name in tag_names if str(tag_name or "").strip()]


def _create_notice_draft(
    wp: WPClient,
    candidate: NoticeCandidate,
    category_ids: Sequence[int],
    tag_ids: Sequence[int],
) -> int | None:
    featured_media = maybe_generate_structured_eyecatch_media(wp, candidate)
    payload = {
        "title": candidate.title,
        "content": candidate.body_html,
        "status": "draft",
        "categories": list(category_ids),
        "slug": candidate.candidate_slug,
        "tags": list(tag_ids),
        "meta": candidate.metadata,
    }
    if featured_media:
        payload["featured_media"] = featured_media
    last_reason = ""
    for attempt in range(1, 3):
        try:
            resp = requests.post(
                f"{wp.api}/posts",
                json=payload,
                auth=wp.auth,
                headers=wp.headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            last_reason = _request_error_reason(exc)
        else:
            if resp.status_code == 201:
                post_id = resp.json().get("id")
                if post_id:
                    _emit_event(
                        "canary_post_created",
                        post_id=post_id,
                        candidate_id=candidate.metadata["candidate_id"],
                        candidate_key=_candidate_metadata_key(candidate),
                        family=_candidate_metadata_family(candidate),
                        attempt=attempt,
                    )
                    return int(post_id)
                last_reason = "missing_post_id"
            else:
                last_reason = _reason_from_response(resp)
        if attempt < 2:
            _emit_event(
                "canary_post_retry",
                attempt=attempt,
                candidate_id=candidate.metadata["candidate_id"],
                candidate_key=_candidate_metadata_key(candidate),
                family=_candidate_metadata_family(candidate),
                reason=last_reason,
            )
    _emit_event(
        "canary_post_failed",
        candidate_id=candidate.metadata["candidate_id"],
        candidate_key=_candidate_metadata_key(candidate),
        family=_candidate_metadata_family(candidate),
        reason=last_reason or "unknown",
    )
    return None


def _candidate_lane_target(candidate: NoticeCandidate) -> str:
    family = _candidate_metadata_family(candidate)
    spec = FAMILY_SPECS.get(family)
    if spec is None:
        return TARGET_LANE_AI
    lane_target = str(candidate.metadata.get("lane_target") or spec.lane_target).strip()
    return lane_target or TARGET_LANE_AI


def _route_candidates(candidates: Sequence[NoticeCandidate]) -> tuple[list[NoticeCandidate], list[str]]:
    grouped: dict[str, NoticeCandidate] = {}
    route_outcomes: list[str] = []
    for candidate in candidates:
        family = _candidate_metadata_family(candidate)
        if family not in FAMILY_SPECS:
            route_outcomes.append(ROUTE_OUT_OF_MVP_FAMILY)
            continue
        candidate_key = _candidate_metadata_key(candidate)
        if not candidate_key:
            route_outcomes.append(ROUTE_AMBIGUOUS_SUBJECT)
            continue
        if candidate_key in grouped:
            grouped[candidate_key] = _merge_candidates(grouped[candidate_key], candidate)
            route_outcomes.append(ROUTE_DUPLICATE_ABSORBED)
            continue
        grouped[candidate_key] = candidate

    routed: list[NoticeCandidate] = []
    for candidate in grouped.values():
        lane_target = _candidate_lane_target(candidate)
        if lane_target != TARGET_LANE_FIXED:
            route_outcomes.append(ROUTE_DEFERRED_PICKUP)
            _emit_event(
                "deferred_pickup",
                reason="lane_target_not_fixed",
                lane_target=lane_target,
                family=_candidate_metadata_family(candidate),
                candidate_key=_candidate_metadata_key(candidate),
                source_bundle=_candidate_source_bundle(candidate),
                trigger_only_sources=_candidate_trigger_sources(candidate),
            )
            continue
        if not _candidate_has_t1_source(candidate):
            route_outcomes.append(ROUTE_AWAIT_PRIMARY)
            route_outcomes.append(ROUTE_DEFERRED_PICKUP)
            _emit_event(
                "await_primary",
                family=_candidate_metadata_family(candidate),
                candidate_key=_candidate_metadata_key(candidate),
                source_bundle=_candidate_source_bundle(candidate),
                trigger_only_sources=_candidate_trigger_sources(candidate),
            )
            _emit_event(
                "deferred_pickup",
                reason="await_primary",
                lane_target=lane_target,
                family=_candidate_metadata_family(candidate),
                candidate_key=_candidate_metadata_key(candidate),
                source_bundle=_candidate_source_bundle(candidate),
                trigger_only_sources=_candidate_trigger_sources(candidate),
            )
            continue
        routed.append(candidate)
    return routed, route_outcomes


def _process_candidates(wp: WPClient, candidates: Sequence[NoticeCandidate]) -> ProcessResult:
    created_post_id: int | None = None
    duplicate_skip = False
    attempted_create = False
    routed_candidates, route_outcomes = _route_candidates(candidates)
    for candidate in list(routed_candidates)[:MAX_CANARY_POSTS]:
        duplicates = _find_duplicate_posts(wp, candidate)
        if duplicates:
            duplicate_skip = True
            route_outcomes.append(ROUTE_DUPLICATE_ABSORBED)
            route_outcomes.append(ROUTE_DEFERRED_PICKUP)
            _emit_event(
                "duplicate_skip",
                candidate_id=candidate.metadata["candidate_id"],
                candidate_key=_candidate_metadata_key(candidate),
                family=_candidate_metadata_family(candidate),
                existing_post_ids=[row.get("id") for row in duplicates],
            )
            continue

        category_ids = _resolve_category_ids(
            wp,
            str(candidate.metadata.get("category") or "").strip(),
            parent_category_name=str(candidate.metadata.get("parent_category") or TARGET_PARENT_CATEGORY_NAME),
        )
        if not category_ids:
            _emit_event(
                "category_resolve_fail",
                family=_candidate_metadata_family(candidate),
                category=candidate.metadata.get("category"),
            )
            return ProcessResult(
                created_post_id=None,
                duplicate_skip=duplicate_skip,
                route_outcomes=tuple(route_outcomes),
                error_reason="category_resolve_failed",
                attempted_create=attempted_create,
            )
        tag_ids = _resolve_tag_ids(wp, candidate.metadata.get("tags") or [])
        attempted_create = True
        created_post_id = _create_notice_draft(wp, candidate, category_ids, tag_ids)
        if created_post_id is None:
            return ProcessResult(
                created_post_id=None,
                duplicate_skip=duplicate_skip,
                route_outcomes=tuple(route_outcomes),
                error_reason="draft_create_failed",
                attempted_create=attempted_create,
            )
        route_outcomes.append(ROUTE_FIXED_PRIMARY)
        return ProcessResult(
            created_post_id=created_post_id,
            duplicate_skip=duplicate_skip,
            route_outcomes=tuple(route_outcomes),
            attempted_create=attempted_create,
        )

    return ProcessResult(
        created_post_id=created_post_id,
        duplicate_skip=duplicate_skip,
        route_outcomes=tuple(route_outcomes),
        attempted_create=attempted_create,
    )


def run(argv: Sequence[str] | None = None) -> tuple[int, dict[str, Any]]:
    summary: dict[str, Any] = {
        "wp_post_dry_run": "fail:not_run",
        "source_fetch": "skip:not_run",
        "canary_post_id": None,
        "canary_candidate_id": None,
        "duplicate_skip": False,
        "duplicate_check_implemented": True,
        "max_canary_cap": MAX_CANARY_POSTS,
        "published_write": False,
        "route_outcomes": [],
    }

    try:
        intake_file, intake_source = _resolve_optional_intake(argv)
    except (SystemExit, ValueError) as exc:
        reason = _request_error_reason(exc)
        summary["source_fetch"] = f"fail:{reason}"
        return EXIT_INPUT_ERROR, summary

    try:
        wp = WPClient()
    except Exception as exc:
        reason = _request_error_reason(exc)
        summary["wp_post_dry_run"] = f"fail:{reason}"
        return EXIT_INPUT_ERROR, summary

    summary["wp_post_dry_run"] = _run_wp_post_dry_run(wp)
    if summary["wp_post_dry_run"] != "pass":
        return EXIT_WP_POST_DRY_RUN_FAILED, summary

    if intake_file:
        try:
            items = _load_optional_intake_items(intake_file, intake_source)
        except Exception as exc:
            reason = _request_error_reason(exc)
            _emit_event("source_fetch_fail", reason=reason)
            summary["source_fetch"] = f"fail:{reason}"
            return EXIT_INPUT_ERROR, summary

        if not items:
            _emit_event("source_fetch_skip", reason="no_intake_candidates_found", intake_source=intake_source)
            summary["source_fetch"] = "skip:no_intake_candidates_found"
            return EXIT_OK, summary

        candidates, normalized_outcomes = _normalize_intake_items(items)
        summary["source_fetch"] = "pass"
        if not candidates:
            summary["route_outcomes"] = list(normalized_outcomes)
            return EXIT_OK, summary

        summary["canary_candidate_id"] = candidates[0].metadata["candidate_id"]
        result = _process_candidates(wp, candidates)
        summary["duplicate_skip"] = result.duplicate_skip
        summary["route_outcomes"] = [*normalized_outcomes, *result.route_outcomes]
        if result.created_post_id is None:
            if result.error_reason == "category_resolve_failed":
                return EXIT_INPUT_ERROR, summary
            if result.error_reason == "draft_create_failed" or (
                result.attempted_create and not result.duplicate_skip
            ):
                return EXIT_WP_POST_FAILED, summary
            return EXIT_OK, summary

        summary["canary_post_id"] = result.created_post_id
        return EXIT_OK, summary

    try:
        candidate = _fetch_latest_notice_candidate()
    except Exception as exc:
        reason = _request_error_reason(exc)
        _emit_event("source_fetch_fail", reason=reason)
        summary["source_fetch"] = f"fail:{reason}"
        return EXIT_OK, summary

    if candidate is None:
        _emit_event("source_fetch_skip", reason="no_giants_notice_found")
        summary["source_fetch"] = "skip:no_giants_notice_found"
        return EXIT_OK, summary

    summary["source_fetch"] = "pass"
    summary["canary_candidate_id"] = candidate.metadata["candidate_id"]

    result = _process_candidates(wp, [candidate])
    summary["duplicate_skip"] = result.duplicate_skip
    summary["route_outcomes"] = list(result.route_outcomes)
    if result.created_post_id is None:
        if result.error_reason == "category_resolve_failed":
            return EXIT_INPUT_ERROR, summary
        if result.error_reason == "draft_create_failed" or (
            result.attempted_create and not result.duplicate_skip
        ):
            return EXIT_WP_POST_FAILED, summary
        return EXIT_OK, summary

    summary["canary_post_id"] = result.created_post_id
    return EXIT_OK, summary


def main(argv: Sequence[str] | None = None) -> int:
    code, summary = run(argv)
    print(json.dumps(summary, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
