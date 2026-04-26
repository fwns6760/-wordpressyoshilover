"""Read-only SNS topic fire intake.

This module clusters fan-reaction signals into topic seeds without storing or
re-emitting raw SNS post text, account names, handles, or URLs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence


SOURCE_TIER_REACTION = "reaction"
ROUTE_SOURCE_RECHECK = "source_recheck"
ROUTE_REJECT = "reject"

MIN_SIGNAL_COUNT = 3
RSS_OVERLAP_THRESHOLD = 0.74
MAX_ENTITIES = 4
MAX_TREND_TERMS = 5

_CATEGORIES = (
    "player",
    "manager_strategy",
    "bullpen",
    "lineup",
    "farm",
    "injury_return",
    "transaction",
    "acquisition_trade",
)

_CATEGORY_ALIASES = {
    "player": "player",
    "manager": "manager_strategy",
    "manager_strategy": "manager_strategy",
    "strategy": "manager_strategy",
    "bullpen": "bullpen",
    "lineup": "lineup",
    "farm": "farm",
    "injury": "injury_return",
    "injury_return": "injury_return",
    "return": "injury_return",
    "transaction": "transaction",
    "roster": "transaction",
    "acquisition": "acquisition_trade",
    "trade": "acquisition_trade",
    "acquisition_trade": "acquisition_trade",
}

_CATEGORY_PATTERNS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "player": (
        ("フォーム", re.compile(r"(フォーム|打撃フォーム|投球フォーム|修正)")),
        ("状態", re.compile(r"(状態|調子|復調|不振|好調)")),
        ("起用", re.compile(r"(起用|役割|序列|評価)")),
        ("守備", re.compile(r"(守備|コンバート|ポジション)")),
    ),
    "manager_strategy": (
        ("起用方針", re.compile(r"(采配|起用方針|方針|狙い|勝負手|左右病)")),
        ("競争", re.compile(r"(競争|固定しない|我慢|見極め)")),
        ("ベンチワーク", re.compile(r"(ベンチワーク|作戦|継投判断)")),
    ),
    "bullpen": (
        ("ブルペン", re.compile(r"(ブルペン|中継ぎ|救援|リリーフ)")),
        ("勝ちパ", re.compile(r"(抑え|守護神|勝ちパ|8回|9回|セットアッパー)")),
        ("継投", re.compile(r"(継投|回またぎ|火消し)")),
    ),
    "lineup": (
        ("スタメン", re.compile(r"(スタメン|オーダー|打線)")),
        ("打順", re.compile(r"(打順|1番|2番|3番|4番|5番|クリーンアップ)")),
        ("守備位置", re.compile(r"(先発マスク|一塁|二塁|三塁|遊撃|左翼|中堅|右翼)")),
    ),
    "farm": (
        ("二軍", re.compile(r"(二軍|3軍|ファーム|イースタン|ジャイアンツ球場)")),
        ("若手", re.compile(r"(若手|育成|育成契約|昇格候補|再調整)")),
        ("実戦復帰", re.compile(r"(マルチヒット|実戦復帰|調整登板|教育リーグ)")),
    ),
    "injury_return": (
        ("故障", re.compile(r"(離脱|負傷|故障|診断|別メニュー|違和感|コンディション)")),
        ("復帰", re.compile(r"(復帰|復帰時期|復帰プラン|リハビリ|復活)")),
        ("欠場", re.compile(r"(欠場|抹消|様子見)")),
    ),
    "transaction": (
        ("登録", re.compile(r"(登録|抹消|昇格|降格|公示|支配下|入れ替え)")),
        ("公示", re.compile(r"(出場選手登録|登録抹消|一軍合流)")),
    ),
    "acquisition_trade": (
        ("補強", re.compile(r"(補強|獲得|調査|新外国人)")),
        ("トレード", re.compile(r"(トレード|FA|移籍|人的補償)")),
    ),
}

_DEFAULT_TREND_TERMS = {
    "player": ("選手論",),
    "manager_strategy": ("采配論",),
    "bullpen": ("救援論",),
    "lineup": ("打線論",),
    "farm": ("二軍論",),
    "injury_return": ("復帰論",),
    "transaction": ("公示論",),
    "acquisition_trade": ("補強論",),
}

_MANAGER_OR_COACH_ROLES = frozenset({"manager", "coach"})
_PITCHER_POSITIONS = frozenset({"投手"})

_URL_RE = re.compile(r"https?://\S+")
_HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,32}")
_HTML_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|#39);")
_TOKEN_RE = re.compile(r"[一-龥々]{2,}|[ぁ-ん]{2,}|[ァ-ヴー]{2,}|[A-Za-z0-9]{2,}")
_QUOTE_RE = re.compile(r"[「『\"]([^」』\"]+)[」』\"]")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?／/・,，、\s]+")

_INSULT_TERMS = (
    "死ね",
    "しね",
    "消えろ",
    "クソ",
    "くそ",
    "ゴミ",
    "ごみ",
    "バカ",
    "ばか",
    "アホ",
    "無能",
    "害悪",
    "戦犯",
    "晒し",
    "晒せ",
)
_ACCOUNT_EXPOSURE_TERMS = (
    "アカウント",
    "垢",
    "フォロワー",
    "引用元",
    "この人",
    "あの人",
    "鍵垢",
)
_PRIVATE_OR_FAMILY_TERMS = (
    "家族",
    "嫁",
    "妻",
    "彼女",
    "子供",
    "息子",
    "娘",
    "自宅",
    "住所",
    "学校",
    "不倫",
)
_RUMOR_TERMS = (
    "らしい",
    "かも",
    "っぽい",
    "真偽不明",
    "未確認",
    "リーク",
    "噂",
)
_SENSITIVE_ASSERTION_PATTERNS = (
    re.compile(r"(登録|抹消|昇格|降格|トレード|FA|移籍|獲得|離脱|負傷|故障|診断|復帰)(?:した|したらしい|決定|確定|濃厚|へ)"),
    re.compile(r"(登録された|抹消された|復帰した|離脱した|獲得する|移籍する)"),
)
_SENSITIVE_EXPECTATION_PATTERNS = (
    re.compile(r"(してほしい|見たい|待望|候補|争い|どうなる|あるか|ありそう|かもしれない)"),
)
_DIRECT_QUOTE_HINTS = (
    "って言ってた",
    "とのこと",
    "って書いてた",
    "この一言",
    "発言そのまま",
)

_STOP_TOKENS = frozenset(
    {
        "巨人",
        "ジャイアンツ",
        "読売",
        "今日",
        "今回",
        "これ",
        "それ",
        "また",
        "なんか",
        "みたい",
        "けど",
        "ので",
        "から",
        "ため",
        "話題",
        "反応",
        "ファン",
        "SNS",
        "Yahoo",
        "リアルタイム",
    }
)


@dataclass(frozen=True)
class SNSTopicFireCandidate:
    topic_key: str
    category: str
    entities: tuple[str, ...]
    trend_terms: tuple[str, ...]
    signal_count: int
    source_tier: str
    fact_recheck_required: bool
    route_hint: str
    unsafe_flags: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entities"] = list(self.entities)
        payload["trend_terms"] = list(self.trend_terms)
        payload["unsafe_flags"] = list(self.unsafe_flags)
        return payload


@dataclass(frozen=True)
class _RosterAlias:
    canonical_name: str
    alias: str
    role: str
    position: str


@dataclass(frozen=True)
class _SignalFeatures:
    category: str
    entities: tuple[str, ...]
    trend_terms: tuple[str, ...]
    signal_text: str
    signal_tokens: frozenset[str]
    has_quote_like: bool
    account_exposure_risk: bool
    private_or_family_risk: bool
    rumor_risk: bool
    inflammatory_risk: bool
    sensitive_assertion_risk: bool
    direct_quote_dependent: bool


def evaluate_sns_topic_fire_batch(
    signals: Sequence[Mapping[str, Any]],
    rss_index: Sequence[Mapping[str, Any]] = (),
) -> tuple[SNSTopicFireCandidate, ...]:
    bucketed: dict[tuple[str, str, str], list[_SignalFeatures]] = defaultdict(list)
    for signal in signals:
        features = _extract_signal_features(signal)
        if not features.category:
            continue
        primary_entity = features.entities[0] if features.entities else "generic"
        primary_trend = features.trend_terms[0] if features.trend_terms else "generic"
        trend_bucket = "generic" if primary_entity != "generic" else primary_trend
        bucketed[(features.category, primary_entity, trend_bucket)].append(features)

    candidates = [
        _build_candidate(category, entity, items, rss_index)
        for (category, entity, _trend), items in bucketed.items()
    ]
    candidates.sort(key=lambda item: (-item.signal_count, item.route_hint, item.topic_key))
    return tuple(candidates)


def dump_sns_topic_fire_report(
    candidates: Sequence[SNSTopicFireCandidate],
    *,
    fmt: str = "json",
) -> str:
    if fmt == "human":
        return render_sns_topic_fire_human(candidates)

    payload = {
        "items": len(candidates),
        "routes": _route_counts(candidates),
        "results": [candidate.as_dict() for candidate in candidates],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_sns_topic_fire_human(candidates: Sequence[SNSTopicFireCandidate]) -> str:
    counts = _route_counts(candidates)
    lines = [
        "SNS Topic Fire Intake Dry Run",
        f"items: {len(candidates)}",
        f"source_recheck: {counts.get(ROUTE_SOURCE_RECHECK, 0)}",
        f"reject: {counts.get(ROUTE_REJECT, 0)}",
    ]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                "",
                f"candidate {index}",
                f"topic_key: {candidate.topic_key}",
                f"category: {candidate.category}",
                f"entities: {', '.join(candidate.entities) if candidate.entities else '-'}",
                f"trend_terms: {', '.join(candidate.trend_terms) if candidate.trend_terms else '-'}",
                f"signal_count: {candidate.signal_count}",
                f"source_tier: {candidate.source_tier}",
                f"fact_recheck_required: {'true' if candidate.fact_recheck_required else 'false'}",
                f"route_hint: {candidate.route_hint}",
                f"unsafe_flags: {', '.join(candidate.unsafe_flags) if candidate.unsafe_flags else '-'}",
            ]
        )
    return "\n".join(lines) + "\n"


def _route_counts(candidates: Sequence[SNSTopicFireCandidate]) -> dict[str, int]:
    counts = Counter(candidate.route_hint for candidate in candidates)
    return {
        ROUTE_SOURCE_RECHECK: counts.get(ROUTE_SOURCE_RECHECK, 0),
        ROUTE_REJECT: counts.get(ROUTE_REJECT, 0),
    }


def _build_candidate(
    category: str,
    primary_entity: str,
    items: Sequence[_SignalFeatures],
    rss_index: Sequence[Mapping[str, Any]],
) -> SNSTopicFireCandidate:
    entity_counter = Counter(entity for item in items for entity in item.entities)
    trend_counter = Counter(term for item in items for term in item.trend_terms)

    entities = tuple(
        entity
        for entity, _ in entity_counter.most_common(MAX_ENTITIES)
        if not _looks_like_account_or_url(entity)
    )
    trend_terms = tuple(term for term, _ in trend_counter.most_common(MAX_TREND_TERMS))
    if not trend_terms:
        trend_terms = tuple(_DEFAULT_TREND_TERMS.get(category, ("generic_trend",)))

    unsafe_flags: list[str] = []
    if any(item.inflammatory_risk for item in items):
        unsafe_flags.append("slur_or_harassment")
    if any(item.account_exposure_risk for item in items):
        unsafe_flags.append("account_exposure_required")
    if any(item.private_or_family_risk for item in items) or any(item.rumor_risk for item in items):
        unsafe_flags.append("private_family_or_rumor")
    if any(item.sensitive_assertion_risk for item in items):
        unsafe_flags.append("sns_only_sensitive_assertion")
    if any(item.direct_quote_dependent for item in items):
        unsafe_flags.append("direct_quote_required")
    if len(items) < MIN_SIGNAL_COUNT:
        unsafe_flags.append("too_few_matching_signals")
    if _has_high_rss_overlap(category, entities, trend_terms, rss_index):
        unsafe_flags.append("recent_news_overlap")

    route_hint = ROUTE_REJECT if unsafe_flags else ROUTE_SOURCE_RECHECK
    topic_key = _build_topic_key(category, entities or (primary_entity,), trend_terms)
    return SNSTopicFireCandidate(
        topic_key=topic_key,
        category=category,
        entities=entities,
        trend_terms=trend_terms,
        signal_count=len(items),
        source_tier=SOURCE_TIER_REACTION,
        fact_recheck_required=True,
        route_hint=route_hint,
        unsafe_flags=tuple(_dedupe_preserve(unsafe_flags)),
    )


def _extract_signal_features(signal: Mapping[str, Any]) -> _SignalFeatures:
    raw_text = _first_non_empty(signal, "text", "summary", "displayText", "title", "body")
    text = _sanitize_text(raw_text)
    explicit_entities = _coerce_string_list(signal.get("entities"))
    explicit_trends = _coerce_string_list(signal.get("trend_terms"))

    roster_entities = _extract_roster_entities(text)
    entities = tuple(_dedupe_preserve(explicit_entities + roster_entities))

    category = _normalize_category_hint(signal.get("category") or signal.get("category_hint"))
    if not category:
        category = _infer_category(text, entities)

    trend_terms = tuple(
        _dedupe_preserve(
            _sanitize_term(term) for term in (explicit_trends + _extract_trend_terms(text, category))
        )
    )
    trend_terms = tuple(term for term in trend_terms if term)
    if not trend_terms and category:
        trend_terms = tuple(_DEFAULT_TREND_TERMS.get(category, ("generic_trend",)))

    signal_tokens = frozenset(_tokenize(text))
    has_quote_like = bool(_QUOTE_RE.search(text))
    sensitive_assertion_risk = bool(signal.get("sensitive_assertion")) or _has_sensitive_assertion(text, category)
    direct_quote_dependent = bool(signal.get("requires_direct_quote")) or _is_direct_quote_dependent(text, trend_terms)

    return _SignalFeatures(
        category=category,
        entities=entities,
        trend_terms=trend_terms,
        signal_text=text,
        signal_tokens=signal_tokens,
        has_quote_like=has_quote_like,
        account_exposure_risk=_has_account_exposure_risk(signal, raw_text),
        private_or_family_risk=bool(signal.get("private_or_family")) or _contains_any(raw_text, _PRIVATE_OR_FAMILY_TERMS),
        rumor_risk=bool(signal.get("rumor")) or (_contains_any(raw_text, _RUMOR_TERMS) and not category in {"player", "bullpen", "lineup", "farm"}),
        inflammatory_risk=bool(signal.get("inflammatory")) or _contains_any(raw_text, _INSULT_TERMS),
        sensitive_assertion_risk=sensitive_assertion_risk,
        direct_quote_dependent=direct_quote_dependent,
    )


def _normalize_category_hint(value: Any) -> str:
    key = _normalize_ascii(str(value or ""))
    return _CATEGORY_ALIASES.get(key, "")


def _infer_category(text: str, entities: Sequence[str]) -> str:
    scores: dict[str, int] = {}
    for category, patterns in _CATEGORY_PATTERNS.items():
        score = 0
        for _, pattern in patterns:
            if pattern.search(text):
                score += 2
        if score:
            scores[category] = score

    roster_roles = {_roster_role(entity) for entity in entities}
    roster_positions = {_roster_position(entity) for entity in entities}
    if any(role in _MANAGER_OR_COACH_ROLES for role in roster_roles):
        scores["manager_strategy"] = scores.get("manager_strategy", 0) + 2
    if any(position in _PITCHER_POSITIONS for position in roster_positions) and re.search(r"(継投|中継ぎ|抑え|守護神|勝ちパ)", text):
        scores["bullpen"] = scores.get("bullpen", 0) + 3
    if entities:
        scores["player"] = scores.get("player", 0) + 1

    if not scores:
        return "player" if entities else ""

    priority = {
        "injury_return": 90,
        "transaction": 85,
        "acquisition_trade": 80,
        "bullpen": 70,
        "lineup": 65,
        "farm": 60,
        "manager_strategy": 55,
        "player": 40,
    }
    return max(scores, key=lambda category: (scores[category], priority.get(category, 0), category))


def _extract_trend_terms(text: str, category: str) -> list[str]:
    terms: list[str] = []
    for label, pattern in _CATEGORY_PATTERNS.get(category, ()):
        if pattern.search(text):
            terms.append(label)

    if category == "lineup" and re.search(r"(坂本|岡本|丸|吉川|門脇|浅野|甲斐).*(打順|スタメン|オーダー)", text):
        terms.append("主力打順")
    if category == "farm" and re.search(r"(昇格|一軍)", text):
        terms.append("昇格候補")
    if category == "player" and re.search(r"(打順|スタメン|オーダー)", text):
        terms.append("打順")
    if category == "manager_strategy" and re.search(r"(起用|競争)", text):
        terms.append("起用判断")
    if category == "bullpen" and re.search(r"(8回|9回|終盤)", text):
        terms.append("終盤起用")
    if category == "injury_return" and re.search(r"(復帰|リハビリ)", text):
        terms.append("復帰時期")
    if category == "transaction" and re.search(r"(登録|抹消)", text):
        terms.append("登録抹消")
    if category == "acquisition_trade" and re.search(r"(補強|調査)", text):
        terms.append("補強候補")

    return _dedupe_preserve(terms)


def _has_sensitive_assertion(text: str, category: str) -> bool:
    if category not in {"injury_return", "transaction", "acquisition_trade"}:
        return False
    if any(pattern.search(text) for pattern in _SENSITIVE_EXPECTATION_PATTERNS):
        return False
    return any(pattern.search(text) for pattern in _SENSITIVE_ASSERTION_PATTERNS)


def _is_direct_quote_dependent(text: str, trend_terms: Sequence[str]) -> bool:
    quotes = _QUOTE_RE.findall(text)
    if not quotes:
        return False
    if any(hint in text for hint in _DIRECT_QUOTE_HINTS):
        return True
    non_quote_terms = [term for term in trend_terms if not term.endswith("view")]
    stripped = _QUOTE_RE.sub(" ", text)
    token_count = len(_tokenize(stripped))
    return not non_quote_terms and token_count <= 4


def _has_high_rss_overlap(
    category: str,
    entities: Sequence[str],
    trend_terms: Sequence[str],
    rss_index: Sequence[Mapping[str, Any]],
) -> bool:
    cluster_tokens = set(_tokenize(" ".join([category, *entities, *trend_terms])))
    if not cluster_tokens:
        return False
    for item in rss_index:
        haystack = " ".join(
            str(item.get(field) or "")
            for field in ("title", "summary", "description", "body", "excerpt")
        )
        if not haystack:
            continue
        news_tokens = set(_tokenize(_sanitize_text(haystack)))
        if not news_tokens:
            continue
        overlap = len(cluster_tokens & news_tokens) / max(1, len(cluster_tokens))
        if overlap >= RSS_OVERLAP_THRESHOLD:
            return True
    return False


def _build_topic_key(category: str, entities: Sequence[str], trend_terms: Sequence[str]) -> str:
    entity_slug = _slug_part(next((value for value in entities if value), "generic"))
    trend_slug = _slug_part(next((value for value in trend_terms if value), "topic"))
    return f"{category}_{entity_slug}_{trend_slug}"


def _sanitize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = _HTML_ENTITY_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _HANDLE_RE.sub(" ", text)
    text = text.replace("START", " ").replace("END", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sanitize_term(value: str) -> str:
    cleaned = _sanitize_text(value)
    cleaned = cleaned.strip("・-_/ ")
    return cleaned[:40]


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(text or ""):
        normalized = token.strip().lower()
        if not normalized or normalized in _STOP_TOKENS:
            continue
        tokens.append(normalized)
    return tokens


def _slug_part(value: str) -> str:
    cleaned = _sanitize_text(value)
    cleaned = re.sub(r"[^\w一-龥々ぁ-んァ-ヴー]+", "_", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "generic"


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _has_account_exposure_risk(signal: Mapping[str, Any], text: str) -> bool:
    if bool(signal.get("requires_account_exposure")):
        return True
    if _contains_any(text, _ACCOUNT_EXPOSURE_TERMS):
        return True
    return bool(_HANDLE_RE.search(text))


def _first_non_empty(signal: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = signal.get(key)
        if value:
            return str(value)
    return ""


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item).strip() for item in value if str(item).strip() and not _looks_like_account_or_url(str(item))]
    return []


def _looks_like_account_or_url(value: str) -> bool:
    return bool(_HANDLE_RE.search(value or "") or _URL_RE.search(value or "") or "x.com/" in (value or ""))


def _dedupe_preserve(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _load_roster_aliases() -> tuple[_RosterAlias, ...]:
    path = Path(__file__).resolve().parent.parent / "config" / "giants_roster.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    aliases: list[_RosterAlias] = []
    for item in payload:
        canonical_name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip()
        position = str(item.get("position") or "").strip()
        for alias in item.get("aliases") or [canonical_name]:
            alias_text = str(alias or "").strip()
            if alias_text:
                aliases.append(
                    _RosterAlias(
                        canonical_name=canonical_name,
                        alias=alias_text,
                        role=role,
                        position=position,
                    )
                )
    aliases.sort(key=lambda item: len(item.alias), reverse=True)
    return tuple(aliases)


_ROSTER_ALIASES = _load_roster_aliases()
_ROSTER_BY_CANONICAL = {item.canonical_name: item for item in _ROSTER_ALIASES}


def _extract_roster_entities(text: str) -> list[str]:
    found: list[str] = []
    for entry in _ROSTER_ALIASES:
        if entry.alias and entry.alias in text:
            found.append(entry.canonical_name)
    return _dedupe_preserve(found)


def _roster_role(entity: str) -> str:
    entry = _ROSTER_BY_CANONICAL.get(entity)
    return entry.role if entry else ""


def _roster_position(entity: str) -> str:
    entry = _ROSTER_BY_CANONICAL.get(entity)
    return entry.position if entry else ""


def _normalize_ascii(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().lower().replace(" ", "_")
