import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools import run_ops_secretary_dry_run as dry_run


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ops_secretary"


class RunOpsSecretaryDryRunTests(unittest.TestCase):
    def test_fixture_human_stdout_is_five_line_digest_only(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = dry_run.main(["--fixture", str(FIXTURE_DIR / "typical.json")])

        self.assertEqual(code, 0)
        output = stdout.getvalue().strip()
        self.assertEqual(len(output.splitlines()), 5)
        self.assertTrue(output.startswith("進行中: B: 048 formatter in-flight"))
        self.assertNotIn("[ops]", output)

    def test_fixture_json_stdout_contains_five_field_dict(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = dry_run.main(["--fixture", str(FIXTURE_DIR / "empty.json"), "--format", "json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload, {
            "in_flight": "なし",
            "completed": "なし",
            "blocked_parked": "なし",
            "user_action": "なし",
            "next": "待機",
        })

    def test_strict_outputs_reject_marker(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = dry_run.main(["--fixture", str(FIXTURE_DIR / "draft_url_leak.json"), "--strict"])

        self.assertEqual(code, 0)
        self.assertIn("進行中: [reject:draft_url]", stdout.getvalue())

    def test_stdin_json_is_supported(self):
        fixture = (FIXTURE_DIR / "empty.json").read_text(encoding="utf-8")
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(fixture)), patch("sys.stdout", stdout):
            code = dry_run.main(["--stdin"])

        self.assertEqual(code, 0)
        self.assertIn("next: 待機", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
