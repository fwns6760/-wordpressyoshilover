import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools import run_x_post_queue_smoke as smoke
from src.x_post_queue_ledger import XPostLedgerEntry, XPostQueueEntry, compute_candidate_hash


FIXED_NOW = "2026-04-26T16:00:00+09:00"


def _backup_payload(post_id: int, *, subtype: str = "postgame_result", title: str | None = None) -> dict:
    return {
        "id": post_id,
        "status": "draft",
        "link": f"https://yoshilover.com/?p={post_id}",
        "title": {"rendered": title or f"巨人ニュース {post_id}"},
        "excerpt": {"rendered": "<p>巨人が勝利した。終盤の流れを押し切った。</p>"},
        "content": {"rendered": "<p>巨人が勝利した。終盤の流れを押し切った。</p>"},
        "meta": {"article_subtype": subtype},
    }


class RunXPostQueueSmokeTests(unittest.TestCase):
    def test_dry_run_outputs_queue_judgments_without_writing_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backups = {
                1001: root / "1001.json",
                1002: root / "1002.json",
                1003: root / "1003.json",
            }
            backups[1001].write_text(json.dumps(_backup_payload(1001), ensure_ascii=False), encoding="utf-8")
            backups[1002].write_text(
                json.dumps(_backup_payload(1002, subtype="breaking_notice", title="速報: 巨人ニュース 1002"), ensure_ascii=False),
                encoding="utf-8",
            )
            backups[1003].write_text(json.dumps(_backup_payload(1003), ensure_ascii=False), encoding="utf-8")

            history_path = root / "history.jsonl"
            history_rows = [
                {
                    "post_id": 1001,
                    "ts": "2026-04-26T15:30:00+09:00",
                    "status": "sent",
                    "backup_path": str(backups[1001]),
                },
                {
                    "post_id": 1002,
                    "ts": "2026-04-26T01:00:00+09:00",
                    "status": "sent",
                    "backup_path": str(backups[1002]),
                },
                {
                    "post_id": 1003,
                    "ts": "2026-04-26T15:40:00+09:00",
                    "status": "sent",
                    "backup_path": str(backups[1003]),
                },
            ]
            history_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in history_rows) + "\n",
                encoding="utf-8",
            )

            queue_path = root / "queue.jsonl"
            candidate_hash = compute_candidate_hash(
                1001,
                "https://yoshilover.com/?p=1001",
                "巨人が勝利した。終盤の流れを押し切った。",
            )
            duplicate_entry = XPostQueueEntry(
                queue_id="queue-existing",
                candidate_hash=candidate_hash,
                source_post_id=1001,
                source_canonical_url="https://yoshilover.com/?p=1001",
                title="巨人ニュース 1001",
                post_text="巨人ニュース 1001\nhttps://yoshilover.com/?p=1001",
                post_category="postgame",
                ttl="2026-04-27T15:30:00+09:00",
                status="queued",
                queued_at="2026-04-26T15:30:00+09:00",
                scheduled_at="2026-04-26T15:30:00+09:00",
            )
            queue_path.write_text(json.dumps(duplicate_entry.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")
            queue_before = queue_path.read_text(encoding="utf-8")

            ledger_path = root / "ledger.jsonl"
            posted_entry = XPostLedgerEntry(
                run_id="run-1",
                queue_id="posted-different",
                account_id="main",
                status="posted",
                x_post_id="123",
                x_user_id="456",
                started_at="2026-04-26T10:00:00+09:00",
                finished_at="2026-04-26T10:05:00+09:00",
            )
            ledger_path.write_text(json.dumps(posted_entry.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")
            ledger_before = ledger_path.read_text(encoding="utf-8")

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = smoke.main(
                    [
                        "--dry-run",
                        "--history-path",
                        str(history_path),
                        "--queue-path",
                        str(queue_path),
                        "--ledger-path",
                        str(ledger_path),
                        "--limit",
                        "5",
                        "--daily-cap",
                        "1",
                        "--breaking-excluded",
                        "--now-iso",
                        FIXED_NOW,
                    ]
                )
            queue_after = queue_path.read_text(encoding="utf-8")
            ledger_after = ledger_path.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(len(payload["items"]), 3)
        self.assertEqual(payload["items"][0]["status"], "skipped_duplicate")
        self.assertEqual(payload["items"][1]["status"], "expired")
        self.assertEqual(payload["items"][2]["status"], "skipped_daily_cap")
        self.assertEqual(queue_after, queue_before)
        self.assertEqual(ledger_after, ledger_before)
        self.assertFalse(hasattr(smoke, "tweepy"))

    def test_cli_requires_dry_run_flag(self):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = smoke.main([])

        self.assertEqual(code, 2)
        self.assertIn("only --dry-run is supported", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
