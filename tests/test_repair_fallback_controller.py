from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from src import repair_fallback_controller as controller
from src import repair_provider_ledger


SUCCESS_BODY = (
    "【試合結果】\n"
    "巨人が勝利した。\n"
    "【ハイライト】\n"
    "要点を整理した本文です。\n"
    "【選手成績】\n"
    "主力選手の内容です。\n"
    "【試合展開】\n"
    "終盤までの流れです。"
)
POST = {
    "post_id": 1701,
    "subtype": "postgame",
    "current_body": SUCCESS_BODY,
    "fail_axes": ["density", "source"],
    "source_block": "・ref1: https://www.giants.jp/game/20260420/report/",
}
PROMPT = "repair prompt"


class RepairFallbackControllerTests(unittest.TestCase):
    def _read_rows(self, path: Path) -> list[dict]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_primary_success_skips_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "repair-ledger.jsonl"
            writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)
            fake_meta = {"model": "chatgpt-pro", "raw_response_size": len(SUCCESS_BODY.encode("utf-8"))}
            with patch(
                "src.repair_fallback_controller.call_provider",
                return_value=(SUCCESS_BODY, fake_meta),
            ) as mocked_call:
                result = controller.RepairFallbackController(
                    primary_provider="codex",
                    ledger_writer=writer,
                ).execute(dict(POST), PROMPT)
            rows = self._read_rows(ledger_path)

        self.assertEqual(mocked_call.call_count, 1)
        self.assertEqual(mocked_call.call_args.args[0], "codex")
        self.assertEqual(result.provider, "codex")
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.body_text, SUCCESS_BODY)
        self.assertEqual(result.failure_chain, [])
        self.assertFalse(result.wp_write_allowed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "codex")
        self.assertEqual(rows[0]["status"], "shadow_only")
        self.assertIsNone(rows[0]["provider_meta"]["fallback_from"])
        self.assertIsNone(rows[0]["error_code"])

    def test_primary_failures_trigger_fallback_and_write_two_ledger_entries(self):
        failure_cases = [
            ("timeout", TimeoutError("primary timeout"), "timeout"),
            (
                "auth_fail_401",
                urllib.error.HTTPError("https://stub.invalid/codex", 401, "Unauthorized", hdrs=None, fp=None),
                "auth_fail_401",
            ),
            (
                "rate_limit_429",
                urllib.error.HTTPError("https://stub.invalid/codex", 429, "Too Many Requests", hdrs=None, fp=None),
                "rate_limit_429",
            ),
            (
                "provider_error",
                urllib.error.HTTPError("https://stub.invalid/codex", 503, "Unavailable", hdrs=None, fp=None),
                "provider_error",
            ),
            (
                "schema_invalid",
                json.JSONDecodeError("bad json", "{}", 0),
                "schema_invalid",
            ),
            (
                "network_error",
                urllib.error.URLError("network down"),
                "network_error",
            ),
        ]

        for label, primary_exc, expected_class in failure_cases:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    ledger_path = Path(tmpdir) / f"{label}.jsonl"
                    writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)

                    def fake_call(provider_name: str, prompt: str, api_key: str):
                        del prompt, api_key
                        if provider_name == "codex":
                            raise primary_exc
                        return SUCCESS_BODY, {
                            "model": "gemini-2.5-flash",
                            "raw_response_size": len(SUCCESS_BODY.encode("utf-8")),
                        }

                    with patch("src.repair_fallback_controller.call_provider", side_effect=fake_call) as mocked_call:
                        result = controller.RepairFallbackController(
                            primary_provider="codex",
                            ledger_writer=writer,
                        ).execute(dict(POST), PROMPT)
                    rows = self._read_rows(ledger_path)

                self.assertEqual([call.args[0] for call in mocked_call.call_args_list], ["codex", "gemini"])
                self.assertEqual(result.provider, "gemini")
                self.assertTrue(result.fallback_used)
                self.assertEqual(result.body_text, SUCCESS_BODY)
                self.assertEqual(len(result.failure_chain), 1)
                self.assertEqual(result.failure_chain[0].error_class, expected_class)
                self.assertTrue(result.wp_write_allowed)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["provider"], "codex")
                self.assertEqual(rows[0]["status"], "failed")
                self.assertEqual(rows[0]["error_code"], expected_class)
                self.assertEqual(rows[1]["provider"], "gemini")
                self.assertEqual(rows[1]["status"], "success")
                self.assertEqual(rows[1]["provider_meta"]["fallback_from"], "codex")
                self.assertEqual(rows[1]["provider_meta"]["fallback_reason"], expected_class)

    def test_primary_and_fallback_fail_write_two_failed_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "fallback-fail.jsonl"
            writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)

            def fake_call(provider_name: str, prompt: str, api_key: str):
                del prompt, api_key
                if provider_name == "codex":
                    raise urllib.error.HTTPError(
                        "https://stub.invalid/codex",
                        429,
                        "Too Many Requests",
                        hdrs=None,
                        fp=None,
                    )
                raise urllib.error.URLError("gemini down")

            with patch("src.repair_fallback_controller.call_provider", side_effect=fake_call):
                result = controller.RepairFallbackController(
                    primary_provider="codex",
                    ledger_writer=writer,
                ).execute(dict(POST), PROMPT)
            rows = self._read_rows(ledger_path)

        self.assertEqual(result.provider, "gemini")
        self.assertTrue(result.fallback_used)
        self.assertIsNone(result.body_text)
        self.assertEqual([item.error_class for item in result.failure_chain], ["rate_limit_429", "network_error"])
        self.assertTrue(result.wp_write_allowed)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["status"] for row in rows], ["failed", "failed"])
        self.assertEqual(rows[1]["provider_meta"]["fallback_from"], "codex")
        self.assertEqual(rows[1]["provider_meta"]["fallback_reason"], "rate_limit_429")

    def test_classify_error_covers_all_six_classes(self):
        cases = [
            (subprocess.TimeoutExpired(cmd="codex", timeout=120), None, "timeout"),
            (controller.CodexAuthError("401 unauthorized"), None, "auth_fail_401"),
            (
                urllib.error.HTTPError("https://stub.invalid", 429, "Too Many Requests", hdrs=None, fp=None),
                None,
                "rate_limit_429",
            ),
            (
                urllib.error.HTTPError("https://stub.invalid", 503, "Unavailable", hdrs=None, fp=None),
                None,
                "provider_error",
            ),
            (urllib.error.URLError("down"), None, "network_error"),
            (controller.CodexSchemaError("bad schema"), None, "schema_invalid"),
        ]

        for exc, http_code, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(controller.classify_error(exc, http_code=http_code), expected)

    def test_call_provider_uses_call_codex_for_codex_primary(self):
        fake_meta = {"model": "chatgpt-pro", "raw_response_size": len(SUCCESS_BODY.encode("utf-8"))}
        with patch("src.repair_fallback_controller.call_codex", return_value=(SUCCESS_BODY, fake_meta)) as mocked_call:
            body_text, meta = controller.call_provider("codex", PROMPT, "")

        mocked_call.assert_called_once_with(PROMPT)
        self.assertEqual(body_text, SUCCESS_BODY)
        self.assertEqual(meta, fake_meta)

    def test_openai_stub_interface_supports_env_success_and_random_toggle(self):
        env_key = "REPAIR_PROVIDER_STUB_MODE_OPENAI_API"
        text_key = "REPAIR_PROVIDER_STUB_TEXT_OPENAI_API"
        with patch.dict(os.environ, {env_key: "success", text_key: SUCCESS_BODY}, clear=False):
            body_text, meta = controller.call_openai_api_stub(PROMPT, "")
        self.assertEqual(body_text, SUCCESS_BODY)
        self.assertEqual(meta["model"], "openai_api-stub")

        with patch.dict(os.environ, {env_key: "random", text_key: SUCCESS_BODY}, clear=False), \
             patch("src.repair_fallback_controller.random.choice", return_value="success"):
            body_text, meta = controller.call_openai_api_stub(PROMPT, "")
        self.assertEqual(body_text, SUCCESS_BODY)
        self.assertEqual(meta["stub_mode"], "success")

        with patch.dict(os.environ, {env_key: "random"}, clear=False), \
             patch("src.repair_fallback_controller.random.choice", return_value="provider_error"):
            with self.assertRaises(RuntimeError):
                controller.call_openai_api_stub(PROMPT, "")


if __name__ == "__main__":
    unittest.main()
