"""MANUAL-INTAKE-001 pass-1 CLI.

Manually inject a URL / X URL / news URL into the YOSHILOVER pipeline as a WP
draft. The CLI never auto-publishes. Downstream jobs (guarded-publish,
publish-notice, draft-body-editor) pick up the draft via their existing WP
polling and source_url meta.

memo (--memo) is an operator-only note. It is NEVER:
  - written to entry["summary"]
  - injected into source_fact_block
  - included in any Gemini prompt
  - used as a fact source in body content

memo only appears in CLI stdout/stderr JSON output for audit.
Body grounding integrity is preserved.

Usage:
    python -m src.tools.manual_intake <url> [--memo "..."] [--mode draft|dry-run]
        [--title "..."] [--summary "..."] [--source-published-at "..."]
        [--article-type auto|試合結果|...]

Default --mode is "draft".

--source-published-at accepts an ISO 8601 timestamp. Naive strings are
treated as JST; "Z" / explicit UTC offsets are normalized to JST. The
normalized value is written to WP post meta under
``_yoshilover_source_published_at`` (see WPClient.SOURCE_PUBLISHED_AT_META_KEY)
so guarded-publish's freshness / source-time resolver can pick it up
directly from meta — without depending on body_date fallback. memo is
independent and still never reaches body / source_text / Gemini prompt.

--article-type pins category / subtype / template_key when the operator
overrides the auto detector. Allowed values: auto (default — keeps the
existing detector) plus the YOSHILOVER article-type taxonomy
(試合結果 / 試合速報 / 予告先発 / 公示 / 監督談話 / 選手コメント /
動画 / 成績 / 番組情報 / コラム / ニュース). The category name is never
sent to WP — it is resolved to a numeric category_id via
config/categories.json before WP write.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

JST = timezone(timedelta(hours=9), name="JST")

ROOT = Path(__file__).resolve().parent.parent.parent
_VENDOR = str(ROOT / "vendor")
_SRC = str(ROOT / "src")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


EXIT_OK = 0
EXIT_INVALID_URL = 10
EXIT_FETCH_FAILED = 11
EXIT_MISSING_TITLE_OR_SUMMARY = 12
EXIT_DUPLICATE = 13
EXIT_VALIDATION_FAILED = 14
EXIT_INVALID_SOURCE_PUBLISHED_AT = 15
EXIT_INVALID_ARTICLE_TYPE = 16
EXIT_WP_DRAFT_FAILED = 20
EXIT_DOWNSTREAM_HANDOFF_FAILED = 21
EXIT_RATE_LIMITED = 30
EXIT_UNEXPECTED = 2


# article_type override → (category_name, subtype, template_key).
# category_name MUST resolve to a numeric category_id via config/categories.json
# downstream — we never pass the raw name to WP. subtype values are kept
# conservative (they only steer template_key + freshness pipeline; they do
# not loosen any guarded-publish gate). "auto" sentinel triggers the
# existing _resolve_routing_lightweight detector.
ARTICLE_TYPE_AUTO = "auto"
# article_type override → (category_name, subtype, template_key).
#
# template_key values are the nomotoke renderer keys when the operator
# picks a specific type (NOMOTOKE-INTAKE-TEMPLATE-001). The actual body
# rendering happens later in ``_try_render_via_nomotoke`` — that helper
# falls back to the basic ``<p>summary</p>+出典`` shape when the chosen
# template's required-facts gate cannot be satisfied (e.g. monographer
# 「監督談話」 picked but the title carries no 「{監督名}「{quote}」」 pattern).
# So the operator's pick is always honoured for category / subtype but
# the body is degraded gracefully when facts are missing.
ARTICLE_TYPE_OVERRIDES: dict[str, tuple[str, str, str]] = {
    "試合結果": ("試合速報", "game_result", "nomotoke_card_short_news_url_v1"),
    "試合速報": ("試合速報", "postgame", "nomotoke_card_short_news_url_v1"),
    "予告先発": ("試合速報", "probable_starter", "nomotoke_card_pregame_pitcher_v1"),
    "公示": ("球団情報", "notice", "nomotoke_card_official_notice_v1"),
    "監督談話": ("首脳陣", "manager", "nomotoke_card_manager_comment_v1"),
    "選手コメント": ("選手情報", "comment", "nomotoke_card_player_comment_v1"),
    "動画": ("コラム", "program", "nomotoke_card_video_v1"),
    "成績": ("選手情報", "stats", "nomotoke_card_short_news_url_v1"),
    "番組情報": ("コラム", "program", "nomotoke_card_short_news_url_v1"),
    "コラム": ("コラム", "other", "nomotoke_card_short_news_url_v1"),
    "ニュース": ("コラム", "other", "nomotoke_card_short_news_url_v1"),
}
ARTICLE_TYPE_CHOICES: tuple[str, ...] = (
    ARTICLE_TYPE_AUTO,
    *ARTICLE_TYPE_OVERRIDES.keys(),
)


RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX = 5
DEFAULT_LOCKFILE = ROOT / "logs" / "manual_intake_throttle.json"
DEFAULT_CATEGORY_NAME = "コラム"

_X_HOSTS = {
    "twitter.com",
    "x.com",
    "www.twitter.com",
    "www.x.com",
    "mobile.twitter.com",
    "mobile.x.com",
}

_MIN_TITLE_CHARS = 8

_META_PATTERNS: tuple[tuple[str, str], ...] = (
    (r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', "title"),
    (r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']', "title"),
    (r'<meta\s+name=["\']twitter:title["\']\s+content=["\']([^"\']+)["\']', "title"),
    (r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', "summary"),
    (r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:description["\']', "summary"),
    (r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', "summary"),
    (r'<meta\s+name=["\']twitter:description["\']\s+content=["\']([^"\']+)["\']', "summary"),
    (r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', "image"),
    (r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', "image"),
    (r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', "image"),
)

_YAHOO_BOXSCORE_URL_RE = re.compile(
    r"^https?://baseball\.yahoo\.co\.jp/npb/game/\d+", re.IGNORECASE
)


def _normalize_article_type(value: str) -> tuple[str, str]:
    """Validate the article_type override.

    Returns (canonical_value, error_reason). Empty/None defaults to
    ARTICLE_TYPE_AUTO. Unknown values yield ("", "invalid_article_type").
    """
    raw = (value or "").strip()
    if not raw:
        return ARTICLE_TYPE_AUTO, ""
    if raw in ARTICLE_TYPE_CHOICES:
        return raw, ""
    return "", "invalid_article_type"


def _normalize_source_published_at(value: str) -> tuple[str, str]:
    """Parse an ISO 8601 timestamp and normalize to a JST ISO string.

    Matches `_parse_iso_to_jst` semantics used elsewhere:
    - empty/whitespace -> ("", "")
    - naive string -> JST attached
    - "Z" / UTC offset -> converted to JST
    - unparseable -> ("", "invalid_source_published_at")
    """
    raw = (value or "").strip()
    if not raw:
        return "", ""
    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except (TypeError, ValueError):
        return "", "invalid_source_published_at"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    else:
        parsed = parsed.astimezone(JST)
    return parsed.isoformat(), ""


def _is_valid_url(url: object) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_x_url(url: str) -> bool:
    if not _is_valid_url(url):
        return False
    return (urlparse(url).netloc or "").lower() in _X_HOSTS


def _normalize_x_url_to_twitter(url: str) -> str:
    return re.sub(r"://(www\.|mobile\.)?x\.com/", "://twitter.com/", url)


def _extract_x_status_id(url: str) -> str:
    match = re.search(r"/status(?:es)?/(\d+)", url or "")
    return match.group(1) if match else ""


def _domain_of(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


def _infer_source_name(url: str) -> str:
    domain = _domain_of(url)
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or "manual_intake"


def _check_rate_limit(lockfile: Path = DEFAULT_LOCKFILE) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds)."""
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    history: list[float] = []
    if lockfile.exists():
        try:
            data = json.loads(lockfile.read_text(encoding="utf-8"))
            if isinstance(data, list):
                history = [float(t) for t in data if isinstance(t, (int, float))]
        except Exception:
            history = []
    history = [t for t in history if (now - t) < RATE_LIMIT_WINDOW_SEC]
    if len(history) >= RATE_LIMIT_MAX:
        oldest = min(history)
        retry = int(RATE_LIMIT_WINDOW_SEC - (now - oldest)) + 1
        return False, max(retry, 1)
    history.append(now)
    lockfile.write_text(json.dumps(history), encoding="utf-8")
    return True, 0


def _parse_og_meta(html_text: str) -> dict[str, str]:
    title = ""
    summary = ""
    image = ""
    for pattern, key in _META_PATTERNS:
        if key == "title" and title:
            continue
        if key == "summary" and summary:
            continue
        if key == "image" and image:
            continue
        match = re.search(pattern, html_text, re.IGNORECASE)
        if match:
            value = html.unescape(match.group(1).strip())
            if key == "title":
                title = value
            elif key == "summary":
                summary = value
            elif key == "image":
                image = value
    if not title:
        match = re.search(r"<title>([^<]+)</title>", html_text, re.IGNORECASE)
        if match:
            title = html.unescape(match.group(1).strip())
    return {"title": title, "summary": summary, "image": image}


def _fetch_news_meta(url: str, *, timeout: float = 10.0) -> dict[str, str]:
    """Fetch source URL and return OG meta + raw HTML.

    Returns ``{"title": ..., "summary": ..., "image": ..., "_html": ...}``
    on success, ``{"_error": "..."}`` on failure. The ``_html`` field
    carries the raw decoded body (capped at 800 KB) so callers that need
    full-page parsing (e.g. Yahoo Sportsnavi boxscore for
    ``nomotoke_card_postgame_v1``) can reuse the same fetch instead of
    issuing a second GET. Existing callers that read by key only
    (``title`` / ``summary``) remain unaffected.
    """
    try:
        import urllib.request
    except Exception as exc:
        return {"_error": f"urllib_unavailable:{exc}"}
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; yoshilover-manual-intake/1)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read(800_000)
    except Exception as exc:
        return {"_error": f"fetch_failed:{exc.__class__.__name__}"}
    text = content.decode("utf-8", errors="replace")
    meta = _parse_og_meta(text)
    meta["_html"] = text
    return meta


def _build_body_for_x(canonical_url: str) -> str:
    safe = html.escape(canonical_url)
    return (
        f'<blockquote class="twitter-tweet" data-lang="ja">'
        f'<a href="{safe}"></a></blockquote>\n'
        '<script async src="https://platform.twitter.com/widgets.js" '
        'charset="utf-8"></script>\n'
    )


def _build_body_for_news(
    source_url: str,
    title: str,
    summary: str,
    *,
    og_image: str = "",
) -> str:
    parts: list[str] = []
    # NOMOTOKE-INTAKE-HERO-001: prepend OG image as hero figure so the
    # legacy fallback body also presents like a card. Same safety gate
    # as the nomotoke path.
    if og_image and _is_safe_https_image_url(og_image):
        safe_img = html.escape(og_image)
        safe_alt = html.escape(title or "")
        parts.append(
            '<figure class="nomotoke-hero">'
            f'<img src="{safe_img}" alt="{safe_alt}" loading="lazy">'
            "</figure>"
        )
    if summary:
        parts.append(f"<p>{html.escape(summary)}</p>")
    label = title or source_url
    parts.append(
        f'<p>出典: <a href="{html.escape(source_url)}" target="_blank" '
        f'rel="noopener">{html.escape(label)}</a></p>'
    )
    return "\n".join(parts)


# NOMOTOKE-INTAKE-NOTICE-001: official_notice extractor (no LLM, no
# Gemini). Conservative — falls back to short_news_url unless the title
# explicitly carries a 公示 keyword AND at least one player name maps
# cleanly to ``を(登録|抹消|昇格|降格)``. False positives would put a
# wrong name on a public draft, so the gate is intentionally tight.

_NOTICE_KEYWORD_RE = re.compile(
    r"(公示|出場選手登録|出場選手抹消|登録抹消|支配下登録|"
    r"育成契約|自由契約|現役ドラフト)"
)
# Player-name prefix is the chunk leading up to ``を{action}``. Stop the
# capture at common Japanese delimiters so we never absorb sentence
# fragments. 4-12 chars covers 3-char given names and 漢字 + カタカナ
# stage names without reaching into the next sentence.
_NOTICE_REGISTER_RE = re.compile(
    r"(?P<prefix>[^\s、。「」『』【】（）()／/]{2,12})"
    r"を(?:1軍|一軍|二軍|支配下|出場選手)?(?:選手)?登録"
)
_NOTICE_REMOVE_RE = re.compile(
    r"(?P<prefix>[^\s、。「」『』【】（）()／/]{2,12})"
    r"を(?:1軍|一軍|二軍|支配下|出場選手)?(?:選手)?(?:登録)?抹消"
)
# Skip captures that look like phrases instead of names. A real player
# name ends in a kanji / katakana run; common particles or function
# words at the tail are filtered.
_NOTICE_NAME_TAIL_REJECT_RE = re.compile(r"(?:した|する|ため|として|ことを|ことが|あり)$")
# Reject leading particles + known non-name fragments.
_NOTICE_NAME_HEAD_REJECT_RE = re.compile(r"^(?:と|や|から|まで|など|さらに)")


def _split_notice_names(prefix: str) -> list[str]:
    """Split a captured prefix into one or more player names.

    The capture is only the chunk preceding ``を{action}``; the typical
    headline form 「巨人公示】◯◯と△△を1軍登録、□□は抹消」 places the
    name list immediately before the verb. Splitting on common list
    delimiters (``、`` / ``と`` / ``や`` / ``,``) gives us back the
    individual names. We then drop anything that fails the
    name-shape sanity checks.
    """
    if not prefix:
        return []
    rough = re.split(r"[、,]|\s*と\s*|\s*や\s*", prefix)
    names: list[str] = []
    for chunk in rough:
        n = chunk.strip()
        if not n:
            continue
        if len(n) < 2 or len(n) > 8:
            continue
        if _NOTICE_NAME_TAIL_REJECT_RE.search(n):
            continue
        if _NOTICE_NAME_HEAD_REJECT_RE.search(n):
            continue
        # Names are kanji / katakana / hiragana. Pure alphanumerics are
        # unlikely to be a real name and are dropped.
        if re.fullmatch(r"[A-Za-z0-9]+", n):
            continue
        names.append(n)
    # De-dupe preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        uniq.append(n)
    return uniq[:6]


def _parse_manual_name_list(raw: str) -> list[str]:
    """Split an operator-supplied name list into a clean list[str].

    Accepts comma / 、 / newline / whitespace separators. Each name is
    trimmed; entries shorter than 2 chars or longer than 8 chars are
    dropped because they almost certainly are not a player name and
    would skew the rendered card.
    """
    if not raw or not isinstance(raw, str):
        return []
    rough = re.split(r"[、,\n\r]+|\s{2,}", raw)
    out: list[str] = []
    seen: set[str] = set()
    for chunk in rough:
        n = chunk.strip()
        if not n:
            continue
        if len(n) < 2 or len(n) > 8:
            continue
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out[:8]


def _extract_official_notice_facts(
    title: str, summary: str, og_description: str
) -> dict[str, Any]:
    """Return ``{action, registered, removed}`` when the input clearly
    matches a 公示 announcement, else ``{}``.

    Conservative: requires a 公示 keyword in title + summary +
    og_description (combined) AND at least one extractable name.
    """
    text = "\n".join(s for s in (title, summary, og_description) if s)
    if not text:
        return {}
    if not _NOTICE_KEYWORD_RE.search(text):
        return {}

    registered: list[str] = []
    removed: list[str] = []
    for m in _NOTICE_REGISTER_RE.finditer(text):
        registered.extend(_split_notice_names(m.group("prefix")))
    for m in _NOTICE_REMOVE_RE.finditer(text):
        # The "remove" pattern also matches strings that end ``登録`` (no
        # 抹消). We disambiguate by re-checking that the matched verb
        # really included 抹消.
        snippet = text[m.start(): m.end()]
        if "抹消" not in snippet:
            continue
        removed.extend(_split_notice_names(m.group("prefix")))

    # A name appearing in BOTH register + remove is almost certainly a
    # parse mistake (the two regexes overlap). Drop overlaps from the
    # less-confident side (registered) since 抹消 is the more specific
    # keyword.
    overlap = set(registered) & set(removed)
    registered = [n for n in registered if n not in overlap]

    if not (registered or removed):
        return {}

    if registered and removed:
        action = "swap"
    elif registered:
        action = "register"
    else:
        action = "remove"

    return {
        "action": action,
        "registered": registered,
        "removed": removed,
    }


def _date_label_from_iso(iso: str) -> str:
    """Render an ISO 8601 timestamp into a Japanese ``YYYY年M月D日`` label.

    The renderers all use this format (NOMOTOKE-DATELABEL-FIX) so date
    metadata never leaks ``YYYY-MM-DD`` style ``\\d{1,2}-\\d{1,2}``
    patterns into the body and confuse the score-consistency tokenizer.
    """
    if not iso:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", iso)
    if not m:
        return ""
    return f"{int(m.group(1))}年{int(m.group(2))}月{int(m.group(3))}日"


_YOUTUBE_HOST_RE = re.compile(
    r"^https?://(?:www\.|m\.|mobile\.)?(?:youtube\.com|youtu\.be)/", re.IGNORECASE
)
_YOUTUBE_WATCH_RE = re.compile(
    r"^https?://(?:www\.)?youtube\.com/watch\?v=[A-Za-z0-9_-]{6,}", re.IGNORECASE
)


def _normalize_youtube_url(url: str) -> str:
    """Convert any YouTube URL form to the canonical
    ``https://www.youtube.com/watch?v=<id>`` shape so the video_v1
    renderer's URL gate accepts it.

    Supports: ``youtu.be/<id>``, ``youtube.com/shorts/<id>``,
    ``youtube.com/live/<id>``, ``m.youtube.com/...``,
    ``mobile.youtube.com/...``. Returns the original URL unchanged
    when it does not look like YouTube (the caller's gate then drops
    it). Query parameters other than ``v`` are stripped — they are
    irrelevant to the video card and would only widen the surface
    area for cache-key drift.
    """
    if not isinstance(url, str) or not url:
        return url
    if not _YOUTUBE_HOST_RE.match(url):
        return url
    # Already canonical.
    if _YOUTUBE_WATCH_RE.match(url):
        m = re.match(r"^(https?://(?:www\.)?youtube\.com/watch\?v=)([A-Za-z0-9_-]+)", url, re.IGNORECASE)
        if m:
            return m.group(1) + m.group(2)
        return url
    m = re.search(r"youtu\.be/([A-Za-z0-9_-]{6,})", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    m = re.search(r"youtube\.com/(?:shorts|live|embed|v)/([A-Za-z0-9_-]{6,})", url, re.IGNORECASE)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def _try_render_via_nomotoke(
    template_key: str,
    *,
    title: str,
    summary: str,
    source_url: str,
    source_name: str,
    source_published_at_iso: str,
    is_x: bool,
    og_image: str = "",
    raw_html: str = "",
    manual_facts: dict[str, str] | None = None,
) -> str | None:
    """Render the manual-intake submission with the matching nomotoke
    renderer when the operator's article_type pick maps to a nomotoke
    template_key. Returns the rendered HTML on success, ``None`` when
    the template's required-fact gate could not be satisfied (caller
    falls back to the basic ``<p>summary</p>+出典`` shape).

    Source-only: every field passed into the renderer comes from OG
    fetch / RSS title-summary regex / the operator's own URL — no
    fabrication. The renderer's own gates (body_too_thin, missing
    quote / pitcher pair, etc.) decide whether the richer template is
    appropriate; if not, we degrade gracefully so the operator's
    article_type pick is never a hard block.

    NOMOTOKE-INTAKE-POSTGAME-001: when the operator pasted a Yahoo
    Sportsnavi NPB game URL, the short_news_url template_key gets
    auto-upgraded to ``nomotoke_card_postgame_v1`` and the boxscore
    facts (score / inning_score / matchup_header / date_label) are
    parsed via ``parse_yahoo_game_html`` from the already-fetched raw
    HTML — no additional network call.

    NOMOTOKE-INTAKE-HERO-001: ``og_image`` (when set) is prepended as a
    ``<figure>`` so news-source posts present like a card with a hero
    image, mirroring the visual richness of the X embed body. The
    figure is added AFTER the renderer returns so the renderer's
    source-fact contract is unchanged.
    """
    mf = manual_facts or {}
    if not template_key.startswith("nomotoke_card_"):
        return None
    # X-only entries cannot use the nomotoke short_news_url path because
    # the router would skip with x_post_not_article_source. The plain
    # X embed body is the right shape for those.
    if is_x:
        return None

    # NOMOTOKE-INTAKE-YOUTUBE-NORMALIZE-001: accept all YouTube URL
    # forms (youtu.be / shorts / live) by normalising to the canonical
    # watch URL the video_v1 renderer requires.
    source_url = _normalize_youtube_url(source_url)

    # NOMOTOKE-INTAKE-POSTGAME-001: Yahoo Sportsnavi NPB game URL is the
    # only RSS-pool-external source whose HTML we can parse into a
    # complete postgame card. Auto-upgrade so 試合結果 / 試合速報 picks
    # resolve to the richer template when the URL allows it.
    if (
        template_key == "nomotoke_card_short_news_url_v1"
        and source_url
        and _YAHOO_BOXSCORE_URL_RE.match(source_url)
    ):
        template_key = "nomotoke_card_postgame_v1"

    try:
        os.environ.setdefault("ENABLE_NOMOTOKE_CARD_TEMPLATES", "1")
        from src.nomotoke_card_renderer import select_renderer
    except Exception:
        return None

    date_label = _date_label_from_iso(source_published_at_iso)
    data: dict[str, Any] = {}

    if template_key == "nomotoke_card_short_news_url_v1":
        data = {
            "title": title,
            "summary": summary,
            "source_url": source_url,
            "source_name": source_name or "出典",
            "date_label": date_label,
        }

    elif template_key == "nomotoke_card_postgame_v1":
        # Yahoo Sportsnavi boxscore is the only supported source. The
        # extractor returns None when any required field is missing so
        # the caller falls back gracefully.
        if not raw_html:
            return None
        try:
            from src.source_yahoo_boxscore_extractor import (
                parse_yahoo_game_html,
            )
        except Exception:
            return None
        facts_obj = parse_yahoo_game_html(raw_html)
        if facts_obj is None:
            return None
        data = facts_obj.giants_facts()
        if not data:
            return None
        data["source_url"] = source_url
        data["source_name"] = source_name or "Yahoo!スポーツ"

    elif template_key == "nomotoke_card_official_notice_v1":
        # NOMOTOKE-INTAKE-NOTICE-001: opportunistic extraction from
        # title + summary + raw_html. Falls back to short_news_url
        # gracefully when the extractor cannot find a clean
        # ``を(登録|抹消)`` pattern.
        og_text = ""
        if raw_html:
            m = re.search(
                r'<meta\s+[^>]*?(?:property|name)=["\'](?:og:description|twitter:description|description)["\']'
                r'\s+content=["\']([^"\']+)["\']',
                raw_html,
                re.IGNORECASE,
            )
            if m:
                og_text = html.unescape(m.group(1))
        notice = _extract_official_notice_facts(title, summary, og_text)
        # Operator overrides: comma / 、 / newline-separated lists win
        # over regex extraction so a 公示 article whose headline does
        # not encode names cleanly still produces a real card.
        manual_registered = _parse_manual_name_list(mf.get("registered", ""))
        manual_removed = _parse_manual_name_list(mf.get("removed", ""))
        if manual_registered or manual_removed:
            registered = manual_registered
            removed = manual_removed
            if registered and removed:
                action = "swap"
            elif registered:
                action = "register"
            else:
                action = "remove"
        elif notice:
            registered = notice["registered"]
            removed = notice["removed"]
            action = notice["action"]
        else:
            return None
        if not date_label:
            return None
        if not (registered or removed):
            return None
        # NOMOTOKE-INTAKE-NPB-OFFICIAL-001 (N2): always link to NPB公式
        # 公示ページ. The path varies by date but the year-based
        # landing page is stable; readers click to the year directory
        # and find the specific date page. The renderer emits this as
        # 「NPB公式公示: <a>NPB公式 公示ページ</a>」.
        npb_year = ""
        m_year = re.match(r"^(\d{4})年", date_label or "")
        if m_year:
            npb_year = m_year.group(1)
        data = {
            "team_name": "巨人",
            "action": action,
            "date_label": date_label,
            "registered": registered,
            "removed": removed,
            "source_url": source_url,
            "source_name": source_name or "出典",
            "official_url": (
                f"https://npb.jp/announcement/{npb_year}/" if npb_year else "https://npb.jp/announcement/"
            ),
            "official_url_label": "NPB公式 公示ページ",
        }

    if template_key == "nomotoke_card_video_v1":
        # Only YouTube watch URLs satisfy the renderer's video_url field.
        if not source_url or "youtube.com/watch?v=" not in source_url:
            return None
        try:
            from src.source_youtube_extractor import (
                YouTubeFeedEntry,
                extract_video_card_facts,
            )
        except Exception:
            return None
        e = YouTubeFeedEntry(
            video_id="",
            video_url=source_url,
            title=title,
            published_at=source_published_at_iso,
            channel_name=source_name,
            description=summary,
        )
        data = extract_video_card_facts(e, team_name="巨人")
        # NOMOTOKE-INTAKE-MANUAL-FACTS-001: operator-supplied overrides
        # win over auto-extraction so a video card still renders when
        # the YouTube description does not include the player name or
        # a clean play summary.
        if mf.get("player_name"):
            data["player_name"] = mf["player_name"]
        if mf.get("play_summary"):
            data["play_summary"] = mf["play_summary"]
        # Renderer requires player_name + play_summary; otherwise fall back.
        if not data.get("player_name") or not data.get("play_summary"):
            return None

    elif template_key == "nomotoke_card_manager_comment_v1":
        try:
            from src.nomotoke_rss_router import (
                MANAGER_NAME_ALLOWLIST,
                extract_manager_quote,
            )
        except Exception:
            return None
        mq = extract_manager_quote(title, summary)
        manager_name = mq.get("manager_name") or ""
        quote_short = mq.get("quote_short") or ""
        topic = mq.get("topic") or ""
        # NOMOTOKE-INTAKE-MANUAL-FACTS-001: operator overrides win.
        # The expanded MANAGER_NAME_ALLOWLIST already covers the
        # current 2026 staff, but a manual ``manager_name`` lets the
        # operator land a quote from a name that is not on the
        # allowlist (e.g. retired coach guest commentary).
        if mf.get("manager_name"):
            manager_name = mf["manager_name"]
        if mf.get("quote"):
            quote_short = mf["quote"][:100]
        if not manager_name:
            return None
        # Manual override path bypasses the allowlist gate — the
        # operator has explicitly attributed the quote.
        if not mf.get("manager_name") and manager_name not in MANAGER_NAME_ALLOWLIST:
            return None
        if not quote_short:
            return None
        data = {
            "team_name": "巨人",
            "manager_name": manager_name,
            "topic": topic or quote_short[:30],
            "quote_short": quote_short,
            "source_url": source_url,
            "source_name": source_name or "出典",
            "published_at": source_published_at_iso,
            "date_label": date_label,
        }

    elif template_key == "nomotoke_card_player_comment_v1":
        try:
            from src.nomotoke_rss_router import extract_player_quote
        except Exception:
            return None
        pq = extract_player_quote(title, summary)
        player_name = pq.get("player_name") or ""
        quote_short = pq.get("quote_short") or ""
        # Operator overrides win.
        if mf.get("player_name"):
            player_name = mf["player_name"]
        if mf.get("quote"):
            quote_short = mf["quote"][:100]
        if not player_name or not quote_short:
            return None
        data = {
            "team_name": "巨人",
            "player_name": player_name,
            "topic": quote_short[:30],
            "quote_short": quote_short,
            "source_url": source_url,
            "source_name": source_name or "出典",
            "published_at": source_published_at_iso,
            "date_label": date_label,
        }

    elif template_key == "nomotoke_card_pregame_pitcher_v1":
        try:
            from src.nomotoke_rss_router import detect_pregame_pitcher
        except Exception:
            return None
        pre = detect_pregame_pitcher(title, summary)
        pair = pre.get("pitcher_pair") if pre.get("keyword_present") else None
        # Operator overrides win.
        pitcher_a = mf.get("pitcher_a") or (pair[0] if pair else "")
        pitcher_b = mf.get("pitcher_b") or (pair[1] if pair else "")
        team_b = mf.get("team_b") or "対戦相手"
        if not pitcher_a or not pitcher_b:
            return None
        data = {
            "date_label": date_label,
            "official_url": source_url,
            "matchups": [
                {
                    "team_a": "巨人",
                    "pitcher_a": pitcher_a,
                    "team_b": team_b,
                    "pitcher_b": pitcher_b,
                }
            ],
            "source_url": source_url,
            "source_name": source_name or "出典",
        }

    else:
        return None

    # NOMOTOKE-INTAKE-ROSTER-ASIDE-001 Phase 2: roster aside is now
    # default-on at the renderer level (flag-gating removed). The
    # renderer still emits the aside only when at least one name
    # maps to a roster entry, so the behaviour is identical to the
    # Phase 1 manual-intake path while RSS pipeline posts now also
    # benefit automatically.
    try:
        renderer = select_renderer(template_key)
    except Exception:
        return None
    try:
        result = renderer(data)
    except Exception:
        return None
    if not result.get("validation_ok"):
        return None
    rendered = result.get("content_html") or ""
    if not rendered:
        return None
    # NOMOTOKE-INTAKE-HERO-001: prepend the source page's og:image as a
    # hero figure for templates that benefit from card-style framing.
    # Skipped for video / quote-comment / pregame_pitcher: those carry
    # their own visual centre (YouTube embed / quote block / matchup
    # card) and a stacked OG image would be redundant.
    if og_image and _is_safe_https_image_url(og_image) and template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
    ):
        safe_img = html.escape(og_image)
        safe_alt = html.escape(title or source_name or "")
        figure = (
            '<figure class="nomotoke-hero">'
            f'<img src="{safe_img}" alt="{safe_alt}" loading="lazy">'
            "</figure>\n"
        )
        rendered = figure + rendered
    # NOMOTOKE-INTAKE-BODY-EXCERPT-001: insert a literal-substring
    # 「📖 本文抜粋」 block (≤240 chars) lifted from the source HTML.
    # No LLM, no fabrication — the extractor returns ``""`` whenever
    # the body cannot be parsed cleanly, in which case the rendered
    # body is unchanged. Only short_news_url + postgame currently get
    # the block; comment / video / pregame templates already carry the
    # primary 引用 (quote / play / matchup) and an extra paragraph
    # would dilute focus.
    if raw_html and template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
    ):
        try:
            from src.source_article_body_extractor import (
                extract_article_body_excerpt,
            )
        except Exception:
            extract_article_body_excerpt = None  # type: ignore
        if extract_article_body_excerpt is not None:
            try:
                excerpt = extract_article_body_excerpt(
                    raw_html, source_url, title=title, max_chars=240
                )
            except Exception:
                excerpt = ""
            if excerpt:
                rendered = _insert_body_excerpt_block(
                    rendered, excerpt, source_name
                )

    # NOMOTOKE-INTAKE-WP-CROSSLINK-001: 関連記事 / 直近の試合 / 対戦成績
    # blocks pulled from internal WP REST. Each helper returns ``""``
    # when no usable hit, so downstream behaviour stays graceful when
    # the WP host is unreachable or empty.
    extra_blocks: list[str] = []

    related_query = ""
    for cand in (mf.get("manager_name"), mf.get("player_name")):
        if cand:
            related_query = cand
            break
    if not related_query and template_key == "nomotoke_card_postgame_v1":
        related_query = data.get("home", "") if isinstance(data, dict) else ""
    if not related_query and title:
        # Pick the longest 漢字 / カタカナ run from the title (>=2 chars)
        # — usually a player name or team name. Plain heuristic, no LLM.
        ngrams = re.findall(r"[一-龥ぁ-んァ-ヶー]{2,8}", title)
        related_query = max(ngrams, key=len) if ngrams else ""
    if related_query and template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_manager_comment_v1",
        "nomotoke_card_player_comment_v1",
        "nomotoke_card_video_v1",
        "nomotoke_card_pregame_pitcher_v1",
        "nomotoke_card_official_notice_v1",
    ):
        block = _build_related_articles_block(related_query)
        if block:
            extra_blocks.append(block)

    if template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_pregame_pitcher_v1",
    ):
        block = _build_recent_games_block()
        if block:
            extra_blocks.append(block)

    # NOMOTOKE-INTAKE-LINEUP-001: fetch the Yahoo Sportsnavi preview
    # page and parse out the starting lineup tables. Applied only to
    # postgame_v1 (where the source URL is already a Yahoo /index).
    # Single 6-second GET; returns empty on any failure so the
    # rendered body stays unchanged.
    if template_key == "nomotoke_card_postgame_v1":
        preview_url = _derive_yahoo_preview_url(source_url)
        if preview_url:
            preview_html = _fetch_yahoo_lineup_html(preview_url)
            if preview_html:
                try:
                    from src.source_yahoo_lineup_extractor import (
                        parse_yahoo_lineup_html,
                    )
                except Exception:
                    parse_yahoo_lineup_html = None  # type: ignore
                if parse_yahoo_lineup_html is not None:
                    try:
                        home_lu, away_lu = parse_yahoo_lineup_html(preview_html)
                    except Exception:
                        home_lu, away_lu = [], []
                    block = _build_lineup_block(home_lu, away_lu)
                    if block:
                        extra_blocks.append(block)

    if template_key == "nomotoke_card_postgame_v1" and isinstance(data, dict):
        away = (data.get("away") or "").strip()
        home = (data.get("home") or "").strip()
        opponent = ""
        for cand in (away, home):
            if cand and not any(g in cand for g in ("巨人", "ジャイアンツ", "読売")):
                opponent = cand
                break
        if opponent:
            block = _build_matchup_record_block(opponent)
            if block:
                extra_blocks.append(block)

    # NOMOTOKE-INTAKE-NEXT-GAME-001 (G4) + STANDINGS-001 (C4):
    # game-related templates pull the next Giants game (Yahoo) and
    # the current Central League standings (NPB.jp). Cached for 6h
    # per Cloud Run instance — first request after cold start
    # triggers ≤2 extra GETs, subsequent requests within 6h are free.
    if template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_pregame_pitcher_v1",
        "nomotoke_card_manager_comment_v1",
        "nomotoke_card_player_comment_v1",
    ):
        block = _build_standings_block()
        if block:
            extra_blocks.append(block)
        block = _build_next_game_block()
        if block:
            extra_blocks.append(block)

    # NOMOTOKE-INTAKE-JSONLD-META-001: the 「📅 掲載日 by 著者」 meta
    # line for short_news_url + postgame. Empty when JSON-LD lacks
    # both author and datePublished.
    if raw_html and template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
    ):
        block = _build_jsonld_meta_block(raw_html, source_name)
        if block:
            extra_blocks.append(block)

    # NOMOTOKE-INTAKE-PLAYER-STATS-001 (A) + DEDUP-D1: unified
    # 「🏷 関連選手」 block. Builds jersey + position + name + season
    # stats on a single row per player, replacing the standalone
    # roster aside. When this block fires, the renderer-emitted
    # ``<aside class="nomotoke-roster">...`` is stripped from the
    # rendered body to avoid duplication.
    scan_text = " ".join(s for s in (title, summary) if s)
    player_stats_block = ""
    if scan_text and template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_manager_comment_v1",
        "nomotoke_card_player_comment_v1",
        "nomotoke_card_video_v1",
        "nomotoke_card_pregame_pitcher_v1",
        "nomotoke_card_official_notice_v1",
    ):
        player_stats_block = _build_player_stats_block(scan_text)
        if player_stats_block:
            extra_blocks.append(player_stats_block)
            # Strip the renderer's standalone roster aside — the
            # unified block already carries the same names with extra
            # stats columns.
            rendered = re.sub(
                r'<aside class="nomotoke-roster">.*?</aside>',
                "",
                rendered,
                count=1,
                flags=re.DOTALL,
            )

    # NOMOTOKE-INTAKE-DEDUP-D2: 「直近の試合速報」 (B) was visually
    # redundant with 「直近の試合」 (G2). G2 already lists the most
    # recent 5 試合速報 posts; the standalone 1-line snippet has been
    # removed.

    # NOMOTOKE-INTAKE-AUTHOR-OTHER-001 (D): "this reporter's other
    # articles" cluster. Only when JSON-LD provided an author.
    if raw_html:
        author, _ = _extract_jsonld_author_and_date(raw_html)
        if author:
            block = _build_author_other_articles_block(author)
            if block:
                extra_blocks.append(block)

    # NOMOTOKE-INTAKE-NOTICE-TIMELINE-001 (E) — D4 restriction:
    # 直近の公示 list rendered ONLY inside official_notice posts.
    # Previously it surfaced in short_news_url too, which felt random
    # on game / 監督談話 / video coverage.
    if template_key == "nomotoke_card_official_notice_v1":
        block = _build_recent_notice_timeline_block()
        if block:
            extra_blocks.append(block)

    # NOMOTOKE-INTAKE-OTHERGAMES-001 (N3) — D6 restriction:
    # 当日の他試合 list ONLY on postgame posts, where the reader is
    # already in game-mode and league context is most relevant.
    if template_key == "nomotoke_card_postgame_v1":
        block = _build_other_games_block()
        if block:
            extra_blocks.append(block)

    # NOMOTOKE-INTAKE-DEDUP-D3: 「シリーズ tracker」 (N4) was
    # redundant with 「今季対戦成績」 (G3) which already lists the
    # 5 most recent vs the same opponent — the シリーズ window
    # (±4 days) is a strict subset of those 5 entries. Removed; G3
    # carries the same information.

    # NOMOTOKE-INTAKE-X-EMBED-001 (R-X1): related X posts pulled from
    # the operator's existing rsshub feeds — closes the largest
    # remaining gap with dnomotoke.com which embeds 2-5 X posts per
    # article. Costs ¥0 (rsshub feed reads are internal).
    if template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_manager_comment_v1",
        "nomotoke_card_player_comment_v1",
        "nomotoke_card_pregame_pitcher_v1",
        "nomotoke_card_video_v1",
        "nomotoke_card_official_notice_v1",
    ):
        block = _build_x_embeds_block(title, summary)
        if block:
            extra_blocks.append(block)

    # NOMOTOKE-INTAKE-TRUST-001 (N1): AI 不使用 badge — applied to
    # every nomotoke template so the badge consistently anchors the
    # post to its source.
    if template_key.startswith("nomotoke_card_"):
        block = _build_trust_badge_block(source_name, source_url)
        if block:
            extra_blocks.append(block)

    if extra_blocks:
        rendered = _insert_blocks_before_source_h3(rendered, extra_blocks)

    # NOMOTOKE-INTAKE-READER-UX-001: reader-side UX layer.
    # Order:
    #   1. Inject anchor IDs into known asides (R1 ToC targets).
    #   2. Build the meta header bar (R3) + ToC (R1).
    #   3. Wrap roster names in the lead (R4).
    #   4. Append tag chips at end (R6).
    if template_key.startswith("nomotoke_card_"):
        # Step 1 + 2: ToC anchors + ToC + meta header + share buttons
        # + TOP コメント CTA (operator request: 上部に
        # 「コメントする」 を持ち上げ).
        rendered, toc_entries = _inject_toc_anchors(rendered)
        toc_html = _build_toc_block(toc_entries)
        meta_html = _build_meta_header_bar(
            rendered, normalized_source_published_at
        )
        share_top = _build_share_buttons_block(source_url_fallback=source_url)
        # Big orange comment CTA right under the read-time bar so
        # the comment form (#respond) is one tap away even before
        # the reader scrolls into the body.
        top_cta = (
            '<p class="nomotoke-cta-row" '
            'style="margin:8px 0 12px;text-align:center;">'
            '<a href="#respond" '
            'style="display:inline-block;padding:10px 22px;'
            "background:#f57f17;color:#fff;text-decoration:none;"
            "border-radius:8px;font-weight:700;font-size:15px;"
            'box-shadow:0 2px 6px rgba(245,127,23,0.4);">'
            "💬 この記事にコメントする"
            "</a></p>"
        )
        header_payload = ""
        if meta_html:
            header_payload += meta_html
        header_payload += top_cta
        if share_top:
            header_payload += share_top
        if toc_html:
            header_payload += toc_html
        if header_payload:
            rendered = header_payload + rendered

        # Step 3: lead-only auto-link
        rendered = _wrap_first_roster_names_in_lead(rendered)

        # Step 4: tag chips at bottom (after the existing footer would
        # be appended). The footer is added by ``_result_payload``
        # AFTER the renderer returns, so we append chips here, just
        # before the source-link H3 → wait, actually the footer comes
        # from result_payload's "footer_html" path. The cleanest spot
        # for chips is after the existing rendered body but before
        # the source H3 (so they sit alongside the rest of the
        # discovery blocks).
        chip_block = _build_tag_chip_block(
            title=title,
            summary=summary,
            content_html=rendered,
            category=data.get("category", "") if isinstance(data, dict) else "",
        )
        if chip_block:
            rendered = _insert_blocks_before_source_h3(rendered, [chip_block])

        # NOMOTOKE-INTAKE-SHARE-BUTTONS-001 (R-X2 bottom): second
        # share-buttons block above the source-link section. Audit
        # fix A: emit the visual block only — the top block already
        # carries the script and its handlers cover both blocks.
        rendered = _insert_blocks_before_source_h3(
            rendered, [_build_share_buttons_block(with_script=False)]
        )

        # NOMOTOKE-INTAKE-EMOJI-DECORATE-001: factual-keyword emoji
        # sprinkle. Runs BEFORE the JSON-LD schema is appended so the
        # script payload (which contains JSON, not display text) is
        # never decorated.
        rendered = _decorate_body_with_emoji(rendered)

        # NOMOTOKE-INTAKE-JSONLD-EMIT-001 (N2): NewsArticle schema for
        # search engine rich snippets. Appended at the very end of
        # the body so it's the last script-like content WP serves.
        schema_block = _build_jsonld_article_schema(
            title=title,
            summary=summary,
            source_url=source_url,
            source_name=source_name,
            source_published_at_iso=source_published_at_iso,
            og_image=og_image,
            raw_html=raw_html,
        )
        if schema_block:
            rendered = rendered + schema_block

    return rendered or None


def _insert_blocks_before_source_h3(rendered_html: str, blocks: list[str]) -> str:
    """Insert a list of HTML blocks just before the 出典記事 H3 anchor,
    or append them at the end when the anchor is not present."""
    if not blocks:
        return rendered_html
    payload = "\n".join(blocks) + "\n"
    anchor = "<h3>🔗 出典記事</h3>"
    if anchor in rendered_html:
        return rendered_html.replace(anchor, payload + anchor, 1)
    return rendered_html + payload


def _insert_body_excerpt_block(
    rendered_html: str, excerpt: str, source_name: str
) -> str:
    """Inject the 引用 excerpt block into the rendered body.

    Position: just before the ``<h3>🔗 出典記事</h3>`` heading the
    short_news_url renderer emits, so the reader sees:

        [lead] → [fact card] → [本文抜粋] → [出典記事 link]

    For postgame and any future template without that heading, the
    block is appended at the end. ``source_name`` lands in the
    attribution line (``— {source_name}`` 出典).
    """
    safe_excerpt = html.escape(excerpt).replace("\n", "<br>")
    safe_source = html.escape(source_name or "出典")
    block = (
        '<aside class="nomotoke-source-excerpt">'
        '<p class="nomotoke-source-excerpt__label">📖 本文抜粋</p>'
        f'<blockquote class="nomotoke-source-excerpt__body">'
        f"{safe_excerpt}"
        "</blockquote>"
        f'<p class="nomotoke-source-excerpt__attr">— {safe_source}</p>'
        "</aside>\n"
    )
    anchor = "<h3>🔗 出典記事</h3>"
    if anchor in rendered_html:
        return rendered_html.replace(anchor, block + anchor, 1)
    return rendered_html + block


# NOMOTOKE-INTAKE-WP-CROSSLINK-001: read-only WP REST client for the
# 「関連記事」 / 「直近の試合」 / 「対戦成績」 enrichment blocks. Uses
# unauthenticated GET against the public posts endpoint — published
# posts are visible without auth, draft posts intentionally excluded.

_WP_REST_TIMEOUT_SEC = 6
_GAME_SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-‐−–—ー]\s*(\d{1,2})(?!\d)")


def _wp_query_public_posts(
    *,
    search: str = "",
    categories: list[int] | None = None,
    limit: int = 5,
    after: str = "",
) -> list[dict[str, Any]]:
    """Return a list of published posts matching the query. Empty list
    on any failure — the caller treats this as 「該当なし」 and skips
    the related block, never raising."""
    base = (os.environ.get("WP_URL") or "").strip().rstrip("/")
    if not base:
        return []
    try:
        import urllib.request
        import urllib.parse
    except Exception:
        return []
    params: list[tuple[str, str]] = [
        ("status", "publish"),
        ("per_page", str(max(1, min(limit, 50)))),
        ("orderby", "date"),
        ("order", "desc"),
        # NOMOTOKE-INTAKE-COMMENT-COUNT-001 (F): comment_count in the
        # response so cross-link blocks can render 「💬 N」 next to
        # each title. WP returns 0 when comments are closed or absent.
        ("_fields", "id,title,link,date,categories,comment_count"),
    ]
    if search.strip():
        params.append(("search", search.strip()))
    if categories:
        params.append(("categories", ",".join(str(c) for c in categories if c)))
    if after.strip():
        params.append(("after", after.strip()))
    qs = urllib.parse.urlencode(params)
    url = f"{base}/wp-json/wp/v2/posts?{qs}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "yoshilover-manual-intake/1",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=_WP_REST_TIMEOUT_SEC) as resp:
            content = resp.read(400_000)
    except Exception:
        return []
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return data


def _format_jp_date(iso_date: str) -> str:
    """Render an ISO 8601 / WP date string as ``M/D``. Empty on failure."""
    if not iso_date or not isinstance(iso_date, str):
        return ""
    m = re.match(r"^\d{4}-(\d{2})-(\d{2})", iso_date)
    if not m:
        return ""
    return f"{int(m.group(1))}/{int(m.group(2))}"


def _strip_wp_title_tags(rendered: Any) -> str:
    """Extract plain text from a WP `title.rendered` field."""
    if isinstance(rendered, dict):
        rendered = rendered.get("rendered", "")
    if not isinstance(rendered, str):
        return ""
    s = re.sub(r"<[^>]+>", "", rendered)
    return html.unescape(s).strip()


def _comment_count_badge(post: dict[str, Any]) -> str:
    """Return ``💬 N`` markup when the post has at least 1 comment.
    Empty string for 0 / missing — keeps the line clean for fresh
    posts that haven't accumulated comments yet."""
    raw = post.get("comment_count")
    try:
        n = int(raw) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return f' <span class="nomotoke-comment-count">💬 {n}</span>'


def _build_related_articles_block(query: str, exclude_link: str = "") -> str:
    """Return the 「🔗 関連記事」 HTML block, or empty when no hit."""
    if not query.strip():
        return ""
    posts = _wp_query_public_posts(search=query, limit=4)
    if not posts:
        return ""
    items: list[str] = []
    for p in posts:
        link = (p.get("link") or "").strip()
        if not link or link == exclude_link:
            continue
        title = _strip_wp_title_tags(p.get("title"))
        date_jp = _format_jp_date(p.get("date") or "")
        if not title or not link:
            continue
        prefix = f"{html.escape(date_jp)} " if date_jp else ""
        badge = _comment_count_badge(p)
        items.append(
            f'<li>{prefix}<a href="{html.escape(link)}">{html.escape(title)}</a>{badge}</li>'
        )
        if len(items) >= 3:
            break
    if not items:
        return ""
    return (
        '<aside class="nomotoke-related-posts">'
        '<p class="nomotoke-related-posts__label">🔗 関連記事</p>'
        '<ul class="nomotoke-related-posts__list">'
        + "".join(items)
        + "</ul></aside>"
    )


def _build_recent_games_block(exclude_link: str = "") -> str:
    """Return the 「📅 直近の試合」 block listing the last 5 試合速報 posts."""
    cat_id = _GAME_RESULT_CATEGORY_ID
    if not cat_id:
        return ""
    posts = _wp_query_public_posts(categories=[cat_id], limit=8)
    if not posts:
        return ""
    items: list[str] = []
    for p in posts:
        link = (p.get("link") or "").strip()
        if not link or link == exclude_link:
            continue
        title = _strip_wp_title_tags(p.get("title"))
        date_jp = _format_jp_date(p.get("date") or "")
        if not title:
            continue
        prefix = f"{html.escape(date_jp)} " if date_jp else ""
        badge = _comment_count_badge(p)
        items.append(
            f'<li>{prefix}<a href="{html.escape(link)}">{html.escape(title)}</a>{badge}</li>'
        )
        if len(items) >= 5:
            break
    if not items:
        return ""
    return (
        '<aside class="nomotoke-recent-games">'
        '<p class="nomotoke-recent-games__label">📅 直近の試合</p>'
        '<ul class="nomotoke-recent-games__list">'
        + "".join(items)
        + "</ul></aside>"
    )


def _build_matchup_record_block(opponent: str) -> str:
    """Return the 「🆚 今季対戦成績」 block parsing scores from titles.

    W/L is determined from the Giants' POV: when the article title
    starts with a Giants alias and a score follows, the larger
    number is the Giants score. Conservative — when the title shape
    does not allow unambiguous W/L extraction, the post is skipped
    rather than miscounted."""
    if not opponent.strip():
        return ""
    cat_id = _GAME_RESULT_CATEGORY_ID
    if not cat_id:
        return ""
    season_start = _current_season_start_iso()
    posts = _wp_query_public_posts(
        search=opponent, categories=[cat_id], limit=50, after=season_start
    )
    if not posts:
        return ""
    wins = losses = draws = 0
    counted = 0
    for p in posts:
        title = _strip_wp_title_tags(p.get("title"))
        if not title or opponent not in title:
            continue
        m = _GAME_SCORE_RE.search(title)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        # Order convention: 「巨人 X-Y 阪神」 — first number is Giants.
        # When the opponent name appears BEFORE 巨人, the order is
        # reversed; check by index.
        giants_idx = -1
        for alias in ("巨人", "ジャイアンツ", "読売"):
            i = title.find(alias)
            if i >= 0:
                giants_idx = i
                break
        opp_idx = title.find(opponent)
        if giants_idx < 0 or opp_idx < 0:
            continue
        if giants_idx < opp_idx:
            giants_score, opp_score = a, b
        else:
            giants_score, opp_score = b, a
        if giants_score > opp_score:
            wins += 1
        elif giants_score < opp_score:
            losses += 1
        else:
            draws += 1
        counted += 1
    if counted == 0:
        return ""
    record = f"{wins}勝{losses}敗"
    if draws:
        record += f"{draws}分"
    # NOMOTOKE-INTAKE-MATCHUP-LIST-001 (C-extended): also surface the
    # 5 most recent posts so the reader sees the actual scores, not
    # just the aggregate count.
    list_items: list[str] = []
    for p in posts[:5]:
        title = _strip_wp_title_tags(p.get("title"))
        link = (p.get("link") or "").strip()
        date_jp = _format_jp_date(p.get("date") or "")
        if not (title and link) or opponent not in title:
            continue
        prefix = f"{html.escape(date_jp)} " if date_jp else ""
        badge = _comment_count_badge(p)
        list_items.append(
            f'<li>{prefix}<a href="{html.escape(link)}">{html.escape(title)}</a>{badge}</li>'
        )
        if len(list_items) >= 5:
            break
    matchup_list_html = ""
    if list_items:
        matchup_list_html = (
            '<ul class="nomotoke-season-matchup__list">'
            + "".join(list_items)
            + "</ul>"
        )
    return (
        '<aside class="nomotoke-season-matchup">'
        '<p class="nomotoke-season-matchup__label">🆚 今季対戦成績</p>'
        f'<p>巨人 vs {html.escape(opponent)}: {html.escape(record)} '
        f'(集計 {counted} 試合)</p>'
        f"{matchup_list_html}"
        "</aside>"
    )


def _current_season_start_iso() -> str:
    """Return the YYYY-04-01T00:00:00 ISO string for the current season.

    Defaults to the current calendar year. JST-based: a March entry
    still belongs to the previous season (open week / camp), so March
    submissions look back into last season's record."""
    now = datetime.now(JST)
    year = now.year if now.month >= 4 else now.year - 1
    return f"{year}-04-01T00:00:00"


_GAME_RESULT_CATEGORY_ID = 663  # 試合速報 — see config/categories.json


def _derive_yahoo_preview_url(source_url: str) -> str:
    """Convert ``.../game/<id>/index`` to ``.../game/<id>/preview``.

    Returns ``""`` when the URL is not a Yahoo NPB game URL or the
    expected ``/index`` segment is absent."""
    if not source_url or not _YAHOO_BOXSCORE_URL_RE.match(source_url):
        return ""
    return re.sub(r"/index(\?.*)?$", "/preview", source_url, count=1)


def _fetch_yahoo_lineup_html(preview_url: str) -> str:
    """Single 6-second GET against the Yahoo preview page. Returns the
    raw HTML body (capped at 800 KB) or ``""`` on any failure."""
    if not preview_url:
        return ""
    try:
        import urllib.request
    except Exception:
        return ""
    try:
        req = urllib.request.Request(
            preview_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; yoshilover-manual-intake/1)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            content = resp.read(800_000)
    except Exception:
        return ""
    return content.decode("utf-8", errors="replace")


# NOMOTOKE-INTAKE-JSONLD-META-001: extract author + datePublished
# from JSON-LD blocks for the 「掲載日 by 著者」 meta line. No LLM,
# no fabrication — every value is a literal field from the source
# page's structured data.

_JSONLD_BLOCK_RE_INTAKE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<body>.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _normalise_jsonld_author(value: Any) -> str:
    """JSON-LD ``author`` may be a string, dict ({@type:Person, name}),
    or a list. Returns the first non-empty name or ``""``."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "givenName"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    if isinstance(value, list):
        for item in value:
            n = _normalise_jsonld_author(item)
            if n:
                return n
    return ""


def _extract_jsonld_author_and_date(raw_html: str) -> tuple[str, str]:
    """Return (author_name, date_published_iso) from the first
    ``Article``-typed JSON-LD object that carries either field."""
    if not raw_html or not isinstance(raw_html, str):
        return "", ""
    for m in _JSONLD_BLOCK_RE_INTAKE.finditer(raw_html):
        body = m.group("body").strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            continue
        nodes: list[dict] = []
        if isinstance(parsed, dict):
            nodes.append(parsed)
            graph = parsed.get("@graph")
            if isinstance(graph, list):
                nodes.extend(g for g in graph if isinstance(g, dict))
        elif isinstance(parsed, list):
            nodes.extend(p for p in parsed if isinstance(p, dict))
        for node in nodes:
            t = node.get("@type")
            type_ok = False
            if isinstance(t, str):
                type_ok = "rticle" in t  # NewsArticle / Article / etc.
            elif isinstance(t, list):
                type_ok = any("rticle" in s for s in t if isinstance(s, str))
            if not type_ok:
                continue
            author = _normalise_jsonld_author(node.get("author"))
            date_iso = node.get("datePublished") or node.get("dateCreated") or ""
            if isinstance(date_iso, str):
                date_iso = date_iso.strip()
            else:
                date_iso = ""
            if author or date_iso:
                return author, date_iso
    return "", ""


def _format_jsonld_date_jp(iso: str) -> str:
    """Render an ISO 8601 string as ``M/D HH:MM``. Empty on parse failure."""
    if not iso or not isinstance(iso, str):
        return ""
    m = re.match(
        r"^\d{4}-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?", iso
    )
    if not m:
        return ""
    out = f"{int(m.group(1))}/{int(m.group(2))}"
    if m.group(3) and m.group(4):
        out += f" {m.group(3)}:{m.group(4)}"
    return out


def _build_jsonld_meta_block(raw_html: str, source_name: str) -> str:
    """Return the 「📅 掲載日 by 著者」 line, or empty when neither field
    is available."""
    author, date_iso = _extract_jsonld_author_and_date(raw_html)
    date_jp = _format_jsonld_date_jp(date_iso)
    if not (author or date_jp):
        return ""
    pieces = []
    if date_jp:
        pieces.append(f"📅 {html.escape(date_jp)} 掲載")
    if author:
        attribution = author
        if source_name and source_name not in author:
            attribution = f"{source_name} {author}"
        pieces.append(f"by {html.escape(attribution)}")
    return (
        '<aside class="nomotoke-source-meta">'
        f'<p>{" ".join(pieces)}</p>'
        "</aside>"
    )


# NOMOTOKE-INTAKE-NEXT-GAME-001 (G4) + STANDINGS-001 (C4):
# inline lazy fetch + module-level TTL cache. Each Cloud Run instance
# refetches at most once per ``_CACHE_TTL_SEC`` per data source.
# Storage: in-memory dict — lost on instance restart and rebuilt on
# the next manual-intake submission. No new GCS bucket, no Firestore,
# no Scheduler. ¥0.

_CACHE_TTL_SEC = 6 * 3600  # 6 hours

_NEXT_GAME_CACHE: dict[str, Any] = {"data": None, "fetched_at": 0.0}
_STANDINGS_CACHE: dict[str, Any] = {"data": [], "fetched_at": 0.0}


def _fetch_url_text(url: str, *, timeout: int = 6) -> str:
    """Best-effort HTTP GET. Empty string on any failure."""
    if not url:
        return ""
    try:
        import urllib.request
    except Exception:
        return ""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; yoshilover-manual-intake/1)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read(800_000)
    except Exception:
        return ""
    return content.decode("utf-8", errors="replace")


def _get_giants_next_game() -> dict[str, str]:
    """Return the next pending Giants game from the Yahoo schedule.

    Walks today + next 6 days (looking for the first non-completed
    Giants game). Cached for 6 hours per Cloud Run instance.
    """
    now = time.time()
    if _NEXT_GAME_CACHE.get("data") and (
        now - _NEXT_GAME_CACHE.get("fetched_at", 0) < _CACHE_TTL_SEC
    ):
        return _NEXT_GAME_CACHE["data"] or {}
    try:
        from src.source_yahoo_schedule_extractor import (
            find_giants_pregame_games,
        )
    except Exception:
        return {}
    today = datetime.now(JST).date()
    found: dict[str, str] = {}
    for offset in range(7):
        d = today + timedelta(days=offset)
        url = f"https://baseball.yahoo.co.jp/npb/schedule/?date={d.isoformat()}"
        html_text = _fetch_url_text(url)
        if not html_text:
            continue
        try:
            pregame = find_giants_pregame_games(html_text)
        except Exception:
            pregame = []
        if pregame:
            game = dict(pregame[0])
            game["date"] = d.isoformat()
            found = game
            break
    _NEXT_GAME_CACHE["data"] = found
    _NEXT_GAME_CACHE["fetched_at"] = now
    return found


def _build_next_game_block() -> str:
    """Render the 「🗓 次戦」 ``<aside>``. Empty on cache miss / no
    upcoming Giants game found."""
    g = _get_giants_next_game()
    if not g:
        return ""
    home = (g.get("home") or "").strip()
    away = (g.get("away") or "").strip()
    date_iso = (g.get("date") or "").strip()
    if not (home or away):
        return ""
    date_jp = ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_iso)
    if m:
        date_jp = f"{int(m.group(2))}/{int(m.group(3))}"
    parts = []
    if date_jp:
        parts.append(html.escape(date_jp))
    parts.append(f"{html.escape(away)} vs {html.escape(home)}")
    line = " ".join(parts)
    yahoo_url = (g.get("url") or "").strip()
    anchor = ""
    if yahoo_url:
        anchor = (
            f' (<a href="{html.escape(yahoo_url)}" target="_blank" rel="noopener">Yahoo!</a>)'
        )
    return (
        '<aside class="nomotoke-next-game">'
        '<p class="nomotoke-next-game__label">🗓 次戦</p>'
        f"<p>{line}{anchor}</p>"
        "</aside>"
    )


def _get_standings_for_giants() -> dict[str, str]:
    """Fetch + cache NPB Central League standings; return the Giants row.

    Cache: 6h per Cloud Run instance. Empty dict on parse failure /
    Giants row absent (defensive — keeps the block from rendering
    a half-broken summary).
    """
    now = time.time()
    cached_data = _STANDINGS_CACHE.get("data") or []
    if cached_data and (now - _STANDINGS_CACHE.get("fetched_at", 0) < _CACHE_TTL_SEC):
        rows = cached_data
    else:
        try:
            from src.source_npb_standings_extractor import (
                find_giants_standings_row,
                parse_npb_standings_html,
            )
        except Exception:
            return {}
        year = datetime.now(JST).year
        url = f"https://npb.jp/bis/{year}/stats/std_c.html"
        html_text = _fetch_url_text(url)
        if not html_text:
            return {}
        try:
            rows = parse_npb_standings_html(html_text)
        except Exception:
            rows = []
        _STANDINGS_CACHE["data"] = rows
        _STANDINGS_CACHE["fetched_at"] = now
    try:
        from src.source_npb_standings_extractor import find_giants_standings_row
    except Exception:
        return {}
    giants = find_giants_standings_row(rows)
    return giants or {}


def _build_standings_block() -> str:
    """Render the 「📊 セ・リーグ順位」 ``<aside>``. Empty when the
    Giants row is missing or the parse failed."""
    g = _get_standings_for_giants()
    if not g:
        return ""
    rank = g.get("rank") or ""
    wins = g.get("wins") or ""
    losses = g.get("losses") or ""
    draws = g.get("draws") or ""
    win_pct = g.get("win_pct") or ""
    gb = g.get("gb") or ""
    if not (rank and wins and losses):
        return ""
    record = f"{wins}勝{losses}敗"
    if draws and draws != "0":
        record += f"{draws}分"
    pieces = [f"{rank}位", record]
    if win_pct:
        pieces.append(f"勝率{win_pct}")
    if gb and gb != "-":
        pieces.append(f"ゲーム差{gb}")
    line = " / ".join(pieces)
    today = datetime.now(JST).date()
    today_jp = f"{today.month}/{today.day}"
    return (
        '<aside class="nomotoke-standings">'
        '<p class="nomotoke-standings__label">📊 セ・リーグ順位</p>'
        f"<p>{html.escape(today_jp)}時点: 巨人 {html.escape(line)}</p>"
        "</aside>"
    )


# NOMOTOKE-INTAKE-PLAYER-STATS-001 (A): NPB.jp team stats fetch +
# 30-min in-memory cache. Provides {normalized_name: {col: value}}
# for batting + pitching combined.

_PLAYER_STATS_TTL_SEC = 30 * 60  # 30 minutes (per session memo)
_PLAYER_STATS_CACHE: dict[str, Any] = {
    "batting": {},
    "pitching": {},
    "fetched_at": 0.0,
}


def _refresh_player_stats_cache() -> None:
    """Fetch batting + pitching tables; merge into the in-memory cache.

    Best-effort: failures leave the cache untouched, falling back to
    the previous fetch (or empty dicts on cold start). Each fetch is
    a single ~30 KB GET against npb.jp, gated behind the 30-minute
    TTL so the per-instance cost stays at most 4 fetches/hour.
    """
    try:
        from src.source_npb_team_stats_extractor import (
            parse_npb_team_stats_html,
        )
    except Exception:
        return
    year = datetime.now(JST).year
    batting_url = f"https://npb.jp/bis/{year}/stats/idb1_g.html"
    pitching_url = f"https://npb.jp/bis/{year}/stats/idp1_g.html"
    batting_html = _fetch_url_text(batting_url, timeout=8)
    pitching_html = _fetch_url_text(pitching_url, timeout=8)
    if batting_html:
        parsed = parse_npb_team_stats_html(batting_html)
        if parsed:
            _PLAYER_STATS_CACHE["batting"] = parsed
    if pitching_html:
        parsed = parse_npb_team_stats_html(pitching_html)
        if parsed:
            _PLAYER_STATS_CACHE["pitching"] = parsed
    _PLAYER_STATS_CACHE["fetched_at"] = time.time()


def _get_player_stats_lookup() -> dict[str, dict[str, Any]]:
    """Return ``{normalized_name: {kind: 'batting'|'pitching', record: {...}}}``.

    Lazy refetch every 30 minutes per Cloud Run instance.
    """
    now = time.time()
    if now - _PLAYER_STATS_CACHE.get("fetched_at", 0) > _PLAYER_STATS_TTL_SEC:
        _refresh_player_stats_cache()
    out: dict[str, dict[str, Any]] = {}
    for kind in ("batting", "pitching"):
        bucket = _PLAYER_STATS_CACHE.get(kind) or {}
        for name, rec in bucket.items():
            if name not in out:
                out[name] = {"kind": kind, "record": rec}
    return out


def _normalize_player_name_for_match(name: str) -> str:
    """Match the normalisation used by source_npb_team_stats_extractor:
    strip whitespace + fullwidth space."""
    if not name:
        return ""
    return re.sub(r"[\s　]+", "", name).strip()


def _scan_giants_player_names_in_text(text: str) -> list[str]:
    """Return roster.json player + coach names that appear (full or
    surname-prefix) in the input text. Conservative: 2-4 char
    surnames only match when isolated; full names match anywhere."""
    if not text:
        return []
    try:
        from src.nomotoke_card_renderer import _load_giants_roster
    except Exception:
        return []
    roster = _load_giants_roster()
    found: list[str] = []
    seen: set[str] = set()
    for entry in roster:
        full_name = (entry.get("name") or "").strip()
        if not full_name:
            continue
        match_keys: list[str] = [full_name]
        for alias in entry.get("aliases", []) or []:
            if alias and alias not in match_keys:
                match_keys.append(alias)
        # Add surname (first 2-3 chars of full_name) as a softer match
        # — but only when the full_name itself is not already a hit.
        if len(full_name) >= 3:
            match_keys.append(full_name[:2])
            match_keys.append(full_name[:3])
        hit = any(k and k in text for k in match_keys)
        if hit and full_name not in seen:
            seen.add(full_name)
            found.append(full_name)
    return found[:4]  # cap to keep the block readable


def _format_batting_summary(rec: dict[str, str]) -> str:
    """Pull a compact 「打率 .278 / 8本 / 24打点」 line from a batting row.

    Tolerates column-name drift across NPB pages by trying multiple
    candidate keys for each metric."""
    def _pick(*keys: str) -> str:
        for k in keys:
            v = rec.get(k)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    avg = _pick("打率", "AVG", "Avg")
    hr = _pick("本塁打", "HR", "本")
    rbi = _pick("打点", "RBI")
    parts: list[str] = []
    if avg:
        parts.append(f"打率{avg}")
    if hr:
        parts.append(f"{hr}本")
    if rbi:
        parts.append(f"{rbi}打点")
    return " / ".join(parts)


def _format_pitching_summary(rec: dict[str, str]) -> str:
    """Pull a compact 「N登板 W勝L敗 防御率2.50」 line from a pitching row."""
    def _pick(*keys: str) -> str:
        for k in keys:
            v = rec.get(k)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    games = _pick("登板", "試合", "G")
    wins = _pick("勝", "W")
    losses = _pick("敗", "L")
    era = _pick("防御率", "ERA")
    parts: list[str] = []
    if games:
        parts.append(f"{games}登板")
    if wins or losses:
        parts.append(f"{wins or 0}勝{losses or 0}敗")
    if era:
        parts.append(f"防御率{era}")
    return " ".join(parts)


def _build_player_stats_block(scan_text: str) -> str:
    """Render the unified 「🏷 関連選手」 block (D1).

    Combines the previous standalone roster aside (jersey + position +
    name) with the inline season-stats line so each player surfaces
    on a single row:

      巨人 #20 投手 戸郷翔征 — 📊 5登板 1勝1敗 防御率2.50

    Empty when no roster name matches AND no stats record applies.
    """
    if not scan_text:
        return ""
    candidate_names = _scan_giants_player_names_in_text(scan_text)
    if not candidate_names:
        return ""
    stats = _get_player_stats_lookup()
    try:
        from src.nomotoke_card_renderer import _lookup_roster_by_name
    except Exception:
        _lookup_roster_by_name = None  # type: ignore
    lines: list[str] = []
    seen: set[str] = set()
    for name in candidate_names:
        norm = _normalize_player_name_for_match(name)
        if norm in seen:
            continue
        seen.add(norm)
        # Resolve rendered name from stats first (gives the official
        # spacing / NPB rendering); fall back to the roster name; fall
        # back to the input.
        rec_info = stats.get(norm) if stats else None
        if not rec_info and stats:
            for k, v in stats.items():
                if k.startswith(norm) and len(norm) >= 2:
                    rec_info = v
                    break
        record = (rec_info or {}).get("record") or {}
        kind = (rec_info or {}).get("kind") or ""
        rendered = (record.get("__rendered_name__") or name).strip()

        # Roster-side metadata (jersey / position).
        roster_entry = None
        if _lookup_roster_by_name is not None:
            roster_entry = _lookup_roster_by_name(name) or _lookup_roster_by_name(rendered)
        prefix_parts: list[str] = ["巨人"]
        if roster_entry:
            jn = (roster_entry.get("jersey_number") or "").strip()
            pos = (roster_entry.get("position") or "").strip()
            if jn:
                prefix_parts.append(f"#{jn}")
            if pos:
                prefix_parts.append(pos)
        prefix = " ".join(html.escape(p) for p in prefix_parts)

        # Stats summary tail (optional — empty when no record).
        stats_tail = ""
        if record:
            if kind == "batting":
                summary = _format_batting_summary(record)
            else:
                summary = _format_pitching_summary(record)
            if summary:
                stats_tail = f' — <span class="nomotoke-player-stats__values">📊 {html.escape(summary)}</span>'

        # When neither roster metadata nor stats apply, drop the row
        # so the block doesn't render an awkward bare name list.
        if not roster_entry and not stats_tail:
            continue

        lines.append(
            f'<p class="nomotoke-roster__line">'
            f'<span class="nomotoke-roster__role">{prefix}</span> '
            f'<span class="nomotoke-roster__name">{html.escape(rendered)}</span>'
            f"{stats_tail}"
            "</p>"
        )
        if len(lines) >= 4:
            break
    if not lines:
        return ""
    return (
        '<aside class="nomotoke-player-stats">'
        '<p class="nomotoke-player-stats__label">🏷 関連選手</p>'
        + "".join(lines)
        + "</aside>"
    )


# NOMOTOKE-INTAKE-AUTHOR-OTHER-001 (D): "this reporter's other recent
# articles" cluster, sourced from WP REST search by author name.

def _build_author_other_articles_block(author_name: str, exclude_link: str = "") -> str:
    """Render the 「✍ {author} の他の記事」 block. Empty when no usable
    hit. ``author_name`` is the full byline string (often
    ``"スポーツ報知 山田太郎"``)."""
    if not author_name or not isinstance(author_name, str):
        return ""
    # Use the longest 漢字-カタカナ run as the search query so the WP
    # REST search lands on author bylines stored in titles or excerpts.
    ngrams = re.findall(r"[一-龥ぁ-んァ-ヶー]{2,12}", author_name)
    if not ngrams:
        return ""
    query = max(ngrams, key=len)
    posts = _wp_query_public_posts(search=query, limit=4)
    if not posts:
        return ""
    items: list[str] = []
    for p in posts:
        link = (p.get("link") or "").strip()
        if not link or link == exclude_link:
            continue
        title = _strip_wp_title_tags(p.get("title"))
        date_jp = _format_jp_date(p.get("date") or "")
        if not title:
            continue
        prefix = f"{html.escape(date_jp)} " if date_jp else ""
        items.append(
            f'<li>{prefix}<a href="{html.escape(link)}">{html.escape(title)}</a></li>'
        )
        if len(items) >= 3:
            break
    if not items:
        return ""
    return (
        '<aside class="nomotoke-author-cluster">'
        f'<p class="nomotoke-author-cluster__label">✍ {html.escape(query)} の他の記事</p>'
        '<ul class="nomotoke-author-cluster__list">'
        + "".join(items)
        + "</ul></aside>"
    )


# NOMOTOKE-INTAKE-NOTICE-TIMELINE-001 (E): recent 公示 articles list.

def _build_recent_notice_timeline_block() -> str:
    """Render the 「📋 直近の公示」 block. Empty when no recent notices."""
    notice_cat = 669  # 球団情報 — see config/categories.json
    posts = _wp_query_public_posts(
        search="公示", categories=[notice_cat], limit=8
    )
    if not posts:
        return ""
    items: list[str] = []
    for p in posts:
        title = _strip_wp_title_tags(p.get("title"))
        link = (p.get("link") or "").strip()
        if not (title and link):
            continue
        if "公示" not in title and "登録" not in title and "抹消" not in title:
            continue
        date_jp = _format_jp_date(p.get("date") or "")
        prefix = f"{html.escape(date_jp)} " if date_jp else ""
        items.append(
            f'<li>{prefix}<a href="{html.escape(link)}">{html.escape(title)}</a></li>'
        )
        if len(items) >= 4:
            break
    if not items:
        return ""
    return (
        '<aside class="nomotoke-notice-timeline">'
        '<p class="nomotoke-notice-timeline__label">📋 直近の公示</p>'
        '<ul class="nomotoke-notice-timeline__list">'
        + "".join(items)
        + "</ul></aside>"
    )


# NOMOTOKE-INTAKE-YESTERDAY-GAME-001 (B): yesterday's Giants game
# 1-line snippet, sourced from the most recent 試合速報 post.

def _build_yesterdays_game_block(exclude_link: str = "") -> str:
    """Render the 「🆚 昨日の試合」 block. Empty when no recent
    postgame post available."""
    cat_id = _GAME_RESULT_CATEGORY_ID
    if not cat_id:
        return ""
    posts = _wp_query_public_posts(categories=[cat_id], limit=2)
    if not posts:
        return ""
    p = posts[0]
    link = (p.get("link") or "").strip()
    if link == exclude_link and len(posts) > 1:
        p = posts[1]
        link = (p.get("link") or "").strip()
    if not link:
        return ""
    title = _strip_wp_title_tags(p.get("title"))
    if not title:
        return ""
    date_jp = _format_jp_date(p.get("date") or "")
    prefix = f"{html.escape(date_jp)} " if date_jp else ""
    return (
        '<aside class="nomotoke-yesterday-game">'
        '<p class="nomotoke-yesterday-game__label">🆚 直近の試合速報</p>'
        f'<p>{prefix}<a href="{html.escape(link)}">{html.escape(title)}</a></p>'
        "</aside>"
    )


# NOMOTOKE-INTAKE-READER-UX-001 (R1 + R3 + R4 + R6): reader-side
# enhancements baked into the rendered body. All pure HTML, no JS,
# no external libraries, no auth — the WP theme renders them as part
# of the post body. Each helper short-circuits to ``""`` when its
# required input is empty so a partial post never crashes.

# R3: read time / relative time
# ------------------------------

_READ_CHARS_PER_MINUTE = 600  # JP reading speed approx 10 chars/sec


def _compute_read_minutes(content_html: str) -> int:
    """Count plain-text chars in ``content_html`` and convert to a
    rounded-up minutes count (min 1)."""
    if not content_html:
        return 1
    plain = re.sub(r"<[^>]+>", "", content_html)
    plain = html.unescape(plain)
    plain = re.sub(r"[\s　]+", "", plain)
    n = max(1, len(plain))
    minutes = (n + _READ_CHARS_PER_MINUTE - 1) // _READ_CHARS_PER_MINUTE
    return max(1, minutes)


def _format_relative_time(iso: str) -> str:
    """Render an ISO 8601 timestamp as ``N時間前`` / ``N日前`` / ``YYYY/M/D``.

    Empty string when ``iso`` is unparseable."""
    if not iso or not isinstance(iso, str):
        return ""
    candidate = iso.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except (TypeError, ValueError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    else:
        parsed = parsed.astimezone(JST)
    now = datetime.now(JST)
    delta = now - parsed
    secs = delta.total_seconds()
    if secs < 0:
        return parsed.strftime("%-m/%-d %H:%M")
    if secs < 60:
        return "今"
    if secs < 3600:
        return f"{int(secs // 60)}分前"
    if secs < 86400:
        return f"{int(secs // 3600)}時間前"
    if secs < 7 * 86400:
        return f"{int(secs // 86400)}日前"
    return parsed.strftime("%Y/%-m/%-d")


def _build_meta_header_bar(content_html: str, source_published_at_iso: str) -> str:
    """Render the 「⏱ 読了 ~~ ・ 掲載 ~~」 metadata bar at top of body."""
    minutes = _compute_read_minutes(content_html)
    rel = _format_relative_time(source_published_at_iso)
    pieces: list[str] = [f"⏱ 読了約{minutes}分"]
    if rel:
        pieces.append(f"📅 掲載 {rel}")
    return (
        '<aside class="nomotoke-reader-meta">'
        f'<p>{" ・ ".join(html.escape(p) for p in pieces)}</p>'
        "</aside>"
    )


# R1: table of contents
# ----------------------

# Map known block class names to display labels + anchor ids. The
# anchor id is a stable slug — applied via ``_inject_toc_anchors`` and
# referenced by the ToC links.
_TOC_BLOCK_REGISTRY: tuple[tuple[str, str, str], ...] = (
    ("nomotoke-source-excerpt", "本文抜粋", "toc-excerpt"),
    ("nomotoke-lineup", "今日のスタメン", "toc-lineup"),
    ("nomotoke-yesterday-game", "直近の試合速報", "toc-yesterday"),
    ("nomotoke-recent-games", "直近の試合", "toc-recent-games"),
    ("nomotoke-season-matchup", "今季対戦成績", "toc-matchup"),
    ("nomotoke-related-posts", "関連記事", "toc-related"),
    ("nomotoke-roster", "関連選手・首脳陣", "toc-roster"),
    ("nomotoke-player-stats", "関連選手の今季成績", "toc-player-stats"),
    ("nomotoke-author-cluster", "著者の他の記事", "toc-author"),
    ("nomotoke-notice-timeline", "直近の公示", "toc-notice"),
    ("nomotoke-standings", "セ・リーグ順位", "toc-standings"),
    ("nomotoke-next-game", "次戦", "toc-next-game"),
    ("nomotoke-source-meta", "掲載情報", "toc-source-meta"),
)


def _inject_toc_anchors(content_html: str) -> tuple[str, list[tuple[str, str]]]:
    """For each block in ``_TOC_BLOCK_REGISTRY`` that appears in the
    HTML, add ``id="..."`` to its opening tag. Returns
    (modified_html, [(anchor_id, label)]) where the second element is
    used by ``_render_toc_block``."""
    modified = content_html
    found: list[tuple[str, str]] = []
    for class_name, label, anchor_id in _TOC_BLOCK_REGISTRY:
        # Match the first ``<aside class="...{class_name}..." `` tag and
        # inject id=. Conservative: only the FIRST occurrence per class.
        pattern = re.compile(
            rf'(<aside class="[^"]*{re.escape(class_name)}[^"]*")(>)'
        )
        m = pattern.search(modified)
        if m:
            replacement = f'{m.group(1)} id="{anchor_id}"{m.group(2)}'
            modified = modified[: m.start()] + replacement + modified[m.end():]
            found.append((anchor_id, label))
    return modified, found


def _build_toc_block(toc_entries: list[tuple[str, str]]) -> str:
    """Render the 📖 目次 block, or empty when too few entries."""
    if not toc_entries or len(toc_entries) < 3:
        return ""
    items = "".join(
        f'<li><a href="#{html.escape(aid)}">{html.escape(label)}</a></li>'
        for aid, label in toc_entries
    )
    return (
        '<aside class="nomotoke-toc">'
        '<p class="nomotoke-toc__label">📖 目次</p>'
        f'<ul class="nomotoke-toc__list">{items}</ul>'
        "</aside>"
    )


# R4: roster name auto-link in lead
# ----------------------------------

def _wrap_first_roster_names_in_lead(content_html: str) -> str:
    """Wrap the first occurrence of each roster name found in
    ``<p class="nomotoke-lead">...</p>`` into a search-link anchor.

    Conservative: only the lead paragraph is rewritten so we never
    nest <a> tags or break inline HTML inside fact tables."""
    if not content_html:
        return content_html
    try:
        from src.nomotoke_card_renderer import _load_giants_roster
    except Exception:
        return content_html
    roster = _load_giants_roster()
    if not roster:
        return content_html
    # Names sorted by length desc so 「岡本和真」 wins over 「岡本」.
    names = sorted(
        {(e.get("name") or "").strip() for e in roster if e.get("name")},
        key=len,
        reverse=True,
    )
    lead_re = re.compile(
        r'(<p class="nomotoke-lead">)([^<]+)(</p>)', re.DOTALL
    )
    m = lead_re.search(content_html)
    if not m:
        return content_html
    open_tag, lead_text, close_tag = m.group(1), m.group(2), m.group(3)
    used: set[str] = set()
    rewritten = lead_text
    for name in names:
        if not name or name in used:
            continue
        if name not in rewritten:
            continue
        used.add(name)
        link = f'<a href="/?s={html.escape(name)}">{html.escape(name)}</a>'
        # Replace ONLY the first occurrence — preserves surrounding text
        # context and avoids over-linking.
        rewritten = rewritten.replace(name, link, 1)
        if len(used) >= 4:
            break
    new_lead = open_tag + rewritten + close_tag
    return content_html[: m.start()] + new_lead + content_html[m.end():]


# R6: tag chip block (player + opponent + venue search-links)
# ------------------------------------------------------------

_VENUE_KEYWORDS_FOR_CHIPS: tuple[str, ...] = (
    "東京ドーム", "神宮球場", "マツダスタジアム", "バンテリンドーム",
    "京セラドーム", "ベルーナドーム", "ZOZOマリン", "エスコンフィールド",
    "PayPayドーム", "横浜スタジアム", "ジャイアンツタウン",
)
_TEAM_KEYWORDS_FOR_CHIPS: tuple[str, ...] = (
    "阪神", "中日", "広島", "DeNA", "ヤクルト",
    "楽天", "ロッテ", "オリックス", "ソフトバンク",
    "日本ハム", "西武", "ハヤテ", "オイシックス",
    "ドジャース", "カブス", "パドレス", "メッツ",
)


def _build_tag_chip_block(
    title: str, summary: str, content_html: str, category: str
) -> str:
    """Render the chip-style tag block at the bottom of the post.

    Each chip is a clickable ``<a href="/?s=...">`` link to the WP
    search results page for that token. Uses a fixed soft-amber chip
    style (inline) so the look survives every WP theme."""
    text = " ".join(s for s in (title, summary) if s)
    chips: list[str] = []
    seen: set[str] = set()

    def _add(label: str, search_term: str = "") -> None:
        if label in seen:
            return
        seen.add(label)
        term = search_term or label
        chips.append(
            '<a class="nomotoke-chip" '
            f'href="/?s={html.escape(term)}" '
            'style="display:inline-block;margin:4px 4px 0 0;'
            "padding:4px 10px;background:#fff8e1;color:#5d4037;"
            "border:1px solid #ffd54f;border-radius:14px;"
            'text-decoration:none;font-size:13px;">'
            f"#{html.escape(label)}</a>"
        )

    if category and category.strip():
        _add(category.strip())
    for team in _TEAM_KEYWORDS_FOR_CHIPS:
        if team in text:
            _add(team)
    for venue in _VENUE_KEYWORDS_FOR_CHIPS:
        if venue in text:
            _add(venue)
    try:
        from src.nomotoke_card_renderer import _load_giants_roster
    except Exception:
        roster = []
    else:
        roster = _load_giants_roster()
    for entry in roster:
        full = (entry.get("name") or "").strip()
        if full and full in text:
            _add(full)
            if len(chips) >= 8:
                break

    if not chips:
        return ""
    return (
        '<aside class="nomotoke-tag-chips">'
        '<p class="nomotoke-tag-chips__label">🏷 関連タグ</p>'
        '<p class="nomotoke-tag-chips__row">'
        + "".join(chips)
        + "</p></aside>"
    )


# NOMOTOKE-INTAKE-TRUST-001 (N1): 「🤖 AI 不使用」 trust badge.

def _build_trust_badge_block(source_name: str, source_url: str) -> str:
    """Render the 「🤖 AI 不使用」 attribution badge, anchored to the
    source. Empty when no source name (defensive — drafts without
    source_name are shaped wrong upstream)."""
    if not source_name:
        return ""
    safe_source = html.escape(source_name)
    safe_url = html.escape(source_url) if source_url else ""
    if safe_url:
        attribution = (
            f'<a href="{safe_url}" target="_blank" rel="noopener">{safe_source}</a>'
        )
    else:
        attribution = safe_source
    return (
        '<aside class="nomotoke-trust-badge" '
        'style="margin:16px 0;padding:10px 14px;'
        "border-left:3px solid #2e7d32;background:#e8f5e9;"
        'border-radius:4px;font-size:13px;line-height:1.5;color:#1b5e20;">'
        "🤖 この記事は <strong>AI を使わず</strong>、出典記事の事実だけを構造化して生成しています。"
        f"<br>📰 出典: {attribution}"
        "</aside>"
    )


# NOMOTOKE-INTAKE-JSONLD-EMIT-001 (N2): emit JSON-LD NewsArticle
# schema in the body so search engines render rich snippets.

def _build_jsonld_article_schema(
    *,
    title: str,
    summary: str,
    source_url: str,
    source_name: str,
    source_published_at_iso: str,
    og_image: str,
    raw_html: str,
) -> str:
    """Render a ``<script type="application/ld+json">`` block embedding
    the NewsArticle schema. Empty when title is missing.

    The fields are sourced from operator input (title / summary /
    source_url) + extractor output (og_image / raw_html JSON-LD
    author). NEVER calls an LLM."""
    if not title:
        return ""
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title[:110],
    }
    if summary:
        schema["description"] = summary[:200]
    if source_published_at_iso:
        schema["datePublished"] = source_published_at_iso
    # Author: prefer JSON-LD-extracted author from source page; fall
    # back to source_name.
    author_name = ""
    if raw_html:
        ja, _ = _extract_jsonld_author_and_date(raw_html)
        if ja:
            author_name = ja
    if not author_name and source_name:
        author_name = source_name
    if author_name:
        schema["author"] = {"@type": "Organization", "name": author_name}
    if og_image and _is_safe_https_image_url(og_image):
        schema["image"] = [og_image]
    if source_url:
        schema["mainEntityOfPage"] = {"@type": "WebPage", "@id": source_url}
    schema["publisher"] = {
        "@type": "Organization",
        "name": "YOSHILOVER",
        "url": "https://yoshilover.com",
    }
    payload = json.dumps(schema, ensure_ascii=False)
    # Defensive: never let a literal ``</script>`` close the host
    # script tag from inside the JSON.
    payload = payload.replace("</", "<\\/")
    return (
        '<script type="application/ld+json">'
        f"{payload}"
        "</script>"
    )


# NOMOTOKE-INTAKE-OTHERGAMES-001 (N3): list of OTHER NPB games on the
# same date, sourced from the Yahoo schedule we already fetched (or
# fetched once per 6h via the next-game cache).

_NPB_TEAM_TOKENS_FOR_GAMES = (
    "巨人", "阪神", "中日", "広島", "DeNA", "ヤクルト",
    "楽天", "ロッテ", "オリックス", "ソフトバンク",
    "日本ハム", "西武",
)


def _fetch_today_schedule_html() -> str:
    """Return the Yahoo schedule HTML for today (JST). 6h cache key
    parallel to ``_NEXT_GAME_CACHE`` so repeated calls within a window
    hit memory."""
    now = time.time()
    cached = _OTHER_GAMES_CACHE.get("html") or ""
    if cached and (now - _OTHER_GAMES_CACHE.get("fetched_at", 0) < _CACHE_TTL_SEC):
        return cached
    today = datetime.now(JST).date()
    url = f"https://baseball.yahoo.co.jp/npb/schedule/?date={today.isoformat()}"
    html_text = _fetch_url_text(url)
    if html_text:
        _OTHER_GAMES_CACHE["html"] = html_text
        _OTHER_GAMES_CACHE["fetched_at"] = now
    return html_text


_OTHER_GAMES_CACHE: dict[str, Any] = {"html": "", "fetched_at": 0.0}


def _parse_all_games_on_today(html_text: str) -> list[dict[str, str]]:
    """Return [{home, away, score_line, is_completed}] for every NPB
    game block on the schedule page. Parser uses the same regex shape
    as ``find_giants_completed_games`` but does NOT filter by team."""
    if not html_text:
        return []
    try:
        from src.source_yahoo_schedule_extractor import (
            _AWAY_RE,
            _FINAL_MARKER_RE,
            _HOME_RE,
            _SCHEDULE_GAME_BLOCK_RE,
            _clean_text,
        )
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for m in _SCHEDULE_GAME_BLOCK_RE.finditer(html_text):
        block = m.group("inner")
        home_m = _HOME_RE.search(block)
        away_m = _AWAY_RE.search(block)
        home = _clean_text(home_m.group("inner")) if home_m else ""
        away = _clean_text(away_m.group("inner")) if away_m else ""
        if not (home and away):
            continue
        # Drop blocks that don't carry a real NPB team token (eliminates
        # MLB / 二軍 cross-page bleed).
        if not any(t in home or t in away for t in _NPB_TEAM_TOKENS_FOR_GAMES):
            continue
        # Score: look for an ``X - Y`` token inside the block.
        score = ""
        sm = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})", block)
        if sm:
            score = f"{sm.group(1)}-{sm.group(2)}"
        is_completed = bool(_FINAL_MARKER_RE.search(block))
        out.append(
            {
                "home": home,
                "away": away,
                "score": score,
                "is_completed": str(is_completed),
            }
        )
    return out


def _build_other_games_block() -> str:
    """Render the 「⚾ 当日の他試合」 block. Empty when no other game
    can be parsed cleanly."""
    html_text = _fetch_today_schedule_html()
    if not html_text:
        return ""
    games = _parse_all_games_on_today(html_text)
    if not games:
        return ""
    lines: list[str] = []
    for g in games:
        home = g.get("home", "")
        away = g.get("away", "")
        if any(t in home for t in ("巨人", "ジャイアンツ", "読売")):
            continue
        if any(t in away for t in ("巨人", "ジャイアンツ", "読売")):
            continue
        score = g.get("score") or ""
        if score:
            lines.append(
                f"<li>{html.escape(away)} {html.escape(score)} {html.escape(home)}</li>"
            )
        else:
            lines.append(
                f"<li>{html.escape(away)} vs {html.escape(home)}</li>"
            )
        if len(lines) >= 5:
            break
    if not lines:
        return ""
    return (
        '<aside class="nomotoke-other-games">'
        '<p class="nomotoke-other-games__label">⚾ 当日の他試合 (参考)</p>'
        f'<ul class="nomotoke-other-games__list">{"".join(lines)}</ul>'
        "</aside>"
    )


# NOMOTOKE-INTAKE-SERIES-TRACKER-001 (N4): series-context tracker for
# postgame posts. Groups WP postgame posts about the same opponent
# within a 4-day window into 「第N戦」 format.

def _build_series_tracker_block(opponent: str) -> str:
    """Render the 「🆚 vs {opponent} シリーズ」 block. Empty when fewer
    than 2 hits."""
    if not opponent.strip():
        return ""
    cat_id = _GAME_RESULT_CATEGORY_ID
    if not cat_id:
        return ""
    posts = _wp_query_public_posts(
        search=opponent, categories=[cat_id], limit=10
    )
    if not posts:
        return ""
    today = datetime.now(JST).date()
    now_iso = today.isoformat()
    series_posts: list[dict] = []
    for p in posts:
        title = _strip_wp_title_tags(p.get("title"))
        if opponent not in title:
            continue
        date_str = (p.get("date") or "")[:10]
        if not date_str:
            continue
        try:
            d = datetime.fromisoformat(date_str).date()
        except (TypeError, ValueError):
            continue
        # Series window: posts within 4 days of today.
        if (today - d).days > 4 or (today - d).days < -1:
            continue
        series_posts.append({"date": date_str, "title": title, "link": p.get("link") or ""})
    if len(series_posts) < 2:
        return ""
    series_posts.sort(key=lambda x: x["date"])
    items: list[str] = []
    for idx, sp in enumerate(series_posts, start=1):
        date_jp = _format_jp_date(sp["date"]) or sp["date"]
        link = sp["link"]
        title = sp["title"]
        items.append(
            f'<li>第{idx}戦 {html.escape(date_jp)} '
            f'<a href="{html.escape(link)}">{html.escape(title)}</a></li>'
        )
    return (
        '<aside class="nomotoke-series-tracker">'
        f'<p class="nomotoke-series-tracker__label">🆚 vs {html.escape(opponent)} シリーズ</p>'
        f'<ul class="nomotoke-series-tracker__list">{"".join(items)}</ul>'
        "</aside>"
    )


# NOMOTOKE-INTAKE-EMOJI-DECORATE-001 (R-X3 trim): curated to ~18
# high-impact keywords. The original 40+ list felt too "SNS-like";
# the本家 dnomotoke.com observed in production uses ZERO emoji
# decoration, so we keep just the most essential outcome / venue /
# notice markers and drop the rest.
#
# Order matters: longer phrases come before shorter ones so
# 「サヨナラ勝ち」 matches before 「勝ち」.
_BODY_EMOJI_DECORATIONS: tuple[tuple[str, str], ...] = (
    ("ノーヒットノーラン", "🌟"),
    ("サヨナラ勝ち", "⚡"),
    ("サヨナラ負け", "⚡"),
    ("サヨナラ", "⚡"),
    ("逆転", "🔄"),
    ("連勝", "🔥"),
    ("連敗", "💧"),
    ("引き分け", "🤝"),
    ("本塁打", "💥"),
    ("ホームラン", "💥"),
    ("完封", "🛡"),
    ("完投", "💪"),
    ("勝利", "🏆"),
    ("敗戦", "😢"),
    # Stadium catch-all
    ("バンテリンドーム", "🏟"),
    ("マツダスタジアム", "🏟"),
    ("京セラドーム", "🏟"),
    ("横浜スタジアム", "🏟"),
    ("神宮球場", "🏟"),
    ("東京ドーム", "🏟"),
    # Notice
    ("出場選手登録", "✅"),
    ("登録抹消", "❌"),
    # Pregame + versus
    ("予告先発", "📢"),
    (" vs ", " ⚔️ "),
)


# NOMOTOKE-INTAKE-X-EMBED-001 (R-X1): pull recent X posts from the
# operator's existing rsshub-mirrored feeds and embed 2-3 relevant
# tweets inline. ZERO X API spend — we read the same RSS feeds the
# legacy fetcher already polls.

_X_EMBED_TTL_SEC = 30 * 60  # 30 minutes
_X_EMBED_FEED_URLS: tuple[str, ...] = (
    "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/hochi_giants",
    "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/yomiuri_giants",
    "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/SponichiYakyu",
    "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/nikkansports",
    "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/Sanspo_Giants",
)
_X_EMBED_CACHE: dict[str, Any] = {"items": [], "fetched_at": 0.0}


def _refresh_x_embed_cache() -> None:
    """Fetch every feed once and merge their recent items into the
    cache. ``_X_EMBED_CACHE['items']`` ends up as a list of
    ``{url, text, pubdate}`` dicts ordered by pubdate descending."""
    items: list[dict[str, str]] = []
    for feed_url in _X_EMBED_FEED_URLS:
        xml = _fetch_url_text(feed_url, timeout=8)
        if not xml:
            continue
        for m in re.finditer(r"<item>(.*?)</item>", xml, re.DOTALL):
            block = m.group(1)
            link_m = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
            if not link_m:
                continue
            link = link_m.group(1).strip()
            if "status" not in link:
                continue
            desc_m = re.search(
                r"<description>(.*?)</description>", block, re.DOTALL
            )
            desc = desc_m.group(1) if desc_m else ""
            desc = re.sub(
                r"<!\[CDATA\[(.*?)\]\]>", r"\1", desc, flags=re.DOTALL
            )
            desc = re.sub(r"<[^>]+>", " ", desc)
            desc = html.unescape(desc).strip()
            pub_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.DOTALL)
            pub = pub_m.group(1).strip() if pub_m else ""
            items.append({"url": link, "text": desc[:400], "pubdate": pub})
    _X_EMBED_CACHE["items"] = items
    _X_EMBED_CACHE["fetched_at"] = time.time()


def _get_x_embed_pool() -> list[dict[str, str]]:
    """Return the cached X-tweet pool, refreshing every 30 minutes."""
    now = time.time()
    if now - _X_EMBED_CACHE.get("fetched_at", 0) > _X_EMBED_TTL_SEC:
        _refresh_x_embed_cache()
    return _X_EMBED_CACHE.get("items") or []


def _extract_article_keywords(title: str, summary: str) -> list[str]:
    """Build the keyword list used to filter X tweets for relevance."""
    kws: list[str] = []
    text = " ".join(s for s in (title, summary) if s)
    if not text:
        return kws
    # Player names from roster
    try:
        from src.nomotoke_card_renderer import _load_giants_roster
    except Exception:
        roster = []
    else:
        roster = _load_giants_roster()
    for entry in roster:
        full = (entry.get("name") or "").strip()
        if full and full in text and full not in kws:
            kws.append(full)
    # Opponent teams
    for team in _TEAM_KEYWORDS_FOR_CHIPS:
        if team in text and team not in kws:
            kws.append(team)
    # Venue
    for venue in _VENUE_KEYWORDS_FOR_CHIPS:
        if venue in text and venue not in kws:
            kws.append(venue)
    return kws[:8]


def _build_x_embeds_block(title: str, summary: str) -> str:
    """Render the 「📲 関連 X 投稿」 block with 2-3 relevant tweets.

    Empty when no matching tweet is found in the cached pool.
    """
    keywords = _extract_article_keywords(title, summary)
    if not keywords:
        # Fallback: top 2 latest tweets if no keyword match — still
        # better than empty for engagement.
        keywords = ["巨人", "ジャイアンツ"]
    pool = _get_x_embed_pool()
    if not pool:
        return ""
    matches: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in pool:
        text = item.get("text") or ""
        if not any(kw in text for kw in keywords):
            continue
        url = item.get("url") or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        matches.append(item)
        if len(matches) >= 3:
            break
    if not matches:
        return ""
    parts = [
        '<aside class="nomotoke-x-embeds">',
        '<p class="nomotoke-x-embeds__label">📲 関連 X 投稿</p>',
    ]
    for item in matches:
        safe_url = html.escape(item["url"])
        parts.append(
            f'<blockquote class="twitter-tweet" data-lang="ja" data-dnt="true">'
            f'<a href="{safe_url}"></a>'
            "</blockquote>"
        )
    parts.append(
        '<script async src="https://platform.twitter.com/widgets.js" '
        'charset="utf-8"></script>'
    )
    parts.append("</aside>")
    return "".join(parts)


# NOMOTOKE-INTAKE-SHARE-BUTTONS-001 (R-X2): X / LINE / copy share
# buttons. Inline JS reads ``window.location.href`` at click time
# so the buttons don't need the WP permalink at render time.

# Static share buttons HTML (block 1) — visual layer. The buttons
# render exactly the same regardless of script execution (just sit
# in the DOM as styled anchors).
_SHARE_BUTTONS_VISUAL_HTML = (
    '<aside class="nomotoke-share-buttons" '
    'style="margin:14px 0;padding:10px 0;'
    "border-top:1px solid #eee;border-bottom:1px solid #eee;"
    'text-align:center;">'
    '<p style="margin:0 0 8px;font-size:13px;font-weight:600;">▼ この記事を共有する</p>'
    '<a class="nomotoke-share-x" href="#" '
    'style="display:inline-block;margin:0 6px;padding:6px 14px;'
    "background:#000;color:#fff;text-decoration:none;border-radius:6px;"
    'font-size:13px;font-weight:600;">𝕏 で共有</a>'
    '<a class="nomotoke-share-line" href="#" '
    'style="display:inline-block;margin:0 6px;padding:6px 14px;'
    "background:#06c755;color:#fff;text-decoration:none;border-radius:6px;"
    'font-size:13px;font-weight:600;">LINE で共有</a>'
    '<a class="nomotoke-share-copy" href="#" '
    'style="display:inline-block;margin:0 6px;padding:6px 14px;'
    "background:#455a64;color:#fff;text-decoration:none;border-radius:6px;"
    'font-size:13px;font-weight:600;">URL コピー</a>'
    "</aside>"
)

# JS module — wired ONCE per page using a window-level idempotency
# flag so a second copy of the share-buttons block doesn't double-
# bind the click handlers (audit fix A: prevented the URL コピー
# alert firing twice when both top- and bottom-share blocks
# rendered in the same body).
_SHARE_BUTTONS_SCRIPT_HTML = (
    "<script>"
    "(function(){"
    "if(window.__nomotokeShareInit)return;"
    "window.__nomotokeShareInit=true;"
    "var u=encodeURIComponent(window.location.href);"
    "var t=encodeURIComponent(document.title);"
    "document.querySelectorAll('.nomotoke-share-x').forEach(function(a){"
    "a.href='https://twitter.com/intent/tweet?text='+t+'&url='+u;"
    "a.target='_blank';a.rel='noopener';});"
    "document.querySelectorAll('.nomotoke-share-line').forEach(function(a){"
    "a.href='https://social-plugins.line.me/lineit/share?url='+u;"
    "a.target='_blank';a.rel='noopener';});"
    "document.querySelectorAll('.nomotoke-share-copy').forEach(function(a){"
    "a.addEventListener('click',function(e){e.preventDefault();"
    "navigator.clipboard.writeText(window.location.href)"
    ".then(function(){alert('URL をコピーしました');});});});"
    "})();"
    "</script>"
)


def _build_share_buttons_block(
    *, with_script: bool = True, source_url_fallback: str = ""
) -> str:
    """Return the share-buttons aside (X / LINE / copy).

    Audit fix A: the inline script attaches its handlers exactly
    once even when this helper is called multiple times — both via
    the ``window.__nomotokeShareInit`` JS guard AND, defensively, by
    letting callers pass ``with_script=False`` for every block after
    the first.

    Audit fix B: when ``source_url_fallback`` is provided AND the
    inline script gets stripped by WP's wp_kses on save (which
    happens for authors without ``unfiltered_html``), the buttons
    still resolve via a ``<noscript>``-style anchor pointing to the
    *source article* URL. Sharing the YOSHILOVER post URL is lost in
    that fallback path, but readers can still tap-share the source.
    """
    parts: list[str] = [_SHARE_BUTTONS_VISUAL_HTML]
    if with_script:
        parts.append(_SHARE_BUTTONS_SCRIPT_HTML)
    if source_url_fallback:
        safe_src = html.escape(source_url_fallback)
        parts.append(
            "<noscript>"
            '<p style="text-align:center;font-size:12px;'
            'color:#888;margin:6px 0 0;">'
            "JS が無効の場合は出典記事 URL を共有: "
            f'<a href="https://twitter.com/intent/tweet?url={safe_src}" '
            'target="_blank" rel="noopener">𝕏</a> · '
            f'<a href="https://social-plugins.line.me/lineit/share?url={safe_src}" '
            'target="_blank" rel="noopener">LINE</a>'
            "</p>"
            "</noscript>"
        )
    return "".join(parts)


def _decorate_body_with_emoji(content_html: str) -> str:
    """Apply ``_BODY_EMOJI_DECORATIONS`` to text fragments between
    HTML tags. Returns the modified body. Each keyword is decorated
    AT MOST ONCE per body so the post stays scannable."""
    if not content_html:
        return content_html
    used: set[str] = set()
    parts = re.split(r"(<[^>]+>)", content_html)
    for i, part in enumerate(parts):
        if part.startswith("<") or not part:
            continue
        text = part
        for keyword, emoji in _BODY_EMOJI_DECORATIONS:
            if keyword in used:
                continue
            idx = text.find(keyword)
            if idx < 0:
                continue
            # Avoid double-decorating when the writer already prefixed
            # the same keyword with this emoji (e.g. ``🏆 勝利``
            # already in place). Look at the 3 chars preceding the
            # keyword for the same emoji.
            if idx >= 1 and text[max(0, idx - 3) : idx].endswith(emoji):
                used.add(keyword)
                continue
            # Inject emoji + a single space between emoji and keyword.
            replacement = f"{emoji} {keyword}"
            # Special case for the " vs " pattern — already wraps
            # spaces inside the keyword.
            if keyword == " vs ":
                replacement = " ⚔️ "
            text = text[:idx] + replacement + text[idx + len(keyword) :]
            used.add(keyword)
        parts[i] = text
    return "".join(parts)


# NOMOTOKE-RSS-PIPELINE-ENRICHMENT-001 (Phase 3): public entry
# point reused by rss_fetcher.py (RSS auto-pipeline) so every
# nomotoke-rendered RSS post receives the same Phase 1〜N readers'
# blocks the manual-intake form path produces.
#
# Design:
# - Conditional gate: returns ``content_html`` unchanged when no
#   ``class="nomotoke-card-`` marker is present (Gemini-generated
#   bodies / legacy rule-based bodies stay untouched).
# - Skips enrichments that need ``og_image`` / ``raw_html`` /
#   ``source_published_at_iso`` when those values are not provided
#   (the rss_fetcher chokepoint doesn't have them).
# - All helper functions referenced here are the existing module-
#   level helpers; this function is a thin orchestration wrapper.

def apply_rss_pipeline_enrichment(
    content_html: str,
    *,
    title: str,
    source_url: str,
    category: str = "",
    template_key: str = "",
    summary: str = "",
    source_name: str = "",
    source_published_at_iso: str = "",
    og_image: str = "",
    raw_html: str = "",
) -> str:
    """Public Phase 3 entry point. Apply post-body enrichment to a
    nomotoke-renderer body. Returns the input unchanged when the
    body is not a nomotoke-renderer output (defensive gate)."""
    if not content_html or 'class="nomotoke-card-' not in content_html:
        return content_html
    if not source_name:
        source_name = _infer_source_name(source_url)

    extra_blocks: list[str] = []

    related_query = ""
    ngrams = re.findall(r"[一-龥ぁ-んァ-ヶー]{2,8}", title or "")
    related_query = max(ngrams, key=len) if ngrams else ""
    if related_query:
        block = _build_related_articles_block(related_query)
        if block:
            extra_blocks.append(block)

    if template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_pregame_pitcher_v1",
    ):
        block = _build_recent_games_block()
        if block:
            extra_blocks.append(block)

    scan_text = " ".join(s for s in (title, summary) if s)
    if scan_text:
        block = _build_player_stats_block(scan_text)
        if block:
            extra_blocks.append(block)
            content_html = re.sub(
                r'<aside class="nomotoke-roster">.*?</aside>',
                "",
                content_html,
                count=1,
                flags=re.DOTALL,
            )

    if template_key == "nomotoke_card_official_notice_v1":
        block = _build_recent_notice_timeline_block()
        if block:
            extra_blocks.append(block)

    if template_key == "nomotoke_card_postgame_v1":
        block = _build_other_games_block()
        if block:
            extra_blocks.append(block)

    if template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_manager_comment_v1",
        "nomotoke_card_player_comment_v1",
        "nomotoke_card_pregame_pitcher_v1",
        "nomotoke_card_video_v1",
        "nomotoke_card_official_notice_v1",
    ):
        block = _build_x_embeds_block(title, summary)
        if block:
            extra_blocks.append(block)

    if template_key in (
        "nomotoke_card_short_news_url_v1",
        "nomotoke_card_postgame_v1",
        "nomotoke_card_pregame_pitcher_v1",
        "nomotoke_card_manager_comment_v1",
        "nomotoke_card_player_comment_v1",
    ):
        block = _build_standings_block()
        if block:
            extra_blocks.append(block)
        block = _build_next_game_block()
        if block:
            extra_blocks.append(block)

    block = _build_trust_badge_block(source_name, source_url)
    if block:
        extra_blocks.append(block)

    if extra_blocks:
        content_html = _insert_blocks_before_source_h3(content_html, extra_blocks)

    # Reader UX layer
    content_html, toc_entries = _inject_toc_anchors(content_html)
    toc_html = _build_toc_block(toc_entries)
    meta_html = _build_meta_header_bar(content_html, source_published_at_iso)
    share_top = _build_share_buttons_block(source_url_fallback=source_url)
    top_cta = (
        '<p class="nomotoke-cta-row" '
        'style="margin:8px 0 12px;text-align:center;">'
        '<a href="#respond" '
        'style="display:inline-block;padding:10px 22px;'
        "background:#f57f17;color:#fff;text-decoration:none;"
        "border-radius:8px;font-weight:700;font-size:15px;"
        'box-shadow:0 2px 6px rgba(245,127,23,0.4);">'
        "💬 この記事にコメントする"
        "</a></p>"
    )
    header_payload = ""
    if meta_html:
        header_payload += meta_html
    header_payload += top_cta
    if share_top:
        header_payload += share_top
    if toc_html:
        header_payload += toc_html
    if header_payload:
        content_html = header_payload + content_html

    content_html = _wrap_first_roster_names_in_lead(content_html)

    chip_block = _build_tag_chip_block(
        title=title,
        summary=summary,
        content_html=content_html,
        category=category,
    )
    if chip_block:
        content_html = _insert_blocks_before_source_h3(content_html, [chip_block])

    content_html = _insert_blocks_before_source_h3(
        content_html, [_build_share_buttons_block(with_script=False)]
    )

    content_html = _decorate_body_with_emoji(content_html)

    schema_block = _build_jsonld_article_schema(
        title=title,
        summary=summary,
        source_url=source_url,
        source_name=source_name,
        source_published_at_iso=source_published_at_iso,
        og_image=og_image,
        raw_html=raw_html,
    )
    if schema_block:
        content_html = content_html + schema_block

    return content_html


def _build_lineup_block(home_lineup: list[dict], away_lineup: list[dict]) -> str:
    """Render the 「📊 今日のスタメン」 block. Empty when both lists are
    empty."""
    if not home_lineup and not away_lineup:
        return ""

    def _render_table(rows: list[dict]) -> str:
        if not rows:
            return ""
        lis = "".join(
            f'<li>{html.escape(r.get("order", ""))}番 '
            f'({html.escape(r.get("position", ""))}) '
            f'{html.escape(r.get("name", ""))}</li>'
            for r in rows
            if r.get("name")
        )
        return f"<ol>{lis}</ol>" if lis else ""

    parts: list[str] = []
    parts.append(
        '<aside class="nomotoke-lineup">'
        '<p class="nomotoke-lineup__label">📊 今日のスタメン</p>'
    )
    home_html = _render_table(home_lineup)
    if home_html:
        parts.append('<div class="nomotoke-lineup__home">')
        parts.append('<p class="nomotoke-lineup__team-label">ホーム</p>')
        parts.append(home_html)
        parts.append("</div>")
    away_html = _render_table(away_lineup)
    if away_html:
        parts.append('<div class="nomotoke-lineup__away">')
        parts.append('<p class="nomotoke-lineup__team-label">ビジター</p>')
        parts.append(away_html)
        parts.append("</div>")
    parts.append("</aside>")
    return "".join(parts)


def _is_safe_https_image_url(url: str) -> bool:
    """Allow only https URLs ending in a common image extension. Used to
    gate the optional hero-figure prepend so a malformed og:image never
    becomes an XSS vector or a mixed-content warning on the public post.
    """
    if not url or not isinstance(url, str):
        return False
    if not url.startswith("https://"):
        return False
    if '"' in url or "'" in url or "<" in url or ">" in url:
        return False
    lowered = url.lower().split("?", 1)[0]
    return lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


def _title_quality_failure_reason(title: str) -> str:
    if not title:
        return "title_empty"
    if len(title.strip()) < _MIN_TITLE_CHARS:
        return "title_too_short"
    return ""


def _normalize_title_for_dedupe(title: str) -> str:
    return re.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", (title or "")).lower()


def _resolve_wp_category_ids(category: str, logger: logging.Logger | None = None) -> list[int] | None:
    requested = (category or "").strip() or DEFAULT_CATEGORY_NAME
    names = [requested]
    if requested != DEFAULT_CATEGORY_NAME:
        names.append(DEFAULT_CATEGORY_NAME)

    mapping_path = ROOT / "config" / "categories.json"
    mapping: dict[str, Any] = {}
    try:
        if mapping_path.exists():
            mapping = json.loads(mapping_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        if logger is not None:
            logger.warning("category_mapping_load_failed: %s", exc)

    for index, name in enumerate(names):
        try:
            category_id = int(mapping.get(name) or 0)
        except Exception:
            category_id = 0
        if category_id > 0:
            if index > 0 and logger is not None:
                logger.warning("manual_intake_category_fallback requested=%s fallback=%s", requested, name)
            return [category_id]
    if logger is not None:
        logger.warning("manual_intake_category_unresolved category=%s", requested)
    return None


def _is_history_duplicate_local(
    history: dict, *, source_url: str, entry_title_norm: str
) -> bool:
    if source_url and source_url in history:
        return True
    if entry_title_norm and len(entry_title_norm) > 5:
        if f"title:{entry_title_norm[:60]}" in history:
            return True
    return False


def _resolve_routing_lightweight(
    *,
    title: str,
    summary: str,
    source_url: str,
    source_kind: str,
    logger: logging.Logger,
) -> tuple[str, str]:
    """Best-effort category + subtype. Falls back to safe defaults."""
    text = f"{title} {summary}"
    try:
        from rss_fetcher import classify_category as _classify
        from rss_fetcher import _detect_article_subtype as _detect_subtype
    except Exception:
        return "選手情報", source_kind

    keywords: dict[str, Any] = {}
    keywords_path = ROOT / "config" / "keywords.json"
    try:
        if keywords_path.exists():
            keywords = json.loads(keywords_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("keywords_load_failed: %s", exc)

    try:
        category = _classify(text, keywords, source_url=source_url, logger=logger) or "選手情報"
    except Exception as exc:
        logger.warning("classify_category_failed: %s", exc)
        category = "選手情報"
    try:
        subtype = _detect_subtype(title, summary, category, False) or source_kind
    except Exception as exc:
        logger.warning("detect_subtype_failed: %s", exc)
        subtype = source_kind
    return category, subtype


def _safe_load_history(logger: logging.Logger) -> dict:
    try:
        from rss_fetcher import load_history
        return load_history() or {}
    except Exception as exc:
        logger.warning("load_history_failed: %s", exc)
        return {}


def _wp_create_draft(
    wp,
    *,
    title: str,
    content: str,
    category: str,
    source_url: str,
    source_published_at_iso: str,
    logger: logging.Logger,
) -> tuple[int | None, str | None]:
    """Create a draft via WPClient. WPClient has its own dedupe via
    find_recent_post_by_title + source_url. Returns (post_id, draft_url).
    Caller name 'manual_intake' is recorded for audit."""
    categories = _resolve_wp_category_ids(category, logger)
    result = wp.create_post(
        title=title,
        content=content,
        categories=categories,
        status="draft",
        source_url=source_url,
        caller="manual_intake",
        source_lane="manual_intake",
        source_published_at_iso=source_published_at_iso or None,
    )
    post_id: int | None
    draft_url: str | None = None
    if isinstance(result, dict):
        post_id = result.get("id")
        draft_url = result.get("link")
    elif isinstance(result, int):
        post_id = result
    else:
        post_id = None
    if not post_id:
        raise RuntimeError("wp_create_post_returned_no_id")
    return post_id, draft_url


def run_manual_intake(
    *,
    url: str,
    memo: str = "",
    mode: str = "draft",
    title_override: str = "",
    summary_override: str = "",
    source_published_at: str = "",
    article_type: str = ARTICLE_TYPE_AUTO,
    wp_client_factory: Callable[[], Any] | None = None,
    rate_limit_lockfile: Path | None = None,
    fetch_meta: Callable[..., dict[str, str]] = _fetch_news_meta,
    logger: logging.Logger | None = None,
    manual_facts: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run the manual intake pipeline.

    Returns (exit_code, output_dict). memo NEVER reaches body / source_text /
    Gemini prompt — it lives only in the output dict for operator audit.
    """
    logger = logger or logging.getLogger("manual_intake")
    output: dict[str, Any] = {
        "ok": False,
        "mode": mode,
        "url": url,
        "source_url": "",
        "source_kind": "",
        "title": "",
        "category": "",
        "subtype": "",
        "template_key": "manual_intake",
        "status_id": "",
        "duplicate": False,
        "validation_ok": False,
        "reason": "",
        "skip_reason": "",
        "post_id": None,
        "draft_url": None,
        "normalized_source_published_at": "",
        "article_type": ARTICLE_TYPE_AUTO,
        "article_type_source": "auto_detected",
    }

    if not _is_valid_url(url):
        output["reason"] = "invalid_url"
        return EXIT_INVALID_URL, output

    canonical_article_type, at_error = _normalize_article_type(article_type)
    if at_error:
        output["reason"] = "validation_failed"
        output["skip_reason"] = at_error
        return EXIT_INVALID_ARTICLE_TYPE, output
    output["article_type"] = canonical_article_type
    output["article_type_source"] = (
        "auto_detected" if canonical_article_type == ARTICLE_TYPE_AUTO else "user_override"
    )

    normalized_source_published_at, sp_error = _normalize_source_published_at(
        source_published_at
    )
    if sp_error:
        output["reason"] = "validation_failed"
        output["skip_reason"] = sp_error
        return EXIT_INVALID_SOURCE_PUBLISHED_AT, output
    output["normalized_source_published_at"] = normalized_source_published_at

    lockfile = rate_limit_lockfile or DEFAULT_LOCKFILE
    allowed, retry_after = _check_rate_limit(lockfile)
    if not allowed:
        output["reason"] = "rate_limited"
        output["retry_after_sec"] = retry_after
        return EXIT_RATE_LIMITED, output

    is_x = _is_x_url(url)
    source_kind = "x" if is_x else "news"
    output["source_kind"] = source_kind
    canonical_source_url = _normalize_x_url_to_twitter(url) if is_x else url
    output["source_url"] = canonical_source_url

    if is_x:
        status_id = _extract_x_status_id(url)
        output["status_id"] = status_id
        if not status_id:
            output["reason"] = "x_url_status_id_not_found"
            return EXIT_INVALID_URL, output

    title = (title_override or "").strip()
    summary = (summary_override or "").strip()

    og_image = ""
    raw_html = ""
    if is_x:
        if not title and not summary:
            output["reason"] = "missing_title_or_summary"
            return EXIT_MISSING_TITLE_OR_SUMMARY, output
        if not title and summary:
            title = summary[:60]
    else:
        # NOMOTOKE-INTAKE-HERO-001 / POSTGAME-001: always fetch meta so
        # og_image (hero figure) and _html (postgame boxscore parser
        # input) are available even when the operator pre-supplied
        # title / summary. Failure is non-fatal here — the legacy
        # fallback below covers the title/summary missing case.
        meta = fetch_meta(url)
        if "_error" in meta and not (title or summary):
            # Audit fix D: the legacy reason string was the noisy
            # ``fetch_failed:fetch_failed:HTTPError``. Strip the
            # internal prefix so the operator sees a single,
            # actionable phrase.
            raw_err = (meta.get("_error") or "fetch_failed:unknown").strip()
            base_err = raw_err.split(":", 1)[-1] if raw_err.startswith("fetch_failed:") else raw_err
            friendly = {
                "HTTPError": "サイトが応答しません (404/403/500 等の可能性)。URL を確認して再試行してください。",
                "URLError": "サイトに接続できません (DNS / ネットワーク障害の可能性)。",
                "TimeoutError": "サイト応答がタイムアウトしました。少し待って再試行してください。",
                "UnicodeDecodeError": "サイト本文の文字コード解析に失敗しました。",
            }.get(base_err, f"取得失敗 ({base_err})")
            output["reason"] = f"fetch_failed:{friendly}"
            return EXIT_FETCH_FAILED, output
        if not title:
            title = (meta.get("title", "") or "").strip()
        if not summary:
            summary = (meta.get("summary", "") or "").strip()
        og_image = (meta.get("image", "") or "").strip()
        raw_html = meta.get("_html", "") or ""
        if not title or not summary:
            output["reason"] = "missing_title_or_summary"
            return EXIT_MISSING_TITLE_OR_SUMMARY, output

    output["title"] = title

    title_fail = _title_quality_failure_reason(title)
    if title_fail:
        output["skip_reason"] = title_fail
        output["reason"] = "validation_failed"
        return EXIT_VALIDATION_FAILED, output

    category, subtype = _resolve_routing_lightweight(
        title=title,
        summary=summary,
        source_url=canonical_source_url,
        source_kind=source_kind,
        logger=logger,
    )
    template_key = "manual_intake"
    if canonical_article_type != ARTICLE_TYPE_AUTO:
        override_category, override_subtype, override_template = ARTICLE_TYPE_OVERRIDES[
            canonical_article_type
        ]
        category = override_category
        subtype = override_subtype
        template_key = override_template
    output["category"] = category
    output["subtype"] = subtype
    output["template_key"] = template_key
    # Resolve category name -> WP category_id list eagerly so the service /
    # CLI audit JSON shows the IDs that will actually be sent to WP. The
    # category name itself is never sent to WP — only the resolved IDs.
    resolved_category_ids = _resolve_wp_category_ids(category, logger)
    output["category_ids"] = list(resolved_category_ids) if resolved_category_ids else []

    entry_title_norm = _normalize_title_for_dedupe(title)
    history = _safe_load_history(logger)
    if _is_history_duplicate_local(
        history,
        source_url=canonical_source_url,
        entry_title_norm=entry_title_norm,
    ):
        output["duplicate"] = True
        output["reason"] = "history_duplicate"
        return EXIT_DUPLICATE, output

    output["validation_ok"] = True
    output["source_name"] = _infer_source_name(url)

    if mode == "dry-run":
        output["ok"] = True
        return EXIT_OK, output

    if wp_client_factory is None:
        output["reason"] = "wp_client_factory_not_provided"
        return EXIT_WP_DRAFT_FAILED, output

    body: str | None = None
    # NOMOTOKE-INTAKE-TEMPLATE-001: when the operator picked a specific
    # article_type that maps to a nomotoke template, try that renderer
    # first. Falls back to the basic ``<p>summary</p>+出典`` shape if the
    # renderer's required-fact gate cannot be satisfied (so the
    # operator's pick never produces a hard error — they still get a
    # draft, just without the rich card).
    if not is_x and template_key.startswith("nomotoke_card_"):
        body = _try_render_via_nomotoke(
            template_key,
            title=title,
            summary=summary,
            source_url=canonical_source_url,
            source_name=output.get("source_name", ""),
            source_published_at_iso=normalized_source_published_at,
            is_x=is_x,
            og_image=og_image,
            raw_html=raw_html,
            manual_facts=manual_facts or {},
        )
    if body is None:
        if is_x:
            body = _build_body_for_x(canonical_source_url)
        else:
            body = _build_body_for_news(
                canonical_source_url, title, summary, og_image=og_image
            )

    if memo:
        if memo in body:
            raise AssertionError("memo must not appear in WP draft body")
        if memo in title:
            raise AssertionError("memo must not appear in WP draft title")

    try:
        wp = wp_client_factory()
        post_id, draft_url = _wp_create_draft(
            wp,
            title=title,
            content=body,
            category=category,
            source_url=canonical_source_url,
            source_published_at_iso=normalized_source_published_at,
            logger=logger,
        )
    except AssertionError:
        raise
    except Exception as exc:
        output["reason"] = f"wp_draft_failed:{exc.__class__.__name__}"
        logger.error("wp_draft_create_failed: %s", exc)
        return EXIT_WP_DRAFT_FAILED, output

    output["post_id"] = post_id
    output["draft_url"] = draft_url
    output["ok"] = True
    output["downstream_handoff"] = "guarded_publish_polling"
    if memo:
        output["memo"] = memo
    return EXIT_OK, output


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.manual_intake",
        description=(
            "Manually intake a URL/X URL/news URL into the YOSHILOVER WP draft "
            "pipeline. Default --mode 'draft'. Memo is operator-only; it never "
            "reaches body / source_text / Gemini prompt."
        ),
    )
    p.add_argument("url", help="target URL (news article or X status URL)")
    p.add_argument(
        "--memo",
        default="",
        help="operator memo (NOT injected into body / source_text / Gemini prompt)",
    )
    p.add_argument(
        "--mode",
        choices=("draft", "dry-run"),
        default="draft",
        help="default 'draft'; 'dry-run' skips WP write",
    )
    p.add_argument("--title", default="", help="override fetched title")
    p.add_argument("--summary", default="", help="override fetched summary")
    p.add_argument(
        "--source-published-at",
        default="",
        help=(
            "optional ISO 8601 source publish timestamp "
            "(naive treated as JST, Z/UTC offsets normalized to JST). "
            "Used as freshness/source-time metadata only — never as a fact source."
        ),
    )
    p.add_argument(
        "--article-type",
        default=ARTICLE_TYPE_AUTO,
        choices=ARTICLE_TYPE_CHOICES,
        help=(
            "optional article-type classification override. Default 'auto' "
            "uses the existing detector; explicit values pin category / "
            "subtype / template_key. Article type is metadata only — it is "
            "NEVER used as a source fact."
        ),
    )
    # NOMOTOKE-INTAKE-MANUAL-FACTS-001: per-template optional facts for
    # cases where regex extraction cannot recover the field cleanly.
    # Operator-supplied values bypass the regex / allowlist gates of
    # the matching renderer (manager / player / pregame / video /
    # official_notice). Each value is treated as a literal string and
    # is HTML-escaped at render time — no template-level fabrication.
    p.add_argument("--manager-name", default="", help="manager_comment override")
    p.add_argument("--player-name", default="", help="player_comment / video override")
    p.add_argument("--quote", default="", help="quote_short override (manager / player)")
    p.add_argument("--pitcher-a", default="", help="pregame_pitcher Giants 先発")
    p.add_argument("--pitcher-b", default="", help="pregame_pitcher 相手 先発")
    p.add_argument("--team-b", default="", help="pregame_pitcher 対戦相手 team")
    p.add_argument("--play-summary", default="", help="video play_summary override")
    p.add_argument("--registered", default="", help="official_notice 登録選手 (comma-separated)")
    p.add_argument("--removed", default="", help="official_notice 抹消選手 (comma-separated)")
    return p


def _default_wp_client_factory():
    from wp_client import WPClient
    return WPClient()


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("manual_intake")

    try:
        exit_code, output = run_manual_intake(
            url=args.url,
            memo=args.memo,
            mode=args.mode,
            title_override=args.title,
            summary_override=args.summary,
            source_published_at=args.source_published_at,
            article_type=args.article_type,
            wp_client_factory=_default_wp_client_factory,
            logger=logger,
            manual_facts={
                "manager_name": args.manager_name,
                "player_name": args.player_name,
                "quote": args.quote,
                "pitcher_a": args.pitcher_a,
                "pitcher_b": args.pitcher_b,
                "team_b": args.team_b,
                "play_summary": args.play_summary,
                "registered": args.registered,
                "removed": args.removed,
            },
        )
    except SystemExit:
        raise
    except Exception as exc:
        logger.exception("manual_intake_unexpected_error")
        print(
            json.dumps(
                {"ok": False, "reason": f"unexpected:{exc.__class__.__name__}"},
                ensure_ascii=False,
            )
        )
        return EXIT_UNEXPECTED

    print(json.dumps(output, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
