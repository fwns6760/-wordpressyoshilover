"""Rule-first validator for comment-lane drafts (ticket 067)."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


HARD_FAIL_TAGS = (
    "GAME_RESULT_CONFLICT",
    "NO_GAME_BUT_RESULT",
    "SPEAKER_MISSING",
    "QUOTE_UNGROUNDED",
    "TITLE_BODY_ENTITY_MISMATCH",
    "SOURCE_TRUST_TOO_LOW",
)
SOFT_FAIL_TAGS = (
    "TITLE_GENERIC",
    "TITLE_MISSING_SCENE",
    "TITLE_MISSING_NUCLEUS",
    "LEDE_TOO_VAGUE",
    "TOO_MANY_HEADINGS",
    "PRONOUN_AMBIGUOUS",
    "BODY_ORDER_BROKEN",
)

# 067 raw tags must normalize back to the existing 038/040 ledger fail-tag schema.
FAIL_TAG_NORMALIZATION = {
    "GAME_RESULT_CONFLICT": "fact_missing",
    "NO_GAME_BUT_RESULT": "fact_missing",
    "SPEAKER_MISSING": "low_assertability",
    "QUOTE_UNGROUNDED": "attribution_missing",
    "TITLE_BODY_ENTITY_MISMATCH": "title_body_mismatch",
    "SOURCE_TRUST_TOO_LOW": "low_assertability",
    "TITLE_GENERIC": "title_body_mismatch",
    "TITLE_MISSING_SCENE": "title_body_mismatch",
    "TITLE_MISSING_NUCLEUS": "title_body_mismatch",
    "LEDE_TOO_VAGUE": "abstract_lead",
    "TOO_MANY_HEADINGS": "subtype_boundary",
    "PRONOUN_AMBIGUOUS": "low_assertability",
    "BODY_ORDER_BROKEN": "subtype_boundary",
}

EXPECTED_SLOT_ORDER = ("fact_header", "lede", "quote_block", "context", "related")
RESULT_SCORE_RE = re.compile(r"(\d{1,2})\s*[－\-–]\s*(\d{1,2})")
RESULT_ASSERTION_RE = re.compile(
    r"(勝利|敗戦|引き分け|白星|黒星|競り勝った|敗れた|制した|\d{1,2}\s*[－\-–]\s*\d{1,2})"
)
HEADING_RE = re.compile(r"^\s*(?:##+|###|【[^】]+】|<h[23][^>]*>)", re.MULTILINE)
PRONOUN_RE = re.compile(r"(彼|彼女|この人|この一言|その発言|それ|これ)")
TITLE_GENERIC_PATTERNS = (
    re.compile(r"どう見る"),
    re.compile(r"本音"),
    re.compile(r"思い"),
    re.compile(r"語る"),
    re.compile(r"コメントまとめ"),
    re.compile(r"試合後コメント"),
    re.compile(r"ドラ1コンビ"),
    re.compile(r"Xをどう見る"),
    re.compile(r"Xがコメント"),
    re.compile(r"Xについて語る"),
    re.compile(r"注目したい"),
    re.compile(r"振り返りたい"),
    re.compile(r"コメントに注目"),
    re.compile(r"コメントから見えるもの"),
    re.compile(r"選手コメントを読む"),
    re.compile(r"コメントに迫る"),
)
QUOTE_RE = re.compile(r"[「『](.+?)[」』]")
ABSTRACT_LEDE_PREFIXES = (
    "このコメントは",
    "注目を集めた",
    "印象的だった",
    "気になるのは",
    "話題となった",
)


@dataclass(frozen=True)
class CommentValidationResult:
    ok: bool
    hard_fail_tags: tuple[str, ...]
    soft_fail_tags: tuple[str, ...]
    raw_fail_tags: tuple[str, ...]
    normalized_fail_tags: tuple[str, ...]
    stop_lane: str


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def normalize_fail_tags(tags: Sequence[str]) -> tuple[str, ...]:
    return _dedupe(FAIL_TAG_NORMALIZATION[tag] for tag in tags if tag in FAIL_TAG_NORMALIZATION)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _combined_body(draft: Mapping[str, Any]) -> str:
    return "\n".join(
        _text(draft.get(key))
        for key in ("fact_header", "lede", "quote_block", "context", "related")
        if _text(draft.get(key))
    )


def _title_mentions_speaker(title: str, draft: Mapping[str, Any]) -> bool:
    speaker = _text(draft.get("speaker_name") or draft.get("speaker"))
    if not speaker:
        return True
    return speaker in title


def _has_generic_title(title: str) -> bool:
    if not title.strip():
        return True
    quoted = QUOTE_RE.findall(title)
    if len([item for item in quoted if item.strip()]) > 1:
        return True
    return any(pattern.search(title) for pattern in TITLE_GENERIC_PATTERNS)


def _scene_tokens(draft: Mapping[str, Any]) -> tuple[str, ...]:
    tokens = []
    for key in ("scene_type", "game_context", "target_entity", "subject_entity", "opponent"):
        value = _text(draft.get(key))
        if value:
            tokens.append(value)
    return _dedupe(tokens)


def _title_has_scene(title: str, draft: Mapping[str, Any]) -> bool:
    tokens = _scene_tokens(draft)
    if not tokens:
        return True
    return any(token in title for token in tokens)


def _nucleus_text(draft: Mapping[str, Any]) -> str:
    nucleus = _text(draft.get("quote_core"))
    if not nucleus:
        return ""
    quoted = QUOTE_RE.findall(nucleus)
    if quoted:
        nucleus = quoted[0]
    return nucleus.strip("「」『』 ")


def _title_has_nucleus(title: str, draft: Mapping[str, Any]) -> bool:
    nucleus = _nucleus_text(draft)
    if not nucleus:
        return True
    return nucleus in title


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


def _quote_is_grounded(draft: Mapping[str, Any]) -> bool:
    source_ref = _text(draft.get("source_ref") or draft.get("quote_source"))
    if not source_ref or source_ref.lower().startswith("http"):
        return False
    near_top = "\n".join(_text(draft.get(key)) for key in ("fact_header", "lede"))
    return source_ref in near_top or source_ref in _text(draft.get("quote_block"))


def _is_low_trust_source(draft: Mapping[str, Any]) -> bool:
    values = (
        _text(draft.get("source_tier")).lower(),
        _text(draft.get("trust_tier")).lower(),
        _text(draft.get("quote_source_type")).lower(),
        _text(draft.get("source_ref") or draft.get("quote_source")).lower(),
    )
    return any(
        token in value
        for value in values
        for token in ("reaction", "t3", "一般ファン", "fan", "quote / repost")
        if value
    )


def _title_body_mismatch(title: str, draft: Mapping[str, Any], body_text: str) -> bool:
    speaker = _text(draft.get("speaker_name") or draft.get("speaker"))
    if speaker and speaker in title and speaker not in body_text:
        return True

    quoted = [item.strip() for item in QUOTE_RE.findall(title) if item.strip()]
    if quoted and not all(item in body_text for item in quoted):
        return True

    for token in _scene_tokens(draft):
        if token in title and token not in body_text:
            return True
    return False


def _lede_is_too_vague(draft: Mapping[str, Any]) -> bool:
    lede = _text(draft.get("lede"))
    if not lede:
        return True
    if any(lede.startswith(prefix) for prefix in ABSTRACT_LEDE_PREFIXES):
        return True
    if lede.startswith(("「", "『")):
        return True

    speaker = _text(draft.get("speaker_name") or draft.get("speaker"))
    if speaker and speaker not in lede:
        return True
    if not _title_has_scene(lede, draft):
        return True
    if not _title_has_nucleus(lede, draft):
        return True

    downstream = _text(draft.get("downstream_link"))
    if downstream and downstream not in lede:
        return True
    return False


def _has_too_many_headings(draft: Mapping[str, Any]) -> bool:
    text = _combined_body(draft)
    return bool(HEADING_RE.search(text))


def _has_ambiguous_pronoun(draft: Mapping[str, Any]) -> bool:
    speaker = _text(draft.get("speaker_name") or draft.get("speaker"))
    body = _combined_body(draft)
    if not PRONOUN_RE.search(body):
        return False
    sentences = re.split(r"[。!?！？]\s*", body)
    for sentence in sentences:
        if PRONOUN_RE.search(sentence) and speaker and speaker not in sentence:
            return True
    return False


def _is_body_order_broken(draft: Mapping[str, Any]) -> bool:
    actual_order = draft.get("body_order")
    if actual_order is None:
        return False
    actual = tuple(str(item or "").strip() for item in actual_order if str(item or "").strip())
    return actual != EXPECTED_SLOT_ORDER


def validate_comment_lane_draft(draft: Mapping[str, Any]) -> CommentValidationResult:
    title = _text(draft.get("title"))
    body_text = _combined_body(draft)
    speaker = _text(draft.get("speaker_name") or draft.get("speaker"))
    hard_fail_tags: list[str] = []
    soft_fail_tags: list[str] = []

    if _is_low_trust_source(draft):
        hard_fail_tags.append("SOURCE_TRUST_TOO_LOW")
    if not speaker:
        hard_fail_tags.append("SPEAKER_MISSING")
    if not _quote_is_grounded(draft):
        hard_fail_tags.append("QUOTE_UNGROUNDED")

    has_game_context = any(_text(draft.get(key)) for key in ("game_id", "scoreline", "team_result"))
    if not has_game_context and RESULT_ASSERTION_RE.search(body_text):
        hard_fail_tags.append("NO_GAME_BUT_RESULT")

    if _contains_result_conflict(body_text, _text(draft.get("scoreline"))) or _team_result_conflict(
        body_text,
        _text(draft.get("team_result")),
    ):
        hard_fail_tags.append("GAME_RESULT_CONFLICT")

    if _title_body_mismatch(title, draft, body_text):
        hard_fail_tags.append("TITLE_BODY_ENTITY_MISMATCH")

    if _has_generic_title(title) or not _title_mentions_speaker(title, draft):
        soft_fail_tags.append("TITLE_GENERIC")
    if not _title_has_scene(title, draft):
        soft_fail_tags.append("TITLE_MISSING_SCENE")
    if not _title_has_nucleus(title, draft):
        soft_fail_tags.append("TITLE_MISSING_NUCLEUS")
    if _lede_is_too_vague(draft):
        soft_fail_tags.append("LEDE_TOO_VAGUE")
    if _has_too_many_headings(draft):
        soft_fail_tags.append("TOO_MANY_HEADINGS")
    if _has_ambiguous_pronoun(draft):
        soft_fail_tags.append("PRONOUN_AMBIGUOUS")
    if _is_body_order_broken(draft):
        soft_fail_tags.append("BODY_ORDER_BROKEN")

    raw_fail_tags = _dedupe((*hard_fail_tags, *soft_fail_tags))
    normalized_fail_tags = normalize_fail_tags(raw_fail_tags)
    return CommentValidationResult(
        ok=not raw_fail_tags,
        hard_fail_tags=_dedupe(hard_fail_tags),
        soft_fail_tags=_dedupe(soft_fail_tags),
        raw_fail_tags=raw_fail_tags,
        normalized_fail_tags=normalized_fail_tags,
        stop_lane="agent" if hard_fail_tags else "fixed",
    )


__all__ = [
    "EXPECTED_SLOT_ORDER",
    "FAIL_TAG_NORMALIZATION",
    "HARD_FAIL_TAGS",
    "SOFT_FAIL_TAGS",
    "CommentValidationResult",
    "normalize_fail_tags",
    "validate_comment_lane_draft",
]
