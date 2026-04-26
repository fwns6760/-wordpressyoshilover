import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pre_publish_fact_check import detector
from src.pre_publish_fact_check.llm_adapter_gemini import GeminiFlashAdapter
from src.tools import run_pre_publish_fact_check as cli


def make_post(post_id: int, *, body_html: str = "<p>本文</p>") -> dict:
    return {
        "post_id": post_id,
        "title": f"巨人テスト{post_id}",
        "body_html": body_html,
        "body_text": "本文",
        "source_urls": ["https://example.com/source"],
        "source_block": "参照元: https://example.com/source",
        "created_at": "2026-04-26T10:00:00",
        "modified_at": "2026-04-26T10:05:00",
        "categories": [1],
        "tags": [2],
        "inferred_subtype": "postgame",
    }


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeSDK:
    def __init__(self, *, response_text: str | None = None, error: Exception | None = None):
        self.response_text = response_text
        self.error = error
        self.configure_calls: list[str] = []
        self.model_calls: list[dict] = []
        self.generate_calls = 0
        self.prompts: list[str] = []
        self.generation_configs: list[dict] = []

    def configure(self, *, api_key: str) -> None:
        self.configure_calls.append(api_key)

    def GenerativeModel(self, *, model_name: str, system_instruction: str):
        self.model_calls.append(
            {
                "model_name": model_name,
                "system_instruction": system_instruction,
            }
        )
        sdk = self

        class _Model:
            def generate_content(self, prompt: str, generation_config=None):
                sdk.generate_calls += 1
                sdk.prompts.append(prompt)
                sdk.generation_configs.append(generation_config or {})
                if sdk.error is not None:
                    raise sdk.error
                return FakeResponse(sdk.response_text or "")

        return _Model()


class GeminiFlashAdapterTests(unittest.TestCase):
    def test_detect_success_persists_validated_result_to_cache(self):
        response_payload = {
            "overall_severity": "medium",
            "is_4_17_equivalent_risk": False,
            "findings": [
                {
                    "severity": "medium",
                    "risk_type": "unsupported_named_fact",
                    "target": "本文1段落目",
                    "evidence_excerpt": "打率 .476",
                    "why_risky": "source block does not support the number",
                    "suggested_fix": {
                        "operation": "replace",
                        "find_text": ".476",
                        "replace_text": ".276",
                        "rationale": "remove unsupported stat",
                    },
                }
            ],
            "safe_to_publish_after_fixes": True,
            "notes": "1 unsupported numeric-style fact found.",
        }
        fake_sdk = FakeSDK(response_text=json.dumps(response_payload, ensure_ascii=False))
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hallucinate_cache.jsonl"
            adapter = GeminiFlashAdapter(
                api_key="test-key",
                cache_path=cache_path,
                max_calls=5,
            )
            with patch.object(adapter, "_load_sdk_module", return_value=fake_sdk):
                result = adapter.detect(make_post(101))

            self.assertEqual(fake_sdk.generate_calls, 1)
            self.assertEqual(result["post_id"], 101)
            self.assertEqual(result["overall_severity"], "medium")
            self.assertEqual(result["findings"][0]["risk_type"], "unsupported_named_fact")
            self.assertEqual(result["findings"][0]["suggested_fix"]["operation"], "replace")
            self.assertEqual(fake_sdk.configure_calls, ["test-key"])
            self.assertEqual(fake_sdk.generation_configs[0]["response_mime_type"], "application/json")
            self.assertIn('"post_id": 101', fake_sdk.prompts[0])
            cache_lines = cache_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(cache_lines), 1)
            cached_payload = json.loads(cache_lines[0])
            self.assertEqual(cached_payload["result"]["overall_severity"], "medium")

    def test_cache_hit_skips_sdk_and_content_hash_change_misses(self):
        response_payload = {
            "overall_severity": "low",
            "is_4_17_equivalent_risk": False,
            "findings": [],
            "safe_to_publish_after_fixes": True,
            "notes": "clean",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hallucinate_cache.jsonl"
            first_sdk = FakeSDK(response_text=json.dumps(response_payload, ensure_ascii=False))
            first_adapter = GeminiFlashAdapter(api_key="test-key", cache_path=cache_path, max_calls=5)
            with patch.object(first_adapter, "_load_sdk_module", return_value=first_sdk):
                first_result = first_adapter.detect(make_post(202, body_html="<p>本文A</p>"))

            second_sdk = FakeSDK(response_text=json.dumps(response_payload, ensure_ascii=False))
            second_adapter = GeminiFlashAdapter(api_key="test-key", cache_path=cache_path, max_calls=5)
            with patch.object(second_adapter, "_load_sdk_module", return_value=second_sdk):
                cached_result = second_adapter.detect(make_post(202, body_html="<p>本文A</p>"))
                miss_result = second_adapter.detect(make_post(202, body_html="<p>本文B</p>"))

            self.assertEqual(first_result, cached_result)
            self.assertEqual(first_sdk.generate_calls, 1)
            self.assertEqual(second_sdk.generate_calls, 1)
            self.assertEqual(cached_result["content_hash"], first_result["content_hash"])
            self.assertNotEqual(miss_result["content_hash"], first_result["content_hash"])

    def test_error_paths_fallback_to_stub_without_cache_write(self):
        cases = [
            ("rate_limit", RuntimeError("429 rate limit exceeded")),
            ("timeout", TimeoutError("deadline exceeded")),
            ("invalid_json", None),
        ]
        for expected_reason, error in cases:
            with self.subTest(expected_reason=expected_reason):
                response_text = "{not-json}" if error is None else None
                fake_sdk = FakeSDK(response_text=response_text, error=error)
                with tempfile.TemporaryDirectory() as tmpdir:
                    cache_path = Path(tmpdir) / "hallucinate_cache.jsonl"
                    adapter = GeminiFlashAdapter(api_key="test-key", cache_path=cache_path, max_calls=5)
                    with patch.object(adapter, "_load_sdk_module", return_value=fake_sdk):
                        result = adapter.detect(make_post(303))

                expected_stub = detector.build_stub_result(make_post(303))
                self.assertEqual(result["overall_severity"], expected_stub["overall_severity"])
                self.assertEqual(result["findings"], [])
                self.assertIn(expected_reason, result["notes"])
                self.assertFalse(cache_path.exists())

    def test_cli_live_detect_enforces_max_llm_calls_with_mock_sdk(self):
        response_payload = {
            "overall_severity": "none",
            "is_4_17_equivalent_risk": False,
            "findings": [],
            "safe_to_publish_after_fixes": True,
            "notes": "clean",
        }
        fake_sdk = FakeSDK(response_text=json.dumps(response_payload, ensure_ascii=False))
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "extract.json"
            output_path = Path(tmpdir) / "detect.json"
            cache_path = Path(tmpdir) / "hallucinate_cache.jsonl"
            input_path.write_text(
                json.dumps([make_post(1), make_post(2)], ensure_ascii=False),
                encoding="utf-8",
            )

            class PatchedAdapter(GeminiFlashAdapter):
                def __init__(self, *args, **kwargs):
                    kwargs.setdefault("api_key", "test-key")
                    kwargs.setdefault("cache_path", cache_path)
                    super().__init__(*args, **kwargs)

                def _load_sdk_module(self):
                    return fake_sdk

            with patch(
                "src.pre_publish_fact_check.llm_adapter_gemini.GeminiFlashAdapter",
                PatchedAdapter,
            ):
                exit_code = cli.main(
                    [
                        "--mode",
                        "detect",
                        "--live",
                        "--max-llm-calls",
                        "1",
                        "--input-from",
                        str(input_path),
                        "--output",
                        str(output_path),
                    ]
                )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_sdk.generate_calls, 1)
        self.assertEqual(payload[0]["overall_severity"], "none")
        self.assertIn("max_llm_calls_reached:1", payload[1]["notes"])


if __name__ == "__main__":
    unittest.main()
