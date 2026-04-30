"""Weak-title rescue helpers for ticket 290-QA."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

try:
    from .title_player_name_backfiller import backfill_title_player_name
except ImportError:  # pragma: no cover - top-level import path for rss_fetcher
    from title_player_name_backfiller import backfill_title_player_name


_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LEADING_BRACKET_RE = re.compile(r"^\s*【[^】]+】\s*")
_LEADING_TEAM_RE = re.compile(r"^\s*(?:巨人(?:戦)?[・、\s]+|ジャイアンツ[・、\s]+)")
_NAME_TOKEN_RE = re.compile(
    r"(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24})"
    r"(?=(?:投手|捕手|内野手|外野手|選手|監督|コーチ|氏|が|は|も|の|と|、|，|,|「|『|$))"
)
_TWO_NAME_RELATED_RE = re.compile(
    r"^(?P<first>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24})"
    r"と(?P<second>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24})が"
    r"(?P<rest>.+)$"
)
_MESSAGE_RE = re.compile(r"(?P<message>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･]{2,24}監督から[^ ]+?へのメッセージ)")
_COMMENTATOR_RE = re.compile(r"(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･]{2,24}氏)")
_NAMED_EVENT_RE = re.compile(
    r"^(?P<name>[A-Za-zＡ-Ｚａ-ｚ一-龯々ァ-ヴー・･\.\-]{2,24})[、,，]\s*"
    r"(?P<rest>[^。!！?？「」『』]*(?:[0-9０-９]+勝目|神生還|神走塁|好走塁|特大弾|復帰へ前進)[^。!！?？「」『』]*)"
)
_QUOTE_RE = re.compile(r"[「『]([^」』]{1,80})[」』]")
_RELATED_INFO_ESCAPE_RE = re.compile(r"(?:昇格・復帰|登録抹消|合流)\s*関連情報\s*$")
_BLACKLIST_RESCUE_RE = re.compile(r"(?:ベンチ関連の発言ポイント|ベンチ関連発言|関連発言)\s*$")

_GENERIC_NAME_TOKENS = frozenset(
    {
        "巨人",
        "ジャイアンツ",
        "巨人戦",
        "選手",
        "投手",
        "捕手",
        "内野手",
        "外野手",
        "監督",
        "コーチ",
        "首脳陣",
        "ベンチ",
        "チーム",
        "球団",
        "関連情報",
        "関連発言",
        "コメント整理",
        "発言ポイント",
        "試合後",
    }
)
_ROLE_SUFFIXES = ("投手", "捕手", "内野手", "外野手", "選手", "監督", "コーチ", "氏")
_ROLE_DISPLAY_SUFFIXES = {"投手", "選手"}
_SAFETY_BLOCK_MARKERS = ("死亡", "重傷", "救急", "意識不明", "ブルージェイズ", "ロッキーズ", "グッズ", "NIKE", "コジコジ")
_STRONG_EVENT_MARKERS = (
    "神走塁",
    "好走塁",
    "神業スライディング",
    "神生還",
    "スイム",
    "4勝目",
    "3勝目",
    "2勝目",
    "初勝利",
    "初本塁打",
    "特大弾",
    "ホームラン",
    "サヨナラ",
    "タイムリー",
    "決勝打",
    "復帰へ前進",
    "復帰",
    "昇格",
    "登録抹消",
    "再登録",
    "合流",
    "再開",
    "感嘆",
)
_EVENT_PATTERNS = (
    re.compile(r"屋外フリー打撃再開"),
    re.compile(r"フリー打撃再開"),
    re.compile(r"ブルペン(?:で)?(?:本格的な)?投球練習(?:を)?再開"),
    re.compile(r"投球練習(?:を)?再開"),
    re.compile(r"実戦復帰(?:へ前進|へ|見込み|予定|間近)?"),
    re.compile(r"[1１一]軍復帰へ前進"),
    re.compile(r"復帰へ前進"),
    re.compile(r"登録抹消"),
    re.compile(r"再登録"),
    re.compile(r"昇格"),
    re.compile(r"合流"),
    re.compile(r"特大弾(?:も披露)?"),
    re.compile(r"[0-9０-９]+勝目"),
    re.compile(r"神走塁"),
    re.compile(r"好走塁"),
    re.compile(r"神業スライディング"),
    re.compile(r"神生還"),
    re.compile(r"スイム"),
)


@dataclass(frozen=True)
class RescueResult:
    title: str
    strategy: str


def _clean_text(value: str) -> str:
    text = _HTML_RE.sub("", str(value or ""))
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _strip_source_prefixes(value: str) -> str:
    cleaned = _clean_text(value)
    cleaned = _LEADING_BRACKET_RE.sub("", cleaned)
    cleaned = _LEADING_TEAM_RE.sub("", cleaned)
    return cleaned.strip(" ・、")


def _looks_like_name(name: str) -> bool:
    candidate = _clean_text(name).strip("・･、, ")
    if not candidate or len(candidate) < 2:
        return False
    if candidate in _GENERIC_NAME_TOKENS:
        return False
    if any(suffix in candidate for suffix in ("関連情報", "関連発言", "発言ポイント", "コメント整理")):
        return False
    if any(char.isdigit() for char in candidate):
        return False
    return True


def _strip_role_suffix(name: str) -> str:
    cleaned = _clean_text(name)
    for suffix in _ROLE_SUFFIXES:
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)].strip()
    return cleaned


def _metadata_name(metadata: Mapping[str, object]) -> str:
    for key in ("speaker", "player_name", "subject_player", "manager_name"):
        value = _strip_role_suffix(str(metadata.get(key) or ""))
        if _looks_like_name(value):
            return value
    return ""


def _metadata_role(metadata: Mapping[str, object]) -> str:
    role = _clean_text(str(metadata.get("role") or ""))
    if role in _ROLE_DISPLAY_SUFFIXES:
        return role
    return ""


def _extract_first_name(text: str) -> str:
    cleaned = _strip_source_prefixes(text)
    for match in _NAME_TOKEN_RE.finditer(cleaned):
        candidate = _strip_role_suffix(match.group("name"))
        if _looks_like_name(candidate):
            return candidate
    return ""


def _resolve_primary_name(
    *,
    gen_title: str,
    source_title: str,
    body: str,
    summary: str,
    metadata: Mapping[str, object],
) -> str:
    for candidate in (
        _metadata_name(metadata),
        _extract_first_name(gen_title),
        _extract_first_name(source_title),
        _extract_first_name(summary),
    ):
        if _looks_like_name(candidate):
            return candidate

    backfilled = backfill_title_player_name(
        existing_title=gen_title,
        source_title=source_title,
        body=body,
        summary=summary,
        metadata=metadata,
    )
    return _extract_first_name(backfilled.title)


def _display_name(name: str, *, metadata: Mapping[str, object], add_role: bool) -> str:
    cleaned = _strip_role_suffix(name)
    if not add_role:
        return cleaned
    role = _metadata_role(metadata)
    if role and not cleaned.endswith(role):
        return f"{cleaned}{role}"
    return cleaned


def _extract_quote(text: str) -> str:
    match = _QUOTE_RE.search(_clean_text(text))
    if not match:
        return ""
    return match.group(1).strip()


def _extract_event_phrases(text: str, *, limit: int = 2) -> list[str]:
    source = _clean_text(text)
    matches: list[tuple[int, str]] = []
    for pattern in _EVENT_PATTERNS:
        for match in pattern.finditer(source):
            matches.append((match.start(), match.group(0).strip()))
    matches.sort(key=lambda item: item[0])
    ordered_phrases: list[str] = []
    for _, phrase in matches:
        if any(phrase == existing or phrase in existing for existing in ordered_phrases):
            continue
        ordered_phrases = [existing for existing in ordered_phrases if existing not in phrase]
        ordered_phrases.append(phrase)
    if len(ordered_phrases) <= limit:
        return ordered_phrases

    preferred_tail = ""
    for phrase in ordered_phrases[1:]:
        if any(marker in phrase for marker in ("復帰", "登録", "昇格", "合流")):
            preferred_tail = phrase
            break

    selected = [ordered_phrases[0]]
    if preferred_tail and preferred_tail not in selected and len(selected) < limit:
        selected.append(preferred_tail)
    for phrase in ordered_phrases[1:]:
        if len(selected) >= limit:
            break
        if phrase in selected:
            continue
        selected.append(phrase)
    return selected


def _contains_safety_blockers(
    *,
    gen_title: str,
    source_title: str,
    body: str,
    summary: str,
    metadata: Mapping[str, object],
) -> bool:
    combined = " ".join(
        part
        for part in (
            _clean_text(gen_title),
            _clean_text(source_title),
            _clean_text(body),
            _clean_text(summary),
        )
        if part
    )
    if any(marker in combined for marker in _SAFETY_BLOCK_MARKERS):
        return True
    if str(metadata.get("guard_outcome") or "").strip() == "skip":
        return True
    if any(bool(metadata.get(key)) for key in ("already_published", "duplicate_guard_skip", "hard_stop", "major_league_context", "merchandise")):
        return True
    if str(metadata.get("team_scope") or "").strip().lower() == "mixed":
        return True
    return False


def is_strong_with_name_and_event(title: str) -> bool:
    normalized = _clean_text(title)
    if not normalized:
        return False
    if not _extract_first_name(normalized):
        return False
    return any(marker in normalized for marker in _STRONG_EVENT_MARKERS)


def rescue_related_info_escape(
    *,
    gen_title: str,
    source_title: str,
    body: str,
    summary: str,
    metadata: Mapping[str, object],
) -> RescueResult | None:
    normalized_title = _clean_text(gen_title)
    if not _RELATED_INFO_ESCAPE_RE.search(normalized_title):
        return None
    if _contains_safety_blockers(
        gen_title=gen_title,
        source_title=source_title,
        body=body,
        summary=summary,
        metadata=metadata,
    ):
        return None

    source_core = _strip_source_prefixes(source_title)
    if not source_core:
        return None

    multi_match = _TWO_NAME_RELATED_RE.match(source_core)
    if multi_match:
        rest = _clean_text(multi_match.group("rest"))
        event_phrases = _extract_event_phrases(rest, limit=1)
        if not event_phrases:
            return None
        rescued = f"{multi_match.group('first')}・{multi_match.group('second')}が{event_phrases[0]}"
        return RescueResult(title=rescued, strategy="related_info_escape_multi_name")

    primary_name = _resolve_primary_name(
        gen_title=gen_title,
        source_title=source_core,
        body=body,
        summary=summary,
        metadata=metadata,
    )
    event_phrases = _extract_event_phrases(source_core)
    if not primary_name or not event_phrases:
        return None
    display_name = _display_name(primary_name, metadata=metadata, add_role=True)
    rescued = f"{display_name}、{' '.join(event_phrases)}"
    return RescueResult(title=rescued, strategy="related_info_escape_single_name")


def rescue_blacklist_phrase(
    *,
    gen_title: str,
    source_title: str,
    body: str,
    summary: str,
    metadata: Mapping[str, object],
) -> RescueResult | None:
    normalized_title = _clean_text(gen_title)
    if not _BLACKLIST_RESCUE_RE.search(normalized_title):
        return None
    if _contains_safety_blockers(
        gen_title=gen_title,
        source_title=source_title,
        body=body,
        summary=summary,
        metadata=metadata,
    ):
        return None

    source_core = _strip_source_prefixes(source_title)
    if not source_core:
        return None

    message_match = _MESSAGE_RE.search(source_core)
    commentator_match = _COMMENTATOR_RE.search(source_core)
    if message_match:
        rescued = message_match.group("message").strip()
        if commentator_match:
            rescued = f"{rescued} {commentator_match.group('name').strip()}"
        return RescueResult(title=rescued, strategy="blacklist_phrase_message")

    named_event_match = _NAMED_EVENT_RE.match(source_core)
    if named_event_match:
        rescued = f"{named_event_match.group('name')}、{_clean_text(named_event_match.group('rest'))}"
        return RescueResult(title=rescued, strategy="blacklist_phrase_named_event")

    primary_name = _resolve_primary_name(
        gen_title=gen_title,
        source_title=source_core,
        body=body,
        summary=summary,
        metadata=metadata,
    )
    quote = _extract_quote(source_core)
    event_phrases = _extract_event_phrases(source_core, limit=1)
    if not primary_name or not event_phrases:
        return None
    if quote:
        rescued = f"{primary_name}「{quote}」{event_phrases[0]}"
    else:
        rescued = f"{primary_name}、{event_phrases[0]}"
    return RescueResult(title=rescued, strategy="blacklist_phrase_quote_event")


__all__ = [
    "RescueResult",
    "is_strong_with_name_and_event",
    "rescue_blacklist_phrase",
    "rescue_related_info_escape",
]
