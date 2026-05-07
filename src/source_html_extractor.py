"""NOMOTOKE-BODY-EXTRACT-001 Phase 0 — offline OG / meta / JSON-LD extractor.

Pure-function HTML parsing. **No network, no robots check, no cache, no
fetcher**. Phase 0 ships only the parser so callers (CLI dry-run in Phase 1,
draft mode after user GO in Phase 2) can be wired without re-touching this
module.

Design constraints (NOMOTOKE-BODY-EXTRACT-001 locked spec)
==========================================================

- **Full body scraping is forbidden.** The extractor reads exactly:
    - ``<meta property="og:*">`` / ``<meta name="og:*">`` (case-insensitive)
    - ``<link rel="canonical">``
    - ``<script type="application/ld+json">`` (parsed as JSON, but only the
      whitelisted fields are surfaced)
  It NEVER reads ``<article>...</article>``, ``<div class="article-body">``,
  or any body markup. JSON-LD's ``articleBody`` / ``description`` fields are
  intentionally dropped so a body-text extraction can never sneak in via
  structured-data syntax.
- **og:description verbatim is preserved as raw extraction material**, but
  the extractor itself does NOT generate body / lead text. Re-construction
  (1-2 sentence lead) is a separate concern handled by the renderer; Phase 0
  hands callers the raw description and lets them shorten it under their
  own policy.
- **rss_title / rss_summary are never overwritten.** The extractor returns
  fields under the ``primary_og_*`` / ``primary_published_at`` namespace
  exclusively so router / CLI can keep both axes (RSS feed entry vs primary
  source page) separate.
- **Provenance** is mandatory. Each fact carries a ``source`` key
  identifying where it came from (``og:title`` / ``og:description`` /
  ``og:image`` / ``json_ld.headline`` / ``json_ld.datePublished`` /
  ``json_ld.image`` / ``link.canonical``). This is the audit trail for
  source-boundary enforcement.
- **Skip reasons** are emitted on the extractor result, not as exceptions:
    - ``meta_unavailable`` — no OG / no JSON-LD article-shape / no canonical
- Phase 1 (HTTP layer) will add ``robots_blocked`` / ``fetch_forbidden``;
  those are deliberately out of scope here so the extractor stays a pure
  string→dict function.

Public surface
==============

- ``extract_source_meta(html: str) -> ExtractionResult``
- ``ExtractionResult`` (dataclass with ``to_dict()``)

Both are importable but neither is wired into the renderer / router /
draft CLI in Phase 0. ENABLE_NOMOTOKE_SOURCE_EXTRACTOR remains an opt-in
flag for later phases (default OFF; the extractor itself respects no flag
because it has no side effects).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


EXTRACTION_SOURCE_NONE = ""
EXTRACTION_SOURCE_OG_META = "og_meta"
EXTRACTION_SOURCE_JSON_LD = "json_ld"
EXTRACTION_SOURCE_MIXED = "og_meta+json_ld"

SKIP_REASON_META_UNAVAILABLE = "meta_unavailable"

# JSON-LD types we recognize as "this is the article". Anything else is
# ignored — Person / Organization / BreadcrumbList etc. are not the source.
_JSONLD_ARTICLE_TYPES: frozenset = frozenset(
    {
        "NewsArticle",
        "Article",
        "ReportageNewsArticle",
        "AnalysisNewsArticle",
        "BackgroundNewsArticle",
        "OpinionNewsArticle",
        "ReviewNewsArticle",
        "SportsEvent",  # for game-result pages with structured data
    }
)

# JSON-LD field allowlist. ``articleBody`` and ``description`` are
# intentionally absent — even if a publisher serialises the full article
# text into JSON-LD, Phase 0 must not lift it. Re-add only after a body-
# size cap + per-source policy is in place (Phase 2+).
_JSONLD_TITLE_KEYS: tuple = ("headline", "name")
_JSONLD_PUBLISHED_KEYS: tuple = ("datePublished", "dateCreated")
_JSONLD_IMAGE_KEYS: tuple = ("image",)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------


# Match <meta property="..."> or <meta name="..."> with content="..." in
# either attribute order. Property/name are case-insensitive.
_META_TAG_RE = re.compile(
    r"<meta\b[^>]*?>",
    re.IGNORECASE | re.DOTALL,
)
_META_KV_RE = re.compile(
    r'(?P<key>[a-zA-Z_:\-]+)\s*=\s*"(?P<val>[^"]*)"',
    re.IGNORECASE,
)
_META_KV_SQ_RE = re.compile(
    r"(?P<key>[a-zA-Z_:\-]+)\s*=\s*'(?P<val>[^']*)'",
    re.IGNORECASE,
)

# JSON-LD script blocks. Many publishers emit multiple — we collect all and
# pick the first NewsArticle-shaped object.
_JSONLD_BLOCK_RE = re.compile(
    r'<script\b[^>]*?type\s*=\s*["\']application/ld\+json["\'][^>]*?>'
    r"(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

# canonical URL via <link rel="canonical" href="...">. Either attribute
# order accepted.
_LINK_TAG_RE = re.compile(
    r"<link\b[^>]*?>",
    re.IGNORECASE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FactWithSource:
    """A single extracted fact plus the source it was lifted from."""

    value: str = ""
    source: str = ""

    def is_present(self) -> bool:
        return bool(self.value)

    def to_dict(self) -> Dict[str, str]:
        return {"value": self.value, "source": self.source}


@dataclass
class ExtractionResult:
    """Aggregate of all OG / JSON-LD facts surfaced by the extractor.

    Names use the ``primary_*`` namespace so callers can keep RSS-feed
    facts (``rss_title`` / ``rss_summary``) separate without ambiguity.

    ``raw_og_description`` is the verbatim ``og:description`` content. It
    is the **extraction material**; the renderer is the layer that decides
    whether to truncate / summarise. Phase 0 does NOT generate a lead
    paragraph from it.
    """

    extraction_source: str = EXTRACTION_SOURCE_NONE
    skip_reason: str = ""
    primary_og_title: str = ""
    primary_og_description: str = ""
    primary_og_image: str = ""
    primary_published_at: str = ""
    primary_canonical_url: str = ""
    raw_og_description: str = ""
    facts: Dict[str, Dict[str, str]] = field(default_factory=dict)
    jsonld_article_types_seen: List[str] = field(default_factory=list)

    def is_skipped(self) -> bool:
        return bool(self.skip_reason)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_meta_attrs(meta_tag: str) -> Dict[str, str]:
    """Return all attribute key/value pairs from a single <meta> tag."""
    out: Dict[str, str] = {}
    for m in _META_KV_RE.finditer(meta_tag):
        out[m.group("key").lower()] = m.group("val")
    for m in _META_KV_SQ_RE.finditer(meta_tag):
        # Single-quoted attrs override only when not already double-quoted.
        out.setdefault(m.group("key").lower(), m.group("val"))
    return out


def _collect_og_meta(html: str) -> Dict[str, str]:
    """Return a dict of OG meta fields keyed by their ``og:*`` property name.

    Only ``og:*`` (and the alias ``article:published_time``, which is
    OpenGraph's article-namespace published timestamp) is collected. Other
    meta tags (``description`` / ``keywords`` / Twitter card / etc.) are
    intentionally ignored; Phase 0 stays narrow.
    """
    found: Dict[str, str] = {}
    for tag_match in _META_TAG_RE.finditer(html):
        attrs = _parse_meta_attrs(tag_match.group(0))
        prop_name = (attrs.get("property") or attrs.get("name") or "").lower()
        if not prop_name:
            continue
        if prop_name.startswith("og:") or prop_name == "article:published_time":
            content = attrs.get("content")
            if content and prop_name not in found:
                found[prop_name] = content
    return found


def _collect_canonical_url(html: str) -> str:
    """Return the value of ``<link rel="canonical" href="...">`` or ""."""
    for tag_match in _LINK_TAG_RE.finditer(html):
        attrs = _parse_meta_attrs(tag_match.group(0))
        if (attrs.get("rel") or "").lower() == "canonical":
            href = attrs.get("href") or ""
            if href:
                return href
    return ""


def _flatten_jsonld_objects(parsed: Any) -> List[Dict[str, Any]]:
    """Recursively flatten a JSON-LD payload into a list of dict objects.

    JSON-LD blocks may be a single object, a list of objects, or an
    ``@graph`` envelope; this iterator accepts all three.
    """
    out: List[Dict[str, Any]] = []
    if isinstance(parsed, dict):
        out.append(parsed)
        graph = parsed.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                if isinstance(item, dict):
                    out.append(item)
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                out.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    for sub in graph:
                        if isinstance(sub, dict):
                            out.append(sub)
    return out


def _jsonld_object_is_article(obj: Dict[str, Any]) -> bool:
    """True when ``@type`` matches a known article type (str or list)."""
    raw_type = obj.get("@type")
    if isinstance(raw_type, str):
        return raw_type in _JSONLD_ARTICLE_TYPES
    if isinstance(raw_type, list):
        return any(t in _JSONLD_ARTICLE_TYPES for t in raw_type if isinstance(t, str))
    return False


def _normalize_image(value: Any) -> str:
    """Pull a single image URL out of a JSON-LD image field.

    JSON-LD images can be a string, a dict (``{"@type":"ImageObject","url":"..."}``),
    or a list of either. Phase 0 returns the first non-empty URL.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("url", "contentUrl", "@id"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    if isinstance(value, list):
        for item in value:
            url = _normalize_image(item)
            if url:
                return url
    return ""


def _collect_jsonld(html: str) -> Tuple[Dict[str, str], List[str]]:
    """Return (whitelisted JSON-LD facts, list of @type values seen).

    Whitelisted keys: ``headline`` / ``name`` (title), ``datePublished`` /
    ``dateCreated`` (timestamp), ``image`` (image URL). ``articleBody`` and
    ``description`` are intentionally NOT extracted to keep Phase 0 free
    of body-text exposure.
    """
    facts: Dict[str, str] = {}
    types_seen: List[str] = []

    for block_match in _JSONLD_BLOCK_RE.finditer(html):
        body = block_match.group("body").strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            continue

        for obj in _flatten_jsonld_objects(parsed):
            t = obj.get("@type")
            if isinstance(t, str):
                types_seen.append(t)
            elif isinstance(t, list):
                types_seen.extend(s for s in t if isinstance(s, str))

            if not _jsonld_object_is_article(obj):
                continue

            for key in _JSONLD_TITLE_KEYS:
                v = obj.get(key)
                if isinstance(v, str) and v.strip() and "title" not in facts:
                    facts["title"] = v.strip()
                    break

            for key in _JSONLD_PUBLISHED_KEYS:
                v = obj.get(key)
                if isinstance(v, str) and v.strip() and "published_at" not in facts:
                    facts["published_at"] = v.strip()
                    break

            for key in _JSONLD_IMAGE_KEYS:
                if "image" in facts:
                    break
                img = _normalize_image(obj.get(key))
                if img:
                    facts["image"] = img

    return facts, types_seen


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def extract_source_meta(html: str) -> ExtractionResult:
    """Parse ``html`` and return OG / meta / JSON-LD facts with provenance.

    Pure function. Never reads disk, never opens a socket, never imports
    a HTTP client. Returns ``ExtractionResult`` with ``skip_reason``
    populated when no recognised metadata is present.

    Phase 0 contract:
      - article body / paragraphs / table content are NOT read
      - JSON-LD's ``articleBody`` / ``description`` are NOT extracted
      - ``primary_og_description`` carries the verbatim ``og:description``
        only — it is the renderer's responsibility to shorten it under the
        og:description-no-verbatim-transcription policy
    """
    if not isinstance(html, str) or not html:
        return ExtractionResult(skip_reason=SKIP_REASON_META_UNAVAILABLE)

    og = _collect_og_meta(html)
    canonical = _collect_canonical_url(html)
    jsonld_facts, jsonld_types_seen = _collect_jsonld(html)

    facts: Dict[str, Dict[str, str]] = {}

    title_value = ""
    title_source = ""
    if og.get("og:title"):
        title_value = og["og:title"]
        title_source = "og:title"
    elif jsonld_facts.get("title"):
        title_value = jsonld_facts["title"]
        title_source = "json_ld.headline"
    if title_value:
        facts["title"] = {"value": title_value, "source": title_source}

    description_value = ""
    description_source = ""
    if og.get("og:description"):
        description_value = og["og:description"]
        description_source = "og:description"
    if description_value:
        facts["description"] = {
            "value": description_value,
            "source": description_source,
        }

    image_value = ""
    image_source = ""
    if og.get("og:image"):
        image_value = og["og:image"]
        image_source = "og:image"
    elif jsonld_facts.get("image"):
        image_value = jsonld_facts["image"]
        image_source = "json_ld.image"
    if image_value:
        facts["image"] = {"value": image_value, "source": image_source}

    published_value = ""
    published_source = ""
    # Prefer the OG-namespace article:published_time when present (publisher-
    # asserted), then fall back to JSON-LD datePublished.
    if og.get("article:published_time"):
        published_value = og["article:published_time"]
        published_source = "og:article:published_time"
    elif jsonld_facts.get("published_at"):
        published_value = jsonld_facts["published_at"]
        published_source = "json_ld.datePublished"
    if published_value:
        facts["published_at"] = {
            "value": published_value,
            "source": published_source,
        }

    if canonical:
        facts["canonical_url"] = {"value": canonical, "source": "link.canonical"}

    has_og = any(k for k in og if k.startswith("og:"))
    has_jsonld_article = bool(jsonld_facts)

    if not has_og and not has_jsonld_article and not canonical:
        return ExtractionResult(
            skip_reason=SKIP_REASON_META_UNAVAILABLE,
            jsonld_article_types_seen=jsonld_types_seen,
        )

    if has_og and has_jsonld_article:
        extraction_source = EXTRACTION_SOURCE_MIXED
    elif has_og:
        extraction_source = EXTRACTION_SOURCE_OG_META
    elif has_jsonld_article:
        extraction_source = EXTRACTION_SOURCE_JSON_LD
    else:
        # Only canonical link without OG / JSON-LD article — useful but
        # not enough on its own to consider the extraction successful.
        return ExtractionResult(
            skip_reason=SKIP_REASON_META_UNAVAILABLE,
            primary_canonical_url=canonical,
            jsonld_article_types_seen=jsonld_types_seen,
            facts=facts,
        )

    return ExtractionResult(
        extraction_source=extraction_source,
        skip_reason="",
        primary_og_title=title_value,
        primary_og_description=description_value,
        primary_og_image=image_value,
        primary_published_at=published_value,
        primary_canonical_url=canonical,
        raw_og_description=og.get("og:description") or "",
        facts=facts,
        jsonld_article_types_seen=jsonld_types_seen,
    )


__all__ = [
    "EXTRACTION_SOURCE_NONE",
    "EXTRACTION_SOURCE_OG_META",
    "EXTRACTION_SOURCE_JSON_LD",
    "EXTRACTION_SOURCE_MIXED",
    "SKIP_REASON_META_UNAVAILABLE",
    "ExtractionResult",
    "FactWithSource",
    "extract_source_meta",
]
