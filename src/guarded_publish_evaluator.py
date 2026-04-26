from __future__ import annotations

import html
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.lineup_source_priority import compute_lineup_dedup, extract_game_id
from src.pre_publish_fact_check import extractor
from src.title_body_nucleus_validator import validate_title_body_nucleus


JST = ZoneInfo("Asia/Tokyo")
RELAXED_FOR_BREAKING_BOARD_FLAGS = frozenset({"subtype_unresolved", "heading_sentence_as_h3"})

HARD_STOP_FLAGS = frozenset(
    {
        "unsupported_named_fact",
        "obvious_misinformation",
        "title_body_mismatch_strict",
        "cross_article_contamination",
        "x_sns_auto_post_risk",
        "ranking_list_only",
        "lineup_no_hochi_source",
        "lineup_prefix_misuse",
        "dev_log_contamination_scattered",
    }
)
REPAIRABLE_FLAGS = frozenset(
    {
        "weird_heading_label",
        "dev_log_contamination",
        "site_component_mixed_into_body",
        "ai_tone_heading_or_lead",
        "light_structure_break",
        "weak_source_display",
        "long_body",
        "missing_primary_source",
        "missing_featured_media",
        "title_body_mismatch_partial",
        "numerical_anomaly_low_severity",
        "stale_for_breaking_board",
        "expired_lineup_or_pregame",
        "expired_game_context",
        "injury_death",
        "lineup_duplicate_excessive",
    }
) | RELAXED_FOR_BREAKING_BOARD_FLAGS
SOFT_CLEANUP_FLAGS = REPAIRABLE_FLAGS

PRIMARY_SRC_RE = re.compile(
    r"(Yahoo!プロ野球|報知|スポーツナビ|日刊スポーツ|スポニチ|デイリー|サンケイ|スポーツ報知|読売新聞)"
)
SPECULATIVE_TITLE_RE = re.compile(
    r"(どう見[るた]|どこを|どこへ|どこか|見たい|見せ[るたい]|予想|気になる|狙いはどこ|何を|どんな|"
    r"どう並べ|どう動く|どう攻め|どう戦|誰だ|どう打|どう起用|どうな[るた]|なぜ|何が|[？?]|"
    r"ポイント[はが]|順調ならば|週明けにも.*か$)"
)
INJURY_DEATH_RE = re.compile(
    r"(故障|離脱|登録抹消|抹消|コンディション不良|アクシデント|復帰|亡くな|天国|死去|【コメント】|引退|交代|診断|症状|ケガ)"
)
RANKING_LIST_ONLY_RE = re.compile(r"(①.*②|⑤|通算安打.*：|順位.*ranking|NPB通算)", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
H3_RE = re.compile(r"(?is)<h3\b[^>]*>(.*?)</h3>")
NEXT_HEADING_RE = re.compile(r"(?is)<h[1-6]\b[^>]*>")
PRE_BLOCK_RE = re.compile(r"(?is)<pre\b[^>]*>(.*?)</pre>")
CODE_BLOCK_RE = re.compile(r"(?is)<code\b[^>]*>(.*?)</code>")
HEADING_SENTENCE_END_RE = re.compile(
    r"(した|している|していた|と語った|と話した|を確認した|を記録した|と発表した|となった|を達成した)$"
)
PLAYER_HEURISTIC_RE = re.compile(r"([一-龯々]{2,4}(?:投手|捕手|内野手|外野手|選手|監督)?|[A-Za-z]{2,}[0-9]*|[一-龯々]{2,4}[A-Za-z0-9]+)")
LINEUP_SIGNAL_RE = re.compile(r"(スタメン|先発オーダー|オーダー|先発投手|予告先発|[1-9１-９]番)")
POSTGAME_SIGNAL_RE = re.compile(r"(試合結果|勝利|敗戦|引き分け|[0-9０-９]+\s*[-－ー]\s*[0-9０-９]+)")
LOW_SEVERITY_NUMERIC_RE = re.compile(r"打率\s*(?:0|０)?[\.．]([4-9][0-9０-９]{2})")
POSTCHECK_META_RE = re.compile(r"(tweet_id|x_post_id|posted_to_x|posted_to_twitter|auto_tweet|auto_post_to_x|sns_posted)")
LIGHT_STRUCTURE_BREAK_RE = re.compile(r"(?is)<p\b[^>]*>\s*(?:&nbsp;|\s|<br\s*/?>)*</p>|(?:<br\s*/?>\s*){2,}")
AI_TONE_LEAD_RE = re.compile(
    r"(注目したい|注目ポイント|見どころ|ポイントは|どう見る|どう動く|狙いはどこ|気になる)"
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
ISO_YMD_RE = re.compile(r"(?<!\d)(20\d{2})[/-](\d{1,2})[/-](\d{1,2})(?!\d)")
COMPACT_YMD_RE = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
JP_YMD_RE = re.compile(r"(?<!\d)(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
JP_MD_RE = re.compile(r"(?<!\d)(\d{1,2})月\s*(\d{1,2})日")
SLASH_MD_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!/\d)")
TIME_TAIL_RE = re.compile(r"^[\sT　]*(?:(\d{1,2}):(\d{2})|(\d{1,2})時(?:\s*(\d{1,2})分?)?)")
GAME_START_TIME_RE = re.compile(
    r"(?:試合開始|開始予定|開始時刻|プレーボール|開始)\D{0,8}(?:(\d{1,2}):(\d{2})|(\d{1,2})時(?:\s*(\d{1,2})分?)?)"
)
TITLE_DUPLICATE_SUFFIX_RE = re.compile(r"(?:\s*(?:\(\s*\d+\s*\)|（\s*\d+\s*）|[-－ー]\s*\d+))+$")
TITLE_NUMBER_TOKEN_RE = re.compile(r"\d+")
DEFAULT_GAME_START_HOUR = 18
FRESHNESS_THRESHOLDS_HOURS: dict[str, float] = {
    "lineup": 6.0,
    "pregame": 6.0,
    "probable_starter": 6.0,
    "farm_lineup": 6.0,
    "postgame": 24.0,
    "game_result": 24.0,
    "roster": 24.0,
    "injury": 24.0,
    "registration": 24.0,
    "recovery": 24.0,
    "notice": 24.0,
    "player_notice": 24.0,
    "player_recovery": 24.0,
    "comment": 48.0,
    "speech": 48.0,
    "manager": 48.0,
    "program": 48.0,
    "off_field": 48.0,
    "farm_feature": 48.0,
}
LINEUP_FRESHNESS_SUBTYPES = frozenset({"lineup", "pregame", "probable_starter", "farm_lineup"})
GAME_CONTEXT_FRESHNESS_SUBTYPES = frozenset({"postgame", "game_result"})
FRESHNESS_HOLD_CLASSES = frozenset({"stale", "expired"})
LINEUP_TITLE_TOKEN_MATCH_SUBTYPES = frozenset(
    {"lineup", "lineup_notice", "pregame", "probable_starter", "farm_lineup"}
)
SOURCE_DATE_META_FIELDS = (
    "source_published_at",
    "published_at",
    "source_datetime",
    "source_date",
    "article_date",
    "source_created_at",
)
SOURCE_URL_META_FIELDS = (
    "_yoshilover_source_url",
    "source_url",
    "canonical_source_url",
)

SITE_COMPONENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fan_voice", re.compile(r"💬\s*[^。\n]{0,120}")),
    ("related_articles", re.compile(r"【関連記事】")),
    ("fan_voice_label", re.compile(r"💬\s*ファンの声")),
)

LABEL_EXPECTATIONS: dict[str, tuple[re.Pattern[str], ...]] = {
    "試合結果": (re.compile(r"(勝利|敗戦|引き分け|[0-9０-９]+\s*[-－ー]\s*[0-9０-９]+)"),),
    "スタメン": (re.compile(r"(スタメン|先発|オーダー|[1-9１-９]番)"),),
    "出典": (PRIMARY_SRC_RE, re.compile(r"https?://")),
    "関連情報": (re.compile(r"(関連|関連記事|あわせて読みたい|過去記事)"),),
    "ファンの声": (re.compile(r"(ファンの声|SNS|X|コメント)"),),
    "コメント": (re.compile(r"(コメント|語った|話した|発言|述べた)"),),
    "2軍戦": (re.compile(r"(二軍|2軍|２軍|ファーム)"),),
    "今日のポイント": (re.compile(r"(ポイント|注目|鍵|見どころ)"),),
}

OPPONENT_CANONICAL = {
    "DeNA": "DeNA",
    "ＤｅＮＡ": "DeNA",
    "横浜": "DeNA",
    "阪神": "阪神",
    "ヤクルト": "ヤクルト",
    "中日": "中日",
    "広島": "広島",
    "西武": "西武",
    "日本ハム": "日本ハム",
    "楽天": "楽天",
    "ロッテ": "ロッテ",
    "ソフトバンク": "ソフトバンク",
    "オリックス": "オリックス",
}
OPPONENT_RE = re.compile("|".join(re.escape(token) for token in OPPONENT_CANONICAL))


def _strip_html(value: str) -> str:
    text = TAG_RE.sub("\n", value or "")
    text = html.unescape(text).replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_wp_datetime(value: str, *, fallback_now: datetime | None = None) -> datetime:
    if not value:
        return _now_jst(fallback_now)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _normalize_title_key(title: str) -> str:
    return re.sub(r"\s+", "", title or "").strip().lower()


def _normalize_title_text(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(title or ""))
    return re.sub(r"\s+", " ", normalized).strip()


def _strip_title_duplicate_suffix(title: str) -> str:
    normalized = _normalize_title_text(title)
    while normalized:
        stripped = TITLE_DUPLICATE_SUFFIX_RE.sub("", normalized).strip()
        if stripped == normalized:
            return normalized
        normalized = stripped
    return ""


def _exact_title_duplicate_key(title: str) -> str:
    return _normalize_title_key(_normalize_title_text(title))


def _normalized_title_duplicate_key(title: str) -> str:
    return _normalize_title_key(_strip_title_duplicate_suffix(title))


def _lineup_title_token_duplicate_key(title: str) -> str | None:
    normalized = _strip_title_duplicate_suffix(title)
    if not normalized:
        return None
    number_tokens = TITLE_NUMBER_TOKEN_RE.findall(normalized)
    if not number_tokens:
        return None
    prefix = normalized[:30].casefold().strip()
    if not prefix:
        return None
    return f"{prefix}::{'/'.join(number_tokens)}"


def _parse_optional_wp_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return _parse_wp_datetime(raw)
    except ValueError:
        return None


def _safe_datetime(
    year: int,
    month: int,
    day: int,
    *,
    hour: int = 0,
    minute: int = 0,
) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute, tzinfo=JST)
    except ValueError:
        return None


def _infer_year(month: int, day: int, *, now: datetime) -> int:
    candidate = _safe_datetime(now.year, month, day)
    if candidate is None:
        return now.year
    if candidate - now > timedelta(days=45):
        return now.year - 1
    if now - candidate > timedelta(days=330):
        return now.year + 1
    return now.year


def _time_from_tail(tail: str) -> tuple[int, int] | None:
    match = TIME_TAIL_RE.search(tail[:12])
    if not match:
        return None
    if match.group(1) is not None and match.group(2) is not None:
        return int(match.group(1)), int(match.group(2))
    if match.group(3) is not None:
        return int(match.group(3)), int(match.group(4) or 0)
    return None


def _append_date_candidate(
    candidates: list[tuple[datetime, bool]],
    seen: set[str],
    dt: datetime | None,
    *,
    has_explicit_time: bool,
) -> None:
    if dt is None:
        return
    key = f"{dt.isoformat()}::{int(has_explicit_time)}"
    if key in seen:
        return
    seen.add(key)
    candidates.append((dt, has_explicit_time))


def _extract_date_candidates(value: Any, *, now: datetime) -> list[tuple[datetime, bool]]:
    text = html.unescape(str(value or ""))
    if not text.strip():
        return []
    candidates: list[tuple[datetime, bool]] = []
    seen: set[str] = set()

    for match in ISO_YMD_RE.finditer(text):
        time_hint = _time_from_tail(text[match.end() :])
        hour, minute = time_hint if time_hint is not None else (0, 0)
        _append_date_candidate(
            candidates,
            seen,
            _safe_datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), hour=hour, minute=minute),
            has_explicit_time=time_hint is not None,
        )

    for match in COMPACT_YMD_RE.finditer(text):
        _append_date_candidate(
            candidates,
            seen,
            _safe_datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))),
            has_explicit_time=False,
        )

    for match in JP_YMD_RE.finditer(text):
        time_hint = _time_from_tail(text[match.end() :])
        hour, minute = time_hint if time_hint is not None else (0, 0)
        _append_date_candidate(
            candidates,
            seen,
            _safe_datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), hour=hour, minute=minute),
            has_explicit_time=time_hint is not None,
        )

    for match in JP_MD_RE.finditer(text):
        year = _infer_year(int(match.group(1)), int(match.group(2)), now=now)
        time_hint = _time_from_tail(text[match.end() :])
        hour, minute = time_hint if time_hint is not None else (0, 0)
        _append_date_candidate(
            candidates,
            seen,
            _safe_datetime(year, int(match.group(1)), int(match.group(2)), hour=hour, minute=minute),
            has_explicit_time=time_hint is not None,
        )

    for match in SLASH_MD_RE.finditer(text):
        year = _infer_year(int(match.group(1)), int(match.group(2)), now=now)
        time_hint = _time_from_tail(text[match.end() :])
        hour, minute = time_hint if time_hint is not None else (0, 0)
        _append_date_candidate(
            candidates,
            seen,
            _safe_datetime(year, int(match.group(1)), int(match.group(2)), hour=hour, minute=minute),
            has_explicit_time=time_hint is not None,
        )

    return candidates


def _resolved_subtype(raw_post: dict[str, Any], record: dict[str, Any]) -> str:
    meta = (raw_post or {}).get("meta") or {}
    for candidate in (meta.get("article_subtype"), raw_post.get("article_subtype"), record.get("inferred_subtype")):
        value = str(candidate or "").strip().lower()
        if value:
            return value
    return "other"


def _freshness_threshold_hours(subtype: str) -> float:
    return float(FRESHNESS_THRESHOLDS_HOURS.get((subtype or "").strip().lower(), 24.0))


def _source_url_candidates(raw_post: dict[str, Any], record: dict[str, Any]) -> list[str]:
    urls: list[str] = [str(value) for value in (record.get("source_urls") or []) if str(value).strip()]
    meta = (raw_post or {}).get("meta") or {}
    for container in (meta, raw_post):
        for key in SOURCE_URL_META_FIELDS:
            value = container.get(key)
            if isinstance(value, str) and value.strip() and value not in urls:
                urls.append(value)
        links = container.get("source_links")
        if isinstance(links, list):
            for item in links:
                if isinstance(item, str) and item.strip() and item not in urls:
                    urls.append(item)
                elif isinstance(item, dict):
                    for key in ("url", "href", "link"):
                        candidate = str(item.get(key) or "").strip()
                        if candidate and candidate not in urls:
                            urls.append(candidate)
    return urls


def _body_text_without_source(record: dict[str, Any]) -> str:
    body_text = str(record.get("body_text") or "")
    source_block = str(record.get("source_block") or "")
    if source_block:
        body_text = body_text.replace(source_block, "")
    return URL_RE.sub("", body_text)


def _resolve_content_datetime(raw_post: dict[str, Any], record: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    created_at = _parse_optional_wp_datetime(record.get("created_at"))
    meta = (raw_post or {}).get("meta") or {}

    for container_name, container in (("raw_post", raw_post or {}), ("meta", meta)):
        for key in SOURCE_DATE_META_FIELDS:
            if key not in container:
                continue
            raw_value = container.get(key)
            parsed = _parse_optional_wp_datetime(raw_value)
            if parsed is not None:
                return {
                    "content_date": parsed.date().isoformat(),
                    "age_reference_dt": parsed,
                    "detected_dt": parsed,
                    "priority_rank": 1,
                    "detected_by": f"{container_name}.{key}",
                    "age_basis": "exact_source_datetime",
                }
            for candidate_dt, has_explicit_time in _extract_date_candidates(raw_value, now=now):
                age_reference_dt = candidate_dt
                age_basis = "source_text_date_only"
                if not has_explicit_time and created_at is not None and created_at.date() == candidate_dt.date():
                    age_reference_dt = created_at
                    age_basis = "created_at_same_day_precision"
                elif has_explicit_time:
                    age_basis = "exact_source_datetime"
                return {
                    "content_date": candidate_dt.date().isoformat(),
                    "age_reference_dt": age_reference_dt,
                    "detected_dt": candidate_dt,
                    "priority_rank": 1,
                    "detected_by": f"{container_name}.{key}",
                    "age_basis": age_basis,
                }

    source_block = str(record.get("source_block") or "")
    for candidate_dt, has_explicit_time in _extract_date_candidates(source_block, now=now):
        age_reference_dt = candidate_dt
        age_basis = "source_block_date_only"
        if not has_explicit_time and created_at is not None and created_at.date() == candidate_dt.date():
            age_reference_dt = created_at
            age_basis = "created_at_same_day_precision"
        elif has_explicit_time:
            age_basis = "exact_source_datetime"
        return {
            "content_date": candidate_dt.date().isoformat(),
            "age_reference_dt": age_reference_dt,
            "detected_dt": candidate_dt,
            "priority_rank": 1,
            "detected_by": "source_block",
            "age_basis": age_basis,
        }

    for source_url in _source_url_candidates(raw_post, record):
        for candidate_dt, _ in _extract_date_candidates(source_url, now=now):
            age_reference_dt = candidate_dt
            age_basis = "source_url_date_only"
            if created_at is not None and created_at.date() == candidate_dt.date():
                age_reference_dt = created_at
                age_basis = "created_at_same_day_precision"
            return {
                "content_date": candidate_dt.date().isoformat(),
                "age_reference_dt": age_reference_dt,
                "detected_dt": candidate_dt,
                "priority_rank": 1,
                "detected_by": "source_url",
                "age_basis": age_basis,
            }

    for candidate_dt, has_explicit_time in _extract_date_candidates(_body_text_without_source(record), now=now):
        age_reference_dt = candidate_dt
        age_basis = "body_date_only"
        if not has_explicit_time and created_at is not None and created_at.date() == candidate_dt.date():
            age_reference_dt = created_at
            age_basis = "created_at_same_day_precision"
        elif has_explicit_time:
            age_basis = "exact_body_datetime"
        return {
            "content_date": candidate_dt.date().isoformat(),
            "age_reference_dt": age_reference_dt,
            "detected_dt": candidate_dt,
            "priority_rank": 2,
            "detected_by": "body_date",
            "age_basis": age_basis,
        }

    if created_at is not None:
        return {
            "content_date": created_at.date().isoformat(),
            "age_reference_dt": created_at,
            "detected_dt": created_at,
            "priority_rank": 3,
            "detected_by": "created_at",
            "age_basis": "created_at",
        }

    return {
        "content_date": now.date().isoformat(),
        "age_reference_dt": now,
        "detected_dt": now,
        "priority_rank": 4,
        "detected_by": "fallback_now",
        "age_basis": "fallback_now",
    }


def _estimate_game_start_dt(reference_date: str, title: str, body_text: str) -> tuple[datetime, str]:
    base_date = datetime.fromisoformat(reference_date).date()
    search_text = "\n".join((title or "", body_text or "")).strip()
    match = GAME_START_TIME_RE.search(search_text)
    if match:
        if match.group(1) is not None and match.group(2) is not None:
            hour, minute = int(match.group(1)), int(match.group(2))
        else:
            hour, minute = int(match.group(3) or 0), int(match.group(4) or 0)
        return datetime(base_date.year, base_date.month, base_date.day, hour, minute, tzinfo=JST), "explicit"
    return (
        datetime(base_date.year, base_date.month, base_date.day, DEFAULT_GAME_START_HOUR, 0, tzinfo=JST),
        "default",
    )


def freshness_check(raw_post: dict[str, Any], record: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now_jst = _now_jst(now)
    subtype = _resolved_subtype(raw_post, record)
    threshold_hours = _freshness_threshold_hours(subtype)
    content_info = _resolve_content_datetime(raw_post, record, now=now_jst)
    age_reference_dt = content_info["age_reference_dt"]
    age_hours = max(0.0, (now_jst - age_reference_dt).total_seconds() / 3600.0)
    freshness_class = "fresh"
    hard_stop_flag: str | None = None
    reason_parts = [
        f"subtype={subtype}",
        f"threshold={threshold_hours:g}h",
        f"priority={content_info['priority_rank']}",
        f"detected_by={content_info['detected_by']}",
        f"age_basis={content_info['age_basis']}",
        f"content_date={content_info['content_date']}",
        f"age_hours={age_hours:.2f}",
    ]

    if subtype in LINEUP_FRESHNESS_SUBTYPES:
        game_start_dt, start_source = _estimate_game_start_dt(
            str(content_info["content_date"]),
            str(record.get("title") or ""),
            str(record.get("body_text") or ""),
        )
        if now_jst >= game_start_dt:
            freshness_class = "expired"
            hard_stop_flag = "expired_lineup_or_pregame"
            reason_parts.append(
                f"game_start_estimate={game_start_dt.strftime('%Y-%m-%dT%H:%M:%S%z')}({start_source})"
            )
        elif age_hours > threshold_hours:
            freshness_class = "expired"
            hard_stop_flag = "expired_lineup_or_pregame"
    elif subtype in GAME_CONTEXT_FRESHNESS_SUBTYPES and age_hours > threshold_hours:
        freshness_class = "expired"
        hard_stop_flag = "expired_game_context"
    elif age_hours > threshold_hours:
        freshness_class = "stale"
        hard_stop_flag = "stale_for_breaking_board"

    if hard_stop_flag is None:
        reason_parts.append("status=fresh")
    else:
        reason_parts.append(f"hard_stop={hard_stop_flag}")

    return {
        "subtype": subtype,
        "content_date": str(content_info["content_date"]),
        "freshness_age_hours": round(age_hours, 2),
        "freshness_class": freshness_class,
        "freshness_reason": "; ".join(reason_parts),
        "hard_stop_flag": hard_stop_flag,
    }


def _build_game_key(record: dict[str, Any]) -> str:
    lane = str(record.get("inferred_subtype") or "other")
    opening = str(record.get("body_text") or "")[:600]
    match = OPPONENT_RE.search(opening)
    opponent = OPPONENT_CANONICAL.get(match.group(0), "unknown") if match else "unknown"
    modified_at = _parse_wp_datetime(str(record.get("modified_at") or ""))
    return f"{lane}/{opponent}/{modified_at.date().isoformat()}"


def _contains_primary_source(record: dict[str, Any]) -> bool:
    body_text = str(record.get("body_text") or "")
    source_block = str(record.get("source_block") or "")
    return bool(PRIMARY_SRC_RE.search(body_text) or PRIMARY_SRC_RE.search(source_block))


def _has_featured_media(raw_post: dict[str, Any]) -> bool:
    try:
        return int(raw_post.get("featured_media") or 0) > 0
    except (TypeError, ValueError):
        return False


def _prose_char_count(body_text: str) -> int:
    chunks: list[str] = []
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("参照元"):
            continue
        if re.fullmatch(r"https?://[^\s]+", line):
            continue
        if any(pattern.search(line) for _, pattern in SITE_COMPONENT_PATTERNS):
            continue
        chunks.append(line)
    return len("".join(chunks))


def _collect_site_component_flags(body_text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    total_chars = len(body_text)
    if total_chars <= 0:
        return findings

    positions: list[float] = []
    for _, pattern in SITE_COMPONENT_PATTERNS:
        positions.extend(match.start() / total_chars for match in pattern.finditer(body_text))
    if not positions:
        return findings

    if any(position < 0.7 for position in positions):
        findings.append(
            {
                "flag": "site_component_mixed_into_body",
                "legacy_flag": "site_component_mixed_into_body_middle",
                "detail": "middle",
            }
        )
    else:
        findings.append(
            {
                "flag": "site_component_mixed_into_body",
                "legacy_flag": "site_component_mixed_into_body_tail",
                "detail": "tail",
            }
        )
    return findings


def _body_for_nucleus_validator(body_html: str) -> str:
    body_text = _strip_html(body_html)
    fallback_lines: list[str] = []
    for line in body_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        fallback_lines.append(stripped)
        if stripped.startswith("参照元"):
            continue
        if re.fullmatch(r"https?://[^\s]+", stripped):
            continue
        if any(pattern.search(stripped) for _, pattern in SITE_COMPONENT_PATTERNS):
            continue
        if _normalize_heading_label(stripped) in LABEL_EXPECTATIONS:
            continue
        if _dev_line_categories(stripped):
            continue
        first_sentence = re.split(r"[。！？]", stripped, maxsplit=1)[0].strip()
        return first_sentence or stripped
    return fallback_lines[0] if fallback_lines else ""


def _normalize_heading_label(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("：", "").replace(":", "").strip()


def _append_reason(
    reasons: list[dict[str, Any]],
    *,
    flag: str,
    category: str,
    legacy_flag: str | None = None,
    detail: str | None = None,
) -> None:
    payload = {
        "flag": flag,
        "category": category,
    }
    if legacy_flag:
        payload["legacy_flag"] = legacy_flag
    if detail:
        payload["detail"] = detail
    if payload not in reasons:
        reasons.append(payload)


def _reason_flags(reasons: list[dict[str, Any]], category: str) -> list[str]:
    return [str(item["flag"]) for item in reasons if item.get("category") == category]


def _legacy_flags(reasons: list[dict[str, Any]], category: str) -> list[str]:
    legacy: list[str] = []
    for item in reasons:
        if item.get("category") != category:
            continue
        flag = str(item.get("legacy_flag") or item["flag"])
        if flag not in legacy:
            legacy.append(flag)
    return legacy


def _merge_legacy_flags(*flag_groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in flag_groups:
        for flag in group:
            if flag not in merged:
                merged.append(flag)
    return merged


def _heading_sentence_as_h3_hits(body_html: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for match in H3_RE.finditer(body_html or ""):
        heading_text = _strip_html(match.group(1))
        if len(heading_text) < 30:
            continue
        has_sentence_signal = bool("。" in heading_text or HEADING_SENTENCE_END_RE.search(heading_text))
        if not has_sentence_signal:
            continue
        if not (re.search(r"[0-9０-９]", heading_text) or PLAYER_HEURISTIC_RE.search(heading_text)):
            continue
        hits.append({"type": "heading_sentence_as_h3", "heading": heading_text})
    return hits


def _weird_heading_labels(body_html: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for match in H3_RE.finditer(body_html or ""):
        heading_text = _strip_html(match.group(1))
        label = _normalize_heading_label(heading_text)
        expectations = LABEL_EXPECTATIONS.get(label)
        if expectations is None:
            continue
        next_heading = NEXT_HEADING_RE.search(body_html, match.end())
        section_html = body_html[match.end() : next_heading.start() if next_heading else len(body_html)]
        section_text = _strip_html(section_html)
        if len(section_text) < 20:
            continue
        if any(pattern.search(section_text) for pattern in expectations):
            continue
        findings.append({"type": "weird_heading_label", "heading": heading_text})
    return findings


def _iter_meta_nodes(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_meta_nodes(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_meta_nodes(nested)


def _coerce_meta_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if not normalized or normalized in {"0", "false", "off", "no", "none", "null"}:
        return False
    return True


def _fact_check_risk_flags(raw_post: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    meta = (raw_post or {}).get("meta")
    for node in _iter_meta_nodes(meta):
        risk_type = str(node.get("risk_type") or "").strip()
        if risk_type in {
            "unsupported_named_fact",
            "unsupported_numeric_fact",
            "unsupported_date_time_fact",
            "unsupported_quote",
            "unsupported_attribution",
        }:
            if "unsupported_named_fact" not in flags:
                flags.append("unsupported_named_fact")
        elif risk_type in {"contradiction", "source_mismatch"}:
            if "obvious_misinformation" not in flags:
                flags.append("obvious_misinformation")
    return flags


def _has_x_sns_auto_post_risk(raw_post: dict[str, Any]) -> bool:
    meta = (raw_post or {}).get("meta")
    for node in _iter_meta_nodes(meta):
        for key, value in node.items():
            if not POSTCHECK_META_RE.search(str(key).lower()):
                continue
            if _coerce_meta_truthy(value):
                return True
    return False


def _strict_title_body_mismatch(
    title: str,
    body_text: str,
    nucleus_reason_code: str | None,
) -> bool:
    if nucleus_reason_code not in {"SUBJECT_ABSENT", "EVENT_DIVERGE"}:
        return False
    opening = "\n".join(line.strip() for line in body_text.splitlines()[:4] if line.strip())
    title_has_lineup = bool(LINEUP_SIGNAL_RE.search(title))
    body_has_lineup = bool(LINEUP_SIGNAL_RE.search(opening))
    title_has_postgame = bool(POSTGAME_SIGNAL_RE.search(title))
    body_has_postgame = bool(POSTGAME_SIGNAL_RE.search(opening))
    if title_has_lineup and body_has_postgame and not body_has_lineup:
        return True
    if title_has_postgame and body_has_lineup and not body_has_postgame:
        return True
    return False


def _title_body_reason_flag(title: str, body_text: str, nucleus_reason_code: str | None) -> str:
    if nucleus_reason_code == "MULTIPLE_NUCLEI":
        return "cross_article_contamination"
    if _strict_title_body_mismatch(title, body_text, nucleus_reason_code):
        return "title_body_mismatch_strict"
    return "title_body_mismatch_partial"


def _has_low_severity_numerical_anomaly(body_text: str) -> bool:
    return bool(LOW_SEVERITY_NUMERIC_RE.search(body_text))


def _has_light_structure_break(body_html: str) -> bool:
    return bool(LIGHT_STRUCTURE_BREAK_RE.search(body_html or ""))


def _has_ai_tone_heading_or_lead(title: str, body_text: str) -> bool:
    if SPECULATIVE_TITLE_RE.search(title):
        return True
    lead = "\n".join(line.strip() for line in body_text.splitlines()[:3] if line.strip())
    return bool(AI_TONE_LEAD_RE.search(lead))


def _dev_line_categories(line: str) -> set[str]:
    categories: set[str] = set()
    if "Traceback (most recent call last)" in line or re.search(r"^[A-Za-z_]+Error:\s", line):
        categories.add("traceback")
    if any(token in line for token in ("python3 -m", "git diff", "git log", "git push")):
        categories.add("command")
    if any(token in line for token in ("wsl.exe", "cmd /c", "bash -lc")):
        categories.add("shell")
    if any(token in line for token in ("--full-auto", "--skip-git-repo-check")):
        categories.add("flag")
    if any(token in line for token in ("commit_hash", "task_id", "bg_id")) or re.search(r"bg_[a-z0-9]{8}", line):
        categories.add("meta_id")
    if any(token in line for token in ("[scan] emitted=", "[result] post_id=", "status=sent", "status=suppressed")):
        categories.add("result")
    lowered = line.lower()
    if "tokens used" in lowered or "changed_files" in line or "open_questions" in line:
        categories.add("agent_meta")
    if re.search(r"\b(Codex|Claude)\b", line):
        categories.add("agent_name")
    return categories


def _build_block_detail(block_type: str, lines: list[str], categories: set[str]) -> dict[str, Any]:
    preview = "\n".join(lines[:5]).strip()
    return {
        "block_type": block_type,
        "line_count": len(lines),
        "categories": sorted(categories),
        "preview": preview,
    }


def _detect_dev_log_blocks(body_html: str, body_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clear_blocks: list[dict[str, Any]] = []
    scattered_blocks: list[dict[str, Any]] = []

    for pattern, block_type in ((PRE_BLOCK_RE, "pre_block"), (CODE_BLOCK_RE, "code_block")):
        for match in pattern.finditer(body_html or ""):
            block_lines = [line.strip() for line in _strip_html(match.group(1)).splitlines() if line.strip()]
            if not block_lines:
                continue
            categories = {"code_block"}
            for line in block_lines:
                categories.update(_dev_line_categories(line))
            detail = _build_block_detail(block_type, block_lines, categories)
            if len(block_lines) >= 5 and len(categories) >= 2:
                clear_blocks.append(detail)
            elif len(categories) >= 2 or "code_block" in categories:
                scattered_blocks.append(detail)

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    block_lines: list[str] = []
    block_categories: set[str] = set()
    for line in lines + [""]:
        categories = _dev_line_categories(line)
        if categories:
            block_lines.append(line)
            block_categories.update(categories)
            continue
        if not block_lines:
            continue
        detail = _build_block_detail("line_block", block_lines, block_categories)
        if len(block_lines) >= 5 and len(block_categories) >= 2:
            clear_blocks.append(detail)
        elif block_categories:
            scattered_blocks.append(detail)
        block_lines = []
        block_categories = set()
    return clear_blocks, scattered_blocks


def _evaluate_record(raw_post: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    record = extractor.extract_post_record(raw_post)
    title = str(record.get("title") or "")
    body_html = str(record.get("body_html") or "")
    body_text = str(record.get("body_text") or "")
    modified = str(record.get("modified_at") or "")
    game_key = _build_game_key(record)

    reasons: list[dict[str, Any]] = []
    cleanup_details: list[dict[str, Any]] = []

    if not _has_featured_media(raw_post):
        _append_reason(reasons, flag="missing_featured_media", category="repairable")
    if not _contains_primary_source(record):
        repairable_flag = "weak_source_display" if record.get("source_urls") else "missing_primary_source"
        _append_reason(
            reasons,
            flag=repairable_flag,
            category="repairable",
            legacy_flag="missing_primary_source" if repairable_flag == "weak_source_display" else None,
        )
    if _has_ai_tone_heading_or_lead(title, body_text):
        _append_reason(
            reasons,
            flag="ai_tone_heading_or_lead",
            category="repairable",
            legacy_flag="speculative_title" if SPECULATIVE_TITLE_RE.search(title) else None,
        )
    if INJURY_DEATH_RE.search(title) or INJURY_DEATH_RE.search(body_text):
        _append_reason(reasons, flag="injury_death", category="hard_stop")
    if RANKING_LIST_ONLY_RE.search(body_text):
        _append_reason(reasons, flag="ranking_list_only", category="hard_stop")

    for risk_flag in _fact_check_risk_flags(raw_post):
        _append_reason(reasons, flag=risk_flag, category="hard_stop")
    if _has_x_sns_auto_post_risk(raw_post):
        _append_reason(reasons, flag="x_sns_auto_post_risk", category="hard_stop")

    for site_flag in _collect_site_component_flags(body_text):
        _append_reason(
            reasons,
            flag=site_flag["flag"],
            category="repairable",
            legacy_flag=site_flag.get("legacy_flag"),
            detail=site_flag.get("detail"),
        )

    nucleus_result = validate_title_body_nucleus(
        title,
        _body_for_nucleus_validator(body_html),
        str(record.get("inferred_subtype") or ""),
    )
    if not nucleus_result.aligned:
        mismatch_flag = _title_body_reason_flag(title, body_text, nucleus_result.reason_code)
        mismatch_category = "hard_stop" if mismatch_flag in HARD_STOP_FLAGS else "repairable"
        _append_reason(
            reasons,
            flag=mismatch_flag,
            category=mismatch_category,
            legacy_flag="title_body_mismatch" if mismatch_category == "hard_stop" else None,
            detail=nucleus_result.reason_code,
        )

    heading_hits = _heading_sentence_as_h3_hits(body_html)
    cleanup_details.extend(heading_hits)
    if heading_hits:
        _append_reason(reasons, flag="heading_sentence_as_h3", category="repairable")

    weird_label_hits = _weird_heading_labels(body_html)
    if weird_label_hits:
        _append_reason(reasons, flag="weird_heading_label", category="repairable")

    dev_log_blocks, scattered_dev_logs = _detect_dev_log_blocks(body_html, body_text)
    for detail in dev_log_blocks:
        cleanup_details.append({"type": "dev_log_contamination", **detail})
    if dev_log_blocks:
        _append_reason(reasons, flag="dev_log_contamination", category="repairable")
    if scattered_dev_logs and not dev_log_blocks:
        _append_reason(reasons, flag="dev_log_contamination_scattered", category="hard_stop")

    if _has_light_structure_break(body_html):
        _append_reason(reasons, flag="light_structure_break", category="repairable")
    if str(record.get("inferred_subtype") or "") == "other":
        _append_reason(reasons, flag="subtype_unresolved", category="repairable")
    if _prose_char_count(body_text) > 3500:
        _append_reason(reasons, flag="long_body", category="repairable")
    if _has_low_severity_numerical_anomaly(body_text):
        _append_reason(reasons, flag="numerical_anomaly_low_severity", category="repairable")

    freshness = freshness_check(raw_post, record, now=now)
    enforce_freshness = str(raw_post.get("status") or "").strip().lower() != "publish"
    if enforce_freshness and freshness["hard_stop_flag"] is not None:
        freshness_flag = str(freshness["hard_stop_flag"])
        freshness_category = "repairable" if freshness_flag in REPAIRABLE_FLAGS else "hard_stop"
        _append_reason(reasons, flag=freshness_flag, category=freshness_category)

    hard_stop_flags = _reason_flags(reasons, "hard_stop")
    repairable_flags = _reason_flags(reasons, "repairable")
    red_flags = _legacy_flags(reasons, "hard_stop")
    yellow_reasons = _legacy_flags(reasons, "repairable")
    cleanup_types = list(dict.fromkeys(detail["type"] for detail in cleanup_details))
    publishable = not bool(hard_stop_flags)
    cleanup_required = bool(repairable_flags) and publishable
    entry_category = "hard_stop" if hard_stop_flags else "repairable" if repairable_flags else "clean"

    entry = {
        "post_id": int(record["post_id"]),
        "title": title,
        "modified": modified,
        "game_key": game_key,
        "subtype": freshness["subtype"],
        "category": entry_category,
        "publishable": publishable,
        "cleanup_required": cleanup_required,
        "reasons": reasons,
        "hard_stop_flags": hard_stop_flags,
        "repairable_flags": repairable_flags,
        "soft_cleanup_flags": repairable_flags,
        "content_date": freshness["content_date"],
        "freshness_age_hours": freshness["freshness_age_hours"],
        "freshness_class": freshness["freshness_class"],
        "freshness_reason": freshness["freshness_reason"],
    }

    if red_flags:
        entry["red_flags"] = _merge_legacy_flags(red_flags, yellow_reasons)
        if yellow_reasons:
            entry["yellow_reasons"] = yellow_reasons
        if any(flag in {"title_body_mismatch_strict", "title_body_mismatch_partial", "cross_article_contamination"} for flag in hard_stop_flags + repairable_flags):
            entry["nucleus_reason_code"] = nucleus_result.reason_code
        return {
            "judgment": "red",
            "entry": entry,
            "cleanup_candidate": None,
        }

    if yellow_reasons:
        entry["yellow_reasons"] = yellow_reasons
        entry["needs_hallucinate_re_evaluation"] = True
        cleanup_candidate = None
        if cleanup_types:
            cleanup_candidate = {
                "post_id": entry["post_id"],
                "title": title,
                "game_key": game_key,
                "cleanup_types": cleanup_types,
                "repairable_flags": repairable_flags,
                "details": cleanup_details,
                "post_judgment": "repairable",
            }
        return {
            "judgment": "yellow",
            "entry": entry,
            "cleanup_candidate": cleanup_candidate,
        }

    entry["needs_hallucinate_re_evaluation"] = True
    entry["reason_summary"] = "featured_media, primary_source, title_body_aligned"
    return {
        "judgment": "green",
        "entry": entry,
        "cleanup_candidate": None,
    }


def _lineup_red_flags(decision: dict[str, Any] | None) -> list[str]:
    if not decision:
        return []
    status = str(decision.get("status") or "").strip().lower()
    if status == "duplicate_absorbed":
        return ["lineup_duplicate_excessive"]
    if status == "deferred":
        return ["lineup_no_hochi_source"]
    if status == "prefix_violation":
        return ["lineup_prefix_misuse"]
    return []


def _duplicate_guard_game_id(raw_post: dict[str, Any]) -> str:
    meta = (raw_post or {}).get("meta") or {}
    for value in (meta.get("game_id"), raw_post.get("game_id")):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    extracted = str(extract_game_id(raw_post) or "").strip()
    return extracted


def _title_duplicate_cluster_requires_hard_stop(candidates: list[dict[str, Any]]) -> bool:
    game_ids = {str(candidate.get("game_id") or "").strip() for candidate in candidates if str(candidate.get("game_id") or "").strip()}
    missing_game_id = any(not str(candidate.get("game_id") or "").strip() for candidate in candidates)
    if missing_game_id or len(game_ids) > 1:
        return True
    subtypes = {str(candidate.get("subtype") or "").strip().lower() for candidate in candidates}
    return subtypes != {"lineup_notice"}


def _append_title_duplicate_matches(
    grouped_candidates: dict[str, list[dict[str, Any]]],
    *,
    match_type: str,
    by_post_id: dict[int, dict[str, Any]],
) -> None:
    for candidates in grouped_candidates.values():
        if len(candidates) < 2 or not _title_duplicate_cluster_requires_hard_stop(candidates):
            continue
        for candidate in candidates:
            post_id = int(candidate["post_id"])
            payload = by_post_id.setdefault(
                post_id,
                {
                    "post_id": post_id,
                    "status": "title_duplicate_cluster",
                    "reason": "title_duplicate_cluster",
                    "match_types": [],
                },
            )
            match_types = payload["match_types"]
            if match_type not in match_types:
                match_types.append(match_type)


def _title_duplicate_decisions(raw_posts: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_exact_key: dict[str, list[dict[str, Any]]] = {}
    by_normalized_key: dict[str, list[dict[str, Any]]] = {}
    by_token_key: dict[str, list[dict[str, Any]]] = {}

    for raw_post in raw_posts:
        record = extractor.extract_post_record(raw_post)
        post_id = int(record["post_id"])
        title = str(record.get("title") or "")
        subtype = _resolved_subtype(raw_post, record)
        candidate = {
            "post_id": post_id,
            "title": title,
            "subtype": subtype,
            "game_id": _duplicate_guard_game_id(raw_post),
        }

        exact_key = _exact_title_duplicate_key(title)
        if exact_key:
            by_exact_key.setdefault(exact_key, []).append(candidate)

        normalized_key = _normalized_title_duplicate_key(title)
        if normalized_key:
            by_normalized_key.setdefault(normalized_key, []).append(candidate)

        if subtype in LINEUP_TITLE_TOKEN_MATCH_SUBTYPES:
            token_key = _lineup_title_token_duplicate_key(title)
            if token_key:
                by_token_key.setdefault(token_key, []).append(candidate)

    by_post_id: dict[int, dict[str, Any]] = {}
    _append_title_duplicate_matches(by_exact_key, match_type="exact_title_match", by_post_id=by_post_id)
    _append_title_duplicate_matches(
        by_normalized_key,
        match_type="normalized_suffix_title_match",
        by_post_id=by_post_id,
    )
    _append_title_duplicate_matches(by_token_key, match_type="lineup_title_token_match", by_post_id=by_post_id)

    return by_post_id


def _merge_lineup_decision(entry: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
    if not decision:
        return entry
    merged = dict(entry)
    merged["lineup_priority_status"] = decision.get("status")
    merged["lineup_priority_reason"] = decision.get("reason")
    for key in (
        "candidate_key",
        "game_id",
        "source_url",
        "source_name",
        "source_domain",
        "is_hochi_source",
        "representative_post_id",
        "representative_source_url",
        "subtype",
    ):
        value = decision.get(key)
        if value not in (None, ""):
            merged[key] = value
    return merged


def _apply_lineup_guard(
    evaluated: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    merged_entry = _merge_lineup_decision(evaluated["entry"], decision)
    extra_red_flags = _lineup_red_flags(decision)
    if not extra_red_flags:
        return {
            "judgment": evaluated["judgment"],
            "entry": merged_entry,
            "cleanup_candidate": evaluated["cleanup_candidate"],
        }

    entry = dict(merged_entry)
    reasons = list(entry.get("reasons") or [])
    legacy_map = {
        "lineup_duplicate_excessive": "lineup_duplicate_absorbed_by_hochi",
        "lineup_no_hochi_source": "lineup_no_hochi_source",
        "lineup_prefix_misuse": "lineup_prefix_misuse",
    }
    for flag in extra_red_flags:
        _append_reason(
            reasons,
            flag=flag,
            category="hard_stop",
            legacy_flag=legacy_map.get(flag),
            detail=str(decision.get("reason") or ""),
        )
    entry["reasons"] = reasons
    entry["hard_stop_flags"] = _reason_flags(reasons, "hard_stop")
    entry["repairable_flags"] = _reason_flags(reasons, "repairable")
    entry["soft_cleanup_flags"] = entry["repairable_flags"]
    entry["publishable"] = False
    entry["cleanup_required"] = False
    entry["category"] = "hard_stop"
    yellow_reasons = _legacy_flags(reasons, "repairable")
    entry["red_flags"] = _merge_legacy_flags(_legacy_flags(reasons, "hard_stop"), yellow_reasons)
    if yellow_reasons:
        entry["yellow_reasons"] = yellow_reasons
    entry.pop("reason_summary", None)
    cleanup_candidate = None
    return {
        "judgment": "red",
        "entry": entry,
        "cleanup_candidate": cleanup_candidate,
    }


def _apply_title_duplicate_guard(
    evaluated: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    if not decision:
        return evaluated

    entry = dict(evaluated["entry"])
    reasons = list(entry.get("reasons") or [])
    entry["duplicate_title_match_types"] = list(decision.get("match_types") or [])
    if "lineup_duplicate_excessive" not in _reason_flags(reasons, "hard_stop"):
        _append_reason(
            reasons,
            flag="lineup_duplicate_excessive",
            category="hard_stop",
            detail=";".join(entry["duplicate_title_match_types"]) or str(decision.get("reason") or ""),
        )
    entry["reasons"] = reasons
    entry["hard_stop_flags"] = _reason_flags(reasons, "hard_stop")
    entry["repairable_flags"] = _reason_flags(reasons, "repairable")
    entry["soft_cleanup_flags"] = entry["repairable_flags"]
    entry["publishable"] = False
    entry["cleanup_required"] = False
    entry["category"] = "hard_stop"
    yellow_reasons = _legacy_flags(reasons, "repairable")
    entry["red_flags"] = _merge_legacy_flags(_legacy_flags(reasons, "hard_stop"), yellow_reasons)
    if yellow_reasons:
        entry["yellow_reasons"] = yellow_reasons
    entry.pop("reason_summary", None)
    return {
        "judgment": "red",
        "entry": entry,
        "cleanup_candidate": None,
    }


def _published_today_keys(raw_posts: list[dict[str, Any]], *, now: datetime) -> tuple[set[str], set[str]]:
    title_keys: set[str] = set()
    game_keys: set[str] = set()
    today = _now_jst(now).date()
    for raw_post in raw_posts:
        record = extractor.extract_post_record(raw_post)
        published_at = _parse_wp_datetime(str(raw_post.get("date") or record.get("created_at") or ""), fallback_now=now)
        if published_at.date() != today:
            continue
        title_keys.add(_normalize_title_key(str(record.get("title") or "")))
        game_keys.add(_build_game_key(record))
    return title_keys, game_keys


def evaluate_raw_posts(
    raw_posts: list[dict[str, Any]],
    *,
    window_hours: int,
    max_pool: int,
    now: datetime | None = None,
    published_today_raw_posts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now_jst = _now_jst(now)
    cutoff = now_jst - timedelta(hours=max(0, int(window_hours)))
    title_keys: set[str] = set()
    game_keys: set[str] = set()
    if published_today_raw_posts:
        title_keys, game_keys = _published_today_keys(published_today_raw_posts, now=now_jst)

    green: list[dict[str, Any]] = []
    yellow: list[dict[str, Any]] = []
    red: list[dict[str, Any]] = []
    cleanup_candidates: list[dict[str, Any]] = []

    filtered: list[dict[str, Any]] = []
    for raw_post in raw_posts[: max(0, int(max_pool))]:
        record = extractor.extract_post_record(raw_post)
        modified_at = _parse_wp_datetime(str(record.get("modified_at") or ""), fallback_now=now_jst)
        if modified_at < cutoff:
            continue
        if title_keys or game_keys:
            title_key = _normalize_title_key(str(record.get("title") or ""))
            game_key = _build_game_key(record)
            if title_key in title_keys or game_key in game_keys:
                continue
        filtered.append(raw_post)

    lineup_dedup = compute_lineup_dedup(filtered)
    title_duplicate_by_post_id = _title_duplicate_decisions(filtered)
    lineup_by_post_id = {
        int(post_id): decision
        for post_id, decision in lineup_dedup.get("by_post_id", {}).items()
        if str(post_id).strip()
    }

    for raw_post in filtered:
        evaluated = _evaluate_record(raw_post, now=now_jst)
        decision = lineup_by_post_id.get(int(evaluated["entry"]["post_id"]))
        evaluated = _apply_lineup_guard(evaluated, decision)
        title_duplicate_decision = title_duplicate_by_post_id.get(int(evaluated["entry"]["post_id"]))
        evaluated = _apply_title_duplicate_guard(evaluated, title_duplicate_decision)
        judgment = evaluated["judgment"]
        if judgment == "green":
            green.append(evaluated["entry"])
        elif judgment == "yellow":
            yellow.append(evaluated["entry"])
        else:
            red.append(evaluated["entry"])
        if evaluated["cleanup_candidate"] is not None:
            cleanup_candidates.append(evaluated["cleanup_candidate"])

    cleanup_post_ids = {candidate["post_id"] for candidate in cleanup_candidates}
    all_entries = [*green, *yellow, *red]
    stale_top_list = sorted(
        (
            {
                "post_id": int(entry["post_id"]),
                "title": str(entry["title"]),
                "content_date": str(entry.get("content_date") or ""),
                "age_hours": float(entry.get("freshness_age_hours") or 0.0),
                "subtype": str(entry.get("subtype") or ""),
                "freshness_class": str(entry.get("freshness_class") or "fresh"),
                "freshness_reason": str(entry.get("freshness_reason") or ""),
            }
            for entry in all_entries
            if entry.get("freshness_class") in FRESHNESS_HOLD_CLASSES
        ),
        key=lambda item: item["age_hours"],
        reverse=True,
    )[:10]
    report = {
        "scan_meta": {
            "window_hours": int(window_hours),
            "max_pool": int(max_pool),
            "scanned": len(filtered),
            "ts": now_jst.isoformat(),
        },
        "green": green,
        "yellow": yellow,
        "red": red,
        "cleanup_candidates": cleanup_candidates,
        "lineup_dedup": lineup_dedup,
        "stale_top_list": stale_top_list,
        "summary": {
            "green_count": len(green),
            "yellow_count": len(yellow),
            "red_count": len(red),
            "cleanup_count": len(cleanup_candidates),
            "hard_stop_count": len(red),
            "repairable_count": len(yellow),
            "clean_count": len(green),
            "soft_cleanup_count": len(yellow),
            "publishable_count": len(green) + len(yellow),
            "publishable_minus_cleanup_pending": (len(green) + len(yellow)) - len(cleanup_post_ids),
            "fresh_count": sum(1 for entry in all_entries if entry.get("freshness_class") == "fresh"),
            "stale_hold_count": sum(1 for entry in all_entries if entry.get("freshness_class") == "stale"),
            "expired_hold_count": sum(1 for entry in all_entries if entry.get("freshness_class") == "expired"),
            "lineup_representative_count": int(lineup_dedup["summary"]["representative_count"]),
            "lineup_duplicate_absorbed_count": int(lineup_dedup["summary"]["duplicate_absorbed_count"]),
            "lineup_deferred_count": int(lineup_dedup["summary"]["deferred_count"]),
            "lineup_prefix_violation_count": int(lineup_dedup["summary"]["prefix_violation_count"]),
        },
    }
    return report


def scan_wp_drafts(
    wp_client,
    *,
    window_hours: int,
    max_pool: int,
    exclude_published_today: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    scan_limit = max(1, min(int(max_pool), 100))
    raw_posts = wp_client.list_posts(
        status="draft",
        per_page=scan_limit,
        orderby="modified",
        order="desc",
        context="edit",
    )
    published_today_raw_posts: list[dict[str, Any]] | None = None
    if exclude_published_today:
        published_today_raw_posts = wp_client.list_posts(
            status="publish",
            per_page=scan_limit,
            orderby="date",
            order="desc",
            context="edit",
        )
    return evaluate_raw_posts(
        list(raw_posts or []),
        window_hours=window_hours,
        max_pool=scan_limit,
        now=now,
        published_today_raw_posts=list(published_today_raw_posts or []),
    )


def render_human_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    scan_meta = report["scan_meta"]
    lines = [
        "Guarded Publish Evaluator Dry Run",
        f"window_hours={scan_meta['window_hours']}  max_pool={scan_meta['max_pool']}  scanned={scan_meta['scanned']}  ts={scan_meta['ts']}",
        "",
        "Summary",
        "status   count",
        f"green    {summary['green_count']}",
        f"yellow   {summary['yellow_count']}",
        f"red      {summary['red_count']}",
        f"hard_stop {summary['hard_stop_count']}",
        f"repairable {summary['repairable_count']}",
        f"clean {summary['clean_count']}",
        f"soft_cleanup {summary['soft_cleanup_count']}",
        f"cleanup  {summary['cleanup_count']}",
        f"publishable {summary['publishable_count']}",
        f"publishable_minus_cleanup_pending {summary['publishable_minus_cleanup_pending']}",
        f"fresh {summary['fresh_count']}",
        f"stale_hold {summary['stale_hold_count']}",
        f"expired_hold {summary['expired_hold_count']}",
    ]

    for label in ("green", "yellow", "red"):
        lines.extend(["", f"{label.title()} Preview"])
        entries = report[label]
        if not entries:
            lines.append("- none")
            continue
        for entry in entries[:5]:
            flags = entry.get("yellow_reasons") or entry.get("red_flags") or []
            suffix = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"- {entry['post_id']} | {entry['title']}{suffix}")
    lines.extend(["", "Freshness Hold Top"])
    stale_top_list = report.get("stale_top_list") or []
    if not stale_top_list:
        lines.append("- none")
    else:
        for item in stale_top_list:
            lines.append(
                "- "
                f"{item['post_id']} | {item['title']} | {item['content_date']} | "
                f"{item['age_hours']:.2f}h | {item['subtype']} | {item['freshness_class']} | {item['freshness_reason']}"
            )
    return "\n".join(lines) + "\n"


def dump_report(report: dict[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(report: dict[str, Any], *, fmt: str, output_path: str | None) -> str:
    rendered = dump_report(report, fmt=fmt)
    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


__all__ = [
    "dump_report",
    "evaluate_raw_posts",
    "render_human_report",
    "scan_wp_drafts",
    "write_report",
]
