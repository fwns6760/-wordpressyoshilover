"""NOMOTOKE-RSS-CARD-001B — separate CLI that turns RSS-derived entries into
WordPress drafts via nomotoke_card_renderer + nomotoke_rss_router.

Usage
-----

    python -m src.tools.run_nomotoke_rss_card_draft \
        [--source live|json] \
        [--template <template_key>[,<template_key>...]] \
        [--limit N] \
        [--mode dry-run|draft] \
        [--out PATH] \
        [--audit-log logs/nomotoke_card_draft_log.jsonl] \
        [--max-per-source 30] \
        [--max-total 400] \
        [--json-fixtures PATH] \
        [--sources-file PATH]

Default --mode is "dry-run". --mode draft is required to actually create WP
drafts. Dry-run never invokes ``WPClient`` or any network mutation.

``--source logging`` is **NOT supported** in 001B; it is reserved for the
dry-run observability CLI ``run_nomotoke_rss_card_dry_run`` (NOMOTOKE-RSS-
CARD-001A). Argparse rejects it (exit 2).

Hard rules
==========

- NEVER call Gemini or any LLM API.
- NEVER pass a category NAME to WPClient.create_post — only category_id list.
- NEVER include full ``required_facts`` / ``extracted_facts`` in the WP body
  HTML comment. Those go to ``logs/nomotoke_card_draft_log.jsonl`` only.
  The HTML comment is restricted to: template_key, source_url_hash,
  route_id, source_published_at_iso (ISO 8601 only).
- NEVER touch rss_fetcher.py / wp_client.py / manual_intake.py beyond import.
- NEVER auto-publish (status is hard-coded to "draft").
- NEVER emit RSS_ONLY_BLOCKED_TEMPLATES (the router cannot produce them).

source_published_at handling (001B limitation)
==============================================

WPClient.create_post only accepts the ``_yoshilover_source_url`` meta key.
It does NOT accept a ``source_published_at`` meta key. Therefore:

- The CLI extracts ``source_published_at_iso`` from the RSS entry's
  ``published`` / ``published_parsed`` / ``updated`` / ``updated_parsed``.
- It is recorded in the JSONL audit log (always) and in the WP body HTML
  comment (minimal, ISO only).
- ``--mode draft``: if no source_published_at can be derived, the entry is
  skipped with reason ``source_published_at_missing``. Silent stop is
  forbidden — the skip is always reported in the JSON summary.
- Drafts created by this CLI MAY still be flagged by ``guarded-publish``
  with ``source_time_missing_review`` because the body HTML comment is
  not what guarded-publish reads. A follow-up ticket
  (NOMOTOKE-RSS-CARD-001B-V2) is required to extend WPClient.create_post
  to persist ``_yoshilover_source_published_at`` meta. Until that lands,
  001B drafts are **review-preferred**.

Dimension separation
====================

``template_key`` and ``category_id`` are independent dimensions:

- ``template_key`` — renderer / dedupe / audit dimension. Drives
  select_renderer dispatch and the layer-4 same-run dedupe key.
- ``category_id`` — WP taxonomy dimension only. Only used to populate the
  ``categories=[int]`` field on WPClient.create_post.

The CLI never derives one from the other beyond the explicit
``resolve_category_id_from_template(template_key)`` lookup. Multiple
template_keys can map to the same category_id; that is fine. dedupe is
strictly ``(canonical_url, template_key)``.

Future WPClient extension (NOMOTOKE-RSS-CARD-001B-V2 candidate):

    Add the following meta keys to WPClient.create_post (additive,
    backwards-compatible). Until then, this CLI keeps them in the body
    HTML comment + jsonl audit log only.

        _yoshilover_template_key
        _yoshilover_route_id
        _yoshilover_source_lane
        _yoshilover_source_published_at
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
_VENDOR = str(ROOT / "vendor")
_SRC = str(ROOT / "src")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.nomotoke_rss_router import (  # noqa: E402
    RSS_ONLY_ALLOWED_TEMPLATES,
    RSS_ONLY_BLOCKED_TEMPLATES,
    RouteResult,
    _parse_iso_or_rfc822,
    normalize_canonical_url,
    route_rss_entry_to_nomotoke_card,
)

# Reuse the dry-run CLI's input-loading path so we don't re-implement it.
from src.tools.run_nomotoke_rss_card_dry_run import (  # noqa: E402
    _entry_to_router_input,
    _fetch_feed,
    run_json_fixture_pass,
    run_live_rss_pass,
    run_logging_sample_pass,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


DEFAULT_AUDIT_LOG_PATH = ROOT / "logs" / "nomotoke_card_draft_log.jsonl"
DEFAULT_CATEGORIES_FILE = ROOT / "config" / "categories.json"
DEFAULT_FALLBACK_CATEGORY_NAME = "コラム"

CALLER_NAME = "nomotoke_card_draft_cli"
SOURCE_LANE_NAME = "nomotoke_card"

# NOMOTOKE-BODY-EXTRACT-001 Phase 1A: opt-in source extractor flag.
# Default OFF. Only consulted in --mode dry-run; --mode draft never wires
# the fetcher (per locked spec — draft mode joins after Phase 2 user GO).
ENABLE_SOURCE_EXTRACTOR_ENV = "ENABLE_NOMOTOKE_SOURCE_EXTRACTOR"

# Map nomotoke renderer category names (may not be WP categories) to
# closest-matching WP categories defined in config/categories.json.
# Final fallback is DEFAULT_FALLBACK_CATEGORY_NAME ("コラム").
_NOMOTOKE_TO_WP_CATEGORY_FALLBACK: Dict[str, str] = {
    "試合速報": "試合速報",       # exact
    "公示": "球団情報",
    "中継": "コラム",
    "動画": "コラム",
    "個人成績": "選手情報",
    "監督談話": "首脳陣",
    "選手コメント": "選手情報",
    "ニュース": "コラム",
}


# ---------------------------------------------------------------------------
# Category id resolver
# ---------------------------------------------------------------------------


def _load_categories_map(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except Exception:
            continue
    return out


def resolve_category_id_from_template(
    template_key: str,
    *,
    categories_map: Dict[str, int],
) -> Tuple[Optional[int], str]:
    """Return (category_id, resolved_name).

    Order:
      1. nomotoke_category_for_template (from renderer's _TEMPLATE_CATEGORY)
      2. _NOMOTOKE_TO_WP_CATEGORY_FALLBACK[nomotoke_category]
      3. DEFAULT_FALLBACK_CATEGORY_NAME ("コラム")

    Returns (None, "") when no resolution succeeded — caller must skip with
    skip_reason="category_id_unresolved".
    """
    # Lazy import so renderer module's flag-gated select_renderer doesn't fire
    # at module load time of this CLI (CLI does not require the renderer flag
    # to be ON unless we're actually rendering).
    from src.nomotoke_card_renderer import _TEMPLATE_CATEGORY

    nomotoke_cat = _TEMPLATE_CATEGORY.get(template_key, "")
    if nomotoke_cat and nomotoke_cat in categories_map:
        return categories_map[nomotoke_cat], nomotoke_cat
    fallback_name = _NOMOTOKE_TO_WP_CATEGORY_FALLBACK.get(nomotoke_cat, "")
    if fallback_name and fallback_name in categories_map:
        return categories_map[fallback_name], fallback_name
    if DEFAULT_FALLBACK_CATEGORY_NAME in categories_map:
        return (
            categories_map[DEFAULT_FALLBACK_CATEGORY_NAME],
            DEFAULT_FALLBACK_CATEGORY_NAME,
        )
    return None, ""


# ---------------------------------------------------------------------------
# Entry input loading (delegated to dry-run CLI helpers)
# ---------------------------------------------------------------------------


def _iter_input_entries(
    *,
    source: str,
    sources_file: Path,
    max_per_source: int,
    max_total: int,
    hours: int,
    json_fixtures_dir: Path,
) -> Iterable[Tuple[str, Dict[str, str]]]:
    """Yield (source_name, entry_dict) tuples from the chosen source.

    entry_dict has keys: title, summary, link, published.
    """
    if source == "live":
        sources_data: List[Dict[str, Any]] = json.loads(
            sources_file.read_text(encoding="utf-8")
        )
        seen = 0
        for src in sources_data:
            if seen >= max_total:
                break
            source_name = (src.get("name") or "").strip()
            url = (src.get("url") or "").strip()
            if not url:
                continue
            feed, err = _fetch_feed(url)
            if feed is None:
                continue
            entries = list(feed.entries or [])[:max_per_source]
            if seen + len(entries) > max_total:
                entries = entries[: max_total - seen]
            for raw in entries:
                seen += 1
                yield source_name, _entry_to_router_input(raw)
    elif source == "json":
        if not json_fixtures_dir.exists():
            return
        for f in sorted(json_fixtures_dir.glob("*.json")):
            try:
                obj = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            yield (
                (obj.get("source_name") or "").strip(),
                {
                    "title": (obj.get("title") or "").strip(),
                    "summary": (obj.get("summary") or "").strip(),
                    "link": (obj.get("link") or "").strip(),
                    "published": (obj.get("published") or "").strip(),
                },
            )
    else:
        # 'logging' is intentionally rejected by argparse; reaching here means
        # a programmer passed an unknown source.
        raise ValueError(f"unknown --source: {source!r}")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _write_audit_log(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# HTML comment minimal — meta_policy: NEVER include required_facts full text.
# ---------------------------------------------------------------------------


def _to_iso_basic(iso_extended: str) -> str:
    """Convert ISO 8601 extended form (``2026-05-06T09:30:00Z``) to basic
    form (``20260506T093000Z``). The basic form is still valid ISO 8601
    but avoids the ``-`` characters that the score-consistency tokenizer
    interprets as separators between two integers, which would create a
    phantom score pair and conflict with real scores in the article body.

    Empty / unrecognized inputs pass through unchanged.
    """
    s = (iso_extended or "").strip()
    if not s:
        return ""
    if "-" not in s and ":" not in s:
        return s
    return s.replace("-", "").replace(":", "")


def _build_minimal_html_comment(
    *,
    template_key: str,
    source_url_hash: str,
    route_id: str,
    source_published_at_iso: str = "",
) -> str:
    """Return the only HTML comment allowed in the WP body.

    Contains template_key + source_url_hash + route_id + source_published_at_iso
    ONLY. NEVER required_facts / extracted_facts / tier / confidence.

    The ``source_published_at_iso`` value is serialized in ISO 8601 basic
    form (``20260506T093000Z``) so the comment cannot inject a phantom
    ``\\d{1,2}-\\d{1,2}`` token into the body's score-consistency check.
    """
    payload: Dict[str, Any] = {
        "template_key": template_key,
        "source_url_hash": source_url_hash,
        "route_id": route_id,
    }
    if source_published_at_iso:
        payload["source_published_at_iso"] = _to_iso_basic(source_published_at_iso)
    return f"<!-- nomotoke_card_meta:{json.dumps(payload, ensure_ascii=False)} -->"


def _resolve_source_published_at_iso(entry: Dict[str, Any]) -> str:
    """Extract a canonical ISO 8601 timestamp (UTC) from an RSS entry.

    Tries (in order): ``published``, ``published_parsed``, ``updated``,
    ``updated_parsed``. Returns "" when no usable timestamp is present.
    """
    # String forms
    for key in ("published", "updated", "source_published_at"):
        raw = (entry.get(key) or "").strip() if isinstance(entry.get(key), str) else ""
        if not raw:
            continue
        d = _parse_iso_or_rfc822(raw)
        if d is not None:
            return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # struct_time forms (feedparser style: published_parsed / updated_parsed)
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st is None:
            continue
        try:
            # struct_time tuple (UTC by feedparser convention)
            dt = datetime(*st[:6], tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------------------
# Dedupe (layer 4: same-run process-scope)
# ---------------------------------------------------------------------------


def is_duplicate_nomotoke_card(
    *,
    seen: set,
    source_url: str,
    template_key: str,
    title: str,
) -> bool:
    """Same-run dedupe (layer 4). layer_1 (WP-side) is handled inside
    WPClient.create_post via find_recent_post_by_title + source_url meta.
    """
    canonical = normalize_canonical_url(source_url) or source_url
    key = (canonical, template_key)
    if key in seen:
        return True
    seen.add(key)
    return False


# ---------------------------------------------------------------------------
# WP draft payload (categories MUST be list[int]; never names)
# ---------------------------------------------------------------------------


def build_wp_draft_payload(
    *,
    title: str,
    content_html: str,
    category_id: int,
    canonical_source_url: str,
) -> Dict[str, Any]:
    """Build the kwargs for WPClient.create_post.

    Strict: ``categories`` is list[int]. Refuses a name string.
    """
    if not isinstance(category_id, int) or category_id <= 0:
        raise ValueError(
            f"category_id must be a positive int (got {category_id!r}); "
            "names are forbidden — see config/categories.json"
        )
    return {
        "title": title,
        "content": content_html,
        "categories": [category_id],
        "status": "draft",
        "source_url": canonical_source_url,
        "caller": CALLER_NAME,
        "source_lane": SOURCE_LANE_NAME,
    }


# ---------------------------------------------------------------------------
# Single-entry processing
# ---------------------------------------------------------------------------


def _is_source_extractor_enabled(args_flag: bool) -> bool:
    """OR-merge the ``--enable-source-extractor`` flag with the env var.

    ``ENABLE_NOMOTOKE_SOURCE_EXTRACTOR=1`` (or true / yes / on) enables the
    extractor without a CLI flag — useful for ops scenarios where the flag
    cannot be threaded but the env can. Default is OFF either way.
    """
    if args_flag:
        return True
    raw = os.environ.get(ENABLE_SOURCE_EXTRACTOR_ENV, "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _attach_source_extractor_facts(
    *,
    base_summary: Dict[str, Any],
    primary_source_url: str,
    pipeline: Optional[Dict[str, Any]],
    logger: logging.Logger,
) -> None:
    """When the Phase 1A pipeline is wired AND the primary source URL is
    a non-X external article URL, fetch the page (via the injected HTTP
    client) and attach OG / JSON-LD facts to ``base_summary``.

    Adds keys (always, when pipeline is non-None and url qualifies):
      - extraction_source ("og_meta" / "json_ld" / "og_meta+json_ld" / "")
      - extraction_skip_reason ("" / robots_blocked / fetch_forbidden /
        meta_unavailable)
      - primary_og_title / primary_og_description / primary_og_image /
        primary_published_at / primary_canonical_url (empty strings when
        unavailable)
      - extracted_facts (dict, fact-name -> {value, source}) — empty when
        the extractor skipped
      - cache_hit (bool)
      - status_code (int) — 0 when no HTTP was made (robots / cache hit)

    rss_title / rss_summary / source_url / related_x_url / data_preview
    keys are NEVER written here — those belong to upstream layers and the
    extractor must not blur the source-boundary by re-routing them.
    """
    if pipeline is None:
        return
    if not primary_source_url or not isinstance(primary_source_url, str):
        return
    # Lazy import so test runs that do not exercise the extractor never
    # have to load fetcher / requests.
    try:
        from src.source_html_fetcher import fetch_source_meta as _fetch
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("source_html_fetcher import failed: %s", exc)
        return

    try:
        result = _fetch(primary_source_url, **pipeline)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "fetch_source_meta unexpected error for %s: %s",
            primary_source_url,
            exc,
        )
        return

    base_summary["extraction_source"] = result.extraction_source or ""
    base_summary["extraction_skip_reason"] = result.skip_reason or ""
    base_summary["cache_hit"] = bool(result.cache_hit)
    base_summary["status_code"] = int(result.status_code or 0)

    extraction = result.extraction
    if extraction is not None and not extraction.is_skipped():
        base_summary["primary_og_title"] = extraction.primary_og_title
        base_summary["primary_og_description"] = extraction.primary_og_description
        base_summary["primary_og_image"] = extraction.primary_og_image
        base_summary["primary_published_at"] = extraction.primary_published_at
        base_summary["primary_canonical_url"] = extraction.primary_canonical_url
        base_summary["extracted_facts"] = dict(extraction.facts)
    else:
        base_summary["primary_og_title"] = ""
        base_summary["primary_og_description"] = ""
        base_summary["primary_og_image"] = ""
        base_summary["primary_published_at"] = ""
        base_summary["primary_canonical_url"] = ""
        base_summary["extracted_facts"] = {}


def _is_x_or_twitter_url(url: str) -> bool:
    if not url:
        return False
    try:
        from urllib.parse import urlparse as _u

        host = _u(url).netloc.lower()
    except Exception:
        return False
    return host in {
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
        "x.com",
        "www.x.com",
        "mobile.x.com",
    }


def _process_one_entry(
    *,
    source_name: str,
    entry: Dict[str, str],
    template_allowlist: Optional[set],
    categories_map: Dict[str, int],
    same_run_dedupe: set,
    mode: str,
    audit_log_path: Path,
    wp_client_factory: Optional[Callable[[], Any]],
    logger: logging.Logger,
    source_extractor_pipeline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Returns a per-entry summary dict (always emitted to stdout JSON)."""
    route_id = uuid.uuid4().hex[:16]
    source_published_at_iso = _resolve_source_published_at_iso(entry)
    base_summary: Dict[str, Any] = {
        "route_id": route_id,
        "source_name": source_name,
        "title": (entry.get("title") or "")[:120],  # raw RSS input (operator audit)
        "rendered_title": "",  # what WP would actually receive (after sanitize)
        "source_url": (entry.get("link") or ""),
        "source_url_hash": "",
        "matched": False,
        # template_key (renderer/dedupe/audit dimension) is independent of
        # category_id (WP taxonomy dimension); never derived from each other.
        "template_key": "",
        "skip_reason": "",
        "wp_post_id": None,
        "category_id": None,
        "category_name": "",
        "mode": mode,
        "source_published_at_iso": source_published_at_iso,
        "source_published_at_present": bool(source_published_at_iso),
    }

    try:
        result: RouteResult = route_rss_entry_to_nomotoke_card(
            entry,
            source_name=source_name,
            source_url=entry.get("link", ""),
        )
    except ValueError as exc:
        base_summary["skip_reason"] = f"defensive_value_error:{exc}"
        return base_summary

    # Filter by allowlist if provided
    if template_allowlist is not None and result.template_key not in template_allowlist:
        if not result.matched:
            base_summary["skip_reason"] = result.skip_reason or "no_template_match"
        else:
            base_summary["skip_reason"] = "template_not_in_allowlist"
            base_summary["template_key"] = result.template_key
        return base_summary

    if not result.matched:
        base_summary["skip_reason"] = result.skip_reason or "unknown_skip"
        base_summary["template_key"] = result.template_key
        return base_summary

    base_summary["matched"] = True
    base_summary["template_key"] = result.template_key

    # NOMOTOKE-BODY-EXTRACT-001 Phase 1A opt-in:
    # When the source extractor pipeline is wired AND we're in dry-run
    # mode, fetch the primary source URL and attach OG / JSON-LD facts to
    # the per-entry summary. The fetch is skipped for X-only URLs (the
    # router has already either skipped them as x_post_not_article_source
    # or promoted an external URL to ``canonical_url``).
    if (
        mode == "dry-run"
        and source_extractor_pipeline is not None
        and result.canonical_url
        and not _is_x_or_twitter_url(result.canonical_url)
    ):
        _attach_source_extractor_facts(
            base_summary=base_summary,
            primary_source_url=result.canonical_url,
            pipeline=source_extractor_pipeline,
            logger=logger,
        )

    # LOCKED: blocked templates must NEVER be emitted
    if result.template_key in RSS_ONLY_BLOCKED_TEMPLATES:
        base_summary["skip_reason"] = "blocked_template_emitted_by_router_BUG"
        return base_summary

    # Resolve category_id (categories MUST be id list, NEVER name)
    category_id, resolved_cat_name = resolve_category_id_from_template(
        result.template_key,
        categories_map=categories_map,
    )
    if category_id is None:
        base_summary["skip_reason"] = "category_id_unresolved"
        return base_summary
    base_summary["category_id"] = category_id
    base_summary["category_name"] = resolved_cat_name

    # Same-run dedupe (layer 4)
    if is_duplicate_nomotoke_card(
        seen=same_run_dedupe,
        source_url=result.canonical_url or entry.get("link", ""),
        template_key=result.template_key,
        title=base_summary["title"],
    ):
        base_summary["skip_reason"] = "duplicate_same_run"
        return base_summary

    # source_published_at gate: --mode draft requires a derivable ISO timestamp.
    # --mode dry-run records absence in the summary but does not skip; the
    # absence flag is what the operator uses to assess RSS supply quality.
    if mode == "draft" and not source_published_at_iso:
        base_summary["skip_reason"] = "source_published_at_missing"
        return base_summary

    # Render via select_renderer
    # NB: select_renderer requires ENABLE_NOMOTOKE_CARD_TEMPLATES flag ON.
    # The flag is gated only on the renderer factory; in --mode draft we set
    # the env var locally to avoid sprinkling toggles on operators.
    os.environ.setdefault("ENABLE_NOMOTOKE_CARD_TEMPLATES", "1")
    from src.nomotoke_card_renderer import select_renderer

    try:
        renderer = select_renderer(result.template_key)
    except (RuntimeError, ValueError) as exc:
        base_summary["skip_reason"] = f"renderer_unavailable:{exc.__class__.__name__}"
        return base_summary

    data_preview = (result.would_render_call or {}).get("data_preview", {}) or {}

    # Phase 2A: forward extractor-derived primary_og_* fields into data_preview
    # so the renderer can use them for lead-text generation + fact-card
    # enrichment WITHOUT mutating rss_title (= entry["title"]) or rss_summary
    # (= entry["summary"]). The extractor fields live in their own keyspace
    # and the renderer reads them as optional inputs (default ""). draft mode
    # in Phase 2A still does NOT wire the fetcher (pipeline is None when
    # mode == "draft") so this is dry-run-only by construction.
    for og_key in (
        "primary_og_title",
        "primary_og_description",
        "primary_og_image",
        "primary_published_at",
        "primary_canonical_url",
    ):
        v = base_summary.get(og_key)
        if v:
            data_preview[og_key] = v

    render_result = renderer(data_preview)
    if not render_result.get("validation_ok"):
        base_summary["skip_reason"] = (
            f"renderer_validation_failed:{render_result.get('skip_reason', '')}"
        )
        return base_summary

    rendered_title = render_result.get("title") or ""
    rendered_html = render_result.get("content_html") or ""
    canonical_url = result.canonical_url or entry.get("link", "")
    source_url_hash = result.dedupe_key.split(":", 1)[-1] if result.dedupe_key else ""
    base_summary["source_url_hash"] = source_url_hash
    base_summary["rendered_title"] = rendered_title

    # Phase 2A: in dry-run, surface a short body preview for operator review
    # so the rendered output can be sanity-checked without grepping the
    # audit log. Truncated to keep the summary JSON small.
    if mode == "dry-run":
        base_summary["rendered_body_preview"] = (rendered_html or "")[:600]

    # Append the minimal HTML comment (template_key + source_url_hash + route_id
    # + source_published_at_iso). NEVER include required_facts / extracted_facts.
    minimal_comment = _build_minimal_html_comment(
        template_key=result.template_key,
        source_url_hash=source_url_hash,
        route_id=route_id,
        source_published_at_iso=source_published_at_iso,
    )
    rendered_html_with_comment = rendered_html + "\n" + minimal_comment

    # Build WP payload (category_id list MUST, never names).
    payload = build_wp_draft_payload(
        title=rendered_title,
        content_html=rendered_html_with_comment,
        category_id=category_id,
        canonical_source_url=canonical_url,
    )

    # Audit log: full required_facts / extracted_facts go HERE only.
    audit_record = {
        "route_id": route_id,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "template_key": result.template_key,
        "source_name": source_name,
        "source_url": canonical_url,
        "source_url_hash": source_url_hash,
        "source_published_at_iso": source_published_at_iso,
        "source_published_at_present": bool(source_published_at_iso),
        "tier": result.tier,
        "confidence": result.confidence,
        "extracted_facts": result.extracted_facts,
        "required_facts_used": data_preview,
        "category_id": category_id,
        "category_name": resolved_cat_name,
        "rendered_title": rendered_title,
        "mode": mode,
    }

    if mode == "dry-run":
        audit_record["wp_post_id"] = None
        audit_record["dry_run"] = True
        _write_audit_log(audit_log_path, audit_record)
        return base_summary

    # mode == "draft": create WP draft
    if wp_client_factory is None:
        base_summary["skip_reason"] = "wp_client_factory_not_provided"
        audit_record["wp_create_skipped_reason"] = base_summary["skip_reason"]
        _write_audit_log(audit_log_path, audit_record)
        return base_summary

    try:
        wp = wp_client_factory()
        post_id = wp.create_post(**payload)
    except Exception as exc:
        base_summary["skip_reason"] = f"wp_create_post_failed:{exc.__class__.__name__}"
        audit_record["wp_create_error"] = str(exc)
        _write_audit_log(audit_log_path, audit_record)
        logger.error("wp_create_post_failed: %s", exc)
        return base_summary

    if isinstance(post_id, dict):
        wp_post_id = post_id.get("id")
    else:
        wp_post_id = post_id
    base_summary["wp_post_id"] = wp_post_id
    audit_record["wp_post_id"] = wp_post_id
    _write_audit_log(audit_log_path, audit_record)
    return base_summary


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.tools.run_nomotoke_rss_card_draft",
        description=(
            "NOMOTOKE-RSS-CARD-001B: convert RSS-derived entries to "
            "nomotoke-style WP drafts. Default --mode dry-run."
        ),
    )
    p.add_argument(
        "--source",
        default="live",
        choices=("live", "json"),
        help=(
            "entry source (default: live). 'logging' is NOT supported here; "
            "it is reserved for run_nomotoke_rss_card_dry_run (001A)."
        ),
    )
    p.add_argument(
        "--template",
        default="",
        help=(
            "comma-separated allowlist of template_keys (subset of "
            "RSS_ONLY_ALLOWED_TEMPLATES). Empty = allow all 4 RSS-only OK."
        ),
    )
    p.add_argument("--limit", type=int, default=0, help="max entries to process; 0 = no limit")
    p.add_argument(
        "--mode",
        default="dry-run",
        choices=("dry-run", "draft"),
        help="default 'dry-run'; 'draft' creates WP drafts",
    )
    p.add_argument("--out", default="", help="JSON summary output path; default = stdout")
    p.add_argument(
        "--audit-log",
        default=str(DEFAULT_AUDIT_LOG_PATH),
        help="JSONL audit log path (full required_facts go here ONLY)",
    )
    p.add_argument("--max-per-source", type=int, default=30)
    p.add_argument("--max-total", type=int, default=400)
    p.add_argument("--hours", type=int, default=72)
    p.add_argument(
        "--json-fixtures",
        default=str(ROOT / "tests" / "fixtures" / "nomotoke_rss_router"),
    )
    p.add_argument(
        "--sources-file",
        default=str(ROOT / "config" / "rss_sources.json"),
    )
    p.add_argument(
        "--categories-file",
        default=str(DEFAULT_CATEGORIES_FILE),
    )
    p.add_argument(
        "--enable-source-extractor",
        action="store_true",
        default=False,
        help=(
            "(Phase 1A opt-in) fetch primary article URL and attach OG / "
            "JSON-LD facts to the dry-run summary. Default OFF. ONLY honored "
            "in --mode dry-run; --mode draft ignores the flag. Also enabled "
            "by env "
            + ENABLE_SOURCE_EXTRACTOR_ENV
            + "=1. Never modifies rss_title / rss_summary / WP body — facts "
            "are surfaced under primary_og_* keys for observability."
        ),
    )
    return p


def _default_wp_client_factory() -> Any:
    from src.wp_client import WPClient

    return WPClient()


def main(
    argv: Optional[List[str]] = None,
    *,
    wp_client_factory: Optional[Callable[[], Any]] = None,
    source_extractor_pipeline: Optional[Dict[str, Any]] = None,
) -> int:
    args = _build_arg_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("nomotoke_card_draft")

    template_allowlist: Optional[set]
    if args.template.strip():
        template_allowlist = {
            t.strip() for t in args.template.split(",") if t.strip()
        }
        # Reject blocked templates explicitly.
        for tk in template_allowlist:
            if tk in RSS_ONLY_BLOCKED_TEMPLATES:
                logger.error(
                    "blocked template specified in --template: %s; "
                    "router will never emit it. Refusing to run.",
                    tk,
                )
                return 2
    else:
        template_allowlist = set(RSS_ONLY_ALLOWED_TEMPLATES)

    categories_map = _load_categories_map(Path(args.categories_file))

    if args.mode == "draft" and wp_client_factory is None:
        wp_client_factory = _default_wp_client_factory

    # Phase 1A: build the source-extractor pipeline only when the flag is
    # set AND the mode is dry-run. ``--mode draft`` ignores the flag — the
    # locked spec requires user GO before draft mode wires the fetcher.
    extractor_enabled = _is_source_extractor_enabled(args.enable_source_extractor)
    if (
        extractor_enabled
        and args.mode == "dry-run"
        and source_extractor_pipeline is None
    ):
        try:
            from src.source_html_fetcher import build_default_pipeline

            source_extractor_pipeline = build_default_pipeline()
            logger.info(
                "source extractor pipeline armed (dry-run, default DI)"
            )
        except Exception as exc:
            logger.warning(
                "failed to construct source extractor pipeline: %s; "
                "continuing without it",
                exc,
            )
            source_extractor_pipeline = None
    elif extractor_enabled and args.mode == "draft":
        logger.warning(
            "%s requested in --mode draft; ignored — Phase 2 user GO is "
            "required before draft mode wires the fetcher.",
            ENABLE_SOURCE_EXTRACTOR_ENV,
        )
        source_extractor_pipeline = None
    elif args.mode != "dry-run":
        source_extractor_pipeline = None

    same_run_dedupe: set = set()
    summaries: List[Dict[str, Any]] = []
    audit_log_path = Path(args.audit_log)
    processed = 0

    # argparse rejects --source logging before reaching here; defensive guard:
    if args.source not in ("live", "json"):
        logger.error("unsupported --source: %s", args.source)
        return 2

    entries_iter = _iter_input_entries(
        source=args.source,
        sources_file=Path(args.sources_file),
        max_per_source=args.max_per_source,
        max_total=args.max_total,
        hours=getattr(args, "hours", 0),
        json_fixtures_dir=Path(args.json_fixtures),
    )

    for source_name, entry in entries_iter:
        if args.limit and processed >= args.limit:
            break
        processed += 1
        summary = _process_one_entry(
            source_name=source_name,
            entry=entry,
            template_allowlist=template_allowlist,
            categories_map=categories_map,
            same_run_dedupe=same_run_dedupe,
            mode=args.mode,
            audit_log_path=audit_log_path,
            wp_client_factory=wp_client_factory if args.mode == "draft" else None,
            logger=logger,
            source_extractor_pipeline=source_extractor_pipeline,
        )
        summaries.append(summary)

    output = {
        "schema_version": "nomotoke_rss_card_draft.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": args.mode,
        "source": args.source,
        "template_allowlist": sorted(template_allowlist or []),
        "processed": processed,
        "summary_counts": _summarize_counts(summaries),
        "results": summaries,
    }
    out_text = json.dumps(output, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"wrote: {args.out}")
    else:
        print(out_text)
    return 0


def _summarize_counts(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "matched": 0,
        "skipped": 0,
        "drafts_created": 0,
        "by_template": {},
        "by_skip_reason": {},
    }
    for s in summaries:
        if s.get("matched"):
            out["matched"] += 1
            tk = s.get("template_key", "")
            if tk:
                out["by_template"][tk] = out["by_template"].get(tk, 0) + 1
        if s.get("skip_reason"):
            out["skipped"] += 1
            r = s["skip_reason"]
            out["by_skip_reason"][r] = out["by_skip_reason"].get(r, 0) + 1
        if s.get("wp_post_id"):
            out["drafts_created"] += 1
    return out


if __name__ == "__main__":
    sys.exit(main())
