"""INSIGHT-005 — GCS persistence for the insight SQLite + outputs.

Cloud Run job filesystem is ephemeral. Without persistence each nightly
run starts from an empty DB and the multi-game / streak / z-score
detectors never have enough baseline to fire. This module syncs the
canonical artefacts (DB, CSV, digest directory) with a GCS bucket so
that:

  1. Job start: download ``insight.db`` (and optionally CSV) from GCS to
     ``data/insight/`` *before* the ETL pipeline runs.
  2. Job end: upload ``insight.db`` + ``article_candidates.csv`` +
     ``digest/<date>.md`` back to GCS.

Default bucket / prefix come from environment variables so the same
image can be reused across deployments without rebuilding:

  * ``INSIGHT_GCS_BUCKET`` — bucket name (e.g. ``baseballsite-yoshilover-insight``)
  * ``INSIGHT_GCS_PREFIX`` — optional prefix (default ``""``)

When ``INSIGHT_GCS_BUCKET`` is unset the sync is a **no-op** so local
runs (without auth) keep working unchanged.

Hard constraints:
  * Does not touch WordPress / publish flow / Gemini / X API / Cloud
    Scheduler / env. Only reads & writes GCS objects under the configured
    bucket + prefix.
  * Failure on download (bucket empty, network) does NOT block the
    pipeline — a fresh DB is built. Failure on upload IS surfaced as a
    soft error in the summary dict.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


# ─── helpers ────────────────────────────────────────────────────────────────


def gcs_bucket_name() -> Optional[str]:
    name = (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()
    return name or None


def gcs_prefix() -> str:
    p = (os.environ.get("INSIGHT_GCS_PREFIX") or "").strip().strip("/")
    return p


def _client():
    """Lazy import google.cloud.storage so unit tests can monkeypatch
    without the dependency installed at import time."""
    from google.cloud import storage  # noqa: WPS433
    return storage.Client()


def _bucket(client=None, bucket_name: Optional[str] = None):
    bn = bucket_name or gcs_bucket_name()
    if not bn:
        raise RuntimeError("INSIGHT_GCS_BUCKET not set")
    c = client or _client()
    return c.bucket(bn)


def _object_path(local_path: Path, base_dir: Path, prefix: str) -> str:
    rel = local_path.relative_to(base_dir).as_posix()
    if prefix:
        return f"{prefix}/{rel}"
    return rel


# ─── high-level API ────────────────────────────────────────────────────────


def download_state(
    *,
    base_dir: Path,
    bucket_name: Optional[str] = None,
    prefix: Optional[str] = None,
    objects: Iterable[str] = ("insight.db", "article_candidates.csv"),
    client=None,
) -> dict:
    """Pull canonical state files from GCS into ``base_dir``.

    Missing objects (first run, or never uploaded) are skipped silently
    — the pipeline will start fresh. Returns a summary dict.
    """
    bn = bucket_name or gcs_bucket_name()
    if not bn:
        return {"skipped": True, "reason": "no_bucket", "downloaded": []}
    prefix = prefix if prefix is not None else gcs_prefix()
    bucket = _bucket(client=client, bucket_name=bn)
    base_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict] = []
    missing: list[str] = []
    for rel in objects:
        object_name = f"{prefix}/{rel}" if prefix else rel
        blob = bucket.blob(object_name)
        if not blob.exists():
            missing.append(object_name)
            continue
        target = base_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target))
        downloaded.append({"object": object_name, "local": str(target), "size": target.stat().st_size})
    return {
        "skipped": False,
        "bucket": bn,
        "prefix": prefix,
        "downloaded": downloaded,
        "missing": missing,
    }


def upload_state(
    *,
    base_dir: Path,
    digest_dir: Optional[Path] = None,
    bucket_name: Optional[str] = None,
    prefix: Optional[str] = None,
    objects: Iterable[str] = ("insight.db", "article_candidates.csv"),
    client=None,
) -> dict:
    """Push canonical state + (optionally) the day's digest markdown(s)
    back to GCS. Missing local files are skipped (logged)."""
    bn = bucket_name or gcs_bucket_name()
    if not bn:
        return {"skipped": True, "reason": "no_bucket", "uploaded": []}
    prefix = prefix if prefix is not None else gcs_prefix()
    bucket = _bucket(client=client, bucket_name=bn)
    uploaded: list[dict] = []
    missing: list[str] = []

    for rel in objects:
        src = base_dir / rel
        if not src.exists():
            missing.append(rel)
            continue
        object_name = f"{prefix}/{rel}" if prefix else rel
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(src))
        uploaded.append({"object": object_name, "local": str(src), "size": src.stat().st_size})

    if digest_dir is not None and digest_dir.exists() and digest_dir.is_dir():
        for md_path in sorted(digest_dir.glob("*.md")):
            object_name = _object_path(md_path, base_dir, prefix)
            blob = bucket.blob(object_name)
            blob.upload_from_filename(str(md_path))
            uploaded.append({"object": object_name, "local": str(md_path), "size": md_path.stat().st_size})

    return {
        "skipped": False,
        "bucket": bn,
        "prefix": prefix,
        "uploaded": uploaded,
        "missing": missing,
    }
