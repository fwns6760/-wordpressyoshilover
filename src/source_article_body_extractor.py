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
# Lines that contain a parenthesised photo / camera / source credit are
# caption metadata, not article body. Matches both half-width and
# full-width parens, and the common Japanese credit prefixes used by
# 報知 / 日テレ / NHK / 朝日 / 産経 / 共同 等. The line is dropped wholesale
# (description + credit together) — these blocks never belong inline
# with the article narrative.
_PHOTO_CREDIT_LINE_RE = re.compile(
    r"[（(]\s*(?:写真|撮影|提供|画像|Photo|PHOTO)\s*[：:＝=／/]?\s*[^）)]{0,60}[）)]\s*$"
)
# Copyright / rights footer lines.
_COPYRIGHT_LINE_RE = re.compile(
    r"^\s*(?:©|Ⓒ|\(c\)|（c）|Copyright|COPYRIGHT|無断複写|無断転載|All\s+Rights\s+Reserved)",
    re.IGNORECASE,
)
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
    # Share / SNS UI button labels that React-rendered news sites
    # (e.g. news.ntv.co.jp) emit as separate sibling <p>/<button>
    # nodes inside the article container. Each label only ever
    # appears alone on its own line in the chrome; real article
    # prose never reduces to a single one of these words.
    "スポーツ",
    "ポスト",
    "ツイート",
    "送る",
    "シェア",
    "ブックマーク",
    "コピー",
    "URLをコピー",
    "リンクをコピー",
    "クリップボードにコピー",
    "クリップボードにコピーしました",
    "シェアする",
    "保存",
    "保存する",
    "もっと見る",
    "いいね",
    "メール",
    "印刷",
    "LINEで送る",
    "Facebookでシェア",
    "Xでシェア",
    "Twitterでシェア",
    "はてブ",
    "Pocket",
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
        if _PHOTO_CREDIT_LINE_RE.search(cleaned):
            continue
        if _COPYRIGHT_LINE_RE.match(cleaned):
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
    if _PHOTO_CREDIT_LINE_RE.search(line):
        return True
    if _COPYRIGHT_LINE_RE.match(line):
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


_DIV_OPEN_RE = re.compile(r"<div\b", re.IGNORECASE)
_DIV_CLOSE_RE = re.compile(r"</div\s*>", re.IGNORECASE)


def _extract_balanced_div_inner(html: str, opening_pattern: "re.Pattern[str]") -> str:
    """opening_pattern (1 つの開始 div tag を必ず match する regex) を起点に、
    div 入れ子をカウントして balanced な inner HTML を返す。

    sanspo のように nested ``<div>`` 内に本物 body が埋まっていて、非貪欲
    ``.+?`` regex が最初の内側 ``</div>`` で停止して fragment が空になる
    ケースを正しく扱うため (#16 / 337-INGEST Phase 3)。
    開始 tag が見つからない / 閉じ div が無い場合は ``""``。
    """
    m = opening_pattern.search(html)
    if not m:
        return ""
    body_start = m.end()
    depth = 1
    pos = body_start
    n = len(html)
    while pos < n:
        next_open = _DIV_OPEN_RE.search(html, pos)
        next_close = _DIV_CLOSE_RE.search(html, pos)
        if not next_close:
            return ""
        if next_open and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            if depth == 0:
                return html[body_start:next_close.start()]
            pos = next_close.end()
    return ""


_SANSPO_OPENING_DIV_RE = re.compile(
    r'<div[^>]+class="[^"]*\barticle-body\b[^"]*"[^>]*>',
    re.IGNORECASE,
)


_SIRABEE_POST_ID_RE = re.compile(r"sirabee\.com/\d{4}/\d{1,2}/\d{1,2}/(\d+)/?")


def _extract_via_sirabee_wpjson(source_url: str) -> str:
    """Fetch the full article body via Shirabee's public WordPress REST API.

    Shirabee (sirabee.com) is a client-side rendered SPA — the static HTML
    only contains Vue template placeholders. Its WordPress REST endpoint
    (``/wp-json/wp/v2/posts/<id>``) returns the SSR body in
    ``content.rendered`` as a small JSON payload (no auth, no quota).

    Returns the HTML body string (caller will strip via
    ``_strip_html_to_plain``), or ``""`` on any failure so the strategy
    ladder falls through.
    """
    if not source_url:
        return ""
    m = _SIRABEE_POST_ID_RE.search(source_url)
    if not m:
        return ""
    post_id = m.group(1)
    try:
        import requests as _requests
    except Exception:
        return ""
    api_url = f"https://sirabee.com/wp-json/wp/v2/posts/{post_id}"
    try:
        resp = _requests.get(api_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return ""
        data = resp.json()
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    content = ((data.get("content") or {}).get("rendered") or "")
    if not isinstance(content, str) or not content.strip():
        return ""
    return content


def _extract_via_giants_jp_next_data(html: str) -> str:
    """giants.jp の Next.js SSR HTML から本文を抽出。

    Page HTML 内 ``<script id="__NEXT_DATA__">…</script>`` の JSON に、
    ``props.pageProps.responseNewsDetail.result[0].contents.__dynamic_parts``
    の配列が入っている。各要素の ``items.headline`` と ``items.text`` を
    順番に結合してプレーンテキスト本文として返す。

    抽出失敗時は空文字 (silent fallback to next strategy)。
    """
    import json as _json
    import re as _re

    m = _re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        _re.S,
    )
    if not m:
        return ""
    try:
        data = _json.loads(m.group(1))
    except (ValueError, _json.JSONDecodeError):
        return ""

    try:
        result = (
            data.get("props", {})
            .get("pageProps", {})
            .get("responseNewsDetail", {})
            .get("result")
        )
    except AttributeError:
        return ""
    if not isinstance(result, list) or not result:
        return ""

    contents = result[0].get("contents") or {}
    parts = contents.get("__dynamic_parts") or []
    if not isinstance(parts, list):
        return ""

    paragraphs: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        items = part.get("items") or {}
        if not isinstance(items, dict):
            continue
        headline = (items.get("headline") or "").strip()
        text = (items.get("text") or "").strip()
        if headline:
            paragraphs.append(headline)
        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs).strip()


_NIKKAN_GENDAI_PUBLISH_DATE_RE = re.compile(r"^(?:公開日|更新日)：")
_NIKKAN_GENDAI_SKIP_LINE_RE = re.compile(
    r"^(?:記事|印刷|>>\s*バックナンバー|\d+|[1-9]\d?\.\d+万)$"
)
_NIKKAN_GENDAI_STOP_LINE_RE = re.compile(
    r"^(?:次ページ|次へ|政治・社会|芸能|ライフ|マネー|健康|BOOKS|"
    r"最新のスポーツ記事|野球のアクセスランキング|編集部オススメ|"
    r"人気キーワード|アクセスランキング|もっと見る)"
)


def _extract_via_nikkan_gendai_plain(html: str, title: str = "") -> str:
    """Extract www.nikkan-gendai.com article prose from the full page text.

    Nikkan Gendai pages currently expose only a short meta description to
    the generic strategies used here, while the visible article text is
    surrounded by navigation, pagination, rankings, and related lists. Use
    the rendered H1/title neighborhood as the anchor, then stop at the
    first pagination / site-chrome marker.
    """
    if not html:
        return ""
    plain = _strip_html_to_plain(html)
    if not plain:
        return ""

    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    if not lines:
        return ""

    title_clean = _normalize_title_echo_text(title)
    start = 0
    if title_clean:
        title_indexes = [
            idx
            for idx, line in enumerate(lines)
            if _is_title_echo(_normalize_title_echo_text(line), title_clean)
        ]
        dated_title_indexes = [
            idx
            for idx in title_indexes
            if any(
                _NIKKAN_GENDAI_PUBLISH_DATE_RE.match(lines[j])
                for j in range(idx + 1, min(len(lines), idx + 8))
            )
        ]
        if dated_title_indexes:
            start = dated_title_indexes[-1] + 1
        elif title_indexes:
            start = title_indexes[-1] + 1
    if start == 0:
        for idx, line in enumerate(lines):
            if _NIKKAN_GENDAI_PUBLISH_DATE_RE.match(line):
                start = idx + 1
                break

    body_lines: list[str] = []
    for line in lines[start:]:
        if _NIKKAN_GENDAI_STOP_LINE_RE.match(line):
            if body_lines:
                break
            continue
        if _is_noise_line(line):
            continue
        if _NIKKAN_GENDAI_PUBLISH_DATE_RE.match(line):
            continue
        if _NIKKAN_GENDAI_SKIP_LINE_RE.match(line):
            continue
        if "この記事の画像を見る" in line:
            continue
        if title_clean and _is_title_echo(_normalize_title_echo_text(line), title_clean):
            continue
        body_lines.append(line)
        if len("\n".join(body_lines)) >= 1800:
            break

    return "\n".join(body_lines).strip()


def _extract_via_site_selectors(html: str, host: str) -> str:
    """Try the curated site-specific selector table for the matching
    host. Returns the inner HTML fragment or ``""``."""
    if not html or not host:
        return ""
    host_l = host.lower()
    if "sanspo.com" in host_l:
        balanced = _extract_balanced_div_inner(html, _SANSPO_OPENING_DIV_RE)
        if balanced and len(balanced.strip()) >= 20:
            return balanced
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

    # ticket 421: sirabee.com は client-side rendered SPA で HTML 内の
    # `<div class="article-content">` は ${article.title} 等の Vue template
    # placeholder のみ含む → HTML 解析戦略は全て fail。 同 site の公開
    # WordPress REST API (/wp-json/wp/v2/posts/<id>) は SSR で full body
    # を返すので、 そこを 1 fetch で取得する。 cost ¥0、 認証不要。
    if "sirabee.com" in host:
        sirabee_body = _extract_via_sirabee_wpjson(source_url)
        if sirabee_body:
            candidates.append((sirabee_body, True))

    jsonld_body = _extract_via_jsonld(raw_html)
    if jsonld_body:
        # JSON-LD articleBody is already plain text per spec.
        candidates.append((jsonld_body, False))

    # 2026-05-15 giants.jp は Next.js SPA で本文が __NEXT_DATA__ JSON 内に
    # ある。news / 試合関連ページの responseNewsDetail / responseGameDetail を
    # 検出して dynamic_parts.items.text を結合する。
    if "giants.jp" in host:
        next_body = _extract_via_giants_jp_next_data(raw_html)
        if next_body:
            candidates.append((next_body, False))

    if host in {"www.nikkan-gendai.com", "nikkan-gendai.com"}:
        nikkan_gendai_body = _extract_via_nikkan_gendai_plain(raw_html, title=title)
        if nikkan_gendai_body:
            candidates.append((nikkan_gendai_body, False))

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


# ---------------------------------------------------------------------------
# Presentation helpers — used by the body excerpt renderer to make the
# excerpt block easier to scan. Pure functions; no I/O.
# ---------------------------------------------------------------------------


_HEADING_PREFIXES = ("◆", "●", "■", "▶", "▼", "★", "☆", "◇", "▽", "◎", "□")
_LONG_PARAGRAPH_THRESHOLD = 80
_SENTENCE_FINALS = "。！？"


def classify_excerpt_paragraph(paragraph: str) -> str:
    """Return the structural kind of an excerpt paragraph.

    Kinds:

    - ``"heading"`` — opens with a section marker (◆/●/■/▶/▼/★/☆),
      typically the game-summary or topic line at the top of a body
      ("◆ＪＥＲＡセ・リーグ 巨人１―５ヤクルト…").
    - ``"quote"`` — the line is essentially a single long 「…」 direct
      quote: starts with 「, closes with 」 near the end, and the inside
      is substantial (≥30 chars). Used to lift player / manager
      comments into a visual blockquote.
    - ``"para"`` — regular body paragraph (default).
    """
    p = (paragraph or "").strip()
    if not p:
        return "para"
    if p[:1] in _HEADING_PREFIXES:
        return "heading"
    if p.startswith("「"):
        close = p.rfind("」")
        if close >= 0 and (close - 1) >= 30 and close >= len(p) - 10:
            return "quote"
    return "para"


def split_paragraph_sentences(text: str, *, threshold: int = _LONG_PARAGRAPH_THRESHOLD) -> list[str]:
    """Split a long, multi-sentence paragraph into a list of sentences.

    Trigger condition: paragraph length > ``threshold`` AND it contains
    at least two sentence-final characters (「。」/「！」/「？」). Otherwise
    returns ``[text]`` — short / single-sentence paragraphs stay intact.

    Each returned sentence keeps its terminating punctuation. Leading
    / trailing whitespace is stripped.

    Caller controls how to join (e.g. ``<br>`` for intra-paragraph soft
    breaks, ``</p><p>`` for hard paragraph breaks).
    """
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= threshold:
        return [t]
    finals_count = sum(t.count(ch) for ch in _SENTENCE_FINALS)
    if finals_count < 2:
        return [t]
    chunks: list[str] = []
    buf = ""
    for ch in t:
        buf += ch
        if ch in _SENTENCE_FINALS:
            stripped = buf.strip()
            if stripped:
                chunks.append(stripped)
            buf = ""
    tail = buf.strip()
    if tail:
        chunks.append(tail)
    return chunks


__all__ = [
    "extract_article_body_excerpt",
    "classify_excerpt_paragraph",
    "split_paragraph_sentences",
]
