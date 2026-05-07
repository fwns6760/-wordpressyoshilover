"""NOMOTOKE-RSS-CARD-001A — RSS-to-nomotoke-card router (pure function).

Purpose
=======

Classify an existing RSS entry to one of the SHAPE-001 nomotoke card templates
**without** Gemini, **without** WP I/O, and **without** rss_fetcher.py touch.
Used only from the dry-run CLI and tests.

Quality boundary (LOCKED, immovable in 001A)
============================================

RSS-only OK (router may emit):
    - nomotoke_card_short_news_url_v1   — fallback, source_url + source_name + title
    - nomotoke_card_manager_comment_v1  — manager_name in allowlist + quote_short
    - nomotoke_card_player_comment_v1   — player_name + quote_short
    - nomotoke_card_pregame_pitcher_v1  — "予告先発" keyword + pitcher_pair extracted + stale ≤ 36h

RSS-only NG (router NEVER emits — there is intentionally no branch):
    - nomotoke_card_lineup_v1
    - nomotoke_card_postgame_v1
    - nomotoke_card_live_at_bats_v1
    - nomotoke_card_player_stats_v1
    - nomotoke_card_broadcast_v1
    - nomotoke_card_official_notice_v1
    - nomotoke_card_video_v1   (until YouTube channel RSS source is configured)

Hard rules
==========

- No HTTP. No I/O. No Gemini. No WP. No rss_fetcher.py import at runtime.
- Required-facts gate: missing fields → skip with explicit reason. Never AI-fill.
- ``next_recommended_templates`` MUST exclude blocked templates even if their
  fixtures hit. low/impossible templates are intentionally absent from the
  template registry below.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


ENABLE_FLAG = "ENABLE_NOMOTOKE_RSS_CARD_ROUTING"


# ---------------------------------------------------------------------------
# Template keys (RSS-only OK only — RSS-only NG keys are deliberately NOT
# referenced from this module so that no code path can construct them.)
# ---------------------------------------------------------------------------

TEMPLATE_KEY_SHORT_NEWS_URL = "nomotoke_card_short_news_url_v1"
TEMPLATE_KEY_MANAGER_COMMENT = "nomotoke_card_manager_comment_v1"
TEMPLATE_KEY_PLAYER_COMMENT = "nomotoke_card_player_comment_v1"
TEMPLATE_KEY_PREGAME_PITCHER = "nomotoke_card_pregame_pitcher_v1"


RSS_ONLY_ALLOWED_TEMPLATES: Tuple[str, ...] = (
    TEMPLATE_KEY_SHORT_NEWS_URL,
    TEMPLATE_KEY_MANAGER_COMMENT,
    TEMPLATE_KEY_PLAYER_COMMENT,
    TEMPLATE_KEY_PREGAME_PITCHER,
)


RSS_ONLY_BLOCKED_TEMPLATES: Tuple[str, ...] = (
    "nomotoke_card_lineup_v1",
    "nomotoke_card_postgame_v1",
    "nomotoke_card_live_at_bats_v1",
    "nomotoke_card_player_stats_v1",
    "nomotoke_card_broadcast_v1",
    "nomotoke_card_official_notice_v1",
    "nomotoke_card_video_v1",
)


# Quality ceiling per template (LOCKED).
QUALITY_CEILING_BY_TEMPLATE: Dict[str, Dict[str, Any]] = {
    TEMPLATE_KEY_SHORT_NEWS_URL: {
        "rss_only_quality": "high",
        "reason": "URL + title + source_name のみで成立。RSS で全部揃う。",
        "required_external_data": [],
        "allow_rss_only": True,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    TEMPLATE_KEY_MANAGER_COMMENT: {
        "rss_only_quality": "medium",
        "reason": "「{監督名}「{quote}」」regex で拾える。topic 推定は難。allowlist + quote_short 必須。",
        "required_external_data": [],
        "allow_rss_only": True,
        "allow_manual_intake": True,
        "allow_structured_data": False,
    },
    TEMPLATE_KEY_PLAYER_COMMENT: {
        "rss_only_quality": "medium",
        "reason": "「{選手名}「{quote}」」regex 抽出。player_name は曖昧性あり。quote_short 必須。",
        "required_external_data": [],
        "allow_rss_only": True,
        "allow_manual_intake": True,
        "allow_structured_data": False,
    },
    TEMPLATE_KEY_PREGAME_PITCHER: {
        "rss_only_quality": "medium",
        "reason": "「予告先発」keyword + 投手ペア regex。stale 36h 越えは skip。",
        "required_external_data": [],
        "allow_rss_only": True,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    "nomotoke_card_lineup_v1": {
        "rss_only_quality": "impossible",
        "reason": "5 列スタメン表(打順/守備/選手名/打率/防御率)が RSS title/summary に存在せず。",
        "required_external_data": ["NPB公式 lineup", "球団公式 lineup", "一球速報"],
        "allow_rss_only": False,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    "nomotoke_card_postgame_v1": {
        "rss_only_quality": "low",
        "reason": "スコアは headline regex で抽出可。ただし inning_score / at_bats_rows / pitching_rows が RSS にない。full card は無理。",
        "required_external_data": ["NPB公式 score", "Yahoo score"],
        "allow_rss_only": False,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    "nomotoke_card_live_at_bats_v1": {
        "rss_only_quality": "impossible",
        "reason": "試合中の at_bats_rows / pitching_rows が RSS に存在せず。",
        "required_external_data": ["一球速報", "公式 score 構造データ"],
        "allow_rss_only": False,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    "nomotoke_card_player_stats_v1": {
        "rss_only_quality": "impossible",
        "reason": "成績表(打率/試合/打席/本塁打/打点/OPS or 投手 stats)が RSS にない。",
        "required_external_data": ["NPB公式 stats", "DELTA"],
        "allow_rss_only": False,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    "nomotoke_card_broadcast_v1": {
        "rss_only_quality": "low",
        "reason": "5 列放送表(媒体/CH/時間/解説/実況)が RSS にない。",
        "required_external_data": ["球団公式放送予定", "番組表 HTML"],
        "allow_rss_only": False,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    "nomotoke_card_official_notice_v1": {
        "rss_only_quality": "low",
        "reason": "NPB公式 X bridge から「登録: X / 抹消: Y」regex 抽出は不安定。登録人数・残り枠は無理。",
        "required_external_data": ["NPB公式公示 HTML"],
        "allow_rss_only": False,
        "allow_manual_intake": True,
        "allow_structured_data": True,
    },
    "nomotoke_card_video_v1": {
        "rss_only_quality": "impossible",
        "reason": "現状 config/rss_sources.json に YouTube channel RSS 未登録。supply ゼロ。YouTube RSS 追加で 'high' に昇格可。",
        "required_external_data": ["YouTube channel RSS の rss_sources.json への追加"],
        "allow_rss_only": False,
        "allow_manual_intake": True,
        "allow_structured_data": False,
    },
}


# ---------------------------------------------------------------------------
# Source tier mapping
# ---------------------------------------------------------------------------

_TIER_1_NAMES = frozenset(
    {
        "TokyoGiants",
        "yomiuri_giants",
        "hochi_giants",
        "Sanspo_Giants",
        "巨人公式X",
        "読売ジャイアンツX",
        "スポーツ報知巨人班X",
        "サンスポ巨人X",
        "スポーツ報知 巨人",
        "日刊スポーツ 巨人",
        "Full-Count 巨人",
    }
)

_TIER_2_NAMES = frozenset(
    {
        "hochi_baseball",
        "npb",
        "報知野球X",
        "NPB公式X",
    }
)

_TIER_3_NAMES = frozenset(
    {
        "SportsHochi",
        "nikkansports",
        "SponichiYakyu",
        "ベースボールキング",
        "スポーツ報知X",
        "日刊スポーツX",
        "スポニチ野球記者X",
    }
)


def source_tier(source_name: str) -> int:
    """Return tier (1/2/3) or 0 if unknown."""
    name = (source_name or "").strip()
    if name in _TIER_1_NAMES:
        return 1
    if name in _TIER_2_NAMES:
        return 2
    if name in _TIER_3_NAMES:
        return 3
    return 0


# ---------------------------------------------------------------------------
# Manager allowlist (Giants 2026 only)
# ---------------------------------------------------------------------------

MANAGER_NAME_ALLOWLIST: Tuple[str, ...] = ("阿部",)


# ---------------------------------------------------------------------------
# Misc constants
# ---------------------------------------------------------------------------

QUOTE_SHORT_MAX_CHARS = 100
PREGAME_STALE_HOURS = 36

GIANTS_KEYWORDS: Tuple[str, ...] = (
    "巨人",
    "ジャイアンツ",
    "Giants",
    "GIANTS",
    "東京ドーム",
    "阿部監督",
    "阿部慎之助",
    "yomiuri_giants",
    "TokyoGiants",
)

NOMOTOKE_FORBIDDEN_PHRASINGS: Tuple[str, ...] = (
    "ｶｯﾀｶﾞﾈｰ",
    "ﾏｹﾀｶﾞﾈｰ",
    "ｶﾞﾈｰ",
    "ﾄﾞﾝﾏｲ",
)

_TRACKING_PARAM_KEYS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "ref",
        "ref_src",
        "source",
        "_src",
        "share",
        "s",
        "t",
    }
)

_UNSAFE_URL_RE = re.compile(r"^(?:javascript|data|file|vbscript):", re.IGNORECASE)


# Closed skip_reason taxonomy emitted by the router.
SKIP_REASON_TAXONOMY: Tuple[str, ...] = (
    "unsafe_url",
    "missing_source_url",
    "missing_source_name",
    "missing_title",
    "not_giants_related",
    "stale_for_template",
    "manager_not_in_allowlist",
    "quote_too_long",
    "quote_multiline_not_allowed",
    "insufficient_required_facts:pregame_pitcher:pitcher_pair",
    "insufficient_required_facts:manager_comment:quote_short",
    "insufficient_required_facts:player_comment:player_name",
    "insufficient_required_facts:player_comment:quote_short",
    "insufficient_required_facts:short_news_url:title",
    "insufficient_required_facts:short_news_url:source_url",
    "insufficient_required_facts:short_news_url:source_name",
)


# ---------------------------------------------------------------------------
# Flag gating (placeholder; router is invoked directly from CLI/tests)
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Return True iff ENABLE_NOMOTOKE_RSS_CARD_ROUTING env is truthy."""
    raw = os.environ.get(ENABLE_FLAG, "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# URL utilities
# ---------------------------------------------------------------------------


def _is_unsafe_url(url: str) -> bool:
    return bool(_UNSAFE_URL_RE.match((url or "").strip()))


def normalize_canonical_url(url: str) -> str:
    """Normalize a URL for dedupe.

    - drop fragment
    - strip tracking params
    - x.com -> twitter.com
    - lowercase scheme + host
    - strip trailing slash on non-root paths
    - reject unsafe schemes (returns "")
    """
    if not url or not isinstance(url, str):
        return ""
    raw = url.strip()
    if not raw or _is_unsafe_url(raw):
        return ""
    try:
        p = urlparse(raw)
    except Exception:
        return ""
    if p.scheme.lower() not in ("http", "https"):
        return ""
    netloc = (p.netloc or "").lower()
    netloc = re.sub(r"^(www\.|mobile\.)?x\.com$", "twitter.com", netloc)
    netloc = re.sub(r"^www\.twitter\.com$", "twitter.com", netloc)
    netloc = re.sub(r"^mobile\.twitter\.com$", "twitter.com", netloc)
    qs = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAM_KEYS
    ]
    new_q = urlencode(qs)
    path = p.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((p.scheme.lower(), netloc, path, "", new_q, ""))


def _hash_canonical(canonical: str) -> str:
    if not canonical:
        return ""
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Giants relevance
# ---------------------------------------------------------------------------


def is_giants_relevant(title: str, summary: str, source_name: str) -> bool:
    """Tier-1 source grants automatic relevance; otherwise keyword check."""
    if source_tier(source_name) == 1:
        return True
    text = f"{title or ''}\n{summary or ''}\n{source_name or ''}"
    return any(kw in text for kw in GIANTS_KEYWORDS)


# ---------------------------------------------------------------------------
# Forbidden phrasing guard (defense in depth)
# ---------------------------------------------------------------------------


def _check_nomotoke_phrasing(*texts: str) -> None:
    for t in texts:
        if not t:
            continue
        for bad in NOMOTOKE_FORBIDDEN_PHRASINGS:
            if bad in t:
                raise ValueError("nomotoke_phrasing_detected")


# ---------------------------------------------------------------------------
# Stale check
# ---------------------------------------------------------------------------


_STALE_HOURS_BY_TEMPLATE: Dict[str, int] = {
    TEMPLATE_KEY_PREGAME_PITCHER: PREGAME_STALE_HOURS,
}


def _parse_iso_or_rfc822(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            d = datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d
        except ValueError:
            continue
    try:
        d = parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def is_stale(
    published_at_iso: str,
    template_key: str,
    *,
    now: Optional[datetime] = None,
) -> bool:
    cap = _STALE_HOURS_BY_TEMPLATE.get(template_key)
    if cap is None:
        return False
    pub = _parse_iso_or_rfc822(published_at_iso)
    if pub is None:
        return False
    n = now if now is not None else datetime.now(timezone.utc)
    return (n - pub).total_seconds() > cap * 3600


def _date_label_from_iso(iso: str) -> str:
    d = _parse_iso_or_rfc822(iso)
    if d is None:
        return ""
    jst = d.astimezone(timezone(timedelta(hours=9)))
    return jst.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Regex extractors
# ---------------------------------------------------------------------------


# 「[巨人・]?{監督名}監督「{quote}」」 — strict pattern.
_MANAGER_QUOTE_RE = re.compile(
    r"(?:.*?[・･]\s*)?(?P<name>[^\s「」『』]{1,8})監督[「『](?P<quote>[^「」『』\n]{1,150})[」』]"
)
_MANAGER_TOPIC_RE = re.compile(
    r"(?:.*?[・･]\s*)?(?P<name>[^\s]{1,8})監督[、,]?\s*(?P<topic>[^「」\n]{2,40}?)(?:について|に関して|を巡って|を巡り)"
)


def extract_manager_quote(title: str, summary: str) -> Dict[str, str]:
    """Return {manager_name, quote_short, topic} or {} if not matched."""
    text = f"{title or ''}\n{summary or ''}"
    m = _MANAGER_QUOTE_RE.search(text)
    if m:
        return {
            "manager_name": m.group("name"),
            "quote_short": m.group("quote"),
            "topic": "",
        }
    m = _MANAGER_TOPIC_RE.search(text)
    if m:
        return {
            "manager_name": m.group("name"),
            "quote_short": "",
            "topic": m.group("topic"),
        }
    return {}


# 「[巨人・]?{選手名}「{quote}」」 — explicitly excludes "監督" prefix.
# Optional team-name prefix ending in ・/･ is consumed; the captured name itself
# never contains ・/･ so "巨人・岡本「..." → name="岡本".
_PLAYER_QUOTE_RE = re.compile(
    r"(?:[^\s「」『』]+?[・･])?(?P<name>[^\s「」『』監・･]{2,12})[「『](?P<quote>[^「」『』\n]{1,150})[」』]"
)


def extract_player_quote(title: str, summary: str) -> Dict[str, str]:
    """Return {player_name, quote_short} or {} if not matched.

    Excludes manager-quote patterns so manager_comment_card has priority.
    """
    text = f"{title or ''}\n{summary or ''}"
    if _MANAGER_QUOTE_RE.search(text):
        return {}
    m = _PLAYER_QUOTE_RE.search(text)
    if m:
        name = m.group("name").strip()
        quote = m.group("quote").strip()
        if not name or not quote:
            return {}
        return {"player_name": name, "quote_short": quote}
    return {}


_PREGAME_KEYWORD_RE = re.compile(r"予告先発")
_PITCHER_PAIR_RE = re.compile(r"([^\s対×vsVS]{2,8})\s*(?:対|vs|VS|×|－)\s*([^\s対×vsVS]{2,8})")


def detect_pregame_pitcher(title: str, summary: str) -> Dict[str, Any]:
    """Return {keyword_present, pitcher_pair} or {} if keyword absent."""
    text = f"{title or ''}\n{summary or ''}"
    if not _PREGAME_KEYWORD_RE.search(text):
        return {}
    m = _PITCHER_PAIR_RE.search(text)
    pair = (m.group(1).strip(), m.group(2).strip()) if m else None
    return {"keyword_present": True, "pitcher_pair": pair}


# ---------------------------------------------------------------------------
# Title sanitizer (NOMOTOKE-RSS-CARD-001B-TITLE-FIX)
#
# Applied ONLY to short_news_url_card titles via the router. Existing 10
# SHAPE-001 renderers are NOT affected. Source-only fact rule preserved:
# only RSS noise is deleted (URLs, "詳細はこちら" footers, hashtag #,
# HTML tags, runaway whitespace). Never adds tokens. Never invents words.
# ---------------------------------------------------------------------------


_TITLE_SANITIZE_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_TITLE_SANITIZE_HTML_RE = re.compile(r"<[^>]+>")
_TITLE_SANITIZE_HASHTAG_RE = re.compile(r"#([^\s#]+)")
_TITLE_SANITIZE_TRAILING_PHRASES: Tuple[str, ...] = (
    "試合詳細はこちら",
    "試合詳細",
    "詳細はこちら",
    "詳しくはこちら",
    "続きはこちら",
    "記事はこちら",
    "全文はこちら",
    "以下から",
    "詳細はリプライから",
    "リンクはこちら",
)
TITLE_MAX_CHARS_SHORT_NEWS = 50


def sanitize_short_news_title(title: str) -> str:
    """Return a publish-quality short_news_url title.

    Steps (deterministic, source-only):
      1. strip URL fragments (http(s)://...)
      2. strip embedded HTML tags (<br>, <a>, ...)
      3. convert hashtag `#word` to plain `word`
      4. remove trailing footer phrases like 「試合詳細はこちら」
      5. collapse whitespace (incl. full-width space U+3000)
      6. trim trailing punctuation/separators
      7. cap at TITLE_MAX_CHARS_SHORT_NEWS chars (truncate at 「。」 boundary
         when possible, else hard-cap with ellipsis)

    Returns "" when input is empty/None or sanitization removes everything.
    """
    if not title:
        return ""
    s = str(title)
    s = _TITLE_SANITIZE_URL_RE.sub(" ", s)
    s = _TITLE_SANITIZE_HTML_RE.sub(" ", s)
    s = _TITLE_SANITIZE_HASHTAG_RE.sub(r"\1", s)
    for phrase in _TITLE_SANITIZE_TRAILING_PHRASES:
        s = s.replace(phrase, " ")
    s = re.sub(r"[\s　]+", " ", s).strip()
    s = re.sub(r"[\s。、,.:：]+$", "", s).strip()
    if not s:
        return ""
    if len(s) <= TITLE_MAX_CHARS_SHORT_NEWS:
        return s
    cut = s[:TITLE_MAX_CHARS_SHORT_NEWS]
    idx = cut.rfind("。")
    if 0 < idx <= TITLE_MAX_CHARS_SHORT_NEWS:
        return cut[: idx + 1]
    return cut.rstrip() + "…"


# ---------------------------------------------------------------------------
# Quote-length guard
# ---------------------------------------------------------------------------


def _quote_too_long(quote: str) -> bool:
    return bool(quote) and len(quote.strip()) > QUOTE_SHORT_MAX_CHARS


def _quote_multiline(quote: str) -> bool:
    return bool(quote) and ("\n" in quote)


# ---------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------


@dataclass
class RouteResult:
    matched: bool
    template_key: str
    tier: int
    extracted_facts: Dict[str, Any] = field(default_factory=dict)
    missing_facts: List[str] = field(default_factory=list)
    skip_reason: str = ""
    dedupe_key: str = ""
    would_render_call: Optional[Dict[str, Any]] = None
    confidence: str = "low"
    canonical_url: str = ""
    source_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _confidence_for(template_key: str, tier: int) -> str:
    if template_key == TEMPLATE_KEY_SHORT_NEWS_URL:
        return "low"
    if tier == 1:
        return "high"
    if tier in (2, 3):
        return "medium"
    return "low"


def _dedupe_key(template_key: str, canonical: str) -> str:
    if not canonical:
        return ""
    h = _hash_canonical(canonical)
    short = {
        TEMPLATE_KEY_SHORT_NEWS_URL: "short_news_url",
        TEMPLATE_KEY_MANAGER_COMMENT: "manager_comment",
        TEMPLATE_KEY_PLAYER_COMMENT: "player_comment",
        TEMPLATE_KEY_PREGAME_PITCHER: "pregame",
    }.get(template_key, template_key)
    return f"{short}:{h}"


def _skip(
    reason: str,
    *,
    template_key: str = "",
    tier: int = 0,
    canonical_url: str = "",
    source_name: str = "",
    missing_facts: Optional[List[str]] = None,
) -> RouteResult:
    return RouteResult(
        matched=False,
        template_key=template_key,
        tier=tier,
        extracted_facts={},
        missing_facts=list(missing_facts or []),
        skip_reason=reason,
        dedupe_key="",
        would_render_call=None,
        confidence="low",
        canonical_url=canonical_url,
        source_name=source_name,
    )


# ---------------------------------------------------------------------------
# Required-facts mapping (per-template, exposed for the report).
# ---------------------------------------------------------------------------


REQUIRED_FACTS_BY_TEMPLATE: Dict[str, List[str]] = {
    TEMPLATE_KEY_SHORT_NEWS_URL: ["source_url", "source_name", "title"],
    TEMPLATE_KEY_MANAGER_COMMENT: [
        "source_url",
        "source_name",
        "title",
        "manager_name(allowlist)",
        "quote_short(<=100chars)",
    ],
    TEMPLATE_KEY_PLAYER_COMMENT: [
        "source_url",
        "source_name",
        "title",
        "player_name",
        "quote_short(<=100chars)",
    ],
    TEMPLATE_KEY_PREGAME_PITCHER: [
        "source_url",
        "source_name",
        "title",
        "keyword:予告先発",
        "pitcher_pair",
        "stale<=36h",
    ],
}


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------


def route_rss_entry_to_nomotoke_card(
    entry: Mapping[str, Any],
    *,
    source_name: str,
    source_url: str = "",
) -> RouteResult:
    """Classify a single RSS entry to a nomotoke card template.

    Returns a RouteResult whose ``template_key`` is either:
        - one of RSS_ONLY_ALLOWED_TEMPLATES, when matched=True
        - "" when matched=False

    NEVER returns a RSS_ONLY_BLOCKED_TEMPLATES key. The branches for those
    templates do not exist in this function. (Verified by tests.)
    """
    title = (entry.get("title") or "").strip()
    summary = (entry.get("summary") or entry.get("description") or "").strip()
    link = (entry.get("link") or "").strip()
    published = (entry.get("published") or "").strip()

    # Defense-in-depth: never let nomotoke phrasings into the result.
    _check_nomotoke_phrasing(title, summary, source_name)

    chosen_url = source_url or link
    canonical = normalize_canonical_url(chosen_url)
    tier = source_tier(source_name)

    if not chosen_url or _is_unsafe_url(chosen_url) or not canonical:
        return _skip("unsafe_url", tier=tier, source_name=source_name)

    if not is_giants_relevant(title, summary, source_name):
        return _skip(
            "not_giants_related",
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
        )

    # ------------------------------------------------------------------
    # 1. pregame_pitcher_card
    # ------------------------------------------------------------------
    pre = detect_pregame_pitcher(title, summary)
    if pre.get("keyword_present"):
        if is_stale(published, TEMPLATE_KEY_PREGAME_PITCHER):
            # fall through to other templates / fallback
            pass
        else:
            pair = pre.get("pitcher_pair")
            if not pair:
                return _skip(
                    "insufficient_required_facts:pregame_pitcher:pitcher_pair",
                    template_key=TEMPLATE_KEY_PREGAME_PITCHER,
                    tier=tier,
                    canonical_url=canonical,
                    source_name=source_name,
                    missing_facts=["pitcher_pair"],
                )
            return RouteResult(
                matched=True,
                template_key=TEMPLATE_KEY_PREGAME_PITCHER,
                tier=tier,
                extracted_facts={
                    "keyword_matched": True,
                    "pitcher_pair": list(pair),
                },
                missing_facts=[],
                skip_reason="",
                dedupe_key=_dedupe_key(TEMPLATE_KEY_PREGAME_PITCHER, canonical),
                would_render_call={
                    "renderer_func_name": "render_pregame_pitcher_card",
                    "data_preview": {
                        "date_label": _date_label_from_iso(published),
                        "official_url": chosen_url,
                        "matchups": [
                            {
                                "team_a": "巨人",
                                "pitcher_a": pair[0],
                                "team_b": "対戦相手",
                                "pitcher_b": pair[1],
                            }
                        ],
                        "source_url": chosen_url,
                    },
                },
                confidence=_confidence_for(TEMPLATE_KEY_PREGAME_PITCHER, tier),
                canonical_url=canonical,
                source_name=source_name,
            )

    # ------------------------------------------------------------------
    # 2. manager_comment_card
    # ------------------------------------------------------------------
    mq = extract_manager_quote(title, summary)
    manager_allowlist_skip = False
    if mq.get("manager_name"):
        if mq["manager_name"] not in MANAGER_NAME_ALLOWLIST:
            manager_allowlist_skip = True
        else:
            quote = mq.get("quote_short", "")
            if _quote_multiline(quote):
                return _skip(
                    "quote_multiline_not_allowed",
                    template_key=TEMPLATE_KEY_MANAGER_COMMENT,
                    tier=tier,
                    canonical_url=canonical,
                    source_name=source_name,
                )
            if _quote_too_long(quote):
                return _skip(
                    "quote_too_long",
                    template_key=TEMPLATE_KEY_MANAGER_COMMENT,
                    tier=tier,
                    canonical_url=canonical,
                    source_name=source_name,
                )
            if not quote:
                return _skip(
                    "insufficient_required_facts:manager_comment:quote_short",
                    template_key=TEMPLATE_KEY_MANAGER_COMMENT,
                    tier=tier,
                    canonical_url=canonical,
                    source_name=source_name,
                    missing_facts=["quote_short"],
                )
            return RouteResult(
                matched=True,
                template_key=TEMPLATE_KEY_MANAGER_COMMENT,
                tier=tier,
                extracted_facts=dict(mq),
                missing_facts=[],
                skip_reason="",
                dedupe_key=_dedupe_key(TEMPLATE_KEY_MANAGER_COMMENT, canonical),
                would_render_call={
                    "renderer_func_name": "render_manager_comment_card",
                    "data_preview": {
                        "team_name": "巨人",
                        "manager_name": mq["manager_name"],
                        "topic": mq.get("topic") or quote[:30],
                        "quote_short": quote,
                        "source_url": chosen_url,
                        "source_name": source_name,
                        "published_at": published,
                        "date_label": _date_label_from_iso(published),
                    },
                },
                confidence=_confidence_for(TEMPLATE_KEY_MANAGER_COMMENT, tier),
                canonical_url=canonical,
                source_name=source_name,
            )

    # ------------------------------------------------------------------
    # 3. player_comment_card
    # ------------------------------------------------------------------
    pq = extract_player_quote(title, summary)
    if pq:
        quote = pq.get("quote_short", "")
        player = pq.get("player_name", "")
        if _quote_multiline(quote):
            return _skip(
                "quote_multiline_not_allowed",
                template_key=TEMPLATE_KEY_PLAYER_COMMENT,
                tier=tier,
                canonical_url=canonical,
                source_name=source_name,
            )
        if _quote_too_long(quote):
            return _skip(
                "quote_too_long",
                template_key=TEMPLATE_KEY_PLAYER_COMMENT,
                tier=tier,
                canonical_url=canonical,
                source_name=source_name,
            )
        if not player:
            return _skip(
                "insufficient_required_facts:player_comment:player_name",
                template_key=TEMPLATE_KEY_PLAYER_COMMENT,
                tier=tier,
                canonical_url=canonical,
                source_name=source_name,
                missing_facts=["player_name"],
            )
        if not quote:
            return _skip(
                "insufficient_required_facts:player_comment:quote_short",
                template_key=TEMPLATE_KEY_PLAYER_COMMENT,
                tier=tier,
                canonical_url=canonical,
                source_name=source_name,
                missing_facts=["quote_short"],
            )
        return RouteResult(
            matched=True,
            template_key=TEMPLATE_KEY_PLAYER_COMMENT,
            tier=tier,
            extracted_facts=dict(pq),
            missing_facts=[],
            skip_reason="",
            dedupe_key=_dedupe_key(TEMPLATE_KEY_PLAYER_COMMENT, canonical),
            would_render_call={
                "renderer_func_name": "render_player_comment_card",
                "data_preview": {
                    "team_name": "巨人",
                    "player_name": player,
                    "topic": quote[:30],
                    "quote_short": quote,
                    "source_url": chosen_url,
                    "source_name": source_name,
                    "published_at": published,
                    "date_label": _date_label_from_iso(published),
                },
            },
            confidence=_confidence_for(TEMPLATE_KEY_PLAYER_COMMENT, tier),
            canonical_url=canonical,
            source_name=source_name,
        )

    # ------------------------------------------------------------------
    # 4. short_news_url_card (fallback, low confidence)
    # ------------------------------------------------------------------
    if manager_allowlist_skip:
        # Still emit short_news_url; keep audit info.
        pass

    if not title:
        return _skip(
            "insufficient_required_facts:short_news_url:title",
            template_key=TEMPLATE_KEY_SHORT_NEWS_URL,
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
            missing_facts=["title"],
        )
    if not chosen_url:
        return _skip(
            "insufficient_required_facts:short_news_url:source_url",
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
            missing_facts=["source_url"],
        )
    if not source_name:
        return _skip(
            "insufficient_required_facts:short_news_url:source_name",
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
            missing_facts=["source_name"],
        )

    extracted = {}
    if manager_allowlist_skip and mq.get("manager_name"):
        extracted["fallback_from"] = (
            f"manager_not_in_allowlist:{mq['manager_name']}"
        )

    sanitized_title = sanitize_short_news_title(title)
    if not sanitized_title:
        return _skip(
            "insufficient_required_facts:short_news_url:title",
            template_key=TEMPLATE_KEY_SHORT_NEWS_URL,
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
            missing_facts=["title"],
        )
    if title and title != sanitized_title:
        extracted["title_raw"] = title[:200]
        extracted["title_sanitized"] = sanitized_title

    return RouteResult(
        matched=True,
        template_key=TEMPLATE_KEY_SHORT_NEWS_URL,
        tier=tier,
        extracted_facts=extracted,
        missing_facts=[],
        skip_reason="",
        dedupe_key=_dedupe_key(TEMPLATE_KEY_SHORT_NEWS_URL, canonical),
        would_render_call={
            "renderer_func_name": "render_short_news_url_card",
            "data_preview": {
                "title": sanitized_title,
                "summary": summary[:200],
                "source_url": chosen_url,
                "source_name": source_name,
                "date_label": _date_label_from_iso(published),
            },
        },
        confidence=_confidence_for(TEMPLATE_KEY_SHORT_NEWS_URL, tier),
        canonical_url=canonical,
        source_name=source_name,
    )


# ---------------------------------------------------------------------------
# Recommendation helpers (used by the dry-run report)
# ---------------------------------------------------------------------------


def derive_next_recommended(
    template_counts: Mapping[str, int],
    template_confidence_counts: Mapping[str, Mapping[str, int]],
    *,
    min_hit: int = 5,
    min_high_medium_ratio: float = 0.5,
) -> List[str]:
    """Return RSS-only allowed templates that meet hit and confidence gates.

    NEVER includes blocked templates (they cannot appear in template_counts
    because the router does not emit them).
    """
    out: List[str] = []
    for tk in RSS_ONLY_ALLOWED_TEMPLATES:
        if tk in RSS_ONLY_BLOCKED_TEMPLATES:
            # impossible by construction, defensive
            continue
        hits = int(template_counts.get(tk, 0) or 0)
        if hits < min_hit:
            continue
        conf = template_confidence_counts.get(tk, {}) or {}
        hm = int(conf.get("high", 0) or 0) + int(conf.get("medium", 0) or 0)
        total = sum(int(v or 0) for v in conf.values())
        if total <= 0:
            continue
        if (hm / total) < min_high_medium_ratio:
            continue
        out.append(tk)
    return out


def derive_not_suitable_for_rss() -> List[str]:
    """Return blocked templates + low/impossible templates (always)."""
    return list(RSS_ONLY_BLOCKED_TEMPLATES)


__all__ = [
    "ENABLE_FLAG",
    "TEMPLATE_KEY_SHORT_NEWS_URL",
    "TEMPLATE_KEY_MANAGER_COMMENT",
    "TEMPLATE_KEY_PLAYER_COMMENT",
    "TEMPLATE_KEY_PREGAME_PITCHER",
    "RSS_ONLY_ALLOWED_TEMPLATES",
    "RSS_ONLY_BLOCKED_TEMPLATES",
    "QUALITY_CEILING_BY_TEMPLATE",
    "REQUIRED_FACTS_BY_TEMPLATE",
    "SKIP_REASON_TAXONOMY",
    "MANAGER_NAME_ALLOWLIST",
    "QUOTE_SHORT_MAX_CHARS",
    "PREGAME_STALE_HOURS",
    "GIANTS_KEYWORDS",
    "TITLE_MAX_CHARS_SHORT_NEWS",
    "RouteResult",
    "is_enabled",
    "source_tier",
    "normalize_canonical_url",
    "is_giants_relevant",
    "is_stale",
    "extract_manager_quote",
    "extract_player_quote",
    "detect_pregame_pitcher",
    "sanitize_short_news_title",
    "route_rss_entry_to_nomotoke_card",
    "derive_next_recommended",
    "derive_not_suitable_for_rss",
]
