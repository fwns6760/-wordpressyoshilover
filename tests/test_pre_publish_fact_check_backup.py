import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.pre_publish_fact_check.backup import BackupError, create_backup


def _sample_post():
    return {
        "id": 123,
        "title": {"raw": "巨人が勝利"},
        "content": {"raw": "<p>raw</p>", "rendered": "<p>rendered</p>"},
        "modified": "2026-04-25T12:00:00",
        "status": "draft",
    }


class BackupTests(unittest.TestCase):
    def test_atomic_write_uses_tmp_then_rename(self):
        calls = []
        original_rename = os.rename

        def wrapped_rename(src, dst):
            calls.append((src, dst, os.path.exists(src)))
            return original_rename(src, dst)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.pre_publish_fact_check.backup.os.rename", side_effect=wrapped_rename):
                backup_path = create_backup(_sample_post(), tmpdir)

        self.assertEqual(len(calls), 1)
        src, dst, src_exists = calls[0]
        self.assertTrue(str(src).endswith(".tmp"))
        self.assertEqual(str(backup_path), str(dst))
        self.assertTrue(src_exists)

    def test_filename_format_and_content_shape(self):
        now = datetime(2026, 4, 25, 1, 2, 3, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = create_backup(_sample_post(), tmpdir, now=now)
            payload = json.loads(backup_path.read_text(encoding="utf-8"))
        self.assertEqual(backup_path.name, "123_2026-04-25T010203Z.json")
        self.assertEqual(
            sorted(payload.keys()),
            sorted(
                [
                    "post_id",
                    "fetched_at",
                    "title",
                    "content_raw",
                    "content_rendered",
                    "modified",
                    "status",
                ]
            ),
        )
        self.assertEqual(payload["post_id"], 123)
        self.assertEqual(payload["title"], "巨人が勝利")

    def test_backup_failure_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pathlib.Path.open", side_effect=PermissionError("blocked")):
                with self.assertRaises(BackupError) as ctx:
                    create_backup(_sample_post(), Path(tmpdir) / "nested")
        self.assertIn("failed to write backup", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
