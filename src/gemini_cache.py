from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src import cloud_run_persistence


JST = cloud_run_persistence.JST
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
DEFAULT_GEMINI_CACHE_PREFIX = "gemini_cache"
DEFAULT_LOCAL_CACHE_DIR = Path("/tmp/gemini_cache")
_MAX_CACHE_ENTRIES_PER_SOURCE = 32


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def normalize_content_text(content_text: str) -> str:
    lines = [line.strip() for line in str(content_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def compute_content_hash(content_text: str) -> str:
    normalized = normalize_content_text(content_text).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


@dataclass(frozen=True)
class GeminiCacheKey:
    source_url_hash: str
    content_hash: str
    prompt_template_id: str


@dataclass
class GeminiCacheValue:
    generated_text: str
    generated_at_iso: str
    model: str
    prompt_template_id: str


@dataclass
class _GeminiCacheEntry:
    content_hash: str
    generated_text: str
    generated_at_iso: str
    model: str
    prompt_template_id: str

    def to_value(self) -> GeminiCacheValue:
        return GeminiCacheValue(
            generated_text=self.generated_text,
            generated_at_iso=self.generated_at_iso,
            model=self.model,
            prompt_template_id=self.prompt_template_id,
        )


class GeminiCacheBackendError(RuntimeError):
    """Raised when the cache backend cannot be accessed safely."""


class GeminiCacheManager:
    _shared_instances: dict[tuple[str, str, str], "GeminiCacheManager"] = {}

    def __init__(
        self,
        *,
        state_manager: cloud_run_persistence.GCSStateManager | None = None,
        local_cache_dir: str | Path = DEFAULT_LOCAL_CACHE_DIR,
    ) -> None:
        self._state_manager = state_manager
        self._local_cache_dir = Path(local_cache_dir)
        self._memory: dict[str, list[_GeminiCacheEntry]] = {}
        self._loaded_source_hashes: set[str] = set()

    @classmethod
    def from_env(cls) -> "GeminiCacheManager":
        bucket_name = str(os.environ.get("GCS_STATE_BUCKET", cloud_run_persistence.DEFAULT_BUCKET_NAME)).strip()
        project_id = cloud_run_persistence._default_project_id()
        prefix = DEFAULT_GEMINI_CACHE_PREFIX
        key = (bucket_name, prefix, project_id)
        existing = cls._shared_instances.get(key)
        if existing is not None:
            return existing

        state_manager = None
        if shutil.which("gcloud"):
            state_manager = cloud_run_persistence.GCSStateManager(
                bucket_name=bucket_name,
                prefix=prefix,
                project_id=project_id,
            )

        manager = cls(state_manager=state_manager)
        cls._shared_instances[key] = manager
        return manager

    def lookup(
        self,
        cache_key: GeminiCacheKey,
        *,
        cooldown_hours: int,
        now: datetime | None = None,
    ) -> tuple[GeminiCacheValue | None, str, int]:
        entries = self._load_entries(cache_key.source_url_hash)
        cache_size_bytes = self._cache_size_bytes(cache_key.source_url_hash)

        exact_match: _GeminiCacheEntry | None = None
        cooldown_match: _GeminiCacheEntry | None = None
        threshold = _now_jst(now) - timedelta(hours=max(int(cooldown_hours), 0))

        for entry in entries:
            if entry.prompt_template_id != cache_key.prompt_template_id:
                continue
            if entry.content_hash == cache_key.content_hash:
                exact_match = entry
                break
            generated_at = _parse_datetime(entry.generated_at_iso)
            if generated_at is None or generated_at < threshold:
                continue
            if cooldown_match is None:
                cooldown_match = entry

        if exact_match is not None:
            return exact_match.to_value(), "content_hash_exact", cache_size_bytes
        if cooldown_match is not None:
            return cooldown_match.to_value(), "cooldown_active", cache_size_bytes
        return None, "miss", cache_size_bytes

    def save(
        self,
        cache_key: GeminiCacheKey,
        generated_text: str,
        *,
        now: datetime | None = None,
        model: str = DEFAULT_MODEL_NAME,
    ) -> int:
        source_url_hash = str(cache_key.source_url_hash or "").strip()
        if not source_url_hash:
            return 0

        entries = self._load_entries(source_url_hash)
        new_entry = _GeminiCacheEntry(
            content_hash=str(cache_key.content_hash or ""),
            generated_text=str(generated_text or ""),
            generated_at_iso=_now_jst(now).isoformat(),
            model=str(model or DEFAULT_MODEL_NAME),
            prompt_template_id=str(cache_key.prompt_template_id or ""),
        )
        deduped = [
            entry
            for entry in entries
            if not (
                entry.content_hash == new_entry.content_hash
                and entry.prompt_template_id == new_entry.prompt_template_id
            )
        ]
        deduped.insert(0, new_entry)
        self._memory[source_url_hash] = deduped[:_MAX_CACHE_ENTRIES_PER_SOURCE]
        self._loaded_source_hashes.add(source_url_hash)
        self._write_entries(source_url_hash)
        return self._cache_size_bytes(source_url_hash)

    def _remote_name(self, source_url_hash: str) -> str:
        return f"{source_url_hash[:2]}/{source_url_hash}.json"

    def _local_path(self, source_url_hash: str) -> Path:
        return self._local_cache_dir / source_url_hash[:2] / f"{source_url_hash}.json"

    def _load_entries(self, source_url_hash: str) -> list[_GeminiCacheEntry]:
        key = str(source_url_hash or "").strip()
        if not key:
            return []
        if key in self._loaded_source_hashes:
            return list(self._memory.get(key, []))

        if self._state_manager is not None:
            try:
                downloaded = self._state_manager.download(self._remote_name(key), self._local_path(key))
            except cloud_run_persistence.GCSAccessError as exc:
                raise GeminiCacheBackendError(str(exc)) from exc
            if not downloaded:
                self._local_path(key).unlink(missing_ok=True)

        entries = self._parse_entries(self._local_path(key))
        self._memory[key] = entries
        self._loaded_source_hashes.add(key)
        return list(entries)

    def _write_entries(self, source_url_hash: str) -> None:
        target = self._local_path(source_url_hash)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_url_hash": source_url_hash,
            "entries": [asdict(entry) for entry in self._memory.get(source_url_hash, [])],
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if self._state_manager is not None:
            try:
                self._state_manager.upload(target, self._remote_name(source_url_hash))
            except cloud_run_persistence.GCSAccessError as exc:
                raise GeminiCacheBackendError(str(exc)) from exc

    def _parse_entries(self, path: Path) -> list[_GeminiCacheEntry]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            return []

        parsed: list[_GeminiCacheEntry] = []
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            parsed.append(
                _GeminiCacheEntry(
                    content_hash=str(raw_entry.get("content_hash") or ""),
                    generated_text=str(raw_entry.get("generated_text") or ""),
                    generated_at_iso=str(raw_entry.get("generated_at_iso") or ""),
                    model=str(raw_entry.get("model") or DEFAULT_MODEL_NAME),
                    prompt_template_id=str(raw_entry.get("prompt_template_id") or ""),
                )
            )
        parsed.sort(
            key=lambda entry: _parse_datetime(entry.generated_at_iso) or datetime.min.replace(tzinfo=JST),
            reverse=True,
        )
        return parsed[:_MAX_CACHE_ENTRIES_PER_SOURCE]

    def _cache_size_bytes(self, source_url_hash: str) -> int:
        payload = {
            "source_url_hash": str(source_url_hash or ""),
            "entries": [asdict(entry) for entry in self._memory.get(str(source_url_hash or ""), [])],
        }
        return len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def classify_lookup_hit_kind(
    *,
    cache_key: GeminiCacheKey,
    cached_value: GeminiCacheValue | None,
    hit_reason: str,
    expected_model: str = DEFAULT_MODEL_NAME,
) -> str:
    if cached_value is None:
        return "unknown"
    normalized_reason = str(hit_reason or "").strip().lower()
    if normalized_reason not in {"content_hash_exact", "cooldown_active"}:
        return "unknown"
    cached_prompt_template_id = str(cached_value.prompt_template_id or "").strip()
    cached_model = str(cached_value.model or DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME
    normalized_expected_model = str(expected_model or DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME
    if (
        normalized_reason == "content_hash_exact"
        and cached_prompt_template_id == str(cache_key.prompt_template_id or "").strip()
        and cached_model == normalized_expected_model
    ):
        return "exact_hit"
    return "cooldown_hit"


__all__ = [
    "DEFAULT_MODEL_NAME",
    "GeminiCacheBackendError",
    "GeminiCacheKey",
    "GeminiCacheManager",
    "GeminiCacheValue",
    "classify_lookup_hit_kind",
    "compute_content_hash",
    "normalize_content_text",
]
