"""sns_realtime_topic_state — GCS-backed yesterday's mention counts.

ticket 445 (a): 急上昇 marker。 昨日の言及回数 snapshot を `gs://{GCS_BUCKET}/sns_realtime_topic/counts_{YYYY-MM-DD}.json` に保存し、 今日の fire で読み出して delta を表示する。

free tier 内 (1 file/日 × 365 日 = 365 file × 数 KB = 数 MB)。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict

_logger = logging.getLogger(__name__)


def _gcs_path(date_str: str) -> str:
    return f"sns_realtime_topic/counts_{date_str}.json"


def save_counts(counts: Dict[str, int], date: datetime) -> bool:
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
            json.dumps(counts, ensure_ascii=False),
            content_type="application/json",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        _logger.warning("sns_realtime save_counts failed: %s", exc)
        return False


def load_previous_counts(today: datetime) -> Dict[str, int]:
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
        # value は int であることを保証
        return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}
    except Exception as exc:  # noqa: BLE001
        _logger.warning("sns_realtime load_previous_counts failed: %s", exc)
        return {}
