"""NOMOTOKE-VIDEO-SOURCE-001 — pure YouTube channel-RSS atom parser.

Phase scope (this module)
=========================

- Parse a YouTube channel atom feed (e.g.
  ``https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}``)
  into a list of ``YouTubeFeedEntry`` records.
- NO network. The string parser is pure; the caller (CLI / fetcher
  module) supplies the raw XML. Production rss_fetcher.py is NOT
  auto-connected — that requires a separate explicit wiring at user GO.
- Extract source-only facts that the existing ``video_v1`` renderer
  expects: video URL, title (raw), published_at, channel name,
  thumbnail URL, description.

What this module deliberately does NOT do
=========================================

- HTTP fetch — fetch is the caller's responsibility (Phase 1A's
  ``source_html_fetcher`` style). Adding a default fetcher here would
  conflict with the "禁止: 本番 rss_fetcher.py 自動接続" lock.
- AI / Gemini summarisation — extraction is regex / XML traversal only.
- Full body / page scraping — only the atom feed is parsed.
- Production RSS source registration — the ``rss_sources.json`` file is
  unchanged. Dry-run ingestion happens via fixture files passed
  explicitly through a CLI flag.
- Direct WP write — no draft creation here.

Skip taxonomy emitted by ``parse_youtube_atom``
================================================

- ``invalid_xml`` — input is empty / non-string / not valid atom.
- ``no_entries`` — feed parsed but contains zero ``<entry>``.
- ``no_video_id`` — entry has no ``yt:videoId`` (cannot construct video URL).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


YOUTUBE_WATCH_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"

# YouTube channel-feed atom XML uses these namespaces:
#   default — http://www.w3.org/2005/Atom
#   yt:     — http://www.youtube.com/xml/schemas/2015
#   media:  — http://search.yahoo.com/mrss/
# We do not use a full XML parser to avoid pulling in lxml; instead we use
# regex on a per-element basis, which is sufficient for this strict feed
# shape.

SKIP_REASON_INVALID_XML = "invalid_xml"
SKIP_REASON_NO_ENTRIES = "no_entries"
SKIP_REASON_NO_VIDEO_ID = "no_video_id"


# ---------------------------------------------------------------------------
# Regex (per-entry sub-extractors)
# ---------------------------------------------------------------------------


_FEED_TITLE_RE = re.compile(
    r"<feed\b[^>]*>.*?<title[^>]*>(?P<title>[^<]+)</title>",
    re.DOTALL | re.IGNORECASE,
)
_FEED_AUTHOR_RE = re.compile(
    r"<feed\b[^>]*>.*?<author>\s*<name>(?P<name>[^<]+)</name>",
    re.DOTALL | re.IGNORECASE,
)
_FEED_CHANNEL_ID_RE = re.compile(
    r"<yt:channelId>(?P<channel_id>[A-Za-z0-9_-]+)</yt:channelId>",
    re.IGNORECASE,
)
_ENTRY_BLOCK_RE = re.compile(
    r"<entry\b[^>]*>(?P<body>.*?)</entry>",
    re.DOTALL | re.IGNORECASE,
)
_ENTRY_VIDEO_ID_RE = re.compile(
    r"<yt:videoId>(?P<video_id>[A-Za-z0-9_-]+)</yt:videoId>",
    re.IGNORECASE,
)
_ENTRY_TITLE_RE = re.compile(
    r"<title[^>]*>(?P<title>[^<]+)</title>",
    re.IGNORECASE | re.DOTALL,
)
_ENTRY_PUBLISHED_RE = re.compile(
    r"<published[^>]*>(?P<published>[^<]+)</published>",
    re.IGNORECASE,
)
_ENTRY_AUTHOR_RE = re.compile(
    r"<author>\s*<name>(?P<name>[^<]+)</name>",
    re.IGNORECASE | re.DOTALL,
)
_ENTRY_LINK_RE = re.compile(
    r"<link\b[^>]*href=\"(?P<href>[^\"]+)\"",
    re.IGNORECASE,
)
_ENTRY_THUMBNAIL_RE = re.compile(
    r"<media:thumbnail\b[^>]*url=\"(?P<url>[^\"]+)\"",
    re.IGNORECASE,
)
_ENTRY_DESCRIPTION_RE = re.compile(
    r"<media:description[^>]*>(?P<text>[^<]+)</media:description>",
    re.IGNORECASE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class YouTubeFeedEntry:
    """One <entry> from a YouTube channel atom feed.

    Field provenance:
      - video_id        ← <yt:videoId>
      - video_url       ← https://www.youtube.com/watch?v={video_id}
      - title           ← <title> (raw, no sanitisation)
      - published_at    ← <published> (ISO 8601)
      - channel_name    ← <author><name> (entry-level), falls back to feed
      - channel_id      ← <yt:channelId> (feed-level)
      - thumbnail_url   ← <media:thumbnail url="...">
      - description     ← <media:description>
    """

    video_id: str = ""
    video_url: str = ""
    title: str = ""
    published_at: str = ""
    channel_name: str = ""
    channel_id: str = ""
    thumbnail_url: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class YouTubeFeedParseResult:
    feed_title: str = ""
    feed_channel_id: str = ""
    feed_channel_name: str = ""
    entries: List[YouTubeFeedEntry] = field(default_factory=list)
    skip_reason: str = ""

    def is_skipped(self) -> bool:
        return bool(self.skip_reason)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feed_title": self.feed_title,
            "feed_channel_id": self.feed_channel_id,
            "feed_channel_name": self.feed_channel_name,
            "entries": [e.to_dict() for e in self.entries],
            "skip_reason": self.skip_reason,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _xml_unescape(s: str) -> str:
    """Cheap XML entity decode for &amp; / &lt; / &gt; / &quot; / &#xx; etc.

    We only see the standard 5 entities + numeric refs in YouTube atom
    feeds; using ``html.unescape`` which handles the long tail.
    """
    if not s:
        return s
    import html as _html

    return _html.unescape(s)


def _first_match_group(rx: re.Pattern, text: str, group: str) -> str:
    m = rx.search(text or "")
    if not m:
        return ""
    try:
        return _xml_unescape(m.group(group)).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------


def parse_youtube_atom(xml: str) -> YouTubeFeedParseResult:
    """Parse a YouTube channel atom feed string into a list of entries.

    Pure function. Empty / non-string input → ``invalid_xml`` skip.
    Feed with zero entries → ``no_entries`` skip. Per-entry parser drops
    entries that lack ``<yt:videoId>`` (no usable video URL); if NONE of
    the entries have a video_id the whole result skips with
    ``no_video_id``.
    """
    if not isinstance(xml, str) or not xml:
        return YouTubeFeedParseResult(skip_reason=SKIP_REASON_INVALID_XML)
    if "<feed" not in xml.lower():
        return YouTubeFeedParseResult(skip_reason=SKIP_REASON_INVALID_XML)

    feed_title = _first_match_group(_FEED_TITLE_RE, xml, "title")
    feed_channel_id = _first_match_group(_FEED_CHANNEL_ID_RE, xml, "channel_id")
    feed_channel_name = _first_match_group(_FEED_AUTHOR_RE, xml, "name")

    blocks = _ENTRY_BLOCK_RE.findall(xml)
    if not blocks:
        return YouTubeFeedParseResult(
            feed_title=feed_title,
            feed_channel_id=feed_channel_id,
            feed_channel_name=feed_channel_name,
            skip_reason=SKIP_REASON_NO_ENTRIES,
        )

    entries: List[YouTubeFeedEntry] = []
    for body in blocks:
        video_id = _first_match_group(_ENTRY_VIDEO_ID_RE, body, "video_id")
        if not video_id:
            continue
        title = _first_match_group(_ENTRY_TITLE_RE, body, "title")
        published = _first_match_group(_ENTRY_PUBLISHED_RE, body, "published")
        author = _first_match_group(_ENTRY_AUTHOR_RE, body, "name")
        thumbnail = _first_match_group(_ENTRY_THUMBNAIL_RE, body, "url")
        description = _first_match_group(_ENTRY_DESCRIPTION_RE, body, "text")
        # entry/link is optional — yt:videoId already gives us enough to
        # build the canonical watch URL.
        entries.append(
            YouTubeFeedEntry(
                video_id=video_id,
                video_url=YOUTUBE_WATCH_URL_TEMPLATE.format(video_id=video_id),
                title=title,
                published_at=published,
                channel_name=author or feed_channel_name,
                channel_id=feed_channel_id,
                thumbnail_url=thumbnail,
                description=description,
            )
        )

    if not entries:
        return YouTubeFeedParseResult(
            feed_title=feed_title,
            feed_channel_id=feed_channel_id,
            feed_channel_name=feed_channel_name,
            skip_reason=SKIP_REASON_NO_VIDEO_ID,
        )

    return YouTubeFeedParseResult(
        feed_title=feed_title,
        feed_channel_id=feed_channel_id,
        feed_channel_name=feed_channel_name,
        entries=entries,
    )


# ---------------------------------------------------------------------------
# Entry → video_v1 data_preview projection
# ---------------------------------------------------------------------------


# Player-name extractor (kanji surname OR katakana foreign name, NOT
# hiragana — same rule as Phase 2C+ player_quote guard so phrases /
# particles do not slip in as names).
_VIDEO_PLAYER_NAME_RE = re.compile(
    r"(?P<name>(?:[一-龥々]{2,5}|[ァ-ヴー]{3,12}))"
)

# Stoplist of generic baseball nouns that match the kanji regex but are
# NOT player names. Matching one of these advances the search to the
# next token instead of returning a false positive (e.g. ``球団``,
# ``選手``, ``ハイライト`` would otherwise become player_name when the
# title has no actual player name).
_VIDEO_PLAYER_NAME_STOPLIST: frozenset = frozenset(
    {
        "巨人", "ジャイアンツ", "読売",
        "球団", "選手", "投手", "監督", "コーチ", "捕手",
        "内野手", "外野手", "ベンチ",
        "球場", "ドーム", "スタジアム", "ジータス",
        "試合", "結果", "速報", "中継", "公式",
        "ハイライト", "シーズン", "ファーム", "二軍", "一軍",
        "野球", "プロ",
    }
)
# Play-summary keyword set (literal substring scan, like
# _SHORT_NEWS_OUTCOME_KEYWORDS — promotes auto-routability).
_VIDEO_PLAY_SUMMARY_KEYWORDS: tuple = (
    "ホームラン",
    "本塁打",
    "サヨナラ",
    "完封",
    "完投",
    "三振",
    "好投",
    "好捕",
    "ファインプレー",
    "盗塁",
    "ハイライト",
    "リリーフ",
    "クローザー",
    "決勝打",
    "勝利打点",
    "適時打",
)


def extract_video_card_facts(
    entry: YouTubeFeedEntry,
    *,
    team_name: str = "巨人",
) -> Dict[str, str]:
    """Project a YouTube atom entry into the data_preview shape that
    ``render_video_card`` consumes.

    Required fields per the renderer (``missing_video_fields`` skip
    fires when any are blank):
      - ``video_url``
      - ``team_name``
      - ``player_name``
      - ``play_summary``

    Optional:
      - ``description`` (renderer truncates to 120 chars at first 「。」)
      - ``date_label`` (display)
      - ``embed_html`` (Phase 1: empty — the renderer falls back to a
        plain anchor link to the video URL, which keeps it source-only.
        embed iframe wiring is a Phase 2 concern that needs CSP review.)

    Returns the partial dict; caller checks for required-field
    completeness or hands directly to the renderer (which will skip with
    ``missing_video_fields`` when incomplete).
    """
    if not isinstance(entry, YouTubeFeedEntry):
        return {}

    title = (entry.title or "").strip()

    # Player-name: scan title for a kanji or katakana token; reject
    # results that look like decoration brackets, team aliases, or
    # generic baseball nouns ("球団", "選手", "ハイライト", etc.).
    # The check is a SUBSTRING match so candidates like "試合運営" /
    # "球団からの" are rejected on contained keywords.
    player_name = ""
    for m in _VIDEO_PLAYER_NAME_RE.finditer(title):
        candidate = m.group("name").strip()
        if candidate.startswith("【") or candidate.endswith("】"):
            continue
        contains_stop = any(
            stop in candidate for stop in _VIDEO_PLAYER_NAME_STOPLIST
        )
        if contains_stop:
            continue
        player_name = candidate
        break

    play_summary = ""
    for kw in _VIDEO_PLAY_SUMMARY_KEYWORDS:
        if kw in title:
            play_summary = kw
            break

    # Date label: take the YYYY-MM-DD prefix of published_at when present.
    date_label = ""
    if entry.published_at:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", entry.published_at)
        if m:
            date_label = (
                f"{int(m.group(1))}年{int(m.group(2))}月{int(m.group(3))}日"
            )

    return {
        "video_url": entry.video_url,
        "team_name": team_name,
        "player_name": player_name,
        "play_summary": play_summary,
        "description": (entry.description or "")[:280],
        "date_label": date_label,
        # Source-side metadata for downstream auditing.
        "source_url": entry.video_url,
        "source_name": entry.channel_name,
        "thumbnail_url": entry.thumbnail_url,
    }


__all__ = [
    "YOUTUBE_WATCH_URL_TEMPLATE",
    "SKIP_REASON_INVALID_XML",
    "SKIP_REASON_NO_ENTRIES",
    "SKIP_REASON_NO_VIDEO_ID",
    "YouTubeFeedEntry",
    "YouTubeFeedParseResult",
    "parse_youtube_atom",
    "extract_video_card_facts",
]
