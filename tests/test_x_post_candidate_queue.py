"""Tests for src/x_post_candidate_queue.py (417).

GCS をモックして enqueue / drain / mark_processed / dedup / source 判定 を verify。
production の GCS API 呼出はしない (`google.cloud.storage` を patch)。
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src import x_post_candidate_queue as q


def _make_article(source_url="https://hochi.news/giants/1", title="戸郷翔征が好投", **kw):
    return q.CandidateArticleInfo(
        source_url=source_url,
        title=title,
        summary=kw.get("summary", ""),
        source_name=kw.get("source_name", "スポーツ報知"),
        source_type=kw.get("source_type", "rss"),
        article_subtype=kw.get("article_subtype", "postgame"),
        player_canonical=kw.get("player_canonical", []),
    )


class IsHochiOrSanspoSourceTests(unittest.TestCase):
    def test_hochi_news_url_matches(self):
        self.assertTrue(q.is_hochi_or_sanspo_source("https://hochi.news/giants/1", ""))
        self.assertTrue(q.is_hochi_or_sanspo_source("https://news.hochi.news/giants/2", ""))

    def test_sanspo_url_matches(self):
        self.assertTrue(q.is_hochi_or_sanspo_source("https://www.sanspo.com/article/1", ""))

    def test_rsshub_hochi_handle_matches(self):
        self.assertTrue(q.is_hochi_or_sanspo_source("https://rsshub.local/twitter/user/hochi_giants", ""))
        self.assertTrue(q.is_hochi_or_sanspo_source("https://rsshub.local/twitter/user/sportshochi", ""))

    def test_source_name_marker_matches(self):
        self.assertTrue(q.is_hochi_or_sanspo_source("", "スポーツ報知"))
        self.assertTrue(q.is_hochi_or_sanspo_source("", "サンケイスポーツ"))

    def test_nikkan_or_daily_does_not_match(self):
        self.assertFalse(q.is_hochi_or_sanspo_source("https://www.nikkansports.com/baseball/news/1.html", "日刊スポーツ"))
        self.assertFalse(q.is_hochi_or_sanspo_source("https://www.daily.co.jp/baseball/giants/1.html", "デイリースポーツ"))

    def test_empty_input_returns_false(self):
        self.assertFalse(q.is_hochi_or_sanspo_source("", ""))


class EnqueueTests(unittest.TestCase):
    def test_empty_source_url_skipped(self):
        article = _make_article(source_url="")
        self.assertFalse(q.enqueue(article))

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_new_entry_uploaded(self, mock_bucket_fn):
        mock_bucket = MagicMock()
        mock_blob_exists = MagicMock()
        mock_blob_exists.exists.return_value = False
        mock_bucket.blob.return_value = mock_blob_exists
        mock_bucket_fn.return_value = mock_bucket

        article = _make_article()
        self.assertTrue(q.enqueue(article))
        # blob.upload_from_string が 1 回呼ばれた
        mock_blob_exists.upload_from_string.assert_called_once()
        # アップロード内容が JSON dict であること
        call_args = mock_blob_exists.upload_from_string.call_args
        body = call_args.args[0] if call_args.args else call_args.kwargs.get("data")
        decoded = json.loads(body)
        self.assertEqual(decoded["source_url"], article.source_url)
        self.assertEqual(decoded["title"], article.title)

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_dedup_skip_if_already_queued(self, mock_bucket_fn):
        mock_bucket = MagicMock()
        existing_blob = MagicMock()
        existing_blob.exists.return_value = True
        mock_bucket.blob.return_value = existing_blob
        mock_bucket_fn.return_value = mock_bucket

        article = _make_article()
        self.assertFalse(q.enqueue(article))
        existing_blob.upload_from_string.assert_not_called()

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_gcs_exception_does_not_raise(self, mock_bucket_fn):
        mock_bucket_fn.side_effect = RuntimeError("GCS auth failure")
        article = _make_article()
        # fault-tolerant: should not raise, returns False
        result = q.enqueue(article)
        self.assertFalse(result)


class DrainTests(unittest.TestCase):
    @patch("src.x_post_candidate_queue._get_bucket")
    def test_empty_queue_returns_empty_list(self, mock_bucket_fn):
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []
        mock_bucket_fn.return_value = mock_bucket
        self.assertEqual(q.drain(), [])

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_drain_returns_entries(self, mock_bucket_fn):
        article = _make_article()
        blob = MagicMock()
        blob.updated = datetime(2026, 5, 22, 9, 0, 0, tzinfo=timezone.utc)
        blob.download_as_text.return_value = json.dumps({
            "source_url": article.source_url,
            "title": article.title,
            "summary": article.summary,
            "source_name": article.source_name,
            "source_type": article.source_type,
            "article_subtype": article.article_subtype,
            "player_canonical": article.player_canonical,
            "enqueued_at_utc": "2026-05-21T10:00:00Z",
            "schema_version": q.QUEUE_SCHEMA_VERSION,
        })
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [blob]
        mock_bucket_fn.return_value = mock_bucket
        out = q.drain(max_count=10)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].source_url, article.source_url)

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_drain_orders_newest_first(self, mock_bucket_fn):
        old_blob = MagicMock()
        old_blob.updated = datetime(2026, 5, 21, 3, 0, 0, tzinfo=timezone.utc)
        old_blob.download_as_text.return_value = json.dumps({
            "source_url": "https://hochi.news/g/old",
            "title": "old", "summary": "", "source_name": "スポーツ報知",
            "source_type": "rss", "article_subtype": "postgame",
            "player_canonical": [],
            "enqueued_at_utc": "2026-05-21T03:00:00Z",
            "schema_version": q.QUEUE_SCHEMA_VERSION,
        })
        new_blob = MagicMock()
        new_blob.updated = datetime(2026, 5, 22, 9, 30, 0, tzinfo=timezone.utc)
        new_blob.download_as_text.return_value = json.dumps({
            "source_url": "https://hochi.news/g/new",
            "title": "new", "summary": "", "source_name": "スポーツ報知",
            "source_type": "rss", "article_subtype": "postgame",
            "player_canonical": [],
            "enqueued_at_utc": "2026-05-22T09:30:00Z",
            "schema_version": q.QUEUE_SCHEMA_VERSION,
        })
        mock_bucket = MagicMock()
        # GCS returns lex order (old hash < new hash); drain must re-sort.
        mock_bucket.list_blobs.return_value = [old_blob, new_blob]
        mock_bucket_fn.return_value = mock_bucket
        out = q.drain(max_count=10)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].source_url, "https://hochi.news/g/new")
        self.assertEqual(out[1].source_url, "https://hochi.news/g/old")

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_drain_caps_at_max_count_keeping_newest(self, mock_bucket_fn):
        def _blob(hash_id: str, upload_dt: datetime) -> MagicMock:
            blob = MagicMock()
            blob.updated = upload_dt
            blob.download_as_text.return_value = json.dumps({
                "source_url": f"https://hochi.news/g/{hash_id}",
                "title": hash_id, "summary": "", "source_name": "スポーツ報知",
                "source_type": "rss", "article_subtype": "postgame",
                "player_canonical": [],
                "enqueued_at_utc": upload_dt.isoformat(),
                "schema_version": q.QUEUE_SCHEMA_VERSION,
            })
            return blob
        blobs = [
            _blob("a", datetime(2026, 5, 21, 3, 0, 0, tzinfo=timezone.utc)),
            _blob("b", datetime(2026, 5, 22, 9, 0, 0, tzinfo=timezone.utc)),
            _blob("c", datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)),
            _blob("d", datetime(2026, 5, 22, 9, 30, 0, tzinfo=timezone.utc)),
        ]
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = blobs
        mock_bucket_fn.return_value = mock_bucket
        out = q.drain(max_count=2)
        self.assertEqual(len(out), 2)
        # Newest two (d, b) — older c, a dropped.
        urls = {c.source_url for c in out}
        self.assertEqual(urls, {"https://hochi.news/g/d", "https://hochi.news/g/b"})

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_corrupt_entry_skipped(self, mock_bucket_fn):
        bad_blob = MagicMock()
        bad_blob.updated = datetime(2026, 5, 22, 9, 0, 0, tzinfo=timezone.utc)
        bad_blob.download_as_text.return_value = "{not valid json"
        good_blob = MagicMock()
        good_blob.updated = datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc)
        good_blob.download_as_text.return_value = json.dumps({
            "source_url": "https://hochi.news/g/2",
            "title": "戸郷投手",
            "summary": "",
            "source_name": "スポーツ報知",
            "source_type": "rss",
            "article_subtype": "postgame",
            "player_canonical": [],
            "enqueued_at_utc": "2026-05-21T10:00:00Z",
            "schema_version": q.QUEUE_SCHEMA_VERSION,
        })
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [bad_blob, good_blob]
        mock_bucket_fn.return_value = mock_bucket
        out = q.drain()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].source_url, "https://hochi.news/g/2")

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_gcs_exception_returns_empty(self, mock_bucket_fn):
        mock_bucket_fn.side_effect = RuntimeError("GCS list failure")
        self.assertEqual(q.drain(), [])


class MarkProcessedTests(unittest.TestCase):
    @patch("src.x_post_candidate_queue._get_bucket")
    def test_existing_entry_moved(self, mock_bucket_fn):
        mock_bucket = MagicMock()
        src_blob = MagicMock()
        src_blob.exists.return_value = True
        dst_blob = MagicMock()
        # bucket.blob() で src と dst を返し分ける
        mock_bucket.blob.side_effect = [src_blob, dst_blob]
        mock_bucket_fn.return_value = mock_bucket

        article = _make_article()
        self.assertTrue(q.mark_processed(article))
        mock_bucket.copy_blob.assert_called_once()
        src_blob.delete.assert_called_once()

    @patch("src.x_post_candidate_queue._get_bucket")
    def test_missing_src_returns_false(self, mock_bucket_fn):
        mock_bucket = MagicMock()
        src_blob = MagicMock()
        src_blob.exists.return_value = False
        mock_bucket.blob.side_effect = [src_blob, MagicMock()]
        mock_bucket_fn.return_value = mock_bucket

        article = _make_article()
        self.assertFalse(q.mark_processed(article))

    def test_empty_source_url_returns_false(self):
        article = _make_article(source_url="")
        self.assertFalse(q.mark_processed(article))


class SourceUrlHashTests(unittest.TestCase):
    def test_same_url_same_hash(self):
        a = q._source_url_hash("https://hochi.news/giants/1")
        b = q._source_url_hash("https://hochi.news/giants/1")
        self.assertEqual(a, b)

    def test_different_url_different_hash(self):
        a = q._source_url_hash("https://hochi.news/giants/1")
        b = q._source_url_hash("https://hochi.news/giants/2")
        self.assertNotEqual(a, b)

    def test_hash_length_16(self):
        h = q._source_url_hash("https://hochi.news/giants/1")
        self.assertEqual(len(h), 16)


if __name__ == "__main__":
    unittest.main()
