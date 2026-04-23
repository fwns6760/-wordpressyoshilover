"""Programmatic repair playbook enforcement for ticket 040.

This module encodes the accepted repair policy so downstream callers can:
1. order fail tags by the fixed repair priority,
2. derive the allowed repair actions / scope for the chosen lane, and
3. emit ledger-compatible fields for ticket 038.

The public API intentionally stays small and data-oriented.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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


@dataclass(frozen=True)
class PromotionCandidate:
    kind: str
    window: str
    as_of_date: str
    fail_tag: str
    count: int
    promotion_target: str | None = None
    subtype: str | None = None
    prompt_version: str | None = None
    source_family: str | None = None
    subtypes: tuple[str, ...] = ()
    source_families: tuple[str, ...] = ()
    sample_candidate_keys: tuple[str, ...] = ()
    ratio: float | None = None


@dataclass(frozen=True)
class _LedgerDraft:
    candidate_key: str
    subtype: str
    prompt_version: str
    fail_tags: tuple[str, ...]
    source_family: str
    timestamp: datetime
    outcome: str


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


_LEDGER_SUFFIXES = frozenset({".json", ".jsonl"})
_SAMPLE_KEY_LIMIT = 10
_PROMOTION_PRIORITY = {"036": 0, "037": 1, "035": 2}
_WINDOW_DURATIONS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _iter_ledger_paths(ledger_path: Path) -> tuple[Path, ...]:
    if ledger_path.is_file():
        return (ledger_path,) if ledger_path.suffix.lower() in _LEDGER_SUFFIXES else ()
    if not ledger_path.exists() or not ledger_path.is_dir():
        return ()
    return tuple(
        sorted(path for path in ledger_path.iterdir() if path.is_file() and path.suffix.lower() in _LEDGER_SUFFIXES)
    )


def _iter_json_objects(path: Path) -> Iterable[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    try:
                        item = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        yield item
            return

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        records = payload.get("records")
        if isinstance(records, list):
            for item in records:
                if isinstance(item, dict):
                    yield item
            return
        yield payload


def _string_field(item: dict[str, Any], field: str) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_ledger_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw_value = value.strip()
    if not raw_value:
        return None
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def _normalize_fail_tags(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        raw_tags: Sequence[Any] = tuple(part.strip() for part in value.split(","))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_tags = value
    else:
        return None

    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        tag = str(raw_tag or "").strip()
        if not tag or tag not in SUPPORTED_FAIL_TAGS or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tuple(tags)


def _parse_ledger_draft(item: dict[str, Any]) -> _LedgerDraft | None:
    candidate_key = _string_field(item, "candidate_key")
    subtype = _string_field(item, "subtype")
    prompt_version = _string_field(item, "prompt_version")
    source_family = _string_field(item, "source_family")
    outcome = _string_field(item, "outcome")
    timestamp = _parse_ledger_timestamp(item.get("ts"))
    fail_tags = _normalize_fail_tags(item.get("fail_tags"))

    if not all((candidate_key, subtype, prompt_version, source_family, outcome, timestamp)):
        return None
    if fail_tags is None:
        return None

    return _LedgerDraft(
        candidate_key=candidate_key,
        subtype=subtype,
        prompt_version=prompt_version,
        fail_tags=fail_tags,
        source_family=source_family,
        timestamp=timestamp,
        outcome=outcome,
    )


def _normalize_timestamp_for_now(value: datetime, now: datetime) -> datetime:
    if now.tzinfo is None:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    if value.tzinfo is None:
        return value.replace(tzinfo=now.tzinfo)
    return value.astimezone(now.tzinfo)


def _records_in_window(records: Sequence[_LedgerDraft], *, now: datetime, window: str) -> tuple[_LedgerDraft, ...]:
    cutoff = now - _WINDOW_DURATIONS[window]
    selected: list[_LedgerDraft] = []
    for record in records:
        timestamp = _normalize_timestamp_for_now(record.timestamp, now)
        if cutoff <= timestamp <= now:
            selected.append(record)
    return tuple(selected)


def _sample_keys(records: Sequence[_LedgerDraft]) -> tuple[str, ...]:
    return tuple(record.candidate_key for record in records[:_SAMPLE_KEY_LIMIT])


def _format_list(values: Sequence[str]) -> str:
    return "[" + ",".join(values) + "]"


def _build_036_groups(records: Sequence[_LedgerDraft]) -> dict[tuple[str, str, str], list[_LedgerDraft]]:
    groups: dict[tuple[str, str, str], list[_LedgerDraft]] = defaultdict(list)
    for record in records:
        for fail_tag in record.fail_tags:
            groups[(record.subtype, record.prompt_version, fail_tag)].append(record)
    return groups


def _build_037_groups(records: Sequence[_LedgerDraft]) -> dict[tuple[str, str], list[_LedgerDraft]]:
    groups: dict[tuple[str, str], list[_LedgerDraft]] = defaultdict(list)
    for record in records:
        for fail_tag in record.fail_tags:
            groups[(record.source_family, fail_tag)].append(record)
    return groups


def _sort_candidate(candidate: PromotionCandidate) -> tuple[int, str, str, str, str]:
    return (
        _PROMOTION_PRIORITY.get(candidate.promotion_target or "", 99),
        "0" if candidate.window == "24h" else "1",
        candidate.fail_tag,
        candidate.subtype or candidate.source_family or "",
        candidate.prompt_version or "",
    )


def aggregate_fail_tags(ledger_dir: Path, *, now: datetime) -> list[PromotionCandidate]:
    records: list[_LedgerDraft] = []
    for path in _iter_ledger_paths(Path(ledger_dir)):
        for item in _iter_json_objects(path):
            record = _parse_ledger_draft(item)
            if record is not None:
                records.append(record)

    as_of_date = now.date().isoformat()
    records_24h = _records_in_window(records, now=now, window="24h")
    records_7d = _records_in_window(records, now=now, window="7d")

    trigger_candidates: list[PromotionCandidate] = []
    for (subtype, prompt_version, fail_tag), group_records in sorted(_build_036_groups(records_24h).items()):
        if len(group_records) < 2:
            continue
        trigger_candidates.append(
            PromotionCandidate(
                kind="trigger",
                window="24h",
                as_of_date=as_of_date,
                subtype=subtype,
                prompt_version=prompt_version,
                fail_tag=fail_tag,
                count=len(group_records),
                sample_candidate_keys=_sample_keys(group_records),
            )
        )

    promotion_candidates: list[PromotionCandidate] = []
    emitted_036_groups: set[tuple[str, str, str]] = set()

    groups_24h = _build_036_groups(records_24h)
    for (subtype, prompt_version, fail_tag), group_records in sorted(groups_24h.items()):
        if len(group_records) < 3:
            continue
        emitted_036_groups.add((subtype, prompt_version, fail_tag))
        promotion_candidates.append(
            PromotionCandidate(
                kind="promotion",
                promotion_target="036",
                window="24h",
                as_of_date=as_of_date,
                subtype=subtype,
                prompt_version=prompt_version,
                fail_tag=fail_tag,
                count=len(group_records),
                sample_candidate_keys=_sample_keys(group_records),
            )
        )

    for (subtype, prompt_version, fail_tag), group_records in sorted(_build_036_groups(records_7d).items()):
        if (subtype, prompt_version, fail_tag) in emitted_036_groups or len(group_records) < 5:
            continue
        promotion_candidates.append(
            PromotionCandidate(
                kind="promotion",
                promotion_target="036",
                window="7d",
                as_of_date=as_of_date,
                subtype=subtype,
                prompt_version=prompt_version,
                fail_tag=fail_tag,
                count=len(group_records),
                sample_candidate_keys=_sample_keys(group_records),
            )
        )

    fail_tags_with_036 = {candidate.fail_tag for candidate in promotion_candidates if candidate.promotion_target == "036"}

    for (source_family, fail_tag), group_records in sorted(_build_037_groups(records_7d).items()):
        if fail_tag in fail_tags_with_036:
            continue
        subtypes = tuple(sorted({record.subtype for record in group_records}))
        if len(subtypes) < 2:
            continue
        promotion_candidates.append(
            PromotionCandidate(
                kind="promotion",
                promotion_target="037",
                window="7d",
                as_of_date=as_of_date,
                source_family=source_family,
                fail_tag=fail_tag,
                subtypes=subtypes,
                count=len(group_records),
                sample_candidate_keys=_sample_keys(group_records),
            )
        )

    fail_tags_with_037 = {candidate.fail_tag for candidate in promotion_candidates if candidate.promotion_target == "037"}
    close_marker_records = [record for record in records_7d if "close_marker" in record.fail_tags]
    close_marker_ratio = (len(close_marker_records) / len(records_7d) * 100.0) if records_7d else 0.0
    if (
        close_marker_records
        and "close_marker" not in fail_tags_with_036
        and "close_marker" not in fail_tags_with_037
        and (len(close_marker_records) >= 2 or close_marker_ratio >= 10.0)
    ):
        promotion_candidates.append(
            PromotionCandidate(
                kind="promotion",
                promotion_target="035",
                window="7d",
                as_of_date=as_of_date,
                fail_tag="close_marker",
                count=len(close_marker_records),
                ratio=close_marker_ratio,
                sample_candidate_keys=_sample_keys(close_marker_records),
            )
        )

    promotion_candidates = sorted(promotion_candidates, key=_sort_candidate)

    summary_candidates: list[PromotionCandidate] = []
    fail_tag_records: dict[str, list[_LedgerDraft]] = defaultdict(list)
    for record in records_7d:
        for fail_tag in record.fail_tags:
            fail_tag_records[fail_tag].append(record)
    for fail_tag, group_records in sorted(fail_tag_records.items(), key=lambda item: (-len(item[1]), item[0])):
        summary_candidates.append(
            PromotionCandidate(
                kind="summary",
                window="7d",
                as_of_date=as_of_date,
                fail_tag=fail_tag,
                count=len(group_records),
                subtypes=tuple(sorted({record.subtype for record in group_records})),
                source_families=tuple(sorted({record.source_family for record in group_records})),
                sample_candidate_keys=_sample_keys(group_records),
            )
        )

    return [*trigger_candidates, *promotion_candidates, *summary_candidates]


def _format_candidate(candidate: PromotionCandidate) -> str:
    window = f"{candidate.window:<3}"
    prefix = f"{candidate.as_of_date} {window}"

    if candidate.kind == "trigger":
        line = (
            f"{prefix} trigger subtype={candidate.subtype} fail_tag={candidate.fail_tag} "
            f"prompt_version={candidate.prompt_version} count={candidate.count}"
        )
        if candidate.sample_candidate_keys:
            line = f"{line} keys={_format_list(candidate.sample_candidate_keys)}"
        return line

    if candidate.promotion_target == "036":
        line = (
            f"{prefix} 036候補 subtype={candidate.subtype} fail_tag={candidate.fail_tag} "
            f"prompt_version={candidate.prompt_version} count={candidate.count}"
        )
        if candidate.sample_candidate_keys:
            line = f"{line} keys={_format_list(candidate.sample_candidate_keys)}"
        return line

    if candidate.promotion_target == "037":
        return (
            f"{prefix} 037候補 source_family={candidate.source_family} fail_tag={candidate.fail_tag} "
            f"subtypes={_format_list(candidate.subtypes)} count={candidate.count}"
        )

    if candidate.promotion_target == "035":
        ratio = 0.0 if candidate.ratio is None else candidate.ratio
        return f"{prefix} 035候補 fail_tag={candidate.fail_tag} count={candidate.count} ratio={ratio:.1f}%"

    if candidate.kind == "summary":
        return (
            f"{prefix} summary fail_tag={candidate.fail_tag} count={candidate.count} "
            f"subtypes={_format_list(candidate.subtypes)} source_families={_format_list(candidate.source_families)}"
        )

    return f"{prefix} {candidate.kind} fail_tag={candidate.fail_tag} count={candidate.count}"


def format_promotion_summary(candidates: list[PromotionCandidate]) -> str:
    if not candidates:
        return "no trigger"
    return "\n".join(_format_candidate(candidate) for candidate in candidates)


__all__ = [
    "PromotionCandidate",
    "RepairPlan",
    "aggregate_fail_tags",
    "decide_outcome",
    "format_promotion_summary",
    "ledger_fields",
    "plan_repair",
]
