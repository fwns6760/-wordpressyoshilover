import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools import run_x_draft_email_dry_run as dry_run


class RunXDraftEmailDryRunTests(unittest.TestCase):
    def _fixture_path(self, articles):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "fixture.json"
        path.write_text(json.dumps({"articles": articles}, ensure_ascii=False), encoding="utf-8")
        return tmp, path

    def _articles(self):
        return [
            {
                "news_family": "試合結果",
                "entity_primary": "巨人",
                "event_nucleus": "巨人 3-2 阪神",
                "source_tier": "fact",
                "safe_fact": "巨人が阪神に3-2で勝利しました。",
                "title": "巨人、阪神に3-2で勝利",
                "published_url": "",
                "source_ref": "",
            },
            {
                "news_family": "試合結果",
                "entity_primary": "巨人",
                "event_nucleus": "下書き URL 混入",
                "source_tier": "fact",
                "safe_fact": "巨人が阪神に3-2で勝利しました。",
                "title": "下書き URL 混入候補",
                "published_url": "https://yoshilover.com/?p=123&preview=true",
                "source_ref": "https://yoshilover.com/?p=123&preview=true",
            },
        ]

    def test_json_stdout_contains_eight_fields_warning_and_excludes_hard_fail(self):
        tmp, fixture = self._fixture_path(self._articles())
        stdout = io.StringIO()
        try:
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture), "--format", "json"])
        finally:
            tmp.cleanup()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["items"], 1)
        self.assertEqual(payload["excluded"], 1)
        candidate = payload["candidates"][0]
        self.assertEqual(
            list(candidate.keys())[:8],
            [
                "recommended_account",
                "source_tier",
                "safe_fact",
                "official_draft",
                "official_alt",
                "inner_angle",
                "risk_note",
                "source_ref",
            ],
        )
        self.assertEqual(candidate["warnings"], ["SOURCE_REF_MISSING"])
        self.assertNotIn("?p=123", stdout.getvalue())

    def test_human_stdout_uses_fixed_field_order_and_warning_line(self):
        tmp, fixture = self._fixture_path(self._articles())
        stdout = io.StringIO()
        try:
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture), "--format", "human"])
        finally:
            tmp.cleanup()

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("X Draft Email Digest", output)
        self.assertIn("items: 1", output)
        self.assertIn("excluded: 1", output)
        expected_labels = [
            "recommended_account",
            "source_tier",
            "safe_fact",
            "official_draft",
            "official_alt",
            "inner_angle",
            "risk_note",
            "source_ref",
        ]
        candidate_lines = output.split("candidate 1", 1)[1].splitlines()
        label_lines = [line for line in candidate_lines if any(line.startswith(f"{label}:") for label in expected_labels)]
        self.assertEqual([line.split(":", 1)[0] for line in label_lines], expected_labels)
        self.assertIn("warnings: SOURCE_REF_MISSING", output)
        self.assertNotIn("下書き URL 混入候補", output)

    def test_no_include_warnings_suppresses_warning_output(self):
        tmp, fixture = self._fixture_path(self._articles())
        stdout = io.StringIO()
        try:
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture), "--format", "json", "--no-include-warnings"])
        finally:
            tmp.cleanup()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertNotIn("warnings", payload["candidates"][0])


if __name__ == "__main__":
    unittest.main()
