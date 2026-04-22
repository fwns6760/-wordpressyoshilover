"""Lane-agnostic hard-fail helpers for ticket 068."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


GAME_RESULT_CONTEXT_SUBTYPES = frozenset(
    {
        "farm",
        "farm_result",
        "lineup",
        "postgame",
        "pregame",
        "probable_starter",
    }
)
TITLE_BODY_MISMATCH_SUBTYPES = frozenset(
    {
        "fact_notice",
        "farm",
        "farm_result",
        "lineup",
        "notice",
        "postgame",
        "pregame",
        "probable_starter",
        "program",
    }
)

RESULT_SCORE_RE = re.compile(r"(\d{1,2})\s*[－\-–]\s*(\d{1,2})")
RESULT_ASSERTION_RE = re.compile(
    r"(勝利|敗戦|引き分け|引分け|白星|黒星|競り勝った|敗れた|制した|\d{1,2}\s*[－\-–]\s*\d{1,2})"
)
QUOTE_RE = re.compile(r"[「『](.+?)[」』]")

_BODY_TEXT_KEYS = (
    "body",
    "body_text",
    "text",
    "fact_header",
    "lede",
    "quote_block",
    "context",
    "related",
    "summary",
    "excerpt",
    "description",
)
_ENTITY_TOKEN_KEYS = (
    "speaker_name",
    "speaker",
    "subject_entity",
    "target_entity",
    "scene_type",
    "game_context",
    "opponent",
    "scoreline",
)
_TOKEN_SEQUENCE_KEYS = (
    "entity_tokens",
    "required_tokens",
    "quoted_tokens",
    "scene_tokens",
)
_SOURCE_TEXT_KEYS = (
    "title",
    "source_title",
    "summary",
    "source_summary",
    "description",
    "text",
    "source_text",
    "excerpt",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_value in values:
        value = _text(raw_value)
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _iter_text_values(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        texts: list[str] = []
        for nested_value in value.values():
            texts.extend(_iter_text_values(nested_value))
        return texts
    if isinstance(value, (list, tuple, set, frozenset)):
        texts: list[str] = []
        for nested_value in value:
            texts.extend(_iter_text_values(nested_value))
        return texts
    text = _text(value)
    return [text] if text else []


def _body_text(body_slots: Mapping[str, Any] | Sequence[str] | str) -> str:
    if isinstance(body_slots, Mapping):
        lines = []
        for key in _BODY_TEXT_KEYS:
            value = _text(body_slots.get(key))
            if value:
                lines.append(value)
        return "\n".join(lines)
    if isinstance(body_slots, str):
        return _text(body_slots)
    return "\n".join(_text(item) for item in body_slots if _text(item))


def _source_texts(source_refs: Any) -> tuple[str, ...]:
    if isinstance(source_refs, Mapping):
        texts: list[str] = []
        for key in _SOURCE_TEXT_KEYS:
            value = source_refs.get(key)
            texts.extend(_iter_text_values(value))
        return _dedupe(texts)
    if isinstance(source_refs, str):
        return (_text(source_refs),) if _text(source_refs) else ()
    if isinstance(source_refs, (list, tuple, set, frozenset)):
        texts: list[str] = []
        for item in source_refs:
            if isinstance(item, Mapping):
                texts.extend(_source_texts(item))
            else:
                text = _text(item)
                if text:
                    texts.append(text)
        return _dedupe(texts)
    return ()


def _mapping_value(mapping: Mapping[str, Any] | Any, key: str) -> str:
    if not isinstance(mapping, Mapping):
        return ""
    return _text(mapping.get(key))


def _expected_scoreline(draft: Mapping[str, Any] | Sequence[str] | str, source_refs: Any) -> str:
    expected = _mapping_value(draft, "scoreline")
    if expected:
        return expected
    expected = _mapping_value(source_refs, "scoreline")
    if expected:
        return expected
    for text in _source_texts(source_refs):
        match = RESULT_SCORE_RE.search(text)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    return ""


def _expected_team_result(draft: Mapping[str, Any] | Sequence[str] | str, source_refs: Any) -> str:
    expected = _mapping_value(draft, "team_result").lower()
    if expected:
        return expected
    expected = _mapping_value(source_refs, "team_result").lower()
    if expected:
        return expected
    for text in _source_texts(source_refs):
        if any(token in text for token in ("勝利", "白星", "競り勝った", "制した")):
            return "win"
        if any(token in text for token in ("敗戦", "黒星", "敗れた")):
            return "loss"
        if any(token in text for token in ("引き分け", "引分け", "ドロー")):
            return "draw"
    return ""


def _has_game_context(draft: Mapping[str, Any] | Sequence[str] | str, source_refs: Any) -> bool:
    if any(_mapping_value(draft, key) for key in ("game_id", "scoreline", "team_result")):
        return True
    if any(_mapping_value(source_refs, key) for key in ("game_id", "scoreline", "team_result")):
        return True
    return False


def _contains_result_conflict(text: str, scoreline: str) -> bool:
    expected = _text(scoreline)
    if not expected:
        return False
    expected_normalized = re.sub(r"\s+", "", expected).replace("–", "-").replace("－", "-")
    for match in RESULT_SCORE_RE.finditer(text):
        candidate = f"{match.group(1)}-{match.group(2)}"
        if candidate != expected_normalized:
            return True
    return False


def _team_result_conflict(text: str, team_result: str) -> bool:
    expected = _text(team_result).lower()
    if not expected:
        return False
    if expected in {"win", "勝利"}:
        return any(token in text for token in ("敗戦", "黒星", "敗れた"))
    if expected in {"loss", "敗戦"}:
        return any(token in text for token in ("勝利", "白星", "競り勝った", "制した"))
    if expected in {"draw", "引き分け", "引分け"}:
        return any(token in text for token in ("勝利", "敗戦", "白星", "黒星"))
    return False


def _quoted_tokens(title: str, body_slots: Mapping[str, Any] | Sequence[str] | str) -> tuple[str, ...]:
    tokens = [item.strip() for item in QUOTE_RE.findall(title) if item.strip()]
    if isinstance(body_slots, Mapping):
        quote_core = _text(body_slots.get("quote_core"))
        if quote_core:
            quoted = [item.strip() for item in QUOTE_RE.findall(quote_core) if item.strip()]
            if quoted:
                tokens.extend(quoted)
            else:
                tokens.append(quote_core.strip("「」『』 "))
    return _dedupe(tokens)


def _entity_tokens(body_slots: Mapping[str, Any] | Sequence[str] | str) -> tuple[str, ...]:
    if not isinstance(body_slots, Mapping):
        return ()

    tokens: list[str] = []
    for key in _ENTITY_TOKEN_KEYS:
        value = _text(body_slots.get(key))
        if value:
            tokens.append(value)

    for key in _TOKEN_SEQUENCE_KEYS:
        value = body_slots.get(key)
        if isinstance(value, str):
            token = _text(value)
            if token:
                tokens.append(token)
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                token = _text(item)
                if token:
                    tokens.append(token)

    return _dedupe(tokens)


def detect_no_game_but_result(draft: Mapping[str, Any] | Sequence[str] | str, source_refs: Any) -> bool:
    body_text = _body_text(draft)
    if not body_text:
        return False
    return not _has_game_context(draft, source_refs) and bool(RESULT_ASSERTION_RE.search(body_text))


def detect_game_result_conflict(draft: Mapping[str, Any] | Sequence[str] | str, source_refs: Any) -> bool:
    body_text = _body_text(draft)
    if not body_text:
        return False

    return _contains_result_conflict(body_text, _expected_scoreline(draft, source_refs)) or _team_result_conflict(
        body_text,
        _expected_team_result(draft, source_refs),
    )


def detect_title_body_entity_mismatch(title: str, body_slots: Mapping[str, Any] | Sequence[str] | str) -> bool:
    title_text = _text(title)
    body_text = _body_text(body_slots)
    if not title_text or not body_text:
        return False

    for token in _quoted_tokens(title_text, body_slots):
        if token and token not in body_text:
            return True

    for token in _entity_tokens(body_slots):
        if token and token in title_text and token not in body_text:
            return True

    return False


__all__ = [
    "GAME_RESULT_CONTEXT_SUBTYPES",
    "TITLE_BODY_MISMATCH_SUBTYPES",
    "detect_game_result_conflict",
    "detect_no_game_but_result",
    "detect_title_body_entity_mismatch",
]
