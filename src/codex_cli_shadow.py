"""Codex CLI shadow runner helpers for ticket 171."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


_AUTH_JSON_MASK = "[auth.json masked]"
_AUTH_JSON_PATH_PATTERN = re.compile(r"(?:(?:~|/)[^\s\"']*auth\.json)|\bauth\.json\b")
_AUTH_FAILURE_KEYWORDS = (
    "401",
    "unauthorized",
    "unauthenticated",
    "authentication failed",
    "auth failed",
)
_DEFAULT_AUTH_JSON_PATH = Path("~/.codex/auth.json")


class CodexSchemaError(RuntimeError):
    """Raised when ``codex exec --json`` returns an unexpected schema."""


class CodexExecError(RuntimeError):
    """Raised when ``codex exec`` exits non-zero."""

    def __init__(self, exit_code: int, stderr: str) -> None:
        self.exit_code = int(exit_code)
        self.stderr = stderr
        detail = stderr or "no stderr"
        super().__init__(f"codex exec failed (exit_code={self.exit_code}): {detail}")


class CodexAuthError(RuntimeError):
    """Raised when Codex CLI authentication fails."""

    def __init__(self, stderr: str) -> None:
        self.stderr = stderr
        detail = stderr or "unauthorized"
        super().__init__(f"codex auth failed: {detail}")


def compute_codex_home(auth_json_path: str | os.PathLike[str]) -> str:
    path = Path(auth_json_path).expanduser()
    if path.name == "auth.json":
        path = path.parent
    return str(path.resolve())


def _sanitize_cli_text(text: str) -> str:
    if not text:
        return ""
    sanitized = _AUTH_JSON_PATH_PATTERN.sub(_AUTH_JSON_MASK, text)
    home_auth_json = str((_DEFAULT_AUTH_JSON_PATH.expanduser()).resolve())
    tmp_auth_json = "/tmp/.codex/auth.json"
    sanitized = sanitized.replace(home_auth_json, _AUTH_JSON_MASK)
    sanitized = sanitized.replace(tmp_auth_json, _AUTH_JSON_MASK)
    return sanitized


def _contains_auth_failure(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in _AUTH_FAILURE_KEYWORDS)


def _build_env(*, auth_mode: str, codex_home: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if auth_mode == "chatgpt_auth":
        env.pop("OPENAI_API_KEY", None)
        if codex_home:
            env["CODEX_HOME"] = codex_home
        return env

    if auth_mode == "api_key":
        api_key = env.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise CodexAuthError("OPENAI_API_KEY is not set")
        env.pop("CODEX_HOME", None)
        return env

    raise ValueError(f"unsupported auth_mode: {auth_mode!r}")


def _parse_stdout_payload(stdout: str) -> tuple[str, dict[str, Any]]:
    stripped = (stdout or "").strip()
    if not stripped:
        raise CodexSchemaError("codex output schema invalid")

    candidates = [stripped]
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if lines and lines[-1] != stripped:
        candidates.append(lines[-1])

    decode_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            decode_error = exc
            continue
        if not isinstance(payload, dict):
            raise CodexSchemaError("codex output schema invalid")
        output = payload.get("output")
        metadata = payload.get("metadata")
        if not isinstance(output, str) or not isinstance(metadata, dict):
            raise CodexSchemaError("codex output schema invalid")
        return output, dict(metadata)

    raise CodexSchemaError("codex output schema invalid") from decode_error


def call_codex(
    prompt: str,
    *,
    auth_mode: str = "chatgpt_auth",
    codex_home: str | None = None,
    timeout: int = 120,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required")

    resolved_codex_home = codex_home
    if auth_mode == "chatgpt_auth" and not resolved_codex_home:
        resolved_codex_home = compute_codex_home(_DEFAULT_AUTH_JSON_PATH)

    env = _build_env(auth_mode=auth_mode, codex_home=resolved_codex_home)
    completed = subprocess.run(
        ["codex", "exec", "--json", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    stderr = _sanitize_cli_text(completed.stderr or "")
    if completed.returncode != 0:
        if _contains_auth_failure(stderr):
            raise CodexAuthError(stderr)
        raise CodexExecError(completed.returncode, stderr)

    return _parse_stdout_payload(completed.stdout or "")


__all__ = [
    "CodexAuthError",
    "CodexExecError",
    "CodexSchemaError",
    "call_codex",
    "compute_codex_home",
]
