"""Tests for src/source_html_extractor.py — NOMOTOKE-BODY-EXTRACT-001 Phase 0.

Acceptance gate
================

- OG / meta / JSON-LD facts are extracted from offline fixture HTML files.
- ``<article>`` body markup, ``<div class="article-body">`` paragraphs, and
  JSON-LD ``articleBody`` / ``description`` fields are NEVER lifted into
  the result. Sentinel strings in the fixtures (``BODY_PARAGRAPH_*`` /
  ``ARTICLE_BODY_DO_NOT_EXTRACT_*`` / ``JSONLD_DESCRIPTION_DO_NOT_EXTRACT_*``)
  are checked against ``ExtractionResult.to_dict()`` to prove the contract.
- Each surfaced fact carries a ``source`` provenance key.
- ``rss_title`` / ``rss_summary`` keys are not produced or overwritten by
  the extractor; ``primary_og_*`` namespace is enforced.
- ``meta_unavailable`` skip is emitted when no OG / no JSON-LD article
  shape / no canonical link is found.
- The extractor performs no network I/O. ``urllib.request`` /
  ``urllib3`` / ``requests`` / ``http.client`` are all unused — the import
  surface is asserted by reading the module source.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.source_html_extractor import (  # noqa: E402
    EXTRACTION_SOURCE_JSON_LD,
    EXTRACTION_SOURCE_MIXED,
    EXTRACTION_SOURCE_OG_META,
    SKIP_REASON_META_UNAVAILABLE,
    ExtractionResult,
    extract_source_meta,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "source_html"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# Sentinel substrings the extractor must NEVER surface. Each is unique
# inside its respective fixture so a substring search across the result
# JSON is sufficient. Used in the negative assertions below.
_BODY_SENTINELS = (
    "BODY_PARAGRAPH_ONE_DO_NOT_EXTRACT",
    "BODY_PARAGRAPH_TWO_DO_NOT_EXTRACT",
    "BODY_PARAGRAPH_THREE_DO_NOT_EXTRACT",
    "BODY_PARAGRAPH_DO_NOT_EXTRACT",
    "ARTICLE_BODY_DO_NOT_EXTRACT_THIS_TEXT_INTO_PHASE_0_RESULT",
    "ARTICLE_BODY_DO_NOT_EXTRACT — 巨人のドラフト1位",
    "JSONLD_DESCRIPTION_DO_NOT_EXTRACT_EITHER",
    "phase 0 must drop description from json_ld",
)


# ---------------------------------------------------------------------------
# OG / JSON-LD positive extraction (hochi-shape fixture)
# ---------------------------------------------------------------------------
class HochiOgAndJsonLdExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r: ExtractionResult = extract_source_meta(_load("hochi_news_sample.html"))

    def test_extraction_succeeds_and_is_mixed(self):
        self.assertFalse(self.r.is_skipped())
        # OG present + JSON-LD article present → mixed
        self.assertEqual(self.r.extraction_source, EXTRACTION_SOURCE_MIXED)

    def test_primary_og_title_lifted_from_og_tag(self):
        self.assertIn("若林楽人", self.r.primary_og_title)
        self.assertIn("マルチ安打", self.r.primary_og_title)
        self.assertEqual(self.r.facts["title"]["source"], "og:title")

    def test_primary_og_description_carries_raw_text(self):
        self.assertIn("巨人の若林楽人外野手", self.r.primary_og_description)
        self.assertEqual(self.r.facts["description"]["source"], "og:description")
        # raw_og_description must equal the og:description content verbatim
        self.assertEqual(
            self.r.raw_og_description, self.r.primary_og_description
        )

    def test_primary_og_image_present(self):
        self.assertEqual(
            self.r.primary_og_image,
            "https://hochi.news/article-image/wakabayashi.jpg",
        )
        self.assertEqual(self.r.facts["image"]["source"], "og:image")

    def test_primary_published_at_prefers_og_namespace(self):
        # article:published_time is the OG-namespace published timestamp.
        # Phase 0 prefers it over JSON-LD's datePublished.
        self.assertEqual(
            self.r.primary_published_at, "2026-05-06T19:55:00+09:00"
        )
        self.assertEqual(
            self.r.facts["published_at"]["source"],
            "og:article:published_time",
        )

    def test_canonical_url_lifted_from_link_tag(self):
        self.assertEqual(
            self.r.primary_canonical_url,
            "https://hochi.news/articles/20260506-OHT1T51399.html",
        )
        self.assertEqual(
            self.r.facts["canonical_url"]["source"], "link.canonical"
        )

    def test_jsonld_types_seen_includes_news_article(self):
        self.assertIn("NewsArticle", self.r.jsonld_article_types_seen)


# ---------------------------------------------------------------------------
# JSON-LD-only extraction (sanspo-shape fixture: og + json_ld both, but
# datePublished only in JSON-LD because article:published_time is absent)
# ---------------------------------------------------------------------------
class SanspoOgPlusJsonLdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r: ExtractionResult = extract_source_meta(_load("sanspo_sample.html"))

    def test_extraction_succeeds_mixed(self):
        self.assertFalse(self.r.is_skipped())
        self.assertEqual(self.r.extraction_source, EXTRACTION_SOURCE_MIXED)

    def test_primary_og_title_from_og(self):
        self.assertIn("竹丸和幸", self.r.primary_og_title)
        self.assertEqual(self.r.facts["title"]["source"], "og:title")

    def test_primary_published_at_falls_back_to_jsonld(self):
        # sanspo emits no article:published_time; JSON-LD datePublished
        # must fill in.
        self.assertEqual(self.r.primary_published_at, "2026-05-06T17:50+09:00")
        self.assertEqual(
            self.r.facts["published_at"]["source"],
            "json_ld.datePublished",
        )

    def test_primary_og_description_carries_score_and_opponent(self):
        # The body of the sanspo og:description naturally contains
        # 「巨人0－5ヤクルト」 / 「9回戦」 / 「東京D」 — Phase 0 returns it
        # verbatim because the description IS extraction material. The
        # renderer is the layer that decides not to transcribe it whole.
        d = self.r.primary_og_description
        self.assertIn("巨人0－5ヤクルト", d)
        self.assertIn("9回戦", d)
        self.assertIn("東京D", d)


# ---------------------------------------------------------------------------
# meta_unavailable skip
# ---------------------------------------------------------------------------
class MetaUnavailableSkipTests(unittest.TestCase):
    def test_meta_unavailable_when_no_og_no_jsonld_article(self):
        r = extract_source_meta(_load("meta_unavailable_sample.html"))
        self.assertTrue(r.is_skipped())
        self.assertEqual(r.skip_reason, SKIP_REASON_META_UNAVAILABLE)
        # BreadcrumbList is seen but is NOT an article shape
        self.assertIn("BreadcrumbList", r.jsonld_article_types_seen)
        # Generic <meta name="description"> is NOT picked up
        self.assertEqual(r.primary_og_description, "")
        self.assertEqual(r.raw_og_description, "")

    def test_empty_html_returns_skip(self):
        r = extract_source_meta("")
        self.assertTrue(r.is_skipped())
        self.assertEqual(r.skip_reason, SKIP_REASON_META_UNAVAILABLE)

    def test_non_string_input_returns_skip(self):
        r = extract_source_meta(None)  # type: ignore[arg-type]
        self.assertTrue(r.is_skipped())


# ---------------------------------------------------------------------------
# Body-text scrape forbidden — PROOF tests
# ---------------------------------------------------------------------------
class BodyScrapeForbiddenTests(unittest.TestCase):
    """The extractor must not surface any sentinel from <article> /
    <div class="article-body"> / JSON-LD articleBody / JSON-LD description.

    These sentinels live in the hochi + sanspo fixtures and would only
    appear in the result if the extractor read body markup or the wrong
    JSON-LD fields. Catching them here is the structural guard against
    accidental body scraping creep.
    """

    def _result_blob(self, name: str) -> str:
        r = extract_source_meta(_load(name))
        return json.dumps(r.to_dict(), ensure_ascii=False)

    def test_hochi_result_does_not_contain_any_body_sentinel(self):
        blob = self._result_blob("hochi_news_sample.html")
        for sentinel in _BODY_SENTINELS:
            self.assertNotIn(
                sentinel,
                blob,
                f"Phase 0 leak: sentinel {sentinel!r} reached extractor output",
            )

    def test_sanspo_result_does_not_contain_any_body_sentinel(self):
        blob = self._result_blob("sanspo_sample.html")
        for sentinel in _BODY_SENTINELS:
            self.assertNotIn(
                sentinel,
                blob,
                f"Phase 0 leak: sentinel {sentinel!r} reached extractor output",
            )

    def test_jsonld_articlebody_field_is_dropped_even_when_present(self):
        # hochi fixture has an articleBody field with a long sentinel string.
        # Confirm none of it surfaces.
        r = extract_source_meta(_load("hochi_news_sample.html"))
        for k, v in r.facts.items():
            self.assertNotIn("ARTICLE_BODY_DO_NOT_EXTRACT", v.get("value", ""))

    def test_jsonld_description_field_is_dropped_even_when_present(self):
        # sanspo fixture's JSON-LD has a description field. Phase 0 must
        # NOT lift it (description must come from og:description only).
        r = extract_source_meta(_load("sanspo_sample.html"))
        self.assertNotIn(
            "JSONLD_DESCRIPTION_DO_NOT_EXTRACT_EITHER",
            r.primary_og_description,
        )

    def test_no_paragraph_text_in_result(self):
        # No fact value should contain the article's <p> body text from
        # either fixture.
        for name in ("hochi_news_sample.html", "sanspo_sample.html"):
            r = extract_source_meta(_load(name))
            for k, fact in r.facts.items():
                v = fact.get("value", "")
                # <article>/<p> body sentinels are unique enough to detect.
                for sentinel in _BODY_SENTINELS:
                    self.assertNotIn(
                        sentinel,
                        v,
                        f"{name}: fact[{k}] leaked body sentinel {sentinel!r}",
                    )


# ---------------------------------------------------------------------------
# rss_title / rss_summary namespace separation
# ---------------------------------------------------------------------------
class NamespaceSeparationTests(unittest.TestCase):
    """The extractor must not produce ``rss_title`` / ``rss_summary`` keys.

    Locked spec: RSS-feed entry facts (rss_title / rss_summary) and primary-
    source page facts (primary_og_*) live in separate namespaces. The
    extractor only writes to the primary_og_* / primary_published_at /
    primary_canonical_url namespace.
    """

    def test_result_dict_keys_contain_only_primary_namespace(self):
        r = extract_source_meta(_load("hochi_news_sample.html"))
        d = r.to_dict()
        self.assertNotIn("rss_title", d)
        self.assertNotIn("rss_summary", d)
        # Positive: the primary_* namespace is present.
        for key in (
            "primary_og_title",
            "primary_og_description",
            "primary_og_image",
            "primary_published_at",
            "primary_canonical_url",
        ):
            self.assertIn(key, d)


# ---------------------------------------------------------------------------
# Provenance presence
# ---------------------------------------------------------------------------
class FactProvenanceTests(unittest.TestCase):
    def test_every_surfaced_fact_carries_source(self):
        r = extract_source_meta(_load("hochi_news_sample.html"))
        self.assertGreater(len(r.facts), 0)
        for fact_name, fact in r.facts.items():
            self.assertIn("value", fact, f"{fact_name} missing value")
            self.assertIn("source", fact, f"{fact_name} missing source")
            self.assertNotEqual(
                fact["source"], "", f"{fact_name} source is empty"
            )

    def test_known_provenance_strings(self):
        r = extract_source_meta(_load("hochi_news_sample.html"))
        valid_sources = {
            "og:title",
            "og:description",
            "og:image",
            "og:article:published_time",
            "json_ld.headline",
            "json_ld.datePublished",
            "json_ld.image",
            "link.canonical",
        }
        for fact in r.facts.values():
            self.assertIn(
                fact["source"],
                valid_sources,
                f"unexpected source: {fact['source']!r}",
            )


# ---------------------------------------------------------------------------
# Renderer / router are NOT touched in Phase 0 — proof by import surface
# ---------------------------------------------------------------------------
class Phase0NoSideEffectsTests(unittest.TestCase):
    def test_module_does_not_import_network_clients(self):
        src = (ROOT / "src" / "source_html_extractor.py").read_text(
            encoding="utf-8"
        )
        forbidden_imports = [
            "import requests",
            "from requests",
            "import urllib.request",
            "from urllib.request",
            "import urllib3",
            "from urllib3",
            "import http.client",
            "from http.client",
            "import aiohttp",
            "from aiohttp",
            "import httpx",
            "from httpx",
        ]
        for needle in forbidden_imports:
            self.assertNotIn(
                needle,
                src,
                f"Phase 0 must not import network client: {needle!r}",
            )

    def test_module_does_not_import_renderer_or_router(self):
        # Phase 0 is a pure extractor. It must not pull the renderer or
        # router into its module — those wirings happen in Phase 1+ via
        # the CLI / draft pipeline.
        src = (ROOT / "src" / "source_html_extractor.py").read_text(
            encoding="utf-8"
        )
        for needle in (
            "nomotoke_card_renderer",
            "nomotoke_rss_router",
            "rss_fetcher",
            "wp_client",
            "google.cloud",
            "gemini",
            "vertex",
        ):
            self.assertNotIn(
                needle,
                src,
                f"Phase 0 must not depend on {needle!r}",
            )

    def test_module_does_not_read_robots_or_disk(self):
        src = (ROOT / "src" / "source_html_extractor.py").read_text(
            encoding="utf-8"
        )
        # No file I/O, no robots fetch, no os.path traversal.
        # ``open(`` would imply disk read; the extractor should be pure.
        # Allow ``re`` and ``json`` (which are imported standard lib).
        for needle in ("open(", "Path(", "robots.txt"):
            self.assertNotIn(
                needle,
                src,
                f"Phase 0 must not touch disk / robots: {needle!r}",
            )


# ---------------------------------------------------------------------------
# raw og:description is preserved (renderer responsibility to shorten)
# ---------------------------------------------------------------------------
class RawDescriptionPolicyTests(unittest.TestCase):
    def test_raw_og_description_is_full_verbatim(self):
        # Phase 0 hands the renderer the raw og:description so the
        # renderer can decide whether to truncate / summarise. The
        # extractor itself does NOT generate body / lead text from it.
        r = extract_source_meta(_load("sanspo_sample.html"))
        self.assertGreater(len(r.raw_og_description), 50)
        # Verbatim preservation: starts with the same opening as the
        # fixture's og:description.
        self.assertTrue(
            r.raw_og_description.startswith("（セ・リーグ、巨人0－5ヤクルト")
        )

    def test_extractor_does_not_expose_a_body_or_lead_field(self):
        # The result dataclass must not have a "body" / "lead" / "summary"
        # field — those are renderer responsibilities. Phase 0 stops at
        # raw_og_description.
        r = extract_source_meta(_load("hochi_news_sample.html"))
        d = r.to_dict()
        for forbidden in ("body", "lead", "summary", "article_body"):
            self.assertNotIn(
                forbidden,
                d,
                f"Phase 0 must not surface a {forbidden!r} field",
            )


if __name__ == "__main__":
    unittest.main()
