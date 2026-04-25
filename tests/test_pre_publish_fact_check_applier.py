import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.pre_publish_fact_check.applier import ApplyRefusedError, apply_approved_fixes
from src.pre_publish_fact_check.contracts import ApprovalRecord


def _content_hash(body_html: str) -> str:
    return hashlib.sha256(body_html.encode("utf-8")).hexdigest()


def _approval_record(
    *,
    post_id=1,
    body_html="<p>打率 .476 です。</p>",
    findings=None,
):
    if findings is None:
        findings = [
            {
                "finding_index": 0,
                "severity": "high",
                "risk_type": "unsupported_named_fact",
                "target": "body",
                "evidence_excerpt": "打率 .476",
                "why_risky": "unsupported",
                "suggested_fix": {
                    "operation": "replace",
                    "find_text": ".476",
                    "replace_text": ".276",
                    "rationale": "source mismatch",
                },
                "approve": True,
            }
        ]
    return ApprovalRecord.from_dict(
        {
            "post_id": post_id,
            "content_hash": _content_hash(body_html),
            "overall_severity": "high",
            "is_4_17_equivalent_risk": False,
            "safe_to_publish_after_fixes": True,
            "findings": findings,
            "notes": "approval",
        }
    )


def _post(body_html="<p>打率 .476 です。</p>"):
    return {
        "id": 1,
        "title": {"raw": "巨人が勝利"},
        "content": {"raw": body_html, "rendered": body_html},
        "modified": "2026-04-25T12:00:00",
        "status": "draft",
    }


class ApplierTests(unittest.TestCase):
    def test_dry_run_produces_diff_without_wp_write(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post()

        result = apply_approved_fixes(
            wp_client=wp_client,
            post_id=1,
            approval_records=[_approval_record()],
            backup_dir="unused",
            live=False,
        )

        self.assertIn(".476", result.diff)
        self.assertIn(".276", result.diff)
        wp_client.update_post_fields.assert_not_called()
        self.assertIsNone(result.summary["backup_path"])

    def test_no_approved_findings_refuses(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post()
        record = _approval_record(
            findings=[
                {
                    "finding_index": 0,
                    "severity": "high",
                    "risk_type": "unsupported_named_fact",
                    "target": "body",
                    "evidence_excerpt": "打率 .476",
                    "why_risky": "unsupported",
                    "suggested_fix": {
                        "operation": "replace",
                        "find_text": ".476",
                        "replace_text": ".276",
                        "rationale": "source mismatch",
                    },
                    "approve": False,
                }
            ]
        )

        with self.assertRaises(ApplyRefusedError) as ctx:
            apply_approved_fixes(
                wp_client=wp_client,
                post_id=1,
                approval_records=[record],
                backup_dir="unused",
                live=True,
            )
        self.assertEqual(str(ctx.exception), "no approved findings")

    def test_needs_manual_review_blocks_apply_even_when_approved(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post()
        record = _approval_record(
            findings=[
                {
                    "finding_index": 0,
                    "severity": "high",
                    "risk_type": "unsupported_named_fact",
                    "target": "body",
                    "evidence_excerpt": "打率 .476",
                    "why_risky": "unsupported",
                    "suggested_fix": {
                        "operation": "needs_manual_review",
                        "find_text": ".476",
                        "replace_text": "",
                        "rationale": "human must verify",
                    },
                    "approve": True,
                }
            ]
        )

        with self.assertRaises(ApplyRefusedError) as ctx:
            apply_approved_fixes(
                wp_client=wp_client,
                post_id=1,
                approval_records=[record],
                backup_dir="unused",
                live=True,
            )
        self.assertEqual(str(ctx.exception), "no applicable approved findings")
        self.assertEqual(ctx.exception.summary["refused"][0]["reason"], "manual_review_only")

    def test_find_text_not_found_is_skipped_per_finding(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post()
        record = _approval_record(
            findings=[
                {
                    "finding_index": 0,
                    "severity": "high",
                    "risk_type": "unsupported_named_fact",
                    "target": "body",
                    "evidence_excerpt": "missing",
                    "why_risky": "unsupported",
                    "suggested_fix": {
                        "operation": "replace",
                        "find_text": "不存在",
                        "replace_text": "置換",
                        "rationale": "skip",
                    },
                    "approve": True,
                },
                {
                    "finding_index": 1,
                    "severity": "high",
                    "risk_type": "unsupported_named_fact",
                    "target": "body",
                    "evidence_excerpt": "打率 .476",
                    "why_risky": "unsupported",
                    "suggested_fix": {
                        "operation": "replace",
                        "find_text": ".476",
                        "replace_text": ".276",
                        "rationale": "apply",
                    },
                    "approve": True,
                },
            ]
        )

        result = apply_approved_fixes(
            wp_client=wp_client,
            post_id=1,
            approval_records=[record],
            backup_dir="unused",
            live=False,
        )

        self.assertEqual(result.summary["refused"][0]["reason"], "find_text_not_found")
        self.assertEqual(result.summary["applied"][0]["finding_index"], 1)

    def test_find_text_not_found_all_skipped_refuses(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post()
        record = _approval_record(
            findings=[
                {
                    "finding_index": 0,
                    "severity": "high",
                    "risk_type": "unsupported_named_fact",
                    "target": "body",
                    "evidence_excerpt": "missing",
                    "why_risky": "unsupported",
                    "suggested_fix": {
                        "operation": "replace",
                        "find_text": "不存在",
                        "replace_text": "置換",
                        "rationale": "skip",
                    },
                    "approve": True,
                }
            ]
        )

        with self.assertRaises(ApplyRefusedError) as ctx:
            apply_approved_fixes(
                wp_client=wp_client,
                post_id=1,
                approval_records=[record],
                backup_dir="unused",
                live=True,
            )
        self.assertEqual(str(ctx.exception), "no applicable approved findings")

    def test_content_hash_mismatch_refuses(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post("<p>別本文</p>")

        with self.assertRaises(ApplyRefusedError) as ctx:
            apply_approved_fixes(
                wp_client=wp_client,
                post_id=1,
                approval_records=[_approval_record()],
                backup_dir="unused",
                live=True,
            )
        self.assertEqual(str(ctx.exception), "content drifted, re-extract+approve required")

    def test_backup_failure_refuses_before_wp_write(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post()
        with patch(
            "src.pre_publish_fact_check.applier.create_backup",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                apply_approved_fixes(
                    wp_client=wp_client,
                    post_id=1,
                    approval_records=[_approval_record()],
                    backup_dir="unused",
                    live=True,
                )
        wp_client.update_post_fields.assert_not_called()

    def test_successful_apply_path_returns_summary_json(self):
        wp_client = Mock()
        wp_client.get_post.return_value = _post()
        with patch(
            "src.pre_publish_fact_check.applier.create_backup",
            return_value=Path("/tmp/backup.json"),
        ):
            result = apply_approved_fixes(
                wp_client=wp_client,
                post_id=1,
                approval_records=[_approval_record()],
                backup_dir=tempfile.gettempdir(),
                live=True,
                stderr=io.StringIO(),
            )

        wp_client.update_post_fields.assert_called_once()
        kwargs = wp_client.update_post_fields.call_args.kwargs
        self.assertEqual(kwargs["content"], "<p>打率 .276 です。</p>")
        self.assertEqual(result.summary["backup_path"], "/tmp/backup.json")
        self.assertEqual(result.summary["applied"][0]["finding_index"], 0)


if __name__ == "__main__":
    unittest.main()
