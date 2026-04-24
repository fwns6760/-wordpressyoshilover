from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src import nucleus_ledger_emitter as emitter


class NucleusLedgerEmitterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 4, 24, 12, 30, tzinfo=emitter.JST)

    def _meta(self, **overrides) -> emitter.DraftMeta:
        payload = {
            "draft_id": 63175,
            "candidate_key": "transaction_notice:20260420:山瀬慎之助+丸佳浩:register_deregister",
            "subtype": "lineup",
            "source_trust": "primary",
            "source_family": "npb_roster",
            "chosen_lane": "fixed",
            "chosen_model": None,
            "prompt_version": "v1",
            "template_version": "notice_v1",
        }
        payload.update(overrides)
        return emitter.DraftMeta(**payload)

    def _read_jsonl(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_resolve_sink_dir_defaults_to_repo_logs_directory(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(emitter.ENV_SINK_DIR, None)
            self.assertEqual(emitter.resolve_sink_dir(), emitter.DEFAULT_SINK_DIR)

    def test_resolve_sink_dir_uses_env_override(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_SINK_DIR: tmpdir}, clear=False
        ):
            self.assertEqual(emitter.resolve_sink_dir(), Path(tmpdir))

    def test_resolve_sink_dir_argument_override_beats_env(self):
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as override_dir, patch.dict(
            os.environ, {emitter.ENV_SINK_DIR: tmpdir}, clear=False
        ):
            self.assertEqual(emitter.resolve_sink_dir(override_dir), Path(override_dir))

    def test_build_ledger_entry_populates_required_fields(self):
        entry = emitter.build_ledger_entry(
            self._meta(),
            "岡本和真 4番起用",
            "岡本和真は4番で先発出場するオーダーに入った。",
            now=self.now,
        )

        self.assertEqual(entry["date"], "2026-04-24")
        self.assertEqual(entry["draft_id"], 63175)
        self.assertEqual(entry["candidate_key"], self._meta().candidate_key)
        self.assertEqual(entry["subtype"], "lineup")
        self.assertEqual(entry["source_trust"], "primary")
        self.assertEqual(entry["source_family"], "npb_roster")
        self.assertEqual(entry["chosen_lane"], "fixed")
        self.assertEqual(entry["prompt_version"], "v1")
        self.assertEqual(entry["template_version"], "notice_v1")
        self.assertEqual(entry["outcome"], "accept_draft")
        self.assertEqual(entry["repair_applied"], "no")
        self.assertEqual(entry["repair_actions"], [])

    def test_build_ledger_entry_uses_adapter_outputs(self):
        entry = emitter.build_ledger_entry(
            self._meta(),
            "岡本和真 4番起用",
            "坂本勇人は3番で先発出場する。",
            now=self.now,
        )

        self.assertEqual(entry["fail_tags"], ["title_body_mismatch"])
        self.assertEqual(entry["context_flags"], ["ctx_subject_absent"])

    def test_build_ledger_entry_aligned_result_keeps_fail_tags_empty(self):
        entry = emitter.build_ledger_entry(
            self._meta(),
            "岡本和真 4番起用",
            "岡本和真は4番で先発出場するオーダーに入った。",
            now=self.now,
        )

        self.assertEqual(entry["fail_tags"], [])
        self.assertEqual(entry["context_flags"], [])

    def test_build_ledger_entry_subject_absent_maps_to_expected_flags(self):
        entry = emitter.build_ledger_entry(
            self._meta(),
            "岡本和真 4番起用",
            "坂本勇人は3番で先発出場する。",
            now=self.now,
        )

        self.assertEqual(entry["fail_tags"], ["title_body_mismatch"])
        self.assertEqual(entry["context_flags"], ["ctx_subject_absent"])

    def test_emit_returns_gate_off_when_env_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {}, clear=False):
            os.environ.pop(emitter.ENV_EMIT_ENABLED, None)
            sink_root = Path(tmpdir) / "ledger"
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                sink_dir=sink_root,
                now=self.now,
            )

        self.assertEqual(result.status, "gate_off")
        self.assertIsNone(result.entry)
        self.assertFalse(sink_root.exists())

    def test_emit_appends_jsonl_when_env_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            sink_root = Path(tmpdir) / "ledger"
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                sink_dir=sink_root,
                now=self.now,
            )
            assert result.sink_path is not None
            rows = self._read_jsonl(result.sink_path)

        self.assertEqual(result.status, "emitted")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["draft_id"], 63175)

    def test_emit_enabled_argument_true_forces_append_without_env(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {}, clear=False):
            os.environ.pop(emitter.ENV_EMIT_ENABLED, None)
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                enabled=True,
                sink_dir=tmpdir,
                now=self.now,
            )
            sink_exists = result.sink_path is not None and result.sink_path.exists()

        self.assertEqual(result.status, "emitted")
        self.assertTrue(sink_exists)

    def test_emit_enabled_argument_false_forces_gate_off(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            sink_root = Path(tmpdir) / "ledger"
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                enabled=False,
                sink_dir=sink_root,
                now=self.now,
            )

        self.assertEqual(result.status, "gate_off")
        self.assertFalse(sink_root.exists())

    def test_emit_uses_sink_dir_override(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            sink_root = Path(tmpdir) / "custom-ledger"
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                sink_dir=sink_root,
                now=self.now,
            )

        self.assertEqual(result.status, "emitted")
        assert result.sink_path is not None
        self.assertEqual(result.sink_path.parent, sink_root)

    def test_emit_consecutive_calls_append_two_lines_to_same_file(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            sink_root = Path(tmpdir) / "ledger"
            first = emitter.emit_nucleus_ledger_entry(
                self._meta(draft_id=1),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                sink_dir=sink_root,
                now=self.now,
            )
            second = emitter.emit_nucleus_ledger_entry(
                self._meta(draft_id=2),
                "坂本勇人 3安打 3打点",
                "坂本勇人は3安打3打点の活躍で、巨人の3-2勝利を導いた。",
                sink_dir=sink_root,
                now=self.now,
            )
            assert first.sink_path is not None
            rows = self._read_jsonl(first.sink_path)

        assert second.sink_path is not None
        self.assertEqual(first.sink_path, second.sink_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["draft_id"] for row in rows], [1, 2])

    def test_emit_uses_separate_files_across_jst_date_boundary(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            sink_root = Path(tmpdir) / "ledger"
            before_midnight = datetime(2026, 4, 24, 23, 59, tzinfo=emitter.JST)
            after_midnight = before_midnight + timedelta(minutes=2)
            first = emitter.emit_nucleus_ledger_entry(
                self._meta(draft_id=1),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                sink_dir=sink_root,
                now=before_midnight,
            )
            second = emitter.emit_nucleus_ledger_entry(
                self._meta(draft_id=2),
                "坂本勇人 3安打 3打点",
                "坂本勇人は3安打3打点の活躍で、巨人の3-2勝利を導いた。",
                sink_dir=sink_root,
                now=after_midnight,
            )

        assert first.sink_path is not None
        assert second.sink_path is not None
        self.assertNotEqual(first.sink_path, second.sink_path)
        self.assertEqual(first.sink_path.name, "2026-04-24.jsonl")
        self.assertEqual(second.sink_path.name, "2026-04-25.jsonl")

    def test_emit_integration_smoke_persists_validator_and_adapter_output(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "坂本勇人は3番で先発出場する。",
                sink_dir=tmpdir,
                now=self.now,
            )
            assert result.sink_path is not None
            row = self._read_jsonl(result.sink_path)[0]

        self.assertEqual(row["fail_tags"], ["title_body_mismatch"])
        self.assertEqual(row["context_flags"], ["ctx_subject_absent"])

    def test_emit_creates_missing_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            sink_root = Path(tmpdir) / "missing" / "nested" / "ledger"
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                sink_dir=sink_root,
                now=self.now,
            )
            sink_exists = sink_root.exists()

        self.assertEqual(result.status, "emitted")
        self.assertTrue(sink_exists)

    def test_emitted_entry_contains_core_json_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ, {emitter.ENV_EMIT_ENABLED: "1"}, clear=False
        ):
            result = emitter.emit_nucleus_ledger_entry(
                self._meta(),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                sink_dir=tmpdir,
                now=self.now,
            )
            assert result.sink_path is not None
            row = self._read_jsonl(result.sink_path)[0]

        self.assertIn("date", row)
        self.assertIn("draft_id", row)
        self.assertIn("fail_tags", row)
        self.assertIn("context_flags", row)
        self.assertIn("outcome", row)

    def test_build_ledger_entry_uses_env_fallback_for_prompt_and_template_versions(self):
        with patch.dict(
            os.environ,
            {
                emitter.ENV_PROMPT_VERSION: "env-prompt-v2",
                emitter.ENV_TEMPLATE_VERSION: "env-template-v2",
            },
            clear=False,
        ):
            entry = emitter.build_ledger_entry(
                self._meta(prompt_version=None, template_version=None),
                "岡本和真 4番起用",
                "岡本和真は4番で先発出場するオーダーに入った。",
                now=self.now,
            )

        self.assertEqual(entry["prompt_version"], "env-prompt-v2")
        self.assertEqual(entry["template_version"], "env-template-v2")

    def test_build_ledger_entry_normalizes_blank_optional_fields_to_none(self):
        entry = emitter.build_ledger_entry(
            self._meta(candidate_key=" ", source_family=" ", chosen_model=" "),
            "岡本和真 4番起用",
            "岡本和真は4番で先発出場するオーダーに入った。",
            now=self.now,
        )

        self.assertIsNone(entry["candidate_key"])
        self.assertIsNone(entry["source_family"])
        self.assertIsNone(entry["chosen_model"])


if __name__ == "__main__":
    unittest.main()
