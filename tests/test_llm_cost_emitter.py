from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from src import llm_cost_emitter


class LlmCostEmitterTests(unittest.TestCase):
    def _emit_payload(self, **overrides: object) -> dict[str, object]:
        stdout = io.StringIO()
        kwargs: dict[str, object] = {
            "lane": "rss_fetcher_grounded",
            "call_site": "rss_fetcher.generate_article_with_gemini",
            "post_id": 1234,
            "source_url": "https://example.com/a",
            "content_hash": "hash-1",
            "model": "gemini-2.5-flash",
            "input_chars": 100,
            "output_chars": 80,
            "token_in": None,
            "token_out": None,
            "cache_hit": False,
            "skip_reason": None,
            "success": True,
            "error_class": None,
            "timestamp": "2026-04-28T10:00:00+0900",
        }
        kwargs.update(overrides)
        with patch("sys.stdout", stdout):
            llm_cost_emitter.emit_llm_cost(**kwargs)
        return json.loads(stdout.getvalue().strip())

    def test_emit_writes_jsonpayload_to_stdout(self):
        payload = self._emit_payload()
        self.assertEqual(payload["event"], "llm_cost")
        self.assertEqual(payload["lane"], "rss_fetcher_grounded")
        self.assertEqual(payload["call_site"], "rss_fetcher.generate_article_with_gemini")
        self.assertEqual(payload["post_id"], 1234)
        self.assertEqual(payload["model"], "gemini-2.5-flash")
        self.assertIn("estimated_cost_jpy", payload)

    def test_emit_no_prompt_or_body_in_payload(self):
        payload = self._emit_payload()
        forbidden = {"prompt", "body_text", "source_text", "secret", "api_key"}
        self.assertTrue(forbidden.isdisjoint(payload.keys()))

    def test_estimate_tokens_from_chars(self):
        self.assertEqual(llm_cost_emitter._estimate_tokens_from_chars(100), 25)

    def test_estimate_cost_jpy_2_5_flash(self):
        self.assertEqual(
            llm_cost_emitter.estimate_cost_jpy("gemini-2.5-flash", 1000, 2000),
            0.795,
        )

    def test_estimate_cost_jpy_2_0_flash(self):
        self.assertEqual(
            llm_cost_emitter.estimate_cost_jpy("gemini-2.0-flash", 1000, 2000),
            0.135,
        )

    def test_estimate_cost_jpy_unknown_model_returns_zero(self):
        self.assertEqual(
            llm_cost_emitter.estimate_cost_jpy("unknown-model", 1000, 2000),
            0.0,
        )

    def test_extract_usage_metadata_present(self):
        self.assertEqual(
            llm_cost_emitter.extract_usage_metadata(
                {
                    "usageMetadata": {
                        "promptTokenCount": 12,
                        "candidatesTokenCount": 7,
                    }
                }
            ),
            (12, 7),
        )

    def test_extract_usage_metadata_absent_returns_none_none(self):
        self.assertEqual(llm_cost_emitter.extract_usage_metadata({}), (None, None))

    def test_emit_uses_usage_metadata_when_provided(self):
        payload = self._emit_payload(token_in=12, token_out=7)
        self.assertEqual(payload["token_source"], "usage_metadata")
        self.assertEqual(payload["token_in_estimate"], 12)
        self.assertEqual(payload["token_out_estimate"], 7)

    def test_emit_falls_back_to_char_div_4_when_metadata_missing(self):
        payload = self._emit_payload(input_chars=100, output_chars=80, token_in=None, token_out=None)
        self.assertEqual(payload["token_source"], "char_div_4")
        self.assertEqual(payload["token_in_estimate"], 25)
        self.assertEqual(payload["token_out_estimate"], 20)

    def test_emit_error_path(self):
        payload = self._emit_payload(success=False, error_class="ConnectionError")
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_class"], "ConnectionError")

    def test_emit_cache_hit(self):
        payload = self._emit_payload(
            cache_hit=True,
            skip_reason="content_hash_dedupe",
            token_in=0,
            token_out=0,
        )
        self.assertTrue(payload["cache_hit"])
        self.assertEqual(payload["skip_reason"], "content_hash_dedupe")

    def test_hash_source_url_deterministic(self):
        first = llm_cost_emitter.hash_source_url("https://example.com/a")
        second = llm_cost_emitter.hash_source_url("https://example.com/a")
        self.assertEqual(first, second)

    def test_hash_source_url_none_returns_none(self):
        self.assertIsNone(llm_cost_emitter.hash_source_url(None))


if __name__ == "__main__":
    unittest.main()
