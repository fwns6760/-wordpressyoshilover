from __future__ import annotations

import hashlib
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import cloud_run_secret_auth


SENTINEL_AUTH = b'{"auth_mode":"chatgpt_auth","tokens":{"refresh_token":"sentinel-refresh-token"}}'
CHANGED_AUTH = b'{"auth_mode":"chatgpt_auth","tokens":{"refresh_token":"rotated-token"}}'


class SecretAuthManagerTests(unittest.TestCase):
    def test_restore_writes_auth_file_and_sets_mode_600(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=SENTINEL_AUTH,
            stderr=b"",
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", return_value=completed) as mocked_run:
            manager = cloud_run_secret_auth.SecretAuthManager(codex_home=tmpdir)
            auth_path = manager.restore()
            self.assertEqual(auth_path.read_bytes(), SENTINEL_AUTH)
            self.assertEqual(stat.S_IMODE(auth_path.stat().st_mode), 0o600)
            self.assertEqual(
                mocked_run.call_args.args[0],
                [
                    "gcloud",
                    "--project",
                    "baseballsite",
                    "secrets",
                    "versions",
                    "access",
                    "latest",
                    "--secret",
                    "codex-auth-json",
                ],
            )
            self.assertTrue(mocked_run.call_args.kwargs["capture_output"])
            self.assertTrue(mocked_run.call_args.kwargs["check"])

    def test_restore_failure_raises_secret_access_error_and_masks_auth_content(self) -> None:
        stderr = b'failed while reading /tmp/.codex/auth.json {"refresh_token":"sentinel-refresh-token"}'
        error = subprocess.CalledProcessError(returncode=1, cmd=["gcloud"], stderr=stderr)
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", side_effect=error):
            manager = cloud_run_secret_auth.SecretAuthManager(codex_home=tmpdir)
            with self.assertRaises(cloud_run_secret_auth.SecretAccessError) as ctx:
                manager.restore()

        detail = str(ctx.exception)
        self.assertIn("[REDACTED auth.json content]", detail)
        self.assertNotIn("sentinel-refresh-token", detail)
        self.assertNotIn("/tmp/.codex/auth.json", detail)

    def test_writeback_if_changed_skips_when_sha_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run") as mocked_run:
            manager = cloud_run_secret_auth.SecretAuthManager(codex_home=tmpdir)
            manager.codex_home.mkdir(parents=True, exist_ok=True)
            manager.auth_path.write_bytes(SENTINEL_AUTH)
            sha_before = manager.compute_sha()

            wrote_back = manager.writeback_if_changed(sha_before)

        self.assertFalse(wrote_back)
        mocked_run.assert_not_called()

    def test_writeback_if_changed_adds_secret_version_when_sha_changes(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", return_value=completed) as mocked_run:
            manager = cloud_run_secret_auth.SecretAuthManager(codex_home=tmpdir)
            manager.codex_home.mkdir(parents=True, exist_ok=True)
            manager.auth_path.write_bytes(SENTINEL_AUTH)
            sha_before = manager.compute_sha()
            manager.auth_path.write_bytes(CHANGED_AUTH)

            wrote_back = manager.writeback_if_changed(sha_before)

        self.assertTrue(wrote_back)
        self.assertEqual(
            mocked_run.call_args.args[0],
            [
                "gcloud",
                "--project",
                "baseballsite",
                "secrets",
                "versions",
                "add",
                "codex-auth-json",
                "--data-file",
                str(Path(tmpdir).resolve() / "auth.json"),
            ],
        )
        self.assertTrue(mocked_run.call_args.kwargs["capture_output"])
        self.assertTrue(mocked_run.call_args.kwargs["check"])

    def test_writeback_failure_raises_secret_writeback_error_and_masks_auth_content(self) -> None:
        stderr = b'cannot add new version {"refresh_token":"sentinel-refresh-token"}'
        error = subprocess.CalledProcessError(returncode=1, cmd=["gcloud"], stderr=stderr)
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", side_effect=error):
            manager = cloud_run_secret_auth.SecretAuthManager(codex_home=tmpdir)
            manager.codex_home.mkdir(parents=True, exist_ok=True)
            manager.auth_path.write_bytes(SENTINEL_AUTH)
            sha_before = hashlib.sha256(b"before").hexdigest()

            with self.assertRaises(cloud_run_secret_auth.SecretWritebackError) as ctx:
                manager.writeback_if_changed(sha_before)

        detail = str(ctx.exception)
        self.assertIn("[REDACTED auth.json content]", detail)
        self.assertNotIn("sentinel-refresh-token", detail)

    def test_cleanup_removes_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = cloud_run_secret_auth.SecretAuthManager(codex_home=tmpdir)
            manager.codex_home.mkdir(parents=True, exist_ok=True)
            manager.auth_path.write_bytes(SENTINEL_AUTH)

            manager.cleanup()

            self.assertFalse(manager.codex_home.exists())

    def test_restore_returns_path_and_compute_sha_without_leaking_auth_content(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=SENTINEL_AUTH,
            stderr=b"",
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("subprocess.run", return_value=completed):
            manager = cloud_run_secret_auth.SecretAuthManager(codex_home=tmpdir)
            auth_path = manager.restore()
            sha_value = manager.compute_sha()

        self.assertEqual(auth_path.name, "auth.json")
        self.assertEqual(sha_value, hashlib.sha256(SENTINEL_AUTH).hexdigest())
        self.assertNotIn("sentinel-refresh-token", str(auth_path))
        self.assertNotIn("sentinel-refresh-token", sha_value)


if __name__ == "__main__":
    unittest.main()
