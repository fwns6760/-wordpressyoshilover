"""NOMOTOKE-INTAKE-BODY-EXCERPT-001 — local-only, no-LLM article body
excerpt extractor.

Goal
====

Pull a short (≤240 char) plain-text excerpt of the source article body
from raw HTML, suitable for inclusion as a 引用 block. The excerpt MUST
be a literal substring of the source HTML (after tag stripping +
entity decoding) so:

- ハルシネーションは構造的に発生しない (literal substring 抽出のみ)
- 著作権上の引用要件を満たす範囲 (≤240 字 / 2-3 文) に収める
- 必ず出典を明示する用途で使う

Strategy
========

1. JSON-LD ``Article.articleBody`` field — most news sites embed this.
   Fully-structured, deterministic, encoding-safe.
2. ``<article>`` element — HTML5 standard for news article body.
3. Site-specific selector table — hochi.news / sponichi.co.jp /
   nikkansports.com / sankei.com / news.yahoo.co.jp / Full-Count etc.
4. Generic class-name heuristic — ``article-body`` / ``news-text`` /
   ``post-content`` / ``entry-content`` / etc.
5. ``<meta name="description">`` — last-resort, returns empty if too
   short.

When all five fail, returns ``""``. The caller then renders the body
without the excerpt block (graceful fallback — no broken card).

Constraints
===========

- Pure parsing. No network. No LLM. No outbound call.
- Output is plain text — every HTML tag stripped, every entity decoded.
- Output never echoes the source title verbatim (that would just be
  duplicating the H1 the renderer already shows).
- Output is capped at ``max_chars`` (default 240) at the last 「。」 /
  「.」 sentence boundary above half the cap.
- Returns ``""`` on any parse error so the renderer never breaks.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Site-specific selector table
# ---------------------------------------------------------------------------
#
# Each entry: ``(host_substring, list[regex_pattern_with_named_group(body)])``.
# Patterns are matched against the raw HTML; the first non-empty body
# wins. Selectors are intentionally broad — site redesigns occasionally
# rename the wrapper class but rarely drop the structural ``<article>``
# tag, so the generic fallback usually still works.
_SITE_SELECTORS: tuple = (
    (
        "hochi.news",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\barticle__body\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
            re.compile(
                r'<div[^>]+class="[^"]*\bpreview__detail\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
            re.compile(
                r'<div[^>]+id="article-body"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
    (
        "sponichi.co.jp",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\barticle-body\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
    (
        "daily.co.jp",
        (
            re.compile(
                r'<div[^>]+id=["\']NWrelart:Body["\'][^>]*>(?P<body>.+?)</div>',
                re.DOTALL | re.IGNORECASE,
            ),
            re.compile(
                r'<div[^>]+class=["\'][^"\']*\bmainTxt\b[^"\']*["\'][^>]*>(?P<body>.+?)</div>',
                re.DOTALL | re.IGNORECASE,
            ),
        ),
    ),
    (
        "nikkansports.com",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\bnews-text\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
    (
        "sankei.com",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\barticle-body\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
    (
        "sanspo.com",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\barticle-body\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
    (
        "yahoo.co.jp",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\barticleBody\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
    (
        "full-count.jp",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\bc-wp-post\b[^"]*"[^>]*>(?P<body>.+?)</div>\s*<!--\s*s-entry-body\s*-->',
                re.DOTALL,
            ),
            re.compile(
                r'<div[^>]+class="[^"]*\bentry-content\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
    (
        "baseballking.jp",
        (
            re.compile(
                r'<div[^>]+class="[^"]*\bentry-content\b[^"]*"[^>]*>(?P<body>.+?)</div>',
                re.DOTALL,
            ),
        ),
    ),
)


_ARTICLE_TAG_RE = re.compile(
    r"<article\b[^>]*>(?P<body>.+?)</article>",
    re.DOTALL | re.IGNORECASE,
)

_GENERIC_CLASS_RE = re.compile(
    r'<(?:div|section)[^>]+class="[^"]*\b(?:article-body|articleBody|news-text|'
    r"post-content|entry-content|news-detail-text|main-content|article-text)"
    r'\b[^"]*"[^>]*>(?P<body>.+?)</(?:div|section)>',
    re.DOTALL | re.IGNORECASE,
)


_JSONLD_BLOCK_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<body>.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style|noscript)\b[^>]*>.*?</(?:script|style|noscript)>",
    re.DOTALL | re.IGNORECASE,
)
_ASIDE_RE = re.compile(r"<aside\b[^>]*>.*?</aside>", re.DOTALL | re.IGNORECASE)
_FIGURE_RE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.DOTALL | re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_OPEN_RE = re.compile(
    r"<(?:p|div|li|h[1-6])\b[^>]*>", re.IGNORECASE
)
_WHITESPACE_RUN_RE = re.compile(r"[　\s]+")
_DATE_LINE_RE = re.compile(
    r"^\[?\d{4}[./年]\d{1,2}(?:[./月]\d{1,2}日?)?"
    r"(?:\s*\d{1,2}(?::\d{2}(?::\d{2})?|時\d{1,2}分(?:\d{1,2}秒)?))?\]?$"
)
_YAHOO_DELIVERY_RE = re.compile(
    r"^\d{1,2}/\d{1,2}\([月火水木金土日]\)\s*\d{1,2}:\d{2}\s*配信$"
)
_COMMENT_COUNT_LABEL_RE = re.compile(r"^コメント\s*\d+\s*件$")
_DIGITS_ONLY_RE = re.compile(r"^\d{1,4}$")
_IMAGE_CAPTION_RE = re.compile(r"^[^\n]{0,60}（カメラ[・\s][^）]{0,40}）[^\n]{0,20}$")
_RELATED_LINK_MARKER_RE = re.compile(r"^【[^】]{1,30}】[^\n]*$")
_BOILERPLATE_LINES = {
    "PR",
    "広告",
    "ホーム",
    "野球",
    "ニュース",
    "RSS",
    "プロ野球",
    "読売ジャイアンツ（巨人）",
    "拡大",
    "続きを見る",
    "通知ON",
    "通知OFF",
    "野球スコア速報",
    "編集者のオススメ記事",
}


def _strip_html_to_plain(fragment: str) -> str:
    """Convert an HTML fragment to plain text.

    - ``<br>`` / ``<p>`` / ``<div>`` etc. become newlines so paragraph
      breaks survive the strip.
    - All other tags are removed.
    - Entities are decoded.
    - Whitespace runs collapse to single spaces (newlines preserved).
    """
    if not fragment:
        return ""
    s = _SCRIPT_STYLE_RE.sub("", fragment)
    s = _ASIDE_RE.sub("", s)
    s = _FIGURE_RE.sub("", s)
    s = _BR_RE.sub("\n", s)
    s = _BLOCK_OPEN_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = html_lib.unescape(s)
    # Collapse whitespace within each line, but preserve line breaks.
    lines = []
    for raw_line in s.split("\n"):
        cleaned = _WHITESPACE_RUN_RE.sub(" ", raw_line).strip()
        if not cleaned:
            continue
        low = cleaned.lower()
        if any(marker in low for marker in ("googletag", "document.write", "function()")):
            continue
        if cleaned in _BOILERPLATE_LINES:
            continue
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _normalize_title_echo_text(text: str) -> str:
    return _WHITESPACE_RUN_RE.sub(" ", html_lib.unescape(text or "")).strip()


_SENTENCE_END_CHARS = "。！？!?"
_QUOTE_CLOSE_CHARS = "」』）)"
_CLAUSE_BREAK_CHARS = "、,"
_CLEAN_TRAILING_WINDOW = 80


def _clean_trailing_fragment(text: str) -> str:
    """If ``text`` ends mid-word (no sentence / quote / paragraph
    boundary at the tail), step back to the nearest natural boundary
    within the trailing window.

    Without this safety net even short excerpts (e.g. JSON-LD
    ``articleBody`` that the publisher already truncated) can leak a
    fragment like ``…先制点が取れたことは大き`` into the rendered post.
    """
    if not text:
        return text
    t = text.rstrip()
    if not t:
        return t
    last = t[-1]
    if last in _SENTENCE_END_CHARS or last in _QUOTE_CLOSE_CHARS or last == "\n":
        return t
    cut_floor = max(0, len(t) - _CLEAN_TRAILING_WINDOW)
    sub = t[cut_floor:]
    for chars in (_SENTENCE_END_CHARS, _QUOTE_CLOSE_CHARS):
        last_idx = max((sub.rfind(ch) for ch in chars), default=-1)
        if last_idx >= 0:
            return t[: cut_floor + last_idx + 1]
    last_idx = max((sub.rfind(ch) for ch in _CLAUSE_BREAK_CHARS), default=-1)
    if last_idx >= 0:
        return t[: cut_floor + last_idx + 1].rstrip() + "…"
    return t


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    """Cap ``text`` at ``max_chars`` with a tiered boundary preference:

    1. Sentence-final 「。」 / 「！」 / 「？」 / 「!」 / 「?」 above half-cap
    2. Quote close 「」」 / 「』」 / 「）」 / 「)」 above half-cap
    3. Paragraph break ``\\n`` above half-cap
    4. Clause break 「、」 / 「,」 above half-cap, suffixed with 「…」
    5. Hard cut + 「…」

    When the text is already within ``max_chars`` it still passes
    through ``_clean_trailing_fragment`` so a publisher-truncated
    source body never ends mid-word.
    """
    if not text:
        return text
    if len(text) <= max_chars:
        return _clean_trailing_fragment(text)
    head = text[:max_chars]
    half = max_chars // 2

    last_idx = max((head.rfind(ch) for ch in _SENTENCE_END_CHARS), default=-1)
    if last_idx > half:
        return head[: last_idx + 1]

    last_idx = max((head.rfind(ch) for ch in _QUOTE_CLOSE_CHARS), default=-1)
    if last_idx > half:
        return head[: last_idx + 1]

    idx = head.rfind("\n")
    if idx > half:
        return head[:idx].rstrip()

    last_idx = max((head.rfind(ch) for ch in _CLAUSE_BREAK_CHARS), default=-1)
    if last_idx > half:
        return head[: last_idx + 1].rstrip() + "…"

    return head.rstrip() + "…"


def _drop_title_echo(text: str, title: str) -> str:
    """Remove a leading line that exactly echoes the article title.

    The renderer already prints the title in the H1; repeating it as
    the first line of the excerpt is noise. Mid-text title mentions
    are kept intact since they may be part of a quote or context."""
    if not text or not title:
        return text
    title_clean = _normalize_title_echo_text(title)
    if not title_clean:
        return text
    lines = text.split("\n", 1)
    if not lines:
        return text
    head = _normalize_title_echo_text(lines[0])
    if head and (head == title_clean or title_clean in head and len(head) <= len(title_clean) + 6):
        return lines[1] if len(lines) > 1 else ""
    return text


def _is_title_echo(head_for_title: str, title_clean: str) -> bool:
    """Return True when ``head_for_title`` is essentially the article
    title (in either direction): exact match, or one is a prefix /
    substring of the other within a small length tolerance.

    The asymmetric old check broke whenever the source body opened with
    a short version of the title and the caller passed in a long WP-
    stored title with publisher suffix (e.g. "（スポーツ報知）- Yahoo!
    ニュース"), leaving the title duplicated as the first excerpt line.
    """
    if not head_for_title or not title_clean:
        return False
    if head_for_title == title_clean:
        return True
    tol = 20
    if title_clean in head_for_title and len(head_for_title) <= len(title_clean) + tol:
        return True
    if head_for_title in title_clean and len(title_clean) <= len(head_for_title) + tol:
        return True
    # Prefix overlap: the shorter one is a leading slice of the longer
    # one, within tolerance. Catches the Yahoo case where the body
    # opens with "「正直言って…」堀内恒夫氏…アドバイス" and the WP title
    # appends "（スポーツ報知）- Yahoo!ニュース".
    # CAREFUL: this must NOT fire when ``head_for_title`` is a long
    # body paragraph that merely starts with the title (e.g. JSON-LD
    # articleBody coming back as one long string). Cap the longer side
    # at ``shorter + tol`` so this only matches a head line that is
    # essentially the title plus a short publisher / site suffix.
    shorter, longer = (
        (head_for_title, title_clean)
        if len(head_for_title) <= len(title_clean)
        else (title_clean, head_for_title)
    )
    # Allow a wider tolerance for the prefix-overlap case so the
    # Yahoo "<title>（スポーツ報知） - Yahoo!ニュース" suffix (~22 chars)
    # still gets recognised, but reject long body paragraphs that
    # merely begin with the title.
    prefix_tol = 30
    if (
        len(shorter) >= 12
        and longer.startswith(shorter)
        and len(longer) <= len(shorter) + prefix_tol
    ):
        return True
    return False


def _is_noise_line(line: str) -> bool:
    """Return True for lines that are navigation / date / comment-count /
    image-caption / related-link markers — never part of the article body.
    """
    if not line:
        return True
    if line in _BOILERPLATE_LINES:
        return True
    if _DATE_LINE_RE.match(line):
        return True
    if _YAHOO_DELIVERY_RE.match(line):
        return True
    if _COMMENT_COUNT_LABEL_RE.match(line):
        return True
    if _DIGITS_ONLY_RE.match(line):
        return True
    if _IMAGE_CAPTION_RE.match(line):
        return True
    if _RELATED_LINK_MARKER_RE.match(line):
        return True
    return False


def _drop_leading_boilerplate(text: str, title: str = "") -> str:
    """Remove leading navigation/date/title lines before body text."""
    if not text:
        return ""
    title_clean = _normalize_title_echo_text(title)
    lines = text.splitlines()
    while lines:
        head = lines[0].strip()
        head_for_title = _normalize_title_echo_text(head)
        if not head:
            lines.pop(0)
            continue
        if _is_noise_line(head):
            lines.pop(0)
            continue
        if _is_title_echo(head_for_title, title_clean):
            lines.pop(0)
            continue
        break
    # Also strip noise lines interleaved inside the first few lines
    # (Yahoo emits image caption between delivery date and body).
    cleaned: list[str] = []
    for ln in lines:
        if not cleaned and _is_noise_line(ln.strip()):
            continue
        if len(cleaned) < 3 and _is_noise_line(ln.strip()):
            continue
        cleaned.append(ln)
    return "\n".join(cleaned)


def _extract_via_jsonld(html: str) -> str:
    """Return the first non-empty JSON-LD ``Article.articleBody`` field
    found in the HTML, or ``""``.

    JSON-LD payloads can be a single object, a list, or an ``@graph``
    envelope. The first ``Article``-typed object with a string
    ``articleBody`` wins.
    """
    if not html:
        return ""
    for m in _JSONLD_BLOCK_RE.finditer(html):
        body = m.group("body").strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            continue
        nodes = []
        if isinstance(parsed, dict):
            nodes.append(parsed)
            graph = parsed.get("@graph")
            if isinstance(graph, list):
                nodes.extend(g for g in graph if isinstance(g, dict))
        elif isinstance(parsed, list):
            nodes.extend(p for p in parsed if isinstance(p, dict))
        for node in nodes:
            ab = node.get("articleBody")
            if isinstance(ab, str) and len(ab.strip()) >= 20:
                return ab.strip()
    return ""


def _extract_via_site_selectors(html: str, host: str) -> str:
    """Try the curated site-specific selector table for the matching
    host. Returns the inner HTML fragment or ``""``."""
    if not html or not host:
        return ""
    host_l = host.lower()
    for needle, patterns in _SITE_SELECTORS:
        if needle not in host_l:
            continue
        for pat in patterns:
            m = pat.search(html)
            if m:
                frag = m.group("body")
                if frag and len(frag.strip()) >= 20:
                    return frag
    return ""


def _extract_via_article_tag(html: str) -> str:
    """Return the inner HTML of the first ``<article>`` element, or
    ``""``."""
    if not html:
        return ""
    m = _ARTICLE_TAG_RE.search(html)
    if m:
        frag = m.group("body")
        if frag and len(frag.strip()) >= 30:
            return frag
    return ""


def _extract_via_generic_class(html: str) -> str:
    """Try common article-wrapper class names. Returns inner HTML or
    ``""``."""
    if not html:
        return ""
    m = _GENERIC_CLASS_RE.search(html)
    if m:
        frag = m.group("body")
        if frag and len(frag.strip()) >= 30:
            return frag
    return ""


def extract_article_body_excerpt(
    raw_html: str,
    source_url: str,
    *,
    max_chars: int = 240,
    title: str = "",
) -> str:
    """Return a plain-text excerpt of the article body, ≤``max_chars``.

    The result is a literal substring of the page (after tag stripping
    and entity decoding). Empty string when no body could be parsed.

    Args:
        raw_html: The full source-page HTML the caller already fetched.
        source_url: The canonical source URL — used only to pick the
            site-specific selector. No network call is made.
        max_chars: Soft cap — the truncator prefers the last sentence
            boundary above ``max_chars // 2`` so output never ends mid-
            word in the common case.
        title: The article H1 — used to drop a duplicated leading line
            that echoes the title.

    Returns:
        Plain-text excerpt (no HTML), or ``""`` when extraction failed
        on every strategy.
    """
    if not isinstance(raw_html, str) or not raw_html:
        return ""

    host = ""
    try:
        host = (urlparse(source_url).netloc or "").lower()
    except Exception:
        host = ""

    # Strategy ladder: JSON-LD → site selector → <article> → generic
    # class. Each strategy returns either a plain-text body (JSON-LD)
    # or an HTML fragment that must be stripped.
    candidates: list[tuple[str, bool]] = []

    jsonld_body = _extract_via_jsonld(raw_html)
    if jsonld_body:
        # JSON-LD articleBody is already plain text per spec.
        candidates.append((jsonld_body, False))

    site_frag = _extract_via_site_selectors(raw_html, host)
    if site_frag:
        candidates.append((site_frag, True))

    article_frag = _extract_via_article_tag(raw_html)
    if article_frag:
        candidates.append((article_frag, True))

    generic_frag = _extract_via_generic_class(raw_html)
    if generic_frag:
        candidates.append((generic_frag, True))

    for raw, needs_strip in candidates:
        text = _strip_html_to_plain(raw) if needs_strip else raw
        if not text:
            continue
        text = _drop_leading_boilerplate(text, title)
        text = _drop_title_echo(text, title)
        if len(text) < 20:
            continue
        return _truncate_at_sentence(text, max_chars)

    return ""


__all__ = ["extract_article_body_excerpt"]
