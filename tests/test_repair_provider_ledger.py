from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from src import repair_provider_ledger as ledger
from src.tools import draft_body_editor as dbe


FIXED_NOW = datetime.fromisoformat("2026-04-26T15:50:00+09:00")
HEADINGS = ("【試合結果】", "【ハイライト】", "【選手成績】", "【試合展開】")
CURRENT_BODY = (
    "【試合結果】\n"
    "本文Aです。\n"
    "【ハイライト】\n"
    "本文Bです。\n"
    "【選手成績】\n"
    "本文Cです。\n"
    "【試合展開】\n"
    "本文Dです。"
)
NEW_BODY = (
    "【試合結果】\n"
    "本文Aです。\n"
    "【ハイライト】\n"
    "本文Bです。\n"
    "【選手成績】\n"
    "本文Cです。\n"
    "【試合展開】\n"
    "本文Dです。"
)
SOURCE_BLOCK = "・本文A\n・本文B\n・本文C\n・本文D"


class RepairProviderLedgerTests(unittest.TestCase):
    def _entry(self, **overrides) -> ledger.RepairLedgerEntry:
        input_hash = overrides.pop("input_hash", ledger.compute_input_hash({"id": 123, "body": "seed"}))
        payload = {
            "schema_version": ledger.SCHEMA_VERSION,
            "run_id": "run-123",
            "lane": "repair",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "source_post_id": 123,
            "input_hash": input_hash,
            "output_hash": ledger.compute_output_hash("improved"),
            "artifact_uri": "file:///tmp/out.txt",
            "status": "shadow_only",
            "strict_pass": False,
            "error_code": None,
            "idempotency_key": ledger.make_idempotency_key(123, input_hash, "gemini"),
            "created_at": FIXED_NOW.isoformat(),
            "started_at": FIXED_NOW.isoformat(),
            "finished_at": FIXED_NOW.isoformat(),
            "metrics": {
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 0,
                "body_len_before": 100,
                "body_len_after": 85,
                "body_len_delta_pct": -0.15,
            },
            "provider_meta": {
                "raw_response_size": 8,
                "fallback_from": None,
                "fallback_reason": None,
                "quality_flags": [],
            },
        }
        payload.update(overrides)
        return ledger.RepairLedgerEntry(**payload)

    def _read_jsonl(self, path: Path) -> list[dict]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_schema_v0_missing_field_raises_error(self):
        with self.assertRaises(TypeError):
            ledger.RepairLedgerEntry(
                schema_version=ledger.SCHEMA_VERSION,
                run_id="run-123",
                lane="repair",
                provider="gemini",
                model="gemini-2.5-flash",
                source_post_id=123,
                input_hash="abc",
                output_hash="def",
                artifact_uri="file:///tmp/out.txt",
                status="shadow_only",
                strict_pass=False,
                error_code=None,
                idempotency_key="123:abc:gemini",
                created_at=FIXED_NOW.isoformat(),
                started_at=FIXED_NOW.isoformat(),
                metrics={},
                provider_meta={},
            )

    def test_jsonl_writer_appends_and_readback_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"
            writer = ledger.JsonlLedgerWriter(path)
            entry = self._entry()

            writer.write(entry)
            rows = self._read_jsonl(path)

        self.assertEqual(rows, [entry.to_dict()])

    def test_jsonl_writer_duplicate_idempotency_key_raises_lock_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.jsonl"
            writer = ledger.JsonlLedgerWriter(path)
            first = self._entry()
            second = self._entry(run_id="run-456")

            writer.write(first)
            with self.assertRaises(ledger.LedgerLockError):
                writer.write(second)

    def test_judge_strict_pass_representative_patterns(self):
        base_entry = self._entry()
        cases = [
            ("all_true_in_range", True, True, True, -0.15, True),
            ("hard_stop_false", False, True, True, -0.15, False),
            ("fact_check_false", True, False, True, -0.15, False),
            ("forbidden_false", True, True, False, -0.15, False),
            ("delta_too_small", True, True, True, -0.21, False),
            ("delta_too_large", True, True, True, 0.36, False),
            ("delta_lower_bound", True, True, True, -0.20, True),
            ("delta_upper_bound", True, True, True, 0.35, True),
        ]

        for label, hard_stop, fact_check, no_new_forbidden, delta_pct, expected in cases:
            with self.subTest(label=label):
                actual = ledger.judge_strict_pass(
                    base_entry,
                    hard_stop_flags_resolved=hard_stop,
                    fact_check_pass=fact_check,
                    no_new_forbidden=no_new_forbidden,
                    body_len_delta_pct=delta_pct,
                )
                self.assertEqual(actual, expected)

    def test_compute_body_len_delta_pct_reports_negative_15_percent(self):
        self.assertEqual(ledger.compute_body_len_delta_pct(100, 85), -0.15)

    def test_fallback_fields_are_preserved_in_entry(self):
        entry = self._entry(
            provider="openai_api",
            model="gpt-4o-mini",
            provider_meta={
                "raw_response_size": 12,
                "fallback_from": "codex",
                "fallback_reason": "gemini_timeout",
                "quality_flags": ["fallback_used"],
            },
        )

        payload = entry.to_dict()

        self.assertEqual(payload["provider"], "openai_api")
        self.assertEqual(payload["provider_meta"]["fallback_from"], "codex")
        self.assertEqual(payload["provider_meta"]["fallback_reason"], "gemini_timeout")

    def test_firestore_writer_stub_calls_mock_interface(self):
        client = Mock()
        collection_ref = client.collection.return_value
        document_ref = collection_ref.document.return_value
        writer = ledger.FirestoreLedgerWriter(client, "repair-ledger")
        entry = self._entry()

        writer.write(entry)

        client.collection.assert_called_once_with("repair-ledger")
        collection_ref.document.assert_called_once_with(entry.idempotency_key)
        document_ref.set.assert_called_once_with(entry.to_dict())

    def test_draft_body_editor_dry_run_writes_shadow_only_ledger_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current_path = Path(tmpdir) / "current.txt"
            source_path = Path(tmpdir) / "source.txt"
            out_path = Path(tmpdir) / "out.txt"
            current_path.write_text(CURRENT_BODY, encoding="utf-8")
            source_path.write_text(SOURCE_BLOCK, encoding="utf-8")
            argv = [
                "--post-id", "321",
                "--subtype", "postgame",
                "--fail", "density",
                "--current-body", str(current_path),
                "--source-block", str(source_path),
                "--out", str(out_path),
                "--dry-run",
            ]
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch("src.tools.draft_body_editor._lookup_required_headings", return_value=HEADINGS), \
                 patch("src.tools.draft_body_editor.call_gemini", return_value=NEW_BODY), \
                 patch("src.tools.draft_body_editor.repair_provider_ledger._now_jst", return_value=FIXED_NOW), \
                 patch.dict(
                     os.environ,
                     {
                         "GEMINI_API_KEY": "test-key",
                         ledger.ENV_LEDGER_DIR: tmpdir,
                     },
                     clear=False,
                 ), \
                 patch("sys.stdout", stdout), \
                 patch("sys.stderr", stderr):
                code = dbe.main(argv)

            self.assertEqual(code, 0)
            ledger_path = Path(tmpdir) / "2026-04-26.jsonl"
            rows = self._read_jsonl(ledger_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "shadow_only")
            self.assertTrue(rows[0]["strict_pass"])
            self.assertEqual(rows[0]["provider"], "gemini")
            self.assertEqual(rows[0]["model"], "gemini-2.5-flash")
            self.assertEqual(rows[0]["metrics"]["body_len_delta_pct"], len(NEW_BODY) / len(CURRENT_BODY) - 1)


if __name__ == "__main__":
    unittest.main()
