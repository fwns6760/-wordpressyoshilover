"""Validator for instagram/youtube social_video_notice articles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from src.social_video_notice_contract import OPINION_LEAK_PATTERNS, SUPPORTED_PLATFORMS, SocialVideoNoticeArticle
from src.title_body_nucleus_validator import validate_title_body_nucleus


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_OPINION_LEAK_RE = re.compile("|".join(re.escape(pattern) for pattern in OPINION_LEAK_PATTERNS))
_INSTAGRAM_URL_KINDS = {"p", "reel", "tv"}
_WORDPRESS_EMBED_BLOCK_RE = re.compile(r"<!--\s*wp:embed\b.*?<!--\s*/wp:embed\s*-->", re.DOTALL)
_SOCIAL_SOURCE_LINE_RE = re.compile(r'<p class="yoshilover-social-source">.*?</p>\s*', re.DOTALL)


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


def _is_instagram_article(article: SocialVideoNoticeArticle) -> bool:
    return article.source_platform == "instagram"


def _is_supported_instagram_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname not in {"instagram.com", "www.instagram.com"}:
        return False
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        return False
    return path_parts[0] in _INSTAGRAM_URL_KINDS and bool(path_parts[1])


def _instagram_embed_missing(article: SocialVideoNoticeArticle) -> bool:
    body_html = article.body_html or ""
    required_markers = (
        "<!-- wp:embed",
        "wp-block-embed-instagram",
        '<div class="wp-block-embed__wrapper">',
        "<!-- /wp:embed -->",
    )
    return any(marker not in body_html for marker in required_markers)


def _contains_reuploaded_image(article: SocialVideoNoticeArticle) -> bool:
    body_html = (article.body_html or "").lower()
    return "<img" in body_html or "wp-content/uploads" in body_html or "wp-image-" in body_html


def _body_for_nucleus_validation(article: SocialVideoNoticeArticle) -> str:
    body_html = article.body_html or ""
    body_html = _WORDPRESS_EMBED_BLOCK_RE.sub("", body_html)
    source_subject_line = f"<p>{article.source_account_name}</p>\n" if article.source_account_name else ""
    body_html = _SOCIAL_SOURCE_LINE_RE.sub(source_subject_line, body_html)
    return body_html


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

    if _is_instagram_article(article):
        if not _is_supported_instagram_url(article.source_url):
            return SocialVideoNoticeValidationResult(
                ok=False,
                reason_code="UNSUPPORTED_INSTAGRAM_URL",
                detail=article.source_url,
            )
        if _instagram_embed_missing(article):
            return SocialVideoNoticeValidationResult(
                ok=False,
                reason_code="EMBED_MISSING",
                detail="instagram WordPress embed block is required",
            )
        if _contains_reuploaded_image(article):
            return SocialVideoNoticeValidationResult(
                ok=False,
                reason_code="IMAGE_REUPLOAD_FORBIDDEN",
                detail="instagram body must use source embed/link, not copied images",
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
        _body_for_nucleus_validation(article),
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
