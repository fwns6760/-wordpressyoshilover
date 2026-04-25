import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from src.tools import run_pre_publish_fact_check as cli


class FakeWPClient:
    def __init__(self):
        self.updated_payloads = []

    def get_post(self, post_id):
        return {
            "id": post_id,
            "title": {"raw": "巨人が勝利"},
            "content": {"raw": "<p>打率 .476 です。</p>", "rendered": "<p>打率 .476 です。</p>"},
            "date": "2026-04-25T09:00:00",
            "modified": "2026-04-25T10:00:00",
            "status": "draft",
            "categories": [1],
            "tags": [2],
        }

    def list_posts(self, **kwargs):
        return [self.get_post(1)]

    def update_post_fields(self, post_id, **fields):
        self.updated_payloads.append((post_id, fields))


class FactCheckCLITests(unittest.TestCase):
    def test_extract_detect_approve_apply_dry_chain(self):
        fake_wp = FakeWPClient()
        with tempfile.TemporaryDirectory() as tmpdir:
            extract_path = Path(tmpdir) / "extract.json"
            detect_path = Path(tmpdir) / "detect.json"
            approve_path = Path(tmpdir) / "approve.yaml"
            stderr = io.StringIO()

            with patch("src.tools.run_pre_publish_fact_check._make_wp_client", return_value=fake_wp):
                self.assertEqual(
                    cli.main(["--mode", "extract", "--post-id", "1", "--output", str(extract_path)]),
                    0,
                )
                self.assertEqual(
                    cli.main(
                        [
                            "--mode",
                            "detect",
                            "--input-from",
                            str(extract_path),
                            "--output",
                            str(detect_path),
                        ]
                    ),
                    0,
                )

                detect_payload = json.loads(detect_path.read_text(encoding="utf-8"))
                detect_payload[0]["findings"] = [
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
                    }
                ]
                detect_payload[0]["overall_severity"] = "high"
                detect_payload[0]["safe_to_publish_after_fixes"] = True
                detect_path.write_text(json.dumps(detect_payload, ensure_ascii=False), encoding="utf-8")

                self.assertEqual(
                    cli.main(
                        [
                            "--mode",
                            "approve",
                            "--input-from",
                            str(detect_path),
                            "--output",
                            str(approve_path),
                        ]
                    ),
                    0,
                )

                approve_payload = yaml.safe_load(approve_path.read_text(encoding="utf-8"))
                approve_payload[0]["findings"][0]["approve"] = True
                approve_path.write_text(
                    yaml.safe_dump(approve_payload, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )

                with patch("sys.stderr", stderr), patch("sys.stdout", io.StringIO()):
                    exit_code = cli.main(
                        [
                            "--mode",
                            "apply",
                            "--post-id",
                            "1",
                            "--approve-yaml",
                            str(approve_path),
                        ]
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn("post-1:proposed", stderr.getvalue())
        self.assertEqual(fake_wp.updated_payloads, [])

    def test_apply_requires_approve_yaml(self):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            exit_code = cli.main(["--mode", "apply", "--post-id", "1"])
        self.assertEqual(exit_code, 1)
        self.assertIn("apply requires --approve-yaml", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
