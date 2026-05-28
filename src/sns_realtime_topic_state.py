"""sns_realtime_topic_state — GCS-backed yesterday's mention counts (per page).

ticket 445 (a + page split): 急上昇 marker。 昨日の言及回数 snapshot を
`gs://{GCS_BUCKET}/sns_realtime_topic/counts_{YYYY-MM-DD}.json` に保存。

format: page split 対応で nested dict
  {"1gun": {"戸郷翔征": 15, ...}, "farm": {"林 燦": 2, ...}}

free tier 内 (1 file/日 × 365 日 = 365 file × 数 KB = 数 MB)。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict

_logger = logging.getLogger(__name__)

PageCounts = Dict[str, Dict[str, int]]  # {page_key: {name: count}}


def _gcs_path(date_str: str) -> str:
    return f"sns_realtime_topic/counts_{date_str}.json"


def save_counts(counts_by_page: PageCounts, date: datetime) -> bool:
    bucket_name = os.environ.get("GCS_BUCKET", "").strip()
    if not bucket_name:
        _logger.info("sns_realtime save_counts skipped (no GCS_BUCKET)")
        return False
    try:
        from google.cloud import storage  # type: ignore

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_gcs_path(date.strftime("%Y-%m-%d")))
        blob.upload_from_string(
            json.dumps(counts_by_page, ensure_ascii=False),
            content_type="application/json",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        _logger.warning("sns_realtime save_counts failed: %s", exc)
        return False


def load_previous_counts(today: datetime) -> PageCounts:
    """Return nested dict {page_key: {name: count}}. Empty dict if not available."""
    bucket_name = os.environ.get("GCS_BUCKET", "").strip()
    if not bucket_name:
        return {}
    yesterday = today - timedelta(days=1)
    try:
        from google.cloud import storage  # type: ignore

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_gcs_path(yesterday.strftime("%Y-%m-%d")))
        if not blob.exists():
            return {}
        raw = blob.download_as_text()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        # legacy flat dict (v0) は {1gun: <data>} に migrate
        if data and not any(isinstance(v, dict) for v in data.values()):
            return {"1gun": {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}}
        out: PageCounts = {}
        for page_key, page_data in data.items():
            if isinstance(page_data, dict):
                out[str(page_key)] = {
                    str(k): int(v) for k, v in page_data.items() if isinstance(v, (int, float))
                }
        return out
    except Exception as exc:  # noqa: BLE001
        _logger.warning("sns_realtime load_previous_counts failed: %s", exc)
        return {}
