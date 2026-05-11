"""Title player-name backfill helpers for ticket 277-QA."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from src.article_quality_guards import is_generic_compound_subject
from src.title_validator import title_has_person_name_candidate


_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LINEUP_PREFIX_RE = re.compile(r"^\s*巨人スタメン\s*")
_LEADING_PARTICLE_RE = re.compile(r"^[がをにのへともや]")
_GENERIC_HEAD_RE = re.compile(
    r"^(?P<label>選手|投手|捕手|内野手|外野手|コーチ|監督|チーム|首脳陣)"
    r"(?P<rest>(?:[、，,]\s*.*|\s+.*|[がはもをにへと].*|$))"
)
_GENERIC_COMPOUND_HEAD_RE = re.compile(
    r"^(?P<label>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24}?(?:選手|投手))"
    r"(?P<rest>(?:[、，,]\s*.*|\s+.*|[がはもをにへと].*|$))"
)
_QUOTE_RE = re.compile(r"[「『]([^」』]{1,40})[」』]")
_NAME_WITH_ROLE_RE = re.compile(
    r"#?(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24}?)[\s\u3000]*(?P<role>投手|捕手|内野手|外野手|選手|監督|コーチ)"
)
_NAME_RE = re.compile(
    r"(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24})(?=(?:が|は|も|の|と|、|，|,|「|『|[0-9０-９]|$))"
)
_GENERIC_LABELS = frozenset({"選手", "投手", "捕手", "内野手", "外野手", "コーチ", "監督", "チーム", "首脳陣"})
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
        "若手",
        "主力",
        "育成",
        "新人",
        "紹介",
        "調整",
        "確認",
        "整理",
        "注目",
        "試合",
        "先発",
        "登板",
        "登録",
        "抹消",
        "復帰",
        "昇格",
        "合流",
        "新星",
        "投打",
        "恩返し",
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
    "若手",
    "主力",
    "育成",
    "新人",
    "スポーツ",
    "報知",
    "日刊",
    "スポニチ",
    "サンスポ",
    "デイリー",
    "東スポ",
    "巨人班",
    "公式",
    "ニュース",
    "オンライン",
    "新聞",
    "通信",
    "編集部",
    "取材班",
    "番記者",
    "メディア",
    "ベースボール",
    "チャンネル",
    "テレビ",
    "ラジオ",
    "Xが",
    "Ｘが",
    "ジャイアンツ球場",
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
    "新星",
    "投打",
    "恩返し",
)


@dataclass(frozen=True)
class TitlePlayerNameBackfillResult:
    title: str
    changed: bool
    review_reason: str = ""
    player_name: str = ""
    role: str = ""


@dataclass(frozen=True)
class _CandidateSelection:
    name: str = ""
    role: str = ""
    ambiguous: bool = False


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
    compound_match = _GENERIC_COMPOUND_HEAD_RE.match(cleaned)
    if compound_match and is_generic_compound_subject(compound_match.group("label")):
        return False
    if cleaned.startswith(tuple(_GENERIC_LABELS)) and any(marker in cleaned for marker in _COMMENT_TITLE_MARKERS):
        return False
    if _GENERIC_HEAD_RE.match(cleaned):
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


def _candidate_key(name: str) -> str:
    return re.sub(r"\s+", "", _clean_text(name))


def _candidate_mention_count(name: str, *texts: str) -> int:
    key = _candidate_key(name)
    if not key:
        return 0
    count = 0
    for text in texts:
        compact = re.sub(r"\s+", "", _clean_text(text))
        count += compact.count(key)
    return count


def _choose_unique_frequency_leader(
    candidates: list[tuple[str, str]],
    *,
    source_title: str,
    body: str,
    summary: str,
) -> tuple[str, str] | None:
    ranked = sorted(
        (
            (_candidate_mention_count(name, source_title, body, summary), index, name, role)
            for index, (name, role) in enumerate(candidates)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked:
        return None
    if len(ranked) == 1:
        _, _, name, role = ranked[0]
        return name, role
    top_count, _, name, role = ranked[0]
    second_count = ranked[1][0]
    if top_count > second_count:
        return name, role
    return None


def _common_candidate_role(candidates: list[tuple[str, str]], metadata_role: str = "") -> str:
    if metadata_role:
        return metadata_role
    roles = {role for _, role in candidates if role}
    if len(roles) == 1:
        return roles.pop()
    return ""


def _collect_candidates_from_text(text: str, *, allow_loose_names: bool = True) -> list[tuple[str, str]]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for match in _NAME_WITH_ROLE_RE.finditer(cleaned):
        _append_candidate(candidates, seen, match.group("name"), role_hint=match.group("role"))
    if not allow_loose_names:
        return candidates
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
) -> _CandidateSelection:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    metadata_role = _normalize_role(str(metadata.get("role") or ""))
    for key in ("speaker", "player_name", "subject_player"):
        _append_candidate(candidates, seen, str(metadata.get(key) or ""), role_hint=metadata_role)
    metadata_candidate_count = len(candidates)
    text_sources = (
        (source_title, _title_already_has_named_subject(source_title)),
        (body, True),
        (summary, True),
    )
    for text, allow_loose_names in text_sources:
        for name, role in _collect_candidates_from_text(text, allow_loose_names=allow_loose_names):
            _append_candidate(candidates, seen, name, role_hint=role)
    if not candidates:
        return _CandidateSelection()
    if metadata_candidate_count:
        name, role = candidates[0]
    else:
        role_candidates = [(name, role) for name, role in candidates if role]
        choice_pool = role_candidates or candidates
        selected = _choose_unique_frequency_leader(choice_pool, source_title=source_title, body=body, summary=summary)
        if selected is None:
            return _CandidateSelection(role=_common_candidate_role(choice_pool, metadata_role), ambiguous=True)
        name, role = selected
    if not role:
        role = _infer_role(
            name,
            existing_title=existing_title,
            source_title=source_title,
            body=body,
            summary=summary,
            metadata=metadata,
        )
    return _CandidateSelection(name=name, role=role)


def _display_name(name: str, role: str) -> str:
    base_name, embedded_role = _split_name_role(name)
    resolved_role = _normalize_role(role) or embedded_role or "氏"
    if resolved_role == "氏":
        return f"{base_name}氏"
    if resolved_role == "選手":
        return base_name
    if base_name.endswith(resolved_role):
        return base_name
    return f"{base_name}{resolved_role}"


def _generic_label_matches_role(label: str, role: str) -> bool:
    normalized_role = _normalize_role(role)
    if label == "選手":
        return normalized_role in {"選手", "投手"}
    if label in {"捕手", "内野手", "外野手"}:
        return normalized_role == "選手"
    if label == "投手":
        return normalized_role == "投手"
    if label == "監督":
        return normalized_role == "監督"
    if label == "コーチ":
        return normalized_role == "コーチ"
    if label == "首脳陣":
        return normalized_role in {"監督", "コーチ"}
    return False


def _generic_compound_matches_role(label: str, role: str) -> bool:
    normalized_role = _normalize_role(role)
    if label.endswith("投手"):
        return normalized_role == "投手"
    if label.endswith("選手"):
        return normalized_role in {"選手", "投手"}
    return False


def _extract_first_quote(*texts: str) -> str:
    for text in texts:
        cleaned = _clean_text(text)
        if not cleaned:
            continue
        match = _QUOTE_RE.search(cleaned)
        if match:
            return match.group(1).strip()
    return ""


def _replace_generic_subject(existing_title: str, display_name: str, *, role: str = "") -> str:
    cleaned = _clean_text(existing_title)
    if not cleaned:
        return display_name

    lineup_stripped = cleaned
    if _LINEUP_PREFIX_RE.match(cleaned):
        candidate = _LINEUP_PREFIX_RE.sub("", cleaned, count=1).lstrip()
        if candidate and (_LEADING_PARTICLE_RE.match(candidate) or _GENERIC_HEAD_RE.match(candidate)):
            lineup_stripped = candidate

    if lineup_stripped in _GENERIC_LABELS:
        if not _generic_label_matches_role(lineup_stripped, role):
            return ""
        return display_name

    if _LEADING_PARTICLE_RE.match(lineup_stripped):
        return f"{display_name}{lineup_stripped}"

    compound_match = _GENERIC_COMPOUND_HEAD_RE.match(lineup_stripped)
    if compound_match and is_generic_compound_subject(compound_match.group("label")):
        if not _generic_compound_matches_role(compound_match.group("label"), role):
            return ""
        rest = compound_match.group("rest") or ""
        return f"{display_name}{rest}"

    match = _GENERIC_HEAD_RE.match(lineup_stripped)
    if match:
        if not _generic_label_matches_role(match.group("label"), role):
            return ""
        rest = match.group("rest") or ""
        return f"{display_name}{rest}"

    return ""


def _neutral_subject_for_role(role: str) -> str:
    if _normalize_role(role) in {"監督", "コーチ"}:
        return "首脳陣"
    return "巨人"


def _replace_generic_subject_neutral(existing_title: str, role: str = "") -> str:
    neutral_subject = _neutral_subject_for_role(role)
    cleaned = _clean_text(existing_title)
    if not cleaned:
        return neutral_subject

    lineup_stripped = cleaned
    if _LINEUP_PREFIX_RE.match(cleaned):
        candidate = _LINEUP_PREFIX_RE.sub("", cleaned, count=1).lstrip()
        if candidate and (_LEADING_PARTICLE_RE.match(candidate) or _GENERIC_HEAD_RE.match(candidate)):
            lineup_stripped = candidate

    if lineup_stripped in _GENERIC_LABELS:
        return neutral_subject
    if _LEADING_PARTICLE_RE.match(lineup_stripped):
        return f"{neutral_subject}{lineup_stripped}"
    compound_match = _GENERIC_COMPOUND_HEAD_RE.match(lineup_stripped)
    if compound_match and is_generic_compound_subject(compound_match.group("label")):
        rest = compound_match.group("rest") or ""
        return f"{neutral_subject}{rest}"
    match = _GENERIC_HEAD_RE.match(lineup_stripped)
    if match:
        rest = match.group("rest") or ""
        return f"{neutral_subject}{rest}"
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

    selection = _choose_candidate(
        existing_title=current_title,
        source_title=source_title_clean,
        body=body,
        summary=summary,
        metadata=metadata,
    )
    player_name = selection.name
    role = selection.role
    if selection.ambiguous:
        neutral_title = _replace_generic_subject_neutral(current_title, role=role)
        if neutral_title:
            return TitlePlayerNameBackfillResult(
                title=neutral_title,
                changed=neutral_title != current_title,
                role=role,
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

    replaced = _replace_generic_subject(current_title, display_name, role=role)
    if replaced:
        return TitlePlayerNameBackfillResult(
            title=replaced,
            changed=replaced != current_title,
            player_name=player_name,
            role=role,
        )

    if source_title_clean and _title_already_has_named_subject(source_title_clean):
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
