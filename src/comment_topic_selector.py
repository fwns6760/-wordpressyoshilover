"""Comment-lane topic selection contract for ticket 067.

This module intentionally stays pure and data-oriented. It selects a single
comment nucleus, enforces the 1/1/1/1 gate, and decides whether the material
should become a standalone comment article, be absorbed into postgame, or be
routed away from the fixed comment lane.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


COMMENT_SELECTOR_SLOTS = (
    "speaker",
    "source_ref",
    "game_context",
    "subject_entity",
    "quote_core",
    "downstream_link",
)

COMMENT_LANE = "comment"
REACTION_LANE = "reaction"
ANALYSIS_LANE = "analysis"

ROUTE_STANDALONE = "standalone"
ROUTE_POSTGAME_ABSORB = "postgame_absorb"
ROUTE_REACTION = "reaction"
ROUTE_ANALYSIS = "analysis"

INTERPRETATION_MARKERS = (
    "どう見る",
    "どう読む",
    "見えるもの",
    "注目したい",
    "振り返りたい",
    "考えたい",
    "評価",
    "評論",
    "分析",
    "総論",
    "まとめ",
)
REACTION_SOURCE_MARKERS = ("reaction", "fan", "一般ファン", "fan_reaction")
URL_ONLY_RE = re.compile(r"^https?://", re.IGNORECASE)
_SCENE_SPLIT_RE = re.compile(r"[／/|｜]")
_QUOTED_TEXT_RE = re.compile(r"[「『](.+?)[」』]")


@dataclass(frozen=True)
class CommentTopicSelection:
    lane: str
    route: str
    slots: dict[str, str]
    gate_passed: bool
    standalone_allowed: bool
    absorb_into_postgame: bool
    missing_slots: tuple[str, ...]
    gate_failures: tuple[str, ...]
    speakers: tuple[str, ...]
    scenes: tuple[str, ...]
    nuclei: tuple[str, ...]
    sources: tuple[str, ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    items: list[str] = []
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value:
            continue
        key = re.sub(r"[\s\u3000\"'「」『』]", "", value).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(value)
    return tuple(items)


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _first_present(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        elif value:
            return str(value).strip()
    return ""


def _extract_named_values(payload: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    values: list[str] = []
    for key in keys:
        for item in _sequence(payload.get(key)):
            if isinstance(item, Mapping):
                values.append(_first_present(item, "name", "label", "value", "text"))
            else:
                values.append(str(item or "").strip())
    return _dedupe(values)


def _normalize_source_ref(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if URL_ONLY_RE.match(text):
        return ""
    if "draft" in text.lower() and "http" in text.lower():
        return ""
    return text


def _extract_source_refs(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(
        _extract_named_values(
            payload,
            "source_ref",
            "quote_source",
            "source_name",
            "source_refs",
            "quote_sources",
        )
    )

    for item in _sequence(payload.get("source_links")):
        if not isinstance(item, Mapping):
            continue
        named = _first_present(item, "name", "source_name", "label")
        if named:
            values.append(named)

    return _dedupe(_normalize_source_ref(value) for value in values)


def _extract_scenes(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("scene_type", "game_context", "scene", "scene_candidates"):
        raw_value = payload.get(key)
        for item in _sequence(raw_value):
            text = str(item or "").strip()
            if not text:
                continue
            if key == "scene_candidates":
                values.extend(part.strip() for part in _SCENE_SPLIT_RE.split(text) if part.strip())
            else:
                values.append(text)

    normalized: list[str] = []
    for value in values:
        if any(value in existing or existing in value for existing in normalized):
            continue
        normalized.append(value)
    return _dedupe(normalized)


def _extract_quote_cores(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(_extract_named_values(payload, "quote_core", "quote_candidates", "nucleus_candidates"))
    for text in list(values):
        quoted = _QUOTED_TEXT_RE.findall(text)
        values.extend(item.strip() for item in quoted if item.strip())
    return _dedupe(values)


def _extract_slots(payload: Mapping[str, Any]) -> dict[str, str]:
    slots = {
        "speaker": _first_present(payload, "speaker", "speaker_name"),
        "source_ref": _first_present(payload, "source_ref", "quote_source", "source_name"),
        "game_context": _first_present(payload, "game_context", "scene_type", "scene"),
        "subject_entity": _first_present(payload, "subject_entity", "target_entity"),
        "quote_core": _first_present(payload, "quote_core"),
        "downstream_link": _first_present(payload, "downstream_link", "next_hook", "follow_up"),
    }
    slots["source_ref"] = _normalize_source_ref(slots["source_ref"])
    return slots


def _text_blob(payload: Mapping[str, Any]) -> str:
    values = [
        _first_present(payload, "title", "angle", "summary", "body", "quote_core"),
    ]
    return " ".join(part for part in values if part).strip()


def _is_reaction_source(payload: Mapping[str, Any]) -> bool:
    source_tier = str(payload.get("source_tier") or "").strip().lower()
    trust_tier = str(payload.get("trust_tier") or "").strip().lower()
    quote_source_type = str(payload.get("quote_source_type") or "").strip().lower()
    source_ref = str(payload.get("source_ref") or payload.get("quote_source") or "").strip().lower()
    return (
        source_tier in REACTION_SOURCE_MARKERS
        or trust_tier in {"t3", "reaction"}
        or any(marker in quote_source_type for marker in REACTION_SOURCE_MARKERS)
        or any(marker in source_ref for marker in REACTION_SOURCE_MARKERS)
    )


def _is_analysis_angle(payload: Mapping[str, Any]) -> bool:
    lane_hint = str(payload.get("lane_hint") or payload.get("angle_type") or "").strip().lower()
    if lane_hint in {ANALYSIS_LANE, REACTION_LANE}:
        return lane_hint == ANALYSIS_LANE
    text = _text_blob(payload)
    return any(marker in text for marker in INTERPRETATION_MARKERS)


def _is_standalone_worthy(payload: Mapping[str, Any]) -> bool:
    explicit = payload.get("is_standalone_worthy")
    if explicit is not None:
        return bool(explicit)
    if payload.get("independent_commentary") is not None:
        return bool(payload.get("independent_commentary"))
    if payload.get("standalone_signal") is not None:
        return bool(payload.get("standalone_signal"))
    score = payload.get("independence_score")
    if score is None:
        return False
    try:
        return float(score) >= 0.5
    except (TypeError, ValueError):
        return False


def select_comment_topic(payload: Mapping[str, Any]) -> CommentTopicSelection:
    slots = _extract_slots(payload)
    speakers = _extract_named_values(payload, "speaker", "speaker_name", "speakers", "speaker_candidates")
    scenes = _extract_scenes(payload)
    nuclei = _extract_quote_cores(payload)
    sources = _extract_source_refs(payload)

    gate_failures: list[str] = []
    if len(speakers) != 1:
        gate_failures.append("multiple_speakers" if len(speakers) > 1 else "speaker_missing")
    if len(scenes) != 1:
        gate_failures.append("multiple_scenes" if len(scenes) > 1 else "scene_missing")
    if len(nuclei) != 1:
        gate_failures.append("multiple_nuclei" if len(nuclei) > 1 else "nucleus_missing")
    if len(sources) != 1:
        gate_failures.append("multiple_sources" if len(sources) > 1 else "source_missing")

    missing_slots = tuple(slot for slot, value in slots.items() if not value)
    if missing_slots:
        gate_failures.append("slot_missing")

    lane = COMMENT_LANE
    route = ROUTE_POSTGAME_ABSORB

    if _is_analysis_angle(payload):
        lane = ANALYSIS_LANE
        route = ROUTE_ANALYSIS
        gate_failures.append("analysis_boundary")
    elif _is_reaction_source(payload):
        lane = REACTION_LANE
        route = ROUTE_REACTION
        gate_failures.append("reaction_boundary")

    gate_passed = lane == COMMENT_LANE and not gate_failures and not missing_slots
    standalone_allowed = False
    absorb_into_postgame = False

    if lane == COMMENT_LANE:
        standalone_allowed = gate_passed and bool(slots["downstream_link"]) and _is_standalone_worthy(payload)
        absorb_into_postgame = not standalone_allowed
        route = ROUTE_STANDALONE if standalone_allowed else ROUTE_POSTGAME_ABSORB
        if gate_passed and not standalone_allowed:
            if not slots["downstream_link"]:
                gate_failures.append("missing_downstream_link")
            if not _is_standalone_worthy(payload):
                gate_failures.append("not_independent_enough")

    return CommentTopicSelection(
        lane=lane,
        route=route,
        slots=slots,
        gate_passed=gate_passed,
        standalone_allowed=standalone_allowed,
        absorb_into_postgame=absorb_into_postgame,
        missing_slots=missing_slots,
        gate_failures=tuple(_dedupe(gate_failures)),
        speakers=speakers,
        scenes=scenes,
        nuclei=nuclei,
        sources=sources,
    )


__all__ = [
    "ANALYSIS_LANE",
    "COMMENT_LANE",
    "COMMENT_SELECTOR_SLOTS",
    "CommentTopicSelection",
    "REACTION_LANE",
    "ROUTE_ANALYSIS",
    "ROUTE_POSTGAME_ABSORB",
    "ROUTE_REACTION",
    "ROUTE_STANDALONE",
    "select_comment_topic",
]
