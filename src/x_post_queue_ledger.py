"""Queue + ledger schema helpers for X-post cloud migration ticket 173."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
QUEUE_SCHEMA_VERSION = "x_post_queue_v0"
LEDGER_SCHEMA_VERSION = "x_post_ledger_v0"
QUEUE_STATUS_QUEUED = "queued"
QUEUE_STATUS_POSTED = "posted"
QUEUE_STATUS_FAILED_RETRYABLE = "failed_retryable"
QUEUE_STATUS_FAILED_TERMINAL = "failed_terminal"
QUEUE_STATUS_EXPIRED = "expired"
QUEUE_STATUS_SKIPPED_DUPLICATE = "skipped_duplicate"
QUEUE_STATUS_SKIPPED_DAILY_CAP = "skipped_daily_cap"

_DEFAULT_TTL_SECONDS = 24 * 60 * 60
_CATEGORY_TTL_SECONDS = {
    "lineup": _DEFAULT_TTL_SECONDS,
    "postgame": _DEFAULT_TTL_SECONDS,
    "breaking": 3 * 60 * 60,
    "notice": _DEFAULT_TTL_SECONDS,
    "comment": 72 * 60 * 60,
    "evergreen": 72 * 60 * 60,
}


class QueueLockError(RuntimeError):
    """Reserved for future queue locking failures."""


class QueueWriteError(RuntimeError):
    """Raised when queue or ledger persistence fails."""


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


def _strip_html(value: Any) -> str:
    parser = _HTMLStripper()
    parser.feed(str(value or ""))
    parser.close()
    return parser.text()


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unescape(_strip_html(value or ""))).strip()


def _as_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed


def _now_jst(now: str | datetime | None = None) -> datetime:
    parsed = _parse_datetime(now)
    if parsed is None:
        return datetime.now(JST)
    return parsed.astimezone(JST)


def _read_jsonl_rows(path: str | Path) -> list[dict[str, Any]]:
    target = _as_path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise QueueWriteError(f"jsonl row must be an object: {target}:{line_no}")
            rows.append(payload)
    return rows


def _append_jsonl_row(path: str | Path, payload: dict[str, Any]) -> None:
    target = _as_path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise QueueWriteError(f"failed to append jsonl: {target}") from exc


@dataclass(frozen=True)
class XPostQueueEntry:
    queue_id: str
    candidate_hash: str
    source_post_id: int | str
    source_canonical_url: str
    title: str
    post_text: str
    post_category: str
    media_urls: tuple[str, ...] = ()
    account_id: str = "main"
    ttl: str = ""
    status: str = QUEUE_STATUS_QUEUED
    queued_at: str = ""
    scheduled_at: str = ""
    posted_at: str | None = None
    x_post_id: str | None = None
    retry_count: int = 0
    last_error_code: str | None = None
    last_error_message: str | None = None
    idempotency_key: str = ""
    schema_version: str = QUEUE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            object.__setattr__(
                self,
                "idempotency_key",
                make_idempotency_key(self.candidate_hash, self.account_id),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "queue_id": self.queue_id,
            "candidate_hash": self.candidate_hash,
            "source_post_id": self.source_post_id,
            "source_canonical_url": self.source_canonical_url,
            "title": self.title,
            "post_text": self.post_text,
            "post_category": self.post_category,
            "media_urls": list(self.media_urls),
            "account_id": self.account_id,
            "ttl": self.ttl,
            "status": self.status,
            "queued_at": self.queued_at,
            "scheduled_at": self.scheduled_at,
            "posted_at": self.posted_at,
            "x_post_id": self.x_post_id,
            "retry_count": self.retry_count,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "XPostQueueEntry":
        return cls(
            schema_version=str(payload.get("schema_version") or QUEUE_SCHEMA_VERSION),
            queue_id=str(payload.get("queue_id") or ""),
            candidate_hash=str(payload.get("candidate_hash") or ""),
            source_post_id=payload.get("source_post_id") or "",
            source_canonical_url=str(payload.get("source_canonical_url") or ""),
            title=str(payload.get("title") or ""),
            post_text=str(payload.get("post_text") or ""),
            post_category=str(payload.get("post_category") or ""),
            media_urls=tuple(str(item) for item in payload.get("media_urls") or ()),
            account_id=str(payload.get("account_id") or "main"),
            ttl=str(payload.get("ttl") or ""),
            status=str(payload.get("status") or QUEUE_STATUS_QUEUED),
            queued_at=str(payload.get("queued_at") or ""),
            scheduled_at=str(payload.get("scheduled_at") or ""),
            posted_at=str(payload["posted_at"]) if payload.get("posted_at") not in (None, "") else None,
            x_post_id=str(payload["x_post_id"]) if payload.get("x_post_id") not in (None, "") else None,
            retry_count=int(payload.get("retry_count") or 0),
            last_error_code=(
                str(payload["last_error_code"]) if payload.get("last_error_code") not in (None, "") else None
            ),
            last_error_message=(
                str(payload["last_error_message"]) if payload.get("last_error_message") not in (None, "") else None
            ),
            idempotency_key=str(payload.get("idempotency_key") or ""),
        )


@dataclass(frozen=True)
class XPostLedgerEntry:
    run_id: str
    queue_id: str
    account_id: str
    status: str
    x_post_id: str | None
    x_user_id: str | None
    started_at: str
    finished_at: str
    rate_limit_remaining: int | None = None
    rate_limit_reset: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    schema_version: str = LEDGER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "queue_id": self.queue_id,
            "account_id": self.account_id,
            "status": self.status,
            "x_post_id": self.x_post_id,
            "x_user_id": self.x_user_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_reset": self.rate_limit_reset,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "XPostLedgerEntry":
        return cls(
            schema_version=str(payload.get("schema_version") or LEDGER_SCHEMA_VERSION),
            run_id=str(payload.get("run_id") or ""),
            queue_id=str(payload.get("queue_id") or ""),
            account_id=str(payload.get("account_id") or ""),
            status=str(payload.get("status") or ""),
            x_post_id=str(payload["x_post_id"]) if payload.get("x_post_id") not in (None, "") else None,
            x_user_id=str(payload["x_user_id"]) if payload.get("x_user_id") not in (None, "") else None,
            started_at=str(payload.get("started_at") or ""),
            finished_at=str(payload.get("finished_at") or ""),
            rate_limit_remaining=(
                int(payload["rate_limit_remaining"])
                if payload.get("rate_limit_remaining") not in (None, "")
                else None
            ),
            rate_limit_reset=(
                str(payload["rate_limit_reset"]) if payload.get("rate_limit_reset") not in (None, "") else None
            ),
            error_code=str(payload["error_code"]) if payload.get("error_code") not in (None, "") else None,
            error_message=(
                str(payload["error_message"]) if payload.get("error_message") not in (None, "") else None
            ),
        )


class QueueWriter(ABC):
    @abstractmethod
    def append(self, entry: XPostQueueEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_entries(self) -> list[XPostQueueEntry]:
        raise NotImplementedError


class LedgerWriter(ABC):
    @abstractmethod
    def append(self, entry: XPostLedgerEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_entries(self) -> list[XPostLedgerEntry]:
        raise NotImplementedError


class JsonlQueueWriter(QueueWriter):
    def __init__(self, path: str | Path) -> None:
        self.path = _as_path(path)

    def append(self, entry: XPostQueueEntry) -> None:
        _append_jsonl_row(self.path, entry.to_dict())

    def read_entries(self) -> list[XPostQueueEntry]:
        return [XPostQueueEntry.from_mapping(row) for row in _read_jsonl_rows(self.path)]


class JsonlLedgerWriter(LedgerWriter):
    def __init__(self, path: str | Path) -> None:
        self.path = _as_path(path)

    def append(self, entry: XPostLedgerEntry) -> None:
        _append_jsonl_row(self.path, entry.to_dict())

    def read_entries(self) -> list[XPostLedgerEntry]:
        return [XPostLedgerEntry.from_mapping(row) for row in _read_jsonl_rows(self.path)]


class FirestoreQueueWriter(QueueWriter):
    """Firestore stub adapter: keeps writes in memory and never opens a connection."""

    def __init__(self, client: Any, collection: str) -> None:
        self.client = client
        self.collection = str(collection)
        self._buffer: list[XPostQueueEntry] = []

    def append(self, entry: XPostQueueEntry) -> None:
        self._buffer.append(entry)

    def read_entries(self) -> list[XPostQueueEntry]:
        return list(self._buffer)


class FirestoreLedgerWriter(LedgerWriter):
    """Firestore stub adapter: keeps writes in memory and never opens a connection."""

    def __init__(self, client: Any, collection: str) -> None:
        self.client = client
        self.collection = str(collection)
        self._buffer: list[XPostLedgerEntry] = []

    def append(self, entry: XPostLedgerEntry) -> None:
        self._buffer.append(entry)

    def read_entries(self) -> list[XPostLedgerEntry]:
        return list(self._buffer)


def compute_candidate_hash(post_id: int | str, canonical_url: str, body_excerpt: str) -> str:
    normalized = "\n".join(
        [
            str(post_id).strip(),
            str(canonical_url or "").strip(),
            _normalize_text(body_excerpt),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def make_idempotency_key(candidate_hash: str, account_id: str) -> str:
    return f"{str(candidate_hash).strip()}:{str(account_id).strip()}"


def judge_dedup(queue_writer: QueueWriter, ledger_writer: LedgerWriter, key: str) -> str:
    normalized = str(key).strip()
    for entry in queue_writer.read_entries():
        if entry.idempotency_key == normalized:
            return "duplicate"
    for entry in ledger_writer.read_entries():
        if entry.status == QUEUE_STATUS_POSTED and entry.queue_id == normalized:
            return "duplicate"
    return "ok"


def judge_daily_cap(
    ledger_writer: LedgerWriter,
    account_id: str,
    cap: int,
    breaking_excluded: bool = False,
    *,
    category: str | None = None,
    now: str | datetime | None = None,
) -> str:
    if int(cap) < 0:
        raise ValueError("cap must be >= 0")
    if breaking_excluded and str(category or "").strip().lower() == "breaking":
        return "ok"

    current_day = _now_jst(now).date()
    posted_today = 0
    for entry in ledger_writer.read_entries():
        if entry.account_id != account_id or entry.status != QUEUE_STATUS_POSTED:
            continue
        finished_at = _parse_datetime(entry.finished_at) or _parse_datetime(entry.started_at)
        if finished_at is None:
            continue
        if finished_at.astimezone(JST).date() == current_day:
            posted_today += 1

    return QUEUE_STATUS_SKIPPED_DAILY_CAP if posted_today >= int(cap) else "ok"


def judge_ttl_expired(entry: XPostQueueEntry | Mapping[str, Any], now: str | datetime | None) -> bool:
    ttl_value = entry.ttl if isinstance(entry, XPostQueueEntry) else str(entry.get("ttl") or "")
    ttl_dt = _parse_datetime(ttl_value)
    if ttl_dt is None:
        raise ValueError("entry ttl must be ISO8601")
    return _now_jst(now) > ttl_dt.astimezone(JST)


def default_ttl_seconds(category: str | None) -> int:
    return _CATEGORY_TTL_SECONDS.get(str(category or "").strip().lower(), _DEFAULT_TTL_SECONDS)


__all__ = [
    "FirestoreLedgerWriter",
    "FirestoreQueueWriter",
    "JST",
    "JsonlLedgerWriter",
    "JsonlQueueWriter",
    "LedgerWriter",
    "LEDGER_SCHEMA_VERSION",
    "QUEUE_SCHEMA_VERSION",
    "QUEUE_STATUS_EXPIRED",
    "QUEUE_STATUS_FAILED_RETRYABLE",
    "QUEUE_STATUS_FAILED_TERMINAL",
    "QUEUE_STATUS_POSTED",
    "QUEUE_STATUS_QUEUED",
    "QUEUE_STATUS_SKIPPED_DAILY_CAP",
    "QUEUE_STATUS_SKIPPED_DUPLICATE",
    "QueueLockError",
    "QueueWriteError",
    "QueueWriter",
    "XPostLedgerEntry",
    "XPostQueueEntry",
    "compute_candidate_hash",
    "default_ttl_seconds",
    "judge_daily_cap",
    "judge_dedup",
    "judge_ttl_expired",
    "make_idempotency_key",
]
