import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import publish_notice_scanner as scanner


NOW = datetime(2026, 5, 2, 12, 0, tzinfo=scanner.JST)


class PublishNoticeLedgerTTLPruneTests(unittest.TestCase):
    def _post(self, **overrides):
        payload = {
            "id": 901,
            "title": {"rendered": "レビュー待ち記事"},
            "excerpt": {"rendered": "<p>レビュー待ち記事の要約。</p>"},
            "content": {"rendered": "<p>本文1段落目。</p>"},
            "link": "https://yoshilover.com/draft-901/",
            "date": "2026-04-20T10:00:00+09:00",
            "status": "draft",
            "meta": {"article_subtype": "postgame"},
        }
        payload.update(overrides)
        return payload

    def _guarded_entry(self, **overrides):
        payload = {
            "post_id": 901,
            "ts": NOW.isoformat(),
            "status": "refused",
            "judgment": "yellow",
            "publishable": True,
            "cleanup_required": False,
            "cleanup_success": False,
            "hold_reason": "backlog_only",
        }
        payload.update(overrides)
        return payload

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _capture_log_events(self):
        events: list[dict[str, object]] = []

        def fake_log_event(event: str, **payload):
            events.append({"event": event, **payload})

        return events, fake_log_event

    def _ttl_events(self, events: list[dict[str, object]]) -> list[dict[str, object]]:
        return [event for event in events if event["event"] == "permanent_dedup_ttl_prune"]

    def _run_guarded_scan(
        self,
        root: Path,
        *,
        ledger_payload: dict[str, object] | None = None,
        guarded_entries: list[dict[str, object]] | None = None,
        ttl_enabled: bool = True,
        ttl_days: str = "7",
        max_per_run: int | None = None,
        fetch_post_detail=None,
    ):
        guarded_history_path = root / "guarded_publish_history.jsonl"
        guarded_cursor_path = root / "guarded_publish_history_cursor.txt"
        history_path = root / "history.json"
        queue_path = root / "queue.jsonl"
        ledger_path = root / "publish_notice_old_candidate_once.json"
        guarded_entries = guarded_entries or []
        guarded_history_path.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in guarded_entries),
            encoding="utf-8",
        )
        if ledger_payload is not None:
            self._write_json(ledger_path, ledger_payload)

        env = {
            "ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE": "1",
            "PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS": "3",
            "PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_PATH": str(ledger_path),
        }
        if ttl_enabled:
            env["ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL"] = "1"
            env["PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL_DAYS"] = ttl_days

        events, fake_log_event = self._capture_log_events()
        with patch.dict("os.environ", env, clear=False), patch.object(
            scanner,
            "_log_event",
            side_effect=fake_log_event,
        ):
            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                cursor_path=guarded_cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=fetch_post_detail or (lambda base, post_id: self._post(id=post_id)),
                now=lambda: NOW,
                max_per_run=max_per_run,
            )

        return result, ledger_path, history_path, queue_path, events

    def _run_outer_scan_with_class_reserve(
        self,
        root: Path,
        *,
        ledger_payload: dict[str, object],
    ):
        cursor_path = root / "cursor.txt"
        history_path = root / "history.json"
        queue_path = root / "queue.jsonl"
        guarded_history_path = root / "guarded_publish_history.jsonl"
        guarded_cursor_path = root / "guarded_cursor.txt"
        ledger_path = root / "publish_notice_old_candidate_once.json"
        cursor_path.write_text("2026-05-02T08:00:00+09:00\n", encoding="utf-8")
        history_path.write_text("{}\n", encoding="utf-8")
        guarded_history_path.write_text("", encoding="utf-8")
        self._write_json(ledger_path, ledger_payload)

        env = {
            "ENABLE_PUBLISH_NOTICE_CLASS_RESERVE": "1",
            "ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE": "1",
            "ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL": "1",
            "PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL_DAYS": "7",
            "PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_PATH": str(ledger_path),
        }
        events, fake_log_event = self._capture_log_events()
        with patch.dict("os.environ", env, clear=False), patch.object(
            scanner,
            "_log_event",
            side_effect=fake_log_event,
        ):
            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                guarded_publish_history_path=guarded_history_path,
                guarded_cursor_path=guarded_cursor_path,
                fetch=lambda base, after: [],
                now=lambda: NOW,
            )

        return result, ledger_path, events

    def test_ttl_expired_entry_is_pruned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, _, _, events = self._run_guarded_scan(
                Path(tmpdir),
                ledger_payload={"901": {"ts": "2026-04-25T11:59:59+09:00"}},
            )
            ledger_after = self._read_json(ledger_path)

        self.assertEqual(result.old_candidate_ledger_after, {})
        self.assertTrue(result.old_candidate_ledger_write_needed)
        self.assertEqual(ledger_after, {})
        self.assertEqual(
            self._ttl_events(events),
            [
                {
                    "event": "permanent_dedup_ttl_prune",
                    "count": 1,
                    "cutoff_ts": "2026-04-25T12:00:00+09:00",
                }
            ],
        )

    def test_within_ttl_entry_is_kept(self):
        ledger_payload = {"901": {"ts": "2026-04-25T12:00:00+09:00"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, _, _, events = self._run_guarded_scan(
                Path(tmpdir),
                ledger_payload=ledger_payload,
            )
            ledger_after = self._read_json(ledger_path)

        self.assertEqual(result.old_candidate_ledger_after, ledger_payload)
        self.assertFalse(result.old_candidate_ledger_write_needed)
        self.assertEqual(ledger_after, ledger_payload)
        self.assertEqual(self._ttl_events(events)[0]["count"], 0)

    def test_flag_off_baseline_no_prune(self):
        ledger_payload = {"901": {"ts": "2026-04-20T10:00:00+09:00"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, _, _, events = self._run_guarded_scan(
                Path(tmpdir),
                ledger_payload=ledger_payload,
                ttl_enabled=False,
            )
            ledger_after = self._read_json(ledger_path)

        self.assertEqual(result.old_candidate_ledger_after, ledger_payload)
        self.assertFalse(result.old_candidate_ledger_write_needed)
        self.assertEqual(ledger_after, ledger_payload)
        self.assertEqual(self._ttl_events(events), [])

    def test_empty_ledger_no_op(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, _, _, events = self._run_guarded_scan(Path(tmpdir))

        self.assertEqual(result.old_candidate_ledger_after, {})
        self.assertFalse(result.old_candidate_ledger_write_needed)
        self.assertFalse(ledger_path.exists())
        self.assertEqual(self._ttl_events(events)[0]["count"], 0)

    def test_all_expired_ledger_fully_cleared(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, _, _, events = self._run_guarded_scan(
                Path(tmpdir),
                ledger_payload={
                    "901": {"ts": "2026-04-20T10:00:00+09:00"},
                    "902": "2026-04-18T10:00:00+09:00",
                },
                max_per_run=0,
            )
            ledger_after = self._read_json(ledger_path)

        self.assertEqual(result.old_candidate_ledger_after, {})
        self.assertTrue(result.old_candidate_ledger_write_needed)
        self.assertEqual(ledger_after, {})
        self.assertEqual(self._ttl_events(events)[0]["count"], 2)

    def test_mixed_ttl_correct_partial_prune(self):
        ledger_payload = {
            "901": {"ts": "2026-04-24T12:00:00+09:00"},
            "902": {"ts": "2026-04-25T12:00:00+09:00"},
            "903": "2026-04-26T12:00:00+09:00",
            "904": "2026-04-20T12:00:00+09:00",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, _, _, events = self._run_guarded_scan(
                Path(tmpdir),
                ledger_payload=ledger_payload,
            )
            ledger_after = self._read_json(ledger_path)

        self.assertEqual(
            result.old_candidate_ledger_after,
            {
                "902": {"ts": "2026-04-25T12:00:00+09:00"},
                "903": "2026-04-26T12:00:00+09:00",
            },
        )
        self.assertEqual(ledger_after, result.old_candidate_ledger_after)
        self.assertEqual(self._ttl_events(events)[0]["count"], 2)

    def test_size_invariant_after_prune(self):
        ledger_payload = {
            "901": {"ts": "2026-04-20T10:00:00+09:00"},
            "902": {"ts": "2026-04-26T10:00:00+09:00"},
            "903": "2026-04-28T10:00:00+09:00",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ledger_path = root / "publish_notice_old_candidate_once.json"
            self._write_json(ledger_path, ledger_payload)
            size_before = ledger_path.stat().st_size
            _, ledger_path, events = self._run_outer_scan_with_class_reserve(
                root,
                ledger_payload=ledger_payload,
            )
            size_after = ledger_path.stat().st_size
            ledger_after = self._read_json(ledger_path)

        self.assertLessEqual(size_after, size_before)
        self.assertEqual(
            ledger_after,
            {
                "902": {"ts": "2026-04-26T10:00:00+09:00"},
                "903": "2026-04-28T10:00:00+09:00",
            },
        )
        self.assertEqual(self._ttl_events(events)[0]["count"], 1)

    def test_prune_does_not_touch_non_old_candidate_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, history_path, queue_path, events = self._run_guarded_scan(
                Path(tmpdir),
                ledger_payload={"901": {"ts": "2026-04-20T10:00:00+09:00"}},
                guarded_entries=[
                    self._guarded_entry(
                        post_id=902,
                        judgment="review",
                        hold_reason="cleanup_required",
                    )
                ],
                fetch_post_detail=lambda base, post_id: self._post(id=post_id),
            )
            queue_rows = [
                json.loads(line)
                for line in queue_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ledger_after = self._read_json(ledger_path)
            history_after = self._read_json(history_path)

        self.assertEqual([request.post_id for request in result.emitted], [902])
        self.assertEqual(result.skipped, [])
        self.assertEqual(ledger_after, {})
        self.assertEqual(list(history_after.keys()), ["902"])
        self.assertEqual(queue_rows[0]["reason"], "cleanup_required")
        self.assertTrue(str(result.emitted[0].subject_override).startswith("【要review】"))
        self.assertEqual(self._ttl_events(events)[0]["count"], 1)

    def test_ts_field_missing_safely_skipped(self):
        ledger_payload = {
            "901": {},
            "902": {"ts": "2026-04-20T10:00:00+09:00"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result, ledger_path, _, _, events = self._run_guarded_scan(
                Path(tmpdir),
                ledger_payload=ledger_payload,
            )
            ledger_after = self._read_json(ledger_path)

        self.assertEqual(result.old_candidate_ledger_after, {"901": {}})
        self.assertEqual(ledger_after, {"901": {}})
        self.assertTrue(result.old_candidate_ledger_write_needed)
        self.assertEqual(self._ttl_events(events)[0]["count"], 1)


if __name__ == "__main__":
    unittest.main()
