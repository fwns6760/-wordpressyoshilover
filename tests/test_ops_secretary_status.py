import json
import unittest
from pathlib import Path

from src.ops_secretary_status import (
    FIELD_ORDER,
    format_digest_human,
    format_digest_json,
    redact_field,
    render_ops_status_digest,
    select_user_action,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ops_secretary"


def _fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class OpsSecretaryStatusTests(unittest.TestCase):
    def test_human_output_is_exactly_five_lines_in_fixed_order(self):
        digest = render_ops_status_digest(_fixture("typical.json"))
        output = format_digest_human(digest)
        lines = output.splitlines()

        self.assertEqual(len(lines), 5)
        self.assertEqual(
            [line.split(":", 1)[0] for line in lines],
            ["進行中", "完了", "blocked/parked", "user action", "next"],
        )
        self.assertIn("B: 048 formatter in-flight", lines[0])
        self.assertIn("B: 065-B1 close", lines[1])
        self.assertIn("A: 041 close", lines[1])
        self.assertIn("runtime: evidence parked", lines[2])
        self.assertEqual(lines[3], "user action: 048 close 後に 046-A1 fire 判断")

    def test_empty_fields_use_required_defaults(self):
        digest = render_ops_status_digest(_fixture("empty.json"))
        self.assertEqual(format_digest_json(digest), {
            "in_flight": "なし",
            "completed": "なし",
            "blocked_parked": "なし",
            "user_action": "なし",
            "next": "待機",
        })
        self.assertIn("user action: なし", format_digest_human(digest))

    def test_user_action_selects_one_by_priority_then_input_order(self):
        self.assertEqual(
            select_user_action(_fixture("multi_user_action.json")["user_action_candidates"]),
            "secret rotate stop 判断",
        )

        same_priority = [
            {"kind": "ticket_decision", "text": "first decision"},
            {"kind": "ticket_decision", "text": "second decision"},
        ]
        self.assertEqual(select_user_action(same_priority), "first decision")

    def test_redaction_path_for_draft_url_secret_long_log_and_diff(self):
        self.assertEqual(render_ops_status_digest(_fixture("draft_url_leak.json")).in_flight, "[REDACTED:draft_url]")
        secret_digest = render_ops_status_digest(_fixture("secret_leak.json"))
        self.assertEqual(secret_digest.completed, "[REDACTED:secret]")
        self.assertEqual(secret_digest.user_action, "[REDACTED:secret]")
        self.assertEqual(render_ops_status_digest(_fixture("long_log.json")).blocked_parked, "[REDACTED:long_log]")
        self.assertEqual(redact_field("diff --git a/file b/file\n@@ -1 +1 @@"), "[REDACTED:diff]")

    def test_reject_path_for_draft_url_secret_long_log_and_diff(self):
        self.assertEqual(render_ops_status_digest(_fixture("draft_url_leak.json"), strict=True).in_flight, "[reject:draft_url]")
        secret_digest = render_ops_status_digest(_fixture("secret_leak.json"), strict=True)
        self.assertEqual(secret_digest.completed, "[reject:secret]")
        self.assertEqual(secret_digest.user_action, "[reject:secret]")
        self.assertEqual(render_ops_status_digest(_fixture("long_log.json"), strict=True).blocked_parked, "[reject:long_log]")
        self.assertEqual(redact_field("diff --git a/file b/file\n@@ -1 +1 @@", strict=True), "[reject:diff]")

    def test_json_format_contains_only_five_fields(self):
        digest = render_ops_status_digest(_fixture("typical.json"))
        payload = format_digest_json(digest)

        self.assertEqual(list(payload.keys()), list(FIELD_ORDER))
        self.assertEqual(payload["next"], "048 close 後に 046-A1 fixture dry-run fire 判断")


if __name__ == "__main__":
    unittest.main()
