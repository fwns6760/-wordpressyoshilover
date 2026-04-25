"""Dry-run X post template candidate generator for PUB-005-A2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlsplit

from src.x_published_poster import PublishedArticle, load_post_history, record_post_history


MAX_X_POST_LENGTH = 280
TEMPLATE_TYPE_QUOTE_CLIP = "quote_clip"
TEMPLATE_TYPE_FAN_REACTION_HOOK = "fan_reaction_hook"
TEMPLATE_TYPE_PROGRAM_MEMO = "program_memo"
TEMPLATE_TYPE_SMALL_NOTE = "small_note"
TEMPLATE_TYPES = (
    TEMPLATE_TYPE_QUOTE_CLIP,
    TEMPLATE_TYPE_FAN_REACTION_HOOK,
    TEMPLATE_TYPE_PROGRAM_MEMO,
    TEMPLATE_TYPE_SMALL_NOTE,
)

REFUSE_REASON_POST_NOT_PUBLISH = "post_not_publish"
REFUSE_REASON_ARTICLE_URL_INVALID = "article_url_invalid"
REFUSE_REASON_DUPLICATE_POST_ID_HISTORY = "duplicate_post_id_history"
REFUSE_REASON_REWRITE_TOO_CLOSE = "rewrite_too_close_to_article"
REFUSE_REASON_TEMPLATE_CONTENT_THIN = "template_content_too_thin"

_PROGRAM_KEYWORDS = (
    "番組",
    "放送",
    "配信",
    "中継",
    "出演",
    "実況",
    "解説",
    "radiko",
    "ABEMA",
    "G+",
    "ジータス",
    "BS",
    "CS",
    "テレビ",
    "ラジオ",
)
_FAN_REACTION_HOOKS = (
    (("サヨナラ", "逆転", "連敗ストップ", "連勝", "勝利", "快勝", "白星"), "この勝ち方は大きい。"),
    (("本塁打", "ホームラン", "適時打", "決勝打"), "一気に空気が動いた。"),
    (("スタメン", "先発", "予告先発"), "試合前に押さえたい。"),
    (("公示", "昇格", "登録", "抹消"), "動きが出た。"),
)
_URL_DENY_PATTERNS = (
    re.compile(r"(?:\?|&)preview(?:=|&|$)", re.IGNORECASE),
    re.compile(r"preview_(?:id|nonce)=", re.IGNORECASE),
    re.compile(r"(?:\?|&)status=(?:draft|private)(?:&|$)", re.IGNORECASE),
    re.compile(r"(?:\?|&)p=\d+(?:&|$)", re.IGNORECASE),
    re.compile(r"_private", re.IGNORECASE),
    re.compile(r"/draft(?:/|$)", re.IGNORECASE),
)
_QUOTE_PATTERN = re.compile(r"(?:(?P<speaker>[^「」]{1,12})\s*)?「(?P<quote>[^」]{4,28})」")
_SENTENCE_PATTERN = re.compile(r"[^。！？!?]+[。！？!?]?")
_TRIM_BOUNDARY_CHARS = "。！？!?」』）)]、,， "


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def text(self) -> str:
        return "".join(self._parts)


@dataclass(frozen=True)
class TemplateCandidate:
    post_id: str | int
    article_url: str
    template_type: str
    text: str
    generated_at: str
    refuse_reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.refuse_reason is None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "post_id": self.post_id,
            "article_url": self.article_url,
            "template_type": self.template_type,
            "text": self.text,
            "generated_at": self.generated_at,
        }
        if self.refuse_reason is not None:
            payload["refuse_reason"] = self.refuse_reason
        return payload


@dataclass(frozen=True)
class TemplateCandidateBatch:
    post_id: str | int
    article_url: str
    generated_at: str
    accepted: tuple[TemplateCandidate, ...]
    refused: tuple[TemplateCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "article_url": self.article_url,
            "generated_at": self.generated_at,
            "accepted": [candidate.to_dict() for candidate in self.accepted],
            "refused": [candidate.to_dict() for candidate in self.refused],
        }


def _strip_html(value: str) -> str:
    parser = _HTMLStripper()
    parser.feed(str(value or ""))
    parser.close()
    return parser.text()


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(_strip_html(value or ""))).strip()


def _normalize_similarity(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", _normalize_text(value).lower())


def _split_sentences(value: str | None) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []
    sentences = [match.group(0).strip() for match in _SENTENCE_PATTERN.finditer(text)]
    return [sentence for sentence in sentences if sentence]


def _trim_text(value: str, max_length: int, *, min_length: int = 8) -> str:
    text = _normalize_text(value)
    if len(text) <= max_length:
        return text

    window = text[:max_length].rstrip()
    best_index = -1
    for char in _TRIM_BOUNDARY_CHARS:
        position = window.rfind(char)
        if position >= min_length - 1:
            best_index = max(best_index, position)
    if best_index >= 0:
        trimmed = window[: best_index + 1].rstrip()
        if len(trimmed) >= min_length:
            return trimmed
    return window


def _looks_like_title_rewrite(text: str, title: str) -> bool:
    core = _normalize_similarity(text)
    title_core = _normalize_similarity(title)
    if not core or not title_core:
        return False
    if core == title_core or core.endswith(title_core) or title_core.endswith(core):
        return True
    return SequenceMatcher(a=core, b=title_core).ratio() >= 0.94


def _canonical_url_is_allowed(url: str | None) -> bool:
    normalized = str(url or "").strip()
    if not normalized or any(pattern.search(normalized) for pattern in _URL_DENY_PATTERNS):
        return False
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https":
        return False
    if not hostname or hostname in {"localhost", "internal", "intranet"}:
        return False
    if hostname.endswith((".local", ".internal", ".lan", ".corp")):
        return False
    return True


def _history_contains_post_id(
    post_id: str | int,
    post_history: Mapping[str, Any] | Iterable[str | int] | None,
) -> bool:
    if not post_history:
        return False

    post_key = str(post_id)
    if isinstance(post_history, Mapping):
        if post_key in post_history:
            return True
        return post_id in post_history

    return post_key in {str(item) for item in post_history}


def _extract_quote_fragment(article: PublishedArticle) -> tuple[str, str] | None:
    for source in (article.title, article.excerpt, article.body_first_paragraph):
        text = _normalize_text(source)
        if not text:
            continue
        match = _QUOTE_PATTERN.search(text)
        if not match:
            continue
        quote = _trim_text(match.group("quote"), 28, min_length=4)
        if len(quote) < 4:
            continue
        speaker = _normalize_text(match.group("speaker") or "")
        speaker = re.sub(r"[：:、。・]+$", "", speaker)
        return speaker[-12:], quote
    return None


def _extract_detail_sentence(article: PublishedArticle) -> str:
    title_core = _normalize_similarity(article.title)
    for source in (article.excerpt, article.body_first_paragraph):
        for sentence in _split_sentences(source):
            if len(sentence) < 14:
                continue
            sentence_core = _normalize_similarity(sentence)
            if not sentence_core:
                continue
            if title_core and SequenceMatcher(a=sentence_core, b=title_core).ratio() >= 0.88:
                continue
            return _trim_text(sentence, 96, min_length=14)
    return ""


def _extract_program_fragment(article: PublishedArticle) -> str:
    for source in (article.excerpt, article.body_first_paragraph, article.title):
        for sentence in _split_sentences(source):
            if any(keyword.lower() in sentence.lower() for keyword in _PROGRAM_KEYWORDS):
                return _trim_text(sentence, 96, min_length=12)
    return ""


def _select_fan_reaction_hook(article: PublishedArticle) -> str:
    combined = " ".join(
        filter(
            None,
            (
                _normalize_text(article.title),
                _normalize_text(article.excerpt),
                _normalize_text(article.body_first_paragraph),
            ),
        )
    )
    if any(keyword.lower() in combined.lower() for keyword in _PROGRAM_KEYWORDS):
        return ""
    for keywords, hook in _FAN_REACTION_HOOKS:
        if any(keyword in combined for keyword in keywords):
            return hook
    return ""


def _applicable_template_types(article: PublishedArticle) -> list[str]:
    template_types: list[str] = []
    if _extract_quote_fragment(article):
        template_types.append(TEMPLATE_TYPE_QUOTE_CLIP)
    if _select_fan_reaction_hook(article):
        template_types.append(TEMPLATE_TYPE_FAN_REACTION_HOOK)
    if _extract_program_fragment(article):
        template_types.append(TEMPLATE_TYPE_PROGRAM_MEMO)
    template_types.append(TEMPLATE_TYPE_SMALL_NOTE)
    return template_types


def _build_body(
    article: PublishedArticle,
    template_type: str,
    *,
    detail_sentence: str,
    program_fragment: str,
    fan_reaction_hook: str,
    quote_fragment: tuple[str, str] | None,
) -> tuple[str, str | None]:
    title_summary = _trim_text(article.title, 88, min_length=10)

    if template_type == TEMPLATE_TYPE_QUOTE_CLIP:
        if quote_fragment is None:
            return title_summary, REFUSE_REASON_TEMPLATE_CONTENT_THIN
        speaker, quote = quote_fragment
        lead = f"{speaker}の「{quote}」が残る。" if speaker else f"「{quote}」が残る。"
        if detail_sentence and quote not in detail_sentence:
            return f"{lead} {detail_sentence}".strip(), None
        return lead, None

    if template_type == TEMPLATE_TYPE_FAN_REACTION_HOOK:
        summary = detail_sentence or title_summary
        reason = None if detail_sentence else REFUSE_REASON_REWRITE_TOO_CLOSE
        return f"{fan_reaction_hook} {summary}".strip(), reason

    if template_type == TEMPLATE_TYPE_PROGRAM_MEMO:
        summary = program_fragment or detail_sentence or title_summary
        reason = None if program_fragment else REFUSE_REASON_TEMPLATE_CONTENT_THIN
        return f"番組メモ。{summary}".strip(), reason

    summary = detail_sentence or title_summary
    reason = None if detail_sentence else REFUSE_REASON_REWRITE_TOO_CLOSE
    return f"ひとことメモ。{summary}".strip(), reason


def _finalize_text(body: str, article_url: str) -> str:
    max_body_length = MAX_X_POST_LENGTH - len(article_url) - 1
    normalized_body = _normalize_text(body)
    if max_body_length < 1:
        return article_url
    if len(normalized_body) > max_body_length:
        normalized_body = _trim_text(normalized_body, max_body_length, min_length=1)
    text = f"{normalized_body}\n{article_url}".strip()
    if len(text) <= MAX_X_POST_LENGTH:
        return text
    body_budget = max(MAX_X_POST_LENGTH - len(article_url) - 1, 0)
    return f"{normalized_body[:body_budget].rstrip()}\n{article_url}".strip()


def _blocking_refuse_reason(
    article: PublishedArticle,
    post_history: Mapping[str, Any] | Iterable[str | int] | None,
) -> str | None:
    if str(article.post_status or "").strip().lower() != "publish":
        return REFUSE_REASON_POST_NOT_PUBLISH
    if not _canonical_url_is_allowed(article.canonical_url):
        return REFUSE_REASON_ARTICLE_URL_INVALID
    if _history_contains_post_id(article.article_id, post_history):
        return REFUSE_REASON_DUPLICATE_POST_ID_HISTORY
    return None


def generate_template_candidates(
    article: PublishedArticle | Mapping[str, Any],
    *,
    post_history: Mapping[str, Any] | Iterable[str | int] | None = None,
    now: str | datetime | None = None,
) -> TemplateCandidateBatch:
    published_article = article if isinstance(article, PublishedArticle) else PublishedArticle.from_mapping(article)
    current_time = now if isinstance(now, datetime) else None
    generated_at = (
        current_time.astimezone(timezone.utc).isoformat()
        if current_time is not None
        else str(now).strip() if isinstance(now, str) and str(now).strip()
        else datetime.now(timezone.utc).isoformat()
    )
    detail_sentence = _extract_detail_sentence(published_article)
    program_fragment = _extract_program_fragment(published_article)
    fan_reaction_hook = _select_fan_reaction_hook(published_article)
    quote_fragment = _extract_quote_fragment(published_article)
    blocking_reason = _blocking_refuse_reason(published_article, post_history)

    accepted: list[TemplateCandidate] = []
    refused: list[TemplateCandidate] = []

    for template_type in _applicable_template_types(published_article):
        body, local_reason = _build_body(
            published_article,
            template_type,
            detail_sentence=detail_sentence,
            program_fragment=program_fragment,
            fan_reaction_hook=fan_reaction_hook,
            quote_fragment=quote_fragment,
        )
        text = _finalize_text(body, published_article.canonical_url)
        refuse_reason = blocking_reason or local_reason
        if refuse_reason is None and _looks_like_title_rewrite(body, published_article.title):
            refuse_reason = REFUSE_REASON_REWRITE_TOO_CLOSE

        candidate = TemplateCandidate(
            post_id=published_article.article_id,
            article_url=published_article.canonical_url,
            template_type=template_type,
            text=text,
            generated_at=generated_at,
            refuse_reason=refuse_reason,
        )
        if candidate.accepted:
            accepted.append(candidate)
        else:
            refused.append(candidate)

    return TemplateCandidateBatch(
        post_id=published_article.article_id,
        article_url=published_article.canonical_url,
        generated_at=generated_at,
        accepted=tuple(accepted),
        refused=tuple(refused),
    )


def load_template_candidate_history(path: str | None) -> dict[str, str]:
    return load_post_history(path)


def record_template_candidate_history(
    path: str | None,
    history: dict[str, str],
    post_id: str | int,
    *,
    posted_at: str | datetime | None = None,
) -> None:
    record_post_history(path, history, post_id, posted_at=posted_at)


__all__ = [
    "MAX_X_POST_LENGTH",
    "REFUSE_REASON_ARTICLE_URL_INVALID",
    "REFUSE_REASON_DUPLICATE_POST_ID_HISTORY",
    "REFUSE_REASON_POST_NOT_PUBLISH",
    "REFUSE_REASON_REWRITE_TOO_CLOSE",
    "REFUSE_REASON_TEMPLATE_CONTENT_THIN",
    "TEMPLATE_TYPE_FAN_REACTION_HOOK",
    "TEMPLATE_TYPE_PROGRAM_MEMO",
    "TEMPLATE_TYPE_QUOTE_CLIP",
    "TEMPLATE_TYPE_SMALL_NOTE",
    "TEMPLATE_TYPES",
    "TemplateCandidate",
    "TemplateCandidateBatch",
    "generate_template_candidates",
    "load_template_candidate_history",
    "record_template_candidate_history",
]
