"""Gemini cost ledger emitter for Cloud Logging structured JSON.

Each LLM call emits one JSON object to stdout. Cloud Run collects stdout as
structured log payload, so production source of truth is Cloud Logging.
Local JSONL files are for dev/test only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any


_PRICING_USD_PER_M: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-2.0-flash": {"in": 0.10, "out": 0.40},
}
_FX_JPY_PER_USD = float(os.environ.get("LLM_COST_FX_JPY_PER_USD", "150"))


def _estimate_tokens_from_chars(chars: int) -> int:
    """Return a rough token estimate when usageMetadata is unavailable."""
    return max(0, int(chars) // 4)


def estimate_cost_jpy(model: str, token_in: int, token_out: int) -> float:
    """Estimate JPY cost from token counts and static per-model pricing."""
    pricing = _PRICING_USD_PER_M.get(model)
    if not pricing:
        return 0.0
    usd = (
        (token_in / 1_000_000.0) * pricing["in"]
        + (token_out / 1_000_000.0) * pricing["out"]
    )
    return round(usd * _FX_JPY_PER_USD, 4)


def hash_source_url(url: str | None) -> str | None:
    if not url:
        return None
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def extract_usage_metadata(
    gemini_response: dict[str, Any] | None,
) -> tuple[int | None, int | None]:
    """Extract prompt/output token counts from Gemini REST usageMetadata."""
    if not isinstance(gemini_response, dict):
        return None, None
    meta = gemini_response.get("usageMetadata")
    if not isinstance(meta, dict):
        return None, None
    prompt_token_count = meta.get("promptTokenCount")
    candidate_token_count = meta.get("candidatesTokenCount")
    return (
        int(prompt_token_count) if isinstance(prompt_token_count, int) else None,
        int(candidate_token_count) if isinstance(candidate_token_count, int) else None,
    )


def _resolve_tokens(
    *,
    input_chars: int,
    output_chars: int,
    token_in: int | None,
    token_out: int | None,
) -> tuple[int, int, str]:
    has_usage_metadata = token_in is not None or token_out is not None
    resolved_in = token_in if token_in is not None else _estimate_tokens_from_chars(input_chars)
    resolved_out = token_out if token_out is not None else _estimate_tokens_from_chars(output_chars)
    return (
        int(resolved_in),
        int(resolved_out),
        "usage_metadata" if has_usage_metadata else "char_div_4",
    )


def emit_llm_cost(
    *,
    lane: str,
    call_site: str,
    post_id: int | str | None,
    source_url: str | None,
    content_hash: str | None,
    model: str,
    input_chars: int,
    output_chars: int,
    token_in: int | None,
    token_out: int | None,
    cache_hit: bool,
    skip_reason: str | None,
    success: bool,
    error_class: str | None,
    timestamp: str | None = None,
) -> None:
    """Emit one structured llm_cost payload to stdout.

    The interface deliberately accepts only metadata. Prompt text, article body,
    source text, secrets, and env values are never passed to this function.
    """
    resolved_in, resolved_out, token_source = _resolve_tokens(
        input_chars=input_chars,
        output_chars=output_chars,
        token_in=token_in,
        token_out=token_out,
    )
    payload: dict[str, Any] = {
        "event": "llm_cost",
        "lane": lane,
        "call_site": call_site,
        "post_id": post_id,
        "source_url_hash": hash_source_url(source_url),
        "content_hash": content_hash,
        "model": model,
        "input_chars": int(input_chars),
        "output_chars": int(output_chars),
        "token_in_estimate": resolved_in,
        "token_out_estimate": resolved_out,
        "token_source": token_source,
        "estimated_cost_jpy": estimate_cost_jpy(model, resolved_in, resolved_out),
        "cache_hit": bool(cache_hit),
        "skip_reason": skip_reason,
        "success": bool(success),
        "error_class": error_class,
        "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


__all__ = [
    "_FX_JPY_PER_USD",
    "_PRICING_USD_PER_M",
    "_estimate_tokens_from_chars",
    "emit_llm_cost",
    "estimate_cost_jpy",
    "extract_usage_metadata",
    "hash_source_url",
]
