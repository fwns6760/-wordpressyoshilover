"""Normalize ticket 071 nucleus validator results for the existing ledger schema."""

from __future__ import annotations

from src.title_body_nucleus_validator import NucleusAlignmentResult


KNOWN_REASON_CODES = frozenset({"SUBJECT_ABSENT", "EVENT_DIVERGE", "MULTIPLE_NUCLEI"})

_REASON_TO_FAIL_TAGS = {
    "SUBJECT_ABSENT": ("title_body_mismatch",),
    "EVENT_DIVERGE": ("title_body_mismatch",),
    "MULTIPLE_NUCLEI": ("title_body_mismatch",),
}

_REASON_TO_CONTEXT_FLAGS = {
    "SUBJECT_ABSENT": ("ctx_subject_absent",),
    "EVENT_DIVERGE": ("ctx_event_diverge",),
    "MULTIPLE_NUCLEI": ("ctx_multiple_nuclei",),
}


def validator_result_to_fail_tags(result: NucleusAlignmentResult) -> list[str]:
    """Normalize a 071 nucleus validator result into existing ledger fail_tags.

    Known reason_codes (SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI) all
    map to ``title_body_mismatch`` (ledger schema 10 種を壊さない方針).
    aligned=True / unknown reason_code → empty list.
    """

    if not isinstance(result, NucleusAlignmentResult):
        raise TypeError("result must be a NucleusAlignmentResult")

    if not isinstance(result.reason_code, str):
        return []
    return list(_REASON_TO_FAIL_TAGS.get(result.reason_code, ()))


def validator_result_to_context_flags(result: NucleusAlignmentResult) -> list[str]:
    """Emit ledger context flags (ctx_* prefix) for the validator reason_code."""

    if not isinstance(result, NucleusAlignmentResult):
        raise TypeError("result must be a NucleusAlignmentResult")

    if not isinstance(result.reason_code, str):
        return []
    return list(_REASON_TO_CONTEXT_FLAGS.get(result.reason_code, ()))


__all__ = [
    "KNOWN_REASON_CODES",
    "validator_result_to_context_flags",
    "validator_result_to_fail_tags",
]
