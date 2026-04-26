from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import cloud_run_secret_auth


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "codex_shadow_entrypoint.sh"
RESTORED_AUTH = b'{"auth_mode":"chatgpt_auth","tokens":{"refresh_token":"entrypoint-token"}}'
UPDATED_AUTH = b'{"auth_mode":"chatgpt_auth","tokens":{"refresh_token":"entrypoint-token-rotated"}}'


class CodexShadowEntrypointTests(unittest.TestCase):
    def test_entrypoint_runs_shadow_lane_and_cleans_up_codex_home(self) -> None:
        restore_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=RESTORED_AUTH, stderr=b"")
        runner_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "subprocess.run",
            side_effect=[restore_result, runner_result],
        ) as mocked_run:
            exit_code = cloud_run_secret_auth.run_codex_shadow_entrypoint(
                ["--codex-home", tmpdir, "--max-posts", "4"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            mocked_run.call_args_list[1].args[0],
            [
                sys.executable,
                "-m",
                "src.tools.run_draft_body_editor_lane",
                "--provider",
                "codex",
                "--max-posts",
                "4",
            ],
        )
        self.assertEqual(
            mocked_run.call_args_list[1].kwargs["env"]["CODEX_HOME"],
            str(Path(tmpdir).resolve()),
        )
        self.assertFalse(Path(tmpdir).exists())

    def test_entrypoint_writebacks_when_runner_changes_auth_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = Path(tmpdir).resolve() / "auth.json"
            calls: list[list[str]] = []

            def fake_run(cmd, **kwargs):
                calls.append(list(cmd))
                if cmd[0] == "gcloud" and "access" in cmd:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=RESTORED_AUTH, stderr=b"")
                if cmd[0] == sys.executable:
                    auth_path.write_bytes(UPDATED_AUTH)
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                if cmd[0] == "gcloud" and "add" in cmd:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
                raise AssertionError(f"unexpected command: {cmd}")

            with patch("subprocess.run", side_effect=fake_run):
                exit_code = cloud_run_secret_auth.run_codex_shadow_entrypoint(["--codex-home", tmpdir])

        self.assertEqual(exit_code, 0)
        self.assertEqual(sum(1 for cmd in calls if cmd[0] == "gcloud" and "add" in cmd), 1)

    def test_entrypoint_returns_runner_exit_code(self) -> None:
        restore_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=RESTORED_AUTH, stderr=b"")
        runner_result = subprocess.CompletedProcess(args=[], returncode=9, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "subprocess.run",
            side_effect=[restore_result, runner_result],
        ):
            exit_code = cloud_run_secret_auth.run_codex_shadow_entrypoint(["--codex-home", tmpdir])

        self.assertEqual(exit_code, 9)

    def test_main_masks_secret_errors(self) -> None:
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gcloud"],
            stderr=b'failed {"refresh_token":"entrypoint-token"}',
        )
        stderr_buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", side_effect=error), patch(
            "sys.stderr",
            stderr_buffer,
        ):
            exit_code = cloud_run_secret_auth.main(["entrypoint", "--codex-home", tmpdir])

        self.assertEqual(exit_code, 1)
        self.assertIn("[REDACTED auth.json content]", stderr_buffer.getvalue())
        self.assertNotIn("entrypoint-token", stderr_buffer.getvalue())

    def test_shell_script_is_thin_python_wrapper(self) -> None:
        script_text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", script_text)
        self.assertIn("python3 -m src.cloud_run_secret_auth entrypoint", script_text)


if __name__ == "__main__":
    unittest.main()
