"""Validator for x_source_notice articles."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from src.title_body_nucleus_validator import NucleusAlignmentResult, validate_title_body_nucleus
from src.x_source_notice_contract import (
    BANNED_OPINION_PHRASES,
    SUPPORTED_PLATFORMS,
    SUPPORTED_POST_KINDS,
    SUPPORTED_TIERS,
    XSourceNoticeArticle,
    XSourceNoticePayload,
)


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_OPINION_LEAK_RE = re.compile("|".join(re.escape(pattern) for pattern in BANNED_OPINION_PHRASES))


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason_code: str | None
    detail: str | None


def _normalize_text(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", (value or "").strip())


def _plain_text(html_text: str | None) -> str:
    stripped = _HTML_TAG_RE.sub("", html_text or "")
    return html.unescape(_normalize_text(stripped))


def _is_fact_style_title(title: str, account_name: str) -> bool:
    normalized_title = _normalize_text(title)
    normalized_account = _normalize_text(account_name)
    if not normalized_title or not normalized_account:
        return False
    return normalized_title.startswith(f"{normalized_account}、")


def _nucleus_result(
    payload: XSourceNoticePayload,
    article: XSourceNoticeArticle,
) -> NucleusAlignmentResult:
    return validate_title_body_nucleus(
        article.title,
        article.body_html,
        subtype="x_source_notice",
        known_subjects=[_normalize_text(payload.source_account_name)] if _normalize_text(payload.source_account_name) else [],
    )


def validate_x_source_notice(
    payload: XSourceNoticePayload,
    article: XSourceNoticeArticle,
    *,
    topic_recheck_passed: bool = False,
) -> ValidationResult:
    """Validate an x_source_notice payload/article pair."""

    missing_fields = [
        field_name
        for field_name in ("source_url", "source_account_name", "post_text")
        if not _normalize_text(getattr(payload, field_name))
    ]
    if missing_fields:
        return ValidationResult(ok=False, reason_code="SOURCE_MISSING", detail=", ".join(missing_fields))

    if _normalize_text(payload.source_platform).lower() not in SUPPORTED_PLATFORMS:
        return ValidationResult(
            ok=False,
            reason_code="UNSUPPORTED_PLATFORM",
            detail=_normalize_text(payload.source_platform),
        )

    if _normalize_text(payload.source_tier).lower() not in SUPPORTED_TIERS:
        return ValidationResult(
            ok=False,
            reason_code="UNSUPPORTED_TIER",
            detail=_normalize_text(payload.source_tier),
        )

    if _normalize_text(payload.post_kind).lower() not in SUPPORTED_POST_KINDS:
        return ValidationResult(
            ok=False,
            reason_code="UNSUPPORTED_POST_KIND",
            detail=_normalize_text(payload.post_kind),
        )

    body_html = article.body_html or ""
    source_line_missing = []
    if article.source_url not in body_html:
        source_line_missing.append("source_url")
    if article.source_account_name not in body_html:
        source_line_missing.append("source_account_name")
    if source_line_missing:
        return ValidationResult(
            ok=False,
            reason_code="SOURCE_BODY_MISMATCH",
            detail=", ".join(source_line_missing),
        )

    opinion_target = f"{_normalize_text(article.title)}\n{_plain_text(article.body_html)}"
    matched_phrase = _OPINION_LEAK_RE.search(opinion_target)
    if matched_phrase:
        return ValidationResult(
            ok=False,
            reason_code="OPINION_LEAK",
            detail=matched_phrase.group(0),
        )

    nucleus_result = _nucleus_result(payload, article)
    if nucleus_result.reason_code == "MULTIPLE_NUCLEI":
        return ValidationResult(
            ok=False,
            reason_code="MULTIPLE_NUCLEI",
            detail=nucleus_result.detail,
        )
    if nucleus_result.reason_code in {"SUBJECT_ABSENT", "EVENT_DIVERGE"}:
        return ValidationResult(
            ok=False,
            reason_code="TITLE_BODY_MISMATCH",
            detail=f"{nucleus_result.reason_code}: {nucleus_result.detail}",
        )

    if _normalize_text(payload.source_tier).lower() == "topic" and not topic_recheck_passed and _is_fact_style_title(
        article.title, payload.source_account_name
    ):
        return ValidationResult(
            ok=False,
            reason_code="TOPIC_TIER_AS_FACT",
            detail="topic tier cannot use fact-style title without recheck",
        )

    return ValidationResult(ok=True, reason_code=None, detail=None)


__all__ = ["ValidationResult", "validate_x_source_notice"]
