"""377-ARCHIVE: @sakaikkotaiso (小林誠司 名言集) を GCS に archive する one-shot script.

Goal:
  X API v2 で 妻 account @sakaikkotaiso の original tweet を新しい順に
  paid budget cap まで fetch、 text hash dedup、 GCS JSONL upload。
  RT は exclude で API レベル除外 (課金なし)、 media expansion は
  別課金回避のため取らない (media_keys の有無だけ記録)。

Usage:
  python3 -m src.tools.archive_kobayashi_meigen \
    --max-paid-reads 870 \
    --gcs-bucket baseballsite-yoshilover-insight \
    --gcs-key archives/kobayashi_meigen/tweets.jsonl

Cost: max_paid_reads * $0.005 / read (pay-per-use, 他人 account)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any

import tweepy
from google.cloud import storage

LOG = logging.getLogger(__name__)

USER_ID = "1092767600105336832"  # @sakaikkotaiso
USERNAME = "sakaikkotaiso"


def _normalize_text(text: str) -> str:
    """text dedup 用に URL / mention / hashtag / 余分空白 を取り除く."""
    t = re.sub(r"https?://\S+", "", text or "")
    t = re.sub(r"@\w+", "", t)
    t = re.sub(r"#\S+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _build_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=os.environ.get("X_BEARER_TOKEN"),
        consumer_key=os.environ.get("X_API_KEY"),
        consumer_secret=os.environ.get("X_API_SECRET"),
        access_token=os.environ.get("X_ACCESS_TOKEN"),
        access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET"),
    )


def _tweet_to_record(tweet: Any) -> dict[str, Any]:
    media_keys: list[str] = []
    attachments = getattr(tweet, "attachments", None) or {}
    if isinstance(attachments, dict):
        media_keys = list(attachments.get("media_keys") or [])
    pm = getattr(tweet, "public_metrics", None) or {}
    if not isinstance(pm, dict):
        pm = dict(pm) if pm else {}
    created_at = getattr(tweet, "created_at", None)
    return {
        "tweet_id": str(tweet.id),
        "text": tweet.text,
        "created_at": created_at.isoformat() if created_at else None,
        "public_metrics": {
            "retweet_count": pm.get("retweet_count", 0),
            "reply_count": pm.get("reply_count", 0),
            "like_count": pm.get("like_count", 0),
            "quote_count": pm.get("quote_count", 0),
        },
        "lang": getattr(tweet, "lang", None),
        "has_media": bool(media_keys),
        "media_keys": media_keys,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_archive(
    *,
    max_paid_reads: int,
    pause_seconds: float = 1.0,
) -> tuple[list[dict[str, Any]], int]:
    """Return (unique records, paid_read_count).

    paid_read_count = X API に課金される取得 件数 (= fetched, RT は API
    側で exclude されてるので発生しない)。 unique records = text hash
    dedup 後の保存対象。
    """
    client = _build_client()
    pagination_token: str | None = None
    paid_reads = 0
    records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    seen_ids: set[str] = set()

    while paid_reads < max_paid_reads:
        remaining = max_paid_reads - paid_reads
        page_size = min(100, remaining)
        if page_size < 5:
            LOG.info("Remaining budget (%d) below page min, stop.", remaining)
            break

        LOG.info(
            "Fetching page: page_size=%d paid_so_far=%d/%d token=%s",
            page_size, paid_reads, max_paid_reads, pagination_token,
        )
        resp = client.get_users_tweets(
            id=USER_ID,
            max_results=page_size,
            exclude=["retweets"],
            tweet_fields=[
                "created_at", "public_metrics", "lang", "attachments",
            ],
            pagination_token=pagination_token,
        )

        if resp.data is None or len(resp.data) == 0:
            LOG.info("No more tweets returned.")
            break

        page_count = len(resp.data)
        paid_reads += page_count
        LOG.info("Page returned %d tweets (paid_reads=%d).", page_count, paid_reads)

        for t in resp.data:
            tid = str(t.id)
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            text_hash = hashlib.sha256(_normalize_text(t.text).encode()).hexdigest()
            if text_hash in seen_hashes:
                LOG.info("text dupe skip: id=%s", tid)
                continue
            seen_hashes.add(text_hash)
            records.append(_tweet_to_record(t))

        meta = getattr(resp, "meta", None) or {}
        next_token = meta.get("next_token") if isinstance(meta, dict) else None
        if not next_token:
            LOG.info("No next_token, end of timeline reached.")
            break
        pagination_token = next_token

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return records, paid_reads


def upload_jsonl_to_gcs(
    *,
    records: list[dict[str, Any]],
    bucket_name: str,
    object_key: str,
) -> str:
    payload = "\n".join(
        json.dumps(r, ensure_ascii=False) for r in records
    ) + ("\n" if records else "")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_key)
    blob.upload_from_string(payload, content_type="application/x-ndjson")
    return f"gs://{bucket_name}/{object_key}"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(
        description="Archive @sakaikkotaiso tweets to GCS (377-ARCHIVE).",
    )
    parser.add_argument("--max-paid-reads", type=int, default=870)
    parser.add_argument("--gcs-bucket", default="baseballsite-yoshilover-insight")
    parser.add_argument(
        "--gcs-key",
        default="archives/kobayashi_meigen/tweets.jsonl",
    )
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="fetch をスキップ、 設定だけ表示。",
    )
    args = parser.parse_args(argv)

    LOG.info("max_paid_reads=%d  pay_estimate=$%.2f",
             args.max_paid_reads, args.max_paid_reads * 0.005)
    LOG.info("gcs target=gs://%s/%s", args.gcs_bucket, args.gcs_key)
    if args.dry_run:
        LOG.info("dry-run, exit before fetch.")
        return 0

    records, paid_reads = fetch_archive(
        max_paid_reads=args.max_paid_reads,
        pause_seconds=args.pause_seconds,
    )
    LOG.info("fetched=%d  unique_saved=%d  actual_cost=$%.3f",
             paid_reads, len(records), paid_reads * 0.005)

    if not records:
        LOG.warning("No records to upload, skip GCS write.")
        return 0

    gcs_uri = upload_jsonl_to_gcs(
        records=records,
        bucket_name=args.gcs_bucket,
        object_key=args.gcs_key,
    )
    LOG.info("uploaded: %s", gcs_uri)

    with_media = sum(1 for r in records if r.get("has_media"))
    LOG.info("media-containing tweets: %d / %d", with_media, len(records))
    if records:
        oldest = records[-1].get("created_at")
        newest = records[0].get("created_at")
        LOG.info("range: newest=%s  oldest=%s", newest, oldest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
