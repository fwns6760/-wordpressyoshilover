from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import patch

from src import codex_cli_shadow


class CodexCliShadowTests(unittest.TestCase):
    def test_compute_codex_home_returns_parent_directory(self):
        self.assertEqual(
            codex_cli_shadow.compute_codex_home("/tmp/.codex/auth.json"),
            "/tmp/.codex",
        )

    def test_call_codex_success_returns_output_and_metadata(self):
        completed = subprocess.CompletedProcess(
            args=["codex", "exec", "--json", "repair prompt"],
            returncode=0,
            stdout='{"output":"hello","metadata":{"model":"chatgpt-pro","raw_response_size":5}}',
            stderr="",
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "should-not-leak"}, clear=False), \
             patch("subprocess.run", return_value=completed) as mocked_run:
            text, meta = codex_cli_shadow.call_codex(
                "repair prompt",
                auth_mode="chatgpt_auth",
                codex_home="/tmp/.codex",
                timeout=10,
            )

        self.assertEqual(text, "hello")
        self.assertEqual(meta, {"model": "chatgpt-pro", "raw_response_size": 5})
        self.assertEqual(
            mocked_run.call_args.args[0],
            ["codex", "exec", "--json", "repair prompt"],
        )
        self.assertEqual(mocked_run.call_args.kwargs["timeout"], 10)
        self.assertEqual(mocked_run.call_args.kwargs["env"]["CODEX_HOME"], "/tmp/.codex")
        self.assertNotIn("OPENAI_API_KEY", mocked_run.call_args.kwargs["env"])

    def test_call_codex_timeout_propagates(self):
        timeout_error = subprocess.TimeoutExpired(cmd="codex", timeout=10)
        with patch("subprocess.run", side_effect=timeout_error):
            with self.assertRaises(subprocess.TimeoutExpired):
                codex_cli_shadow.call_codex(
                    "repair prompt",
                    auth_mode="chatgpt_auth",
                    codex_home="/tmp/.codex",
                    timeout=10,
                )

    def test_call_codex_nonzero_exit_raises_exec_error(self):
        completed = subprocess.CompletedProcess(
            args=["codex", "exec", "--json", "repair prompt"],
            returncode=1,
            stdout="",
            stderr="provider down",
        )
        with patch("subprocess.run", return_value=completed):
            with self.assertRaises(codex_cli_shadow.CodexExecError) as ctx:
                codex_cli_shadow.call_codex(
                    "repair prompt",
                    auth_mode="chatgpt_auth",
                    codex_home="/tmp/.codex",
                )

        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertEqual(ctx.exception.stderr, "provider down")

    def test_call_codex_auth_error_masks_auth_json_path(self):
        stderr = "401 Unauthorized while reading /tmp/.codex/auth.json"
        completed = subprocess.CompletedProcess(
            args=["codex", "exec", "--json", "repair prompt"],
            returncode=1,
            stdout="",
            stderr=stderr,
        )
        with patch("subprocess.run", return_value=completed):
            with self.assertRaises(codex_cli_shadow.CodexAuthError) as ctx:
                codex_cli_shadow.call_codex(
                    "repair prompt",
                    auth_mode="chatgpt_auth",
                    codex_home="/tmp/.codex",
                )

        self.assertIn("[auth.json masked]", str(ctx.exception))
        self.assertNotIn("/tmp/.codex/auth.json", str(ctx.exception))
        self.assertEqual(ctx.exception.stderr, "401 Unauthorized while reading [auth.json masked]")

    def test_call_codex_invalid_json_raises_schema_error(self):
        completed = subprocess.CompletedProcess(
            args=["codex", "exec", "--json", "repair prompt"],
            returncode=0,
            stdout="not-json",
            stderr="",
        )
        with patch("subprocess.run", return_value=completed):
            with self.assertRaises(codex_cli_shadow.CodexSchemaError):
                codex_cli_shadow.call_codex(
                    "repair prompt",
                    auth_mode="chatgpt_auth",
                    codex_home="/tmp/.codex",
                )

    def test_call_codex_api_key_mode_passes_openai_api_key(self):
        completed = subprocess.CompletedProcess(
            args=["codex", "exec", "--json", "repair prompt"],
            returncode=0,
            stdout='{"output":"hello","metadata":{}}',
            stderr="",
        )
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "CODEX_HOME": "/tmp/should-be-removed"},
            clear=False,
        ), patch("subprocess.run", return_value=completed) as mocked_run:
            text, meta = codex_cli_shadow.call_codex(
                "repair prompt",
                auth_mode="api_key",
                timeout=10,
            )

        self.assertEqual(text, "hello")
        self.assertEqual(meta, {})
        self.assertEqual(mocked_run.call_args.kwargs["env"]["OPENAI_API_KEY"], "sk-test")
        self.assertNotIn("CODEX_HOME", mocked_run.call_args.kwargs["env"])


if __name__ == "__main__":
    unittest.main()
