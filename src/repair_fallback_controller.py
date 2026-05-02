"""Fallback controller for repair-provider migration ticket 170."""

from __future__ import annotations

import json
import os
import random
import socket
import subprocess
import time
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from src import llm_call_dedupe
from src import repair_provider_ledger
from src.codex_cli_shadow import CodexAuthError, CodexSchemaError, call_codex
from src.tools import draft_body_editor


_STUB_MODE_ENV = "REPAIR_PROVIDER_STUB_MODE"
_STUB_TEXT_ENV = "REPAIR_PROVIDER_STUB_TEXT"
_CODEX_WP_WRITE_ALLOWED_ENV = "CODEX_WP_WRITE_ALLOWED"
_SUCCESS_TEXT_TEMPLATE = (
    "【試合結果】\n"
    "{provider} stub 成功です。\n"
    "【ハイライト】\n"
    "stub の本文です。\n"
    "【選手成績】\n"
    "stub の本文です。\n"
    "【試合展開】\n"
    "stub の本文です。"
)


@dataclass(frozen=True)
class FailureRecord:
    provider: str
    error_class: str
    error_message: str
    latency_ms: int


@dataclass(frozen=True)
class RepairResult:
    provider: str
    fallback_used: bool
    body_text: str | None
    failure_chain: list[FailureRecord]
    wp_write_allowed: bool = True
    llm_skip_reason: str | None = None
    content_hash: str | None = None


def classify_error(exception: BaseException, http_code: int | None = None) -> str:
    if isinstance(exception, CodexAuthError):
        return "auth_fail_401"
    if isinstance(exception, CodexSchemaError):
        return "schema_invalid"
    if isinstance(exception, subprocess.TimeoutExpired):
        return "timeout"
    code = http_code
    if code is None and isinstance(exception, urllib.error.HTTPError):
        code = exception.code
    if code == 401:
        return "auth_fail_401"
    if code == 429:
        return "rate_limit_429"
    if code is not None and 500 <= code <= 599:
        return "provider_error"
    if isinstance(exception, TimeoutError):
        return "timeout"
    if isinstance(exception, (urllib.error.URLError, socket.timeout)):
        return "network_error"
    if isinstance(exception, json.JSONDecodeError):
        return "schema_invalid"
    return "provider_error"


def _provider_api_key(provider_name: str) -> str:
    if provider_name == "gemini":
        return os.getenv("GEMINI_API_KEY", "").strip()
    if provider_name == "openai_api":
        return os.getenv("OPENAI_API_KEY", "").strip()
    if provider_name == "codex":
        return os.getenv("CODEX_API_KEY", "").strip()
    return ""


def _stub_mode(provider_name: str) -> str:
    provider_key = provider_name.upper()
    for env_key in (
        f"{_STUB_MODE_ENV}_{provider_key}",
        _STUB_MODE_ENV,
    ):
        value = os.getenv(env_key, "").strip().lower()
        if value:
            return value
    return "provider_error"


def _stub_text(provider_name: str) -> str:
    provider_key = provider_name.upper()
    for env_key in (
        f"{_STUB_TEXT_ENV}_{provider_key}",
        _STUB_TEXT_ENV,
    ):
        value = os.getenv(env_key, "")
        if value.strip():
            return value
    return _SUCCESS_TEXT_TEMPLATE.format(provider=provider_name)


def _resolve_random_stub_mode(provider_name: str) -> str:
    choice = random.choice(("success", "provider_error"))
    if choice == "provider_error":
        raise RuntimeError(f"{provider_name} stub provider failure")
    return choice


def _raise_stub_error(provider_name: str, mode: str) -> None:
    url = f"https://stub.invalid/{provider_name}"
    if mode in {"401", "auth_fail_401", "unauthorized"}:
        raise urllib.error.HTTPError(url, 401, "Unauthorized", hdrs=None, fp=None)
    if mode in {"429", "rate_limit_429", "rate_limit"}:
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)
    if mode in {"5xx", "500", "503", "provider_error"}:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", hdrs=None, fp=None)
    if mode in {"network_error", "url_error"}:
        raise urllib.error.URLError("stub network failure")
    if mode in {"timeout"}:
        raise TimeoutError(f"{provider_name} stub timeout")
    if mode in {"schema_invalid", "json"}:
        raise json.JSONDecodeError("stub invalid json", "{}", 0)
    raise RuntimeError(f"{provider_name} stub failure: {mode}")


def _call_stub_provider(provider_name: str, prompt: str, api_key: str) -> tuple[str, dict[str, Any]]:
    del prompt, api_key
    mode = _stub_mode(provider_name)
    if mode == "random":
        mode = _resolve_random_stub_mode(provider_name)
    if mode == "success":
        body_text = _stub_text(provider_name)
        return body_text, {
            "model": f"{provider_name}-stub",
            "raw_response_size": len(body_text.encode("utf-8")),
            "stub_mode": mode,
        }
    _raise_stub_error(provider_name, mode)


def call_openai_api_stub(prompt: str, api_key: str) -> tuple[str, dict[str, Any]]:
    return _call_stub_provider("openai_api", prompt, api_key)


def call_provider(provider_name: str, prompt: str, api_key: str) -> tuple[str, dict[str, Any]]:
    if provider_name == "gemini":
        body_text = draft_body_editor.call_gemini(prompt, api_key)
        return body_text, {
            "model": "gemini-2.5-flash",
            "raw_response_size": len(body_text.encode("utf-8")),
        }
    if provider_name == "codex":
        del api_key
        return call_codex(prompt)
    if provider_name == "openai_api":
        return call_openai_api_stub(prompt, api_key)
    raise ValueError(f"unsupported provider: {provider_name!r}")


def _wp_write_allowed(provider_name: str) -> bool:
    if provider_name != "codex":
        return True
    return os.getenv(_CODEX_WP_WRITE_ALLOWED_ENV, "false").strip().lower() == "true"


class RepairFallbackController:
    def __init__(self, primary_provider: str, fallback_provider: str = "gemini", ledger_writer=None) -> None:
        if ledger_writer is None:
            raise ValueError("ledger_writer is required")
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider
        self.ledger_writer = ledger_writer

    def execute(self, post: dict[str, Any], prompt: str) -> RepairResult:
        post_id = _resolve_post_id(post)
        body_before = str(post.get("current_body") or post.get("body") or "")
        content_hash = llm_call_dedupe.compute_content_hash(post_id, body_before)
        input_hash = repair_provider_ledger.compute_input_hash(
            {
                "post_id": post_id,
                "current_body": body_before,
                "prompt": prompt,
            }
        )
        artifact_uri = _artifact_uri_for_writer(self.ledger_writer)
        run_id = str(uuid4())
        now = repair_provider_ledger._now_jst()
        dedupe_record = llm_call_dedupe.find_recent_record(
            post_id,
            content_hash,
            llm_call_dedupe.DEFAULT_LEDGER_PATH,
            now=now,
        )
        if dedupe_record is not None:
            result = str(dedupe_record.get("result") or "generated")
            cached_failure_chain = _failure_chain_from_payload(dedupe_record.get("failure_chain"))
            if not cached_failure_chain and not str(dedupe_record.get("body_text") or ""):
                cached_failure_chain = [
                    FailureRecord(
                        provider=str(dedupe_record.get("provider") or self.primary_provider),
                        error_class=str(dedupe_record.get("error_code") or "provider_error"),
                        error_message="cached failure",
                        latency_ms=0,
                    )
                ]
            llm_call_dedupe.record_call(
                post_id,
                content_hash,
                result,
                "content_hash_dedupe",
                ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
                now=now,
                provider=dedupe_record.get("provider"),
                model=dedupe_record.get("model"),
                body_text=dedupe_record.get("body_text"),
                error_code=dedupe_record.get("error_code"),
                token_in=dedupe_record.get("token_in"),
                token_out=dedupe_record.get("token_out"),
                cost=dedupe_record.get("cost"),
                fallback_used=dedupe_record.get("fallback_used"),
                wp_write_allowed=dedupe_record.get("wp_write_allowed"),
                failure_chain=dedupe_record.get("failure_chain"),
                reused_from_timestamp=dedupe_record.get("timestamp"),
            )
            if str(dedupe_record.get("body_text") or ""):
                return RepairResult(
                    provider=str(dedupe_record.get("provider") or self.primary_provider),
                    fallback_used=bool(dedupe_record.get("fallback_used", False)),
                    body_text=str(dedupe_record.get("body_text") or ""),
                    failure_chain=cached_failure_chain,
                    wp_write_allowed=bool(dedupe_record.get("wp_write_allowed", True)),
                    llm_skip_reason="content_hash_dedupe",
                    content_hash=content_hash,
                )
            draft_body_editor.emit_ingest_visibility_fix_v1(
                skip_reason="content_hash_dedupe",
                source_path="src/repair_fallback_controller.py",
                post_id=post_id,
                content_hash=content_hash,
                provider=str(dedupe_record.get("provider") or self.primary_provider),
            )
            return RepairResult(
                provider=str(dedupe_record.get("provider") or self.primary_provider),
                fallback_used=bool(dedupe_record.get("fallback_used", False)),
                body_text=None,
                failure_chain=cached_failure_chain,
                wp_write_allowed=bool(dedupe_record.get("wp_write_allowed", True)),
                llm_skip_reason="content_hash_dedupe",
                content_hash=content_hash,
            )

        primary_success, primary_payload = self._attempt_provider(
            provider=self.primary_provider,
            prompt=prompt,
        )
        if primary_success:
            body_text, meta, started_at, finished_at, latency_ms = primary_payload
            wp_write_allowed = _wp_write_allowed(self.primary_provider)
            self._write_entry(
                run_id=run_id,
                provider=self.primary_provider,
                post_id=post_id,
                input_hash=input_hash,
                artifact_uri=artifact_uri,
                current_body=body_before,
                body_text=body_text,
                status="success" if wp_write_allowed else "shadow_only",
                error_code=None,
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=latency_ms,
                meta=meta,
                fallback_from=None,
                fallback_reason=None,
                quality_flags=[] if wp_write_allowed else ["shadow_only"],
            )
            llm_call_dedupe.record_call(
                post_id,
                content_hash,
                "generated",
                ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
                now=finished_at,
                provider=self.primary_provider,
                model=meta.get("model"),
                body_text=body_text,
                error_code=None,
                token_in=None,
                token_out=None,
                cost=None,
                fallback_used=False,
                wp_write_allowed=wp_write_allowed,
                failure_chain=[],
            )
            return RepairResult(
                provider=self.primary_provider,
                fallback_used=False,
                body_text=body_text,
                failure_chain=[],
                wp_write_allowed=wp_write_allowed,
                content_hash=content_hash,
            )

        primary_exc, primary_started_at, primary_finished_at, primary_latency_ms = primary_payload
        primary_error_class = classify_error(primary_exc)
        primary_failure = FailureRecord(
            provider=self.primary_provider,
            error_class=primary_error_class,
            error_message=str(primary_exc),
            latency_ms=primary_latency_ms,
        )
        self._write_entry(
            run_id=run_id,
            provider=self.primary_provider,
            post_id=post_id,
            input_hash=input_hash,
            artifact_uri=artifact_uri,
            current_body=body_before,
            body_text="",
            status="failed",
            error_code=primary_error_class,
            started_at=primary_started_at,
            finished_at=primary_finished_at,
            latency_ms=primary_latency_ms,
            meta={},
            fallback_from=None,
            fallback_reason=None,
            quality_flags=["fallback_candidate"],
        )

        fallback_success, fallback_payload = self._attempt_provider(
            provider=self.fallback_provider,
            prompt=prompt,
        )
        if fallback_success:
            body_text, meta, started_at, finished_at, latency_ms = fallback_payload
            wp_write_allowed = _wp_write_allowed(self.fallback_provider)
            quality_flags = ["fallback_used"]
            if not wp_write_allowed:
                quality_flags.append("shadow_only")
            self._write_entry(
                run_id=run_id,
                provider=self.fallback_provider,
                post_id=post_id,
                input_hash=input_hash,
                artifact_uri=artifact_uri,
                current_body=body_before,
                body_text=body_text,
                status="success" if wp_write_allowed else "shadow_only",
                error_code=None,
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=latency_ms,
                meta=meta,
                fallback_from=self.primary_provider,
                fallback_reason=primary_error_class,
                quality_flags=quality_flags,
            )
            llm_call_dedupe.record_call(
                post_id,
                content_hash,
                "generated",
                ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
                now=finished_at,
                provider=self.fallback_provider,
                model=meta.get("model"),
                body_text=body_text,
                error_code=None,
                token_in=None,
                token_out=None,
                cost=None,
                fallback_used=True,
                wp_write_allowed=wp_write_allowed,
                failure_chain=_failure_chain_to_payload([primary_failure]),
            )
            return RepairResult(
                provider=self.fallback_provider,
                fallback_used=True,
                body_text=body_text,
                failure_chain=[primary_failure],
                wp_write_allowed=wp_write_allowed,
                content_hash=content_hash,
            )

        fallback_exc, fallback_started_at, fallback_finished_at, fallback_latency_ms = fallback_payload
        fallback_error_class = classify_error(fallback_exc)
        fallback_failure = FailureRecord(
            provider=self.fallback_provider,
            error_class=fallback_error_class,
            error_message=str(fallback_exc),
            latency_ms=fallback_latency_ms,
        )
        self._write_entry(
            run_id=run_id,
            provider=self.fallback_provider,
            post_id=post_id,
            input_hash=input_hash,
            artifact_uri=artifact_uri,
            current_body=body_before,
            body_text="",
            status="failed",
            error_code=fallback_error_class,
            started_at=fallback_started_at,
            finished_at=fallback_finished_at,
            latency_ms=fallback_latency_ms,
            meta={},
            fallback_from=self.primary_provider,
            fallback_reason=primary_error_class,
            quality_flags=["fallback_used", "fallback_failed"],
        )
        llm_call_dedupe.record_call(
            post_id,
            content_hash,
            "failed",
            ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
            now=fallback_finished_at,
            provider=self.fallback_provider,
            model=None,
            body_text="",
            error_code=fallback_error_class,
            token_in=None,
            token_out=None,
            cost=None,
            fallback_used=True,
            wp_write_allowed=_wp_write_allowed(self.fallback_provider),
            failure_chain=_failure_chain_to_payload([primary_failure, fallback_failure]),
        )
        return RepairResult(
            provider=self.fallback_provider,
            fallback_used=True,
            body_text=None,
            failure_chain=[primary_failure, fallback_failure],
            wp_write_allowed=_wp_write_allowed(self.fallback_provider),
            content_hash=content_hash,
        )

    def _attempt_provider(
        self,
        *,
        provider: str,
        prompt: str,
    ) -> tuple[bool, Any]:
        started_at = repair_provider_ledger._now_jst()
        started_monotonic = time.monotonic()
        try:
            body_text, meta = call_provider(provider, prompt, _provider_api_key(provider))
            finished_at = repair_provider_ledger._now_jst()
            latency_ms = max(int((time.monotonic() - started_monotonic) * 1000), 0)
            if not body_text.strip():
                raise RuntimeError(f"{provider} returned empty body")
            return True, (body_text, meta, started_at, finished_at, latency_ms)
        except Exception as exc:
            finished_at = repair_provider_ledger._now_jst()
            latency_ms = max(int((time.monotonic() - started_monotonic) * 1000), 0)
            return False, (exc, started_at, finished_at, latency_ms)

    def _write_entry(
        self,
        *,
        run_id: str,
        provider: str,
        post_id: int,
        input_hash: str,
        artifact_uri: str,
        current_body: str,
        body_text: str,
        status: str,
        error_code: str | None,
        started_at,
        finished_at,
        latency_ms: int,
        meta: dict[str, Any],
        fallback_from: str | None,
        fallback_reason: str | None,
        quality_flags: list[str],
    ) -> None:
        body_len_before = len(current_body)
        body_len_after = len(body_text)
        entry = repair_provider_ledger.RepairLedgerEntry(
            schema_version=repair_provider_ledger.SCHEMA_VERSION,
            run_id=run_id,
            lane="repair",
            provider=provider,
            model=str(meta.get("model") or f"{provider}-stub"),
            source_post_id=post_id,
            input_hash=input_hash,
            output_hash=repair_provider_ledger.compute_output_hash(body_text),
            artifact_uri=artifact_uri,
            status=status,
            strict_pass=False,
            error_code=error_code,
            idempotency_key=repair_provider_ledger.make_idempotency_key(
                post_id,
                input_hash,
                provider,
            ),
            created_at=finished_at.isoformat(),
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            metrics={
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": latency_ms,
                "body_len_before": body_len_before,
                "body_len_after": body_len_after,
                "body_len_delta_pct": repair_provider_ledger.compute_body_len_delta_pct(
                    body_len_before,
                    body_len_after,
                ),
            },
            provider_meta={
                "raw_response_size": int(meta.get("raw_response_size", len(body_text.encode("utf-8")))),
                "fallback_from": fallback_from,
                "fallback_reason": fallback_reason,
                "quality_flags": list(quality_flags),
            },
        )
        self.ledger_writer.write(entry)


def _resolve_post_id(post: dict[str, Any]) -> int:
    raw_value = post.get("post_id", post.get("id"))
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"post_id is required for fallback controller: {raw_value!r}") from exc


def _artifact_uri_for_writer(writer: Any) -> str:
    path = getattr(writer, "path", None)
    if path:
        return Path(path).resolve().as_uri()
    collection = getattr(writer, "collection", None)
    if collection:
        return f"firestore://{collection}"
    return f"memory://{writer.__class__.__name__}"


def _failure_chain_to_payload(chain: list[FailureRecord]) -> list[dict[str, Any]]:
    return [
        {
            "provider": item.provider,
            "error_class": item.error_class,
            "error_message": item.error_message,
            "latency_ms": item.latency_ms,
        }
        for item in chain
    ]


def _failure_chain_from_payload(payload: Any) -> list[FailureRecord]:
    if not isinstance(payload, list):
        return []
    chain: list[FailureRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        chain.append(
            FailureRecord(
                provider=str(item.get("provider") or "unknown"),
                error_class=str(item.get("error_class") or "provider_error"),
                error_message=str(item.get("error_message") or "cached failure"),
                latency_ms=int(item.get("latency_ms") or 0),
            )
        )
    return chain


__all__ = [
    "FailureRecord",
    "RepairFallbackController",
    "RepairResult",
    "call_openai_api_stub",
    "call_provider",
    "classify_error",
]
