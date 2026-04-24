"""Builder for x_source_notice articles."""

from __future__ import annotations

import html
import re
from urllib.parse import urlsplit, urlunsplit

from src.x_source_notice_contract import SUBTYPE, XSourceNoticeArticle, XSourceNoticePayload


_CLAUSE_SPLIT_RE = re.compile(r"[。！？\r\n]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCTUATION_RE = re.compile(r"[。！？.!?]+$")
_LEADING_BRACKET_RE = re.compile(r"^[【\[\(（].*?[】\]\)）]\s*")


def _normalize_text(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", (value or "").strip())


def _canonicalize_x_url(url: str | None) -> str:
    normalized = _normalize_text(url)
    if not normalized:
        return ""
    parts = urlsplit(normalized)
    netloc = parts.netloc.lower()
    if netloc in {"twitter.com", "www.twitter.com", "mobile.twitter.com", "www.x.com"}:
        netloc = "x.com"
    return urlunsplit((parts.scheme or "https", netloc or "x.com", parts.path, "", ""))


def _split_clauses(text: str | None) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    clauses = [clause.strip() for clause in _CLAUSE_SPLIT_RE.split(normalized) if clause.strip()]
    return clauses


def _first_clause(text: str | None) -> str:
    clauses = _split_clauses(text)
    return clauses[0] if clauses else ""


def _ensure_sentence(text: str | None) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    normalized = _TRAILING_PUNCTUATION_RE.sub("", normalized)
    return f"{normalized}。"


def _strip_leading_label(text: str) -> str:
    return _LEADING_BRACKET_RE.sub("", _normalize_text(text))


def _extract_nucleus_event(payload: XSourceNoticePayload) -> str | None:
    clause = _strip_leading_label(_first_clause(payload.post_text))
    if not clause:
        return None
    prefixes = [
        payload.source_account_name,
        "読売ジャイアンツ",
        "ジャイアンツ",
        "巨人",
        "NPB",
        "日本野球機構",
    ]
    cleaned = clause
    for prefix in prefixes:
        normalized_prefix = _normalize_text(prefix)
        if not normalized_prefix:
            continue
        pattern = re.compile(rf"^{re.escape(normalized_prefix)}(?:は|が|も|、|:|：)\s*")
        cleaned = pattern.sub("", cleaned)
    return _normalize_text(cleaned or clause) or None


def _build_fact_title(payload: XSourceNoticePayload, nucleus_event: str | None) -> str:
    account_name = _normalize_text(payload.source_account_name)
    if account_name and nucleus_event:
        return f"{account_name}、{nucleus_event}"
    return account_name or (nucleus_event or "")


def _build_topic_title(payload: XSourceNoticePayload, nucleus_event: str | None) -> str:
    account_name = _normalize_text(payload.source_account_name)
    snippet = _normalize_text(nucleus_event or _first_clause(payload.post_text))
    if account_name and snippet:
        return f"{account_name}が報じる: {snippet}"
    return account_name or snippet


def _source_tier_label(source_tier: str) -> str:
    normalized = _normalize_text(source_tier).lower()
    return normalized or "unknown"


def _build_source_line(payload: XSourceNoticePayload, canonical_url: str) -> str:
    account_name = html.escape(_normalize_text(payload.source_account_name), quote=False)
    tier_label = html.escape(_source_tier_label(payload.source_tier), quote=False)
    escaped_url = html.escape(canonical_url, quote=True)
    return f'<p>出典: {account_name} [{tier_label}] <a href="{escaped_url}">{escaped_url}</a></p>'


def _build_summary_line(payload: XSourceNoticePayload) -> str:
    summary = _ensure_sentence(_extract_nucleus_event(payload) or _first_clause(payload.post_text) or payload.post_text)
    summary = summary[:-1] if summary.endswith("。") else summary
    return f"<p>「{html.escape(summary, quote=False)}」という投稿。</p>"


def _build_supplement_line(payload: XSourceNoticePayload) -> str | None:
    note = _normalize_text(payload.supplement_note)
    if not note:
        return None
    return f"<p>補足: {html.escape(_ensure_sentence(note), quote=False)}</p>"


def _extract_nucleus_subject(payload: XSourceNoticePayload) -> str | None:
    account_type = _normalize_text(payload.source_account_type).lower()
    if account_type == "team_official":
        return "球団"
    if account_type == "league_official":
        return "NPB"
    if account_type in {"press_major", "press_reporter", "press_misc"}:
        return _normalize_text(payload.source_account_name) or None
    return _normalize_text(payload.source_account_name) or None


def build_x_source_notice_article(
    payload: XSourceNoticePayload,
    *,
    topic_recheck_passed: bool = False,
) -> XSourceNoticeArticle | None:
    """Build an x_source_notice article from a single X source payload."""

    canonical_url = _canonicalize_x_url(payload.source_url)
    source_tier = _normalize_text(payload.source_tier).lower()
    post_kind = _normalize_text(payload.post_kind).lower()
    source_platform = _normalize_text(payload.source_platform).lower()
    source_account_name = _normalize_text(payload.source_account_name)
    source_account_type = _normalize_text(payload.source_account_type).lower()
    nucleus_event = _extract_nucleus_event(payload)

    if source_tier == "fact" or topic_recheck_passed:
        title = _build_fact_title(payload, nucleus_event)
    else:
        title = _build_topic_title(payload, nucleus_event)

    paragraphs = [_build_source_line(payload, canonical_url), _build_summary_line(payload)]
    supplement_line = _build_supplement_line(payload)
    if supplement_line:
        paragraphs.append(supplement_line)

    return XSourceNoticeArticle(
        subtype=SUBTYPE,
        title=title,
        body_html="\n".join(paragraphs),
        badge={
            "platform": "x",
            "source_tier": source_tier,
            "post_kind": post_kind,
            "account_type": source_account_type,
        },
        nucleus_subject=_extract_nucleus_subject(payload),
        nucleus_event=nucleus_event,
        source_platform=source_platform,
        source_url=canonical_url,
        source_account_name=source_account_name,
        source_account_type=source_account_type,
        source_tier=source_tier,
        post_kind=post_kind,
        published_at=payload.published_at,
    )


__all__ = ["build_x_source_notice_article"]
