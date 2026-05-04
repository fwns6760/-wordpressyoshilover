from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER_PATH = Path("/tmp/pub004d/wp_revert_audit_ledger.jsonl")
FALLBACK_LEDGER_PATH = ROOT / "logs" / "wp_revert_audit_ledger.jsonl"
AUDIT_LEDGER_ENV = "ENABLE_WP_REVERT_AUDIT_LEDGER"
BLOCK_ENV = "ENABLE_WP_PUBLISHED_REVERT_GUARD"
LEDGER_PATH_ENV = "WP_REVERT_AUDIT_LEDGER_PATH"
AUDITED_TARGET_STATUSES = frozenset({"draft", "private", "trash"})
BLOCKED_TARGET_STATUSES = frozenset({"draft", "private"})


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def audit_enabled() -> bool:
    return _truthy_env(AUDIT_LEDGER_ENV)


def block_enabled() -> bool:
    return _truthy_env(BLOCK_ENV)


def resolve_ledger_path(value: str | Path | None = None) -> Path:
    if value is not None and str(value).strip():
        return value if isinstance(value, Path) else Path(value)
    env_value = str(os.environ.get(LEDGER_PATH_ENV, "")).strip()
    if env_value:
        return Path(env_value)
    if DEFAULT_LEDGER_PATH.parent.exists():
        return DEFAULT_LEDGER_PATH
    return FALLBACK_LEDGER_PATH


def append_event(
    *,
    post_id: int,
    status_before: str,
    status_after: str,
    caller: str | None,
    source_lane: str | None,
    channel: str,
    blocked: bool,
    reason: str,
    path: str | Path | None = None,
) -> Path:
    ledger_path = resolve_ledger_path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event": "wp_published_revert_attempt",
        "ts": datetime.now(timezone.utc).isoformat(),
        "post_id": int(post_id),
        "status_before": str(status_before or "").strip(),
        "status_after": str(status_after or "").strip(),
        "caller": str(caller or "unknown"),
        "source_lane": str(source_lane or "unknown"),
        "channel": str(channel or "unknown"),
        "blocked": bool(blocked),
        "reason": str(reason or "").strip() or "published_post_status_revert_attempt",
    }
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(json.dumps(payload, ensure_ascii=False))
    return ledger_path
