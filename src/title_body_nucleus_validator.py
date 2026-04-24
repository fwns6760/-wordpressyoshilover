"""Rule-based title/body nucleus alignment validator for ticket 071."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


_HTML_BREAK_RE = re.compile(r"(?i)<\s*(?:br|/p|/div|/li|/h[1-6])\s*/?\s*>")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t\u3000]+")
_LINE_SPLIT_RE = re.compile(r"[\r\n]+")
_SEGMENT_SPLIT_RE = re.compile(r"[。！？]\s*")
_TRAILING_PUNCTUATION_RE = re.compile(r"[。、，,・：:]+$")
_LEADING_DECORATION_RE = re.compile(r"^[\s【】\[\]（）()「」『』]+")

_TEAM_ALIASES = ("読売ジャイアンツ", "ジャイアンツ", "巨人")
_FARM_MARKERS = ("二軍", "2軍", "２軍", "ファーム")
_FIRST_TEAM_MARKERS = ("一軍", "1軍", "１軍")
_POSTGAME_RESULT_MARKERS = ("勝利", "白星", "敗戦", "黒星", "引き分け", "試合結果")
_LINEUP_MARKERS = ("先発オーダー", "スタメン", "オーダー", "先発投手", "予告先発", "4番", "1番")
_SUBJECT_STOPWORDS = {
    "試合結果",
    "試合後",
    "試合前",
    "先発情報",
    "先発投手",
    "先発オーダー",
    "スタメン",
    "出場選手",
    "継投策",
    "起用法",
    "二軍結果",
    "一軍結果",
    "試合概要",
    "勝利",
    "敗戦",
    "守備",
    "登録",
    "抹消",
    "昇格",
    "降格",
}

_KNOWN_SUBJECT_PARTICLE_TEMPLATE = r"{subject}(?:は|が|も)"
_TEAM_SUBJECT_RE = re.compile(r"(読売ジャイアンツ|ジャイアンツ|巨人)")
_PUBLIC_NUMBER_RE = re.compile(r"((?:公示番号|背番号|#)\s*[0-9０-９]+)")
_MANAGER_SUBJECT_RE = re.compile(r"([一-龯々ヶ]{1,6}監督)")
_KANJI_NAME_RE = re.compile(r"([一-龯々ヶ]{3,6})(?:投手|捕手|内野手|外野手|選手)?")
_KATAKANA_NAME_RE = re.compile(r"([ァ-ヴー]{2,}(?:[=＝・･][ァ-ヴー]{2,})*)")

_TEAM_INDEPENDENT_RE = re.compile(r"((?:読売ジャイアンツ|ジャイアンツ|巨人))(?:は|が|も)")
_PUBLIC_INDEPENDENT_RE = re.compile(r"((?:公示番号|背番号|#)\s*[0-9０-９]+)(?:は|が|も)")
_MANAGER_INDEPENDENT_RE = re.compile(r"([一-龯々ヶ]{1,6}監督)(?:は|が|も)")
_KANJI_INDEPENDENT_RE = re.compile(r"([一-龯々ヶ]{3,6})(?:投手|捕手|内野手|外野手|選手)?(?:は|が|も)")
_KATAKANA_INDEPENDENT_RE = re.compile(r"([ァ-ヴー]{2,}(?:[=＝・･][ァ-ヴー]{2,})*)(?:は|が|も)")

_EVENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("roster_up", re.compile(r"(?:出場選手)?登録|昇格|一軍合流")),
    ("roster_down", re.compile(r"抹消|降格")),
    ("lineup_role", re.compile(r"[0-9０-９]+番起用|[0-9０-９]+番|スタメン|先発オーダー|オーダー")),
    ("starting_pitcher", re.compile(r"予告先発|先発投手|先発")),
    ("manager_strategy", re.compile(r"継投策?|采配|起用|判断|方針")),
    ("manager_comment", re.compile(r"発言|コメント|言及|説明")),
    ("home_run", re.compile(r"(?:第)?[0-9０-９]+号")),
    ("hits", re.compile(r"[0-9０-９]+安打")),
    ("rbis", re.compile(r"[0-9０-９]+打点")),
    ("game_result", re.compile(r"試合結果|勝利|白星|敗戦|黒星|引き分け|[0-9０-９]+\s*[-－ー]\s*[0-9０-９]+")),
    ("appearance", re.compile(r"登板|先発出場|出場|出番")),
    ("defense", re.compile(r"守備|好守|失策")),
    ("training", re.compile(r"(?:二軍|2軍|２軍|一軍|1軍|１軍)?練習|調整")),
)
_FALLBACK_EVENT_RE = re.compile(
    r"([^\s。]{1,16}(?:した|する|したか|見せた|語った|振り返った|放った|決めた|担った|続けた|説明した))"
)


@dataclass(frozen=True)
class NucleusAlignmentResult:
    aligned: bool
    title_subject: str | None
    title_event: str | None
    body_subject: str | None
    body_event: str | None
    reason_code: str | None
    detail: str | None


def _normalize_text(text: str) -> str:
    normalized = _HTML_BREAK_RE.sub("\n", text or "")
    normalized = _HTML_TAG_RE.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    return normalized.strip()


def _normalize_subject(subject: str | None) -> str:
    if not subject:
        return ""
    normalized = _normalize_text(subject)
    for suffix in ("投手", "捕手", "内野手", "外野手", "選手"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized.strip()


def _clean_subject_candidate(candidate: str) -> str:
    cleaned = _normalize_subject(candidate)
    cleaned = _LEADING_DECORATION_RE.sub("", cleaned)
    cleaned = _TRAILING_PUNCTUATION_RE.sub("", cleaned)
    return cleaned.strip()


def _is_team_subject(subject: str | None) -> bool:
    normalized = _normalize_subject(subject)
    return any(alias in normalized for alias in _TEAM_ALIASES)


def _subject_variants_equivalent(left: str | None, right: str | None) -> bool:
    left_normalized = _normalize_subject(left)
    right_normalized = _normalize_subject(right)
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if _is_team_subject(left_normalized) and _is_team_subject(right_normalized):
        return True
    if len(left_normalized) >= 3 and len(right_normalized) >= 3:
        if left_normalized in right_normalized or right_normalized in left_normalized:
            return True

    left_base = left_normalized.replace("監督", "")
    right_base = right_normalized.replace("監督", "")
    if left_base and right_base:
        if left_base == right_base:
            return True
        if len(left_base) >= 2 and len(right_base) >= 2:
            return left_base.startswith(right_base) or right_base.startswith(left_base)
    return False


def _candidate_allowed(candidate: str) -> bool:
    token = _clean_subject_candidate(candidate)
    if not token:
        return False
    if token in _SUBJECT_STOPWORDS:
        return False
    if _is_team_subject(token):
        return True
    if _PUBLIC_NUMBER_RE.fullmatch(token):
        return True
    if "監督" in token:
        return True
    stripped = token.replace(" ", "")
    return len(stripped) >= 2


def _append_unique_subject(
    seen: list[tuple[int, str]],
    start: int,
    subject: str,
) -> None:
    cleaned = _clean_subject_candidate(subject)
    if not _candidate_allowed(cleaned):
        return
    for _, existing in seen:
        if _subject_variants_equivalent(existing, cleaned):
            return
    seen.append((start, cleaned))


def _find_subject_candidates(text: str, known_subjects: Sequence[str] | None = None) -> list[str]:
    normalized = _normalize_text(text)
    matches: list[tuple[int, str]] = []
    if normalized:
        for subject in sorted({item for item in (known_subjects or ()) if item}, key=len, reverse=True):
            lookup = _normalize_text(subject)
            start = normalized.find(lookup)
            if start >= 0:
                _append_unique_subject(matches, start, lookup)

        for pattern in (
            _PUBLIC_NUMBER_RE,
            _TEAM_SUBJECT_RE,
            _MANAGER_SUBJECT_RE,
            _KANJI_NAME_RE,
            _KATAKANA_NAME_RE,
        ):
            for match in pattern.finditer(normalized):
                _append_unique_subject(matches, match.start(1), match.group(1))

    matches.sort(key=lambda item: (item[0], -len(item[1])))
    return [subject for _, subject in matches]


def _find_independent_subjects(text: str, known_subjects: Sequence[str] | None = None) -> list[str]:
    normalized = _normalize_text(text)
    matches: list[tuple[int, str]] = []
    if normalized:
        for subject in sorted({item for item in (known_subjects or ()) if item}, key=len, reverse=True):
            lookup = _normalize_text(subject)
            pattern = re.compile(_KNOWN_SUBJECT_PARTICLE_TEMPLATE.format(subject=re.escape(lookup)))
            match = pattern.search(normalized)
            if match:
                _append_unique_subject(matches, match.start(), lookup)

        for pattern in (
            _PUBLIC_INDEPENDENT_RE,
            _TEAM_INDEPENDENT_RE,
            _MANAGER_INDEPENDENT_RE,
            _KANJI_INDEPENDENT_RE,
            _KATAKANA_INDEPENDENT_RE,
        ):
            for match in pattern.finditer(normalized):
                _append_unique_subject(matches, match.start(1), match.group(1))

    matches.sort(key=lambda item: (item[0], -len(item[1])))
    return [subject for _, subject in matches]


def _extract_subject(text: str, known_subjects: Sequence[str] | None = None) -> str | None:
    candidates = _find_subject_candidates(text, known_subjects)
    return candidates[0] if candidates else None


def _extract_body_subject(
    opening_text: str,
    subtype: str,
    known_subjects: Sequence[str] | None = None,
) -> str | None:
    independent = _find_independent_subjects(opening_text, known_subjects)
    if subtype == "manager":
        for subject in independent:
            if "監督" in subject:
                return subject
    if independent:
        return independent[0]
    return _extract_subject(opening_text, known_subjects)


def _extract_event_match(text: str) -> tuple[str | None, str | None]:
    normalized = _normalize_text(text)
    for category, pattern in _EVENT_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return match.group(0).strip(), category
    fallback_matches = list(_FALLBACK_EVENT_RE.finditer(normalized))
    if fallback_matches:
        return fallback_matches[-1].group(1).strip(), "verb_phrase"
    return None, None


def _body_opening_lines(body: str) -> list[str]:
    normalized = _normalize_text(body)
    if not normalized:
        return []
    raw_lines = [line.strip() for line in _LINE_SPLIT_RE.split(normalized)]
    lines = [line for line in raw_lines if line]
    if not lines:
        return []
    return lines[:4]


def _opening_text(body: str) -> str:
    return "\n".join(_body_opening_lines(body))


def _split_segments(text: str) -> list[str]:
    segments: list[str] = []
    for line in _body_opening_lines(text):
        for segment in _SEGMENT_SPLIT_RE.split(line):
            cleaned = segment.strip()
            if cleaned:
                segments.append(cleaned)
    return segments


def _collect_opening_nuclei(
    opening_text: str,
    subtype: str,
    known_subjects: Sequence[str] | None = None,
) -> list[tuple[str, str, str]]:
    nuclei: list[tuple[str, str, str]] = []
    for segment in _split_segments(opening_text):
        subjects = _find_independent_subjects(segment, known_subjects)
        if subtype == "manager":
            manager_subjects = [subject for subject in subjects if "監督" in subject]
            if manager_subjects:
                subjects = manager_subjects
        event_text, event_category = _extract_event_match(segment)
        if not event_text or not event_category:
            continue
        for subject in subjects:
            already_seen = any(
                _subject_variants_equivalent(existing_subject, subject) and existing_category == event_category
                for existing_subject, _, existing_category in nuclei
            )
            if not already_seen:
                nuclei.append((subject, event_text, event_category))
    return nuclei


def _has_subject_in_opening(title_subject: str | None, opening_text: str, known_subjects: Sequence[str] | None = None) -> bool:
    if not title_subject:
        return False
    for subject in _find_subject_candidates(opening_text, known_subjects):
        if _subject_variants_equivalent(title_subject, subject):
            return True
    normalized_opening = _normalize_text(opening_text)
    normalized_title_subject = _normalize_text(title_subject)
    return normalized_title_subject in normalized_opening


def _has_postgame_support(text: str) -> bool:
    normalized = _normalize_text(text)
    if any(marker in normalized for marker in _POSTGAME_RESULT_MARKERS):
        return True
    return bool(re.search(r"[0-9０-９]+\s*[-－ー]\s*[0-9０-９]+", normalized))


def _has_lineup_support(text: str) -> bool:
    normalized = _normalize_text(text)
    return any(marker in normalized for marker in _LINEUP_MARKERS)


def _opening_has_multiple_nuclei(
    opening_text: str,
    subtype: str,
    known_subjects: Sequence[str] | None = None,
) -> tuple[bool, str | None]:
    nuclei = _collect_opening_nuclei(opening_text, subtype, known_subjects)
    unique_subjects: list[str] = []
    for subject, _, _ in nuclei:
        if not any(_subject_variants_equivalent(existing, subject) for existing in unique_subjects):
            unique_subjects.append(subject)
    if len(unique_subjects) >= 2:
        return True, ", ".join(unique_subjects)
    return False, None


def validate_title_body_nucleus(
    title: str,
    body: str,
    subtype: str,
    *,
    known_subjects: list[str] | None = None,
) -> NucleusAlignmentResult:
    normalized_title = _normalize_text(title)
    opening_text = _opening_text(body)

    title_subject = _extract_subject(normalized_title, known_subjects)
    title_event, title_event_category = _extract_event_match(normalized_title)
    body_subject = _extract_body_subject(opening_text, subtype, known_subjects)
    body_event, body_event_category = _extract_event_match(opening_text)

    has_multiple, multiple_detail = _opening_has_multiple_nuclei(opening_text, subtype, known_subjects)
    if has_multiple:
        return NucleusAlignmentResult(
            aligned=False,
            title_subject=title_subject,
            title_event=title_event,
            body_subject=body_subject,
            body_event=body_event,
            reason_code="MULTIPLE_NUCLEI",
            detail=f"opening subjects={multiple_detail}",
        )

    if title_subject and not _has_subject_in_opening(title_subject, opening_text, known_subjects):
        return NucleusAlignmentResult(
            aligned=False,
            title_subject=title_subject,
            title_event=title_event,
            body_subject=body_subject,
            body_event=body_event,
            reason_code="SUBJECT_ABSENT",
            detail="title subject missing from body opening",
        )

    same_subject = _subject_variants_equivalent(title_subject, body_subject) if title_subject and body_subject else False
    if same_subject and title_event_category and body_event_category and title_event_category != body_event_category:
        return NucleusAlignmentResult(
            aligned=False,
            title_subject=title_subject,
            title_event=title_event,
            body_subject=body_subject,
            body_event=body_event,
            reason_code="EVENT_DIVERGE",
            detail=f"title={title_event_category} body={body_event_category}",
        )

    if subtype == "postgame" and (title_event_category == "game_result" or _is_team_subject(title_subject)):
        if not _has_postgame_support(opening_text):
            return NucleusAlignmentResult(
                aligned=False,
                title_subject=title_subject,
                title_event=title_event,
                body_subject=body_subject,
                body_event=body_event,
                reason_code="EVENT_DIVERGE",
                detail="postgame opening lacks result signal",
            )

    if subtype in {"lineup", "pregame"} and title_event_category in {"starting_pitcher", "lineup_role"}:
        if not _has_lineup_support(opening_text):
            return NucleusAlignmentResult(
                aligned=False,
                title_subject=title_subject,
                title_event=title_event,
                body_subject=body_subject,
                body_event=body_event,
                reason_code="EVENT_DIVERGE",
                detail="lineup or pregame opening lacks lineup signal",
            )

    if subtype == "farm":
        normalized_opening = _normalize_text(opening_text)
        if any(marker in normalized_opening for marker in _FIRST_TEAM_MARKERS) and not any(
            marker in normalized_opening for marker in _FARM_MARKERS
        ):
            return NucleusAlignmentResult(
                aligned=False,
                title_subject=title_subject,
                title_event=title_event,
                body_subject=body_subject,
                body_event=body_event,
                reason_code="EVENT_DIVERGE",
                detail="farm opening mixes first-team context",
            )

    return NucleusAlignmentResult(
        aligned=True,
        title_subject=title_subject,
        title_event=title_event,
        body_subject=body_subject,
        body_event=body_event,
        reason_code=None,
        detail=None,
    )


__all__ = ["NucleusAlignmentResult", "validate_title_body_nucleus"]
