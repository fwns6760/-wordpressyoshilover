"""Best-effort Cloud Run ledger helpers for runner entrypoints."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src import repair_provider_ledger
from src.cloud_run_persistence import ArtifactUploader


ENV_LEDGER_FIRESTORE_ENABLED = "LEDGER_FIRESTORE_ENABLED"
ENV_LEDGER_GCS_ARTIFACT_ENABLED = "LEDGER_GCS_ARTIFACT_ENABLED"
DEFAULT_NOTICE_COLLECTION = "notice_ledger"


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _warn(message: str) -> None:
    print(f"[ledger] warning: {message}", file=sys.stderr)


def _stringify_error(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _coerce_post_id(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def read_entries_from_offset(path: str | Path, start_offset: int) -> list[repair_provider_ledger.RepairLedgerEntry]:
    target = Path(path)
    if not target.exists():
        return []
    safe_offset = max(int(start_offset), 0)
    with target.open("rb") as handle:
        handle.seek(safe_offset)
        payload = handle.read()
    if not payload:
        return []

    entries: list[repair_provider_ledger.RepairLedgerEntry] = []
    for index, raw_line in enumerate(payload.decode("utf-8", errors="replace").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("ledger row must be a JSON object")
            entries.append(repair_provider_ledger.RepairLedgerEntry(**row))
        except Exception as exc:
            _warn(f"failed to parse appended ledger row path={target} index={index}: {exc}")
    return entries


def build_entry(
    *,
    lane: str,
    provider: str,
    model: str,
    source_post_id: int,
    before_body: str,
    after_body: str,
    status: str,
    error_code: str | None = None,
    quality_flags: list[str] | None = None,
    fallback_from: str | None = None,
    fallback_reason: str | None = None,
    strict_pass: bool | None = None,
    input_payload: dict[str, Any] | None = None,
    now: datetime | None = None,
    run_id: str | None = None,
    artifact_uri: str | None = None,
) -> repair_provider_ledger.RepairLedgerEntry:
    current = repair_provider_ledger._now_jst(now)
    body_before = str(before_body or "")
    body_after = str(after_body or "")
    input_hash = repair_provider_ledger.compute_input_hash(
        input_payload
        if input_payload is not None
        else {
            "lane": lane,
            "source_post_id": int(source_post_id),
            "status": status,
            "before_body": body_before,
        }
    )
    body_len_before = len(body_before)
    body_len_after = len(body_after)
    return repair_provider_ledger.RepairLedgerEntry(
        schema_version=repair_provider_ledger.SCHEMA_VERSION,
        run_id=str(run_id or uuid4()),
        lane=lane,
        provider=provider,
        model=model,
        source_post_id=int(source_post_id),
        input_hash=input_hash,
        output_hash=repair_provider_ledger.compute_output_hash(body_after),
        artifact_uri=str(artifact_uri or f"memory://{lane}"),
        status=status,
        strict_pass=bool(status == "success" and not error_code) if strict_pass is None else bool(strict_pass),
        error_code=_stringify_error(error_code),
        idempotency_key=repair_provider_ledger.make_idempotency_key(
            int(source_post_id),
            input_hash,
            provider,
        ),
        created_at=current.isoformat(),
        started_at=current.isoformat(),
        finished_at=current.isoformat(),
        metrics={
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": 0,
            "body_len_before": body_len_before,
            "body_len_after": body_len_after,
            "body_len_delta_pct": repair_provider_ledger.compute_body_len_delta_pct(
                body_len_before,
                body_len_after,
            ),
        },
        provider_meta={
            "raw_response_size": len(body_after.encode("utf-8")),
            "fallback_from": fallback_from,
            "fallback_reason": fallback_reason,
            "quality_flags": list(quality_flags or []),
        },
    )


def replace_artifact_uri(
    entry: repair_provider_ledger.RepairLedgerEntry,
    artifact_uri: str,
) -> repair_provider_ledger.RepairLedgerEntry:
    payload = entry.to_dict()
    payload["artifact_uri"] = str(artifact_uri)
    return repair_provider_ledger.RepairLedgerEntry(**payload)


class BestEffortLedgerSink:
    def __init__(
        self,
        *,
        collection_name: str = repair_provider_ledger.DEFAULT_FIRESTORE_COLLECTION,
        fallback_path: str | Path | None = None,
        project_id: str | None = None,
        bucket_name: str | None = None,
        prefix: str | None = None,
    ) -> None:
        self.firestore_enabled = _env_enabled(ENV_LEDGER_FIRESTORE_ENABLED)
        self.gcs_enabled = _env_enabled(ENV_LEDGER_GCS_ARTIFACT_ENABLED)
        self.firestore_writer = (
            repair_provider_ledger.FirestoreLedgerWriter(
                project_id=project_id,
                collection_name=collection_name,
            )
            if self.firestore_enabled
            else None
        )
        self.uploader = (
            ArtifactUploader(
                bucket_name=bucket_name or "yoshilover-history",
                prefix=prefix or "repair_artifacts",
                project_id=project_id,
            )
            if self.gcs_enabled
            else None
        )
        self.fallback_writer = (
            repair_provider_ledger.JsonlLedgerWriter(Path(fallback_path))
            if fallback_path is not None and self.firestore_enabled
            else None
        )

    @property
    def enabled(self) -> bool:
        return self.firestore_enabled or self.gcs_enabled

    def persist(
        self,
        entry: repair_provider_ledger.RepairLedgerEntry,
        *,
        before_body: str,
        after_body: str,
        extra_meta: dict[str, Any] | None = None,
    ) -> repair_provider_ledger.RepairLedgerEntry:
        current = entry
        if self.uploader is not None:
            try:
                artifact_uri = self.uploader.upload(
                    post_id=entry.source_post_id,
                    provider=entry.provider,
                    run_id=entry.run_id,
                    before_body=before_body,
                    after_body=after_body,
                    extra_meta=extra_meta,
                )
                current = replace_artifact_uri(entry, artifact_uri)
            except Exception as exc:
                _warn(
                    f"gcs upload failed lane={entry.lane} post_id={entry.source_post_id}: {exc}"
                )

        if self.firestore_writer is None:
            return current

        try:
            self.firestore_writer.write(current)
        except Exception as exc:
            _warn(
                f"firestore write failed lane={entry.lane} post_id={entry.source_post_id}: {exc}"
            )
            if self.fallback_writer is not None:
                try:
                    self.fallback_writer.write(current)
                except Exception as fallback_exc:
                    _warn(
                        f"jsonl fallback failed lane={entry.lane} post_id={entry.source_post_id}: {fallback_exc}"
                    )
        return current


__all__ = [
    "BestEffortLedgerSink",
    "DEFAULT_NOTICE_COLLECTION",
    "ENV_LEDGER_FIRESTORE_ENABLED",
    "ENV_LEDGER_GCS_ARTIFACT_ENABLED",
    "build_entry",
    "read_entries_from_offset",
    "replace_artifact_uri",
]
