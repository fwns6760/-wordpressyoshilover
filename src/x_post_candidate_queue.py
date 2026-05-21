"""417: X-post candidate queue (rss_fetcher → x_post_mail_lane bridge).

rss_fetcher が報知 / サンスポ source を classify 完了した時点で `enqueue()` し、
別 Cloud Run job (`x-post-mail-lane`) が cron `*/30 6-22 * * *` で `drain()`
→ Gemma 4 で X-post 候補生成 → mail 送信 → `mark_processed()` の流れ。

ストレージは GCS (`gs://<bucket>/x_post_candidate_queue/{queued,processed}/<source_url_hash>.json`)。
Cloud Run 2 service (yoshilover-fetcher / x-post-mail-lane) が共有するため
sqlite local では不可、GCS で entry 単位の atomic write を採用。

Idempotency: filename = sha256(source_url)[:16].json で 同じ source_url の
2 度目の enqueue は dedup skip (queued / processed の両方を check)。

Fault-tolerance: enqueue は **絶対に例外を上に投げない** (rss_fetcher の
pipeline を queue 障害で止めないため)。失敗時は WARN log + return False。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_QUEUE_BUCKET_ENV = "X_POST_CANDIDATE_QUEUE_BUCKET"
_DEFAULT_BUCKET = "baseballsite-yoshilover-state"
_QUEUE_PREFIX = "x_post_candidate_queue"
_QUEUED_PREFIX = f"{_QUEUE_PREFIX}/queued/"
_PROCESSED_PREFIX = f"{_QUEUE_PREFIX}/processed/"

QUEUE_SCHEMA_VERSION = "x_post_candidate_v0"


@dataclass
class CandidateArticleInfo:
    """X-post 候補生成の入力 article info (rss_fetcher → x_post_mail_lane)."""

    source_url: str
    title: str
    summary: str
    source_name: str
    source_type: str
    article_subtype: str
    player_canonical: list[str] = field(default_factory=list)
    enqueued_at_utc: str = ""
    schema_version: str = QUEUE_SCHEMA_VERSION


def _source_url_hash(source_url: str) -> str:
    """Stable short hash (16 hex chars = 64 bits) for filename."""
    if not source_url:
        return "_empty_"
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_bucket():
    """Lazy import + bucket handle. Raises on credential/import failure."""
    from google.cloud import storage  # type: ignore[import-not-found]

    bucket_name = os.environ.get(_QUEUE_BUCKET_ENV, _DEFAULT_BUCKET)
    client = storage.Client()
    return client.bucket(bucket_name)


def enqueue(article_info: CandidateArticleInfo) -> bool:
    """Idempotent enqueue. Returns True if a new entry was written, False if dedup-skipped or failed.

    Fault-tolerant: never raises. Caller (rss_fetcher) must continue
    regardless of queue success/failure.
    """
    if not article_info.source_url:
        logger.info("x_post_queue_enqueue_skip reason=empty_source_url")
        return False
    if not article_info.enqueued_at_utc:
        article_info.enqueued_at_utc = _now_utc_iso()
    try:
        bucket = _get_bucket()
        h = _source_url_hash(article_info.source_url)
        # Dedup: skip if already present in queued OR processed
        for prefix in (_QUEUED_PREFIX, _PROCESSED_PREFIX):
            blob = bucket.blob(f"{prefix}{h}.json")
            if blob.exists():
                logger.info(
                    "x_post_queue_dedup_skip source_url=%s hash=%s prefix=%s",
                    article_info.source_url,
                    h,
                    prefix.rstrip("/"),
                )
                return False
        # Write new entry
        target_blob = bucket.blob(f"{_QUEUED_PREFIX}{h}.json")
        target_blob.upload_from_string(
            json.dumps(asdict(article_info), ensure_ascii=False),
            content_type="application/json",
        )
        logger.info(
            "x_post_queue_enqueued source_url=%s hash=%s subtype=%s",
            article_info.source_url,
            h,
            article_info.article_subtype,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — fault-tolerant per contract
        logger.warning(
            "x_post_queue_enqueue_failed source_url=%s err=%r",
            article_info.source_url,
            exc,
        )
        return False


def drain(max_count: int = 50) -> list[CandidateArticleInfo]:
    """Drain up to `max_count` queued entries. Does NOT mark them processed.

    Caller MUST call `mark_processed()` per entry after mail send succeeds,
    otherwise the entry stays queued and will be re-drained next fire (which
    is the desired behaviour for retry — until mail succeeds).
    """
    try:
        bucket = _get_bucket()
        blobs = list(bucket.list_blobs(prefix=_QUEUED_PREFIX, max_results=max_count))
    except Exception as exc:  # noqa: BLE001
        logger.warning("x_post_queue_drain_failed err=%r", exc)
        return []
    out: list[CandidateArticleInfo] = []
    for blob in blobs:
        try:
            data = json.loads(blob.download_as_text())
            out.append(CandidateArticleInfo(**data))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "x_post_queue_drain_entry_corrupt blob=%s err=%r", blob.name, exc
            )
            continue
    logger.info("x_post_queue_drain count=%d", len(out))
    return out


def mark_processed(article_info: CandidateArticleInfo) -> bool:
    """Move queued entry to processed prefix (= mail successfully sent).

    Returns True on success, False on failure (caller may log but should not crash).
    """
    if not article_info.source_url:
        return False
    try:
        bucket = _get_bucket()
        h = _source_url_hash(article_info.source_url)
        src_blob = bucket.blob(f"{_QUEUED_PREFIX}{h}.json")
        dst_blob = bucket.blob(f"{_PROCESSED_PREFIX}{h}.json")
        if not src_blob.exists():
            logger.info(
                "x_post_queue_mark_processed_skip reason=src_not_found source_url=%s hash=%s",
                article_info.source_url,
                h,
            )
            return False
        bucket.copy_blob(src_blob, bucket, dst_blob.name)
        src_blob.delete()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "x_post_queue_mark_processed_failed source_url=%s err=%r",
            article_info.source_url,
            exc,
        )
        return False


def is_hochi_or_sanspo_source(source_url: str, source_name: str = "") -> bool:
    """報知 / サンスポ source か判定.

    判定軸:
    - URL host: hochi.news / news.hochi.news / sanspo.com / www.sanspo.com
    - URL host: rsshub-* via /twitter/user/hochi_giants / hochi_baseball / sportshochi
    - URL host: rsshub-* via /twitter/user/sanspo_giants / sanspo
    - source_name marker: 「報知」「スポーツ報知」「サンスポ」「サンケイスポーツ」
    """
    if not source_url and not source_name:
        return False
    src = (source_url or "").lower()
    name = source_name or ""
    # URL host check
    url_hits = (
        "hochi.news" in src
        or "sanspo.com" in src
        or "hochi_giants" in src
        or "hochi_baseball" in src
        or "sportshochi" in src
        or "sanspo_giants" in src
    )
    if url_hits:
        return True
    # source_name marker check (Japanese)
    name_markers = (
        "報知",
        "スポーツ報知",
        "SportsHochi",
        "サンスポ",
        "サンケイスポーツ",
        "Sanspo",
    )
    return any(marker in name for marker in name_markers)
