"""Pure first-wave pickup promotion judgment for fixture dry-runs.

046-A1 keeps this logic outside the runtime runner. The runtime route can
import it in a later ticket, but this module performs no WP writes and makes
no network calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from src.source_trust import classify_url


ROUTE_FIXED_PRIMARY = "fixed_primary"
ROUTE_DEFERRED_PICKUP = "deferred_pickup"
ROUTE_DUPLICATE_ABSORBED = "duplicate_absorbed"

TRUST_TIER_T1 = "T1"
TRUST_TIER_T2 = "T2"

SOURCE_KIND_OFFICIAL_WEB = "official_web"
SOURCE_KIND_NPB = "npb"
SOURCE_KIND_MAJOR_RSS = "major_rss"
SOURCE_KIND_TEAM_X = "team_x"
SOURCE_KIND_TV_RADIO_COMMENT = "tv_radio_comment"
SOURCE_KIND_COMMENT_QUOTE = "comment_quote"

FIRST_WAVE_FAMILIES = (
    "lineup_notice",
    "comment_notice",
    "injury_notice",
    "postgame_result",
)

FIRST_WAVE_PROMOTION_SOURCE_KINDS: dict[str, frozenset[str]] = {
    "lineup_notice": frozenset({SOURCE_KIND_OFFICIAL_WEB, SOURCE_KIND_TEAM_X}),
    "comment_notice": frozenset(
        {
            SOURCE_KIND_OFFICIAL_WEB,
            SOURCE_KIND_TEAM_X,
            SOURCE_KIND_MAJOR_RSS,
            SOURCE_KIND_TV_RADIO_COMMENT,
            SOURCE_KIND_COMMENT_QUOTE,
        }
    ),
    "injury_notice": frozenset(
        {
            SOURCE_KIND_OFFICIAL_WEB,
            SOURCE_KIND_TV_RADIO_COMMENT,
            SOURCE_KIND_COMMENT_QUOTE,
        }
    ),
    "postgame_result": frozenset({SOURCE_KIND_OFFICIAL_WEB, SOURCE_KIND_TEAM_X, SOURCE_KIND_NPB}),
}

SOURCE_KIND_ALLOWED_TRUST_TIERS: dict[str, frozenset[str]] = {
    SOURCE_KIND_OFFICIAL_WEB: frozenset({TRUST_TIER_T1}),
    SOURCE_KIND_NPB: frozenset({TRUST_TIER_T1}),
    SOURCE_KIND_TEAM_X: frozenset({TRUST_TIER_T1, TRUST_TIER_T2}),
    SOURCE_KIND_MAJOR_RSS: frozenset({TRUST_TIER_T2}),
    SOURCE_KIND_TV_RADIO_COMMENT: frozenset({TRUST_TIER_T1, TRUST_TIER_T2}),
    SOURCE_KIND_COMMENT_QUOTE: frozenset({TRUST_TIER_T1, TRUST_TIER_T2}),
}

PRIMARY_URL_REQUIRED_SOURCE_KINDS = frozenset({SOURCE_KIND_OFFICIAL_WEB, SOURCE_KIND_TEAM_X})


@dataclass(frozen=True)
class FirstWaveCandidate:
    subtype: str
    candidate_key: str
    source_kind: str
    trust_tier: str
    source_url: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FirstWaveCandidate":
        subtype = _first_non_empty(raw, "subtype", "family", "article_type")
        return cls(
            subtype=subtype,
            candidate_key=_clean(raw.get("candidate_key")),
            source_kind=_normalize_source_kind(raw.get("source_kind")),
            trust_tier=_clean(raw.get("trust_tier")).upper(),
            source_url=_clean(raw.get("source_url")),
        )


@dataclass(frozen=True)
class PromotionDecision:
    route: str
    subtype: str
    candidate_key: str
    source_kind: str
    trust_tier: str

    def evidence_line(self) -> str:
        return (
            f"route={self.route} "
            f"subtype={self.subtype} "
            f"candidate_key={self.candidate_key} "
            f"source_kind={self.source_kind} "
            f"trust_tier={self.trust_tier}"
        )


def judge_first_wave_promotion(
    candidate: FirstWaveCandidate | Mapping[str, Any],
    *,
    existing_candidate_keys: Iterable[str] = (),
) -> PromotionDecision:
    """Return the dry-run route decision for one first-wave candidate."""

    normalized = _coerce_candidate(candidate)
    duplicate_keys = {_clean(value) for value in existing_candidate_keys if _clean(value)}
    route = (
        ROUTE_DUPLICATE_ABSORBED
        if normalized.candidate_key and normalized.candidate_key in duplicate_keys
        else ROUTE_FIXED_PRIMARY
        if _matches_first_wave_boundary(normalized)
        else ROUTE_DEFERRED_PICKUP
    )
    return PromotionDecision(
        route=route,
        subtype=normalized.subtype,
        candidate_key=normalized.candidate_key,
        source_kind=normalized.source_kind,
        trust_tier=normalized.trust_tier,
    )


def judge_first_wave_batch(
    candidates: Sequence[FirstWaveCandidate | Mapping[str, Any]],
    *,
    existing_candidate_keys: Iterable[str] = (),
) -> tuple[PromotionDecision, ...]:
    """Evaluate candidates in order and absorb duplicate candidate keys."""

    seen = {_clean(value) for value in existing_candidate_keys if _clean(value)}
    decisions: list[PromotionDecision] = []
    for candidate in candidates:
        normalized = _coerce_candidate(candidate)
        decision = judge_first_wave_promotion(normalized, existing_candidate_keys=seen)
        decisions.append(decision)
        if normalized.candidate_key:
            seen.add(normalized.candidate_key)
    return tuple(decisions)


def _matches_first_wave_boundary(candidate: FirstWaveCandidate) -> bool:
    allowed_source_kinds = FIRST_WAVE_PROMOTION_SOURCE_KINDS.get(candidate.subtype)
    if not allowed_source_kinds or candidate.source_kind not in allowed_source_kinds:
        return False
    allowed_tiers = SOURCE_KIND_ALLOWED_TRUST_TIERS.get(candidate.source_kind, frozenset())
    if candidate.trust_tier not in allowed_tiers:
        return False
    if candidate.source_kind in PRIMARY_URL_REQUIRED_SOURCE_KINDS:
        return classify_url(candidate.source_url) == "primary"
    return True


def _coerce_candidate(candidate: FirstWaveCandidate | Mapping[str, Any]) -> FirstWaveCandidate:
    if isinstance(candidate, FirstWaveCandidate):
        return candidate
    return FirstWaveCandidate.from_mapping(candidate)


def _first_non_empty(raw: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _clean(raw.get(key))
        if value:
            return value
    return ""


def _normalize_source_kind(value: Any) -> str:
    normalized = _clean(value).lower().replace("-", "_")
    aliases = {
        "official": SOURCE_KIND_OFFICIAL_WEB,
        "official_site": SOURCE_KIND_OFFICIAL_WEB,
        "giants_official": SOURCE_KIND_OFFICIAL_WEB,
        "npb_web": SOURCE_KIND_NPB,
        "team_twitter": SOURCE_KIND_TEAM_X,
        "team_x_post": SOURCE_KIND_TEAM_X,
        "x_team": SOURCE_KIND_TEAM_X,
        "rss": SOURCE_KIND_MAJOR_RSS,
        "sports_rss": SOURCE_KIND_MAJOR_RSS,
        "tv_radio": SOURCE_KIND_TV_RADIO_COMMENT,
        "tv_comment": SOURCE_KIND_TV_RADIO_COMMENT,
        "radio_comment": SOURCE_KIND_TV_RADIO_COMMENT,
        "quote": SOURCE_KIND_COMMENT_QUOTE,
    }
    return aliases.get(normalized, normalized)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
