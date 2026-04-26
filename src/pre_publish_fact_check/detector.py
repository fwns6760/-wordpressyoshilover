from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

from src.pre_publish_fact_check.contracts import DetectorResult, Severity


NOT_IMPLEMENTED_MESSAGE = (
    "HALLUC-LANE-002 で実装。Gemini Flash adapter は cost-bearing で user 判断 8 類型必須"
)


class LLMAdapter(ABC):
    @abstractmethod
    def detect(self, input_json: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


def _content_hash(body_html: str) -> str:
    return hashlib.sha256((body_html or "").encode("utf-8")).hexdigest()


def build_stub_result(extracted_post: dict[str, Any]) -> dict[str, Any]:
    result = DetectorResult(
        post_id=int(extracted_post["post_id"]),
        content_hash=_content_hash(str(extracted_post.get("body_html") or "")),
        overall_severity=Severity.NONE,
        is_4_17_equivalent_risk=False,
        findings=[],
        safe_to_publish_after_fixes=True,
        notes="STUB: HALLUC-LANE-001 dry-run. Real LLM detection requires HALLUC-LANE-002.",
    )
    return result.to_dict()


def detect_posts(
    extracted_posts: list[dict[str, Any]],
    *,
    live: bool = False,
    adapter: LLMAdapter | None = None,
    max_llm_calls: int = 5,
) -> list[dict[str, Any]]:
    if live and adapter is None:
        from src.pre_publish_fact_check.llm_adapter_gemini import GeminiFlashAdapter

        adapter = GeminiFlashAdapter(max_calls=max_llm_calls)
    if adapter is not None:
        return [adapter.detect(post) for post in extracted_posts]
    return [build_stub_result(post) for post in extracted_posts]
