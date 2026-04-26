"""Common repair-provider ledger schema and local writers."""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "repair_ledger_v0"
JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DIR = ROOT / "logs" / "repair_provider_ledger"
ENV_LEDGER_DIR = "REPAIR_PROVIDER_LEDGER_DIR"
_LOCK_DIRNAME = ".locks"
_ALLOWED_PROVIDERS = frozenset({"gemini", "codex", "openai_api"})
_ALLOWED_STATUSES = frozenset({"success", "failed", "skipped", "shadow_only"})
_REQUIRED_METRICS_KEYS = (
    "input_tokens",
    "output_tokens",
    "latency_ms",
    "body_len_before",
    "body_len_after",
    "body_len_delta_pct",
)
_REQUIRED_PROVIDER_META_KEYS = (
    "raw_response_size",
    "fallback_from",
    "fallback_reason",
    "quality_flags",
)


class LedgerLockError(RuntimeError):
    """Raised when a ledger write cannot acquire a unique idempotency lock."""


class LedgerWriteError(RuntimeError):
    """Raised when a ledger sink cannot persist an entry."""


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _canonicalize_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _ensure_iso8601(label: str, value: str) -> None:
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO8601: {value!r}") from exc


def _ensure_required_mapping_keys(label: str, payload: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ValueError(f"{label} missing required keys: {missing}")


def resolve_jsonl_ledger_dir(override: str | Path | None = None) -> Path:
    if override is not None and str(override).strip():
        return Path(override)
    env_value = os.getenv(ENV_LEDGER_DIR, "").strip()
    if env_value:
        return Path(env_value)
    return DEFAULT_LEDGER_DIR


def resolve_jsonl_ledger_path(
    *,
    now: datetime | None = None,
    sink_dir: str | Path | None = None,
) -> Path:
    current = _now_jst(now)
    return resolve_jsonl_ledger_dir(sink_dir) / f"{current.date().isoformat()}.jsonl"


def compute_input_hash(post: Any) -> str:
    return hashlib.sha256(_canonicalize_json(post).encode("utf-8")).hexdigest()


def compute_output_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def make_idempotency_key(post_id: int, input_hash: str, provider: str) -> str:
    return f"{post_id}:{input_hash}:{provider}"


def compute_body_len_delta_pct(body_len_before: int, body_len_after: int) -> float:
    if body_len_before <= 0:
        if body_len_after <= 0:
            return 0.0
        return 1.0
    return (body_len_after - body_len_before) / body_len_before


@dataclass
class RepairLedgerEntry:
    schema_version: str
    run_id: str
    lane: str
    provider: str
    model: str
    source_post_id: int
    input_hash: str
    output_hash: str
    artifact_uri: str
    status: str
    strict_pass: bool
    error_code: str | None
    idempotency_key: str
    created_at: str
    started_at: str
    finished_at: str
    metrics: dict[str, Any]
    provider_meta: dict[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {SCHEMA_VERSION!r}; got {self.schema_version!r}"
            )
        if self.provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"unsupported provider: {self.provider!r}")
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError(f"unsupported status: {self.status!r}")
        _ensure_iso8601("created_at", self.created_at)
        _ensure_iso8601("started_at", self.started_at)
        _ensure_iso8601("finished_at", self.finished_at)
        _ensure_required_mapping_keys("metrics", self.metrics, _REQUIRED_METRICS_KEYS)
        _ensure_required_mapping_keys(
            "provider_meta",
            self.provider_meta,
            _REQUIRED_PROVIDER_META_KEYS,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "lane": self.lane,
            "provider": self.provider,
            "model": self.model,
            "source_post_id": self.source_post_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "artifact_uri": self.artifact_uri,
            "status": self.status,
            "strict_pass": self.strict_pass,
            "error_code": self.error_code,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metrics": dict(self.metrics),
            "provider_meta": dict(self.provider_meta),
        }


def judge_strict_pass(
    entry: RepairLedgerEntry,
    hard_stop_flags_resolved: bool,
    fact_check_pass: bool,
    no_new_forbidden: bool,
    body_len_delta_pct: float,
) -> bool:
    json_schema_valid = isinstance(entry, RepairLedgerEntry)
    if json_schema_valid:
        try:
            entry.to_dict()
        except ValueError:
            json_schema_valid = False
    return bool(
        json_schema_valid
        and hard_stop_flags_resolved
        and fact_check_pass
        and no_new_forbidden
        and -0.20 <= body_len_delta_pct <= 0.35
    )


@contextmanager
def with_lock(
    idempotency_key: str,
    *,
    lock_dir: str | Path | None = None,
) -> Iterator[Path]:
    lock_root = Path(lock_dir) if lock_dir is not None else DEFAULT_LEDGER_DIR / _LOCK_DIRNAME
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_name = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    lock_path = lock_root / f"{lock_name}.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LedgerLockError(f"duplicate idempotency lock: {idempotency_key}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(idempotency_key)
            handle.write("\n")
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


class LedgerWriter(ABC):
    @abstractmethod
    def write(self, entry: RepairLedgerEntry) -> None:
        """Persist a repair ledger entry."""


class JsonlLedgerWriter(LedgerWriter):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _lock_dir(self) -> Path:
        return self.path.parent / _LOCK_DIRNAME

    def _check_duplicate(self, idempotency_key: str) -> None:
        if not self.path.exists():
            return
        line_no = 0
        try:
            with self.path.open(encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    text = line.strip()
                    if not text:
                        continue
                    payload = json.loads(text)
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("idempotency_key") == idempotency_key:
                        raise LedgerLockError(f"duplicate idempotency_key: {idempotency_key}")
        except LedgerLockError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerWriteError(f"failed to inspect {self.path}:{line_no}") from exc

    def write(self, entry: RepairLedgerEntry) -> None:
        payload = entry.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with with_lock(entry.idempotency_key, lock_dir=self._lock_dir()):
            self._check_duplicate(entry.idempotency_key)
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False))
                    handle.write("\n")
            except OSError as exc:
                raise LedgerWriteError(f"failed to append ledger row: {self.path}") from exc


class FirestoreLedgerWriter(LedgerWriter):
    """Stub adapter for the future Firestore-backed ledger."""

    def __init__(self, client: Any, collection: str) -> None:
        self.client = client
        self.collection = collection

    def write(self, entry: RepairLedgerEntry) -> None:
        payload = entry.to_dict()
        try:
            collection_ref = self.client.collection(self.collection)
            document_ref = collection_ref.document(entry.idempotency_key)
            document_ref.set(payload)
        except Exception as exc:  # pragma: no cover - exercised through mocks
            raise LedgerWriteError(
                f"failed to write Firestore ledger entry: {self.collection}"
            ) from exc


__all__ = [
    "DEFAULT_LEDGER_DIR",
    "ENV_LEDGER_DIR",
    "FirestoreLedgerWriter",
    "JST",
    "JsonlLedgerWriter",
    "LedgerLockError",
    "LedgerWriteError",
    "LedgerWriter",
    "RepairLedgerEntry",
    "SCHEMA_VERSION",
    "compute_body_len_delta_pct",
    "compute_input_hash",
    "compute_output_hash",
    "judge_strict_pass",
    "make_idempotency_key",
    "resolve_jsonl_ledger_dir",
    "resolve_jsonl_ledger_path",
    "with_lock",
]
