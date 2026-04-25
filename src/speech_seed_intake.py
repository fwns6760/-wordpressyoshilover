"""Dry-run speech seed intake for comment-lane candidate evaluation.

This module is intentionally read-only and pure. It evaluates whether one
speech seed is suitable for the comment lane before handing anything to the
existing fixed lane or publish runner.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
import json
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from src.source_id import source_id as build_source_id
from src.source_trust import classify_url


ROUTE_COMMENT_CANDIDATE = "comment_candidate"
ROUTE_DEFERRED_PICKUP = "deferred_pickup"
ROUTE_DUPLICATE_LIKE = "duplicate_like"
ROUTE_REJECT = "reject"

HIGH_OVERLAP_THRESHOLD = 0.72
MEDIUM_OVERLAP_THRESHOLD = 0.48

_WS_RE = re.compile(r"\s+")
_QUOTE_BLOCK_RE = re.compile(r"[「『\"]([^「」『』\"]+)[」』\"]")
_MULTI_SPLIT_RE = re.compile(r"(?:、|,|/|／|｜|\||&|＆|と)")
_CJK_TOKEN_RE = re.compile(r"[一-龥々]{2,}|[ぁ-ん]{2,}|[ァ-ヴー]{2,}|[a-z0-9]{2,}", re.IGNORECASE)
_SCORE_RE = re.compile(r"\d{1,2}\s*[-－–]\s*\d{1,2}")
_POSTGAME_SCENE_MARKERS = ("試合後", "囲み", "postgame", "試合後コメント", "試合後談話")
_POSTGAME_SUMMARY_MARKERS = (
    "試合を振り返",
    "一戦を振り返",
    "試合後コメント",
    "試合後談話",
    "総括",
    "振り返った",
    "勝ててよかった",
    "負けたが",
    "チームとして",
    "投手陣",
    "打線",
    "守備",
    "先発",
    "明日も",
)
_GENERIC_QUOTE_MARKERS = (
    "勝ててよかった",
    "負けはしたが",
    "明日も頑張る",
    "切り替えて",
    "チームとして",
)

_SOURCE_KIND_ALIASES = {
    "official": "official_web",
    "official_site": "official_web",
    "giants_official": "official_web",
    "official_x": "team_x",
    "official_media_x": "official_media_x",
    "team_twitter": "team_x",
    "team_x_post": "team_x",
    "x_team": "team_x",
    "quote": "comment_quote",
    "tv_comment": "tv_radio_comment",
    "radio_comment": "tv_radio_comment",
    "tv_radio": "tv_radio_comment",
    "rss": "major_rss",
    "social_news": "official_media_x",
    "fan": "fan_reaction",
    "fan_comment": "fan_reaction",
    "reply": "fan_reaction",
}

_COMMENT_READY_SOURCE_KINDS = frozenset(
    {
        "official_web",
        "npb",
        "team_x",
        "tv_radio_comment",
        "comment_quote",
    }
)
_TOPIC_ONLY_SOURCE_KINDS = frozenset(
    {
        "major_rss",
        "reporter_x",
        "official_media_x",
        "program_table",
        "farm_info",
        "player_stats_feed",
    }
)
_LOW_TRUST_SOURCE_KINDS = frozenset(
    {
        "",
        "unknown",
        "other",
        "fan_reaction",
        "reaction",
        "repost",
        "quote_post",
        "ambiguous_x",
    }
)


@dataclass(frozen=True)
class SpeechSeedDecision:
    speaker: str
    scene: str
    quote_core: str
    source_kind: str
    trust_hint: str
    candidate_key: str
    news_overlap_score: float
    postgame_summary_like: bool
    route_hint: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def evaluate_speech_seed(
    seed: Mapping[str, Any],
    rss_index: Sequence[Mapping[str, Any]] = (),
) -> SpeechSeedDecision:
    speaker = _clean(seed.get("speaker"))
    scene = _clean(seed.get("scene"))
    source_url = _clean(seed.get("source_url"))
    source_title = _clean(seed.get("source_title"))
    quote_text = _clean(seed.get("quote_text"))
    surrounding_text = _clean(seed.get("surrounding_text"))
    quote_core = _extract_quote_core(quote_text)
    source_kind = _normalize_source_kind(seed.get("source_kind"))
    url_trust = classify_url(source_url) if source_url else "unknown"
    trust_hint = _build_trust_hint(source_kind, url_trust)
    candidate_key = _build_candidate_key(source_url, speaker, scene, quote_core)
    news_overlap_score = _compute_news_overlap_score(seed, rss_index, quote_core=quote_core)
    postgame_summary_like = _is_postgame_summary_like(
        scene=scene,
        source_title=source_title,
        quote_core=quote_core,
        surrounding_text=surrounding_text,
    )

    reasons: list[str] = []
    if not source_url:
        reasons.append("source_url_missing")
    if not speaker:
        reasons.append("speaker_missing")
    if not scene:
        reasons.append("scene_missing")
    if not quote_core:
        reasons.append("quote_core_missing")

    if _looks_multi_value(speaker):
        reasons.append("multiple_speakers")
    if _looks_multi_scene(scene):
        reasons.append("multiple_scenes")
    if _looks_multi_nucleus(quote_text, quote_core):
        reasons.append("multiple_nucleus_like")

    if source_kind in _LOW_TRUST_SOURCE_KINDS:
        reasons.append("source_kind_low_trust")
    elif source_kind in _TOPIC_ONLY_SOURCE_KINDS:
        reasons.append("source_kind_topic_only")
    elif source_kind not in _COMMENT_READY_SOURCE_KINDS:
        reasons.append("source_kind_unmapped")

    if url_trust == "rumor":
        reasons.append("url_trust_rumor")
    elif url_trust == "unknown":
        reasons.append("url_trust_unknown")

    if news_overlap_score >= HIGH_OVERLAP_THRESHOLD:
        reasons.append("news_overlap_high")
    elif news_overlap_score >= MEDIUM_OVERLAP_THRESHOLD:
        reasons.append("news_overlap_medium")

    if postgame_summary_like:
        reasons.append("postgame_summary_like")

    route_hint = _decide_route(
        reasons=reasons,
        source_kind=source_kind,
        news_overlap_score=news_overlap_score,
        postgame_summary_like=postgame_summary_like,
    )

    return SpeechSeedDecision(
        speaker=speaker,
        scene=scene,
        quote_core=quote_core,
        source_kind=source_kind,
        trust_hint=trust_hint,
        candidate_key=candidate_key,
        news_overlap_score=round(news_overlap_score, 3),
        postgame_summary_like=postgame_summary_like,
        route_hint=route_hint,
        reasons=tuple(_dedupe_preserve(reasons)),
    )


def evaluate_speech_seed_batch(
    seeds: Sequence[Mapping[str, Any]],
    rss_index: Sequence[Mapping[str, Any]] = (),
) -> tuple[SpeechSeedDecision, ...]:
    return tuple(evaluate_speech_seed(seed, rss_index) for seed in seeds)


def dump_speech_seed_report(
    decisions: Sequence[SpeechSeedDecision],
    *,
    fmt: str = "json",
) -> str:
    if fmt == "human":
        return render_speech_seed_human(decisions)
    payload = {
        "items": len(decisions),
        "routes": _route_counts(decisions),
        "results": [decision.as_dict() for decision in decisions],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_speech_seed_human(decisions: Sequence[SpeechSeedDecision]) -> str:
    lines = [
        "Speech Seed Intake Dry Run",
        f"items: {len(decisions)}",
    ]
    counts = _route_counts(decisions)
    lines.extend(
        [
            f"comment_candidate: {counts.get(ROUTE_COMMENT_CANDIDATE, 0)}",
            f"deferred_pickup: {counts.get(ROUTE_DEFERRED_PICKUP, 0)}",
            f"duplicate_like: {counts.get(ROUTE_DUPLICATE_LIKE, 0)}",
            f"reject: {counts.get(ROUTE_REJECT, 0)}",
        ]
    )
    for index, decision in enumerate(decisions, start=1):
        lines.extend(
            [
                "",
                f"candidate {index}",
                f"speaker: {decision.speaker}",
                f"scene: {decision.scene}",
                f"quote_core: {decision.quote_core}",
                f"source_kind: {decision.source_kind}",
                f"trust_hint: {decision.trust_hint}",
                f"candidate_key: {decision.candidate_key}",
                f"news_overlap_score: {decision.news_overlap_score:.3f}",
                f"postgame_summary_like: {str(decision.postgame_summary_like).lower()}",
                f"route_hint: {decision.route_hint}",
                f"reasons: {', '.join(decision.reasons) if decision.reasons else '-'}",
            ]
        )
    return "\n".join(lines) + "\n"


def _route_counts(decisions: Sequence[SpeechSeedDecision]) -> dict[str, int]:
    counts = {
        ROUTE_COMMENT_CANDIDATE: 0,
        ROUTE_DEFERRED_PICKUP: 0,
        ROUTE_DUPLICATE_LIKE: 0,
        ROUTE_REJECT: 0,
    }
    for decision in decisions:
        counts[decision.route_hint] = counts.get(decision.route_hint, 0) + 1
    return counts


def _decide_route(
    *,
    reasons: Sequence[str],
    source_kind: str,
    news_overlap_score: float,
    postgame_summary_like: bool,
) -> str:
    hard_reject_reasons = {
        "source_url_missing",
        "speaker_missing",
        "scene_missing",
        "quote_core_missing",
        "multiple_speakers",
        "multiple_scenes",
        "multiple_nucleus_like",
        "source_kind_low_trust",
        "url_trust_rumor",
    }
    if any(reason in hard_reject_reasons for reason in reasons):
        return ROUTE_REJECT
    if news_overlap_score >= HIGH_OVERLAP_THRESHOLD:
        return ROUTE_DUPLICATE_LIKE
    if postgame_summary_like:
        return ROUTE_DEFERRED_PICKUP
    if source_kind in _TOPIC_ONLY_SOURCE_KINDS:
        return ROUTE_DEFERRED_PICKUP
    if "source_kind_unmapped" in reasons:
        return ROUTE_DEFERRED_PICKUP
    if "url_trust_unknown" in reasons and source_kind not in {"comment_quote", "tv_radio_comment"}:
        return ROUTE_DEFERRED_PICKUP
    if news_overlap_score >= MEDIUM_OVERLAP_THRESHOLD:
        return ROUTE_DEFERRED_PICKUP
    return ROUTE_COMMENT_CANDIDATE


def _build_candidate_key(source_url: str, speaker: str, scene: str, quote_core: str) -> str:
    source_key = build_source_id(source_url) if source_url else "missing-source"
    fingerprint = sha1(
        "|".join((_normalized_key(source_key), _normalized_key(speaker), _normalized_key(scene), _normalized_key(quote_core))).encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    return f"speech:{source_key}:{fingerprint}"


def _build_trust_hint(source_kind: str, url_trust: str) -> str:
    if source_kind in _COMMENT_READY_SOURCE_KINDS:
        bucket = "comment_direct"
    elif source_kind in _TOPIC_ONLY_SOURCE_KINDS:
        bucket = "topic_only"
    else:
        bucket = "low_trust"
    return f"{bucket}:{url_trust}"


def _compute_news_overlap_score(
    seed: Mapping[str, Any],
    rss_index: Sequence[Mapping[str, Any]],
    *,
    quote_core: str,
) -> float:
    candidate_titles = [_clean(seed.get("source_title")), quote_core]
    candidate_titles.extend(_coerce_title_list(seed.get("rss_reference_titles")))
    candidate_titles = [title for title in candidate_titles if title]
    if not candidate_titles or not rss_index:
        return 0.0

    best = 0.0
    for rss_row in rss_index:
        title = _extract_index_title(rss_row)
        if not title:
            continue
        for candidate_title in candidate_titles:
            best = max(best, _title_similarity(candidate_title, title))
    return min(best, 1.0)


def _extract_index_title(entry: Mapping[str, Any]) -> str:
    for key in ("title", "source_title", "headline", "name"):
        value = _clean(entry.get(key))
        if value:
            return value
    return ""


def _title_similarity(left: str, right: str) -> float:
    left_key = _normalized_key(left)
    right_key = _normalized_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    shorter = min(len(left_key), len(right_key))
    longer = max(len(left_key), len(right_key))
    containment = 0.0
    if left_key in right_key or right_key in left_key:
        containment = shorter / longer

    left_ngrams = _char_ngrams(left_key, 3)
    right_ngrams = _char_ngrams(right_key, 3)
    ngram_score = _jaccard(left_ngrams, right_ngrams)

    left_tokens = _lexical_tokens(left_key)
    right_tokens = _lexical_tokens(right_key)
    token_score = _jaccard(left_tokens, right_tokens)

    return max(containment * 0.95, ngram_score * 0.7 + token_score * 0.3)


def _char_ngrams(text: str, width: int) -> set[str]:
    if len(text) <= width:
        return {text} if text else set()
    return {text[index : index + width] for index in range(len(text) - width + 1)}


def _lexical_tokens(text: str) -> set[str]:
    return {token for token in _CJK_TOKEN_RE.findall(text) if token}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _coerce_title_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value if _clean(item)]
    cleaned = _clean(value)
    return [cleaned] if cleaned else []


def _looks_multi_value(value: str) -> bool:
    text = _clean(value)
    if not text:
        return False
    if not _MULTI_SPLIT_RE.search(text):
        return False
    parts = [part.strip() for part in _MULTI_SPLIT_RE.split(text) if part.strip()]
    return len(parts) > 1


def _looks_multi_scene(scene: str) -> bool:
    text = _clean(scene)
    if not text:
        return False
    if "と" in text and any(marker in text for marker in _POSTGAME_SCENE_MARKERS):
        return True
    return _looks_multi_value(text)


def _looks_multi_nucleus(quote_text: str, quote_core: str) -> bool:
    matches = _dedupe_preserve(match.strip() for match in _QUOTE_BLOCK_RE.findall(_clean(quote_text)) if match.strip())
    if len(matches) > 1:
        return True
    normalized = _normalized_key(quote_text)
    if any(marker in normalized for marker in ("一方", "また", "そして")) and len(_normalized_key(quote_core)) >= 18:
        return True
    return False


def _is_postgame_summary_like(
    *,
    scene: str,
    source_title: str,
    quote_core: str,
    surrounding_text: str,
) -> bool:
    scene_key = _normalized_key(scene)
    if not any(marker in scene_key for marker in (_normalized_key(item) for item in _POSTGAME_SCENE_MARKERS)):
        return False
    combined = " ".join(part for part in (source_title, quote_core, surrounding_text) if part)
    combined_key = _normalized_key(combined)
    if any(_normalized_key(marker) in combined_key for marker in _POSTGAME_SUMMARY_MARKERS):
        return True
    if _SCORE_RE.search(combined) and (
        any(_normalized_key(marker) in combined_key for marker in ("勝利", "敗戦", "引き分け", "白星", "黒星"))
        or len(_normalized_key(quote_core)) <= 16
        or any(_normalized_key(marker) in _normalized_key(quote_core) for marker in _GENERIC_QUOTE_MARKERS)
    ):
        return True
    return False


def _extract_quote_core(value: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    matches = [match.strip() for match in _QUOTE_BLOCK_RE.findall(text) if match.strip()]
    if len(matches) == 1:
        return _collapse_space(matches[0])
    return _collapse_space(text.strip("「」『』\"' "))


def _normalize_source_kind(value: Any) -> str:
    cleaned = _clean(value).lower().replace("-", "_").replace(" ", "_")
    return _SOURCE_KIND_ALIASES.get(cleaned, cleaned or "unknown")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _collapse_space(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _normalized_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", _clean(value)).lower()
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[^0-9a-zぁ-んァ-ヴー一-龥々]+", " ", normalized)
    return _collapse_space(normalized)


def _dedupe_preserve(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        marker = _normalized_key(value)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        items.append(value)
    return items


__all__ = [
    "ROUTE_COMMENT_CANDIDATE",
    "ROUTE_DEFERRED_PICKUP",
    "ROUTE_DUPLICATE_LIKE",
    "ROUTE_REJECT",
    "SpeechSeedDecision",
    "dump_speech_seed_report",
    "evaluate_speech_seed",
    "evaluate_speech_seed_batch",
    "render_speech_seed_human",
]
