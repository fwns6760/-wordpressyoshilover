"""Reviewable YouTube official/OB source registry for Giants video intake."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "youtube_ob_sources.json"

SOURCE_ROLES = frozenset({
    "official",
    "giants_ob",
    "ob",
    "media",
    "broadcast",
    "coach",
    "player",
    "team_staff",
    "excluded",
})
SOURCE_STATUSES = frozenset({"confirmed", "candidate", "hold", "excluded"})

_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,30}$")
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")


@dataclass(frozen=True)
class YouTubeOBSource:
    channel_id: str
    display_name: str
    role: str
    status: str
    channel_handle: str = ""
    reference: str = ""
    notes: str = ""


def _clean(value: str | None) -> str:
    return (value or "").strip()


def normalize_youtube_channel_id(value: str | None) -> str:
    """Normalize a YouTube channel id, channel URL, or feed URL for lookup."""

    raw_value = _clean(value)
    if not raw_value:
        return ""

    if _CHANNEL_ID_RE.match(raw_value):
        return raw_value

    if raw_value.startswith(("http://", "https://")):
        parsed = urlparse(raw_value)
        query_channel_id = parse_qs(parsed.query).get("channel_id", [""])[0]
        if _CHANNEL_ID_RE.match(query_channel_id):
            return query_channel_id

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == "channel" and _CHANNEL_ID_RE.match(path_parts[1]):
            return path_parts[1]

    return ""


def normalize_youtube_handle(value: str | None) -> str:
    """Normalize a YouTube @handle or handle URL for optional registry lookup."""

    raw_value = _clean(value)
    if not raw_value:
        return ""
    if raw_value.startswith(("http://", "https://")):
        parsed = urlparse(raw_value)
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts:
            return ""
        raw_value = path_parts[0]
    if raw_value.startswith("@"):
        raw_value = raw_value[1:]
    return raw_value.lower()


def normalize_youtube_video_url(url: str | None) -> str:
    """Return a canonical YouTube watch URL when a video id is present."""

    raw_url = _clean(url)
    if not raw_url:
        return ""

    parsed = urlparse(raw_url)
    hostname = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    video_id = ""

    if hostname in {"youtu.be", "www.youtu.be"} and path_parts:
        video_id = path_parts[0]
    elif hostname in {"youtube.com", "www.youtube.com", "m.youtube.com", "mobile.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif path_parts and path_parts[0] in {"shorts", "live", "embed", "v"} and len(path_parts) >= 2:
            video_id = path_parts[1]

    if _VIDEO_ID_RE.match(video_id):
        return f"https://www.youtube.com/watch?v={video_id}"
    return raw_url


def is_supported_youtube_video_url(url: str | None) -> bool:
    """Return True only for a YouTube video URL, not a channel/profile URL."""

    normalized = normalize_youtube_video_url(url)
    parsed = urlparse(normalized)
    if (parsed.hostname or "").lower() not in {"www.youtube.com", "youtube.com"}:
        return False
    if parsed.path != "/watch":
        return False
    return bool(_VIDEO_ID_RE.match(parse_qs(parsed.query).get("v", [""])[0]))


def _source_from_dict(item: dict[str, str], *, seen_channel_ids: set[str]) -> YouTubeOBSource:
    channel_id = normalize_youtube_channel_id(item.get("channel_id"))
    if not channel_id:
        raise ValueError(f"invalid YouTube channel_id: {item.get('channel_id')!r}")
    if channel_id in seen_channel_ids:
        raise ValueError(f"duplicate YouTube channel_id: {channel_id}")
    seen_channel_ids.add(channel_id)

    role = _clean(item.get("role"))
    status = _clean(item.get("status"))
    if role not in SOURCE_ROLES:
        raise ValueError(f"unsupported YouTube source role for {channel_id}: {role}")
    if status not in SOURCE_STATUSES:
        raise ValueError(f"unsupported YouTube source status for {channel_id}: {status}")

    return YouTubeOBSource(
        channel_id=channel_id,
        display_name=_clean(item.get("display_name")),
        role=role,
        status=status,
        channel_handle=_clean(item.get("channel_handle")),
        reference=_clean(item.get("reference")),
        notes=_clean(item.get("notes")),
    )


def load_youtube_ob_sources(path: str | Path | None = None) -> list[YouTubeOBSource]:
    """Load the review registry from JSON, preserving broad candidate shelves."""

    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw_data = json.loads(config_path.read_text(encoding="utf-8"))
    raw_sources = raw_data.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("youtube_ob_sources.json must contain a sources list")

    seen_channel_ids: set[str] = set()
    sources: list[YouTubeOBSource] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ValueError("each YouTube source must be a JSON object")
        sources.append(_source_from_dict(item, seen_channel_ids=seen_channel_ids))
    return sources


def find_youtube_ob_source(
    channel_id_or_url_or_handle: str | None,
    sources: Iterable[YouTubeOBSource] | None = None,
) -> YouTubeOBSource | None:
    """Return a registry source without treating unknown channels as safe."""

    channel_id = normalize_youtube_channel_id(channel_id_or_url_or_handle)
    handle = normalize_youtube_handle(channel_id_or_url_or_handle)
    if not channel_id and not handle:
        return None

    registry = list(sources) if sources is not None else load_youtube_ob_sources()
    for source in registry:
        if channel_id and source.channel_id == channel_id:
            return source
        if handle and normalize_youtube_handle(source.channel_handle) == handle:
            return source
    return None


def is_review_candidate(source: YouTubeOBSource | None) -> bool:
    """Only confirmed and candidate sources are allowed into human review."""

    return bool(source and source.status in {"confirmed", "candidate"} and source.role != "excluded")


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "SOURCE_ROLES",
    "SOURCE_STATUSES",
    "YouTubeOBSource",
    "find_youtube_ob_source",
    "is_review_candidate",
    "is_supported_youtube_video_url",
    "load_youtube_ob_sources",
    "normalize_youtube_channel_id",
    "normalize_youtube_handle",
    "normalize_youtube_video_url",
]
