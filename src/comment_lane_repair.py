"""Bounded repair wrapper for comment-lane validator tags (ticket 067)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src import repair_playbook
from src.comment_lane_validator import FAIL_TAG_NORMALIZATION, HARD_FAIL_TAGS, SOFT_FAIL_TAGS


MAX_SOFT_REPAIR_ROUNDS = 2

SOFT_SCOPE_BY_TAG = {
    "TITLE_GENERIC": "title",
    "TITLE_MISSING_SCENE": "title",
    "TITLE_MISSING_NUCLEUS": "title",
    "LEDE_TOO_VAGUE": "lede",
    "TOO_MANY_HEADINGS": "body_structure",
    "PRONOUN_AMBIGUOUS": "sentence",
    "BODY_ORDER_BROKEN": "slot_order",
}
AGENT_SCOPE_BY_HARD_TAG = {
    "GAME_RESULT_CONFLICT": "fact_header+lede",
    "NO_GAME_BUT_RESULT": "fact_header+lede",
    "SPEAKER_MISSING": "title+lede",
    "QUOTE_UNGROUNDED": "quote_block+source_ref",
    "TITLE_BODY_ENTITY_MISMATCH": "title+lede",
    "SOURCE_TRUST_TOO_LOW": "source_recheck",
}
PLAYBOOK_TRIGGER_BY_SOFT_TAG = {
    "TITLE_GENERIC": "title_body_mismatch",
    "TITLE_MISSING_SCENE": "title_body_mismatch",
    "TITLE_MISSING_NUCLEUS": "title_body_mismatch",
    "LEDE_TOO_VAGUE": "abstract_lead",
    "TOO_MANY_HEADINGS": "subtype_boundary",
    "PRONOUN_AMBIGUOUS": "abstract_lead",
    "BODY_ORDER_BROKEN": "subtype_boundary",
}


@dataclass(frozen=True)
class CommentRepairPlan:
    status: str
    lane: str
    selected_fail_tag: str | None
    normalized_fail_tag: str | None
    repair_scope: str | None
    rounds_used: int
    rounds_remaining: int
    playbook_plan: repair_playbook.RepairPlan | None


def _dedupe(tags: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_tag in tags:
        tag = str(raw_tag or "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        ordered.append(tag)
    return tuple(ordered)


def _first_matching(tags: Sequence[str], expected: Sequence[str]) -> str | None:
    expected_set = set(expected)
    for tag in tags:
        if tag in expected_set:
            return tag
    return None


def plan_comment_repair(fail_tags: Sequence[str], *, round_number: int = 0) -> CommentRepairPlan:
    if round_number < 0:
        raise ValueError("round_number must be >= 0")

    ordered_tags = _dedupe(fail_tags)
    if not ordered_tags:
        return CommentRepairPlan(
            status="accept",
            lane="fixed",
            selected_fail_tag=None,
            normalized_fail_tag=None,
            repair_scope=None,
            rounds_used=round_number,
            rounds_remaining=max(0, MAX_SOFT_REPAIR_ROUNDS - round_number),
            playbook_plan=None,
        )

    hard_tag = _first_matching(ordered_tags, HARD_FAIL_TAGS)
    if hard_tag is not None:
        return CommentRepairPlan(
            status="delegate",
            lane="agent",
            selected_fail_tag=hard_tag,
            normalized_fail_tag=FAIL_TAG_NORMALIZATION[hard_tag],
            repair_scope=AGENT_SCOPE_BY_HARD_TAG.get(hard_tag),
            rounds_used=round_number,
            rounds_remaining=0,
            playbook_plan=None,
        )

    if round_number >= MAX_SOFT_REPAIR_ROUNDS:
        return CommentRepairPlan(
            status="delegate",
            lane="agent",
            selected_fail_tag=ordered_tags[0],
            normalized_fail_tag=FAIL_TAG_NORMALIZATION[ordered_tags[0]],
            repair_scope=SOFT_SCOPE_BY_TAG.get(ordered_tags[0]),
            rounds_used=round_number,
            rounds_remaining=0,
            playbook_plan=None,
        )

    soft_tag = _first_matching(ordered_tags, SOFT_FAIL_TAGS)
    if soft_tag is None:
        raise ValueError(f"unsupported comment fail tags: {ordered_tags!r}")

    normalized = FAIL_TAG_NORMALIZATION[soft_tag]
    playbook_plan = repair_playbook.plan_repair([PLAYBOOK_TRIGGER_BY_SOFT_TAG[soft_tag]], "fixed")
    return CommentRepairPlan(
        status="repair",
        lane="fixed",
        selected_fail_tag=soft_tag,
        normalized_fail_tag=normalized,
        repair_scope=SOFT_SCOPE_BY_TAG[soft_tag],
        rounds_used=round_number,
        rounds_remaining=MAX_SOFT_REPAIR_ROUNDS - round_number - 1,
        playbook_plan=playbook_plan,
    )


__all__ = [
    "AGENT_SCOPE_BY_HARD_TAG",
    "CommentRepairPlan",
    "MAX_SOFT_REPAIR_ROUNDS",
    "PLAYBOOK_TRIGGER_BY_SOFT_TAG",
    "SOFT_SCOPE_BY_TAG",
    "plan_comment_repair",
]
