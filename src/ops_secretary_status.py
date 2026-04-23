"""Content renderer for the ops secretary status digest (ticket 070)."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


FIELD_ORDER = ("in_flight", "completed", "blocked_parked", "user_action", "next")
FIELD_LABELS = {
    "in_flight": "進行中",
    "completed": "完了",
    "blocked_parked": "blocked/parked",
    "user_action": "user action",
    "next": "next",
}
FIELD_DEFAULTS = {
    "in_flight": "なし",
    "completed": "なし",
    "blocked_parked": "なし",
    "user_action": "なし",
    "next": "待機",
}

USER_ACTION_PRIORITY = {
    "hard_blocker": 0,
    "ticket_decision": 1,
    "info": 2,
}

MAX_FIELD_LENGTH = 400

_DRAFT_URL_PATTERNS = (
    re.compile(r"[\?&]p=\d+\b", re.IGNORECASE),
    re.compile(r"\bstatus=draft\b", re.IGNORECASE),
    re.compile(r"\bpreview(?:=true|_id=|_nonce=|\b)", re.IGNORECASE),
    re.compile(r"/wp-admin/post\.php\b", re.IGNORECASE),
    re.compile(
        r"https?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|"
        r"192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|"
        r"[^/\s]+\.local)\b",
        re.IGNORECASE,
    ),
)
_SECRET_PATTERNS = (
    re.compile(r"\bsk_[A-Za-z0-9_-]+"),
    re.compile(r"\bAKIA[A-Z0-9]*"),
    re.compile(r"\b(?:token|api_key)=[^\s]+", re.IGNORECASE),
    re.compile(r"\b[A-Z][A-Z0-9_]{2,}=[^\s]+"),
    re.compile(
        r"(?=[A-Za-z0-9_-]{32,}\b)(?=[A-Za-z0-9_-]*[A-Za-z])"
        r"(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{32,}"
    ),
)
_DIFF_PATTERNS = (
    re.compile(r"diff --git"),
    re.compile(r"(^|\n)@@(?:\s|$)"),
)


@dataclass(frozen=True)
class OpsStatusDigest:
    in_flight: str
    completed: str
    blocked_parked: str
    user_action: str
    next: str


def _marker(reason: str, *, strict: bool) -> str:
    if strict:
        return f"[reject:{reason}]"
    return f"[REDACTED:{reason}]"


def _redaction_reason(text: str) -> str | None:
    if not text:
        return None
    if any(pattern.search(text) for pattern in _DIFF_PATTERNS):
        return "diff"
    if len(text) > MAX_FIELD_LENGTH:
        return "long_log"
    if any(pattern.search(text) for pattern in _DRAFT_URL_PATTERNS):
        return "draft_url"
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        return "secret"
    return None


def redact_field(text: str, *, strict: bool = False) -> str:
    """Return redacted/rejected field text when forbidden content is present."""

    value = str(text or "")
    reason = _redaction_reason(value)
    if reason is None:
        return value
    return _marker(reason, strict=strict)


def _coerce_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _join_field(value: Any, default: str) -> str:
    lines = _coerce_lines(value)
    if not lines:
        return default
    return " / ".join(lines)


def _candidate_text(candidate: Any) -> str:
    if isinstance(candidate, Mapping):
        return str(candidate.get("text") or candidate.get("message") or "")
    return str(candidate or "")


def _candidate_kind(candidate: Any) -> str:
    if isinstance(candidate, Mapping):
        return str(candidate.get("kind") or "info")
    return "info"


def select_user_action(candidates: list[Any]) -> str:
    """Select one user action by ticket-070 priority rules."""

    usable = [
        (index, _candidate_kind(candidate), _candidate_text(candidate))
        for index, candidate in enumerate(candidates)
    ]
    usable = [(index, kind, text) for index, kind, text in usable if text]
    if not usable:
        return FIELD_DEFAULTS["user_action"]
    selected = min(
        usable,
        key=lambda item: (USER_ACTION_PRIORITY.get(item[1], USER_ACTION_PRIORITY["info"]), item[0]),
    )
    return selected[2]


def render_ops_status_digest(snapshot: Mapping[str, Any], *, strict: bool = False) -> OpsStatusDigest:
    """Build the fixed five-field ops status digest from a state snapshot fixture."""

    in_flight = _join_field(snapshot.get("in_flight") or snapshot.get("in_progress"), FIELD_DEFAULTS["in_flight"])
    completed = _join_field(snapshot.get("completed"), FIELD_DEFAULTS["completed"])
    blocked_parked = _join_field(
        snapshot.get("blocked_parked") or snapshot.get("blocked") or snapshot.get("parked"),
        FIELD_DEFAULTS["blocked_parked"],
    )
    user_action = select_user_action(list(snapshot.get("user_action_candidates") or []))
    next_step = _join_field(snapshot.get("next"), FIELD_DEFAULTS["next"])

    return OpsStatusDigest(
        in_flight=redact_field(in_flight, strict=strict),
        completed=redact_field(completed, strict=strict),
        blocked_parked=redact_field(blocked_parked, strict=strict),
        user_action=redact_field(user_action, strict=strict),
        next=redact_field(next_step, strict=strict),
    )


def format_digest_human(digest: OpsStatusDigest) -> str:
    """Format the digest as the exact five-line human stdout body."""

    values = format_digest_json(digest)
    return "\n".join(f"{FIELD_LABELS[field]}: {values[field]}" for field in FIELD_ORDER)


def format_digest_json(digest: OpsStatusDigest) -> dict[str, str]:
    """Return a five-field JSON-serializable dict."""

    return {field: getattr(digest, field) for field in FIELD_ORDER}
