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
    def setUp(self) -> None:
        self._dedupe_tmpdir = tempfile.TemporaryDirectory()
        self._dedupe_path = Path(self._dedupe_tmpdir.name) / "llm_call_dedupe.jsonl"
        self._dedupe_patcher = patch.object(
            controller.llm_call_dedupe,
            "DEFAULT_LEDGER_PATH",
            self._dedupe_path,
        )
        self._dedupe_patcher.start()

    def tearDown(self) -> None:
        self._dedupe_patcher.stop()
        self._dedupe_tmpdir.cleanup()

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
            with patch.dict(os.environ, {"CODEX_WP_WRITE_ALLOWED": "false"}, clear=False):
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

    def test_primary_success_allows_wp_write_for_codex_when_env_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "repair-ledger.jsonl"
            writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)
            fake_meta = {"model": "chatgpt-pro", "raw_response_size": len(SUCCESS_BODY.encode("utf-8"))}
            with patch.dict(os.environ, {"CODEX_WP_WRITE_ALLOWED": "true"}, clear=False):
                with patch(
                    "src.repair_fallback_controller.call_provider",
                    return_value=(SUCCESS_BODY, fake_meta),
                ):
                    result = controller.RepairFallbackController(
                        primary_provider="codex",
                        ledger_writer=writer,
                    ).execute(dict(POST), PROMPT)
            rows = self._read_rows(ledger_path)

        self.assertEqual(result.provider, "codex")
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.body_text, SUCCESS_BODY)
        self.assertTrue(result.wp_write_allowed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "codex")
        self.assertEqual(rows[0]["status"], "success")
        self.assertEqual(rows[0]["provider_meta"]["quality_flags"], [])

    def test_cached_generated_result_skips_provider_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "repair-ledger.jsonl"
            dedupe_path = Path(tmpdir) / "llm_call_dedupe.jsonl"
            writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)
            content_hash = controller.llm_call_dedupe.compute_content_hash(POST["post_id"], POST["current_body"])
            controller.llm_call_dedupe.record_call(
                POST["post_id"],
                content_hash,
                "generated",
                ledger_path=dedupe_path,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text=SUCCESS_BODY,
                fallback_used=False,
                wp_write_allowed=True,
            )
            with patch.object(controller.llm_call_dedupe, "DEFAULT_LEDGER_PATH", dedupe_path), \
                 patch("src.repair_fallback_controller.call_provider") as mocked_call:
                result = controller.RepairFallbackController(
                    primary_provider="codex",
                    ledger_writer=writer,
                ).execute(dict(POST), PROMPT)

        mocked_call.assert_not_called()
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.body_text, SUCCESS_BODY)
        self.assertEqual(result.llm_skip_reason, "content_hash_dedupe")

    def test_cached_failed_result_skips_provider_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "repair-ledger.jsonl"
            dedupe_path = Path(tmpdir) / "llm_call_dedupe.jsonl"
            writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)
            content_hash = controller.llm_call_dedupe.compute_content_hash(POST["post_id"], POST["current_body"])
            controller.llm_call_dedupe.record_call(
                POST["post_id"],
                content_hash,
                "failed",
                ledger_path=dedupe_path,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                error_code="gemini_api_error",
                failure_chain=[{"provider": "gemini", "error_class": "gemini_api_error", "error_message": "cached failure", "latency_ms": 0}],
            )
            with patch.object(controller.llm_call_dedupe, "DEFAULT_LEDGER_PATH", dedupe_path), \
                 patch("src.repair_fallback_controller.call_provider") as mocked_call:
                result = controller.RepairFallbackController(
                    primary_provider="codex",
                    ledger_writer=writer,
                ).execute(dict(POST), PROMPT)

        mocked_call.assert_not_called()
        self.assertIsNone(result.body_text)
        self.assertEqual(result.llm_skip_reason, "content_hash_dedupe")
        self.assertEqual(result.failure_chain[0].error_class, "gemini_api_error")

    def test_wp_write_allowed_env_gate_only_affects_codex(self):
        cases = [
            ("env_unset_codex", {}, "codex", False),
            ("env_false_codex", {"CODEX_WP_WRITE_ALLOWED": "false"}, "codex", False),
            ("env_true_codex", {"CODEX_WP_WRITE_ALLOWED": "true"}, "codex", True),
            ("env_mixed_case_codex", {"CODEX_WP_WRITE_ALLOWED": "TrUe"}, "codex", True),
            ("env_unset_gemini", {}, "gemini", True),
            ("env_false_gemini", {"CODEX_WP_WRITE_ALLOWED": "false"}, "gemini", True),
            ("env_true_gemini", {"CODEX_WP_WRITE_ALLOWED": "true"}, "gemini", True),
            ("env_false_openai", {"CODEX_WP_WRITE_ALLOWED": "false"}, "openai_api", True),
            ("env_true_openai", {"CODEX_WP_WRITE_ALLOWED": "true"}, "openai_api", True),
        ]

        for label, env_overrides, provider_name, expected in cases:
            with self.subTest(label=label):
                with patch.dict(os.environ, env_overrides, clear=False):
                    if "CODEX_WP_WRITE_ALLOWED" not in env_overrides:
                        with patch.dict(os.environ, {}, clear=True):
                            self.assertEqual(controller._wp_write_allowed(provider_name), expected)
                    else:
                        self.assertEqual(controller._wp_write_allowed(provider_name), expected)

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
                self._dedupe_path.unlink(missing_ok=True)
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
