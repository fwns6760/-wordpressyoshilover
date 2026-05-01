from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import cloud_run_persistence


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "publish_notice_entrypoint.sh"


class GCSStateManagerTests(unittest.TestCase):
    def test_download_returns_true_when_object_exists(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", return_value=completed) as mocked_run:
            manager = cloud_run_persistence.GCSStateManager(
                bucket_name="bucket-name",
                prefix="publish_notice",
                project_id="project-id",
            )
            target = Path(tmpdir) / "state" / "cursor.txt"
            downloaded = manager.download("cursor.txt", target)
            self.assertTrue(target.parent.exists())

        self.assertTrue(downloaded)
        self.assertEqual(
            mocked_run.call_args.args[0],
            [
                "gcloud",
                "--project",
                "project-id",
                "storage",
                "cp",
                "gs://bucket-name/publish_notice/cursor.txt",
                str(target),
                "--quiet",
            ],
        )

    def test_download_returns_false_when_object_is_missing(self) -> None:
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gcloud"],
            stderr=b"CommandException: No URLs matched: gs://bucket-name/publish_notice/cursor.txt",
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", side_effect=error):
            manager = cloud_run_persistence.GCSStateManager("bucket-name", "publish_notice", "project-id")
            downloaded = manager.download("cursor.txt", Path(tmpdir) / "cursor.txt")

        self.assertFalse(downloaded)

    def test_download_failure_raises_gcs_access_error(self) -> None:
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gcloud"],
            stderr=b"AccessDeniedException: 403 forbidden",
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", side_effect=error):
            manager = cloud_run_persistence.GCSStateManager("bucket-name", "publish_notice", "project-id")
            with self.assertRaises(cloud_run_persistence.GCSAccessError) as ctx:
                manager.download("cursor.txt", Path(tmpdir) / "cursor.txt")

        self.assertIn("403 forbidden", str(ctx.exception))

    def test_upload_writes_via_temp_object_then_moves_into_place(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", return_value=completed) as mocked_run:
            local_path = Path(tmpdir) / "history.json"
            local_path.write_text("{}\n", encoding="utf-8")
            manager = cloud_run_persistence.GCSStateManager("bucket-name", "publish_notice", "project-id")

            manager.upload(local_path, "history.json")

        first_call = mocked_run.call_args_list[0].args[0]
        second_call = mocked_run.call_args_list[1].args[0]
        self.assertEqual(first_call[:6], ["gcloud", "--project", "project-id", "storage", "cp", str(local_path)])
        self.assertTrue(first_call[6].startswith("gs://bucket-name/publish_notice/history.json.uploading-"))
        self.assertEqual(first_call[7], "--quiet")
        self.assertEqual(second_call[:5], ["gcloud", "--project", "project-id", "storage", "mv"])
        self.assertEqual(second_call[5], first_call[6])
        self.assertEqual(second_call[6], "gs://bucket-name/publish_notice/history.json")
        self.assertEqual(second_call[7], "--quiet")

    def test_with_state_uploads_updated_file_on_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = cloud_run_persistence.GCSStateManager("bucket-name", "publish_notice", "project-id")
            target = Path(tmpdir) / "cursor.txt"

            with patch.object(manager, "download", return_value=False) as mocked_download, patch.object(
                manager, "upload"
            ) as mocked_upload:
                with manager.with_state("cursor.txt", target) as downloaded:
                    self.assertFalse(downloaded)
                    target.write_text("cursor\n", encoding="utf-8")

        mocked_download.assert_called_once_with("cursor.txt", target)
        mocked_upload.assert_called_once_with(target, "cursor.txt")

    def test_with_state_can_skip_upload_on_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = cloud_run_persistence.GCSStateManager("bucket-name", "publish_notice", "project-id")
            target = Path(tmpdir) / "guarded_publish_history.jsonl"

            with patch.object(manager, "download", return_value=False) as mocked_download, patch.object(
                manager, "upload"
            ) as mocked_upload:
                with manager.with_state("guarded_publish_history.jsonl", target, upload_on_exit=False) as downloaded:
                    self.assertFalse(downloaded)
                    target.write_text('{"status":"refused"}\n', encoding="utf-8")

        mocked_download.assert_called_once_with("guarded_publish_history.jsonl", target)
        mocked_upload.assert_not_called()


class ArtifactUploaderTests(unittest.TestCase):
    def test_upload_success_returns_gcs_uri(self) -> None:
        fixed_now = datetime.fromisoformat("2026-04-26T19:10:00+09:00")
        captured: dict[str, object] = {}

        def fake_upload(local_path, remote_name):
            captured["remote_name"] = remote_name
            captured["payload"] = json.loads(Path(local_path).read_text(encoding="utf-8"))

        with patch("src.cloud_run_persistence._now_jst", return_value=fixed_now), patch.object(
            cloud_run_persistence.GCSStateManager,
            "upload",
            side_effect=fake_upload,
        ):
            uploader = cloud_run_persistence.ArtifactUploader(
                bucket_name="yoshilover-history",
                prefix="repair_artifacts",
                project_id="project-id",
            )
            uri = uploader.upload(
                post_id=63105,
                provider="codex",
                run_id="run-1",
                before_body="Alpha\nBeta",
                after_body="Alpha\nGamma\nBeta",
                extra_meta={"lane": "repair"},
            )

        self.assertEqual(uri, "gs://yoshilover-history/repair_artifacts/2026-04-26/63105_codex_run-1.json")
        self.assertEqual(captured["remote_name"], "2026-04-26/63105_codex_run-1.json")
        payload = captured["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["post_id"], 63105)
        self.assertEqual(payload["provider"], "codex")
        self.assertEqual(payload["extra_meta"]["lane"], "repair")
        self.assertEqual(payload["diff_summary"]["line_count_delta"], 1)
        self.assertIn("Gamma", payload["diff_summary"]["added_keywords"])

    def test_upload_subprocess_failure_raises_gcs_access_error(self) -> None:
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gcloud"],
            stderr=b"AccessDeniedException: upload blocked",
        )
        with patch("subprocess.run", side_effect=error):
            uploader = cloud_run_persistence.ArtifactUploader(
                bucket_name="yoshilover-history",
                prefix="repair_artifacts",
                project_id="project-id",
            )
            with self.assertRaises(cloud_run_persistence.GCSAccessError):
                uploader.upload(
                    post_id=63105,
                    provider="gemini",
                    run_id="run-2",
                    before_body="Before",
                    after_body="After",
                )

    def test_compute_diff_summary_reports_line_char_and_keyword_delta(self) -> None:
        summary = cloud_run_persistence.ArtifactUploader.compute_diff_summary(
            "Alpha\nBeta",
            "Alpha\nGamma\nBeta",
        )
        self.assertEqual(summary["line_count_before"], 2)
        self.assertEqual(summary["line_count_after"], 3)
        self.assertEqual(summary["line_count_delta"], 1)
        self.assertEqual(summary["char_delta"], len("Alpha\nGamma\nBeta") - len("Alpha\nBeta"))
        self.assertEqual(summary["added_keywords"], ["Gamma"])
        self.assertEqual(summary["removed_keywords"], [])


class PublishNoticeEntrypointTests(unittest.TestCase):
    def test_entrypoint_runs_runner_and_persists_cursor_and_history(self) -> None:
        runner_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            guarded_cursor_path = Path(tmpdir) / "guarded_publish_history_cursor.txt"
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"

            def fake_run(cmd, **kwargs):
                if cmd[0] == "gcloud" and cmd[4] == "cp" and cmd[5].startswith("gs://"):
                    if cmd[5].endswith("/guarded_publish_history.jsonl"):
                        guarded_history_path.write_text("", encoding="utf-8")
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                    error = subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr=b"CommandException: No URLs matched")
                    raise error
                if cmd[0] == sys.executable:
                    cursor_path.write_text("cursor\n", encoding="utf-8")
                    history_path.write_text("{}\n", encoding="utf-8")
                    guarded_cursor_path.write_text("2026-04-24T11:00:00+09:00\n", encoding="utf-8")
                    return runner_result
                if cmd[0] == "gcloud" and cmd[4] in {"cp", "mv"}:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                raise AssertionError(f"unexpected command: {cmd}")

            with patch("subprocess.run", side_effect=fake_run) as mocked_run:
                exit_code = cloud_run_persistence.run_publish_notice_entrypoint(
                    [
                        "--bucket-name",
                        "bucket-name",
                        "--prefix",
                        "publish_notice",
                        "--project-id",
                        "project-id",
                        "--cursor-path",
                        str(cursor_path),
                        "--history-path",
                        str(history_path),
                        "--queue-path",
                        str(Path(tmpdir) / "queue.jsonl"),
                        "--guarded-history-path",
                        str(guarded_history_path),
                        "--guarded-history-cursor-path",
                        str(guarded_cursor_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        runner_command = next(
            call.args[0] for call in mocked_run.call_args_list if call.args[0][0] == sys.executable
        )
        self.assertEqual(
            runner_command,
            [
                sys.executable,
                "-m",
                "src.tools.run_publish_notice_email_dry_run",
                "--scan",
                "--send",
                "--cursor-path",
                str(cursor_path),
                "--history-path",
                str(history_path),
                "--queue-path",
                str(Path(tmpdir) / "queue.jsonl"),
            ],
        )
        commands = [call.args[0] for call in mocked_run.call_args_list]
        guarded_cursor_upload_cp = [
            command
            for command in commands
            if command[:6] == ["gcloud", "--project", "project-id", "storage", "cp", str(guarded_cursor_path)]
        ]
        self.assertTrue(guarded_cursor_upload_cp)
        self.assertTrue(
            guarded_cursor_upload_cp[0][6].startswith(
                "gs://bucket-name/publish_notice/guarded_publish_history_cursor.txt.uploading-"
            )
        )

    def test_run_publish_notice_entrypoint_queue_path_download_upload(self) -> None:
        runner_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_cursor_path = Path(tmpdir) / "guarded_publish_history_cursor.txt"
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"

            def fake_run(cmd, **kwargs):
                if cmd[0] == "gcloud" and cmd[4] == "cp" and cmd[5].startswith("gs://"):
                    if cmd[5].endswith("/queue.jsonl"):
                        queue_path.write_text('{"status":"queued"}\n', encoding="utf-8")
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                    if cmd[5].endswith("/guarded_publish_history.jsonl"):
                        guarded_history_path.write_text("", encoding="utf-8")
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                    raise subprocess.CalledProcessError(
                        returncode=1,
                        cmd=cmd,
                        stderr=b"CommandException: No URLs matched",
                    )
                if cmd[0] == sys.executable:
                    cursor_path.write_text("cursor\n", encoding="utf-8")
                    history_path.write_text("{}\n", encoding="utf-8")
                    queue_path.write_text('{"status":"queued"}\n{"status":"sent"}\n', encoding="utf-8")
                    guarded_cursor_path.write_text("2026-04-24T11:30:00+09:00\n", encoding="utf-8")
                    return runner_result
                if cmd[0] == "gcloud" and cmd[4] in {"cp", "mv"}:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                raise AssertionError(f"unexpected command: {cmd}")

            with patch("subprocess.run", side_effect=fake_run) as mocked_run:
                exit_code = cloud_run_persistence.run_publish_notice_entrypoint(
                    [
                        "--bucket-name",
                        "bucket-name",
                        "--prefix",
                        "publish_notice",
                        "--project-id",
                        "project-id",
                        "--cursor-path",
                        str(cursor_path),
                        "--history-path",
                        str(history_path),
                        "--queue-path",
                        str(queue_path),
                        "--guarded-history-path",
                        str(guarded_history_path),
                        "--guarded-history-cursor-path",
                        str(guarded_cursor_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        commands = [call.args[0] for call in mocked_run.call_args_list]
        self.assertIn(
            [
                "gcloud",
                "--project",
                "project-id",
                "storage",
                "cp",
                "gs://bucket-name/publish_notice/queue.jsonl",
                str(queue_path),
                "--quiet",
            ],
            commands,
        )
        self.assertIn(
            [
                "gcloud",
                "--project",
                "project-id",
                "storage",
                "cp",
                "gs://bucket-name/guarded_publish/guarded_publish_history.jsonl",
                str(guarded_history_path),
                "--quiet",
            ],
            commands,
        )
        self.assertIn(
            [
                "gcloud",
                "--project",
                "project-id",
                "storage",
                "cp",
                "gs://bucket-name/publish_notice/guarded_publish_history_cursor.txt",
                str(guarded_cursor_path),
                "--quiet",
            ],
            commands,
        )
        queue_upload_cp = [
            command
            for command in commands
            if command[:6] == ["gcloud", "--project", "project-id", "storage", "cp", str(queue_path)]
        ]
        self.assertTrue(queue_upload_cp)
        self.assertTrue(queue_upload_cp[0][6].startswith("gs://bucket-name/publish_notice/queue.jsonl.uploading-"))
        self.assertIn(
            ["gcloud", "--project", "project-id", "storage", "mv", queue_upload_cp[0][6], "gs://bucket-name/publish_notice/queue.jsonl", "--quiet"],
            commands,
        )
        guarded_history_upload_cp = [
            command
            for command in commands
            if command[:6] == ["gcloud", "--project", "project-id", "storage", "cp", str(guarded_history_path)]
        ]
        self.assertEqual(guarded_history_upload_cp, [])

    def test_entrypoint_restores_and_uploads_old_candidate_once_ledger(self) -> None:
        runner_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_cursor_path = Path(tmpdir) / "guarded_publish_history_cursor.txt"
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            old_candidate_ledger_path = Path(tmpdir) / "publish_notice_old_candidate_once.json"

            def fake_run(cmd, **kwargs):
                if cmd[0] == "gcloud" and cmd[4] == "cp" and cmd[5].startswith("gs://"):
                    if cmd[5].endswith("/guarded_publish_history.jsonl"):
                        guarded_history_path.write_text("", encoding="utf-8")
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                    if cmd[5].endswith("/publish_notice_old_candidate_once.json"):
                        old_candidate_ledger_path.write_text(
                            json.dumps({"901": "2026-05-01T09:00:00+09:00"}, ensure_ascii=False) + "\n",
                            encoding="utf-8",
                        )
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                    raise subprocess.CalledProcessError(
                        returncode=1,
                        cmd=cmd,
                        stderr=b"CommandException: No URLs matched",
                    )
                if cmd[0] == sys.executable:
                    self.assertEqual(
                        kwargs["env"]["PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_PATH"],
                        str(old_candidate_ledger_path),
                    )
                    cursor_path.write_text("cursor\n", encoding="utf-8")
                    history_path.write_text("{}\n", encoding="utf-8")
                    queue_path.write_text('{"status":"queued"}\n', encoding="utf-8")
                    guarded_cursor_path.write_text("2026-04-24T11:30:00+09:00\n", encoding="utf-8")
                    old_candidate_ledger_path.write_text(
                        json.dumps({"901": "2026-05-01T09:00:00+09:00", "902": "2026-05-01T09:05:00+09:00"}, ensure_ascii=False)
                        + "\n",
                        encoding="utf-8",
                    )
                    return runner_result
                if cmd[0] == "gcloud" and cmd[4] in {"cp", "mv"}:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                raise AssertionError(f"unexpected command: {cmd}")

            with patch("subprocess.run", side_effect=fake_run) as mocked_run:
                exit_code = cloud_run_persistence.run_publish_notice_entrypoint(
                    [
                        "--bucket-name",
                        "bucket-name",
                        "--prefix",
                        "publish_notice",
                        "--project-id",
                        "project-id",
                        "--cursor-path",
                        str(cursor_path),
                        "--history-path",
                        str(history_path),
                        "--queue-path",
                        str(queue_path),
                        "--old-candidate-ledger-path",
                        str(old_candidate_ledger_path),
                        "--guarded-history-path",
                        str(guarded_history_path),
                        "--guarded-history-cursor-path",
                        str(guarded_cursor_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        commands = [call.args[0] for call in mocked_run.call_args_list]
        self.assertIn(
            [
                "gcloud",
                "--project",
                "project-id",
                "storage",
                "cp",
                "gs://bucket-name/publish_notice/publish_notice_old_candidate_once.json",
                str(old_candidate_ledger_path),
                "--quiet",
            ],
            commands,
        )
        old_candidate_upload_cp = [
            command
            for command in commands
            if command[:6] == ["gcloud", "--project", "project-id", "storage", "cp", str(old_candidate_ledger_path)]
        ]
        self.assertTrue(old_candidate_upload_cp)
        self.assertTrue(
            old_candidate_upload_cp[0][6].startswith(
                "gs://bucket-name/publish_notice/publish_notice_old_candidate_once.json.uploading-"
            )
        )
        self.assertIn(
            [
                "gcloud",
                "--project",
                "project-id",
                "storage",
                "mv",
                old_candidate_upload_cp[0][6],
                "gs://bucket-name/publish_notice/publish_notice_old_candidate_once.json",
                "--quiet",
            ],
            commands,
        )

    def test_entrypoint_returns_runner_exit_code(self) -> None:
        runner_result = subprocess.CompletedProcess(args=[], returncode=7, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_cursor_path = Path(tmpdir) / "guarded_publish_history_cursor.txt"
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"

            def fake_run(cmd, **kwargs):
                if cmd[0] == "gcloud" and cmd[4] == "cp" and cmd[5].startswith("gs://"):
                    if cmd[5].endswith("/guarded_publish_history.jsonl"):
                        guarded_history_path.write_text("", encoding="utf-8")
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                    raise subprocess.CalledProcessError(
                        returncode=1,
                        cmd=cmd,
                        stderr=b"CommandException: No URLs matched",
                    )
                if cmd[0] == sys.executable:
                    cursor_path.write_text("cursor\n", encoding="utf-8")
                    history_path.write_text("{}\n", encoding="utf-8")
                    return runner_result
                if cmd[0] == "gcloud":
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                raise AssertionError(f"unexpected command: {cmd}")

            with patch("subprocess.run", side_effect=fake_run):
                exit_code = cloud_run_persistence.run_publish_notice_entrypoint(
                    [
                        "--cursor-path",
                        str(cursor_path),
                        "--history-path",
                        str(history_path),
                        "--queue-path",
                        str(queue_path),
                        "--guarded-history-path",
                        str(guarded_history_path),
                        "--guarded-history-cursor-path",
                        str(guarded_cursor_path),
                    ]
                )

        self.assertEqual(exit_code, 7)

    def test_main_reports_errors_to_stderr(self) -> None:
        stderr_buffer = io.StringIO()
        with patch(
            "src.cloud_run_persistence.run_publish_notice_entrypoint",
            side_effect=cloud_run_persistence.GCSAccessError("denied"),
        ), patch("sys.stderr", stderr_buffer):
            exit_code = cloud_run_persistence.main(["entrypoint"])

        self.assertEqual(exit_code, 1)
        self.assertIn("gcloud storage access failed: denied", stderr_buffer.getvalue())

    def test_shell_script_is_thin_python_wrapper(self) -> None:
        script_text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", script_text)
        self.assertIn("python3 -m src.cloud_run_persistence entrypoint", script_text)


if __name__ == "__main__":
    unittest.main()
