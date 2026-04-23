"""WP publish polling trigger for ticket 061-P1.2."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlencode, urljoin
import urllib.request

from src.x_published_poster import (
    PostPayload,
    PublishedArticle,
    build_post,
    generate_teaser,
    load_post_history,
    save_post_history,
    validate_post,
)


_WP_FIELDS = "id,title,excerpt,content,link,date,status"
_PARAGRAPH_PATTERN = re.compile(r"<p\b[^>]*>.*?</p>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ScanResult:
    detected: int
    ok: int
    skipped: list[tuple[str | int, str]]
    new_cursor: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_since_iso(now: datetime | None = None) -> str:
    base_time = now or _utc_now()
    return (base_time - timedelta(hours=24)).isoformat()


def _extract_rendered(value: Any) -> str:
    if isinstance(value, Mapping):
        rendered = value.get("rendered")
        if rendered is not None:
            return str(rendered)
    if value is None:
        return ""
    return str(value)


def _extract_first_paragraph(value: str) -> str:
    match = _PARAGRAPH_PATTERN.search(str(value or ""))
    if match:
        return match.group(0)
    return str(value or "")


def _published_at_to_iso(value: str | datetime | None, fallback: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    text = str(value or "").strip()
    return text or fallback


def _response_header(headers: Any, name: str) -> str | None:
    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is not None:
            return str(value)
        lower_name = name.lower()
        value = headers.get(lower_name)
        if value is not None:
            return str(value)
    return None


def fetch_published_since_wp(
    base_url: str,
    since_iso: str,
    per_page: int = 20,
    timeout: int = 30,
) -> list[PublishedArticle]:
    endpoint = urljoin(base_url.rstrip("/") + "/", "wp-json/wp/v2/posts")
    page = 1
    articles: list[PublishedArticle] = []

    while True:
        query = urlencode(
            {
                "status": "publish",
                "after": since_iso,
                "per_page": per_page,
                "orderby": "date",
                "order": "asc",
                "_fields": _WP_FIELDS,
                "page": page,
            }
        )
        request = urllib.request.Request(f"{endpoint}?{query}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = getattr(response, "headers", {})

        if not isinstance(payload, list):
            raise ValueError("WP posts response must be a list")

        for item in payload:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("status") or "").strip().lower() != "publish":
                continue
            articles.append(
                PublishedArticle(
                    article_id=item.get("id") or "",
                    title=_extract_rendered(item.get("title")),
                    excerpt=_extract_rendered(item.get("excerpt")),
                    body_first_paragraph=_extract_first_paragraph(_extract_rendered(item.get("content"))),
                    canonical_url=str(item.get("link") or ""),
                    published_at=item.get("date"),
                    post_status=str(item.get("status") or ""),
                )
            )

        if len(payload) < per_page:
            break

        total_pages = _response_header(headers, "X-WP-TotalPages")
        if total_pages is not None:
            try:
                if page >= int(total_pages):
                    break
            except ValueError:
                pass
        page += 1

    return articles


def load_cursor(cursor_path: Path) -> str | None:
    if not cursor_path.exists():
        return None
    value = cursor_path.read_text(encoding="utf-8").strip()
    return value or None


def save_cursor(cursor_path: Path, iso: str) -> None:
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{cursor_path}.tmp")
    tmp_path.write_text(f"{iso}\n", encoding="utf-8")
    os.replace(tmp_path, cursor_path)


def append_queue(queue_path: Path, payload: PostPayload) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "article_id": payload.article_id,
        "teaser": payload.teaser,
        "canonical_url": payload.canonical_url,
        "text": payload.text,
        "published_at": payload.published_at.isoformat(),
        "queued_at": _utc_now().isoformat(),
    }
    with queue_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def scan_and_queue(
    fetch_fn: Callable[[str], list[PublishedArticle]],
    cursor_path: str | Path,
    queue_path: str | Path,
    history_path: str | Path | None,
) -> ScanResult:
    now = _utc_now()
    cursor_file = Path(cursor_path)
    queue_file = Path(queue_path)
    current_cursor = load_cursor(cursor_file) or _default_since_iso(now)
    history = load_post_history(history_path)

    articles = list(fetch_fn(current_cursor))
    skipped: list[tuple[str | int, str]] = []
    accepted = 0

    for article in articles:
        payload = build_post(article, post_history=history, now=now)
        if payload is None:
            teaser = generate_teaser(article)
            validation = validate_post(
                article,
                teaser,
                article.canonical_url,
                post_history=history,
                now=now,
            )
            skipped.append((article.article_id, validation.hard_fail_code or "UNKNOWN"))
            continue

        append_queue(queue_file, payload)
        history[str(payload.article_id)] = payload.published_at.isoformat()
        accepted += 1

    if history_path is not None:
        save_post_history(history_path, history)

    new_cursor = current_cursor
    if articles:
        new_cursor = _published_at_to_iso(articles[-1].published_at, current_cursor)
    save_cursor(cursor_file, new_cursor)

    return ScanResult(
        detected=len(articles),
        ok=accepted,
        skipped=skipped,
        new_cursor=new_cursor,
    )


__all__ = [
    "ScanResult",
    "append_queue",
    "fetch_published_since_wp",
    "load_cursor",
    "save_cursor",
    "scan_and_queue",
]
