"""Independent publish scanner for ticket 076 publish notice mail."""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import html
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import urlencode, urljoin
import urllib.request
from zoneinfo import ZoneInfo

from src.publish_notice_email_sender import PublishNoticeRequest, build_subject


JST = ZoneInfo("Asia/Tokyo")
_DEFAULT_WP_API_BASE = "https://yoshilover.com/wp-json/wp/v2"
_PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_LINEUP_ORDER_RE = re.compile(r"(?<![0-9０-９])[1-9１-９]\s*番")
_SCORE_RE = re.compile(r"(?<![0-9０-９])[0-9０-９]+\s*[-－ー]\s*[0-9０-９]+(?![0-9０-９])")
_HISTORY_WINDOW = timedelta(hours=24)
_REVIEW_NOTICE_MAX_PER_RUN_DEFAULT = 10
_REVIEW_NOTICE_WINDOW_HOURS_DEFAULT = 24.0
_GUARDED_PUBLISH_HISTORY_DEFAULT_PATH = Path("/tmp/pub004d/guarded_publish_history.jsonl")
_GUARDED_PUBLISH_HISTORY_FALLBACK_PATH = Path("logs/guarded_publish_history.jsonl")
_GUARDED_PUBLISH_HISTORY_CURSOR_DEFAULT_PATH = Path("/tmp/pub004d/guarded_publish_history_cursor.txt")
_POST_GEN_VALIDATE_HISTORY_DEFAULT_PATH = Path("/tmp/pub004d/post_gen_validate_history.jsonl")
_POST_GEN_VALIDATE_HISTORY_FALLBACK_PATH = Path("logs/post_gen_validate_history.jsonl")
_POST_GEN_VALIDATE_HISTORY_CURSOR_DEFAULT_PATH = Path("/tmp/pub004d/post_gen_validate_history_cursor.txt")
_POST_GEN_VALIDATE_NOTIFICATION_ENV_FLAG = "ENABLE_POST_GEN_VALIDATE_NOTIFICATION"
_POST_GEN_VALIDATE_SKIP_LAYER = "post_gen_validate"
_POST_GEN_VALIDATE_RECORD_TYPE = "post_gen_validate"
_POST_GEN_VALIDATE_REVIEW_PREFIX = "【要review｜post_gen_validate】"
_POST_GEN_VALIDATE_GCS_BUCKET = "baseballsite-yoshilover-state"
_POST_GEN_VALIDATE_GCS_OBJECT = "post_gen_validate/post_gen_validate_history.jsonl"
_GUARDED_PUBLISH_REVIEW_SUBJECT_RE = re.compile(r"^【[^】]+】")
_EXCLUDED_GUARDED_HOLD_REASONS = frozenset(
    {
        "duplicate_publish",
        "review_duplicate_candidate_same_source_url",
    }
)


@dataclass(frozen=True)
class ScanResult:
    emitted: list[PublishNoticeRequest]
    skipped: list[tuple[int | str, str]]
    cursor_before: str | None
    cursor_after: str


FetchFn = Callable[[str, str], list[Mapping[str, Any]]]
PostDetailFetchFn = Callable[[str, int | str], Mapping[str, Any] | None]


@dataclass(frozen=True)
class GuardedPublishHistoryScanResult:
    emitted: list[PublishNoticeRequest]
    skipped: list[tuple[int | str, str]]
    history_after: dict[str, str]
    cursor_before: str | None = None
    cursor_after: str | None = None
    cursor_path: Path | None = None
    cursor_write_needed: bool = False


def _now_jst() -> datetime:
    return datetime.now(JST)


def _coerce_now(now: Callable[[], datetime] | datetime | None) -> datetime:
    if callable(now):
        current = now()
    elif isinstance(now, datetime):
        current = now
    else:
        current = _now_jst()
    if current.tzinfo is None:
        return current.replace(tzinfo=JST)
    return current.astimezone(JST)


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _resolve_guarded_publish_history_path(value: str | Path | None = None) -> Path:
    if value is not None and str(value).strip():
        return _path(value)
    for env_name in ("PUBLISH_NOTICE_GUARDED_PUBLISH_HISTORY_PATH", "GUARDED_PUBLISH_HISTORY_PATH"):
        env_value = str(os.environ.get(env_name, "")).strip()
        if env_value:
            return _path(env_value)
    if _GUARDED_PUBLISH_HISTORY_DEFAULT_PATH.exists():
        return _GUARDED_PUBLISH_HISTORY_DEFAULT_PATH
    return _GUARDED_PUBLISH_HISTORY_FALLBACK_PATH


def _resolve_guarded_publish_history_cursor_path(value: str | Path | None = None) -> Path:
    if value is not None and str(value).strip():
        return _path(value)
    for env_name in (
        "PUBLISH_NOTICE_GUARDED_HISTORY_CURSOR_PATH",
        "GUARDED_PUBLISH_HISTORY_CURSOR_PATH",
    ):
        env_value = str(os.environ.get(env_name, "")).strip()
        if env_value:
            return _path(env_value)
    return _GUARDED_PUBLISH_HISTORY_CURSOR_DEFAULT_PATH


def _resolve_post_gen_validate_history_path(value: str | Path | None = None) -> Path:
    if value is not None and str(value).strip():
        return _path(value)
    env_value = str(os.environ.get("PUBLISH_NOTICE_POST_GEN_VALIDATE_HISTORY_PATH", "")).strip()
    if env_value:
        return _path(env_value)
    return _POST_GEN_VALIDATE_HISTORY_DEFAULT_PATH


def _resolve_post_gen_validate_history_cursor_path(value: str | Path | None = None) -> Path:
    if value is not None and str(value).strip():
        return _path(value)
    env_value = str(os.environ.get("PUBLISH_NOTICE_POST_GEN_VALIDATE_HISTORY_CURSOR_PATH", "")).strip()
    if env_value:
        return _path(env_value)
    return _POST_GEN_VALIDATE_HISTORY_CURSOR_DEFAULT_PATH


def _post_gen_validate_notification_enabled() -> bool:
    return str(os.environ.get(_POST_GEN_VALIDATE_NOTIFICATION_ENV_FLAG, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _parse_datetime_to_jst(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        current = value
    else:
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


def _isoformat_jst(value: str | datetime | None, fallback: datetime | None = None) -> str:
    parsed = _parse_datetime_to_jst(value)
    if parsed is not None:
        return parsed.isoformat()
    if fallback is None:
        return ""
    return _coerce_now(fallback).isoformat()


def _read_cursor(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _write_cursor(path: Path, cursor_iso: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{path}.tmp")
    tmp_path.write_text(f"{cursor_iso}\n", encoding="utf-8")
    os.replace(tmp_path, path)


def _gcs_client():
    try:
        from google.cloud import storage

        return storage.Client()
    except Exception:
        return None


def _sync_post_gen_validate_history_from_gcs(path: Path) -> None:
    client = _gcs_client()
    if client is None:
        return
    try:
        bucket = client.bucket(_POST_GEN_VALIDATE_GCS_BUCKET)
        blob = bucket.blob(_POST_GEN_VALIDATE_GCS_OBJECT)
        if not blob.exists():
            return
        payload = blob.download_as_text(encoding="utf-8")
    except Exception as exc:
        _log_event(
            "post_gen_validate_history_gcs_sync_failed",
            skip_layer=_POST_GEN_VALIDATE_SKIP_LAYER,
            reason=type(exc).__name__,
        )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _log_event(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), file=sys.stderr, flush=True)


def _load_history(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("publish notice history must be a JSON object")
    history: dict[str, str] = {}
    for key, value in payload.items():
        history[str(key)] = str(value)
    return history


def _write_history(path: Path, history: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{path}.tmp")
    tmp_path.write_text(
        json.dumps(dict(sorted(history.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _iter_jsonl_lines_reverse(path: Path, *, chunk_size: int = 65536) -> Iterator[str]:
    if not path.exists():
        return
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        buffer = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer
            split_lines = buffer.split(b"\n")
            buffer = split_lines[0]
            for raw_line in reversed(split_lines[1:]):
                yield raw_line.decode("utf-8", errors="replace")
        if buffer:
            yield buffer.decode("utf-8", errors="replace")


def _prune_history(history: Mapping[str, str], *, now: datetime) -> dict[str, str]:
    pruned: dict[str, str] = {}
    for post_id, posted_at in history.items():
        parsed = _parse_datetime_to_jst(posted_at)
        if parsed is None:
            continue
        if now - parsed > _HISTORY_WINDOW:
            continue
        pruned[str(post_id)] = parsed.isoformat()
    return pruned


def _strip_html(text: str) -> str:
    stripped = _TAG_RE.sub(" ", html.unescape(str(text or "")))
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def _first_paragraph_text(rendered: Any) -> str:
    text = str(rendered or "")
    if not text.strip():
        return ""
    match = _PARAGRAPH_RE.search(text)
    if match:
        return _strip_html(match.group(1))
    return _strip_html(text)


def _extract_rendered(value: Any) -> str:
    if isinstance(value, Mapping):
        raw = value.get("rendered")
        if raw is None:
            raw = value.get("raw")
        return str(raw or "")
    return str(value or "")


def _extract_summary(post: Mapping[str, Any]) -> str | None:
    excerpt_text = _first_paragraph_text(_extract_rendered(post.get("excerpt")))
    if excerpt_text:
        return excerpt_text
    content_text = _first_paragraph_text(_extract_rendered(post.get("content")))
    if content_text:
        return content_text
    return None


def _extract_title(post: Mapping[str, Any]) -> str:
    return _strip_html(_extract_rendered(post.get("title")))


def _extract_plain_text(post: Mapping[str, Any], key: str) -> str:
    return _strip_html(_extract_rendered(post.get(key)))


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _matches_lineup(text: str, text_lower: str) -> bool:
    return (
        _has_any_keyword(text, ("スタメン", "先発", "打順"))
        or _has_any_keyword(text_lower, ("lineup", "starting"))
        or _LINEUP_ORDER_RE.search(text) is not None
    )


def _matches_postgame(text: str, text_lower: str) -> bool:
    return (
        _has_any_keyword(text, ("勝利", "敗戦", "結果", "試合後", "コメント"))
        or _has_any_keyword(text_lower, ("postgame", "result"))
        or _SCORE_RE.search(text) is not None
    )


def _matches_farm(text: str, text_lower: str) -> bool:
    return _has_any_keyword(text, ("2軍", "二軍", "ファーム", "3軍", "三軍", "育成")) or _has_any_keyword(
        text_lower, ("farm",)
    )


def _matches_notice(text: str, text_lower: str) -> bool:
    return _has_any_keyword(text, ("公示", "登録", "抹消", "離脱", "復帰", "FA", "トレード", "移籍", "獲得", "契約")) or _has_any_keyword(
        text_lower, ("notice", "transaction", "roster")
    )


def _matches_program(text: str, text_lower: str) -> bool:
    return _has_any_keyword(text, ("番組", "テレビ", "中継", "Hulu", "DAZN")) or _has_any_keyword(
        text_lower, ("program", "broadcast", "tv", "hulu", "dazn")
    )


def _infer_subtype(post: Mapping[str, Any]) -> str:
    title = _extract_title(post)
    title_compact = _WHITESPACE_RE.sub("", title)
    title_lower = title.lower()
    title_checks = (
        ("lineup", _matches_lineup(title, title_lower)),
        ("farm", _matches_farm(title, title_lower)),
        ("notice", _matches_notice(title, title_lower)),
        ("program", _matches_program(title, title_lower)),
        ("postgame", _matches_postgame(title, title_lower)),
    )
    if len(title_compact) < 5 and not any(matched for _subtype, matched in title_checks):
        return "default"
    for subtype, matched in title_checks:
        if matched:
            return subtype

    supplemental_text = " ".join(
        part for part in (_extract_plain_text(post, "excerpt"), _extract_plain_text(post, "content")) if part
    )
    supplemental_lower = supplemental_text.lower()
    if _matches_lineup(supplemental_text, supplemental_lower):
        return "lineup"
    if _matches_farm(supplemental_text, supplemental_lower):
        return "farm"
    if _matches_notice(supplemental_text, supplemental_lower):
        return "notice"
    if _matches_program(supplemental_text, supplemental_lower):
        return "program"
    if _matches_postgame(supplemental_text, supplemental_lower):
        return "postgame"
    return "default"


def _extract_subtype(post: Mapping[str, Any]) -> str:
    meta = post.get("meta")
    if isinstance(meta, Mapping):
        subtype = str(meta.get("article_subtype") or "").strip().lower()
        if subtype:
            return subtype
        subtype = str(meta.get("subtype") or "").strip().lower()
        if subtype:
            return subtype
    for key in ("article_subtype", "subtype"):
        subtype = str(post.get(key) or "").strip().lower()
        if subtype:
            return subtype
    return _infer_subtype(post)


def _append_queue_log(
    queue_path: str | Path,
    *,
    status: str,
    reason: str | None,
    subject: str,
    recipients: list[str],
    post_id: int | str,
    recorded_at_iso: str,
    extra_payload: Mapping[str, Any] | None = None,
) -> None:
    path = _path(queue_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "status": status,
        "reason": reason,
        "subject": subject,
        "recipients": list(recipients),
        "post_id": post_id,
        "recorded_at": recorded_at_iso,
    }
    if extra_payload:
        for key, value in extra_payload.items():
            if key in entry:
                continue
            entry[str(key)] = value
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _resolve_review_max_per_run(value: int | None) -> int:
    if value is not None:
        return max(0, int(value))
    env_value = str(os.environ.get("PUBLISH_NOTICE_REVIEW_MAX_PER_RUN", "")).strip()
    if not env_value:
        return _REVIEW_NOTICE_MAX_PER_RUN_DEFAULT
    try:
        return max(0, int(env_value))
    except ValueError:
        return _REVIEW_NOTICE_MAX_PER_RUN_DEFAULT


def _resolve_review_window_hours(value: float | int | None) -> float:
    if value is not None:
        return max(0.0, float(value))
    env_value = str(os.environ.get("PUBLISH_NOTICE_REVIEW_WINDOW_HOURS", "")).strip()
    if not env_value:
        return _REVIEW_NOTICE_WINDOW_HOURS_DEFAULT
    try:
        return max(0.0, float(env_value))
    except ValueError:
        return _REVIEW_NOTICE_WINDOW_HOURS_DEFAULT


def _guarded_publish_entry_datetime(entry: Mapping[str, Any]) -> datetime | None:
    for key in ("ts", "recorded_at", "date"):
        parsed = _parse_datetime_to_jst(entry.get(key))
        if parsed is not None:
            return parsed
    return None


def _resolve_guarded_publish_scan_cursor(
    *,
    cursor_before: str | None,
    now: datetime,
    recent_window: timedelta,
) -> tuple[str | None, datetime]:
    cutoff = now - recent_window
    parsed = _parse_datetime_to_jst(cursor_before)
    if parsed is None:
        return None, cutoff
    if parsed < cutoff:
        return parsed.isoformat(), cutoff
    if parsed > now:
        return parsed.isoformat(), now
    return parsed.isoformat(), parsed


def _load_incremental_guarded_publish_entries(
    path: Path,
    *,
    now: datetime,
    recent_window: timedelta,
    cursor_before: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cursor_before_iso, effective_cursor = _resolve_guarded_publish_scan_cursor(
        cursor_before=cursor_before,
        now=now,
        recent_window=recent_window,
    )
    file_size_bytes = path.stat().st_size if path.exists() else 0
    entries: list[dict[str, Any]] = []
    skipped_by_cursor = 0
    valid_row_seen = False

    for raw_line in _iter_jsonl_lines_reverse(path):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        recorded_at = _guarded_publish_entry_datetime(payload)
        if recorded_at is None or recorded_at > now:
            continue
        valid_row_seen = True
        if recorded_at <= effective_cursor:
            skipped_by_cursor += 1
            break
        entries.append(payload)

    return entries, {
        "cursor_before_iso": cursor_before_iso,
        "effective_cursor_iso": effective_cursor.isoformat(),
        "file_empty": file_size_bytes <= 0 or not valid_row_seen,
        "file_size_bytes": file_size_bytes,
        "skipped_by_cursor": skipped_by_cursor,
    }


def _normalize_guarded_reason(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_guarded_publish_review_candidate(
    *,
    judgment: str,
    hold_reason: str,
    status: str,
) -> bool:
    if status in {"sent", "publish", "published"}:
        return False
    if judgment in {"red", "hard_stop"}:
        return False
    if hold_reason.startswith("hard_stop"):
        return False
    if hold_reason in _EXCLUDED_GUARDED_HOLD_REASONS:
        return False
    if judgment in {"yellow", "review"}:
        return True
    return bool(hold_reason)


def _guarded_publish_subject_prefix(*, judgment: str, hold_reason: str) -> str:
    if hold_reason == "backlog_only":
        return "【要確認(古い候補)】"
    if judgment == "review":
        return "【要review】"
    if judgment == "yellow" and (hold_reason == "cleanup_required" or "cleanup" in hold_reason):
        return "【要review】"
    if judgment == "yellow":
        return "【要確認】"
    if hold_reason:
        return f"【hold:{hold_reason}】"
    return "【要review】"


def _build_guarded_publish_subject(title: str, *, judgment: str, hold_reason: str) -> str:
    subject = build_subject(title)
    prefix = _guarded_publish_subject_prefix(judgment=judgment, hold_reason=hold_reason)
    if _GUARDED_PUBLISH_REVIEW_SUBJECT_RE.search(subject):
        return _GUARDED_PUBLISH_REVIEW_SUBJECT_RE.sub(prefix, subject, count=1)
    return f"{prefix}{title}"


def _hash_text(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _post_gen_validate_entry_datetime(entry: Mapping[str, Any]) -> datetime | None:
    for key in ("ts", "recorded_at", "date"):
        parsed = _parse_datetime_to_jst(entry.get(key))
        if parsed is not None:
            return parsed
    return None


def _normalize_fail_axes(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value or "").strip()
    return (text,) if text else ()


def _resolve_post_gen_validate_skip_reason(entry: Mapping[str, Any]) -> str:
    fail_axes = _normalize_fail_axes(entry.get("fail_axis") or entry.get("fail_axes"))
    stop_reason = str(entry.get("skip_reason") or entry.get("stop_reason") or "").strip()
    if fail_axes and fail_axes[0].startswith(("weak_subject_title:", "weak_generated_title:")):
        return fail_axes[0]
    if stop_reason:
        return stop_reason
    if fail_axes:
        return fail_axes[0]
    return "post_gen_validate"


def _post_gen_validate_reason_label(skip_reason: str) -> str:
    normalized = str(skip_reason or "").strip()
    if normalized == "weak_subject_title:related_info_escape":
        return "タイトルが『関連情報』『発言ポイント』だけで、人名や文脈を拾えなかったため"
    if normalized == "weak_generated_title:no_strong_marker":
        return "タイトルが弱い表現で、強いニュース要素を判定できなかったため"
    if normalized == "weak_generated_title:blacklist_phrase":
        return "タイトルに blacklist phrase を含み、そのまま publish 候補にできないため"
    if normalized.startswith("postgame_strict:") and "required_facts_missing" in normalized:
        return "postgame strict template に必要な fact が不足しているため"
    if normalized == "close_marker":
        return "close marker を検出できず、後追い記事の疑いがあるため"
    return normalized


def _post_gen_validate_title(entry: Mapping[str, Any]) -> str:
    source_title = str(entry.get("source_title") or "").strip()
    if source_title:
        return source_title
    generated_title = str(entry.get("generated_title") or entry.get("title") or "").strip()
    if generated_title:
        return generated_title
    return "post_gen_validate skip"


def _post_gen_validate_subject(entry: Mapping[str, Any]) -> str:
    base_subject = build_subject(_post_gen_validate_title(entry))
    if _GUARDED_PUBLISH_REVIEW_SUBJECT_RE.search(base_subject):
        return _GUARDED_PUBLISH_REVIEW_SUBJECT_RE.sub(
            _POST_GEN_VALIDATE_REVIEW_PREFIX,
            base_subject,
            count=1,
        )
    return f"{_POST_GEN_VALIDATE_REVIEW_PREFIX}{_post_gen_validate_title(entry)}"


def _post_gen_validate_source_url_hash(entry: Mapping[str, Any]) -> str:
    explicit = str(entry.get("source_url_hash") or "").strip()
    if explicit:
        return explicit
    return _hash_text(str(entry.get("source_url") or "").strip())


def _post_gen_validate_dedupe_key(entry: Mapping[str, Any]) -> str:
    source_url_hash = _post_gen_validate_source_url_hash(entry)
    skip_reason = _resolve_post_gen_validate_skip_reason(entry)
    if not source_url_hash or not skip_reason:
        return ""
    return f"{_POST_GEN_VALIDATE_RECORD_TYPE}:{source_url_hash}:{skip_reason}"


def _default_fetch(base_url: str, after_iso: str) -> list[Mapping[str, Any]]:
    endpoint = urljoin(base_url.rstrip("/") + "/", "posts")
    query = urlencode(
        {
            "status": "publish",
            "after": after_iso,
            "per_page": 20,
            "orderby": "date",
            "order": "asc",
            "_fields": "id,title,excerpt,content,link,date,status,meta,article_subtype,subtype",
        }
    )
    request = urllib.request.Request(
        f"{endpoint}?{query}",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("publish notice scan response must be a list")
    return [item for item in payload if isinstance(item, Mapping)]


def _wp_basic_auth_header() -> str:
    user = str(os.environ.get("WP_USER", "")).strip()
    app_password = str(os.environ.get("WP_APP_PASSWORD", "")).strip()
    if not user or not app_password:
        raise ValueError("WP_USER and WP_APP_PASSWORD are required for guarded publish review scan")
    token = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _default_fetch_post_detail(base_url: str, post_id: int | str) -> Mapping[str, Any] | None:
    endpoint = urljoin(base_url.rstrip("/") + "/", f"posts/{post_id}")
    query = urlencode(
        {
            "context": "edit",
            "_fields": "id,title,link,date,status,meta,article_subtype,subtype",
        }
    )
    request = urllib.request.Request(
        f"{endpoint}?{query}",
        headers={
            "Accept": "application/json",
            "Authorization": _wp_basic_auth_header(),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, Mapping) else None


def _resolve_wp_api_base(wp_api_base: str | None) -> str:
    if wp_api_base is not None and str(wp_api_base).strip():
        return str(wp_api_base).strip()
    return (
        str(os.environ.get("WP_API_BASE", "")).strip()
        or str(os.environ.get("WORDPRESS_API_BASE", "")).strip()
        or _DEFAULT_WP_API_BASE
    )


def _is_recent_duplicate(history: Mapping[str, str], post_id: int | str, *, now: datetime) -> bool:
    parsed = _parse_datetime_to_jst(history.get(str(post_id)))
    if parsed is None:
        return False
    return now - parsed <= _HISTORY_WINDOW


def _request_from_post(post: Mapping[str, Any]) -> PublishNoticeRequest:
    return PublishNoticeRequest(
        post_id=post.get("id", ""),
        title=_extract_title(post),
        canonical_url=str(post.get("link") or "").strip(),
        subtype=_extract_subtype(post),
        publish_time_iso=_isoformat_jst(post.get("date")),
        summary=_extract_summary(post),
    )


def scan_guarded_publish_history(
    *,
    guarded_publish_history_path: str | Path | None = None,
    cursor_path: str | Path | None = None,
    history_path: str | Path = "logs/publish_notice_history.json",
    queue_path: str | Path = "logs/publish_notice_queue.jsonl",
    wp_api_base: str | None = None,
    fetch_post_detail: PostDetailFetchFn | None = None,
    history: Mapping[str, str] | None = None,
    max_per_run: int | None = None,
    recent_window_hours: float | int | None = None,
    now: Callable[[], datetime] | datetime | None = None,
    recorded_at: Callable[[], datetime] | datetime | None = None,
    write_history: bool = True,
    write_cursor: bool = True,
) -> GuardedPublishHistoryScanResult:
    current_now = _coerce_now(now)
    history_file = _path(history_path)
    guarded_cursor_file = _resolve_guarded_publish_history_cursor_path(cursor_path)
    current_history = _prune_history(
        dict(history) if history is not None else _load_history(history_file),
        now=current_now,
    )
    resolved_max_per_run = _resolve_review_max_per_run(max_per_run)
    if resolved_max_per_run <= 0:
        if write_history:
            _write_history(history_file, current_history)
        return GuardedPublishHistoryScanResult(
            emitted=[],
            skipped=[],
            history_after=current_history,
            cursor_before=_read_cursor(guarded_cursor_file),
            cursor_after=_read_cursor(guarded_cursor_file),
            cursor_path=guarded_cursor_file,
            cursor_write_needed=False,
        )

    recent_window = timedelta(hours=_resolve_review_window_hours(recent_window_hours))
    guarded_history_file = _resolve_guarded_publish_history_path(guarded_publish_history_path)
    cursor_before = _read_cursor(guarded_cursor_file)
    scan_started_at = time.perf_counter()
    history_entries, scan_meta = _load_incremental_guarded_publish_entries(
        guarded_history_file,
        now=current_now,
        recent_window=recent_window,
        cursor_before=cursor_before,
    )
    parse_duration_ms = int((time.perf_counter() - scan_started_at) * 1000)
    base_url = _resolve_wp_api_base(wp_api_base)
    fetch_post_detail_fn = fetch_post_detail or _default_fetch_post_detail
    review_recorded_at = _coerce_now(
        recorded_at if recorded_at is not None else current_now + timedelta(seconds=1)
    )
    review_recorded_at_iso = review_recorded_at.isoformat()

    emitted: list[PublishNoticeRequest] = []
    skipped: list[tuple[int | str, str]] = []
    next_history = dict(current_history)
    seen_post_ids: set[str] = set()
    skipped_by_dedup = 0
    skipped_by_judgment_filter = 0
    scanned_records = 0
    hit_max_per_run = False

    for entry in history_entries:
        if len(emitted) >= resolved_max_per_run:
            hit_max_per_run = True
            break
        scanned_records += 1

        post_id = entry.get("post_id", "")
        post_key = str(post_id or "").strip()
        if not post_key:
            skipped.append(("", "REVIEW_MISSING_POST_ID"))
            continue

        judgment = _normalize_guarded_reason(entry.get("judgment"))
        hold_reason = _normalize_guarded_reason(entry.get("hold_reason"))
        status = _normalize_guarded_reason(entry.get("status"))
        if not _is_guarded_publish_review_candidate(
            judgment=judgment,
            hold_reason=hold_reason,
            status=status,
        ):
            skipped_by_judgment_filter += 1
            skipped.append((post_id, "REVIEW_EXCLUDED"))
            continue
        if post_key in seen_post_ids or _is_recent_duplicate(next_history, post_id, now=current_now):
            skipped_by_dedup += 1
            skipped.append((post_id, "REVIEW_RECENT_DUPLICATE"))
            continue

        try:
            post = fetch_post_detail_fn(base_url, post_id)
        except Exception:
            skipped.append((post_id, "REVIEW_POST_DETAIL_ERROR"))
            continue
        if not isinstance(post, Mapping):
            skipped.append((post_id, "REVIEW_POST_MISSING"))
            continue
        post_status = str(post.get("status") or "").strip().lower()
        if post_status == "publish":
            skipped.append((post_id, "REVIEW_ALREADY_PUBLISHED"))
            continue

        base_request = _request_from_post(post)
        request = PublishNoticeRequest(
            post_id=base_request.post_id,
            title=base_request.title,
            canonical_url=base_request.canonical_url,
            subtype=base_request.subtype,
            publish_time_iso=base_request.publish_time_iso
            or _isoformat_jst(_guarded_publish_entry_datetime(entry), fallback=current_now),
            summary=base_request.summary,
            is_backlog=False,
            notice_kind="review_hold",
            subject_override=_build_guarded_publish_subject(
                base_request.title,
                judgment=judgment,
                hold_reason=hold_reason,
            ),
        )
        emitted.append(request)
        seen_post_ids.add(post_key)
        next_history[post_key] = review_recorded_at_iso
        _append_queue_log(
            queue_path,
            status="queued",
            reason=hold_reason or judgment or None,
            subject=str(request.subject_override or ""),
            recipients=[],
            post_id=request.post_id,
            recorded_at_iso=review_recorded_at_iso,
        )

    cursor_after = scan_meta["cursor_before_iso"]
    if not hit_max_per_run and history_entries:
        newest_entry_dt = _guarded_publish_entry_datetime(history_entries[0])
        if newest_entry_dt is not None:
            cursor_after = newest_entry_dt.isoformat()

    if write_history:
        _write_history(history_file, next_history)
    cursor_write_needed = bool(cursor_after) and cursor_after != cursor_before
    if write_cursor and cursor_write_needed and cursor_after is not None:
        _write_cursor(guarded_cursor_file, cursor_after)

    emitted_count = len(emitted)
    other_skips = max(0, len(skipped) - skipped_by_dedup - skipped_by_judgment_filter)
    _log_event(
        "guarded_publish_history_scan_summary",
        cursor_before_iso=scan_meta["cursor_before_iso"],
        cursor_after_iso=cursor_after,
        scanned_records=scanned_records,
        skipped_by_cursor=int(scan_meta["skipped_by_cursor"]),
        skipped_by_dedup=skipped_by_dedup,
        skipped_by_judgment_filter=skipped_by_judgment_filter,
        emitted_count=emitted_count,
        file_size_bytes=int(scan_meta["file_size_bytes"]),
        parse_duration_ms=parse_duration_ms,
    )
    if emitted_count == 0:
        zero_reason = "all_skipped_by_judgment"
        if bool(scan_meta["file_empty"]):
            zero_reason = "file_empty"
        elif scanned_records == 0:
            zero_reason = "cursor_at_head" if scan_meta["cursor_before_iso"] is not None else "all_skipped_by_cursor"
        elif skipped_by_dedup >= max(skipped_by_judgment_filter, other_skips):
            zero_reason = "all_skipped_by_dedup"
        elif skipped_by_judgment_filter >= max(skipped_by_dedup, other_skips):
            zero_reason = "all_skipped_by_judgment"
        _log_event(
            "guarded_publish_history_scan_zero_emitted",
            reason=zero_reason,
            cursor_iso=cursor_after or scan_meta["cursor_before_iso"],
        )
    return GuardedPublishHistoryScanResult(
        emitted=emitted,
        skipped=skipped,
        history_after=next_history,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
        cursor_path=guarded_cursor_file,
        cursor_write_needed=cursor_write_needed,
    )


def scan_post_gen_validate_history(
    *,
    post_gen_validate_history_path: str | Path | None = None,
    cursor_path: str | Path | None = None,
    history_path: str | Path = "logs/publish_notice_history.json",
    queue_path: str | Path = "logs/publish_notice_queue.jsonl",
    history: Mapping[str, str] | None = None,
    max_per_run: int | None = None,
    recent_window_hours: float | int | None = None,
    now: Callable[[], datetime] | datetime | None = None,
    recorded_at: Callable[[], datetime] | datetime | None = None,
    write_history: bool = True,
    write_cursor: bool = True,
) -> GuardedPublishHistoryScanResult:
    current_now = _coerce_now(now)
    history_file = _path(history_path)
    post_gen_cursor_file = _resolve_post_gen_validate_history_cursor_path(cursor_path)
    current_history = _prune_history(
        dict(history) if history is not None else _load_history(history_file),
        now=current_now,
    )
    resolved_max_per_run = _resolve_review_max_per_run(max_per_run)
    if resolved_max_per_run <= 0:
        if write_history:
            _write_history(history_file, current_history)
        return GuardedPublishHistoryScanResult(
            emitted=[],
            skipped=[],
            history_after=current_history,
            cursor_before=_read_cursor(post_gen_cursor_file),
            cursor_after=_read_cursor(post_gen_cursor_file),
            cursor_path=post_gen_cursor_file,
            cursor_write_needed=False,
        )

    recent_window = timedelta(hours=_resolve_review_window_hours(recent_window_hours))
    ledger_file = _resolve_post_gen_validate_history_path(post_gen_validate_history_path)
    if (
        post_gen_validate_history_path is None
        and str(os.environ.get("PUBLISH_NOTICE_POST_GEN_VALIDATE_HISTORY_PATH", "")).strip() == ""
    ):
        _sync_post_gen_validate_history_from_gcs(ledger_file)
    if not ledger_file.exists():
        ledger_file = _POST_GEN_VALIDATE_HISTORY_FALLBACK_PATH
    cursor_before = _read_cursor(post_gen_cursor_file)
    scan_started_at = time.perf_counter()
    history_entries, scan_meta = _load_incremental_guarded_publish_entries(
        ledger_file,
        now=current_now,
        recent_window=recent_window,
        cursor_before=cursor_before,
    )
    parse_duration_ms = int((time.perf_counter() - scan_started_at) * 1000)
    review_recorded_at = _coerce_now(
        recorded_at if recorded_at is not None else current_now + timedelta(seconds=1)
    )
    review_recorded_at_iso = review_recorded_at.isoformat()

    emitted: list[PublishNoticeRequest] = []
    skipped: list[tuple[int | str, str]] = []
    next_history = dict(current_history)
    seen_dedupe_keys: set[str] = set()
    skipped_by_dedup = 0
    skipped_by_payload = 0
    scanned_records = 0
    hit_max_per_run = False

    for entry in history_entries:
        if len(emitted) >= resolved_max_per_run:
            hit_max_per_run = True
            break
        scanned_records += 1

        dedupe_key = _post_gen_validate_dedupe_key(entry)
        if not dedupe_key:
            skipped_by_payload += 1
            skipped.append(("", "POST_GEN_VALIDATE_MISSING_DEDUPE_KEY"))
            continue
        if dedupe_key in seen_dedupe_keys or _is_recent_duplicate(next_history, dedupe_key, now=current_now):
            skipped_by_dedup += 1
            skipped.append((dedupe_key, "POST_GEN_VALIDATE_RECENT_DUPLICATE"))
            continue

        source_url = str(entry.get("source_url") or "").strip()
        if not source_url:
            skipped_by_payload += 1
            skipped.append((dedupe_key, "POST_GEN_VALIDATE_MISSING_SOURCE_URL"))
            continue

        skip_reason = _resolve_post_gen_validate_skip_reason(entry)
        fail_axes = _normalize_fail_axes(entry.get("fail_axis") or entry.get("fail_axes"))
        request = PublishNoticeRequest(
            post_id=dedupe_key,
            title=_post_gen_validate_title(entry),
            canonical_url=source_url,
            subtype=str(entry.get("article_subtype") or "").strip() or "unknown",
            publish_time_iso=_isoformat_jst(_post_gen_validate_entry_datetime(entry), fallback=current_now),
            summary=None,
            is_backlog=False,
            notice_kind="post_gen_validate",
            subject_override=_post_gen_validate_subject(entry),
            source_title=str(entry.get("source_title") or "").strip() or _post_gen_validate_title(entry),
            generated_title=str(entry.get("generated_title") or entry.get("title") or "").strip(),
            skip_reason=skip_reason,
            skip_reason_label=_post_gen_validate_reason_label(skip_reason),
            source_url_hash=_post_gen_validate_source_url_hash(entry),
            category=str(entry.get("category") or "").strip() or "unknown",
            record_type=_POST_GEN_VALIDATE_RECORD_TYPE,
            skip_layer=_POST_GEN_VALIDATE_SKIP_LAYER,
            fail_axes=fail_axes,
        )
        emitted.append(request)
        seen_dedupe_keys.add(dedupe_key)
        next_history[dedupe_key] = review_recorded_at_iso
        _append_queue_log(
            queue_path,
            status="queued",
            reason=skip_reason,
            subject=str(request.subject_override or ""),
            recipients=[],
            post_id=request.post_id,
            recorded_at_iso=review_recorded_at_iso,
            extra_payload={
                "record_type": _POST_GEN_VALIDATE_RECORD_TYPE,
                "skip_layer": _POST_GEN_VALIDATE_SKIP_LAYER,
                "source_url_hash": request.source_url_hash,
            },
        )

    cursor_after = scan_meta["cursor_before_iso"]
    if not hit_max_per_run and history_entries:
        newest_entry_dt = _post_gen_validate_entry_datetime(history_entries[0])
        if newest_entry_dt is not None:
            cursor_after = newest_entry_dt.isoformat()

    if write_history:
        _write_history(history_file, next_history)
    cursor_write_needed = bool(cursor_after) and cursor_after != cursor_before
    if write_cursor and cursor_write_needed and cursor_after is not None:
        _write_cursor(post_gen_cursor_file, cursor_after)

    _log_event(
        "post_gen_validate_history_scan_summary",
        record_type=_POST_GEN_VALIDATE_RECORD_TYPE,
        skip_layer=_POST_GEN_VALIDATE_SKIP_LAYER,
        cursor_before_iso=scan_meta["cursor_before_iso"],
        cursor_after_iso=cursor_after,
        scanned_records=scanned_records,
        skipped_by_cursor=int(scan_meta["skipped_by_cursor"]),
        skipped_by_dedup=skipped_by_dedup,
        skipped_by_payload=skipped_by_payload,
        emitted_count=len(emitted),
        file_size_bytes=int(scan_meta["file_size_bytes"]),
        parse_duration_ms=parse_duration_ms,
    )
    if hit_max_per_run:
        _log_event(
            "post_gen_validate_history_scan_cap_exceeded",
            record_type=_POST_GEN_VALIDATE_RECORD_TYPE,
            skip_layer=_POST_GEN_VALIDATE_SKIP_LAYER,
            cursor_before_iso=scan_meta["cursor_before_iso"],
            cursor_after_iso=cursor_after,
            emitted_count=len(emitted),
            max_per_run=resolved_max_per_run,
        )
    if not emitted:
        zero_reason = "all_skipped_by_payload"
        other_skips = max(0, len(skipped) - skipped_by_dedup - skipped_by_payload)
        if bool(scan_meta["file_empty"]):
            zero_reason = "file_empty"
        elif scanned_records == 0:
            zero_reason = "cursor_at_head" if scan_meta["cursor_before_iso"] is not None else "all_skipped_by_cursor"
        elif skipped_by_dedup >= max(skipped_by_payload, other_skips):
            zero_reason = "all_skipped_by_dedup"
        elif skipped_by_payload >= max(skipped_by_dedup, other_skips):
            zero_reason = "all_skipped_by_payload"
        _log_event(
            "post_gen_validate_history_scan_zero_emitted",
            record_type=_POST_GEN_VALIDATE_RECORD_TYPE,
            skip_layer=_POST_GEN_VALIDATE_SKIP_LAYER,
            reason=zero_reason,
            cursor_iso=cursor_after or scan_meta["cursor_before_iso"],
        )
    return GuardedPublishHistoryScanResult(
        emitted=emitted,
        skipped=skipped,
        history_after=next_history,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
        cursor_path=post_gen_cursor_file,
        cursor_write_needed=cursor_write_needed,
    )


def scan(
    *,
    wp_api_base: str | None = None,
    cursor_path: str | Path = "logs/publish_notice_cursor.txt",
    history_path: str | Path = "logs/publish_notice_history.json",
    queue_path: str | Path = "logs/publish_notice_queue.jsonl",
    guarded_publish_history_path: str | Path | None = None,
    guarded_cursor_path: str | Path | None = None,
    post_gen_validate_history_path: str | Path | None = None,
    post_gen_validate_cursor_path: str | Path | None = None,
    fetch: FetchFn | None = None,
    now: Callable[[], datetime] | datetime | None = None,
) -> ScanResult:
    current_now = _coerce_now(now)
    cursor_file = _path(cursor_path)
    history_file = _path(history_path)
    history = _prune_history(_load_history(history_file), now=current_now)
    cursor_before = _read_cursor(cursor_file)

    if cursor_before is None:
        cursor_after = current_now.isoformat()
        _write_history(history_file, history)
        _write_cursor(cursor_file, cursor_after)
        return ScanResult(emitted=[], skipped=[], cursor_before=None, cursor_after=cursor_after)

    fetch_fn = fetch or _default_fetch
    base_url = _resolve_wp_api_base(wp_api_base)
    posts = list(fetch_fn(base_url, cursor_before))

    emitted: list[PublishNoticeRequest] = []
    skipped: list[tuple[int | str, str]] = []
    next_history = dict(history)
    seen_post_ids: set[str] = set()
    latest_post_dt: datetime | None = None
    recorded_at_iso = current_now.isoformat()

    for post in posts:
        post_status = str(post.get("status") or "").strip().lower()
        if post_status != "publish":
            continue

        post_id = post.get("id", "")
        post_key = str(post_id)
        post_dt = _parse_datetime_to_jst(post.get("date"))
        if post_dt is not None and (latest_post_dt is None or post_dt > latest_post_dt):
            latest_post_dt = post_dt

        if post_key in seen_post_ids or _is_recent_duplicate(next_history, post_id, now=current_now):
            skipped.append((post_id, "RECENT_DUPLICATE"))
            continue

        request = _request_from_post(post)
        emitted.append(request)
        seen_post_ids.add(post_key)
        next_history[post_key] = request.publish_time_iso or recorded_at_iso
        _append_queue_log(
            queue_path,
            status="queued",
            reason=None,
            subject=build_subject(request.title),
            recipients=[],
            post_id=request.post_id,
            recorded_at_iso=recorded_at_iso,
        )

    review_scan_kwargs: dict[str, Any] = {
        "history_path": history_path,
        "queue_path": queue_path,
        "wp_api_base": base_url,
        "history": next_history,
        "now": current_now,
        "recorded_at": current_now + timedelta(seconds=1),
        "write_history": False,
        "write_cursor": False,
    }
    if guarded_publish_history_path is not None:
        review_scan_kwargs["guarded_publish_history_path"] = guarded_publish_history_path
    if guarded_cursor_path is not None:
        review_scan_kwargs["cursor_path"] = guarded_cursor_path
    review_scan = scan_guarded_publish_history(**review_scan_kwargs)
    emitted.extend(review_scan.emitted)
    skipped.extend(review_scan.skipped)
    next_history = review_scan.history_after

    if _post_gen_validate_notification_enabled():
        remaining_review_cap = max(0, _resolve_review_max_per_run(None) - len(review_scan.emitted))
        post_gen_validate_scan = scan_post_gen_validate_history(
            post_gen_validate_history_path=post_gen_validate_history_path,
            cursor_path=post_gen_validate_cursor_path,
            history_path=history_path,
            queue_path=queue_path,
            history=next_history,
            max_per_run=remaining_review_cap,
            now=current_now,
            recorded_at=current_now + timedelta(seconds=2),
            write_history=False,
            write_cursor=False,
        )
        emitted.extend(post_gen_validate_scan.emitted)
        skipped.extend(post_gen_validate_scan.skipped)
        next_history = post_gen_validate_scan.history_after
    else:
        post_gen_validate_scan = GuardedPublishHistoryScanResult(
            emitted=[],
            skipped=[],
            history_after=next_history,
            cursor_write_needed=False,
        )

    cursor_after = latest_post_dt.isoformat() if latest_post_dt is not None else current_now.isoformat()
    _write_history(history_file, next_history)
    _write_cursor(cursor_file, cursor_after)
    if review_scan.cursor_write_needed and review_scan.cursor_path is not None and review_scan.cursor_after is not None:
        _write_cursor(review_scan.cursor_path, review_scan.cursor_after)
    if (
        post_gen_validate_scan.cursor_write_needed
        and post_gen_validate_scan.cursor_path is not None
        and post_gen_validate_scan.cursor_after is not None
    ):
        _write_cursor(post_gen_validate_scan.cursor_path, post_gen_validate_scan.cursor_after)
    return ScanResult(
        emitted=emitted,
        skipped=skipped,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
    )


__all__ = [
    "GuardedPublishHistoryScanResult",
    "JST",
    "ScanResult",
    "scan",
    "scan_guarded_publish_history",
    "scan_post_gen_validate_history",
]
