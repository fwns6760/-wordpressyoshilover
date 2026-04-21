"""Programmatic repair playbook enforcement for ticket 040.

This module encodes the accepted repair policy so downstream callers can:
1. order fail tags by the fixed repair priority,
2. derive the allowed repair actions / scope for the chosen lane, and
3. emit ledger-compatible fields for ticket 038.

The public API intentionally stays small and data-oriented.
"""

from __future__ import annotations

from dataclasses import dataclass


REPAIR_PRIORITY = (
    "subtype_boundary",
    "fact_missing",
    "title_body_mismatch",
    "thin_body",
    "attribution_missing",
    "abstract_lead",
    "ai_tone",
    "close_marker",
    "tags_category_minor",
    "duplicate",
    "low_assertability",
    "pickup_miss",
)

SUPPORTED_FAIL_TAGS = frozenset(REPAIR_PRIORITY)
UNREPAIRABLE_ONLY_TAGS = frozenset({"duplicate", "low_assertability", "close_marker", "pickup_miss"})
CONTEXT_FLAGS = frozenset(
    {
        "full_rewrite",
        "source_weak",
        "title_body_core_ambiguous",
        "title_body_core_clear",
    }
)
FIXED_ALLOWED_SCOPES = frozenset({"title_only", "intro_only", "attribution_only", "block_patch"})
VALID_LANES = frozenset({"fixed", "agent"})
VALID_OUTCOMES = frozenset({"accept_draft", "repair_closed", "escalated"})

_PRIORITY_INDEX = {tag: index for index, tag in enumerate(REPAIR_PRIORITY)}
_FAIL_TAG_TO_ACTIONS = {
    "subtype_boundary": ("template_restore", "block_reorder"),
    "fact_missing": ("fact_block_add",),
    "title_body_mismatch": ("title_fix",),
    "thin_body": ("fact_block_add",),
    "attribution_missing": ("attribution_add",),
    "abstract_lead": ("lead_replace",),
    "duplicate": (),
    "low_assertability": (),
    "pickup_miss": (),
    "close_marker": (),
    "ai_tone": ("lead_replace",),
    "tags_category_minor": (),
}


@dataclass(frozen=True)
class RepairPlan:
    ordered_fail_tags: tuple[str, ...]
    repair_actions: tuple[str, ...]
    repair_trigger: str | None
    changed_scope: str | None
    source_recheck_used: str
    search_used: str


def _validate_lane(lane: str) -> None:
    if lane not in VALID_LANES:
        raise ValueError(f"unsupported lane: {lane!r}")


def _split_fail_tags(fail_tags: list[str]) -> tuple[tuple[str, ...], set[str]]:
    seen_fail_tags: set[str] = set()
    normalized_fail_tags: list[str] = []
    context_flags: set[str] = set()

    for raw_tag in fail_tags:
        tag = str(raw_tag or "").strip()
        if not tag:
            continue
        if tag in CONTEXT_FLAGS:
            context_flags.add(tag)
            continue
        if tag not in SUPPORTED_FAIL_TAGS:
            raise ValueError(f"unsupported fail tag: {tag!r}")
        if tag in seen_fail_tags:
            continue
        seen_fail_tags.add(tag)
        normalized_fail_tags.append(tag)

    if "title_body_core_ambiguous" in context_flags and "title_body_core_clear" in context_flags:
        raise ValueError("title body core context cannot be both clear and ambiguous")

    ordered = tuple(sorted(normalized_fail_tags, key=lambda tag: _PRIORITY_INDEX[tag]))
    return ordered, context_flags


def _actions_for_tag(tag: str, context_flags: set[str]) -> tuple[str, ...]:
    if tag == "title_body_mismatch" and "title_body_core_ambiguous" in context_flags:
        # Ambiguous body core must not close with a title-only patch.
        return ("title_fix", "lead_replace")
    return _FAIL_TAG_TO_ACTIONS[tag]


def _collect_actions(ordered_fail_tags: tuple[str, ...], context_flags: set[str]) -> tuple[str, ...]:
    actions: list[str] = []
    seen: set[str] = set()
    for tag in ordered_fail_tags:
        for action in _actions_for_tag(tag, context_flags):
            if action in seen:
                continue
            seen.add(action)
            actions.append(action)
    return tuple(actions)


def _derive_changed_scope(repair_actions: tuple[str, ...], lane: str, context_flags: set[str]) -> str | None:
    if not repair_actions:
        return None

    if "full_rewrite" in context_flags:
        if lane == "fixed":
            raise ValueError("fixed lane cannot request full_rewrite")
        return "full_rewrite"

    unique_actions = set(repair_actions)
    if unique_actions == {"title_fix"}:
        return "title_only"
    if unique_actions == {"lead_replace"}:
        return "intro_only"
    if unique_actions == {"attribution_add"}:
        return "attribution_only"
    return "block_patch"


def _derive_source_recheck_fields(
    ordered_fail_tags: tuple[str, ...],
    context_flags: set[str],
) -> tuple[str, str]:
    source_recheck_used = "no"
    search_used = "no"

    if "fact_missing" in ordered_fail_tags or "thin_body" in ordered_fail_tags:
        source_recheck_used = "yes"
        if "source_weak" in context_flags:
            search_used = "yes"
        return source_recheck_used, search_used

    if "title_body_mismatch" in ordered_fail_tags and "title_body_core_ambiguous" in context_flags:
        source_recheck_used = "yes"

    return source_recheck_used, search_used


def plan_repair(fail_tags: list[str], lane: str) -> RepairPlan:
    _validate_lane(lane)
    ordered_fail_tags, context_flags = _split_fail_tags(fail_tags)
    repair_actions = _collect_actions(ordered_fail_tags, context_flags)

    if "full_rewrite" in context_flags and not repair_actions:
        raise ValueError("full_rewrite requires at least one repair action")

    changed_scope = _derive_changed_scope(repair_actions, lane, context_flags)
    if lane == "fixed" and changed_scope not in FIXED_ALLOWED_SCOPES and changed_scope is not None:
        raise ValueError(f"fixed lane cannot use changed_scope={changed_scope!r}")

    source_recheck_used, search_used = _derive_source_recheck_fields(ordered_fail_tags, context_flags)
    repair_trigger = next((tag for tag in ordered_fail_tags if _actions_for_tag(tag, context_flags)), None)

    return RepairPlan(
        ordered_fail_tags=ordered_fail_tags,
        repair_actions=repair_actions,
        repair_trigger=repair_trigger,
        changed_scope=changed_scope,
        source_recheck_used=source_recheck_used,
        search_used=search_used,
    )


def decide_outcome(plan: RepairPlan, validators_pass_after: bool, repair_attempts: int) -> str:
    if repair_attempts < 0:
        raise ValueError("repair_attempts must be >= 0")

    if plan.ordered_fail_tags and set(plan.ordered_fail_tags).issubset(UNREPAIRABLE_ONLY_TAGS):
        return "escalated"
    if repair_attempts > 1:
        return "escalated"
    if not validators_pass_after:
        return "escalated"
    if repair_attempts == 0:
        return "accept_draft"
    if repair_attempts == 1:
        return "repair_closed"
    return "escalated"


def ledger_fields(plan: RepairPlan, lane: str, outcome: str) -> dict[str, object]:
    _validate_lane(lane)
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"unsupported outcome: {outcome!r}")

    return {
        "repair_applied": "yes" if plan.repair_actions else "no",
        "repair_trigger": plan.repair_trigger,
        "repair_actions": list(plan.repair_actions),
        "source_recheck_used": plan.source_recheck_used,
        "search_used": plan.search_used,
        "changed_scope": plan.changed_scope,
        "outcome": outcome,
    }


__all__ = [
    "RepairPlan",
    "decide_outcome",
    "ledger_fields",
    "plan_repair",
]
