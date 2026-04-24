"""Contract for instagram/youtube social_video_notice articles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SUPPORTED_PLATFORMS = frozenset({"instagram", "youtube"})
SUPPORTED_MEDIA_KINDS = frozenset({"video", "image", "short"})
SUBTYPE = "social_video_notice"

OPINION_LEAK_PATTERNS = (
    "だろう",
    "と思う",
    "らしい",
    "噂",
    "推測",
    "かもしれない",
    "期待される",
    "見られる",
    "気がする",
    "はずだ",
    "みたい",
)


@dataclass(frozen=True)
class SocialVideoNoticePayload:
    source_platform: str
    source_url: str
    source_account_name: str
    source_account_type: str
    media_kind: str
    caption_or_title: str
    published_at: str | None = None
    supplement_note: str | None = None


@dataclass(frozen=True)
class SocialVideoNoticeArticle:
    subtype: Literal["social_video_notice"]
    title: str
    body_html: str
    badge: dict[str, str]
    nucleus_subject: str
    nucleus_event: str
    source_platform: str
    source_url: str
    source_account_name: str
    source_account_type: str
    media_kind: str
    published_at: str | None


__all__ = [
    "OPINION_LEAK_PATTERNS",
    "SUBTYPE",
    "SUPPORTED_MEDIA_KINDS",
    "SUPPORTED_PLATFORMS",
    "SocialVideoNoticeArticle",
    "SocialVideoNoticePayload",
]
