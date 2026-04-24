"""Builder for instagram/youtube social_video_notice articles."""

from __future__ import annotations

import html
import re

from src.social_video_notice_contract import (
    OPINION_LEAK_PATTERNS,
    SUBTYPE,
    SocialVideoNoticeArticle,
    SocialVideoNoticePayload,
)


_CLAUSE_SPLIT_RE = re.compile(r"[。！？\r\n]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_SENTENCE_RE = re.compile(r"[。！？.!?]+$")
_PLATFORM_LABELS = {"instagram": "Instagram", "youtube": "YouTube"}
_OPINION_LEAK_RE = re.compile("|".join(re.escape(pattern) for pattern in OPINION_LEAK_PATTERNS))


def _normalize_text(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", (value or "").strip())


def _split_clauses(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    return [clause.strip() for clause in _CLAUSE_SPLIT_RE.split(normalized) if clause.strip()]


def _first_clause(text: str) -> str:
    clauses = _split_clauses(text)
    return clauses[0] if clauses else ""


def _ensure_sentence(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    normalized = _TRAILING_SENTENCE_RE.sub("", normalized)
    return f"{normalized}。"


def _display_account_name(account_name: str) -> str:
    normalized = _normalize_text(account_name)
    if not normalized:
        return ""
    if normalized.startswith("@"):
        return normalized
    return f"@{normalized}"


def _platform_label(platform: str) -> str:
    normalized = _normalize_text(platform).lower()
    return _PLATFORM_LABELS.get(normalized, normalized or "Source")


def _contains_opinion_leak(text: str | None) -> bool:
    return bool(_OPINION_LEAK_RE.search(_normalize_text(text)))


def _build_source_line(payload: SocialVideoNoticePayload) -> str:
    source_label = f"{_platform_label(payload.source_platform)} {_display_account_name(payload.source_account_name)}".strip()
    escaped_url = html.escape(_normalize_text(payload.source_url), quote=True)
    escaped_label = html.escape(source_label, quote=False)
    return f'<p>出典: <a href="{escaped_url}">{escaped_label}</a></p>'


def _build_summary_line(payload: SocialVideoNoticePayload) -> str:
    clause = _first_clause(payload.caption_or_title)
    summary = _ensure_sentence(clause or payload.caption_or_title)
    return f"<p>{html.escape(summary, quote=False)}</p>"


def _build_supplement_line(payload: SocialVideoNoticePayload) -> str | None:
    note = _normalize_text(payload.supplement_note)
    if not note or _contains_opinion_leak(note):
        return None
    return f"<p>{html.escape(_ensure_sentence(note), quote=False)}</p>"


def _trim_title(text: str, *, limit: int = 48) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip()


def _build_title(payload: SocialVideoNoticePayload, nucleus_event: str) -> str:
    parts = [_normalize_text(payload.source_account_name), _normalize_text(nucleus_event)]
    combined = " ".join(part for part in parts if part)
    fallback = combined or _normalize_text(payload.caption_or_title)
    return _trim_title(fallback)


def build_social_video_notice_article(
    payload: SocialVideoNoticePayload,
) -> SocialVideoNoticeArticle:
    """Build a social_video_notice article from a single source payload."""

    nucleus_event = _first_clause(payload.caption_or_title)
    paragraphs = [_build_source_line(payload), _build_summary_line(payload)]
    supplement_line = _build_supplement_line(payload)
    if supplement_line:
        paragraphs.append(supplement_line)

    return SocialVideoNoticeArticle(
        subtype=SUBTYPE,
        title=_build_title(payload, nucleus_event),
        body_html="\n".join(paragraphs),
        badge={
            "platform": _normalize_text(payload.source_platform).lower(),
            "media_kind": _normalize_text(payload.media_kind).lower(),
        },
        nucleus_subject=_normalize_text(payload.source_account_name),
        nucleus_event=nucleus_event,
        source_platform=_normalize_text(payload.source_platform).lower(),
        source_url=_normalize_text(payload.source_url),
        source_account_name=_normalize_text(payload.source_account_name),
        source_account_type=_normalize_text(payload.source_account_type),
        media_kind=_normalize_text(payload.media_kind).lower(),
        published_at=payload.published_at,
    )


__all__ = ["build_social_video_notice_article"]
