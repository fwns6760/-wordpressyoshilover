"""Pure Python published-article post builder for ticket 061-P1.1."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit


EXCERPT_MIN_LENGTH = 40
TEASER_MIN_LENGTH = 10
TEASER_MAX_LENGTH = 120
RECENT_DUPLICATE_WINDOW = timedelta(hours=24)
MAX_PUBLISHED_AGE = timedelta(days=365 * 2)

HARD_FAIL_POST_STATUS = "HARD_FAIL_POST_STATUS"
HARD_FAIL_CANONICAL_MISSING = "HARD_FAIL_CANONICAL_MISSING"
HARD_FAIL_CANONICAL_PREVIEW = "HARD_FAIL_CANONICAL_PREVIEW"
HARD_FAIL_TEASER_GENERIC = "HARD_FAIL_TEASER_GENERIC"
HARD_FAIL_TEASER_BANNED = "HARD_FAIL_TEASER_BANNED"
HARD_FAIL_TEASER_LENGTH = "HARD_FAIL_TEASER_LENGTH"
HARD_FAIL_PUBLISHED_AT_RANGE = "HARD_FAIL_PUBLISHED_AT_RANGE"
HARD_FAIL_DUPLICATE_24H = "HARD_FAIL_DUPLICATE_24H"

_BANNED_LITERAL_PHRASES = (
    "どう見る",
    "本音",
    "思い",
    "語る",
    "コメントまとめ",
    "試合後コメント",
    "ドラ1コンビ",
    "X をどう見る",
    "X がコメント",
    "X について語る",
    "注目したい",
    "振り返りたい",
    "コメントに注目",
    "コメントから見えるもの",
    "選手コメントを読む",
    "史上最高",
    "圧倒的",
    "神",
    "ヤバい",
    "優勝確定",
    "間違いなく",
    "断言",
)

_BANNED_REGEX_PATTERNS = (
    (re.compile(r".+と判明"), "〜と判明"),
    (re.compile(r".+が決定"), "〜が決定"),
    (re.compile(r".+が確定"), "〜が確定"),
    (re.compile(r"(?:か|なのか|とは)[?？]$"), "煽り疑問形"),
)

_CANONICAL_DENY_PATTERNS = (
    re.compile(r"(?:\?|&)preview(?:=|&|$)", re.IGNORECASE),
    re.compile(r"preview_(?:id|nonce)=", re.IGNORECASE),
    re.compile(r"(?:\?|&)status=(?:draft|private)(?:&|$)", re.IGNORECASE),
    re.compile(r"(?:\?|&)p=\d+(?:&|$)", re.IGNORECASE),
    re.compile(r"_private", re.IGNORECASE),
    re.compile(r"/draft(?:/|$)", re.IGNORECASE),
)

_PREFERRED_TRIM_CHARS = "。！？!?」』）)]"
_SECONDARY_TRIM_CHARS = "、,， "


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def text(self) -> str:
        return "".join(self._parts)


@dataclass(frozen=True)
class PublishedArticle:
    article_id: str | int
    title: str
    excerpt: str
    body_first_paragraph: str
    canonical_url: str
    published_at: str | datetime | None
    post_status: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PublishedArticle":
        return cls(
            article_id=payload.get("article_id") or payload.get("post_id") or payload.get("id") or "",
            title=str(payload.get("title") or ""),
            excerpt=str(payload.get("excerpt") or payload.get("post_excerpt") or ""),
            body_first_paragraph=str(payload.get("body_first_paragraph") or payload.get("body") or ""),
            canonical_url=str(payload.get("canonical_url") or payload.get("url") or payload.get("link") or ""),
            published_at=payload.get("published_at") or payload.get("date") or payload.get("date_gmt"),
            post_status=str(payload.get("post_status") or payload.get("status") or ""),
        )


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    hard_fail_code: str | None = None
    matched_banned_phrases: tuple[str, ...] = ()


@dataclass(frozen=True)
class PostPayload:
    article_id: str | int
    teaser: str
    canonical_url: str
    text: str
    published_at: datetime


def _strip_html(value: str) -> str:
    parser = _HTMLStripper()
    parser.feed(str(value or ""))
    parser.close()
    return parser.text()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(_strip_html(value or ""))).strip()


def _normalize_url(value: str | None) -> str:
    return str(value or "").strip()


def _trim_paragraph(value: str, *, min_length: int = EXCERPT_MIN_LENGTH, max_length: int = TEASER_MAX_LENGTH) -> str:
    text = _normalize_text(value)
    if len(text) <= max_length:
        return text

    window = text[:max_length].rstrip()
    for charset in (_PREFERRED_TRIM_CHARS, _SECONDARY_TRIM_CHARS):
        best_index = -1
        for char in charset:
            position = window.rfind(char)
            if position >= min_length - 1:
                best_index = max(best_index, position)
        if best_index >= 0:
            trimmed = window[: best_index + 1].rstrip()
            if len(trimmed) >= min_length:
                return trimmed
    return window


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _current_time(now: str | datetime | None = None) -> datetime:
    return _parse_datetime(now) or datetime.now(timezone.utc)


def _is_private_ipv4(hostname: str) -> bool:
    parts = hostname.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        return False
    octets = [int(part) for part in parts]
    if octets[0] == 10:
        return True
    if octets[0] == 127:
        return True
    if octets[0] == 192 and octets[1] == 168:
        return True
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    return False


def _is_internal_hostname(hostname: str | None) -> bool:
    if not hostname:
        return True
    host = hostname.lower()
    if host in {"localhost", "internal", "intranet"}:
        return True
    if host.endswith((".local", ".internal", ".lan", ".corp")):
        return True
    if _is_private_ipv4(host):
        return True
    return False


def _canonical_url_is_allowed(url: str) -> bool:
    if not url:
        return False
    if any(pattern.search(url) for pattern in _CANONICAL_DENY_PATTERNS):
        return False
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        return False
    if _is_internal_hostname(parsed.hostname):
        return False
    return True


def find_banned_phrases(teaser: str | None) -> tuple[str, ...]:
    text = str(teaser or "").strip()
    if not text:
        return ()
    hits: list[str] = []
    for phrase in _BANNED_LITERAL_PHRASES:
        if phrase in text:
            hits.append(phrase)
    for pattern, label in _BANNED_REGEX_PATTERNS:
        if pattern.search(text):
            hits.append(label)
    seen: set[str] = set()
    ordered: list[str] = []
    for hit in hits:
        if hit in seen:
            continue
        seen.add(hit)
        ordered.append(hit)
    return tuple(ordered)


def generate_teaser(article: PublishedArticle) -> str | None:
    excerpt = _normalize_text(article.excerpt)
    if EXCERPT_MIN_LENGTH <= len(excerpt) <= TEASER_MAX_LENGTH:
        return excerpt

    first_paragraph = _trim_paragraph(article.body_first_paragraph)
    if EXCERPT_MIN_LENGTH <= len(first_paragraph) <= TEASER_MAX_LENGTH:
        return first_paragraph

    title = _normalize_text(article.title)
    if TEASER_MIN_LENGTH <= len(title) <= TEASER_MAX_LENGTH:
        return title
    return None


def _history_contains_recent_article(
    article_id: str | int,
    post_history: Mapping[str, str | datetime | None] | Iterable[str] | None,
    *,
    now: datetime,
) -> bool:
    if not post_history:
        return False

    article_key = str(article_id)
    if isinstance(post_history, Mapping):
        raw_value = post_history.get(article_key)
        if raw_value is None and article_id != article_key:
            raw_value = post_history.get(article_id)
        if raw_value is None:
            return False
        posted_at = _parse_datetime(raw_value)
        if posted_at is None:
            return True
        return now - posted_at <= RECENT_DUPLICATE_WINDOW

    return article_key in {str(item) for item in post_history}


def validate_post(
    article: PublishedArticle,
    teaser: str | None,
    canonical_url: str | None,
    *,
    post_history: Mapping[str, str | datetime | None] | Iterable[str] | None = None,
    now: str | datetime | None = None,
) -> ValidationResult:
    if str(article.post_status or "").strip().lower() != "publish":
        return ValidationResult(ok=False, hard_fail_code=HARD_FAIL_POST_STATUS)

    normalized_url = _normalize_url(canonical_url)
    if not normalized_url:
        return ValidationResult(ok=False, hard_fail_code=HARD_FAIL_CANONICAL_MISSING)
    if not _canonical_url_is_allowed(normalized_url):
        return ValidationResult(ok=False, hard_fail_code=HARD_FAIL_CANONICAL_PREVIEW)

    if teaser is None:
        return ValidationResult(ok=False, hard_fail_code=HARD_FAIL_TEASER_GENERIC)

    banned_hits = find_banned_phrases(teaser)
    if banned_hits:
        return ValidationResult(
            ok=False,
            hard_fail_code=HARD_FAIL_TEASER_BANNED,
            matched_banned_phrases=banned_hits,
        )

    teaser_length = len(teaser)
    if teaser_length < TEASER_MIN_LENGTH or teaser_length > TEASER_MAX_LENGTH:
        return ValidationResult(ok=False, hard_fail_code=HARD_FAIL_TEASER_LENGTH)

    published_at = _parse_datetime(article.published_at)
    current_time = _current_time(now)
    if published_at is None or published_at > current_time or current_time - published_at > MAX_PUBLISHED_AGE:
        return ValidationResult(ok=False, hard_fail_code=HARD_FAIL_PUBLISHED_AT_RANGE)

    if _history_contains_recent_article(article.article_id, post_history, now=current_time):
        return ValidationResult(ok=False, hard_fail_code=HARD_FAIL_DUPLICATE_24H)

    return ValidationResult(ok=True)


def build_post(
    article: PublishedArticle,
    *,
    post_history: Mapping[str, str | datetime | None] | Iterable[str] | None = None,
    now: str | datetime | None = None,
) -> PostPayload | None:
    teaser = generate_teaser(article)
    validation = validate_post(
        article,
        teaser,
        article.canonical_url,
        post_history=post_history,
        now=now,
    )
    if not validation.ok or teaser is None:
        return None

    published_at = _parse_datetime(article.published_at)
    if published_at is None:
        return None

    canonical_url = _normalize_url(article.canonical_url)
    return PostPayload(
        article_id=article.article_id,
        teaser=teaser,
        canonical_url=canonical_url,
        text=f"{teaser}\n{canonical_url}",
        published_at=published_at,
    )


def load_post_history(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    history_path = Path(path)
    if not history_path.exists():
        return {}

    payload = json.loads(history_path.read_text(encoding="utf-8"))
    history: dict[str, str] = {}
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            history[str(key)] = str(value)
        return history
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            article_id = item.get("article_id") or item.get("post_id") or item.get("id")
            posted_at = item.get("posted_at") or item.get("published_at")
            if article_id is None or posted_at in (None, ""):
                continue
            history[str(article_id)] = str(posted_at)
        return history
    raise ValueError("history file must be a JSON object or list")


def save_post_history(path: str | Path, history: Mapping[str, str]) -> None:
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(dict(sorted(history.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def record_post_history(
    path: str | Path | None,
    history: dict[str, str],
    article_id: str | int,
    *,
    posted_at: str | datetime | None = None,
) -> None:
    history[str(article_id)] = (_parse_datetime(posted_at) or datetime.now(timezone.utc)).isoformat()
    if path is not None:
        save_post_history(path, history)


__all__ = [
    "EXCERPT_MIN_LENGTH",
    "HARD_FAIL_CANONICAL_MISSING",
    "HARD_FAIL_CANONICAL_PREVIEW",
    "HARD_FAIL_DUPLICATE_24H",
    "HARD_FAIL_POST_STATUS",
    "HARD_FAIL_PUBLISHED_AT_RANGE",
    "HARD_FAIL_TEASER_BANNED",
    "HARD_FAIL_TEASER_GENERIC",
    "HARD_FAIL_TEASER_LENGTH",
    "PostPayload",
    "PublishedArticle",
    "RECENT_DUPLICATE_WINDOW",
    "TEASER_MAX_LENGTH",
    "TEASER_MIN_LENGTH",
    "ValidationResult",
    "build_post",
    "find_banned_phrases",
    "generate_teaser",
    "load_post_history",
    "record_post_history",
    "save_post_history",
    "validate_post",
]
