"""Common repair-provider ledger schema and local writers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests


SCHEMA_VERSION = "repair_ledger_v0"
JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DIR = ROOT / "logs" / "repair_provider_ledger"
ENV_LEDGER_DIR = "REPAIR_PROVIDER_LEDGER_DIR"
DEFAULT_PROJECT_ID = "baseballsite"
DEFAULT_FIRESTORE_COLLECTION = "repair_ledger"
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


class _FirestoreAPIError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = int(status_code)
        self.detail = str(detail)
        super().__init__(f"firestore api failed({self.status_code}): {self.detail}")


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


def _default_project_id() -> str:
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "PROJECT_ID"):
        value = str(os.environ.get(key, "")).strip()
        if value:
            return value
    return DEFAULT_PROJECT_ID


def _decode_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _firestore_document_id(idempotency_key: str) -> str:
    return hashlib.sha256(str(idempotency_key).encode("utf-8")).hexdigest()


def _firestore_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_firestore_value(item) for item in value]}}
    if isinstance(value, dict):
        return {
            "mapValue": {
                "fields": {
                    str(key): _firestore_value(item)
                    for key, item in value.items()
                }
            }
        }
    return {"stringValue": str(value)}


def _firestore_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _firestore_value(value) for key, value in payload.items()}


def _firestore_error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("status")
            if message:
                return str(message)
    text = _decode_text(getattr(response, "text", "")).strip()
    return text or f"http {response.status_code}"


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
    """Firestore-backed repair ledger writer with idempotency locks."""

    def __init__(
        self,
        project_id: str | Any | None = None,
        collection_name: str = DEFAULT_FIRESTORE_COLLECTION,
        *,
        client: Any | None = None,
        collection: str | None = None,
        lock_collection_name: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        legacy_client = client
        if legacy_client is None and project_id is not None and not isinstance(project_id, str):
            legacy_client = project_id
            project_id = None

        resolved_collection = str(collection or collection_name or DEFAULT_FIRESTORE_COLLECTION).strip()
        if not resolved_collection:
            raise ValueError("collection_name must not be empty")

        self.client = legacy_client
        self.project_id = str(project_id or _default_project_id()).strip()
        self.collection = resolved_collection
        self.collection_name = resolved_collection
        self.lock_collection_name = str(
            lock_collection_name or f"{self.collection_name}_locks"
        ).strip()
        self.timeout = float(timeout)
        self._cached_access_token: str | None = None

    def _database_base_url(self) -> str:
        project_id = self.project_id or _default_project_id()
        return (
            "https://firestore.googleapis.com/v1/"
            f"projects/{quote(project_id, safe='')}/databases/(default)/documents"
        )

    def _collection_url(self, collection_name: str) -> str:
        return f"{self._database_base_url()}/{quote(collection_name, safe='')}"

    def _document_url(self, collection_name: str, document_id: str) -> str:
        return f"{self._collection_url(collection_name)}/{quote(document_id, safe='')}"

    def _access_token(self) -> str:
        if self._cached_access_token:
            return self._cached_access_token
        commands = (
            ["gcloud", "auth", "application-default", "print-access-token"],
            ["gcloud", "auth", "print-access-token"],
        )
        failures: list[str] = []
        for command in commands:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    check=True,
                )
            except FileNotFoundError as exc:
                raise LedgerWriteError("failed to access Firestore: gcloud CLI not found") from exc
            except subprocess.CalledProcessError as exc:
                detail = _decode_text(exc.stderr).strip() or _decode_text(exc.stdout).strip()
                failures.append(detail or "gcloud access token command failed")
                continue
            token = _decode_text(completed.stdout).strip()
            if token:
                self._cached_access_token = token
                return token
            failures.append("gcloud access token command returned empty stdout")
        raise LedgerWriteError(
            "failed to obtain Firestore access token: "
            + "; ".join(detail for detail in failures if detail)
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        expected_statuses: tuple[int, ...],
        json_payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=json_payload,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LedgerWriteError(
                f"failed to connect Firestore API: {self.collection_name}"
            ) from exc
        if response.status_code not in expected_statuses:
            raise _FirestoreAPIError(response.status_code, _firestore_error_detail(response))
        try:
            return response.json()
        except ValueError:
            return {}

    def _create_document(
        self,
        collection_name: str,
        document_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            self._collection_url(collection_name),
            expected_statuses=(200, 201),
            json_payload={"fields": _firestore_fields(payload)},
            params={"documentId": document_id},
        )

    def _delete_document(self, collection_name: str, document_id: str) -> None:
        self._request_json(
            "DELETE",
            self._document_url(collection_name, document_id),
            expected_statuses=(200,),
        )

    def _document_exists(self, collection_name: str, document_id: str) -> bool:
        try:
            self._request_json(
                "GET",
                self._document_url(collection_name, document_id),
                expected_statuses=(200,),
            )
        except _FirestoreAPIError as exc:
            if exc.status_code == 404:
                return False
            raise
        return True

    @contextmanager
    def with_lock(self, idempotency_key: str) -> Iterator[str]:
        lock_doc_id = _firestore_document_id(idempotency_key)
        lock_payload = {
            "idempotency_key": idempotency_key,
            "created_at": _now_jst().isoformat(),
        }

        if self.client is not None:
            lock_ref = self.client.collection(self.lock_collection_name).document(lock_doc_id)
            try:
                snapshot = lock_ref.get() if hasattr(lock_ref, "get") else None
                if snapshot is not None and bool(getattr(snapshot, "exists", False)):
                    raise LedgerLockError(f"duplicate idempotency lock: {idempotency_key}")
                if hasattr(lock_ref, "create"):
                    lock_ref.create(lock_payload)
                else:
                    lock_ref.set(lock_payload)
            except LedgerLockError:
                raise
            except Exception as exc:  # pragma: no cover - legacy client fallback
                text = str(exc)
                if "ALREADY_EXISTS" in text or "already exists" in text.lower():
                    raise LedgerLockError(f"duplicate idempotency lock: {idempotency_key}") from exc
                raise LedgerWriteError(
                    f"failed to acquire Firestore ledger lock: {self.lock_collection_name}"
                ) from exc
            try:
                yield lock_doc_id
            finally:
                try:
                    if hasattr(lock_ref, "delete"):
                        lock_ref.delete()
                except Exception:
                    pass
            return

        try:
            self._create_document(self.lock_collection_name, lock_doc_id, lock_payload)
        except _FirestoreAPIError as exc:
            if exc.status_code == 409 or "ALREADY_EXISTS" in exc.detail:
                raise LedgerLockError(f"duplicate idempotency lock: {idempotency_key}") from exc
            raise LedgerWriteError(
                f"failed to acquire Firestore ledger lock: {self.lock_collection_name}"
            ) from exc
        try:
            yield lock_doc_id
        finally:
            try:
                self._delete_document(self.lock_collection_name, lock_doc_id)
            except (LedgerWriteError, _FirestoreAPIError):
                pass

    def write(self, entry: RepairLedgerEntry) -> None:
        payload = entry.to_dict()
        if self.client is not None:
            try:
                with self.with_lock(entry.idempotency_key):
                    collection_ref = self.client.collection(self.collection_name)
                    document_ref = collection_ref.document(entry.idempotency_key)
                    if hasattr(document_ref, "get"):
                        snapshot = document_ref.get()
                        if snapshot is not None and bool(getattr(snapshot, "exists", False)):
                            raise LedgerLockError(
                                f"duplicate idempotency_key: {entry.idempotency_key}"
                            )
                    document_ref.set(payload)
                return
            except (LedgerLockError, LedgerWriteError):
                raise
            except Exception as exc:  # pragma: no cover - exercised through mocks
                raise LedgerWriteError(
                    f"failed to write Firestore ledger entry: {self.collection_name}"
                ) from exc

        document_id = _firestore_document_id(entry.idempotency_key)
        try:
            with self.with_lock(entry.idempotency_key):
                if self._document_exists(self.collection_name, document_id):
                    raise LedgerLockError(f"duplicate idempotency_key: {entry.idempotency_key}")
                self._create_document(self.collection_name, document_id, payload)
        except LedgerLockError:
            raise
        except _FirestoreAPIError as exc:
            if exc.status_code == 409 or "ALREADY_EXISTS" in exc.detail:
                raise LedgerLockError(f"duplicate idempotency_key: {entry.idempotency_key}") from exc
            raise LedgerWriteError(
                f"failed to write Firestore ledger entry: {self.collection_name}"
            ) from exc
        except LedgerWriteError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise LedgerWriteError(
                f"failed to write Firestore ledger entry: {self.collection_name}"
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
