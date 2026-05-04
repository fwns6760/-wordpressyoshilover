"""Publish notice mail adapter built on top of ticket 072 bridge."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from src.baseball_numeric_fact_consistency import check_consistency
from src.mail_delivery_bridge import send as bridge_send_default


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUMMARY_EVERY = 10
DEFAULT_DAILY_CAP = 100
DEFAULT_DUPLICATE_WINDOW = timedelta(minutes=30)
DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH = ROOT / "logs" / "guarded_publish_yellow_log.jsonl"
DEFAULT_GUARDED_PUBLISH_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
FORCED_SUMMARY_THRESHOLD = 10
_SUMMARY_ONLY_SUPPRESSION_REASONS = frozenset({"BACKLOG_SUMMARY_ONLY", "BURST_SUMMARY_ONLY"})
_PUBLISH_ONLY_MAIL_FILTER_ENV_FLAG = "ENABLE_PUBLISH_ONLY_MAIL_FILTER"
_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS_ENV_FLAG = (
    "ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS"
)
_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS_ENV_FLAG = "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS"
_REPLAY_WINDOW_DEDUP_ENV_FLAG = "ENABLE_REPLAY_WINDOW_DEDUP"
_REPLAY_WINDOW_MINUTES_ENV = "PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES"
_REPLAY_WINDOW_MINUTES_DEFAULT = 10
_PUBLISH_NOTICE_HISTORY_STRICT_STAMP_ENV_FLAG = "ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP"
_DISABLE_BURST_SUMMARY_MAIL_ENV_FLAG = "DISABLE_BURST_SUMMARY_MAIL"
_PUBLISH_ONLY_MAIL_PREFIX = "【公開済】"
_DIRECT_PUBLISH_NOTICE_ORIGIN = "direct_publish_scan"
_PUBLISH_NOTICE_24H_BUDGET_SUMMARY_ONLY_RECORD_TYPE = "24h_budget_summary_only"
_PUBLISH_ONLY_MAIL_FILTER_SUPPRESSION_REASON = "PUBLISH_ONLY_FILTER"
_REPLAY_WINDOW_SUPPRESSION_REASON = "DUPLICATE_WITHIN_REPLAY_WINDOW"
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
_MANUAL_X_STANDARD_HASHTAGS = ("#巨人", "#ジャイアンツ")
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
_MANUAL_X_TRAILING_URL_RE = re.compile(r"^(?P<body>.*?)(?P<url>https?://\S+)$")
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
_MANUAL_X_LONG_TERM_INJURY_RE = re.compile(r"全治\s*(\d+)\s*(?:ヶ月|か月|ヵ月|カ月)")
_FARM_MARKER_RE = re.compile(r"(二軍|三軍|ファーム|イースタン|ウエスタン|farm|Farm|FARM)")
_FARM_RESULT_FACT_RE = re.compile(
    r"(?:\d+\s*[-ー－]\s*\d+|\d+回\d+失点|\d+安打\d+打点|\d+打数\d+安打|\d+奪三振|\d+号)"
)
_FARM_LINEUP_MARKER_RE = re.compile(r"(?:スタメン|先発|[1-9]番)")
_FIRST_TEAM_POSTGAME_SCORE_RE = re.compile(r"\d+\s*(?:-|対)\s*\d+")
_FIRST_TEAM_POSTGAME_KEY_EVENT_RE = re.compile(r"(?:決勝打|本塁打|先制|逆転)")
_FIRST_TEAM_LINEUP_MARKER_RE = re.compile(r"(?:1番|2番|先発|スタメン)")
_PROGRAM_NOTICE_MARKER_RE = re.compile(r"(放送|配信|GIANTS\s*TV|オンエア|テレビ|ラジオ|番組|出演)")
_ROSTER_NOTICE_MARKER_RE = re.compile(r"(出場選手登録|登録抹消|一軍登録|二軍降格|戦力外|引退|公示)")
_INJURY_RECOVERY_MARKER_RE = re.compile(
    r"(怪我|負傷|離脱|戦線復帰|復帰|右肩|左肩|右肘|左肘|手術|リハビリ|抹消|登録抹消)"
)
_INJURY_DETAIL_MARKER_RE = re.compile(r"(全治|診断|復帰時期|手術成功|リハビリ完了)")
_DEFAULT_REVIEW_SUBTYPES = frozenset({"default", "general", "unknown", ""})
_PROGRAM_NOTICE_TIME_RE = re.compile(
    r"(?:"
    r"(?:[01]?\d|2[0-3])[:：]\d{2}|"
    r"(?:午前|午後)\s*\d{1,2}時(?:\d{1,2}分)?|"
    r"\d{1,2}時(?:\d{1,2}分)?"
    r")"
)
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
_MANUAL_X_SENSITIVE_SUBTYPE_KEYWORDS = (
    "injury",
    "injured",
    "death",
    "obituary",
    "grave_incident",
    "重大事故",
)
_MANUAL_X_SENSITIVE_CONTENT_KEYWORDS = (
    "死去",
    "逝去",
    "危篤",
    "重症",
    "重大事故",
    "抹消",
    "登録抹消",
)
_MANUAL_X_TRUNCATION_PUNCTUATION = "、。!！?？"
_FIRST_TEAM_POSTGAME_REVIEW_REASON = "_".join(("first", "team", "postgame", "review"))
_FIRST_TEAM_LINEUP_REVIEW_REASON = "_".join(("first", "team", "lineup", "review"))
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
_REVIEW_X_BLOCK_REASONS = frozenset(
    {
        "roster_movement_yellow_x_blocked",
        "sensitive_content_x_blocked",
    }
)
_REVIEW_REASON_LABELS: dict[str | None, tuple[str, str]] = {
    "summary_dirty_review": (
        "要確認",
        "要約に元記事断片や重複文が混ざっています(本文確認推奨)",
    ),
    "farm_result_review": (
        "要確認",
        "二軍結果の記事で数字または時点の確認が必要です(本文確認推奨)",
    ),
    "farm_lineup_review": (
        "要確認",
        "二軍スタメンの記事で時点または内容確認が必要です(本文確認推奨)",
    ),
    _FIRST_TEAM_POSTGAME_REVIEW_REASON: (
        "要確認",
        "一軍試合結果の記事で score または決定的プレーの確認が必要です(本文確認推奨)",
    ),
    _FIRST_TEAM_LINEUP_REVIEW_REASON: (
        "要確認",
        "一軍スタメンの記事で時点または内容確認が必要です(本文確認推奨)",
    ),
    "program_notice_review": (
        "要確認",
        "放送・配信時刻または番組情報の確認が必要です(本文確認推奨)",
    ),
    "roster_notice_review": (
        "要確認",
        "出場選手登録・公示系の記事です(本文確認推奨)",
    ),
    "injury_recovery_notice_review": (
        "要確認",
        "怪我・復帰記事で診断または復帰時期の確認が必要です(本文確認推奨)",
    ),
    "default_review": (
        "要確認",
        "subtype 未確定の記事です(本文確認推奨)",
    ),
    "cautious_subtype_review": (
        "要確認",
        "公示・注意系の記事です(本文確認推奨)",
    ),
    "roster_movement_yellow_x_blocked": (
        "見送り推奨",
        "登録/抹消/復帰系のため X 投稿候補なし",
    ),
    "sensitive_content_x_blocked": (
        "見送り",
        "センシティブ要素のため X 投稿候補なし",
    ),
    None: (
        "要確認",
        "本文を確認してください",
    ),
}
_DIRTY_REVIEW_SUMMARY_LIMIT = 100
_SAFE_X_CANDIDATE_ARTICLE_TYPES = frozenset(
    {"default", "lineup", "postgame", "farm", "farm_result", "farm_lineup", "program"}
)
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
    is_backlog: bool | None = None
    notice_kind: Literal["publish", "review_hold", "post_gen_validate"] = "publish"
    notice_origin: str | None = None
    subject_override: str | None = None
    source_title: str | None = None
    generated_title: str | None = None
    skip_reason: str | None = None
    skip_reason_label: str | None = None
    source_url_hash: str | None = None
    category: str | None = None
    record_type: str | None = None
    skip_layer: str | None = None
    fail_axes: tuple[str, ...] = ()


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
    sensitive_x_block_reason: str | None = None


@dataclass(frozen=True)
class BurstSummaryEntry:
    post_id: int | str
    title: str
    category: str
    publishable: bool
    cleanup_required: bool
    cleanup_success: bool | None
    is_backlog: bool | None = None


@dataclass(frozen=True)
class BurstSummaryRequest:
    entries: list[BurstSummaryEntry]
    cumulative_published_count: int
    daily_cap: int = DEFAULT_DAILY_CAP
    hard_stop_count: int = 0
    hold_count: int = 0
    summary_mode: Literal["default", "backlog_only", "burst_forced"] = "default"


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
    summary_only_suppressed: int
    reasons: dict[str, int]

    @property
    def should_alert(self) -> bool:
        return (
            self.emitted > 0
            and self.sent == 0
            and self.dry_run == 0
            and self.summary_only_suppressed < self.emitted
        )


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


def _load_jsonl_entries(path: str | Path | None) -> list[dict[str, Any]]:
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


def _load_history_entries(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    target = _path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _write_history_entries(path: str | Path, history: dict[str, str]) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{target}.tmp")
    tmp_path.write_text(
        json.dumps(dict(sorted(history.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, target)


def _prune_history_entries(
    history: dict[str, str],
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    cutoff = _coerce_now(now) - timedelta(hours=24)
    pruned: dict[str, str] = {}
    for key, value in history.items():
        recorded_at = _parse_datetime_to_jst(value)
        if recorded_at is not None and recorded_at < cutoff:
            continue
        pruned[str(key)] = str(value)
    return pruned


def _publish_notice_history_strict_stamp_enabled() -> bool:
    return str(os.environ.get(_PUBLISH_NOTICE_HISTORY_STRICT_STAMP_ENV_FLAG, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _cloud_run_publish_notice_runtime() -> bool:
    return any(
        str(os.environ.get(key, "")).strip()
        for key in ("K_SERVICE", "CLOUD_RUN_JOB", "CLOUD_RUN_EXECUTION")
    )


def _default_project_id() -> str:
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "PROJECT_ID"):
        value = str(os.environ.get(key, "")).strip()
        if value:
            return value
    return "baseballsite"


def _load_remote_publish_notice_queue_entries(history_path: str | Path | None) -> list[dict[str, Any]]:
    if history_path is None or not _cloud_run_publish_notice_runtime():
        return []
    try:
        from src.cloud_run_persistence import DEFAULT_BUCKET_NAME, DEFAULT_PREFIX, GCSStateManager
    except Exception:
        return []

    bucket_name = str(os.environ.get("GCS_STATE_BUCKET", DEFAULT_BUCKET_NAME)).strip() or DEFAULT_BUCKET_NAME
    prefix = str(os.environ.get("GCS_STATE_PREFIX", DEFAULT_PREFIX)).strip() or DEFAULT_PREFIX
    try:
        manager = GCSStateManager(
            bucket_name=bucket_name,
            prefix=prefix,
            project_id=_default_project_id(),
        )
        with tempfile.TemporaryDirectory(prefix="publish-notice-replay-window-") as tmpdir:
            remote_path = Path(tmpdir) / "queue.jsonl"
            if not manager.download("queue.jsonl", remote_path):
                return []
            return _load_jsonl_entries(remote_path)
    except Exception:
        return []


def _load_remote_publish_notice_history_entries(history_path: str | Path | None) -> dict[str, str]:
    if history_path is None or not _cloud_run_publish_notice_runtime():
        return {}
    try:
        from src.cloud_run_persistence import DEFAULT_BUCKET_NAME, DEFAULT_PREFIX, GCSStateManager
    except Exception:
        return {}

    bucket_name = str(os.environ.get("GCS_STATE_BUCKET", DEFAULT_BUCKET_NAME)).strip() or DEFAULT_BUCKET_NAME
    prefix = str(os.environ.get("GCS_STATE_PREFIX", DEFAULT_PREFIX)).strip() or DEFAULT_PREFIX
    try:
        manager = GCSStateManager(
            bucket_name=bucket_name,
            prefix=prefix,
            project_id=_default_project_id(),
        )
        with tempfile.TemporaryDirectory(prefix="publish-notice-replay-window-") as tmpdir:
            remote_path = Path(tmpdir) / "history.json"
            if not manager.download("history.json", remote_path):
                return {}
            return _load_history_entries(remote_path)
    except Exception:
        return {}


def _derive_publish_notice_history_path(history_path: str | Path | None) -> Path | None:
    if history_path is None:
        return None
    target = _path(history_path)
    if target.name == "publish_notice_queue.jsonl":
        return target.with_name("publish_notice_history.json")
    if target.name.endswith("queue.jsonl"):
        return target.with_name("history.json")
    return target.with_name("history.json")


def _verify_wp_status_publish(post_id: int | str) -> bool:
    post_key = str(post_id or "").strip()
    if not post_key.isdigit():
        return False
    try:
        from src.wp_client import WPClient

        post = WPClient().get_post(int(post_key))
    except Exception:
        return False
    return str((post or {}).get("status") or "").strip().lower() == "publish"


def _record_history_after_send(
    history_path: str | Path | None,
    *,
    request: PublishNoticeRequest | None,
    result: PublishNoticeEmailResult,
    recorded_at: datetime | None = None,
) -> bool:
    if not _publish_notice_history_strict_stamp_enabled():
        return False
    if request is None:
        return False
    if str(result.status).strip() != "sent":
        return False

    post_key = str(getattr(request, "post_id", "") or "").strip()
    if not post_key:
        return False
    if post_key.isdigit() and not _verify_wp_status_publish(post_key):
        return False

    target_path = _derive_publish_notice_history_path(history_path)
    if target_path is None:
        return False

    stamp_at = _coerce_now(recorded_at)
    history = _prune_history_entries(_load_history_entries(target_path), now=stamp_at)
    history[post_key] = stamp_at.isoformat()
    _write_history_entries(target_path, history)
    return True


def _latest_guarded_publish_history_entry(
    post_id: int | str,
    *,
    history_path: str | Path = DEFAULT_GUARDED_PUBLISH_HISTORY_PATH,
) -> dict[str, Any] | None:
    target_post_id = str(post_id)
    matched: dict[str, Any] | None = None
    for entry in _load_jsonl_entries(history_path):
        if str(entry.get("post_id")) != target_post_id:
            continue
        matched = entry
    return matched


def _resolve_is_backlog(
    post_id: int | str,
    explicit_is_backlog: bool | None,
    *,
    history_path: str | Path = DEFAULT_GUARDED_PUBLISH_HISTORY_PATH,
    allow_history_lookup: bool = True,
) -> bool:
    if explicit_is_backlog is not None:
        return bool(explicit_is_backlog)
    if not allow_history_lookup:
        return False
    matched = _latest_guarded_publish_history_entry(post_id, history_path=history_path)
    if not matched:
        return False
    return bool(matched.get("is_backlog"))


def _current_queued_batch_size(queue_path: str | Path | None) -> int:
    latest_recorded_at: datetime | None = None
    batch_key: str | None = None
    batch_post_ids: dict[str, set[str]] = {}
    for entry in _load_jsonl_entries(queue_path):
        if str(entry.get("status") or "").strip() != "queued":
            continue
        recorded_at = _parse_datetime_to_jst(entry.get("recorded_at"))
        if recorded_at is None:
            continue
        key = recorded_at.isoformat()
        batch_post_ids.setdefault(key, set()).add(str(entry.get("post_id") or ""))
        if latest_recorded_at is None or recorded_at > latest_recorded_at:
            latest_recorded_at = recorded_at
            batch_key = key
    if batch_key is None:
        return 0
    return len([post_id for post_id in batch_post_ids.get(batch_key, set()) if post_id])


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


def _is_past_publish_date(value: str, *, now: datetime | None = None) -> bool:
    current = _parse_datetime_to_jst(value)
    if current is None:
        return False
    return current.date() < _coerce_now(now).date()


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
    if normalized == "farm_result":
        return "farm_result"
    if normalized == "farm_lineup":
        return "farm_lineup"
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


def _is_first_team_article(title: str, summary: str, subtype: str) -> bool:
    normalized = str(subtype or "").strip().lower()
    if normalized not in {"postgame", "lineup"}:
        return False
    blob = f"{title or ''}\n{summary or ''}"
    if _FARM_MARKER_RE.search(blob):
        return False
    return True


def _is_program_notice(title: str, summary: str, subtype: str) -> bool:
    normalized = str(subtype or "").strip().lower()
    if normalized not in {"program", "notice"}:
        return False
    blob = f"{title or ''}\n{summary or ''}"
    return bool(_PROGRAM_NOTICE_MARKER_RE.search(blob))


def _is_roster_notice(title: str, summary: str, subtype: str) -> bool:
    normalized = str(subtype or "").strip().lower()
    if normalized != "notice":
        return False
    blob = f"{title or ''}\n{summary or ''}"
    return bool(_ROSTER_NOTICE_MARKER_RE.search(blob))


def _is_injury_recovery_notice(title: str, summary: str, subtype: str) -> bool:
    normalized = str(subtype or "").strip().lower()
    if normalized != "notice":
        return False
    blob = f"{title or ''}\n{summary or ''}"
    return bool(_INJURY_RECOVERY_MARKER_RE.search(blob))


def _is_default_review(subtype: str) -> bool:
    normalized = str(subtype or "").strip().lower()
    return normalized in _DEFAULT_REVIEW_SUBTYPES


def _manual_x_has_sensitive_word(title: str, summary: str) -> bool:
    combined = f"{title} {summary}"
    return any(word in combined for word in _MANUAL_X_SENSITIVE_WORDS)


def _manual_x_sensitive_block_reason(
    request: PublishNoticeRequest,
    *,
    article_type: str,
    title: str,
    cleaned_summary: str,
    raw_summary: str,
) -> str | None:
    subtype = str(request.subtype or "").strip()
    normalized_subtype = subtype.lower()
    combined = " ".join(
        item for item in (title, cleaned_summary, raw_summary) if item and item != "(なし)"
    )

    if any(keyword in normalized_subtype or keyword in subtype for keyword in _MANUAL_X_SENSITIVE_SUBTYPE_KEYWORDS):
        return "sensitive_content_x_blocked"
    if any(keyword in combined for keyword in _MANUAL_X_SENSITIVE_CONTENT_KEYWORDS):
        return "sensitive_content_x_blocked"
    injury_match = _MANUAL_X_LONG_TERM_INJURY_RE.search(combined)
    if injury_match:
        try:
            if int(injury_match.group(1)) >= 1:
                return "sensitive_content_x_blocked"
        except ValueError:
            pass
    if article_type == "notice" and any(keyword in combined for keyword in ("抹消", "登録抹消")):
        return "sensitive_content_x_blocked"
    return None


def _manual_x_template_sequence(article_type: str, *, sensitive: bool) -> list[str]:
    if article_type == "lineup":
        templates = ["article_intro", "lineup_focus", "inside_voice", "fan_reaction_hook"]
    elif article_type == "postgame":
        templates = ["article_intro", "postgame_turning_point", "inside_voice", "fan_reaction_hook"]
    elif article_type == "farm":
        templates = ["article_intro", "farm_watch", "inside_voice", "why_it_matters"]
    elif article_type == "farm_result":
        templates = ["article_intro", "farm_watch", "inside_voice"]
    elif article_type == "farm_lineup":
        templates = ["article_intro", "farm_watch"]
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
    if article_type not in {"lineup", "postgame", "farm", "farm_result", "program"}:
        templates = [template for template in templates if template != "inside_voice"]
    return [template for template in templates if template in _MANUAL_X_TEMPLATE_TYPES]


def _manual_x_article_intro_lead(article_type: str) -> str:
    return {
        "lineup": "巨人のスタメン情報を更新しました。",
        "postgame": "巨人の試合結果を更新しました。",
        "farm": "巨人の二軍情報を更新しました。",
        "farm_result": "巨人の二軍試合結果を更新しました。",
        "farm_lineup": "巨人の二軍スタメン情報を更新しました。",
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
        "farm_result": "二軍の動きも追っておきたい。",
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


def _split_manual_x_trailing_hashtags(text: str) -> tuple[str, list[str]]:
    parts = [part for part in str(text or "").split(" ") if part]
    hashtags: list[str] = []
    while parts and parts[-1].startswith("#"):
        hashtags.append(parts.pop())
    hashtags.reverse()
    return " ".join(parts).strip(), hashtags


def _split_manual_x_trailing_url(text: str) -> tuple[str, str]:
    match = _MANUAL_X_TRAILING_URL_RE.match(str(text or "").strip())
    if not match:
        return str(text or "").strip(), ""

    body = match.group("body").rstrip()
    raw_url = match.group("url").strip()
    trimmed_url = raw_url.rstrip("、。,.!?！？")
    trailing = raw_url[len(trimmed_url) :]
    if body and trailing:
        body = f"{body}{trailing}"
    return body.rstrip(), trimmed_url


def _normalize_manual_x_hashtags(hashtags: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in hashtags:
        normalized = _WHITESPACE_RE.sub(" ", str(tag or "").replace("\u3000", " ").strip())
        if not normalized or not normalized.startswith("#") or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)

    preferred = [tag for tag in _MANUAL_X_STANDARD_HASHTAGS if tag in seen]
    extras = [tag for tag in ordered if tag not in _MANUAL_X_STANDARD_HASHTAGS]
    return preferred + extras


def _limit_manual_x_repeated_punctuation(text: str) -> str:
    compact = str(text or "")
    compact = re.sub(r"!{2,}", "!", compact)
    compact = re.sub(r"\?{2,}", "?", compact)
    compact = re.sub(r"！{2,}", "！", compact)
    compact = re.sub(r"？{2,}", "？", compact)
    compact = re.sub(r"…{2,}", "…", compact)
    return compact


def _polish_x_post_text(text: str) -> str:
    compact = _WHITESPACE_RE.sub(" ", str(text or "").replace("\u3000", " ").strip())
    if not compact:
        return ""

    body, hashtags = _split_manual_x_trailing_hashtags(compact)
    body, url = _split_manual_x_trailing_url(body)
    body = _limit_manual_x_repeated_punctuation(body).strip()
    normalized_hashtags = _normalize_manual_x_hashtags(hashtags)

    parts = [part for part in (body, url, " ".join(normalized_hashtags)) if part]
    return _WHITESPACE_RE.sub(" ", " ".join(parts)).strip()


def _truncate_manual_x_body(text: str, max_length: int) -> str:
    compact = str(text or "").rstrip()
    if len(compact) <= max_length:
        return compact
    if max_length <= 1:
        return "…"[:max_length]

    cutoff = max_length - 1
    candidate = compact[:cutoff].rstrip()
    if not candidate:
        return "…"

    tail_window_start = max(0, len(candidate) - 40)
    punctuation_index = max(candidate.rfind(mark) for mark in _MANUAL_X_TRUNCATION_PUNCTUATION)
    if punctuation_index >= tail_window_start:
        candidate = candidate[: punctuation_index + 1].rstrip()
    else:
        last_space = candidate.rfind(" ")
        if last_space >= max(0, len(candidate) - 20):
            candidate = candidate[:last_space].rstrip()
        candidate = candidate.rstrip("、。,. ")

    return f"{candidate or compact[:cutoff].rstrip()}…"


def _trim_manual_x_post_text(value: str) -> str:
    compact = _polish_x_post_text(value)
    if len(compact) <= MAX_MANUAL_X_POST_LENGTH:
        return compact

    body, hashtags = _split_manual_x_trailing_hashtags(compact)
    body, url = _split_manual_x_trailing_url(body)
    suffix_parts = [part for part in (url, " ".join(hashtags)) if part]
    suffix = " ".join(suffix_parts).strip()
    if suffix:
        body_limit = MAX_MANUAL_X_POST_LENGTH - len(suffix) - (1 if body else 0)
        if body_limit > 0:
            trimmed_body = _truncate_manual_x_body(body, body_limit)
            rebuilt = f"{trimmed_body} {suffix}" if trimmed_body else suffix
            if len(rebuilt) <= MAX_MANUAL_X_POST_LENGTH:
                return rebuilt

    return _truncate_manual_x_body(compact, MAX_MANUAL_X_POST_LENGTH)


def _build_x_intent_url(text: str) -> str:
    encoded = quote(str(text or "").strip(), safe="")
    return f"https://twitter.com/intent/tweet?text={encoded}"


def _render_manual_x_post_candidates(context: ManualXContext) -> list[tuple[str, str]]:
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


def _manual_x_candidate_suppression_reason(
    request: PublishNoticeRequest,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
    rendered_candidates: Sequence[tuple[str, str]] | None = None,
) -> str | None:
    yellow_entry = _latest_yellow_log_entry_for_post(request.post_id, yellow_log_path=yellow_log_path)
    if yellow_entry is None:
        applied_flags: set[str] = set()
    else:
        block_reason = str(yellow_entry.get("manual_x_post_block_reason") or "").strip()
        if block_reason:
            return block_reason
        applied_flags = {str(flag) for flag in (yellow_entry.get("applied_flags") or []) if str(flag)}

    if "roster_movement_yellow" in applied_flags:
        return "roster_movement_yellow"
    if "x_post_numeric_mismatch" in applied_flags:
        return "x_post_numeric_mismatch"
    if "x_post_unverified_player_name" in applied_flags:
        return "x_post_unverified_player_name"
    if rendered_candidates:
        detector_report = check_consistency(
            source_text=str(request.title or "").strip(),
            generated_body=str(request.summary or request.title or "").strip(),
            x_candidates=[text for _label, text in rendered_candidates if str(text or "").strip()],
            metadata={
                "article_title": str(request.title or "").strip(),
                "summary": str(request.summary or "").strip(),
            },
            publish_time_iso=str(request.publish_time_iso or "").strip(),
        )
        if detector_report.x_candidate_suppress_flags:
            return str(detector_report.x_candidate_suppress_flags[0])
    return None


def _farm_subtype_review_reason(
    request: PublishNoticeRequest,
    context: ManualXContext,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> str | None:
    normalized_subtype = str(request.subtype or "").strip().lower()
    if normalized_subtype not in {"farm_result", "farm_lineup"}:
        return None

    yellow_entry = _latest_yellow_log_entry_for_post(request.post_id, yellow_log_path=yellow_log_path) or {}
    applied_flags = {
        str(flag).strip()
        for flag in (yellow_entry.get("applied_flags") or [])
        if str(flag).strip()
    }
    if "subtype_unresolved" in applied_flags:
        return f"{normalized_subtype}_review"
    if _is_past_publish_date(request.publish_time_iso):
        return f"{normalized_subtype}_review"

    combined = " ".join(
        item for item in (context.title, context.cleaned_summary) if item and item != "(なし)"
    )
    if normalized_subtype == "farm_result" and not _FARM_RESULT_FACT_RE.search(combined):
        return "farm_result_review"
    if normalized_subtype == "farm_lineup" and not _FARM_LINEUP_MARKER_RE.search(combined):
        return "farm_lineup_review"
    return None


def _first_team_subtype_review_reason(
    request: PublishNoticeRequest,
    context: ManualXContext,
) -> str | None:
    normalized_subtype = str(request.subtype or "").strip().lower()
    raw_title = str(request.title or "").strip()
    raw_summary = _WHITESPACE_RE.sub(" ", str(request.summary or "").strip())
    if not _is_first_team_article(raw_title, raw_summary, normalized_subtype):
        return None

    combined = " ".join(
        item for item in (raw_title, context.cleaned_summary, raw_summary) if item and item != "(なし)"
    )
    if normalized_subtype == "postgame":
        if "試合結果" not in combined:
            return None
        if not _FIRST_TEAM_POSTGAME_SCORE_RE.search(combined) and not _FIRST_TEAM_POSTGAME_KEY_EVENT_RE.search(
            combined
        ):
            return _FIRST_TEAM_POSTGAME_REVIEW_REASON
        return None
    if normalized_subtype == "lineup":
        if _is_past_publish_date(request.publish_time_iso):
            return _FIRST_TEAM_LINEUP_REVIEW_REASON
        if not _FIRST_TEAM_LINEUP_MARKER_RE.search(combined):
            return _FIRST_TEAM_LINEUP_REVIEW_REASON
    return None


def _program_notice_review_reason(
    request: PublishNoticeRequest,
    context: ManualXContext,
) -> str | None:
    normalized_subtype = str(request.subtype or "").strip().lower()
    raw_title = str(request.title or "").strip()
    raw_summary = _WHITESPACE_RE.sub(" ", str(request.summary or "").strip())
    if not _is_program_notice(raw_title, raw_summary, normalized_subtype):
        return None

    combined = " ".join(
        item for item in (raw_title, context.cleaned_summary, raw_summary) if item and item != "(なし)"
    )
    has_date = bool(_MANUAL_X_DATE_RE.search(combined))
    has_time = bool(_PROGRAM_NOTICE_TIME_RE.search(combined))
    has_program_title = bool(_PROGRAM_NOTICE_MARKER_RE.search(combined))
    if has_date and has_time and has_program_title:
        return None
    return "program_notice_review"


def _roster_notice_review_reason(
    request: PublishNoticeRequest,
    context: ManualXContext,
) -> str | None:
    normalized_subtype = str(request.subtype or "").strip().lower()
    raw_title = str(request.title or "").strip()
    raw_summary = _WHITESPACE_RE.sub(" ", str(request.summary or "").strip())
    if not _is_roster_notice(raw_title, raw_summary, normalized_subtype):
        return None
    return "roster_notice_review"


def _injury_recovery_notice_review_reason(
    request: PublishNoticeRequest,
    context: ManualXContext,
) -> str | None:
    normalized_subtype = str(request.subtype or "").strip().lower()
    raw_title = str(request.title or "").strip()
    raw_summary = _WHITESPACE_RE.sub(" ", str(request.summary or "").strip())
    if not _is_injury_recovery_notice(raw_title, raw_summary, normalized_subtype):
        return None

    combined = " ".join(
        item for item in (raw_title, context.cleaned_summary, raw_summary) if item and item != "(なし)"
    )
    if _INJURY_DETAIL_MARKER_RE.search(combined):
        return None
    return "injury_recovery_notice_review"


def _default_review_reason(request: PublishNoticeRequest) -> str | None:
    if _is_default_review(request.subtype):
        return "default_review"
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
    sensitive_x_block_reason = _manual_x_sensitive_block_reason(
        request,
        article_type=article_type,
        title=title,
        cleaned_summary=cleaned_summary,
        raw_summary=raw_summary,
    )
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
        sensitive_x_block_reason=sensitive_x_block_reason,
    )


def build_manual_x_post_candidates(
    request: PublishNoticeRequest,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> list[tuple[str, str]]:
    """Return deterministic manual-copy X post candidates for a publish notice."""

    context = _manual_x_context(request)
    if context.sensitive_x_block_reason:
        return []
    rendered_candidates = _render_manual_x_post_candidates(context)
    if _manual_x_candidate_suppression_reason(
        request,
        yellow_log_path=yellow_log_path,
        rendered_candidates=rendered_candidates,
    ):
        return []
    return rendered_candidates


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
        "record_type",
        "skip_layer",
    ):
        if key not in metadata:
            continue
        value = metadata.get(key)
        if value is None or value == "":
            continue
        lines.append(f"{key}: {value}")
    lines.append("---")
    return lines


def _per_post_metadata_block(metadata: dict[str, Any]) -> list[str]:
    lines = ["--- metadata ---"]
    for key in (
        "mail_type",
        "mail_class",
        "action",
        "priority",
        "post_id",
        "subtype",
        "x_post_ready",
        "reason",
        "record_type",
        "skip_layer",
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


def _format_review_reason_label(reason: str | None) -> tuple[str, str]:
    normalized_reason = str(reason or "").strip() or None
    return _REVIEW_REASON_LABELS.get(normalized_reason, _REVIEW_REASON_LABELS[None])


def _subject_prefix_for_classification(classification: dict[str, Any] | None) -> str:
    mail_class = str((classification or {}).get("mail_class") or "publish").strip() or "publish"
    reason = str((classification or {}).get("reason") or "").strip() or None
    if mail_class == "review" and reason in _REVIEW_X_BLOCK_REASONS:
        return "【要確認・X見送り】"
    return _mail_class_config(mail_class)["prefix"]


def _format_next_action_line(mail_class: str, reason: str | None) -> str:
    normalized_class = str(mail_class or "").strip() or "publish"
    normalized_reason = str(reason or "").strip() or None
    if normalized_class == "review":
        if normalized_reason in _REVIEW_X_BLOCK_REASONS:
            return "次アクション: 記事だけ確認。X 投稿は見送り"
        return "次アクション: 後で確認。急ぎ投稿不要"
    if normalized_class == "publish":
        return "次アクション: 問題なければ放置"
    if normalized_class == "x_candidate":
        return "次アクション: 内容確認後 X 投稿候補から選んで投稿"
    if normalized_class == "urgent":
        return "次アクション: 即確認"
    if normalized_class == "warning":
        return "次アクション: 警告内容を確認"
    return ""


def _format_summary_lines(summary: str | None, *, reason: str | None) -> list[str]:
    if str(reason or "").strip() == "summary_dirty_review":
        compact = _WHITESPACE_RE.sub(" ", str(summary or "").strip())
        if not compact:
            return ["summary: (なし)"]
        excerpt = compact
        if len(excerpt) > _DIRTY_REVIEW_SUMMARY_LIMIT:
            excerpt = f"{excerpt[: _DIRTY_REVIEW_SUMMARY_LIMIT - 1]}…"
        return [
            "summary: 要約は確認用に短縮表示(本文 URL を確認してください)",
            f"summary_excerpt: {excerpt}",
        ]
    return [f"summary: {_normalize_summary(summary)}"]


def _manual_x_candidate_body_lines(
    candidates: Sequence[tuple[str, str]],
    *,
    include_intent_link: bool,
) -> list[str]:
    lines: list[str] = []
    for index, (_label, text) in enumerate(candidates, start=1):
        line_label = f"投稿文{index}" if include_intent_link else f"投稿文{index}(コピー用)"
        lines.append(f"{line_label}: {text}")
        lines.append(f"文字数: {len(text)}")
        if include_intent_link:
            lines.append(f"Xで開く: {_build_x_intent_url(text)}")
    return lines


def _manual_x_candidate_display_mode(mail_state: dict[str, Any]) -> tuple[bool, bool]:
    mail_class = str(mail_state.get("mail_class") or "publish").strip() or "publish"
    x_post_ready = str(mail_state.get("x_post_ready") or "").strip().lower() == "true"
    show_candidates = mail_class == "x_candidate" and x_post_ready and not mail_state.get("suppression_reason")
    show_hidden_notice = (
        not show_candidates
        and (mail_class in {"review", "warning", "urgent"} or (not x_post_ready and mail_class != "publish"))
    )
    return show_candidates, show_hidden_notice


def _manual_x_hidden_notice_line(mail_state: dict[str, Any], *, suppression_reason: Any = None) -> str:
    reason = str(mail_state.get("reason") or suppression_reason or "review_required").strip() or "review_required"
    mail_class = str(mail_state.get("mail_class") or "publish").strip() or "publish"
    if mail_class == "review":
        if reason in _REVIEW_X_BLOCK_REASONS:
            return "[X 投稿候補] 非表示: X 投稿は見送りです"
        return "[X 投稿候補] 非表示: 本文確認後に必要なら手動で判断してください"
    if mail_class == "warning":
        return "[X 投稿候補] 非表示: 警告対応を優先してください"
    if mail_class == "urgent":
        return "[X 投稿候補] 非表示: 緊急確認を優先してください"
    if mail_class == "x_candidate":
        return "[X 投稿候補] 非表示: X 投稿候補を表示できません"
    return "[X 投稿候補] 非表示"


def _per_post_mail_state(
    request: PublishNoticeRequest,
    *,
    yellow_log_path: str | Path = DEFAULT_GUARDED_PUBLISH_YELLOW_LOG_PATH,
) -> dict[str, Any]:
    if str(getattr(request, "notice_kind", "publish") or "publish").strip() == "post_gen_validate":
        review_config = _mail_class_config("review")
        return {
            "mail_type": "per_post",
            "mail_class": "review",
            "action": review_config["action"],
            "priority": review_config["priority"],
            "post_id": request.post_id,
            "subtype": str(request.subtype or "").strip() or "unknown",
            "x_post_ready": "false",
            "reason": str(getattr(request, "skip_reason", "") or "post_gen_validate").strip() or "post_gen_validate",
            "record_type": str(getattr(request, "record_type", "") or "post_gen_validate").strip() or "post_gen_validate",
            "skip_layer": str(getattr(request, "skip_layer", "") or "post_gen_validate").strip() or "post_gen_validate",
            "manual_x_candidates": [],
            "manual_x_display_candidates": [],
            "suppression_reason": None,
        }

    raw_summary = _WHITESPACE_RE.sub(" ", str(request.summary or "").strip())
    context = _manual_x_context(request)
    display_manual_x_candidates = (
        [] if context.sensitive_x_block_reason else _render_manual_x_post_candidates(context)
    )
    suppression_reason = _manual_x_candidate_suppression_reason(
        request,
        yellow_log_path=yellow_log_path,
        rendered_candidates=display_manual_x_candidates,
    ) or context.sensitive_x_block_reason
    manual_x_candidates = [] if suppression_reason else list(display_manual_x_candidates)
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
        reason = str(suppression_reason or "urgent_keyword_detected")
    elif safe_x_candidate:
        mail_class = "x_candidate"
        reason = "manual_x_candidates_clean"
    elif suppression_reason == "roster_movement_yellow":
        mail_class = "review"
        reason = "roster_movement_yellow_x_blocked"
    elif suppression_reason == "sensitive_content_x_blocked":
        mail_class = "review"
        reason = "sensitive_content_x_blocked"
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

    first_team_review_reason = _first_team_subtype_review_reason(request, context)
    if first_team_review_reason and mail_class in {"publish", "x_candidate"}:
        mail_class = "review"
        reason = first_team_review_reason

    program_review_reason = _program_notice_review_reason(request, context)
    if program_review_reason and mail_class in {"publish", "x_candidate"}:
        mail_class = "review"
        reason = program_review_reason

    roster_review_reason = _roster_notice_review_reason(request, context)
    if roster_review_reason and mail_class in {"publish", "x_candidate"}:
        mail_class = "review"
        reason = roster_review_reason

    injury_review = _injury_recovery_notice_review_reason(request, context)
    if injury_review and mail_class in {"publish", "x_candidate"}:
        mail_class = "review"
        reason = injury_review
        x_post_ready = "false"

    default_review_r = _default_review_reason(request)
    if default_review_r and mail_class in {"publish", "x_candidate"}:
        mail_class = "review"
        reason = default_review_r
        x_post_ready = "false"

    farm_review_reason = _farm_subtype_review_reason(
        request,
        context,
        yellow_log_path=yellow_log_path,
    )
    if farm_review_reason and mail_class in {"publish", "x_candidate"}:
        mail_class = "review"
        reason = farm_review_reason

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
        "manual_x_display_candidates": display_manual_x_candidates,
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
        reason = {
            "backlog_only": "backlog_summary_ready",
            "burst_forced": "burst_summary_ready",
        }.get(str(request.summary_mode or "default").strip(), "batch_summary_ready")
        return {
            "mail_type": "batch_summary",
            "mail_class": "summary",
            "action": mail_config["action"],
            "priority": mail_config["priority"],
            "reason": reason,
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
    return _load_jsonl_entries(path)


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


def _replay_window_dedup_enabled() -> bool:
    return str(os.environ.get(_REPLAY_WINDOW_DEDUP_ENV_FLAG, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _resolve_replay_window_minutes() -> int:
    raw_value = str(os.environ.get(_REPLAY_WINDOW_MINUTES_ENV, _REPLAY_WINDOW_MINUTES_DEFAULT)).strip()
    try:
        minutes = int(raw_value)
    except ValueError:
        return _REPLAY_WINDOW_MINUTES_DEFAULT
    return max(1, minutes)


def _is_within_recent_replay_window(
    post_id: int | str,
    *,
    history_path: str | Path | None,
    now: datetime | None = None,
    window_minutes: int,
) -> bool:
    if history_path is None:
        return False
    current_now = _coerce_now(now)
    replay_window = timedelta(minutes=max(1, int(window_minutes)))
    target_post_id = str(post_id)
    merged_entries = _load_queue_entries(history_path)
    merged_entries.extend(_load_remote_publish_notice_queue_entries(history_path))
    for entry in reversed(merged_entries):
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
        if timedelta(0) <= delta <= replay_window:
            return True
    return False


def _has_recent_publish_notice_history_overlap(
    post_id: int | str,
    *,
    duplicate_history_path: str | Path | None,
    now: datetime | None = None,
    window_minutes: int,
) -> bool:
    history_path = _derive_publish_notice_history_path(duplicate_history_path)
    if history_path is None:
        return False
    history_entries = _load_history_entries(history_path)
    history_entries.update(_load_remote_publish_notice_history_entries(history_path))
    recorded_at = _parse_datetime_to_jst(history_entries.get(str(post_id)))
    if recorded_at is None:
        return False
    delta = _coerce_now(now) - recorded_at
    replay_window = timedelta(minutes=max(1, int(window_minutes)))
    return timedelta(0) <= delta <= replay_window


def _should_suppress_recent_replay_duplicate(
    request: PublishNoticeRequest,
    *,
    duplicate_history_path: str | Path | None,
    now: datetime | None = None,
) -> bool:
    if not _replay_window_dedup_enabled():
        return False
    notice_kind = str(getattr(request, "notice_kind", "publish") or "publish").strip() or "publish"
    if notice_kind != "publish":
        return False
    window_minutes = _resolve_replay_window_minutes()
    if _is_within_recent_replay_window(
        request.post_id,
        history_path=duplicate_history_path,
        now=now,
        window_minutes=window_minutes,
    ):
        return True
    notice_origin = str(getattr(request, "notice_origin", "") or "").strip()
    if notice_origin == _DIRECT_PUBLISH_NOTICE_ORIGIN:
        return False
    return _has_recent_publish_notice_history_overlap(
        request.post_id,
        duplicate_history_path=duplicate_history_path,
        now=now,
        window_minutes=window_minutes,
    )


def _force_review_mail_state(mail_state: dict[str, Any]) -> dict[str, Any]:
    forced = dict(mail_state)
    review_config = _mail_class_config("review")
    forced["mail_class"] = "review"
    forced["action"] = review_config["action"]
    forced["priority"] = review_config["priority"]
    forced["reason"] = str(forced.get("reason") or "default_review").strip() or "default_review"
    return forced


def _publish_only_mail_filter_enabled() -> bool:
    return str(os.environ.get(_PUBLISH_ONLY_MAIL_FILTER_ENV_FLAG, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _publish_only_filter_direct_publish_bypass_enabled() -> bool:
    return str(os.environ.get(_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS_ENV_FLAG, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _publish_only_filter_backlog_bypass_enabled() -> bool:
    return str(os.environ.get(_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS_ENV_FLAG, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _burst_summary_mail_disabled() -> bool:
    return str(os.environ.get(_DISABLE_BURST_SUMMARY_MAIL_ENV_FLAG, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_publish_only_subject(subject: str) -> bool:
    return str(subject or "").strip().startswith(_PUBLISH_ONLY_MAIL_PREFIX)


def _should_suppress_publish_only_mail(
    *,
    subject: str,
    classification: dict[str, Any],
    request: PublishNoticeRequest | None = None,
) -> bool:
    if not _publish_only_mail_filter_enabled():
        return False
    mail_type = str((classification or {}).get("mail_type") or "").strip()
    if mail_type != "per_post":
        return False
    if _is_publish_only_subject(subject):
        return False
    if not _publish_only_filter_direct_publish_bypass_enabled():
        return True
    if request is None:
        return True
    notice_kind = str(getattr(request, "notice_kind", "publish") or "publish").strip() or "publish"
    notice_origin = str(getattr(request, "notice_origin", "") or "").strip()
    return not (
        notice_kind == "publish"
        and notice_origin == _DIRECT_PUBLISH_NOTICE_ORIGIN
    )


def _should_bypass_backlog_summary_only(request: PublishNoticeRequest | None) -> bool:
    if request is None:
        return False
    if not _publish_only_filter_backlog_bypass_enabled():
        return False
    notice_kind = str(getattr(request, "notice_kind", "publish") or "publish").strip() or "publish"
    notice_origin = str(getattr(request, "notice_origin", "") or "").strip()
    record_type = str(getattr(request, "record_type", "") or "").strip()
    return (
        notice_kind == "publish"
        and notice_origin == _DIRECT_PUBLISH_NOTICE_ORIGIN
        and record_type != _PUBLISH_NOTICE_24H_BUDGET_SUMMARY_ONLY_RECORD_TYPE
    )


def build_subject(
    title: str,
    publish_dt_jst: str | None = None,
    override: str | None = None,
    classification: dict[str, Any] | None = None,
) -> str:
    del publish_dt_jst
    if override is not None:
        return str(override)
    prefix = _subject_prefix_for_classification(classification)
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
    mail_class = str(mail_state.get("mail_class") or "publish").strip() or "publish"
    reason = str(mail_state.get("reason") or "").strip() or None
    if str(getattr(request, "notice_kind", "publish") or "publish").strip() == "post_gen_validate":
        source_title = str(getattr(request, "source_title", "") or request.title or "").strip()
        generated_title = str(getattr(request, "generated_title", "") or "").strip()
        skip_reason = str(getattr(request, "skip_reason", "") or reason or "post_gen_validate").strip() or "post_gen_validate"
        skip_reason_label = str(getattr(request, "skip_reason_label", "") or skip_reason).strip() or skip_reason
        category = str(getattr(request, "category", "") or "").strip() or "unknown"
        source_url_hash = str(getattr(request, "source_url_hash", "") or "").strip()
        fail_axes = [str(axis).strip() for axis in getattr(request, "fail_axes", ()) if str(axis).strip()]
        lines = [
            "次アクション: skip 理由を確認し、title rescue または source 拡張の要否を判断",
            "判定: 要review",
            f"理由: {skip_reason_label}",
            f"source_title: {source_title or '(none)'}",
            f"generated_title: {generated_title or '(none)'}",
            f"source_url: {str(request.canonical_url or '').strip()}",
            f"category: {category}",
            f"subtype: {str(request.subtype or '').strip() or 'unknown'}",
            f"detected_at: {_format_publish_time_jst(request.publish_time_iso)}",
            f"skip_reason: {skip_reason}",
        ]
        if source_url_hash:
            lines.append(f"source_url_hash: {source_url_hash}")
        if fail_axes:
            lines.append(f"fail_axis: {', '.join(fail_axes)}")
        lines.extend(
            _per_post_metadata_block(
                {
                    "mail_type": mail_state.get("mail_type"),
                    "mail_class": mail_class,
                    "action": mail_state.get("action"),
                    "priority": mail_state.get("priority"),
                    "subtype": str(request.subtype or "").strip() or "unknown",
                    "x_post_ready": "false",
                    "reason": skip_reason,
                    "record_type": mail_state.get("record_type") or "post_gen_validate",
                    "skip_layer": mail_state.get("skip_layer") or "post_gen_validate",
                }
            )
        )
        return "\n".join(lines)

    suppression_reason = mail_state.get("suppression_reason")
    manual_x_candidates = list(
        mail_state.get("manual_x_display_candidates") or mail_state.get("manual_x_candidates") or []
    )
    show_manual_x_candidates, show_hidden_notice = _manual_x_candidate_display_mode(mail_state)
    include_intent_link = show_manual_x_candidates
    lines: list[str] = []
    next_action_line = _format_next_action_line(mail_class, reason)
    if next_action_line:
        lines.append(next_action_line)
    if mail_class == "review":
        action_hint, review_description = _format_review_reason_label(reason)
        lines.extend(
            [
                f"判定: {action_hint}",
                f"理由: {review_description}",
            ]
        )
    lines.extend(
        [
            f"title: {str(request.title or '').strip()}",
            f"url: {str(request.canonical_url or '').strip()}",
            f"subtype: {str(request.subtype or '').strip() or 'unknown'}",
            f"publish time: {_format_publish_time_jst(request.publish_time_iso)}",
        ]
    )
    lines.extend(_format_summary_lines(request.summary, reason=reason))
    if suppression_reason == "roster_movement_yellow":
        lines.append("warning: [Warning] roster movement 系記事、X 自動投稿対象外")
    if show_manual_x_candidates:
        lines.extend(
            [
                "manual_x_post_candidates:",
                f"article_url: {str(request.canonical_url or '').strip()}",
            ]
        )
        lines.extend(_manual_x_candidate_body_lines(manual_x_candidates, include_intent_link=include_intent_link))
    elif show_hidden_notice:
        lines.append(_manual_x_hidden_notice_line(mail_state, suppression_reason=suppression_reason))
    lines.extend(
        _per_post_metadata_block(
            {
                "mail_type": mail_state.get("mail_type"),
                "mail_class": mail_class,
                "action": mail_state.get("action"),
                "priority": mail_state.get("priority"),
                "post_id": request.post_id,
                "subtype": str(request.subtype or "").strip() or "unknown",
                "x_post_ready": mail_state.get("x_post_ready"),
                "reason": mail_state.get("reason"),
            }
        )
    )
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
    guarded_publish_history_path: str | Path = DEFAULT_GUARDED_PUBLISH_HISTORY_PATH,
) -> list[BurstSummaryRequest]:
    if _burst_summary_mail_disabled():
        return []
    if int(summary_every) <= 0:
        raise ValueError("summary_every must be > 0")
    resolved_entries: list[BurstSummaryEntry] = []
    history_resolved_count = 0
    for entry in entries:
        matched_history = None
        if entry.is_backlog is not None:
            history_resolved_count += 1
        else:
            matched_history = _latest_guarded_publish_history_entry(
                entry.post_id,
                history_path=guarded_publish_history_path,
            )
            if matched_history is not None:
                history_resolved_count += 1
        resolved_entries.append(
            replace(
                entry,
                is_backlog=bool(entry.is_backlog)
                if entry.is_backlog is not None
                else bool((matched_history or {}).get("is_backlog")),
            )
        )
    if len(resolved_entries) > FORCED_SUMMARY_THRESHOLD and history_resolved_count == len(resolved_entries):
        return [
            BurstSummaryRequest(
                entries=resolved_entries,
                cumulative_published_count=int(cumulative_before) + len(resolved_entries),
                daily_cap=int(daily_cap),
                summary_mode="burst_forced",
            )
        ]

    backlog_entries = [entry for entry in resolved_entries if bool(entry.is_backlog)]
    fresh_entries = [entry for entry in resolved_entries if not bool(entry.is_backlog)]
    requests: list[BurstSummaryRequest] = []
    if backlog_entries:
        requests.append(
            BurstSummaryRequest(
                entries=backlog_entries,
                cumulative_published_count=int(cumulative_before) + len(resolved_entries),
                daily_cap=int(daily_cap),
                summary_mode="backlog_only",
            )
        )
    summary_size = int(summary_every)
    fresh_offset = len(backlog_entries)
    for start in range(0, len(fresh_entries), summary_size):
        chunk = list(fresh_entries[start : start + summary_size])
        if len(chunk) < summary_size:
            break
        requests.append(
            BurstSummaryRequest(
                entries=chunk,
                cumulative_published_count=int(cumulative_before) + fresh_offset + start + len(chunk),
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
    guarded_publish_history_path: str | Path = DEFAULT_GUARDED_PUBLISH_HISTORY_PATH,
    now: datetime | None = None,
    duplicate_window: timedelta = DEFAULT_DUPLICATE_WINDOW,
) -> PublishNoticeEmailResult:
    normalized_title = str(request.title or "").strip()
    active_subject_override = (
        override_subject if override_subject is not None else getattr(request, "subject_override", None)
    )
    subject = build_subject(normalized_title, override=active_subject_override)
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
        is_backlog=request.is_backlog,
        notice_kind=str(getattr(request, "notice_kind", "publish") or "publish").strip() or "publish",
        notice_origin=getattr(request, "notice_origin", None),
        subject_override=active_subject_override,
        source_title=getattr(request, "source_title", None),
        generated_title=getattr(request, "generated_title", None),
        skip_reason=getattr(request, "skip_reason", None),
        skip_reason_label=getattr(request, "skip_reason_label", None),
        source_url_hash=getattr(request, "source_url_hash", None),
        category=getattr(request, "category", None),
        record_type=getattr(request, "record_type", None),
        skip_layer=getattr(request, "skip_layer", None),
        fail_axes=tuple(getattr(request, "fail_axes", ()) or ()),
    )
    mail_state = _classify_mail(normalized_request)
    if normalized_request.notice_kind != "publish":
        mail_state = _force_review_mail_state(mail_state)
    recipients = resolve_recipients(override_recipient)
    subject = build_subject(normalized_title, override=active_subject_override, classification=mail_state)
    if _should_suppress_publish_only_mail(
        subject=subject,
        classification=mail_state,
        request=normalized_request,
    ):
        return _suppressed(
            _PUBLISH_ONLY_MAIL_FILTER_SUPPRESSION_REASON,
            subject=subject,
            recipients=recipients,
        )
    if _should_suppress_recent_replay_duplicate(
        normalized_request,
        duplicate_history_path=duplicate_history_path,
        now=now,
    ):
        return _suppressed(
            _REPLAY_WINDOW_SUPPRESSION_REASON,
            subject=subject,
            recipients=recipients,
        )
    review_only_notice = normalized_request.notice_kind == "post_gen_validate"
    if not review_only_notice and _current_queued_batch_size(duplicate_history_path) > FORCED_SUMMARY_THRESHOLD:
        return _suppressed("BURST_SUMMARY_ONLY", subject=subject, recipients=recipients)
    is_backlog = _resolve_is_backlog(
        normalized_request.post_id,
        normalized_request.is_backlog,
        history_path=guarded_publish_history_path,
        allow_history_lookup=duplicate_history_path is not None
        or _path(guarded_publish_history_path) != DEFAULT_GUARDED_PUBLISH_HISTORY_PATH,
    )
    if not review_only_notice and is_backlog:
        if not _should_bypass_backlog_summary_only(normalized_request):
            return _suppressed("BACKLOG_SUMMARY_ONLY", subject=subject, recipients=recipients)
    return _deliver_mail(
        subject=subject,
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
        override_recipient=recipients,
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
    request: PublishNoticeRequest | None = None,
    history_path: str | Path | None = None,
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
    _record_history_after_send(
        history_path if history_path is not None else queue_path,
        request=request,
        result=result,
        recorded_at=recorded_at,
    )
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
    summary_only_suppressed = sum(
        1
        for result in results
        if str(result.status).strip() == "suppressed"
        and str(result.reason or "").strip() in _SUMMARY_ONLY_SUPPRESSION_REASONS
    )
    return PublishNoticeExecutionSummary(
        emitted=int(emitted),
        sent=int(status_counter.get("sent", 0)),
        suppressed=int(status_counter.get("suppressed", 0)),
        errors=int(status_counter.get("error", 0)),
        dry_run=int(status_counter.get("dry_run", 0)),
        summary_only_suppressed=int(summary_only_suppressed),
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
