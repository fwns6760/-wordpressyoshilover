from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from src import nucleus_ledger_emitter as emitter
from src.tools import run_notice_fixed_lane as lane


class _FakeWP:
    def __init__(self) -> None:
        self.api = "https://example.com/wp-json/wp/v2"
        self.auth = ("user", "pass")
        self.headers = {"Content-Type": "application/json"}

    def _raise_for_status(self, resp, action: str) -> None:  # pragma: no cover - not used
        if resp.status_code >= 400:
            raise RuntimeError(f"{action}:{resp.status_code}")

    def resolve_category_id(self, name: str) -> int:
        mapping = {
            "選手情報": 664,
            "読売ジャイアンツ": 999,
        }
        return mapping.get(name, 0)


class RunNoticeFixedLaneNucleusHookTests(unittest.TestCase):
    def _make_candidate(self):
        payload = {
            "family": "transaction_notice",
            "source_url": "https://npb.jp/announcement/roster/",
            "trust_tier": lane.TRUST_TIER_T1,
            "notice_date": "20260420",
            "subject": "山瀬慎之助+丸佳浩",
            "notice_kind": "register_deregister",
            "title": "【公示】4月20日 巨人は山瀬慎之助を登録、丸佳浩を抹消",
            "body_html": "<p>山瀬慎之助は登録された。</p>",
            "category": "選手情報",
            "tags": ["公示"],
        }
        candidate, outcome = lane._normalize_intake_item(payload)
        self.assertIsNone(outcome)
        self.assertIsNotNone(candidate)
        return candidate

    def test_gate_off_keeps_existing_process_result_behavior(self):
        candidate = self._make_candidate()
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {emitter.ENV_SINK_DIR: tmpdir},
            clear=False,
        ):
            os.environ.pop(emitter.ENV_EMIT_ENABLED, None)
            with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
                lane, "_resolve_category_ids", return_value=[664, 999]
            ), patch.object(lane, "_resolve_tag_ids", return_value=[888]), patch.object(
                lane, "_create_notice_draft", return_value=63175
            ), patch.object(lane, "_process_postgame_revisit_chain", return_value=[]):
                result = lane._process_candidates(_FakeWP(), [candidate])
            sink_empty = not any(os.scandir(tmpdir))

        self.assertEqual(
            result,
            lane.ProcessResult(
                created_post_id=63175,
                duplicate_skip=False,
                route_outcomes=(lane.ROUTE_FIXED_PRIMARY,),
                attempted_create=True,
            ),
        )
        self.assertTrue(sink_empty)

    def test_gate_on_success_path_calls_emitter(self):
        candidate = self._make_candidate()
        fake_result = emitter.NucleusLedgerEmitResult(status="emitted", entry={}, sink_path=None)
        with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
            lane, "_resolve_category_ids", return_value=[664, 999]
        ), patch.object(lane, "_resolve_tag_ids", return_value=[888]), patch.object(
            lane, "_create_notice_draft", return_value=63175
        ), patch.object(lane, "_process_postgame_revisit_chain", return_value=[]), patch.object(
            lane, "emit_nucleus_ledger_entry", return_value=fake_result
        ) as emit_mock:
            result = lane._process_candidates(_FakeWP(), [candidate])

        self.assertEqual(result.created_post_id, 63175)
        emit_mock.assert_called_once()
        call_args = emit_mock.call_args
        draft_meta = call_args.args[0]
        self.assertEqual(draft_meta.draft_id, 63175)
        self.assertEqual(draft_meta.candidate_key, candidate.metadata["candidate_key"])
        self.assertEqual(draft_meta.subtype, "fact_notice")
        self.assertEqual(draft_meta.source_trust, "primary")
        self.assertEqual(draft_meta.source_family, "transaction_notice")
        self.assertEqual(call_args.kwargs["title"], candidate.title)
        self.assertEqual(call_args.kwargs["body"], candidate.body_html)

    def test_emitter_exception_is_swallowed_and_runner_returns_process_result(self):
        candidate = self._make_candidate()
        stderr = io.StringIO()
        with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
            lane, "_resolve_category_ids", return_value=[664, 999]
        ), patch.object(lane, "_resolve_tag_ids", return_value=[888]), patch.object(
            lane, "_create_notice_draft", return_value=63175
        ), patch.object(lane, "_process_postgame_revisit_chain", return_value=[]), patch.object(
            lane, "emit_nucleus_ledger_entry", side_effect=RuntimeError("boom")
        ), redirect_stderr(stderr):
            result = lane._process_candidates(_FakeWP(), [candidate])

        self.assertEqual(result.created_post_id, 63175)
        self.assertIn("[WARN] nucleus ledger emit failed: boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
