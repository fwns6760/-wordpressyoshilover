from __future__ import annotations

import importlib
import json
import os
import re
from pathlib import Path
from typing import Any

from src.pre_publish_fact_check.contracts import DetectorResult
from src.pre_publish_fact_check.detector import LLMAdapter, build_stub_result


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = ROOT / "logs" / "hallucinate_cache.jsonl"
DEFAULT_MODEL_NAME = "gemini-2.5-flash"

FACT_CHECK_SYSTEM_PROMPT = """
You are the HALLUC-LANE-002 pre-publish fact-check detector for Yoshilover.

Primary mission:
- Verify G3 title/body subject-event alignment.
- Verify G7 numeric/score/date/player facts do not conflict with the cited source.
- Verify G8 the body does not assert named facts unsupported by the provided source block/source URLs.

Return exactly one JSON object matching this schema:
{
  "overall_severity": "none|low|medium|high|critical",
  "is_4_17_equivalent_risk": true|false,
  "findings": [
    {
      "severity": "none|low|medium|high|critical",
      "risk_type": "unsupported_named_fact|unsupported_numeric_fact|unsupported_date_time_fact|unsupported_quote|unsupported_attribution|contradiction|source_mismatch|speculative_claim|stale_or_time_sensitive",
      "target": "brief identifier of the risky claim",
      "evidence_excerpt": "short excerpt from the draft body or source mismatch",
      "why_risky": "short explanation",
      "suggested_fix": {
        "operation": "replace|delete|soften|needs_manual_review",
        "find_text": "exact text to find in the body",
        "replace_text": "replacement text or empty string when deleting",
        "rationale": "why this fix is safer"
      }
    }
  ],
  "safe_to_publish_after_fixes": true|false,
  "notes": "brief summary"
}

Rules:
- Return JSON only. No markdown fences.
- Be conservative: do not invent source evidence.
- If no issue is found, return overall_severity "none", findings [], safe_to_publish_after_fixes true.
- Mark is_4_17_equivalent_risk true when the draft presents unsupported concrete facts, mixed-article contamination, or unverified quotes/results/player status in a reader-visible factual way.
""".strip()


class GeminiFlashAdapter(LLMAdapter):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = DEFAULT_MODEL_NAME,
        cache_path: str | Path = DEFAULT_CACHE_PATH,
        max_calls: int = 5,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or ""
        self._model_name = model_name
        self._cache_path = Path(cache_path)
        self._max_calls = max(0, int(max_calls))
        self._api_calls = 0
        self._cache_loaded = False
        self._cache: dict[str, dict[str, Any]] = {}
        self._sdk_module: Any | None = None
        self._model: Any | None = None

    def detect(self, input_json: dict[str, Any]) -> dict[str, Any]:
        fallback = build_stub_result(input_json)
        cache_key = self._cache_key(
            int(fallback["post_id"]),
            str(fallback["content_hash"]),
        )
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        if not self._api_key:
            return self._fallback(fallback, "gemini_api_key_missing")
        if self._api_calls >= self._max_calls:
            return self._fallback(fallback, f"max_llm_calls_reached:{self._max_calls}")

        try:
            self._api_calls += 1
            payload = self._generate_payload(input_json)
            result = self._normalize_result(payload, fallback)
        except Exception as exc:  # pragma: no cover - exercised by focused tests below
            return self._fallback(fallback, self._classify_error(exc))

        self._append_cache(cache_key, result)
        return result

    def _cache_key(self, post_id: int, content_hash: str) -> str:
        return f"{post_id}:{content_hash}"

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        self._load_cache()
        cached = self._cache.get(cache_key)
        if cached is None:
            return None
        return json.loads(json.dumps(cached, ensure_ascii=False))

    def _load_cache(self) -> None:
        if self._cache_loaded:
            return
        self._cache_loaded = True
        if not self._cache_path.exists():
            return
        with self._cache_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    result = DetectorResult.from_dict(payload["result"]).to_dict()
                    cache_key = self._cache_key(
                        int(payload["post_id"]),
                        str(payload["content_hash"]),
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                self._cache[cache_key] = result

    def _append_cache(self, cache_key: str, result: dict[str, Any]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "post_id": result["post_id"],
            "content_hash": result["content_hash"],
            "result": result,
        }
        with self._cache_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
        self._cache[cache_key] = result

    def _generate_payload(self, input_json: dict[str, Any]) -> dict[str, Any]:
        response = self._get_model().generate_content(
            json.dumps(input_json, ensure_ascii=False, indent=2),
            generation_config={"response_mime_type": "application/json"},
        )
        response_text = self._extract_response_text(response)
        return json.loads(self._strip_code_fence(response_text))

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        sdk = self._load_sdk_module()
        sdk.configure(api_key=self._api_key)
        self._model = sdk.GenerativeModel(
            model_name=self._model_name,
            system_instruction=FACT_CHECK_SYSTEM_PROMPT,
        )
        return self._model

    def _load_sdk_module(self) -> Any:
        if self._sdk_module is None:
            self._sdk_module = importlib.import_module("google.generativeai")
        return self._sdk_module

    def _normalize_result(
        self,
        payload: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("gemini_response_not_object")
        normalized = dict(payload)
        normalized["post_id"] = fallback["post_id"]
        normalized["content_hash"] = fallback["content_hash"]
        return DetectorResult.from_dict(normalized).to_dict()

    def _extract_response_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    return part_text.strip()
        raise ValueError("gemini_response_missing_text")

    def _strip_code_fence(self, response_text: str) -> str:
        stripped = response_text.strip()
        if not stripped.startswith("```"):
            return stripped
        return re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.DOTALL).strip()

    def _fallback(self, fallback: dict[str, Any], reason: str) -> dict[str, Any]:
        result = dict(fallback)
        result["notes"] = (
            "STUB: HALLUC-LANE-001 dry-run. Real LLM detection requires HALLUC-LANE-002. "
            f"Gemini fallback reason={reason}."
        )
        return result

    def _classify_error(self, exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout"
        if isinstance(exc, json.JSONDecodeError):
            return "invalid_json"
        message = str(exc).lower()
        if any(token in message for token in ("429", "rate limit", "too many requests", "resource exhausted")):
            return "rate_limit"
        if any(token in message for token in ("timeout", "timed out", "deadline exceeded")):
            return "timeout"
        if isinstance(exc, ValueError):
            return "invalid_json"
        if isinstance(exc, ImportError):
            return "sdk_unavailable"
        return exc.__class__.__name__.lower()
