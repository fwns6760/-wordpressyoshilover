"""Publish notice mail adapter built on top of ticket 072 bridge."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
from typing import Any, Literal
from zoneinfo import ZoneInfo

from src.mail_delivery_bridge import send as bridge_send_default


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUMMARY_EVERY = 10
DEFAULT_DAILY_CAP = 100
DEFAULT_DUPLICATE_WINDOW = timedelta(minutes=30)
DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH = ROOT / "logs" / "guarded_publish_yellow_log.jsonl"
_WHITESPACE_RE = re.compile(r"\s+")
_SUMMARY_TITLE_LIMIT = 80
MAX_MANUAL_X_POST_LENGTH = 280
_MANUAL_X_TEMPLATE_TYPES = (
    "article_intro",
    "why_it_matters",
    "fan_reaction_hook",
    "lineup_focus",
    "lineup_order_note",
    "postgame_turning_point",
    "postgame_recheck",
    "farm_watch",
    "notice_note",
    "notice_careful",
    "event_detail",
    "event_inside_voice",
    "program_memo",
    "inside_voice",
)
_MANUAL_X_URL_TEMPLATES = frozenset(
    {
        "article_intro",
        "why_it_matters",
        "fan_reaction_hook",
        "lineup_focus",
        "lineup_order_note",
        "postgame_turning_point",
        "postgame_recheck",
        "farm_watch",
        "notice_note",
        "notice_careful",
        "event_detail",
        "event_inside_voice",
        "program_memo",
    }
)
_MANUAL_X_SENSITIVE_WORDS = (
    "怪我",
    "けが",
    "ケガ",
    "負傷",
    "故障",
    "違和感",
    "リハビリ",
    "復帰",
    "手術",
    "診断",
)
_MANUAL_X_PREFIX_TRIM_CHARS = " /／|｜:：-・、"
_MANUAL_X_SUMMARY_SOURCE_PREFIX_RE = re.compile(
    r"^(?:"
    r"報知新聞|"
    r"スポーツ報知巨人班X|"
    r"スポーツ報知X|"
    r"スポーツ報知|"
    r"報知野球X|"
    r"日刊スポーツ(?:\s*X)?|"
    r"スポニチ野球記者X|"
    r"スポニチ|"
    r"サンスポ巨人X|"
    r"サンスポ|"
    r"巨人公式X|"
    r"読売ジャイアンツX|"
    r"Yahoo!?スポーツ(?:ナビ)?|"
    r"Yahoo!ニュース"
    r")\s*(?:/|／|\||｜|:|：)?\s*"
)
_MANUAL_X_SUMMARY_LABEL_PREFIX_RE = re.compile(
    r"^(?:GIANTS(?:\s+[A-Z]+){0,4}|BREAKING(?:\s+[A-Z]+){0,4}|LIVE(?:\s+[A-Z]+){0,4}|TV(?:\s+[A-Z]+){0,4})\s*"
)
_MANUAL_X_SUMMARY_ARTICLE_PREFIX_RE = re.compile(r"^【巨人】\s*")
_MANUAL_X_SUMMARY_TRUNCATION_RE = re.compile(r"(?:\s*(?:\[\.\.\.\]|\[\u2026\]|…|\.\.\.))+\s*$")
_MANUAL_X_DATE_RE = re.compile(r"(?:(\d{1,2})月(\d{1,2})日|(\d{1,2})[/.・](\d{1,2})(?:日)?)")
_MANUAL_X_EVENT_ACTOR_RE = re.compile(r"([一-龯々ぁ-んァ-ヴー]{2,12}(?:監督|コーチ|投手|捕手|内野手|外野手|選手))")
_MANUAL_X_NOTICE_EVENT_KEYWORDS = (
    "開催",
    "日程",
    "予定",
    "イベント",
    "伝統の一戦",
    "女子チーム",
    "ファンフェス",
    "GIANTS MANAGER NOTE",
)
_ALERT_LABELS = {
    "publish_failure": "publish failure",
    "hard_stop": "hard stop",
    "postcheck_failure": "postcheck failure",
    "cleanup_hold": "cleanup hold",
    "x_sns_auto_post_risk": "X/SNS auto-post risk",
}
_SUBJECT_BRAND_SUFFIX = " | YOSHILOVER"
_SUBJECT_BODY_LIMIT = 80
_MAIL_CLASS_CONFIGS = {
    "publish": {
        "prefix": "【公開済】",
        "action": "check_article",
        "priority": "normal",
    },
    "x_candidate": {
        "prefix": "【投稿候補】",
        "action": "copy_x_post",
        "priority": "normal",
    },
    "review": {
        "prefix": "【要確認】",
        "action": "review_article",
        "priority": "high",
    },
    "warning": {
        "prefix": "【警告】",
        "action": "inspect_system",
        "priority": "high",
    },
    "summary": {
        "prefix": "【まとめ】",
        "action": "batch_review",
        "priority": "low",
    },
    "urgent": {
        "prefix": "【緊急】",
        "action": "urgent_check",
        "priority": "urgent",
    },
}
_SAFE_X_CANDIDATE_ARTICLE_TYPES = frozenset({"default", "lineup", "postgame", "farm", "program"})
_CAUTIOUS_REVIEW_ARTICLE_TYPES = frozenset({"notice", "notice_event"})
_MANUAL_X_DIRTY_MARKERS = (
    "📰",
    "⚾",
    "GIANTS MANAGER NOTE",
    "報知新聞",
    "スポーツ報知",
    "スポニチ",
    "サンスポ",
    "Yahoo!",
    "[…]",
    "[...]",
)
_URGENT_KEYWORDS = (
    "訃報",
    "死去",
    "逝去",
    "急逝",
    "死亡",
    "重体",
    "重傷",
    "心肺停止",
    "緊急",
)


@dataclass(frozen=True)
class PublishNoticeRequest:
    post_id: int | str
    title: str
    canonical_url: str
    subtype: str
    publish_time_iso: str
    summary: str | None = None


@dataclass(frozen=True)
class ManualXContext:
    article_type: str
    title: str
    url: str
    cleaned_summary: str
    hook_source: str
    summary_fallback: bool
    event_subject: str
    event_title: str
    event_name: str
    event_dates: str
    event_actor: str


@dataclass(frozen=True)
class BurstSummaryEntry:
    post_id: int | str
    title: str
    category: str
    publishable: bool
    cleanup_required: bool
    cleanup_success: bool | None


@dataclass(frozen=True)
class BurstSummaryRequest:
    entries: list[BurstSummaryEntry]
    cumulative_published_count: int
    daily_cap: int = DEFAULT_DAILY_CAP
    hard_stop_count: int = 0
    hold_count: int = 0


@dataclass(frozen=True)
class AlertMailRequest:
    alert_type: Literal[
        "publish_failure",
        "hard_stop",
        "postcheck_failure",
        "cleanup_hold",
        "x_sns_auto_post_risk",
    ]
    post_id: int | str | None = None
    title: str | None = None
    category: str | None = None
    reason: str | None = None
    detail: str | None = None
    publishable: bool | None = None
    cleanup_required: bool | None = None
    cleanup_success: bool | None = None
    hold_reason: str | None = None


@dataclass(frozen=True)
class EmergencyMailRequest:
    post_id: int | str | None = None
    title: str | None = None
    reason: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class PublishNoticeEmailResult:
    status: Literal["sent", "dry_run", "suppressed", "error"]
    reason: str | None
    subject: str
    recipients: list[str]
    bridge_result: object | None = None


@dataclass(frozen=True)
class PublishNoticeExecutionSummary:
    emitted: int
    sent: int
    suppressed: int
    errors: int
    dry_run: int
    reasons: dict[str, int]

    @property
    def should_alert(self) -> bool:
        return self.emitted > 0 and self.sent == 0 and self.dry_run == 0


@dataclass(frozen=True)
class _BridgeMailRequest:
    to: list[str]
    subject: str
    text_body: str
    html_body: str | None = None
    sender: str | None = None
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


BridgeSend = Callable[..., object]
EmergencyHook = Callable[[EmergencyMailRequest], object | None]


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _latest_yellow_log_entry_for_post(
    post_id: int | str,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> dict[str, Any] | None:
    path = _path(yellow_log_path)
    if not path.exists():
        return None
    target = str(post_id)
    matched: dict[str, Any] | None = None
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("post_id", "")) != target:
                continue
            matched = payload
    return matched


def _normalized_recipients(values: list[str]) -> list[str]:
    recipients: list[str] = []
    for value in values:
        for item in str(value or "").split(","):
            address = item.strip()
            if address:
                recipients.append(address)
    return recipients


def _coerce_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_datetime_to_jst(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        current = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if current.tzinfo is None:
        return current.replace(tzinfo=JST)
    return current.astimezone(JST)


def _format_publish_time_jst(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    current = _parse_datetime_to_jst(text)
    if current is None:
        return text
    return current.strftime("%Y-%m-%d %H:%M JST")


def _normalize_summary(summary: str | None) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(summary or "").strip())
    if not compact:
        return "(なし)"
    if len(compact) > 120:
        return f"{compact[:119]}…"
    return compact


def _normalize_bool(value: bool | None) -> str:
    if value is None:
        return "none"
    return "true" if value else "false"


def _collapse_title(value: str) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    if len(compact) <= _SUMMARY_TITLE_LIMIT:
        return compact
    return compact[: _SUMMARY_TITLE_LIMIT - 1] + "…"


def _trim_manual_x_prefix_noise(value: str) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    while compact:
        trimmed = compact.lstrip(_MANUAL_X_PREFIX_TRIM_CHARS)
        trimmed = re.sub(r"^[📰⚾📺🎥📻🗞️🔥✨⭐️❗‼]+\s*", "", trimmed)
        trimmed = _MANUAL_X_SUMMARY_SOURCE_PREFIX_RE.sub("", trimmed)
        trimmed = trimmed.lstrip(_MANUAL_X_PREFIX_TRIM_CHARS)
        trimmed = re.sub(r"^[📰⚾📺🎥📻🗞️🔥✨⭐️❗‼]+\s*", "", trimmed)
        trimmed = _MANUAL_X_SUMMARY_LABEL_PREFIX_RE.sub("", trimmed)
        trimmed = trimmed.lstrip(_MANUAL_X_PREFIX_TRIM_CHARS)
        trimmed = _MANUAL_X_SUMMARY_ARTICLE_PREFIX_RE.sub("", trimmed)
        trimmed = trimmed.lstrip(_MANUAL_X_PREFIX_TRIM_CHARS)
        if trimmed == compact:
            return trimmed
        compact = trimmed
    return compact


def _remove_title_duplicate_from_summary(summary: str, title: str) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(summary or "").strip())
    compact_title = _WHITESPACE_RE.sub(" ", str(title or "").strip())
    title_variants: list[str] = []
    if compact_title:
        title_variants.append(compact_title)
    stripped_title = re.sub(r"^【[^】]+】\s*", "", compact_title)
    if stripped_title and stripped_title not in title_variants:
        title_variants.append(stripped_title)
    for variant in title_variants:
        if not variant:
            continue
        if compact == variant:
            continue
        if compact.startswith(variant):
            compact = compact[len(variant) :].lstrip(" 　:：-、。")
        elif variant in compact:
            compact = compact.replace(variant, " ").strip()
    return _WHITESPACE_RE.sub(" ", compact).strip()


def _strip_repeated_article_prefix(summary: str) -> str:
    positions = [match.start() for match in re.finditer(r"【巨人】", summary)]
    if len(positions) >= 2:
        return summary[: positions[1]].rstrip(" 　、,。")
    return summary


def _clean_summary_for_x_candidate(summary: str | None, *, title: str = "") -> str:
    compact = _WHITESPACE_RE.sub(" ", str(summary or "").strip())
    if not compact:
        return "(なし)"
    compact = _MANUAL_X_SUMMARY_TRUNCATION_RE.sub("", compact).rstrip(" 　、,")
    compact = _trim_manual_x_prefix_noise(compact)
    compact = _remove_title_duplicate_from_summary(compact, title)
    compact = _strip_repeated_article_prefix(compact)
    compact = _trim_manual_x_prefix_noise(compact)
    compact = _MANUAL_X_SUMMARY_TRUNCATION_RE.sub("", compact).rstrip(" 　、,")
    compact = _WHITESPACE_RE.sub(" ", compact).strip()
    return compact or "(なし)"


def _manual_x_summary_falls_back_to_title(summary: str | None, cleaned_summary: str, title: str) -> bool:
    if cleaned_summary == "(なし)":
        return True
    if len(cleaned_summary) < 30 and not cleaned_summary.endswith(("。", "！", "?", "？", "」")):
        return True
    raw_summary = _WHITESPACE_RE.sub(" ", str(summary or "").strip())
    if _MANUAL_X_SUMMARY_TRUNCATION_RE.search(raw_summary):
        return True
    if cleaned_summary.count("「") > cleaned_summary.count("」"):
        return True
    if cleaned_summary.count("『") > cleaned_summary.count("』"):
        return True
    return cleaned_summary == title


def _manual_x_is_notice_event(title: str, summary: str, raw_summary: str) -> bool:
    combined = " ".join(
        item for item in (_WHITESPACE_RE.sub(" ", str(title or "").strip()), summary, raw_summary) if item
    )
    if not combined:
        return False
    if not any(keyword in combined for keyword in _MANUAL_X_NOTICE_EVENT_KEYWORDS):
        return False
    return bool(_MANUAL_X_DATE_RE.search(combined)) or "GIANTS MANAGER NOTE" in combined.upper()


def _manual_x_event_subject(title: str, summary: str) -> str:
    combined = f"{summary} {title}"
    if "女子チーム" in combined:
        return "巨人女子チーム"
    if "ファンフェス" in combined:
        return "巨人ファンフェス"
    if "イベント" in combined:
        return "巨人イベント"
    return "巨人"


def _manual_x_event_title(title: str, summary: str) -> str:
    combined = f"{summary} {title}"
    quoted_match = re.search(r"「[^」]+」", combined)
    if quoted_match:
        return quoted_match.group(0)
    for keyword in ("伝統の一戦", "ファンフェス"):
        if keyword in combined:
            return keyword
    return ""


def _manual_x_event_name(subject: str, event_title: str) -> str:
    if event_title:
        if event_title.startswith("「"):
            return f"{subject}の{event_title}".strip()
        return f"{subject} {event_title}".strip()
    return subject or "巨人イベント"


def _manual_x_event_dates(title: str, summary: str) -> str:
    dates: list[str] = []
    for match in _MANUAL_X_DATE_RE.finditer(f"{title} {summary}"):
        month = match.group(1) or match.group(3)
        day = match.group(2) or match.group(4)
        if not month or not day:
            continue
        normalized = f"{int(month)}月{int(day)}日"
        if normalized not in dates:
            dates.append(normalized)
    return "と".join(dates)


def _manual_x_event_actor(title: str, summary: str) -> str:
    match = _MANUAL_X_EVENT_ACTOR_RE.search(f"{title} {summary}")
    return match.group(1) if match else ""


def _manual_x_article_type(subtype: str, *, title: str = "", summary: str = "", raw_summary: str = "") -> str:
    normalized = str(subtype or "").strip().lower()
    if "lineup" in normalized or "スタメン" in normalized:
        return "lineup"
    if "postgame" in normalized or "result" in normalized or "試合結果" in normalized:
        return "postgame"
    if "farm" in normalized or "二軍" in normalized or "2軍" in normalized:
        return "farm"
    if _manual_x_is_notice_event(title, summary, raw_summary):
        return "notice_event"
    if "notice" in normalized or "transaction" in normalized or "roster" in normalized or "公示" in normalized:
        return "notice"
    if "program" in normalized or "tv" in normalized or "番組" in normalized:
        return "program"
    return "default"


def _manual_x_has_sensitive_word(title: str, summary: str) -> bool:
    combined = f"{title} {summary}"
    return any(word in combined for word in _MANUAL_X_SENSITIVE_WORDS)


def _manual_x_template_sequence(article_type: str, *, sensitive: bool) -> list[str]:
    if article_type == "lineup":
        templates = ["article_intro", "lineup_focus", "inside_voice", "fan_reaction_hook"]
    elif article_type == "postgame":
        templates = ["article_intro", "postgame_turning_point", "inside_voice", "fan_reaction_hook"]
    elif article_type == "farm":
        templates = ["article_intro", "farm_watch", "inside_voice", "why_it_matters"]
    elif article_type == "notice_event":
        templates = ["article_intro", "event_detail", "event_inside_voice"]
    elif article_type == "notice":
        templates = ["article_intro", "notice_note", "notice_careful"]
    elif article_type == "program":
        templates = ["article_intro", "program_memo", "inside_voice", "why_it_matters"]
    else:
        templates = ["article_intro", "why_it_matters", "fan_reaction_hook"]

    if sensitive or article_type in {"notice", "notice_event"}:
        templates = [template for template in templates if template != "fan_reaction_hook"]
    if article_type not in {"lineup", "postgame", "farm", "program"}:
        templates = [template for template in templates if template != "inside_voice"]
    return [template for template in templates if template in _MANUAL_X_TEMPLATE_TYPES]


def _manual_x_article_intro_lead(article_type: str) -> str:
    return {
        "lineup": "巨人のスタメン情報を更新しました。",
        "postgame": "巨人の試合結果を更新しました。",
        "farm": "巨人の二軍情報を更新しました。",
        "notice": "巨人の公示・選手動向を整理しました。",
        "program": "巨人関連の番組情報を更新しました。",
    }.get(article_type, "巨人ニュースを更新しました。")


def _manual_x_fan_reaction_lead(article_type: str) -> str:
    return {
        "lineup": "このスタメン、巨人ファンはどう見る？",
        "postgame": "この試合、巨人ファンはどう見る？",
    }.get(article_type, "この話題、巨人ファンはどう見る？")


def _manual_x_inside_voice(article_type: str) -> str:
    return {
        "lineup": "この起用は試合前に見ておきたい。",
        "postgame": "これは試合後にもう一度見たいポイント。",
        "farm": "二軍の動きも追っておきたい。",
        "program": "見逃し注意の巨人関連情報です。",
    }.get(article_type, "")


def _render_manual_x_template(
    template_type: str,
    *,
    article_type: str,
    title: str,
    hook_source: str,
    summary_fallback: bool,
    event_subject: str,
    event_title: str,
    event_name: str,
    event_dates: str,
    event_actor: str,
    url: str,
    include_url: bool,
) -> str:
    suffix = f" {url}" if include_url and url else ""
    if template_type == "article_intro":
        if article_type == "notice_event":
            detail = f"{event_actor}のコメントも紹介しています。" if event_actor else "見どころも紹介しています。"
            subject = event_name or title or "巨人イベント"
            return f"{subject}開催情報を更新しました。{detail}{suffix}"
        return f"{_manual_x_article_intro_lead(article_type)}{title}{suffix}"
    if template_type == "why_it_matters":
        if summary_fallback and article_type == "default":
            return f"押さえておきたいポイントを記事にまとめました。{title}{suffix}"
        return f"押さえておきたいポイント。{hook_source}{suffix}"
    if template_type == "fan_reaction_hook":
        if summary_fallback and article_type == "default":
            return f"巨人ニュースを更新しました。記事でポイントを整理しています。{suffix}".strip()
        return f"{_manual_x_fan_reaction_lead(article_type)} {hook_source}{suffix}"
    if template_type == "lineup_focus":
        return f"試合前に確認したい起用ポイント。{title}{suffix}"
    if template_type == "lineup_order_note":
        return f"打順と起用の意図が気になるスタメン。{title}{suffix}"
    if template_type == "postgame_turning_point":
        return f"試合の分岐点を整理。{hook_source}{suffix}"
    if template_type == "postgame_recheck":
        return f"試合後にもう一度見たい場面。{title}{suffix}"
    if template_type == "farm_watch":
        return f"二軍の動きも追っておきたい。{title}{suffix}"
    if template_type == "notice_note":
        return f"公示・選手動向を整理。{title}{suffix}"
    if template_type == "notice_careful":
        return f"事実関係を確認しながら見たい動き。{hook_source}{suffix}"
    if template_type == "event_detail":
        event_label = f"{event_subject}の注目イベント{event_title}" if event_title else event_name or title
        detail = f"開催日程と{event_actor}のコメントを整理しました。" if event_actor else "開催日程と注目ポイントを整理しました。"
        return f"{event_label}。{detail}{suffix}"
    if template_type == "event_inside_voice":
        lead = f"{event_dates}に行われる" if event_dates else "開催前に確認しておきたい"
        subject = event_name or title or "巨人イベント"
        return f"{lead}{subject}。試合前に押さえておきたいポイントです。{suffix}".strip()
    if template_type == "program_memo":
        return f"見逃し注意の巨人関連情報。{title}{suffix}"
    if template_type == "inside_voice":
        return f"{_manual_x_inside_voice(article_type)}{title}"
    return f"{title}{suffix}"


def _trim_manual_x_post_text(value: str) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    if len(compact) <= MAX_MANUAL_X_POST_LENGTH:
        return compact
    return compact[: MAX_MANUAL_X_POST_LENGTH - 1].rstrip() + "…"


def _manual_x_candidate_suppression_reason(
    request: PublishNoticeRequest,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> str | None:
    yellow_entry = _latest_yellow_log_entry_for_post(request.post_id, yellow_log_path=yellow_log_path)
    if yellow_entry is None:
        return None
    block_reason = str(yellow_entry.get("manual_x_post_block_reason") or "").strip()
    if block_reason:
        return block_reason
    applied_flags = {str(flag) for flag in (yellow_entry.get("applied_flags") or []) if str(flag)}
    if "roster_movement_yellow" in applied_flags:
        return "roster_movement_yellow"
    return None


def _manual_x_context(request: PublishNoticeRequest) -> ManualXContext:
    title = _collapse_title(request.title) or "巨人ニュース"
    url = str(request.canonical_url or "").strip()
    raw_summary = _WHITESPACE_RE.sub(" ", str(request.summary or "").strip())
    cleaned_summary = _clean_summary_for_x_candidate(request.summary, title=title)
    article_type = _manual_x_article_type(
        request.subtype,
        title=title,
        summary=cleaned_summary,
        raw_summary=raw_summary,
    )
    summary_fallback = _manual_x_summary_falls_back_to_title(request.summary, cleaned_summary, title)
    hook_source = cleaned_summary if cleaned_summary != "(なし)" and not summary_fallback else title
    event_subject = _manual_x_event_subject(title, cleaned_summary)
    event_title = _manual_x_event_title(title, cleaned_summary)
    return ManualXContext(
        article_type=article_type,
        title=title,
        url=url,
        cleaned_summary=cleaned_summary,
        hook_source=hook_source,
        summary_fallback=summary_fallback,
        event_subject=event_subject,
        event_title=event_title,
        event_name=_manual_x_event_name(event_subject, event_title),
        event_dates=_manual_x_event_dates(title, cleaned_summary),
        event_actor=_manual_x_event_actor(title, cleaned_summary),
    )


def build_manual_x_post_candidates(
    request: PublishNoticeRequest,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> list[tuple[str, str]]:
    """Return deterministic manual-copy X post candidates for a publish notice."""

    if _manual_x_candidate_suppression_reason(request, yellow_log_path=yellow_log_path):
        return []
    context = _manual_x_context(request)
    template_sequence = _manual_x_template_sequence(
        context.article_type,
        sensitive=_manual_x_has_sensitive_word(context.title, context.cleaned_summary),
    )

    candidates: list[tuple[str, str]] = []
    seen_texts: set[str] = set()
    url_candidate_count = 0
    for template_type in template_sequence:
        if len(candidates) >= 3:
            break
        wants_url = template_type in _MANUAL_X_URL_TEMPLATES
        include_url = wants_url and url_candidate_count < 3
        if include_url:
            url_candidate_count += 1
        text = _render_manual_x_template(
            template_type,
            article_type=context.article_type,
            title=context.title,
            hook_source=context.hook_source,
            summary_fallback=context.summary_fallback,
            event_subject=context.event_subject,
            event_title=context.event_title,
            event_name=context.event_name,
            event_dates=context.event_dates,
            event_actor=context.event_actor,
            url=context.url,
            include_url=include_url,
        )
        trimmed = _trim_manual_x_post_text(text)
        if not trimmed or trimmed in seen_texts:
            continue
        seen_texts.add(trimmed)
        candidates.append((f"x_post_{len(candidates) + 1}_{template_type}", trimmed))
    return candidates


def _subject_body(value: str) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(value or "").strip()) or "無題"
    if len(compact) <= _SUBJECT_BODY_LIMIT:
        return compact
    return compact[: _SUBJECT_BODY_LIMIT - 1] + "…"


def _looks_dirty_manual_x_candidate(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return True
    if len(normalized) > MAX_MANUAL_X_POST_LENGTH:
        return True
    return any(marker in normalized for marker in _MANUAL_X_DIRTY_MARKERS)


def _mail_metadata_block(metadata: dict[str, Any]) -> list[str]:
    lines = ["---"]
    for key in (
        "mail_type",
        "mail_class",
        "action",
        "priority",
        "post_id",
        "subtype",
        "x_post_ready",
        "reason",
    ):
        if key not in metadata:
            continue
        value = metadata.get(key)
        if value is None or value == "":
            continue
        lines.append(f"{key}: {value}")
    lines.append("---")
    return lines


def _mail_class_config(mail_class: str) -> dict[str, str]:
    return dict(_MAIL_CLASS_CONFIGS.get(str(mail_class or "").strip(), _MAIL_CLASS_CONFIGS["publish"]))


def _per_post_mail_state(
    request: PublishNoticeRequest,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> dict[str, Any]:
    raw_summary = _WHITESPACE_RE.sub(" ", str(request.summary or "").strip())
    context = _manual_x_context(request)
    suppression_reason = _manual_x_candidate_suppression_reason(request, yellow_log_path=yellow_log_path)
    manual_x_candidates = build_manual_x_post_candidates(request, yellow_log_path=yellow_log_path)
    safe_x_candidate = (
        bool(manual_x_candidates)
        and context.cleaned_summary != "(なし)"
        and context.article_type in _SAFE_X_CANDIDATE_ARTICLE_TYPES
        and not suppression_reason
        and not _manual_x_has_sensitive_word(context.title, context.cleaned_summary)
        and not (raw_summary and context.summary_fallback)
        and not any(_looks_dirty_manual_x_candidate(text) for _label, text in manual_x_candidates)
    )
    combined_text = " ".join(
        item for item in (context.title, context.cleaned_summary, raw_summary) if item and item != "(なし)"
    )
    if any(keyword in combined_text for keyword in _URGENT_KEYWORDS):
        mail_class = "urgent"
        reason = "urgent_keyword_detected"
    elif safe_x_candidate:
        mail_class = "x_candidate"
        reason = "manual_x_candidates_clean"
    elif suppression_reason == "roster_movement_yellow":
        mail_class = "review"
        reason = "roster_movement_yellow_x_blocked"
    elif context.article_type in _CAUTIOUS_REVIEW_ARTICLE_TYPES:
        mail_class = "review"
        reason = "cautious_subtype_review"
    elif _manual_x_has_sensitive_word(context.title, context.cleaned_summary):
        mail_class = "review"
        reason = "sensitive_gate_review"
    elif raw_summary and context.summary_fallback:
        mail_class = "review"
        reason = "summary_dirty_review"
    elif any(_looks_dirty_manual_x_candidate(text) for _label, text in manual_x_candidates):
        mail_class = "review"
        reason = "candidate_copy_review"
    else:
        mail_class = "publish"
        reason = "publish_notice_default"

    mail_config = _mail_class_config(mail_class)
    return {
        "mail_type": "per_post",
        "mail_class": mail_class,
        "action": mail_config["action"],
        "priority": mail_config["priority"],
        "post_id": request.post_id,
        "subtype": str(request.subtype or "").strip() or "unknown",
        "x_post_ready": _normalize_bool(mail_class == "x_candidate"),
        "reason": reason,
        "manual_x_candidates": manual_x_candidates,
        "suppression_reason": suppression_reason,
    }


def _classify_mail(
    request: PublishNoticeRequest | BurstSummaryRequest | AlertMailRequest | EmergencyMailRequest,
    *,
    send_result: PublishNoticeEmailResult | None = None,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> dict[str, Any]:
    del send_result
    if isinstance(request, PublishNoticeRequest):
        return _per_post_mail_state(request, yellow_log_path=yellow_log_path)
    if isinstance(request, BurstSummaryRequest):
        mail_config = _mail_class_config("summary")
        return {
            "mail_type": "batch_summary",
            "mail_class": "summary",
            "action": mail_config["action"],
            "priority": mail_config["priority"],
            "reason": "batch_summary_ready",
        }
    if isinstance(request, AlertMailRequest):
        mail_config = _mail_class_config("warning")
        return {
            "mail_type": "alert",
            "mail_class": "warning",
            "action": mail_config["action"],
            "priority": mail_config["priority"],
            "post_id": request.post_id,
            "reason": str(request.reason or request.alert_type).strip() or "system_warning",
        }
    mail_config = _mail_class_config("urgent")
    return {
        "mail_type": "alert",
        "mail_class": "urgent",
        "action": mail_config["action"],
        "priority": mail_config["priority"],
        "post_id": request.post_id,
        "reason": str(request.reason or "urgent_check").strip() or "urgent_check",
    }


def _load_queue_entries(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    target = _path(path)
    if not target.exists():
        return []
    entries: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                entries.append(payload)
    return entries


def _is_recent_per_post_duplicate(
    post_id: int | str,
    *,
    history_path: str | Path | None,
    now: datetime | None = None,
    duplicate_window: timedelta = DEFAULT_DUPLICATE_WINDOW,
) -> bool:
    if history_path is None:
        return False
    current_now = _coerce_now(now)
    target_post_id = str(post_id)
    for entry in reversed(_load_queue_entries(history_path)):
        notice_kind = str(entry.get("notice_kind") or "per_post").strip() or "per_post"
        if notice_kind != "per_post":
            continue
        if str(entry.get("status") or "").strip() != "sent":
            continue
        if str(entry.get("post_id")) != target_post_id:
            continue
        recorded_at = _parse_datetime_to_jst(entry.get("sent_at") or entry.get("recorded_at"))
        if recorded_at is None:
            continue
        delta = current_now - recorded_at
        if timedelta(0) <= delta <= duplicate_window:
            return True
    return False


def build_subject(
    title: str,
    publish_dt_jst: str | None = None,
    override: str | None = None,
    classification: dict[str, Any] | None = None,
) -> str:
    del publish_dt_jst
    if override is not None:
        return str(override)
    mail_class = str((classification or {}).get("mail_class") or "publish").strip() or "publish"
    prefix = _mail_class_config(mail_class)["prefix"]
    return f"{prefix}{_subject_body(title)}{_SUBJECT_BRAND_SUFFIX}"


def build_summary_subject(request: BurstSummaryRequest) -> str:
    prefix = _mail_class_config("summary")["prefix"]
    return f"{prefix}直近{len(request.entries)}件{_SUBJECT_BRAND_SUFFIX}"


def build_alert_subject(request: AlertMailRequest) -> str:
    prefix = _mail_class_config("warning")["prefix"]
    post_label = request.post_id if request.post_id is not None else "unknown"
    return f"{prefix}post_id={post_label}{_SUBJECT_BRAND_SUFFIX}"


def build_emergency_subject(request: EmergencyMailRequest) -> str:
    del request
    prefix = _mail_class_config("urgent")["prefix"]
    return f"{prefix}X/SNS 確認{_SUBJECT_BRAND_SUFFIX}"


def resolve_recipients(override: list[str] | None) -> list[str]:
    if override is not None:
        return _normalized_recipients(override)

    publish_notice_recipients = _normalized_recipients([os.environ.get("PUBLISH_NOTICE_EMAIL_TO", "")])
    if publish_notice_recipients:
        return publish_notice_recipients

    return _normalized_recipients([os.environ.get("MAIL_BRIDGE_TO", "")])


def build_body_text(
    request: PublishNoticeRequest,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
    classification: dict[str, Any] | None = None,
) -> str:
    mail_state = classification or _classify_mail(request, yellow_log_path=yellow_log_path)
    suppression_reason = mail_state.get("suppression_reason")
    manual_x_candidates = list(mail_state.get("manual_x_candidates") or [])
    lines = _mail_metadata_block(
        {
            "mail_type": mail_state.get("mail_type"),
            "mail_class": mail_state.get("mail_class"),
            "action": mail_state.get("action"),
            "priority": mail_state.get("priority"),
            "post_id": request.post_id,
            "subtype": str(request.subtype or "").strip() or "unknown",
            "x_post_ready": mail_state.get("x_post_ready"),
            "reason": mail_state.get("reason"),
        }
    )
    lines.extend(
        [
        f"title: {str(request.title or '').strip()}",
        f"url: {str(request.canonical_url or '').strip()}",
        f"subtype: {str(request.subtype or '').strip() or 'unknown'}",
        f"publish time: {_format_publish_time_jst(request.publish_time_iso)}",
        f"summary: {_normalize_summary(request.summary)}",
        ]
    )
    if suppression_reason == "roster_movement_yellow":
        lines.append("warning: [Warning] roster movement 系記事、X 自動投稿対象外")
    lines.extend(
        [
            "manual_x_post_candidates:",
            f"article_url: {str(request.canonical_url or '').strip()}",
        ]
    )
    if suppression_reason:
        lines.append(f"suppressed: {suppression_reason}")
    else:
        lines.extend(f"{label}: {text}" for label, text in manual_x_candidates)
    return "\n".join(lines)


def build_summary_body_text(
    request: BurstSummaryRequest,
    *,
    classification: dict[str, Any] | None = None,
) -> str:
    mail_state = classification or _classify_mail(request)
    daily_cap_remaining = max(0, int(request.daily_cap) - int(request.cumulative_published_count))
    lines = _mail_metadata_block(
        {
            "mail_type": mail_state.get("mail_type"),
            "mail_class": mail_state.get("mail_class"),
            "action": mail_state.get("action"),
            "priority": mail_state.get("priority"),
            "reason": mail_state.get("reason"),
        }
    )
    lines.extend(
        [
        f"summary_posts: {len(request.entries)}",
        f"cumulative_published_count: {int(request.cumulative_published_count)}",
        f"daily_cap_remaining: {daily_cap_remaining}",
        f"hard_stop_count: {int(request.hard_stop_count)}",
        f"hold_count: {int(request.hold_count)}",
        "recent_posts:",
        ]
    )
    for entry in request.entries:
        lines.append(
            "  - "
            f"post_id={entry.post_id} | "
            f"title={_collapse_title(entry.title)} | "
            f"category={str(entry.category or '').strip() or 'unknown'} | "
            f"publishable={_normalize_bool(entry.publishable)} | "
            f"cleanup_required={_normalize_bool(entry.cleanup_required)} | "
            f"cleanup_success={_normalize_bool(entry.cleanup_success)}"
        )
    return "\n".join(lines)


def build_alert_body_text(
    request: AlertMailRequest,
    *,
    classification: dict[str, Any] | None = None,
) -> str:
    mail_state = classification or _classify_mail(request)
    lines = _mail_metadata_block(
        {
            "mail_type": mail_state.get("mail_type"),
            "mail_class": mail_state.get("mail_class"),
            "action": mail_state.get("action"),
            "priority": mail_state.get("priority"),
            "post_id": request.post_id,
            "reason": mail_state.get("reason"),
        }
    )
    lines.extend(
        [
        f"alert_type: {request.alert_type}",
        f"post_id: {'' if request.post_id is None else request.post_id}",
        f"title: {str(request.title or '').strip()}",
        f"category: {str(request.category or '').strip() or 'unknown'}",
        f"reason: {str(request.reason or '').strip() or '(none)'}",
        f"detail: {str(request.detail or '').strip() or '(none)'}",
        f"publishable: {_normalize_bool(request.publishable)}",
        f"cleanup_required: {_normalize_bool(request.cleanup_required)}",
        f"cleanup_success: {_normalize_bool(request.cleanup_success)}",
        f"hold_reason: {str(request.hold_reason or '').strip() or '(none)'}",
        ]
    )
    return "\n".join(lines)


def build_burst_summary_requests(
    entries: Sequence[BurstSummaryEntry],
    *,
    summary_every: int = DEFAULT_SUMMARY_EVERY,
    cumulative_before: int = 0,
    daily_cap: int = DEFAULT_DAILY_CAP,
) -> list[BurstSummaryRequest]:
    if int(summary_every) <= 0:
        raise ValueError("summary_every must be > 0")
    requests: list[BurstSummaryRequest] = []
    summary_size = int(summary_every)
    for start in range(0, len(entries), summary_size):
        chunk = list(entries[start : start + summary_size])
        if len(chunk) < summary_size:
            break
        requests.append(
            BurstSummaryRequest(
                entries=chunk,
                cumulative_published_count=int(cumulative_before) + start + len(chunk),
                daily_cap=int(daily_cap),
            )
        )
    return requests


def _suppressed(
    reason: str,
    *,
    subject: str,
    recipients: list[str] | None = None,
    bridge_result: object | None = None,
) -> PublishNoticeEmailResult:
    return PublishNoticeEmailResult(
        status="suppressed",
        reason=reason,
        subject=subject,
        recipients=list(recipients or []),
        bridge_result=bridge_result,
    )


def _error_result(
    *,
    subject: str,
    recipients: list[str] | None = None,
    reason: str | None = None,
    bridge_result: object | None = None,
) -> PublishNoticeEmailResult:
    normalized_reason = str(reason or "").strip() or "UNKNOWN_ERROR"
    return PublishNoticeEmailResult(
        status="error",
        reason=normalized_reason,
        subject=str(subject or "").strip(),
        recipients=list(recipients or []),
        bridge_result=bridge_result,
    )


def _bridge_result_to_email_result(
    *,
    subject: str,
    recipients: list[str],
    bridge_result: object,
) -> PublishNoticeEmailResult:
    bridge_status = str(getattr(bridge_result, "status", "") or "")
    bridge_reason = getattr(bridge_result, "reason", None)
    if bridge_status == "suppressed":
        return _suppressed(
            str(bridge_reason or "UNKNOWN_BRIDGE_SUPPRESSION"),
            subject=subject,
            recipients=recipients,
            bridge_result=bridge_result,
        )
    if bridge_status == "dry_run":
        return PublishNoticeEmailResult(
            status="dry_run",
            reason=None if bridge_reason is None else str(bridge_reason),
            subject=subject,
            recipients=recipients,
            bridge_result=bridge_result,
        )
    return PublishNoticeEmailResult(
        status="sent",
        reason=None if bridge_reason is None else str(bridge_reason),
        subject=subject,
        recipients=recipients,
        bridge_result=bridge_result,
    )


def _deliver_mail(
    *,
    subject: str,
    body_text: str,
    metadata: dict[str, Any],
    dry_run: bool,
    send_enabled: bool | None,
    bridge_send: BridgeSend,
    override_recipient: list[str] | None = None,
    duplicate_history_path: str | Path | None = None,
    dedupe_post_id: int | str | None = None,
    now: datetime | None = None,
    duplicate_window: timedelta = DEFAULT_DUPLICATE_WINDOW,
) -> PublishNoticeEmailResult:
    normalized_subject = str(subject or "").strip()
    recipients = resolve_recipients(override_recipient)
    if not normalized_subject:
        return _suppressed("EMPTY_SUBJECT", subject=normalized_subject, recipients=recipients)
    if not body_text.strip():
        return _suppressed("EMPTY_BODY", subject=normalized_subject, recipients=recipients)
    if not recipients:
        return _suppressed("NO_RECIPIENT", subject=normalized_subject, recipients=recipients)
    if dry_run:
        return PublishNoticeEmailResult(
            status="dry_run",
            reason=None,
            subject=normalized_subject,
            recipients=recipients,
            bridge_result=None,
        )

    active_send_enabled = (
        send_enabled
        if send_enabled is not None
        else str(os.environ.get("PUBLISH_NOTICE_EMAIL_ENABLED", "")).strip() == "1"
    )
    if not active_send_enabled:
        return _suppressed("GATE_OFF", subject=normalized_subject, recipients=recipients)
    if dedupe_post_id is not None and _is_recent_per_post_duplicate(
        dedupe_post_id,
        history_path=duplicate_history_path,
        now=now,
        duplicate_window=duplicate_window,
    ):
        return _suppressed("DUPLICATE_WITHIN_30MIN", subject=normalized_subject, recipients=recipients)

    mail_request = _BridgeMailRequest(
        to=recipients,
        subject=normalized_subject,
        text_body=body_text,
        metadata=dict(metadata),
    )
    try:
        bridge_result = bridge_send(mail_request, dry_run=False)
    except Exception as exc:
        return _error_result(
            subject=normalized_subject,
            recipients=recipients,
            reason=type(exc).__name__,
            bridge_result=exc,
        )
    return _bridge_result_to_email_result(
        subject=normalized_subject,
        recipients=recipients,
        bridge_result=bridge_result,
    )


def send(
    request: PublishNoticeRequest,
    *,
    dry_run: bool = True,
    send_enabled: bool | None = None,
    bridge_send: BridgeSend = bridge_send_default,
    override_recipient: list[str] | None = None,
    override_subject: str | None = None,
    duplicate_history_path: str | Path | None = None,
    now: datetime | None = None,
    duplicate_window: timedelta = DEFAULT_DUPLICATE_WINDOW,
) -> PublishNoticeEmailResult:
    normalized_title = str(request.title or "").strip()
    subject = build_subject(normalized_title, override=override_subject)
    if not normalized_title:
        return _suppressed("EMPTY_TITLE", subject=subject)

    normalized_url = str(request.canonical_url or "").strip()
    if not normalized_url:
        return _suppressed("MISSING_URL", subject=subject)

    normalized_request = PublishNoticeRequest(
        post_id=request.post_id,
        title=normalized_title,
        canonical_url=normalized_url,
        subtype=str(request.subtype or "").strip() or "unknown",
        publish_time_iso=str(request.publish_time_iso or "").strip(),
        summary=request.summary,
    )
    mail_state = _classify_mail(normalized_request)
    return _deliver_mail(
        subject=build_subject(normalized_title, override=override_subject, classification=mail_state),
        body_text=build_body_text(normalized_request, classification=mail_state),
        metadata={
            "post_id": normalized_request.post_id,
            "subtype": normalized_request.subtype,
            "publish_time_iso": normalized_request.publish_time_iso,
            "notice_kind": "per_post",
        },
        dry_run=dry_run,
        send_enabled=send_enabled,
        bridge_send=bridge_send,
        override_recipient=override_recipient,
        duplicate_history_path=duplicate_history_path,
        dedupe_post_id=normalized_request.post_id,
        now=now,
        duplicate_window=duplicate_window,
    )


def send_summary(
    request: BurstSummaryRequest,
    *,
    dry_run: bool = True,
    send_enabled: bool | None = None,
    bridge_send: BridgeSend = bridge_send_default,
    override_recipient: list[str] | None = None,
) -> PublishNoticeEmailResult:
    mail_state = _classify_mail(request)
    return _deliver_mail(
        subject=build_summary_subject(request),
        body_text=build_summary_body_text(request, classification=mail_state),
        metadata={
            "notice_kind": "summary",
            "summary_posts": len(request.entries),
            "cumulative_published_count": int(request.cumulative_published_count),
            "daily_cap": int(request.daily_cap),
        },
        dry_run=dry_run,
        send_enabled=send_enabled,
        bridge_send=bridge_send,
        override_recipient=override_recipient,
    )


def send_alert(
    request: AlertMailRequest,
    *,
    dry_run: bool = True,
    send_enabled: bool | None = None,
    bridge_send: BridgeSend = bridge_send_default,
    override_recipient: list[str] | None = None,
) -> PublishNoticeEmailResult:
    mail_state = _classify_mail(request)
    return _deliver_mail(
        subject=build_alert_subject(request),
        body_text=build_alert_body_text(request, classification=mail_state),
        metadata={
            "notice_kind": "alert",
            "alert_type": request.alert_type,
            "post_id": request.post_id,
            "hold_reason": request.hold_reason,
        },
        dry_run=dry_run,
        send_enabled=send_enabled,
        bridge_send=bridge_send,
        override_recipient=override_recipient,
    )


def emit_emergency_hook(
    request: EmergencyMailRequest,
    *,
    hook: EmergencyHook | None = None,
) -> object | None:
    if hook is None:
        return None
    return hook(request)


def build_send_result_entry(
    *,
    notice_kind: str,
    post_id: int | str,
    result: PublishNoticeEmailResult,
    publish_time_iso: str | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    sent_at_iso = _coerce_now(recorded_at).isoformat()
    payload = {
        "status": str(result.status).strip(),
        "reason": None if result.reason is None else str(result.reason),
        "subject": str(result.subject or "").strip(),
        "recipients": list(result.recipients or []),
        "post_id": post_id,
        "recorded_at": sent_at_iso,
        "sent_at": sent_at_iso,
        "notice_kind": str(notice_kind or "").strip() or "per_post",
    }
    if publish_time_iso is not None:
        payload["publish_time_iso"] = str(publish_time_iso or "")
    return payload


def append_send_result(
    queue_path: str | Path,
    *,
    notice_kind: str,
    post_id: int | str,
    result: PublishNoticeEmailResult,
    publish_time_iso: str | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    payload = build_send_result_entry(
        notice_kind=notice_kind,
        post_id=post_id,
        result=result,
        publish_time_iso=publish_time_iso,
        recorded_at=recorded_at,
    )
    path = _path(queue_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def summarize_execution_results(
    results: Sequence[PublishNoticeEmailResult],
    *,
    emitted: int,
) -> PublishNoticeExecutionSummary:
    status_counter = Counter(str(result.status).strip() for result in results)
    reason_counter = Counter(
        str(result.reason).strip()
        for result in results
        if str(result.reason or "").strip()
    )
    return PublishNoticeExecutionSummary(
        emitted=int(emitted),
        sent=int(status_counter.get("sent", 0)),
        suppressed=int(status_counter.get("suppressed", 0)),
        errors=int(status_counter.get("error", 0)),
        dry_run=int(status_counter.get("dry_run", 0)),
        reasons=dict(sorted(reason_counter.items())),
    )


def build_execution_summary_log(summary: PublishNoticeExecutionSummary) -> str:
    return (
        f"[summary] sent={summary.sent} suppressed={summary.suppressed} "
        f"errors={summary.errors} reasons={json.dumps(summary.reasons, ensure_ascii=False, sort_keys=True)}"
    )


def build_zero_sent_alert_log(summary: PublishNoticeExecutionSummary) -> str | None:
    if not summary.should_alert:
        return None
    return (
        f"[ALERT] publish-notice emitted={summary.emitted} but sent=0 "
        f"(suppressed={summary.suppressed} errors={summary.errors}, "
        f"reasons={json.dumps(summary.reasons, ensure_ascii=False, sort_keys=True)})"
    )


__all__ = [
    "AlertMailRequest",
    "BurstSummaryEntry",
    "BurstSummaryRequest",
    "DEFAULT_DAILY_CAP",
    "DEFAULT_DUPLICATE_WINDOW",
    "DEFAULT_SUMMARY_EVERY",
    "EmergencyMailRequest",
    "JST",
    "PublishNoticeEmailResult",
    "PublishNoticeRequest",
    "build_alert_body_text",
    "build_alert_subject",
    "build_body_text",
    "build_burst_summary_requests",
    "build_execution_summary_log",
    "build_emergency_subject",
    "build_manual_x_post_candidates",
    "build_send_result_entry",
    "build_subject",
    "build_summary_body_text",
    "build_summary_subject",
    "build_zero_sent_alert_log",
    "emit_emergency_hook",
    "append_send_result",
    "PublishNoticeExecutionSummary",
    "resolve_recipients",
    "send",
    "send_alert",
    "send_summary",
    "summarize_execution_results",
]
