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
TEMPLATE_KEY_VIDEO = "nomotoke_card_video_v1"


RSS_ONLY_ALLOWED_TEMPLATES: Tuple[str, ...] = (
    TEMPLATE_KEY_SHORT_NEWS_URL,
    TEMPLATE_KEY_MANAGER_COMMENT,
    TEMPLATE_KEY_PLAYER_COMMENT,
    TEMPLATE_KEY_PREGAME_PITCHER,
    # NOMOTOKE-VIDEO-SOURCE-001: video_v1 graduates from BLOCKED to
    # ALLOWED for the YouTube channel RSS pool. The router only routes
    # to video_v1 when the entry's link is a YouTube watch URL — feeds
    # carrying YouTube entries must be supplied via the operator-curated
    # config/youtube_video_sources.json (NOT config/rss_sources.json),
    # so the production rss_fetcher.py never picks these up.
    TEMPLATE_KEY_VIDEO,
)


RSS_ONLY_BLOCKED_TEMPLATES: Tuple[str, ...] = (
    "nomotoke_card_lineup_v1",
    "nomotoke_card_postgame_v1",
    "nomotoke_card_live_at_bats_v1",
    "nomotoke_card_player_stats_v1",
    "nomotoke_card_broadcast_v1",
    "nomotoke_card_official_notice_v1",
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
    TEMPLATE_KEY_VIDEO: {
        # NOMOTOKE-VIDEO-SOURCE-001: status raised from "impossible" to
        # "medium" once config/youtube_video_sources.json is supplied via
        # --sources-file. play_summary / player_name extraction is
        # title-based; quality is medium because some channel videos
        # (event recaps, behind-the-scenes) lack a clear player + summary
        # and skip with insufficient_required_facts:video:player_name.
        "rss_only_quality": "medium",
        "reason": "YouTube channel RSS は title / link / published / thumbnail を返す。Giants-relevant + player_name + play_summary が抽出できれば video_v1 へ。shorts は skip。",
        "required_external_data": [],
        "allow_rss_only": True,
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
    "x_post_not_article_source",
    "video_source_detected",
    "promo_or_merchandise_content",
    "live_inning_blurb_not_article",
    # NOMOTOKE-VIDEO-SOURCE-001: YouTube channel RSS supply.
    "youtube_shorts_skipped",
    "insufficient_required_facts:video:player_name",
    "insufficient_required_facts:video:play_summary",
)


# Phase 2C+: promo / merchandise / sweepstakes content keywords. Presence
# of ANY of these in title or summary triggers ``promo_or_merchandise_content``
# skip. The list is curated to (a) reject sponsorship posts ("宣伝する"),
# (b) merchandise sales ("記念グッズ" / "受注販売" / "予約販売" /
# "限定発売" / "サイン入り"), (c) sweepstakes ("プレゼント") — and to NOT
# match legitimate game / roster / injury news (which use 抹消 / 召集 /
# 故障 / 違和感 / 復帰 / 発表 instead).
_PROMO_CONTENT_KEYWORDS: Tuple[str, ...] = (
    # Phase 2C+ wave 1: merchandise / sweepstakes / sponsorship
    "記念グッズ",
    "予約販売",
    "受注販売",
    "限定発売",
    "サイン入り",
    "宣伝する",
    "ステッカーをプレゼント",
    "プレゼント！",
    "ちゃっかり宣伝",
    # NOMOTOKE-TEMPLATE-ROUTING-AUDIT-001 wave 2: kid / fan event posts.
    # Live 30-entry dry-run surfaced 「春のKIDS FES」「野球体験会」「観戦した
    # 小学生」 as event-announcement X posts that are not articles. They were
    # falling to short_news_url via the fallback path. Reject at router.
    "野球体験会",
    "観戦した小学生",
    "KIDS FES",
    "イベントを満喫",
    "観戦イベント",
    "見学会",
    "サイン会",
    "ファンミーティング",
)


def _looks_like_promo_content(title: str, summary: str) -> bool:
    """Return True iff the title or summary contains a promo-content marker.

    Substring check on a closed list of phrases that, in observed live X
    RSS samples, only appear in merchandise / sweepstakes / sponsorship
    posts. Legitimate game / roster news does not use these phrases.
    """
    text = f"{title or ''}\n{summary or ''}"
    return any(kw in text for kw in _PROMO_CONTENT_KEYWORDS)


# X-post host detection (after normalize_canonical_url; x.com -> twitter.com).
_X_HOSTS: frozenset[str] = frozenset({"twitter.com"})

# Video source detection — official video destinations only. Embed-platforms in
# X bodies are routed to the (currently blocked) video_card track via a
# distinct skip_reason so analytics can surface supply if YouTube channel RSS
# is wired later.
_VIDEO_URL_RE = re.compile(
    r"https?://(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch|shorts)|youtu\.be/|"
    r"giants\.jp/(?:tv|video|movie)|"
    r"npb\.jp/(?:bis|video)|"
    r"giants-tv\.jp)[^\s　「」『』<>]*",
    re.IGNORECASE,
)

# Generic URL extractor for body-internal links. Used to find an external
# article URL inside an X-post body so the X URL can be demoted to embed.
_GENERIC_URL_RE = re.compile(r"https?://[^\s　「」『』<>]+")


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
    """Return a Japanese-format JST date label.

    Format ``YYYY年M月D日`` (no leading zeros on month/day) avoids the
    ``\\d{1,2}-\\d{1,2}`` pattern matched by the score consistency
    tokenizer — ``2026-05-06`` would otherwise resolve to a phantom
    score of ``(5, 6)`` and conflict with a real score in the summary,
    triggering ``review_score_order_mismatch_review`` on guarded-publish.
    """
    d = _parse_iso_or_rfc822(iso)
    if d is None:
        return ""
    jst = d.astimezone(timezone(timedelta(hours=9)))
    return f"{jst.year}年{jst.month}月{jst.day}日"


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

# Phase 2C cleanup — observed garbage extractions from live X RSS feeds:
#   - 「が運営するお菓子屋」 picked as a "name" because the regex grabs
#     whatever non-space chars sit before 「. Real names start with kanji
#     or katakana, never with a Japanese particle.
#   - 「#吉川尚輝」 — hashtag tokens look like names but are tags.
#   - 「【巨人】吉川尚輝」 — bracket prefixes leak into the rendered title
#     producing 「巨人・【巨人】吉川尚輝」 double-prefix.
# Three rules below reject / clean these without changing the regex's
# main capture so the router still classifies clean cases as before.
_PLAYER_NAME_LEADING_PARTICLES: tuple = (
    "が", "を", "に", "は", "と", "で", "も", "から",
    "まで", "より", "へ", "や",
)
_PLAYER_NAME_BRACKET_PREFIX_RE = re.compile(r"^[【\[][^【\[\]】]{1,10}[】\]]")
_PLAYER_QUOTE_REJECTED_QUOTE_PATTERNS: tuple = (
    "FES", "BACK", "PROJECT", "NEW",  # event / merchandise wording
)


def _player_name_passes_quality(name: str) -> bool:
    """Reject names that are clearly not personal names.

    Japanese personal names in pro baseball are kanji surnames or
    katakana foreign names (or kanji + katakana combos) — they do NOT
    contain hiragana. Live X RSS feeds emit titles like
    「ファーム戦の試合後に「…」」, 「中日戦先発ウィットリーは「…」」, or
    「脱中の山崎伊織の現状説明、…」 where the regex captures a long
    phrase containing hiragana particles. Treating those as names yields
    nonsensical 「{phrase}選手がコメントです。」 closing lines.

    Rules (strict superset of Phase 2C initial release):
      1. Reject empty.
      2. Reject hashtag-only tokens (``#吉川``).
      3. Reject names starting with a Japanese particle.
      4. Reject names containing ANY hiragana char (U+3040 to U+309F).

    Real names that this rejects? Pro baseball: zero observed.
    """
    s = (name or "").strip()
    if not s:
        return False
    if s.startswith("#"):
        return False
    if s.startswith(_PLAYER_NAME_LEADING_PARTICLES):
        return False
    for ch in s:
        # Hiragana block — present in particles / particles-in-phrases
        # but absent from kanji / katakana personal names.
        if "぀" <= ch <= "ゟ":
            return False
    return True


def _player_quote_passes_quality(quote: str) -> bool:
    """Reject quotes that are obvious product / event names rather than
    actual statements. The closing line in the rendered card reads
    ``{name}選手がコメントです。`` so passing a product name through
    creates a nonsensical article — better to skip and let the router
    fall through to the short_news_url card instead.
    """
    s = (quote or "").strip()
    if not s:
        return False
    if s.startswith("#"):
        return False
    upper = s.upper()
    for pat in _PLAYER_QUOTE_REJECTED_QUOTE_PATTERNS:
        if pat in upper:
            return False
    return True


def _strip_player_name_bracket_prefix(name: str) -> str:
    """Drop a leading ``【…】`` / ``[…]`` decoration so titles don't
    render as ``巨人・【巨人】吉川尚輝、…``. Returns the inner name.
    """
    s = (name or "").strip()
    m = _PLAYER_NAME_BRACKET_PREFIX_RE.match(s)
    if m:
        return s[m.end():].strip()
    return s


def extract_player_quote(title: str, summary: str) -> Dict[str, str]:
    """Return {player_name, quote_short} or {} if not matched.

    Excludes manager-quote patterns so manager_comment_card has priority.
    Phase 2C: rejects garbage names (hiragana-leading particles / hashtag
    prefixes) and event-name quotes so live X RSS noise does not produce
    nonsensical player_comment cards.
    """
    text = f"{title or ''}\n{summary or ''}"
    if _MANAGER_QUOTE_RE.search(text):
        return {}
    m = _PLAYER_QUOTE_RE.search(text)
    if m:
        name = _strip_player_name_bracket_prefix(m.group("name"))
        quote = m.group("quote").strip()
        if not name or not quote:
            return {}
        if not _player_name_passes_quality(name):
            return {}
        if not _player_quote_passes_quality(quote):
            return {}
        return {"player_name": name, "quote_short": quote}
    return {}


_PREGAME_KEYWORD_RE = re.compile(r"予告先発")
# NOMOTOKE-TEMPLATE-ROUTING-AUDIT-001: dash inventory expanded so the
# pitcher-pair regex matches the em-dash ``―`` (U+2015) used by hochi
# headlines (e.g. ``中日・柳裕也―巨人・ウィットリー``) and the en-dash
# ``–`` (U+2013). Without these the pre-existing ``－`` (U+FF0D) only
# matched the hyphenated-by-fullwidth-minus shape and 予告先発 entries
# were dropping pitcher_pair extraction.
_PITCHER_PAIR_RE = re.compile(
    r"([^\s対×vsVS]{2,8})\s*(?:対|vs|VS|×|－|―|–|-)\s*([^\s対×vsVS]{2,8})"
)


# NOMOTOKE-TEMPLATE-ROUTING-AUDIT-001: live in-game tweet titles like
# 「【八回表】巨人 0-2 ヤクルト …」 / 「【試合終了】…」 are X play-by-play
# blurbs, not articles. They previously fell through to short_news_url via
# the fallback path, dominating template distribution at 76% in the live
# 30-entry audit. The MVP scope (Phase 1) does NOT publish live updates
# (ENABLE_RSS_SOCIAL_LIVE_UPDATE=0 in the main rss_fetcher), so the
# nomotoke router must mirror that gate.
_LIVE_INNING_TITLE_RE = re.compile(
    r"^\s*【\s*(?:[一二三四五六七八九十]+|[0-9０-９]+)\s*回\s*(?:表|裏|終了|裏終了|表終了)?\s*】"
)
_LIVE_GAME_BOUNDARY_TITLE_RE = re.compile(
    r"^\s*【\s*(?:試合終了|試合開始|試合再開|プレーボール|ゲームセット|試合中止)\s*】"
)


def _looks_like_live_inning_blurb(title: str) -> bool:
    """Return True iff the title is an X live in-game / boundary tweet.

    Matched shapes (Giants公式X live posts):
      - ``【八回表】巨人 0-2 ヤクルト ...``
      - ``【九回裏】 ...``
      - ``【試合終了】巨人 0-5 ヤクルト ...``
      - ``【プレーボール】 ...``

    These are play-by-play tweets, not articles. Phase 1 MVP does not
    publish live updates; routing them to short_news_url forces them
    into the article pool and starves other templates.
    """
    text = (title or "").strip()
    if not text:
        return False
    if _LIVE_INNING_TITLE_RE.match(text):
        return True
    if _LIVE_GAME_BOUNDARY_TITLE_RE.match(text):
        return True
    return False


def detect_pregame_pitcher(title: str, summary: str) -> Dict[str, Any]:
    """Return {keyword_present, pitcher_pair} or {} if keyword absent."""
    text = f"{title or ''}\n{summary or ''}"
    if not _PREGAME_KEYWORD_RE.search(text):
        return {}
    m = _PITCHER_PAIR_RE.search(text)
    pair = (m.group(1).strip(), m.group(2).strip()) if m else None
    return {"keyword_present": True, "pitcher_pair": pair}


# ---------------------------------------------------------------------------
# NOMOTOKE-VIDEO-SOURCE-001: YouTube channel RSS routing helpers.
#
# Production rss_fetcher.py NEVER reads config/youtube_video_sources.json,
# so YouTube entries only enter this router via
# `python -m src.tools.run_nomotoke_rss_card_draft --sources-file=config/
#  youtube_video_sources.json`. The route is dry-run / draft only — there
# is no Scheduler hook for YouTube supply.
# ---------------------------------------------------------------------------


_YOUTUBE_WATCH_RE = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_YOUTUBE_SHORTS_RE = re.compile(
    r"^https?://(?:www\.|m\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})"
)
# Quoted player-name extraction. DRAMATIC BASEBALL titles wrap the player
# name in full-width double quotes ("..."), and 巨人公式 occasionally uses
# single 「」. Allow both, plus a small set of inner chars (kanji /
# katakana / Latin / dot / space).
_VIDEO_QUOTED_NAME_RE = re.compile(
    r"[「“「\"]"
    r"(?P<name>[一-龯ァ-ヴー\.A-Za-zＡ-Ｚａ-ｚ][一-龯ァ-ヴー\.\sA-Za-zＡ-Ｚａ-ｚ]{1,14})"
    r"[」”」\"]"
)


def is_youtube_watch_url(url: str) -> bool:
    return bool(_YOUTUBE_WATCH_RE.match((url or "").strip()))


def is_youtube_shorts_url(url: str) -> bool:
    return bool(_YOUTUBE_SHORTS_RE.match((url or "").strip()))


def youtube_video_id(url: str) -> str:
    """Return the 11-char YouTube video id, or '' if the URL is not a
    youtube watch / youtu.be URL."""
    raw = (url or "").strip()
    m = _YOUTUBE_WATCH_RE.match(raw)
    if m:
        return m.group(1)
    return ""


def youtube_embed_iframe(video_id: str) -> str:
    """Return a sanitizable YouTube embed iframe HTML snippet.

    The renderer's ``_filter_safe_iframe`` re-validates host + attrs, so
    this string is built conservatively (no JS, no arbitrary attrs).
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        return ""
    return (
        f'<iframe width="560" height="315" '
        f'src="https://www.youtube.com/embed/{video_id}" '
        f'title="YouTube video player" frameborder="0" '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
        f'gyroscope; picture-in-picture" allowfullscreen></iframe>'
    )


def extract_video_facts(title: str) -> Dict[str, str]:
    """Extract player_name + play_summary from a YouTube video title.

    Returns ``{}`` when the title carries no clearly-quoted player name —
    the caller then skips with insufficient_required_facts:video:player_name.
    """
    raw = (title or "").strip()
    if not raw:
        return {}
    m = _VIDEO_QUOTED_NAME_RE.search(raw)
    if not m:
        return {}
    name = m.group("name").strip()
    if not name:
        return {}
    after = raw[m.end():].strip()
    # Cut play_summary at the FIRST occurrence of any boundary char so
    # trailing 【巨人×ヤクルト】 channel-decoration tags do not bleed
    # into the summary, AND the trailing ! / ! / 。 sentence terminator
    # is dropped. Iterate by index so the earliest boundary wins
    # regardless of which char it is.
    boundary_chars = "【!！。\n"
    cut_idx = -1
    for i, ch in enumerate(after):
        if ch in boundary_chars:
            cut_idx = i
            break
    if cut_idx > 0:
        after = after[:cut_idx]
    summary = after.strip("、 ・")[:60]
    if not summary:
        return {"player_name": name, "play_summary": ""}
    return {"player_name": name, "play_summary": summary}


# ---------------------------------------------------------------------------
# X-post detection + body-internal URL extraction
# (NOMOTOKE-RSS-CARD-001B-XPOST-FIX)
#
# An X-post URL alone must NOT become a short_news_url article. The router
# only emits short_news_url for an X source when the body contains an
# external (non-X) article URL — that URL is promoted to primary_source and
# the original X URL is demoted to related_source_url / x_embed_url. When
# only a video URL is present we surface video_source_detected so supply can
# be observed without firing the (still-blocked) video_card template. When
# neither external article nor video URL is present, the entry is skipped
# with x_post_not_article_source — score-only / commentary-free X posts are
# intentionally dropped here.
# ---------------------------------------------------------------------------


def is_x_post_url(canonical_url: str) -> bool:
    """Return True iff the canonicalized URL host is an X / Twitter host.

    Input MUST be canonical (output of normalize_canonical_url) so that
    x.com / www.x.com / mobile.x.com all collapse to twitter.com first.
    """
    if not canonical_url:
        return False
    try:
        host = urlparse(canonical_url).netloc.lower()
    except Exception:
        return False
    return host in _X_HOSTS


def extract_external_article_url(
    title: str, summary: str, *, exclude_canonical: str = ""
) -> str:
    """Return the first non-X external article URL found in title/summary.

    Returns "" when no eligible URL is present. The returned URL is already
    canonicalized (tracking params stripped, fragment dropped, host
    lowercased). Filtered out:
        - X / Twitter URLs (tracked separately as related_source_url)
        - ``exclude_canonical`` (the X-post itself)
        - Official video URLs matched by ``_VIDEO_URL_RE`` (YouTube /
          giants.jp/tv / npb.jp/video / giants-tv.jp). Video URLs route to
          ``video_source_detected`` skip, not to short_news_url, so they
          must not be promoted to primary_source here.
    """
    text = f"{title or ''}\n{summary or ''}"
    for m in _GENERIC_URL_RE.finditer(text):
        raw = m.group(0)
        if _VIDEO_URL_RE.match(raw):
            continue
        canonical = normalize_canonical_url(raw)
        if not canonical:
            continue
        if is_x_post_url(canonical):
            continue
        if exclude_canonical and canonical == exclude_canonical:
            continue
        return canonical
    return ""


def extract_video_source_url(title: str, summary: str) -> str:
    """Return the first official video URL (YouTube/giants.jp/npb.jp) or "".

    Used purely for skip_reason routing — the router never emits
    nomotoke_card_video_v1 in 001B (still in RSS_ONLY_BLOCKED_TEMPLATES).
    """
    text = f"{title or ''}\n{summary or ''}"
    m = _VIDEO_URL_RE.search(text)
    if not m:
        return ""
    raw = m.group(0)
    return normalize_canonical_url(raw) or raw


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
        TEMPLATE_KEY_VIDEO: "video",
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
    TEMPLATE_KEY_VIDEO: [
        "youtube_watch_url",
        "video_id(11chars)",
        "player_name(quoted in title)",
        "play_summary",
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

    # Phase 2C: X retweet (``RT @account: ...``) entries are not original
    # source posts. Skip them so live X RSS feeds don't produce cards
    # built around third-party promotional content. The skip reuses the
    # ``not_giants_related`` taxonomy so existing dashboards keep working;
    # the audit log retains the title for operator review.
    title_stripped = (title or "").lstrip()
    if title_stripped.startswith("RT @") or title_stripped.startswith("RT "):
        return _skip(
            "not_giants_related",
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
        )

    # Phase 2C+: merchandise / sweepstakes / sponsorship-promo X posts
    # are not articles. Live drafting surfaced posts like
    #   「…が運営するお菓子屋『COCCOPURIO』をちゃっかり宣伝する…」
    #   「『NAOKI IS BACK』記念グッズ発売✨ …受注販売します」
    # which slipped past the Giants-relevance check (they ARE Giants-
    # related — the player is named) but rendered as URL-card stubs with
    # no journalistic substance. Rejecting them at the router level
    # avoids producing thin promo cards no one would publish.
    if _looks_like_promo_content(title, summary):
        return _skip(
            "promo_or_merchandise_content",
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
        )

    # NOMOTOKE-TEMPLATE-ROUTING-AUDIT-001: skip X live in-game blurbs.
    # MVP does not publish live updates; allowing 【N回表】… into the
    # article pool starved other templates (76% of the live 30-entry
    # dry-run was short_news_url because of these).
    if _looks_like_live_inning_blurb(title):
        return _skip(
            "live_inning_blurb_not_article",
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
        )

    # ------------------------------------------------------------------
    # 0. video_card (NOMOTOKE-VIDEO-SOURCE-001)
    #
    # YouTube watch URLs only — shorts are skipped as a separate class so
    # supply can still be observed. Source must already be Giants-relevant
    # (passed the earlier guard) so a quoted player_name is the article
    # threshold; no quoted name → skip without falling through to
    # short_news_url (a youtube.com link in short_news_url has no
    # journalistic value on its own).
    # ------------------------------------------------------------------
    if is_youtube_shorts_url(canonical):
        return _skip(
            "youtube_shorts_skipped",
            tier=tier,
            canonical_url=canonical,
            source_name=source_name,
        )
    if is_youtube_watch_url(canonical):
        video_id = youtube_video_id(canonical)
        facts = extract_video_facts(title)
        player = facts.get("player_name", "")
        summary_short = facts.get("play_summary", "")
        if not player:
            return _skip(
                "insufficient_required_facts:video:player_name",
                template_key=TEMPLATE_KEY_VIDEO,
                tier=tier,
                canonical_url=canonical,
                source_name=source_name,
                missing_facts=["player_name"],
            )
        if not summary_short:
            return _skip(
                "insufficient_required_facts:video:play_summary",
                template_key=TEMPLATE_KEY_VIDEO,
                tier=tier,
                canonical_url=canonical,
                source_name=source_name,
                missing_facts=["play_summary"],
            )
        return RouteResult(
            matched=True,
            template_key=TEMPLATE_KEY_VIDEO,
            tier=tier,
            extracted_facts={
                "video_id": video_id,
                "player_name": player,
                "play_summary": summary_short,
            },
            missing_facts=[],
            skip_reason="",
            dedupe_key=_dedupe_key(TEMPLATE_KEY_VIDEO, canonical),
            would_render_call={
                "renderer_func_name": "render_video_card",
                "data_preview": {
                    "team_name": "巨人",
                    "player_name": player,
                    "play_summary": summary_short,
                    "video_url": chosen_url,
                    "embed_html": youtube_embed_iframe(video_id),
                    "source_url": chosen_url,
                    "source_name": source_name,
                    "source_label": source_name,
                    "date_label": _date_label_from_iso(published),
                    "description": (summary or "")[:120],
                },
            },
            confidence=_confidence_for(TEMPLATE_KEY_VIDEO, tier),
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
    #
    # X-only posts are intentionally NOT eligible here. An X source must
    # either (a) carry an external article URL inside its body — that URL
    # becomes the primary source while the X URL is demoted to related —
    # or (b) be skipped with x_post_not_article_source / video_source_detected.
    # Score-only / commentary-free X posts (e.g. TokyoGiants 試合終了 box) hit
    # the x_post_not_article_source branch and never become drafts.
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

    primary_url = chosen_url
    primary_canonical = canonical
    related_source_url = ""
    x_source = is_x_post_url(canonical)
    if x_source:
        external_url = extract_external_article_url(
            title, summary, exclude_canonical=canonical
        )
        if external_url:
            primary_url = external_url
            primary_canonical = external_url
            related_source_url = chosen_url
        else:
            video_url = extract_video_source_url(title, summary)
            if video_url:
                return _skip(
                    "video_source_detected",
                    tier=tier,
                    canonical_url=canonical,
                    source_name=source_name,
                )
            return _skip(
                "x_post_not_article_source",
                tier=tier,
                canonical_url=canonical,
                source_name=source_name,
            )

    extracted: Dict[str, Any] = {}
    if manager_allowlist_skip and mq.get("manager_name"):
        extracted["fallback_from"] = (
            f"manager_not_in_allowlist:{mq['manager_name']}"
        )
    if related_source_url:
        extracted["x_embed_url"] = related_source_url
        extracted["primary_source_promoted_from"] = "x_post_body_url"

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

    data_preview: Dict[str, Any] = {
        "title": sanitized_title,
        "summary": summary[:200],
        "source_url": primary_url,
        "source_name": source_name,
        "date_label": _date_label_from_iso(published),
    }
    if related_source_url:
        data_preview["related_source_url"] = related_source_url
        data_preview["related_links"] = [
            {"url": related_source_url, "label": f"関連投稿: {source_name}"}
        ]

    return RouteResult(
        matched=True,
        template_key=TEMPLATE_KEY_SHORT_NEWS_URL,
        tier=tier,
        extracted_facts=extracted,
        missing_facts=[],
        skip_reason="",
        dedupe_key=_dedupe_key(TEMPLATE_KEY_SHORT_NEWS_URL, primary_canonical),
        would_render_call={
            "renderer_func_name": "render_short_news_url_card",
            "data_preview": data_preview,
        },
        confidence=_confidence_for(TEMPLATE_KEY_SHORT_NEWS_URL, tier),
        canonical_url=primary_canonical,
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
    "is_x_post_url",
    "extract_external_article_url",
    "extract_video_source_url",
    "sanitize_short_news_title",
    "route_rss_entry_to_nomotoke_card",
    "derive_next_recommended",
    "derive_not_suitable_for_rss",
]
