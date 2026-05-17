"""377-ARCHIVE Phase 1b: 残 archive 完成 + media URL backfill.

Goal:
  1. 既 archive (gs://.../tweets.jsonl) の oldest created_at から遡って、
     更に古い original tweet を fetch (end_time で過去側を取る)。
     新規分は最初から media expansion 込みで取る (1 度 fetch で済む)。
  2. 既存 archive 内の has_media=True (media_keys あり) tweet IDs を
     `get_tweets(ids=[...])` で 100 件ずつ再 fetch、 media URL を取得。
  3. 全 record に media URL を merge し、 GCS に再 upload。
  4. media URL から画像実体を CDN download し、
     gs://baseballsite-yoshilover-insight/archives/kobayashi_meigen/media/{tweet_id}_{media_key}.{ext}
     に保存 (無料)。

Usage:
  python3 -m src.tools.archive_kobayashi_meigen_complete \
    --budget-usd 5.0
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

import tweepy
from google.cloud import storage

LOG = logging.getLogger(__name__)

USER_ID = "1092767600105336832"
BUCKET = "baseballsite-yoshilover-insight"
JSONL_KEY = "archives/kobayashi_meigen/tweets.jsonl"
MEDIA_PREFIX = "archives/kobayashi_meigen/media/"
COST_PER_RESOURCE = 0.005


def _normalize_text(text: str) -> str:
    t = re.sub(r"https?://\S+", "", text or "")
    t = re.sub(r"@\w+", "", t)
    t = re.sub(r"#\S+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _build_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=os.environ.get("X_BEARER_TOKEN"),
        consumer_key=os.environ.get("X_API_KEY"),
        consumer_secret=os.environ.get("X_API_SECRET"),
        access_token=os.environ.get("X_ACCESS_TOKEN"),
        access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET"),
    )


def _gcs_bucket() -> Any:
    return storage.Client().bucket(BUCKET)


def _download_existing_archive() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (records, by_id index)."""
    blob = _gcs_bucket().blob(JSONL_KEY)
    if not blob.exists():
        return [], {}
    text = blob.download_as_text()
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    by_id = {r["tweet_id"]: r for r in records}
    LOG.info("Loaded existing archive: %d records", len(records))
    return records, by_id


def _upload_archive(records: list[dict[str, Any]]) -> None:
    """records は created_at desc で保存。"""
    records_sorted = sorted(
        records, key=lambda r: r.get("created_at") or "", reverse=True
    )
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in records_sorted) + "\n"
    blob = _gcs_bucket().blob(JSONL_KEY)
    blob.upload_from_string(payload, content_type="application/x-ndjson")
    LOG.info("Uploaded merged archive: %d records → gs://%s/%s",
             len(records_sorted), BUCKET, JSONL_KEY)


def _build_media_map(includes: Any) -> dict[str, dict[str, Any]]:
    if not includes:
        return {}
    media_objs = includes.get("media") if isinstance(includes, dict) else None
    if not media_objs:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for m in media_objs:
        mk = getattr(m, "media_key", None)
        if not mk:
            continue
        out[mk] = {
            "type": getattr(m, "type", None),
            "url": getattr(m, "url", None) or getattr(m, "preview_image_url", None),
            "preview_image_url": getattr(m, "preview_image_url", None),
            "width": getattr(m, "width", None),
            "height": getattr(m, "height", None),
        }
    return out


def _tweet_to_record(tweet: Any, media_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    attachments = getattr(tweet, "attachments", None) or {}
    media_keys: list[str] = []
    if isinstance(attachments, dict):
        media_keys = list(attachments.get("media_keys") or [])
    pm = getattr(tweet, "public_metrics", None) or {}
    if not isinstance(pm, dict):
        pm = dict(pm) if pm else {}
    created_at = getattr(tweet, "created_at", None)
    media_records = []
    for mk in media_keys:
        info = media_map.get(mk)
        if info:
            media_records.append({"media_key": mk, **info})
        else:
            media_records.append({"media_key": mk, "type": None, "url": None})
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
        "media": media_records,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


class BudgetTracker:
    def __init__(self, max_usd: float):
        self.max_usd = max_usd
        self.spent_usd = 0.0
        self.tweet_reads = 0
        self.media_reads = 0

    def add(self, tweet_count: int = 0, media_count: int = 0) -> bool:
        cost = (tweet_count + media_count) * COST_PER_RESOURCE
        if self.spent_usd + cost > self.max_usd:
            LOG.warning("Budget would be exceeded: spent=$%.3f + cost=$%.3f > max=$%.3f",
                        self.spent_usd, cost, self.max_usd)
            return False
        self.spent_usd += cost
        self.tweet_reads += tweet_count
        self.media_reads += media_count
        return True

    def remaining_resources(self) -> int:
        return int((self.max_usd - self.spent_usd) / COST_PER_RESOURCE)


def fetch_older_tweets(
    client: tweepy.Client,
    *,
    end_time_iso: str,
    budget: BudgetTracker,
    pause_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    """end_time より古い original tweet を遡及取得 (media expansion 付き)."""
    new_records: list[dict[str, Any]] = []
    pagination_token: str | None = None
    LOG.info("Fetching older tweets ending before %s", end_time_iso)

    while budget.remaining_resources() >= 5:
        page_size = min(100, max(5, budget.remaining_resources() // 2))
        if page_size < 5:
            break

        LOG.info(
            "Page request: page_size=%d budget_spent=$%.3f remaining_resources=%d",
            page_size, budget.spent_usd, budget.remaining_resources(),
        )
        kwargs = dict(
            id=USER_ID,
            max_results=page_size,
            exclude=["retweets"],
            tweet_fields=[
                "created_at", "public_metrics", "lang", "attachments",
            ],
            expansions=["attachments.media_keys"],
            media_fields=["url", "preview_image_url", "type", "width", "height"],
            end_time=end_time_iso,
        )
        if pagination_token:
            kwargs["pagination_token"] = pagination_token

        resp = client.get_users_tweets(**kwargs)
        if resp.data is None or len(resp.data) == 0:
            LOG.info("No older tweets returned, stop.")
            break

        media_map = _build_media_map(getattr(resp, "includes", None))
        tweet_count = len(resp.data)
        media_count = len(media_map)
        ok = budget.add(tweet_count=tweet_count, media_count=media_count)
        if not ok:
            LOG.warning("Budget exhausted mid-page, stop.")
            break

        for t in resp.data:
            new_records.append(_tweet_to_record(t, media_map))

        meta = getattr(resp, "meta", None) or {}
        next_token = meta.get("next_token") if isinstance(meta, dict) else None
        if not next_token:
            LOG.info("End of timeline (no next_token).")
            break
        pagination_token = next_token

        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return new_records


def backfill_media_urls(
    client: tweepy.Client,
    *,
    target_ids: list[str],
    budget: BudgetTracker,
    pause_seconds: float = 1.0,
) -> dict[str, list[dict[str, Any]]]:
    """tweet_id list を 100 件ずつ batch で取得、 media URL を返す.

    Returns mapping: {tweet_id: [media_record, ...]}
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for i in range(0, len(target_ids), 100):
        batch = target_ids[i:i + 100]
        if budget.remaining_resources() < len(batch):
            LOG.warning("Budget insufficient for batch of %d (remaining=%d)",
                        len(batch), budget.remaining_resources())
            break

        resp = client.get_tweets(
            ids=batch,
            tweet_fields=["attachments"],
            expansions=["attachments.media_keys"],
            media_fields=["url", "preview_image_url", "type", "width", "height"],
        )
        media_map = _build_media_map(getattr(resp, "includes", None))
        tweet_count = len(resp.data) if resp.data else 0
        media_count = len(media_map)
        budget.add(tweet_count=tweet_count, media_count=media_count)

        if resp.data:
            for t in resp.data:
                attachments = getattr(t, "attachments", None) or {}
                media_keys: list[str] = []
                if isinstance(attachments, dict):
                    media_keys = list(attachments.get("media_keys") or [])
                media_records = []
                for mk in media_keys:
                    info = media_map.get(mk)
                    if info:
                        media_records.append({"media_key": mk, **info})
                if media_records:
                    out[str(t.id)] = media_records
        if pause_seconds > 0:
            time.sleep(pause_seconds)
    return out


def download_media_to_gcs(records: list[dict[str, Any]]) -> int:
    """media URL から画像 download、 GCS に保存. Return download count."""
    bucket = _gcs_bucket()
    done = 0
    for r in records:
        tid = r["tweet_id"]
        for m in r.get("media") or []:
            url = m.get("url") or m.get("preview_image_url")
            mk = m.get("media_key")
            if not url or not mk:
                continue
            ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
            if ext not in {"jpg", "jpeg", "png", "gif", "webp", "mp4"}:
                ext = "bin"
            object_key = f"{MEDIA_PREFIX}{tid}_{mk}.{ext}"
            if bucket.blob(object_key).exists():
                continue
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "yoshilover-archive/1.0"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("download fail tid=%s key=%s: %r", tid, mk, exc)
                continue
            content_type = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "gif": "image/gif",
                "webp": "image/webp", "mp4": "video/mp4",
            }.get(ext, "application/octet-stream")
            bucket.blob(object_key).upload_from_string(data, content_type=content_type)
            m["gcs_path"] = f"gs://{BUCKET}/{object_key}"
            done += 1
            if done % 20 == 0:
                LOG.info("downloaded %d media so far", done)
    return done


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-usd", type=float, default=5.0)
    parser.add_argument("--skip-older", action="store_true",
                        help="古い tweet 遡及取得をスキップ (media backfill のみ)")
    parser.add_argument("--skip-media-download", action="store_true",
                        help="CDN download をスキップ (URL 保存のみ)")
    args = parser.parse_args(argv)

    budget = BudgetTracker(max_usd=args.budget_usd)
    LOG.info("budget=$%.2f  cost_per_resource=$%.3f  max_resources=%d",
             args.budget_usd, COST_PER_RESOURCE, budget.remaining_resources())

    records, by_id = _download_existing_archive()
    if not records:
        LOG.error("既 archive がない、 先に Phase 1 を実行してください")
        return 1

    oldest_ts = min(r["created_at"] for r in records if r.get("created_at"))
    LOG.info("Existing archive oldest=%s newest=%s",
             oldest_ts, max(r["created_at"] for r in records if r.get("created_at")))

    client = _build_client()

    # Phase 1: 古い側遡及
    new_old_records: list[dict[str, Any]] = []
    if not args.skip_older:
        new_old_records = fetch_older_tweets(
            client, end_time_iso=oldest_ts, budget=budget,
        )
        LOG.info("Older tweets fetched: %d (budget_spent=$%.3f)",
                 len(new_old_records), budget.spent_usd)
        # text dedup with existing
        seen_ids = set(by_id.keys())
        unique_new = []
        for r in new_old_records:
            if r["tweet_id"] not in seen_ids:
                unique_new.append(r)
                by_id[r["tweet_id"]] = r
                records.append(r)
        LOG.info("Older unique appended: %d", len(unique_new))

    # Phase 2: media URL backfill (既存 has_media=True で media URL 未取得 のもの)
    need_backfill_ids = [
        r["tweet_id"] for r in records
        if r.get("has_media")
        and not any(
            (m.get("url") or m.get("preview_image_url")) for m in (r.get("media") or [])
        )
    ]
    LOG.info("Media backfill needed: %d tweets", len(need_backfill_ids))
    if need_backfill_ids:
        media_by_tid = backfill_media_urls(
            client, target_ids=need_backfill_ids, budget=budget,
        )
        backfilled = 0
        for tid, mlist in media_by_tid.items():
            r = by_id.get(tid)
            if r:
                r["media"] = mlist
                backfilled += 1
        LOG.info("Media backfilled into records: %d (budget_spent=$%.3f)",
                 backfilled, budget.spent_usd)

    # Phase 3: 再 upload
    _upload_archive(records)

    # Phase 4: CDN download
    if not args.skip_media_download:
        n = download_media_to_gcs(records)
        LOG.info("Media files downloaded to GCS: %d", n)
        # Re-upload after gcs_path added
        _upload_archive(records)

    LOG.info(
        "FINAL: tweets=%d, with_media=%d, total_media=%d, "
        "tweet_reads=%d, media_reads=%d, spent=$%.3f / $%.2f",
        len(records),
        sum(1 for r in records if r.get("has_media")),
        sum(len(r.get("media") or []) for r in records),
        budget.tweet_reads, budget.media_reads, budget.spent_usd, args.budget_usd,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
