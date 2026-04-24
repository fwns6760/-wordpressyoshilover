"""Validator for instagram/youtube social_video_notice articles."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.social_video_notice_contract import OPINION_LEAK_PATTERNS, SUPPORTED_PLATFORMS, SocialVideoNoticeArticle
from src.title_body_nucleus_validator import validate_title_body_nucleus


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_OPINION_LEAK_RE = re.compile("|".join(re.escape(pattern) for pattern in OPINION_LEAK_PATTERNS))


@dataclass(frozen=True)
class SocialVideoNoticeValidationResult:
    ok: bool
    reason_code: str | None
    detail: str | None


def _normalize_text(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", (value or "").strip())


def _plain_text(html_text: str) -> str:
    stripped = _HTML_TAG_RE.sub("", html_text or "")
    return _normalize_text(stripped)


def _missing_source_fields(article: SocialVideoNoticeArticle) -> list[str]:
    missing: list[str] = []
    for field_name in ("source_url", "source_account_name", "source_account_type"):
        if not _normalize_text(getattr(article, field_name)):
            missing.append(field_name)
    return missing


def _missing_source_line_parts(article: SocialVideoNoticeArticle) -> list[str]:
    missing: list[str] = []
    body_html = article.body_html or ""
    if article.source_url not in body_html:
        missing.append("source_url")
    if article.source_account_name not in body_html:
        missing.append("source_account_name")
    return missing


def validate_social_video_notice_article(
    article: SocialVideoNoticeArticle,
) -> SocialVideoNoticeValidationResult:
    """Validate a social_video_notice article."""

    missing_source_fields = _missing_source_fields(article)
    if missing_source_fields:
        return SocialVideoNoticeValidationResult(
            ok=False,
            reason_code="SOURCE_MISSING",
            detail=", ".join(missing_source_fields),
        )

    if article.source_platform not in SUPPORTED_PLATFORMS:
        return SocialVideoNoticeValidationResult(
            ok=False,
            reason_code="UNSUPPORTED_PLATFORM",
            detail=article.source_platform,
        )

    missing_source_line_parts = _missing_source_line_parts(article)
    if missing_source_line_parts:
        return SocialVideoNoticeValidationResult(
            ok=False,
            reason_code="SOURCE_BODY_MISMATCH",
            detail=", ".join(missing_source_line_parts),
        )

    plain_text = _plain_text(article.body_html)
    matched_pattern = _OPINION_LEAK_RE.search(plain_text)
    if matched_pattern:
        return SocialVideoNoticeValidationResult(
            ok=False,
            reason_code="OPINION_LEAK",
            detail=matched_pattern.group(0),
        )

    nucleus_result = validate_title_body_nucleus(
        article.title,
        article.body_html,
        subtype=article.subtype,
        known_subjects=[article.nucleus_subject],
    )
    if nucleus_result.reason_code == "MULTIPLE_NUCLEI":
        return SocialVideoNoticeValidationResult(
            ok=False,
            reason_code="MULTIPLE_NUCLEI",
            detail=nucleus_result.detail,
        )
    if nucleus_result.reason_code in {"SUBJECT_ABSENT", "EVENT_DIVERGE"}:
        return SocialVideoNoticeValidationResult(
            ok=False,
            reason_code="TITLE_BODY_MISMATCH",
            detail=f"{nucleus_result.reason_code}: {nucleus_result.detail}",
        )
    if not nucleus_result.aligned:
        return SocialVideoNoticeValidationResult(
            ok=False,
            reason_code="TITLE_BODY_MISMATCH",
            detail=nucleus_result.detail,
        )

    return SocialVideoNoticeValidationResult(ok=True, reason_code=None, detail=None)


__all__ = ["SocialVideoNoticeValidationResult", "validate_social_video_notice_article"]
