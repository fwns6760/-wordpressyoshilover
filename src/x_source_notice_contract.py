"""Contract for x_source_notice articles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


SUBTYPE = "x_source_notice"
SUPPORTED_PLATFORMS = ("x",)
SUPPORTED_TIERS = ("fact", "topic")
SUPPORTED_POST_KINDS = ("post", "quote", "reply")
SUPPORTED_ACCOUNT_TYPES = (
    "team_official",
    "league_official",
    "press_major",
    "press_reporter",
    "press_misc",
)

BANNED_OPINION_PHRASES = (
    "どう見る",
    "本音",
    "思い",
    "語る",
    "コメントまとめ",
    "試合後コメント",
    "Xをどう見る",
    "X をどう見る",
    "Xがコメント",
    "X がコメント",
    "Xについて語る",
    "X について語る",
    "注目したい",
    "振り返りたい",
    "コメントに注目",
    "コメントから見えるもの",
    "選手コメントを読む",
    "コメントに迫る",
)


@dataclass(frozen=True)
class XSourceNoticePayload:
    source_platform: str
    source_url: str
    source_account_name: str
    source_account_type: str
    source_tier: str
    post_kind: str
    post_text: str
    published_at: datetime
    supplement_note: str | None = None


@dataclass(frozen=True)
class XSourceNoticeArticle:
    subtype: Literal["x_source_notice"] = SUBTYPE
    title: str = ""
    body_html: str = ""
    badge: dict[str, str] = field(default_factory=dict)
    nucleus_subject: str | None = None
    nucleus_event: str | None = None
    source_platform: str = ""
    source_url: str = ""
    source_account_name: str = ""
    source_account_type: str = ""
    source_tier: str = ""
    post_kind: str = ""
    published_at: datetime | None = None


__all__ = [
    "BANNED_OPINION_PHRASES",
    "SUBTYPE",
    "SUPPORTED_ACCOUNT_TYPES",
    "SUPPORTED_PLATFORMS",
    "SUPPORTED_POST_KINDS",
    "SUPPORTED_TIERS",
    "XSourceNoticeArticle",
    "XSourceNoticePayload",
]
