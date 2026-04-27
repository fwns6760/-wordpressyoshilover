from __future__ import annotations

import re
from typing import Any


ROLE_KEYWORDS = tuple(
    sorted(
        (
            "球団社長",
            "球団代表",
            "内野手",
            "外野手",
            "投手",
            "捕手",
            "選手",
            "監督",
            "コーチ",
            "右腕",
            "左腕",
            "主将",
            "GM",
        ),
        key=len,
        reverse=True,
    )
)
ROLE_PATTERN = "|".join(re.escape(role) for role in ROLE_KEYWORDS)
NAME_CHAR_CLASS = r"一-龥々ァ-ヴーA-Za-z0-9"
NAME_TOKEN_RE = re.compile(fr"[{NAME_CHAR_CLASS}]{{2,10}}")
AWKWARD_ROLE_PATTERN = re.compile(
    fr"(?P<name>[{NAME_CHAR_CLASS}]{{2,10}}?)(?P<role>{ROLE_PATTERN})(?P<connector>となって|となり|となった|となる)"
)
CONNECTOR_REWRITE_MAP = {
    "となって": "が",
    "となり": "が",
    "となった": "は",
    "となる": "は",
}
GENERIC_NAME_EXCLUSIONS = frozenset(
    {
        "一軍",
        "二軍",
        "主力",
        "先発",
        "救援",
        "新人",
        "助っ人",
        "首脳",
        "打線",
        "球団",
        "本紙",
        "チーム",
        "ベンチ",
        "捕手陣",
        "投手陣",
        "内野陣",
        "外野陣",
    }
)
SENTENCE_BREAKS = ("。", "！", "？", "!", "?", "\n")
PREDICATE_CONTENT_RE = re.compile(r"[一-龥々ぁ-んァ-ヴーA-Za-z0-9]")
URL_HEAD_RE = re.compile(r"^https?://", re.IGNORECASE)
PUNCTUATION_ONLY_RE = re.compile(r"^[\s、,，;；:：\-\-‐‑‒–—―…」』）)\]】]+$")


def _is_probable_entity_name(name: str) -> bool:
    candidate = str(name or "").strip()
    if not NAME_TOKEN_RE.fullmatch(candidate):
        return False
    if candidate in GENERIC_NAME_EXCLUSIONS:
        return False
    return True


def _build_match_detail(match: re.Match[str]) -> dict[str, Any]:
    return {
        "match": match.group(0),
        "name": match.group("name"),
        "role": match.group("role"),
        "connector": match.group("connector"),
        "position": match.start(),
    }


def _sentence_tail(body_text: str, match_end: int) -> str:
    sentence_end = len(body_text)
    for token in SENTENCE_BREAKS:
        position = body_text.find(token, match_end)
        if position != -1:
            sentence_end = min(sentence_end, position)
    return body_text[match_end:sentence_end]


def _rewrite_skip_reason(sentence_tail: str) -> str | None:
    stripped = sentence_tail.lstrip()
    if not stripped:
        return "sentence_end"
    if URL_HEAD_RE.match(stripped):
        return "url_only_tail"
    if PUNCTUATION_ONLY_RE.fullmatch(stripped):
        return "punctuation_only_tail"
    if not PREDICATE_CONTENT_RE.search(stripped):
        return "no_predicate_context"
    return None


def detect_awkward_role_phrasing(body_text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for match in AWKWARD_ROLE_PATTERN.finditer(body_text or ""):
        if not _is_probable_entity_name(match.group("name")):
            continue
        matches.append(_build_match_detail(match))
    return matches


def safe_rewrite_role_phrasing(body_text: str) -> tuple[str, int, list[dict[str, Any]]]:
    text = body_text or ""
    rewritten: list[str] = []
    rewrite_count = 0
    skipped: list[dict[str, Any]] = []
    cursor = 0

    for match in AWKWARD_ROLE_PATTERN.finditer(text):
        if not _is_probable_entity_name(match.group("name")):
            continue

        rewritten.append(text[cursor:match.start()])
        detail = _build_match_detail(match)
        skip_reason = _rewrite_skip_reason(_sentence_tail(text, match.end()))

        if skip_reason is None:
            connector = str(detail["connector"])
            rewritten.append(f"{detail['name']}{detail['role']}{CONNECTOR_REWRITE_MAP[connector]}")
            rewrite_count += 1
        else:
            rewritten.append(text[match.start():match.end()])
            skipped.append({**detail, "reason": skip_reason})

        cursor = match.end()

    rewritten.append(text[cursor:])
    return "".join(rewritten), rewrite_count, skipped
