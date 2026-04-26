"""Mock-only source recheck and draft proposal builder for SNS topic seeds."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import re
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse


ROUTE_DRAFT_READY = "draft_ready"
ROUTE_CANDIDATE_ONLY = "candidate_only"
ROUTE_HOLD_SENSITIVE = "hold_sensitive"
ROUTE_DUPLICATE_NEWS = "duplicate_news"
ROUTE_REJECT = "reject"

Resolver = Callable[[Mapping[str, Any]], Mapping[str, Any]]

_ROUTES = (
    ROUTE_DRAFT_READY,
    ROUTE_CANDIDATE_ONLY,
    ROUTE_HOLD_SENSITIVE,
    ROUTE_DUPLICATE_NEWS,
    ROUTE_REJECT,
)

_CATEGORY_LABELS = {
    "player": "選手動向",
    "manager_strategy": "起用判断",
    "bullpen": "救援起用",
    "lineup": "スタメン動向",
    "farm": "ファーム動向",
    "injury_return": "コンディション情報",
    "transaction": "公示動向",
    "acquisition_trade": "補強動向",
}

_DEFAULT_TRENDS = {
    "player": "状態",
    "manager_strategy": "起用方針",
    "bullpen": "継投方針",
    "lineup": "スタメン構想",
    "farm": "昇格候補",
    "injury_return": "復帰時期",
    "transaction": "登録抹消",
    "acquisition_trade": "補強候補",
}

_SENSITIVE_TOPIC_CATEGORIES = frozenset({"injury_return"})
_SENSITIVE_KEYWORDS = (
    "負傷",
    "故障",
    "診断",
    "離脱",
    "復帰",
    "リハビリ",
    "違和感",
    "家族",
    "妻",
    "嫁",
    "子供",
    "息子",
    "娘",
    "不倫",
    "ハラスメント",
    "暴言",
    "誹謗中傷",
    "中傷",
    "嫌がらせ",
    "噂",
    "真偽不明",
    "未確認",
    "リーク",
)
_REJECT_FLAGS = frozenset({"account_exposure_required", "direct_quote_required", "too_few_matching_signals"})
_HOLD_FLAGS = frozenset({"slur_or_harassment", "private_family_or_rumor", "sns_only_sensitive_assertion"})
_DUPLICATE_FLAGS = frozenset({"recent_news_overlap"})

_URL_RE = re.compile(r"https?://\S+")
_HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,32}")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SourceRecheckDecision:
    topic_key: str
    topic_category: str
    entities: tuple[str, ...]
    trend_terms: tuple[str, ...]
    signal_count: int
    fact_recheck_required: bool
    route: str
    source_recheck_passed: bool
    official_source_present: bool
    recent_news_overlap: bool
    unsafe: bool
    reasons: tuple[str, ...]
    source_urls: tuple[str, ...]
    sns_topic_seed: bool = True
    publish_gate_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entities"] = list(self.entities)
        payload["trend_terms"] = list(self.trend_terms)
        payload["reasons"] = list(self.reasons)
        payload["source_urls"] = list(self.source_urls)
        return payload


@dataclass(frozen=True)
class DraftProposal:
    topic_key: str
    mock_draft_id: str
    title_hint: str
    lead_hint: str
    source_urls: tuple[str, ...]
    topic_category: str
    source_recheck_passed: bool = True
    sns_topic_seed: bool = True
    publish_gate_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_urls"] = list(self.source_urls)
        return payload


def evaluate_sns_topic_source_recheck_batch(
    candidates: Sequence[Mapping[str, Any] | Any],
    resolver: Resolver | None = None,
) -> tuple[SourceRecheckDecision, ...]:
    resolver_fn = resolver or _default_resolver
    decisions: list[SourceRecheckDecision] = []
    for candidate in candidates:
        normalized = _normalize_candidate(candidate)
        resolver_result = _normalize_resolver_result(resolver_fn(normalized))
        decisions.append(_route_candidate(normalized, resolver_result))
    return tuple(decisions)


def build_draft_proposals(decisions: Sequence[SourceRecheckDecision]) -> tuple[DraftProposal, ...]:
    proposals: list[DraftProposal] = []
    for decision in decisions:
        if decision.route != ROUTE_DRAFT_READY:
            continue
        proposals.append(
            DraftProposal(
                topic_key=decision.topic_key,
                mock_draft_id=_build_mock_draft_id(decision.topic_key),
                title_hint=_build_title_hint(decision),
                lead_hint=_build_lead_hint(decision),
                source_urls=decision.source_urls,
                topic_category=decision.topic_category,
            )
        )
    return tuple(proposals)


def dump_sns_topic_source_recheck_report(
    decisions: Sequence[SourceRecheckDecision],
    *,
    fmt: str = "json",
) -> str:
    proposals = build_draft_proposals(decisions)
    if fmt == "human":
        return render_sns_topic_source_recheck_human(decisions, proposals)

    payload = {
        "dry_run": True,
        "items": len(decisions),
        "routed_candidates": _build_routed_candidate_summary(decisions),
        "draft_ids": [proposal.mock_draft_id for proposal in proposals],
        "draft_proposals": [proposal.as_dict() for proposal in proposals],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_sns_topic_source_recheck_human(
    decisions: Sequence[SourceRecheckDecision],
    proposals: Sequence[DraftProposal] | None = None,
) -> str:
    draft_proposals = tuple(proposals or build_draft_proposals(decisions))
    counts = _route_counts(decisions)
    lines = [
        "SNS Topic Source Recheck Dry Run",
        "dry_run: true",
        f"items: {len(decisions)}",
    ]
    for route in _ROUTES:
        lines.append(f"{route}: {counts.get(route, 0)}")
    lines.append(f"draft_ids_count: {len(draft_proposals)}")

    if draft_proposals:
        lines.extend(["", "draft proposals"])
        for index, proposal in enumerate(draft_proposals[:5], start=1):
            lines.extend(
                [
                    f"{index}. topic_key: {proposal.topic_key}",
                    f"   mock_draft_id: {proposal.mock_draft_id}",
                    f"   topic_category: {proposal.topic_category}",
                    f"   title_hint: {proposal.title_hint}",
                    f"   source_urls: {', '.join(proposal.source_urls)}",
                ]
            )
    return "\n".join(lines) + "\n"


def _build_routed_candidate_summary(
    decisions: Sequence[SourceRecheckDecision],
) -> dict[str, dict[str, Any]]:
    grouped = {route: [] for route in _ROUTES}
    for decision in decisions:
        grouped.setdefault(decision.route, []).append(decision)

    return {
        route: {
            "count": len(grouped.get(route, [])),
            "sample": [
                {
                    "topic_key": decision.topic_key,
                    "topic_category": decision.topic_category,
                    "entities": list(decision.entities),
                    "reason": decision.reasons[0] if decision.reasons else "",
                }
                for decision in grouped.get(route, [])[:3]
            ],
        }
        for route in _ROUTES
    }


def _route_counts(decisions: Sequence[SourceRecheckDecision]) -> dict[str, int]:
    counts = Counter(decision.route for decision in decisions)
    return {route: counts.get(route, 0) for route in _ROUTES}


def _route_candidate(
    candidate: Mapping[str, Any],
    resolver_result: Mapping[str, Any],
) -> SourceRecheckDecision:
    topic_key = str(candidate.get("topic_key") or "").strip()
    topic_category = str(candidate.get("topic_category") or "").strip()
    entities = tuple(_sanitize_token_list(candidate.get("entities")))
    trend_terms = tuple(_sanitize_token_list(candidate.get("trend_terms")))
    signal_count = _coerce_int(candidate.get("signal_count"))
    fact_recheck_required = bool(candidate.get("fact_recheck_required", True))
    unsafe_flags = set(_coerce_string_list(candidate.get("unsafe_flags")))

    official_source_present = bool(resolver_result.get("official"))
    recent_news_overlap = bool(candidate.get("recent_news_overlap")) or bool(resolver_result.get("rss_match")) or bool(
        unsafe_flags & _DUPLICATE_FLAGS
    )
    rumor_risk = bool(resolver_result.get("rumor_risk"))
    source_urls = tuple(_collect_non_sns_source_urls(candidate, resolver_result))

    reject_reasons: list[str] = []
    hold_reasons: list[str] = []

    if bool(candidate.get("unsafe")):
        reject_reasons.append("unsafe_flag")
    if not topic_key or not topic_category:
        reject_reasons.append("unusable_candidate")
    if signal_count <= 0:
        reject_reasons.append("missing_signal_count")
    for flag in _REJECT_FLAGS:
        if flag in unsafe_flags:
            reject_reasons.append(flag)

    if topic_category in _SENSITIVE_TOPIC_CATEGORIES:
        hold_reasons.append("sensitive_topic_category")
    if rumor_risk:
        hold_reasons.append("resolver_rumor_risk")
    for flag in _HOLD_FLAGS:
        if flag in unsafe_flags:
            hold_reasons.append(flag)
    if _contains_sensitive_terms(topic_key, entities, trend_terms):
        hold_reasons.append("sensitive_keyword")

    route = ROUTE_CANDIDATE_ONLY
    reasons: tuple[str, ...]
    unsafe = False

    if reject_reasons:
        route = ROUTE_REJECT
        reasons = tuple(_dedupe_preserve(reject_reasons))
        unsafe = True
    elif hold_reasons:
        route = ROUTE_HOLD_SENSITIVE
        reasons = tuple(_dedupe_preserve(hold_reasons))
    elif recent_news_overlap:
        route = ROUTE_DUPLICATE_NEWS
        reasons = ("recent_news_overlap",)
    elif official_source_present and source_urls:
        route = ROUTE_DRAFT_READY
        reasons = ("confirmed_primary_source",)
    else:
        route = ROUTE_CANDIDATE_ONLY
        reasons = ("missing_confirmed_non_sns_source",)

    return SourceRecheckDecision(
        topic_key=topic_key,
        topic_category=topic_category,
        entities=entities,
        trend_terms=trend_terms,
        signal_count=signal_count,
        fact_recheck_required=fact_recheck_required,
        route=route,
        source_recheck_passed=route == ROUTE_DRAFT_READY,
        official_source_present=official_source_present,
        recent_news_overlap=recent_news_overlap,
        unsafe=unsafe,
        reasons=reasons,
        source_urls=source_urls,
    )


def _build_title_hint(decision: SourceRecheckDecision) -> str:
    entity = decision.entities[0] if decision.entities else "巨人"
    trend = decision.trend_terms[0] if decision.trend_terms else _DEFAULT_TRENDS.get(decision.topic_category, "動向")
    if entity == "巨人":
        return f"巨人の{trend}を公式情報ベースで整理"
    return f"{entity}の{trend}を公式情報ベースで整理"


def _build_lead_hint(decision: SourceRecheckDecision) -> str:
    entity = decision.entities[0] if decision.entities else _CATEGORY_LABELS.get(decision.topic_category, "話題")
    trend = decision.trend_terms[0] if decision.trend_terms else _DEFAULT_TRENDS.get(decision.topic_category, "動向")
    return (
        f"{entity}に関する{trend}について、球団公式・報道・RSSで確認できた事実のみを整理する。"
        "未確認のSNS反応や個別投稿の引用には依拠しない。"
    )


def _build_mock_draft_id(topic_key: str) -> str:
    digest = hashlib.sha256(topic_key.encode("utf-8")).hexdigest()[:16]
    return f"mock_draft_{digest}"


def _normalize_candidate(candidate: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(candidate, Mapping):
        payload = dict(candidate)
    elif hasattr(candidate, "as_dict"):
        payload = dict(candidate.as_dict())
    elif is_dataclass(candidate):
        payload = dict(asdict(candidate))
    elif hasattr(candidate, "__dict__"):
        payload = dict(vars(candidate))
    else:
        raise TypeError(f"unsupported candidate type: {type(candidate)!r}")

    payload["topic_key"] = str(payload.get("topic_key") or "").strip()
    payload["topic_category"] = str(payload.get("topic_category") or payload.get("category") or "").strip()
    payload["entities"] = _sanitize_token_list(payload.get("entities"))
    payload["trend_terms"] = _sanitize_token_list(payload.get("trend_terms"))
    payload["signal_count"] = _coerce_int(payload.get("signal_count"))
    payload["fact_recheck_required"] = bool(payload.get("fact_recheck_required", True))
    payload["unsafe_flags"] = _coerce_string_list(payload.get("unsafe_flags"))
    return payload


def _normalize_resolver_result(value: Mapping[str, Any] | None) -> dict[str, Any]:
    mapping = dict(value or {})
    mapping["official"] = bool(mapping.get("official"))
    mapping["rss_match"] = bool(mapping.get("rss_match"))
    mapping["rumor_risk"] = bool(mapping.get("rumor_risk"))
    return mapping


def _collect_non_sns_source_urls(
    candidate: Mapping[str, Any],
    resolver_result: Mapping[str, Any],
) -> list[str]:
    values: list[str] = []
    for key in (
        "source_urls",
        "official_source_urls",
        "report_urls",
        "rss_urls",
        "confirmed_source_urls",
    ):
        values.extend(_coerce_string_list(resolver_result.get(key)))
        values.extend(_coerce_string_list(candidate.get(key)))

    filtered: list[str] = []
    for value in values:
        if _is_sns_url(value):
            continue
        filtered.append(value)
    return _dedupe_preserve(filtered)


def _contains_sensitive_terms(topic_key: str, entities: Sequence[str], trend_terms: Sequence[str]) -> bool:
    haystack = " ".join([topic_key, *entities, *trend_terms])
    return any(keyword in haystack for keyword in _SENSITIVE_KEYWORDS)


def _sanitize_token_list(value: Any) -> list[str]:
    cleaned: list[str] = []
    for item in _coerce_string_list(value):
        token = _sanitize_text_fragment(item)
        if not token or _looks_like_account_or_url(token):
            continue
        cleaned.append(token)
    return _dedupe_preserve(cleaned)


def _sanitize_text_fragment(value: str) -> str:
    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
    text = _URL_RE.sub("", text)
    text = _HANDLE_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip(" 　")


def _looks_like_account_or_url(value: str) -> bool:
    return value.startswith("@") or "http://" in value or "https://" in value


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        rows: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                rows.append(text)
        return rows
    return []


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe_preserve(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _is_sns_url(value: str) -> bool:
    parsed = urlparse(str(value))
    if parsed.scheme not in {"http", "https"}:
        return True
    host = parsed.netloc.lower()
    return host in {
        "x.com",
        "www.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
        "t.co",
    }


def _default_resolver(candidate: Mapping[str, Any]) -> dict[str, Any]:
    del candidate
    return {"official": False, "rss_match": False, "rumor_risk": False, "source_urls": []}
