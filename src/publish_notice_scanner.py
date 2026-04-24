"""Independent publish scanner for ticket 076 publish notice mail."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import html
import json
import os
from pathlib import Path
import re
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
_HISTORY_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class ScanResult:
    emitted: list[PublishNoticeRequest]
    skipped: list[tuple[int | str, str]]
    cursor_before: str | None
    cursor_after: str


FetchFn = Callable[[str, str], list[Mapping[str, Any]]]


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


def _extract_subtype(post: Mapping[str, Any]) -> str:
    meta = post.get("meta")
    if isinstance(meta, Mapping):
        subtype = str(meta.get("article_subtype") or meta.get("subtype") or "").strip().lower()
        if subtype:
            return subtype
    for key in ("article_subtype", "subtype"):
        subtype = str(post.get(key) or "").strip().lower()
        if subtype:
            return subtype
    return "unknown"


def _append_queue_log(
    queue_path: str | Path,
    *,
    status: str,
    reason: str | None,
    subject: str,
    recipients: list[str],
    post_id: int | str,
    recorded_at_iso: str,
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
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


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


def scan(
    *,
    wp_api_base: str | None = None,
    cursor_path: str | Path = "logs/publish_notice_cursor.txt",
    history_path: str | Path = "logs/publish_notice_history.json",
    queue_path: str | Path = "logs/publish_notice_queue.jsonl",
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

    cursor_after = latest_post_dt.isoformat() if latest_post_dt is not None else current_now.isoformat()
    _write_history(history_file, next_history)
    _write_cursor(cursor_file, cursor_after)
    return ScanResult(
        emitted=emitted,
        skipped=skipped,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
    )


__all__ = [
    "JST",
    "ScanResult",
    "scan",
]
