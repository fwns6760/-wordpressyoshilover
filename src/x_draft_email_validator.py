"""Rule-first safety validator for X draft email candidates (ticket 065-B1)."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

try:
    from src.x_draft_email_renderer import FIELD_ORDER, XDraftEmailCandidate
except ImportError:  # pragma: no cover - direct script import fallback
    from x_draft_email_renderer import FIELD_ORDER, XDraftEmailCandidate


HARD_FAIL_TAGS = (
    "DRAFT_URL_LEAK",
    "UNGROUNDED_OFFICIAL_FACT",
    "OFFICIAL_INNER_CROSS_CONTAMINATION",
    "MISSING_RISK_NOTE",
    "CANDIDATE_KEY_DUPLICATE",
    "OVER_LIMIT",
)

SOFT_FAIL_TAGS = (
    "OFFICIAL_ALT_IDENTICAL_TO_DRAFT",
    "SAFE_FACT_EXCESS_LENGTH",
    "SOURCE_REF_MISSING",
)

DRAFT_URL_PATTERNS = (
    re.compile(r"(?:\?|&)p=\d+(?:\D|$)", re.IGNORECASE),
    re.compile(r"(?:\?|&)preview(?:=|&|$)", re.IGNORECASE),
    re.compile(r"preview_(?:id|nonce)=", re.IGNORECASE),
    re.compile(r"(?:\?|&)status=draft(?:\D|$)", re.IGNORECASE),
    re.compile(r"(?:\?|&)status=private(?:\D|$)", re.IGNORECASE),
    re.compile(r"wp-admin|post\.php\?post=", re.IGNORECASE),
    re.compile(r"/(?:draft|private)(?:/|\?|#|$)", re.IGNORECASE),
    re.compile(r"下書き|非公開|プレビュー"),
)

HEDGE_PATTERNS = (
    "確認待ち",
    "未確認",
    "再確認",
    "一次確認",
    "事実確認",
    "可能性",
    "見込み",
    "話題",
    "反応",
    "報道",
    "とされています",
    "ようです",
    "かもしれ",
    "断定は避け",
)

ASSERTIVE_PATTERNS = (
    re.compile(r"巨人.{0,20}(?:勝利|敗戦|敗れ|引き分け)"),
    re.compile(r"\d+[-－対]\d+"),
    re.compile(r"[0-9０-９]+[-－対][0-9０-９]+"),
    re.compile(r"(?:登録|抹消|昇格|降格|公示|先発|出場|欠場|離脱|負傷|故障|発表|決定)(?:されました|しました|です|となりました|と発表)"),
    re.compile(r"(?:勝利|敗戦|敗れました|引き分け|決勝打|本塁打|完封)(?:しました|です|となりました|を挙げました)?"),
)

OFFICIAL_INNER_TONE_PATTERNS = (
    re.compile(r"中の人|個人的|正直|私は|僕は|うちの|運営|舞台裏"),
    re.compile(r"思います|感じます|泣ける|最高|しんどい|エモい|たまらない"),
)

INNER_ASSERTIVE_PATTERNS = (
    re.compile(r"巨人.{0,20}(?:勝利しました|敗れました|敗戦しました)"),
    re.compile(r"[0-9０-９]+[-－対][0-9０-９]+で(?:勝利|敗戦|敗れました)"),
    re.compile(r"(?:登録|抹消|昇格|降格|先発|欠場|離脱|負傷|故障|発表|決定)されました"),
)


@dataclass(frozen=True)
class CandidateValidationResult:
    ok: bool
    hard_fail_tags: tuple[str, ...]
    soft_fail_tags: tuple[str, ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.soft_fail_tags


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return tuple(ordered)


def _candidate_dict(candidate: XDraftEmailCandidate | Mapping[str, Any]) -> dict[str, str]:
    if isinstance(candidate, XDraftEmailCandidate):
        return candidate.to_dict()
    return {field: str(candidate.get(field) or "") for field in FIELD_ORDER}


def _candidate_text(candidate: Mapping[str, str]) -> str:
    return "\n".join(candidate.get(field, "") for field in FIELD_ORDER)


def has_draft_url_leak(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in DRAFT_URL_PATTERNS)


def _has_hedge(text: str) -> bool:
    return any(token in text for token in HEDGE_PATTERNS)


def is_assertive_official_fact(text: str) -> bool:
    if not str(text or "").strip():
        return False
    if _has_hedge(text):
        return False
    return any(pattern.search(text) for pattern in ASSERTIVE_PATTERNS)


def _official_has_inner_tone(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in OFFICIAL_INNER_TONE_PATTERNS)


def _inner_has_fact_assertion(text: str) -> bool:
    if not str(text or "").strip():
        return False
    if "断定は避け" in text or "受け止め" in text:
        return False
    return any(pattern.search(text) for pattern in INNER_ASSERTIVE_PATTERNS)


def _validate_candidate_fields(candidate: Mapping[str, str]) -> CandidateValidationResult:
    hard: list[str] = []
    soft: list[str] = []
    source_tier = candidate.get("source_tier", "").strip().lower()
    official_draft = candidate.get("official_draft", "")
    official_alt = candidate.get("official_alt", "")
    inner_angle = candidate.get("inner_angle", "")

    if has_draft_url_leak(_candidate_text(candidate)):
        hard.append("DRAFT_URL_LEAK")
    if source_tier != "fact" and is_assertive_official_fact(official_draft):
        hard.append("UNGROUNDED_OFFICIAL_FACT")
    if _official_has_inner_tone(official_draft) or _official_has_inner_tone(official_alt) or _inner_has_fact_assertion(inner_angle):
        hard.append("OFFICIAL_INNER_CROSS_CONTAMINATION")
    if source_tier in {"topic", "reaction"} and not candidate.get("risk_note", "").strip():
        hard.append("MISSING_RISK_NOTE")

    if official_alt == official_draft:
        soft.append("OFFICIAL_ALT_IDENTICAL_TO_DRAFT")
    if len(candidate.get("safe_fact", "")) > 200:
        soft.append("SAFE_FACT_EXCESS_LENGTH")
    if not candidate.get("source_ref", "").strip():
        soft.append("SOURCE_REF_MISSING")

    hard_tags = _dedupe(hard)
    soft_tags = _dedupe(soft)
    return CandidateValidationResult(ok=not hard_tags, hard_fail_tags=hard_tags, soft_fail_tags=soft_tags)


def validate_candidate(candidate: XDraftEmailCandidate | Mapping[str, Any]) -> CandidateValidationResult:
    """Validate one rendered candidate without digest-level duplicate/limit rules."""
    return _validate_candidate_fields(_candidate_dict(candidate))


def validate_digest_candidates(
    candidates: Sequence[XDraftEmailCandidate | Mapping[str, Any]],
    candidate_keys: Sequence[tuple[str, str, str]],
    *,
    max_candidates: int = 5,
) -> tuple[CandidateValidationResult, ...]:
    """Validate candidates with digest-level duplicate and max-item constraints."""
    seen_keys: set[tuple[str, str, str]] = set()
    accepted_count = 0
    results: list[CandidateValidationResult] = []

    for candidate, key in zip(candidates, candidate_keys):
        base = validate_candidate(candidate)
        hard = list(base.hard_fail_tags)
        soft = list(base.soft_fail_tags)

        if key in seen_keys:
            hard.append("CANDIDATE_KEY_DUPLICATE")
        else:
            seen_keys.add(key)
            if not hard:
                if accepted_count >= max_candidates:
                    hard.append("OVER_LIMIT")
                else:
                    accepted_count += 1

        hard_tags = _dedupe(hard)
        results.append(CandidateValidationResult(ok=not hard_tags, hard_fail_tags=hard_tags, soft_fail_tags=_dedupe(soft)))

    return tuple(results)
