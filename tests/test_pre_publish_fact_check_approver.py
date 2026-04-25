import tempfile
import unittest
from pathlib import Path

from src.pre_publish_fact_check import approver


def _detector_result_payload():
    return [
        {
            "post_id": 63405,
            "content_hash": "abc123",
            "overall_severity": "high",
            "is_4_17_equivalent_risk": True,
            "safe_to_publish_after_fixes": False,
            "notes": "detected",
            "findings": [
                {
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
                },
                {
                    "severity": "low",
                    "risk_type": "speculative_claim",
                    "target": "body",
                    "evidence_excerpt": "〜とみられる",
                    "why_risky": "soften",
                    "suggested_fix": {
                        "operation": "soften",
                        "find_text": "〜とみられる",
                        "replace_text": "〜の可能性がある",
                        "rationale": "tone down",
                    },
                },
            ],
        }
    ]


class ApproverTests(unittest.TestCase):
    def test_yaml_round_trip(self):
        records = approver.build_approval_records(_detector_result_payload())
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "approve.yaml"
            approver.write_yaml(records, path)
            loaded = approver.load_yaml(path)
        self.assertEqual([record.to_dict() for record in loaded], [record.to_dict() for record in records])

    def test_invalid_yaml_schema_raises(self):
        invalid_yaml = """
- post_id: 1
  content_hash: abc
  overall_severity: high
  is_4_17_equivalent_risk: false
  safe_to_publish_after_fixes: true
  findings:
    - finding_index: 0
      severity: high
      risk_type: unsupported_named_fact
      target: body
      evidence_excerpt: x
      why_risky: y
      suggested_fix:
        operation: bad_operation
        find_text: x
        replace_text: z
        rationale: r
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "invalid.yaml"
            path.write_text(invalid_yaml, encoding="utf-8")
            with self.assertRaises(ValueError):
                approver.load_yaml(path)

    def test_default_approve_is_false(self):
        records = approver.build_approval_records(_detector_result_payload())
        self.assertEqual([finding.approve for finding in records[0].findings], [False, False])

    def test_multi_finding_yaml_order_is_preserved(self):
        records = approver.build_approval_records(_detector_result_payload())
        yaml_text = approver.dump_yaml(records)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "approve.yaml"
            path.write_text(yaml_text, encoding="utf-8")
            loaded = approver.load_yaml(path)
        self.assertEqual([finding.finding_index for finding in loaded[0].findings], [0, 1])
        self.assertEqual(
            [finding.suggested_fix.find_text for finding in loaded[0].findings],
            [".476", "〜とみられる"],
        )


if __name__ == "__main__":
    unittest.main()
