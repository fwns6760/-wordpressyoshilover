"""Reviewable Instagram source registry for Giants social video intake."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "instagram_sources.json"

SOURCE_ROLES = frozenset(
    {
        "official",
        "media",
        "player",
        "development_player",
        "coach",
        "ob",
        "team_staff",
        "candidate_player",
        "former_player",
        "excluded",
    }
)
SOURCE_STATUSES = frozenset({"confirmed", "candidate", "hold", "excluded"})

_HANDLE_RE = re.compile(r"^[a-z0-9._]{1,60}$")


@dataclass(frozen=True)
class InstagramSource:
    handle: str
    display_name: str
    role: str
    status: str
    roster_status: str = ""
    reference: str = ""
    notes: str = ""


def normalize_instagram_handle(value: str | None) -> str:
    """Normalize a handle or Instagram profile URL for registry lookup."""

    raw_value = (value or "").strip()
    if not raw_value:
        return ""

    if raw_value.startswith(("http://", "https://")):
        parsed = urlparse(raw_value)
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts:
            return ""
        raw_value = path_parts[0]

    raw_value = raw_value.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    if raw_value.startswith("@"):
        raw_value = raw_value[1:]
    return raw_value.lower()


def _source_from_dict(item: dict[str, str], *, seen_handles: set[str]) -> InstagramSource:
    handle = normalize_instagram_handle(item.get("handle"))
    if not handle or not _HANDLE_RE.match(handle):
        raise ValueError(f"invalid Instagram handle: {item.get('handle')!r}")
    if handle in seen_handles:
        raise ValueError(f"duplicate Instagram handle: {handle}")
    seen_handles.add(handle)

    role = (item.get("role") or "").strip()
    status = (item.get("status") or "").strip()
    if role not in SOURCE_ROLES:
        raise ValueError(f"unsupported Instagram source role for {handle}: {role}")
    if status not in SOURCE_STATUSES:
        raise ValueError(f"unsupported Instagram source status for {handle}: {status}")

    return InstagramSource(
        handle=handle,
        display_name=(item.get("display_name") or "").strip(),
        role=role,
        status=status,
        roster_status=(item.get("roster_status") or "").strip(),
        reference=(item.get("reference") or "").strip(),
        notes=(item.get("notes") or "").strip(),
    )


def load_instagram_sources(path: str | Path | None = None) -> list[InstagramSource]:
    """Load the review registry from JSON, preserving broad candidate shelves."""

    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw_data = json.loads(config_path.read_text(encoding="utf-8"))
    raw_sources = raw_data.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("instagram_sources.json must contain a sources list")

    seen_handles: set[str] = set()
    sources: list[InstagramSource] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ValueError("each Instagram source must be a JSON object")
        sources.append(_source_from_dict(item, seen_handles=seen_handles))
    return sources


def find_instagram_source(
    handle_or_url: str | None,
    sources: Iterable[InstagramSource] | None = None,
) -> InstagramSource | None:
    """Return a registry source without treating unknown handles as safe."""

    handle = normalize_instagram_handle(handle_or_url)
    if not handle:
        return None
    registry = list(sources) if sources is not None else load_instagram_sources()
    for source in registry:
        if source.handle == handle:
            return source
    return None


def is_review_candidate(source: InstagramSource | None) -> bool:
    """Only confirmed and candidate sources are allowed into human review."""

    return bool(source and source.status in {"confirmed", "candidate"})


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "SOURCE_ROLES",
    "SOURCE_STATUSES",
    "InstagramSource",
    "find_instagram_source",
    "is_review_candidate",
    "load_instagram_sources",
    "normalize_instagram_handle",
]
