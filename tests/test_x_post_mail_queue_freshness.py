"""queue 417 の鮮度フィルタ (_filter_stale_queue_items) の単体テスト。

6/7 に enqueue された記事が 6/22 に「速報」候補化する事故 (古い滞留記事) を、
試合フェーズ鮮度窓で間引くことを verify する。
"""

from __future__ import annotations

import logging
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.tools import run_x_post_mail as r

_JST = timezone(timedelta(hours=9))
_LOG = logging.getLogger("test")


def _item(source_url: str, hours_ago: float):
    """enqueued_at_utc が hours_ago 時間前の duck-typed queue item。"""
    enq = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return types.SimpleNamespace(
        source_url=source_url,
        enqueued_at_utc=enq.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


class FilterStaleQueueItemsTests(unittest.TestCase):
    def setUp(self):
        self.now_jst = datetime.now(_JST)

    @patch.object(r.lane, "phase_freshness_max_age_hours", return_value=12.0)
    def test_drops_items_older_than_phase_window(self, _mock):
        items = [
            _item("https://hochi.news/g/fresh", 2),     # 当日
            _item("https://hochi.news/g/jun7", 24 * 15),  # 15日前 (6/7型)
            _item("https://hochi.news/g/edge", 11),      # 窓内ギリギリ
        ]
        out = r._filter_stale_queue_items(items, now_jst=self.now_jst, log=_LOG)
        urls = [i.source_url for i in out]
        self.assertIn("https://hochi.news/g/fresh", urls)
        self.assertIn("https://hochi.news/g/edge", urls)
        self.assertNotIn("https://hochi.news/g/jun7", urls)

    @patch.object(r.lane, "phase_freshness_max_age_hours", return_value=0.5)
    def test_in_game_window_keeps_only_immediate(self, _mock):
        items = [
            _item("https://hochi.news/g/now", 0.2),
            _item("https://hochi.news/g/1h", 1.0),
        ]
        out = r._filter_stale_queue_items(items, now_jst=self.now_jst, log=_LOG)
        self.assertEqual([i.source_url for i in out], ["https://hochi.news/g/now"])

    @patch.object(r.lane, "phase_freshness_max_age_hours", return_value=24.0)
    def test_missing_enqueue_date_kept(self, _mock):
        # 日付不明 item は弾かない (誤って新着を落とさない安全側)
        bad = types.SimpleNamespace(source_url="https://hochi.news/g/nodate", enqueued_at_utc="")
        out = r._filter_stale_queue_items([bad], now_jst=self.now_jst, log=_LOG)
        self.assertEqual(len(out), 1)

    @patch.object(r.lane, "phase_freshness_max_age_hours", return_value=12.0)
    def test_all_stale_returns_empty(self, _mock):
        items = [_item("https://hochi.news/g/a", 48), _item("https://hochi.news/g/b", 24 * 8)]
        out = r._filter_stale_queue_items(items, now_jst=self.now_jst, log=_LOG)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
