from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src import llm_call_dedupe


class LLMCallDedupeTests(unittest.TestCase):
    def test_compute_content_hash_deterministic(self):
        first = llm_call_dedupe.compute_content_hash(101, "本文です。")
        second = llm_call_dedupe.compute_content_hash(101, "本文です。")
        self.assertEqual(first, second)

    def test_compute_content_hash_different_for_different_body(self):
        first = llm_call_dedupe.compute_content_hash(101, "本文A")
        second = llm_call_dedupe.compute_content_hash(101, "本文B")
        self.assertNotEqual(first, second)

    def test_is_recently_processed_within_24h_returns_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            now = datetime(2026, 4, 27, 10, 0, tzinfo=llm_call_dedupe.JST)
            content_hash = llm_call_dedupe.compute_content_hash(101, "本文です。")
            llm_call_dedupe.record_call(
                101,
                content_hash,
                "generated",
                ledger_path=ledger_path,
                now=now - timedelta(hours=2),
            )
            self.assertTrue(
                llm_call_dedupe.is_recently_processed(
                    101,
                    content_hash,
                    ledger_path,
                    now=now,
                )
            )

    def test_is_recently_processed_after_24h_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            now = datetime(2026, 4, 27, 10, 0, tzinfo=llm_call_dedupe.JST)
            content_hash = llm_call_dedupe.compute_content_hash(101, "本文です。")
            llm_call_dedupe.record_call(
                101,
                content_hash,
                "generated",
                ledger_path=ledger_path,
                now=now - timedelta(hours=25),
            )
            self.assertFalse(
                llm_call_dedupe.is_recently_processed(
                    101,
                    content_hash,
                    ledger_path,
                    now=now,
                )
            )

    def test_is_recently_processed_different_hash_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            now = datetime(2026, 4, 27, 10, 0, tzinfo=llm_call_dedupe.JST)
            first_hash = llm_call_dedupe.compute_content_hash(101, "本文A")
            second_hash = llm_call_dedupe.compute_content_hash(101, "本文B")
            llm_call_dedupe.record_call(
                101,
                first_hash,
                "generated",
                ledger_path=ledger_path,
                now=now,
            )
            self.assertFalse(
                llm_call_dedupe.is_recently_processed(
                    101,
                    second_hash,
                    ledger_path,
                    now=now,
                )
            )

    def test_record_call_appends_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            content_hash = llm_call_dedupe.compute_content_hash(101, "本文です。")
            llm_call_dedupe.record_call(
                101,
                content_hash,
                "generated",
                ledger_path=ledger_path,
                provider="gemini",
                model="gemini-2.5-flash",
            )
            rows = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["post_id"], 101)
        self.assertEqual(rows[0]["content_hash"], content_hash)
        self.assertEqual(rows[0]["provider"], "gemini")

    def test_refused_cooldown_skips_within_24h(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            now = datetime(2026, 4, 27, 10, 0, tzinfo=llm_call_dedupe.JST)
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 101,
                        "ts": (now - timedelta(hours=6)).isoformat(),
                        "status": "refused",
                        "error": "hard_stop:freshness_window",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            matched = llm_call_dedupe.find_recent_refused_history(
                101,
                history_path=history_path,
                now=now,
            )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["status"], "refused")

    def test_refused_cooldown_releases_after_24h(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            now = datetime(2026, 4, 27, 10, 0, tzinfo=llm_call_dedupe.JST)
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 101,
                        "ts": (now - timedelta(hours=30)).isoformat(),
                        "status": "refused",
                        "error": "hard_stop:freshness_window",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            matched = llm_call_dedupe.find_recent_refused_history(
                101,
                history_path=history_path,
                now=now,
            )
        self.assertIsNone(matched)


if __name__ == "__main__":
    unittest.main()
