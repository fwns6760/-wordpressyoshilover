"""Title player-name backfill helpers for ticket 277-QA."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from src.title_validator import title_has_person_name_candidate


_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LINEUP_PREFIX_RE = re.compile(r"^\s*巨人スタメン\s*")
_LEADING_PARTICLE_RE = re.compile(r"^[がをにのへともや]")
_GENERIC_HEAD_RE = re.compile(r"^(選手|投手|コーチ|監督|チーム)(?P<rest>(?:[、，,]\s*.*|\s+.*|$))")
_QUOTE_RE = re.compile(r"[「『]([^」』]{1,40})[」』]")
_NAME_WITH_ROLE_RE = re.compile(
    r"(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24}?)(?P<role>投手|捕手|内野手|外野手|選手|監督|コーチ)"
)
_NAME_RE = re.compile(
    r"(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24})(?=(?:が|は|も|の|と|、|，|,|「|『|[0-9０-９]|$))"
)
_GENERIC_LABELS = frozenset({"選手", "投手", "コーチ", "監督", "チーム"})
_STOPWORDS = frozenset(
    {
        "巨人",
        "ジャイアンツ",
        "読売",
        "チーム",
        "球団",
        "ベンチ",
        "首脳陣",
        "選手",
        "投手",
        "監督",
        "コーチ",
        "スタメン",
        "今季",
        "一軍",
        "二軍",
        "試合",
        "先発",
        "登板",
        "登録",
        "抹消",
        "復帰",
        "昇格",
        "合流",
        "関連情報",
        "コメント整理",
        "発言ポイント",
    }
)
_ROLE_NORMALIZATION = {
    "投手": "投手",
    "捕手": "選手",
    "内野手": "選手",
    "外野手": "選手",
    "選手": "選手",
    "監督": "監督",
    "コーチ": "コーチ",
}
_COMMENT_TITLE_MARKERS = ("コメント整理", "発言ポイント", "談話整理", "コメント")
_STOPWORD_FRAGMENTS = (
    "今季",
    "初先発",
    "試合後",
    "関連情報",
    "コメント",
    "整理",
    "発言",
    "ポイント",
    "スタメン",
    "先発",
    "登板",
    "登録",
    "抹消",
    "復帰",
    "昇格",
    "合流",
    "球団",
    "打線",
)


@dataclass(frozen=True)
class TitlePlayerNameBackfillResult:
    title: str
    changed: bool
    review_reason: str = ""
    player_name: str = ""
    role: str = ""


def _clean_text(value: str) -> str:
    text = _HTML_RE.sub("", str(value or ""))
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _normalize_role(value: str) -> str:
    return _ROLE_NORMALIZATION.get(str(value or "").strip(), "")


def _split_name_role(value: str, role_hint: str = "") -> tuple[str, str]:
    cleaned = _clean_text(value)
    if not cleaned:
        return "", ""
    match = re.match(r"^(?P<name>.+?)(?P<role>投手|捕手|内野手|外野手|選手|監督|コーチ)$", cleaned)
    if match:
        return match.group("name").strip(), _normalize_role(match.group("role"))
    return cleaned, _normalize_role(role_hint)


def _is_valid_name(name: str) -> bool:
    candidate = _clean_text(name).strip("・･、, ")
    if not candidate:
        return False
    if candidate in _STOPWORDS:
        return False
    if candidate in _GENERIC_LABELS:
        return False
    if any(fragment in candidate for fragment in _STOPWORD_FRAGMENTS):
        return False
    if re.search(r"\d", candidate):
        return False
    if len(candidate) < 2:
        return False
    return True


def _title_already_has_named_subject(title: str) -> bool:
    cleaned = _clean_text(title)
    if not cleaned:
        return False
    if cleaned in _GENERIC_LABELS:
        return False
    if cleaned.startswith(tuple(_GENERIC_LABELS)) and any(marker in cleaned for marker in _COMMENT_TITLE_MARKERS):
        return False
    if _GENERIC_HEAD_RE.match(cleaned) and any(marker in cleaned for marker in _COMMENT_TITLE_MARKERS):
        return False
    if _LINEUP_PREFIX_RE.match(cleaned):
        stripped = _LINEUP_PREFIX_RE.sub("", cleaned, count=1).lstrip()
        if not stripped or _LEADING_PARTICLE_RE.match(stripped) or _GENERIC_HEAD_RE.match(stripped):
            return False
    return title_has_person_name_candidate(cleaned)


def _append_candidate(
    candidates: list[tuple[str, str]],
    seen: set[str],
    raw_name: str,
    *,
    role_hint: str = "",
) -> None:
    name, embedded_role = _split_name_role(raw_name, role_hint)
    name = name.strip("・･、, ")
    if not _is_valid_name(name):
        return
    key = re.sub(r"\s+", "", name)
    if key in seen:
        return
    seen.add(key)
    candidates.append((name, embedded_role or _normalize_role(role_hint)))


def _collect_candidates_from_text(text: str) -> list[tuple[str, str]]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for match in _NAME_WITH_ROLE_RE.finditer(cleaned):
        _append_candidate(candidates, seen, match.group("name"), role_hint=match.group("role"))
    for match in _NAME_RE.finditer(cleaned):
        _append_candidate(candidates, seen, match.group("name"))
    return candidates


def _infer_role(
    name: str,
    *,
    existing_title: str,
    source_title: str,
    body: str,
    summary: str,
    metadata: Mapping[str, object],
) -> str:
    metadata_role = _normalize_role(str(metadata.get("role") or ""))
    if metadata_role:
        return metadata_role

    context = " ".join(
        part for part in (
            _clean_text(existing_title),
            _clean_text(source_title),
            _clean_text(body),
            _clean_text(summary),
        )
        if part
    )
    explicit_patterns = (
        (f"{name}投手", "投手"),
        (f"{name}監督", "監督"),
        (f"{name}コーチ", "コーチ"),
        (f"{name}捕手", "選手"),
        (f"{name}内野手", "選手"),
        (f"{name}外野手", "選手"),
        (f"{name}選手", "選手"),
    )
    for marker, normalized_role in explicit_patterns:
        if marker in context:
            return normalized_role

    if "投手" in context:
        return "投手"
    if "監督" in context:
        return "監督"
    if "コーチ" in context:
        return "コーチ"
    if any(
        marker in context
        for marker in ("選手", "スタメン", "先発", "打順", "登録", "抹消", "復帰", "昇格", "合流", "打席", "二塁", "遊撃")
    ):
        return "選手"
    return "氏"


def _choose_candidate(
    *,
    existing_title: str,
    source_title: str,
    body: str,
    summary: str,
    metadata: Mapping[str, object],
) -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    metadata_role = _normalize_role(str(metadata.get("role") or ""))
    for key in ("speaker", "player_name", "subject_player"):
        _append_candidate(candidates, seen, str(metadata.get(key) or ""), role_hint=metadata_role)
    for text in (source_title, body, summary):
        for name, role in _collect_candidates_from_text(text):
            _append_candidate(candidates, seen, name, role_hint=role)
    if not candidates:
        return "", ""
    name, role = candidates[0]
    if not role:
        role = _infer_role(
            name,
            existing_title=existing_title,
            source_title=source_title,
            body=body,
            summary=summary,
            metadata=metadata,
        )
    return name, role


def _display_name(name: str, role: str) -> str:
    base_name, embedded_role = _split_name_role(name)
    resolved_role = _normalize_role(role) or embedded_role or "氏"
    if resolved_role == "氏":
        return f"{base_name}氏"
    if base_name.endswith(resolved_role):
        return base_name
    return f"{base_name}{resolved_role}"


def _extract_first_quote(*texts: str) -> str:
    for text in texts:
        cleaned = _clean_text(text)
        if not cleaned:
            continue
        match = _QUOTE_RE.search(cleaned)
        if match:
            return match.group(1).strip()
    return ""


def _replace_generic_subject(existing_title: str, display_name: str) -> str:
    cleaned = _clean_text(existing_title)
    if not cleaned:
        return display_name

    lineup_stripped = cleaned
    if _LINEUP_PREFIX_RE.match(cleaned):
        candidate = _LINEUP_PREFIX_RE.sub("", cleaned, count=1).lstrip()
        if candidate and (_LEADING_PARTICLE_RE.match(candidate) or _GENERIC_HEAD_RE.match(candidate)):
            lineup_stripped = candidate

    if lineup_stripped in _GENERIC_LABELS:
        return display_name

    if _LEADING_PARTICLE_RE.match(lineup_stripped):
        return f"{display_name}{lineup_stripped}"

    match = _GENERIC_HEAD_RE.match(lineup_stripped)
    if match:
        rest = match.group("rest") or ""
        return f"{display_name}{rest}"

    return ""


def backfill_title_player_name(
    *,
    existing_title: str,
    source_title: str = "",
    body: str = "",
    summary: str = "",
    metadata: Mapping[str, object] | None = None,
) -> TitlePlayerNameBackfillResult:
    metadata = dict(metadata or {})
    current_title = _clean_text(existing_title)
    source_title_clean = _clean_text(source_title)
    fallback_title = source_title_clean or current_title

    if _title_already_has_named_subject(current_title):
        return TitlePlayerNameBackfillResult(
            title=current_title,
            changed=current_title != _clean_text(existing_title),
        )

    player_name, role = _choose_candidate(
        existing_title=current_title,
        source_title=source_title_clean,
        body=body,
        summary=summary,
        metadata=metadata,
    )
    if not player_name:
        return TitlePlayerNameBackfillResult(
            title=fallback_title,
            changed=fallback_title != current_title,
            review_reason="title_player_name_unresolved",
        )

    display_name = _display_name(player_name, role)
    quote = _extract_first_quote(source_title_clean, body, summary)
    if any(marker in current_title for marker in _COMMENT_TITLE_MARKERS):
        if quote:
            resolved = f"{display_name}「{quote}」試合後コメント"
        else:
            resolved = f"{display_name} 試合後コメント"
        return TitlePlayerNameBackfillResult(
            title=resolved,
            changed=resolved != current_title,
            player_name=player_name,
            role=role,
        )

    replaced = _replace_generic_subject(current_title, display_name)
    if replaced:
        return TitlePlayerNameBackfillResult(
            title=replaced,
            changed=replaced != current_title,
            player_name=player_name,
            role=role,
        )

    if source_title_clean and title_has_person_name_candidate(source_title_clean):
        return TitlePlayerNameBackfillResult(
            title=source_title_clean,
            changed=source_title_clean != current_title,
            player_name=player_name,
            role=role,
        )

    return TitlePlayerNameBackfillResult(
        title=fallback_title,
        changed=fallback_title != current_title,
        review_reason="title_player_name_unresolved",
        player_name=player_name,
        role=role,
    )


__all__ = [
    "TitlePlayerNameBackfillResult",
    "backfill_title_player_name",
]
