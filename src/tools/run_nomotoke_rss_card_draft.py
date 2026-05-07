"""NOMOTOKE-RSS-CARD-001B — separate CLI that turns RSS-derived entries into
WordPress drafts via nomotoke_card_renderer + nomotoke_rss_router.

Usage
-----

    python -m src.tools.run_nomotoke_rss_card_draft \
        [--source live|logging|json] \
        [--template <template_key>[,<template_key>...]] \
        [--limit N] \
        [--mode dry-run|draft] \
        [--out PATH] \
        [--audit-log logs/nomotoke_card_draft_log.jsonl] \
        [--max-per-source 30] \
        [--max-total 400] \
        [--hours 72] \
        [--json-fixtures PATH] \
        [--sources-file PATH]

Default --mode is "dry-run". --mode draft is required to actually create WP
drafts. Dry-run never invokes ``WPClient`` or any network mutation.

Hard rules
==========

- NEVER call Gemini or any LLM API.
- NEVER pass a category NAME to WPClient.create_post — only category_id list.
- NEVER include full ``required_facts`` / ``extracted_facts`` in the WP body
  HTML comment. Those go to ``logs/nomotoke_card_draft_log.jsonl`` only.
- NEVER touch rss_fetcher.py / wp_client.py / manual_intake.py beyond import.
- NEVER auto-publish (status is hard-coded to "draft").
- NEVER emit RSS_ONLY_BLOCKED_TEMPLATES (the router cannot produce them).
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
    elif source == "logging":
        # The logging sample is wrapped through the dry-run helper to avoid
        # re-implementing gcloud invocation. We only consume routed results
        # there, so for draft we re-route synthetic entries from the same query.
        # Rather than duplicate that path here, the draft CLI does not support
        # --source logging in pass 1 — flag a clear NotImplementedError to keep
        # the surface honest.
        raise NotImplementedError(
            "--source logging is reserved for the dry-run observability CLI; "
            "draft CLI accepts --source live or --source json."
        )
    else:
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


def _build_minimal_html_comment(
    *,
    template_key: str,
    source_url_hash: str,
    route_id: str,
) -> str:
    """Return the only HTML comment allowed in the WP body.

    Contains template_key + source_url_hash + route_id ONLY.
    NEVER required_facts / extracted_facts / tier / confidence.
    """
    payload = {
        "template_key": template_key,
        "source_url_hash": source_url_hash,
        "route_id": route_id,
    }
    return f"<!-- nomotoke_card_meta:{json.dumps(payload, ensure_ascii=False)} -->"


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
) -> Dict[str, Any]:
    """Returns a per-entry summary dict (always emitted to stdout JSON)."""
    route_id = uuid.uuid4().hex[:16]
    base_summary: Dict[str, Any] = {
        "route_id": route_id,
        "source_name": source_name,
        "title": (entry.get("title") or "")[:120],
        "source_url": (entry.get("link") or ""),
        "matched": False,
        "template_key": "",
        "skip_reason": "",
        "wp_post_id": None,
        "category_id": None,
        "mode": mode,
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

    # Same-run dedupe (layer 4)
    if is_duplicate_nomotoke_card(
        seen=same_run_dedupe,
        source_url=result.canonical_url or entry.get("link", ""),
        template_key=result.template_key,
        title=base_summary["title"],
    ):
        base_summary["skip_reason"] = "duplicate_same_run"
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

    # Append the minimal HTML comment (template_key + source_url_hash + route_id)
    minimal_comment = _build_minimal_html_comment(
        template_key=result.template_key,
        source_url_hash=source_url_hash,
        route_id=route_id,
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
        choices=("live", "json", "logging"),
        help="entry source (default: live; logging is reserved for dry-run CLI)",
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
    return p


def _default_wp_client_factory() -> Any:
    from src.wp_client import WPClient

    return WPClient()


def main(
    argv: Optional[List[str]] = None,
    *,
    wp_client_factory: Optional[Callable[[], Any]] = None,
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

    same_run_dedupe: set = set()
    summaries: List[Dict[str, Any]] = []
    audit_log_path = Path(args.audit_log)
    processed = 0

    if args.source == "logging":
        logger.error(
            "--source logging is reserved for the dry-run observability CLI; "
            "draft CLI accepts --source live or --source json."
        )
        return 2

    entries_iter = _iter_input_entries(
        source=args.source,
        sources_file=Path(args.sources_file),
        max_per_source=args.max_per_source,
        max_total=args.max_total,
        hours=args.hours,
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
