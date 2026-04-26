import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src.x_post_queue_ledger import (
    FirestoreLedgerWriter,
    FirestoreQueueWriter,
    JST,
    JsonlLedgerWriter,
    JsonlQueueWriter,
    QUEUE_STATUS_POSTED,
    QUEUE_STATUS_QUEUED,
    QUEUE_STATUS_SKIPPED_DAILY_CAP,
    XPostLedgerEntry,
    XPostQueueEntry,
    compute_candidate_hash,
    default_ttl_seconds,
    judge_daily_cap,
    judge_dedup,
    judge_ttl_expired,
    make_idempotency_key,
)


FIXED_NOW = datetime(2026, 4, 26, 16, 0, tzinfo=JST)


class XPostQueueLedgerTests(unittest.TestCase):
    def _queue_entry(self, **overrides) -> XPostQueueEntry:
        base = {
            "queue_id": "queue-1",
            "candidate_hash": compute_candidate_hash(63105, "https://yoshilover.com/63105", "巨人が勝利"),
            "source_post_id": 63105,
            "source_canonical_url": "https://yoshilover.com/63105",
            "title": "巨人が勝利",
            "post_text": "巨人が勝利\nhttps://yoshilover.com/63105",
            "post_category": "postgame",
            "media_urls": ("https://example.com/image.jpg",),
            "account_id": "main",
            "ttl": (FIXED_NOW + timedelta(hours=24)).isoformat(),
            "status": QUEUE_STATUS_QUEUED,
            "queued_at": FIXED_NOW.isoformat(),
            "scheduled_at": FIXED_NOW.isoformat(),
            "posted_at": None,
            "x_post_id": None,
            "retry_count": 0,
            "last_error_code": None,
            "last_error_message": None,
            "idempotency_key": "",
        }
        base.update(overrides)
        return XPostQueueEntry(**base)

    def _ledger_entry(self, **overrides) -> XPostLedgerEntry:
        base = {
            "run_id": "run-1",
            "queue_id": make_idempotency_key(
                compute_candidate_hash(63105, "https://yoshilover.com/63105", "巨人が勝利"),
                "main",
            ),
            "account_id": "main",
            "status": QUEUE_STATUS_POSTED,
            "x_post_id": "1234567890",
            "x_user_id": "999",
            "started_at": FIXED_NOW.isoformat(),
            "finished_at": FIXED_NOW.isoformat(),
            "rate_limit_remaining": 15,
            "rate_limit_reset": (FIXED_NOW + timedelta(minutes=15)).isoformat(),
            "error_code": None,
            "error_message": None,
        }
        base.update(overrides)
        return XPostLedgerEntry(**base)

    def test_queue_schema_v0_serializes_all_fields(self):
        entry = self._queue_entry()
        payload = entry.to_dict()

        self.assertEqual(
            list(payload.keys()),
            [
                "schema_version",
                "queue_id",
                "candidate_hash",
                "source_post_id",
                "source_canonical_url",
                "title",
                "post_text",
                "post_category",
                "media_urls",
                "account_id",
                "ttl",
                "status",
                "queued_at",
                "scheduled_at",
                "posted_at",
                "x_post_id",
                "retry_count",
                "last_error_code",
                "last_error_message",
                "idempotency_key",
            ],
        )
        self.assertEqual(payload["schema_version"], "x_post_queue_v0")
        self.assertEqual(payload["media_urls"], ["https://example.com/image.jpg"])
        self.assertTrue(payload["idempotency_key"].endswith(":main"))

    def test_ledger_schema_v0_serializes_all_fields(self):
        entry = self._ledger_entry()
        payload = entry.to_dict()

        self.assertEqual(
            list(payload.keys()),
            [
                "schema_version",
                "run_id",
                "queue_id",
                "account_id",
                "status",
                "x_post_id",
                "x_user_id",
                "started_at",
                "finished_at",
                "rate_limit_remaining",
                "rate_limit_reset",
                "error_code",
                "error_message",
            ],
        )
        self.assertEqual(payload["schema_version"], "x_post_ledger_v0")

    def test_jsonl_queue_writer_append_and_read_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "queue.jsonl"
            writer = JsonlQueueWriter(path)

            writer.append(self._queue_entry())
            rows = writer.read_entries()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source_post_id, 63105)
        self.assertEqual(rows[0].post_category, "postgame")

    def test_jsonl_ledger_writer_append_and_read_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"
            writer = JsonlLedgerWriter(path)

            writer.append(self._ledger_entry())
            rows = writer.read_entries()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, QUEUE_STATUS_POSTED)
        self.assertEqual(rows[0].x_post_id, "1234567890")

    def test_firestore_stubs_keep_entries_in_memory(self):
        queue_writer = FirestoreQueueWriter(client=None, collection="queue")
        ledger_writer = FirestoreLedgerWriter(client=None, collection="ledger")

        queue_writer.append(self._queue_entry())
        ledger_writer.append(self._ledger_entry())

        self.assertEqual(len(queue_writer.read_entries()), 1)
        self.assertEqual(len(ledger_writer.read_entries()), 1)

    def test_duplicate_idempotency_key_is_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            queue_writer = JsonlQueueWriter(queue_path)
            ledger_writer = JsonlLedgerWriter(ledger_path)
            entry = self._queue_entry()

            queue_writer.append(entry)
            result = judge_dedup(queue_writer, ledger_writer, entry.idempotency_key)

        self.assertEqual(result, "duplicate")

    def test_duplicate_posted_ledger_idempotency_key_is_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_writer = JsonlQueueWriter(Path(tmpdir) / "queue.jsonl")
            ledger_writer = JsonlLedgerWriter(Path(tmpdir) / "ledger.jsonl")
            entry = self._queue_entry()
            ledger_writer.append(self._ledger_entry(queue_id=entry.idempotency_key))

            result = judge_dedup(queue_writer, ledger_writer, entry.idempotency_key)

        self.assertEqual(result, "duplicate")

    def test_daily_cap_reached_returns_skipped_daily_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_writer = JsonlLedgerWriter(Path(tmpdir) / "ledger.jsonl")
            ledger_writer.append(self._ledger_entry())

            result = judge_daily_cap(ledger_writer, "main", 1, now=FIXED_NOW)

        self.assertEqual(result, QUEUE_STATUS_SKIPPED_DAILY_CAP)

    def test_breaking_category_can_bypass_daily_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_writer = JsonlLedgerWriter(Path(tmpdir) / "ledger.jsonl")
            ledger_writer.append(self._ledger_entry())

            result = judge_daily_cap(
                ledger_writer,
                "main",
                1,
                True,
                category="breaking",
                now=FIXED_NOW,
            )

        self.assertEqual(result, "ok")

    def test_ttl_expired_returns_true(self):
        entry = self._queue_entry(ttl=(FIXED_NOW - timedelta(minutes=1)).isoformat())
        self.assertTrue(judge_ttl_expired(entry, FIXED_NOW))

    def test_candidate_hash_is_deterministic(self):
        first = compute_candidate_hash(63105, "https://yoshilover.com/63105", "巨人が勝利")
        second = compute_candidate_hash(63105, "https://yoshilover.com/63105", "巨人が勝利")
        third = compute_candidate_hash(63105, "https://yoshilover.com/63105", "巨人が敗戦")

        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_default_ttl_seconds_returns_expected_values_for_all_queue_categories(self):
        self.assertEqual(default_ttl_seconds("lineup"), 24 * 60 * 60)
        self.assertEqual(default_ttl_seconds("postgame"), 24 * 60 * 60)
        self.assertEqual(default_ttl_seconds("breaking"), 3 * 60 * 60)
        self.assertEqual(default_ttl_seconds("notice"), 24 * 60 * 60)
        self.assertEqual(default_ttl_seconds("comment"), 72 * 60 * 60)


if __name__ == "__main__":
    unittest.main()
