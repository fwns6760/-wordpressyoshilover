"""Digest composition for X draft email candidates (ticket 065-B1)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence
import unicodedata

try:
    from src.x_draft_email_renderer import FIELD_ORDER, XDraftEmailCandidate, render_x_draft_email_candidate
    from src.x_draft_email_validator import CandidateValidationResult, validate_digest_candidates
except ImportError:  # pragma: no cover - direct script import fallback
    from x_draft_email_renderer import FIELD_ORDER, XDraftEmailCandidate, render_x_draft_email_candidate
    from x_draft_email_validator import CandidateValidationResult, validate_digest_candidates


CandidateKey = tuple[str, str, str]


@dataclass(frozen=True)
class DigestCandidate:
    candidate: XDraftEmailCandidate
    candidate_key: CandidateKey
    warnings: tuple[str, ...]

    def to_dict(self, *, include_warnings: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = self.candidate.to_dict()
        if include_warnings and self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class ExcludedCandidate:
    candidate_key: CandidateKey
    hard_fail_tags: tuple[str, ...]


@dataclass(frozen=True)
class DigestBuildResult:
    candidates: tuple[DigestCandidate, ...]
    excluded: tuple[ExcludedCandidate, ...]

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)


def normalize_candidate_key(news_family: Any, entity_primary: Any, event_nucleus: Any) -> CandidateKey:
    """Normalize ``(news_family, entity_primary, event_nucleus)`` for intra-digest dedupe."""

    def normalize_part(value: Any) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or ""))
        return "".join(normalized.split()).lower()

    return (normalize_part(news_family), normalize_part(entity_primary), normalize_part(event_nucleus))


def candidate_key_from_article(article: Mapping[str, Any]) -> CandidateKey:
    return normalize_candidate_key(
        article.get("news_family") or article.get("event_family") or article.get("family"),
        article.get("entity_primary") or article.get("entity") or article.get("player") or article.get("team"),
        article.get("event_nucleus") or article.get("nucleus") or article.get("topic") or article.get("title"),
    )


def build_x_draft_email_digest(
    articles: Sequence[Mapping[str, Any]],
    *,
    max_candidates: int = 5,
    include_warnings: bool = True,
) -> DigestBuildResult:
    rendered = tuple(render_x_draft_email_candidate(article) for article in articles)
    keys = tuple(candidate_key_from_article(article) for article in articles)
    validation = validate_digest_candidates(rendered, keys, max_candidates=max_candidates)

    included: list[DigestCandidate] = []
    excluded: list[ExcludedCandidate] = []
    for candidate, key, result in zip(rendered, keys, validation):
        if result.ok:
            warnings = result.soft_fail_tags if include_warnings else ()
            included.append(DigestCandidate(candidate=candidate, candidate_key=key, warnings=warnings))
        else:
            excluded.append(ExcludedCandidate(candidate_key=key, hard_fail_tags=result.hard_fail_tags))
    return DigestBuildResult(candidates=tuple(included), excluded=tuple(excluded))


def format_digest_human(result: DigestBuildResult, *, include_warnings: bool = True) -> str:
    lines = ["X Draft Email Digest", f"items: {len(result.candidates)}", f"excluded: {result.excluded_count}"]
    for index, item in enumerate(result.candidates, start=1):
        data = item.candidate.to_dict()
        lines.append("")
        lines.append(f"candidate {index}")
        for field in FIELD_ORDER:
            lines.append(f"{field}: {data[field]}")
        if include_warnings and item.warnings:
            lines.append(f"warnings: {', '.join(item.warnings)}")
    return "\n".join(lines)


def format_digest_json(result: DigestBuildResult, *, include_warnings: bool = True) -> str:
    payload = {
        "items": len(result.candidates),
        "excluded": result.excluded_count,
        "candidates": [item.to_dict(include_warnings=include_warnings) for item in result.candidates],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
