"""Read-only quality monitor for WordPress drafts.

Scans Draft posts and emits quality-flag records to ``logs/quality_monitor``.
This runner intentionally does **not** modify WordPress, call any LLM, send
email, or change the existing ``run_draft_body_editor_lane`` behaviour. It
reuses that lane's ``_draft_looks_editable`` judgement axis via import so the
two lanes stay semantically aligned.

The ``published`` and ``both`` targets are defined at the CLI/branch level but
are stubbed for now; they emit a summary row flagged ``published_stub`` and
exit 0, leaving the real implementation for a later phase.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from src.tools.run_draft_body_editor_lane import (
    _draft_looks_editable,
    _extract_title,
    _make_wp_client,
    _now_jst,
    _read_recent_touched_post_ids,
)


ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = ROOT / "logs" / "quality_monitor"

DEFAULT_PER_PAGE = 100
DEFAULT_PAGE_LIMIT = 5

EXIT_WP_GET_FAILED = 40

BENIGN_REASONS = frozenset({
    "not_draft",
    "missing_post_id",
    "recently_touched",
    "outside_edit_window",
    "subtype_unresolved",
})

HIGH_SEVERITY_REASONS = frozenset({
    "fact_check_blocked",
    "audit_flagged",
    "missing_primary_source",
})

MID_SEVERITY_REASONS = frozenset({
    "heading_mismatch",
    "contains_embed",
    "title_axis_scope_out",
})


def _severity_for(reason: str) -> str:
    if reason in HIGH_SEVERITY_REASONS:
        return "high"
    if reason in MID_SEVERITY_REASONS:
        return "mid"
    return "low"


def _fetch_drafts_paginated(wp, page_limit: int) -> tuple[list[dict[str, Any]], str, dict[str, int]]:
    """Fetch draft posts with pagination.

    Tries ``status=draft`` first. On any exception, falls back to
    ``status=any`` and filters to drafts. Returns posts, fetch_mode,
    and pagination metadata.
    """
    # Tier 1: status=draft
    posts: list[dict[str, Any]] = []
    pages_fetched = 0
    try:
        for page in range(1, page_limit + 1):
            page_posts = wp.list_posts(
                status="draft",
                per_page=DEFAULT_PER_PAGE,
                orderby="modified",
                order="desc",
                context="edit",
                page=page,
            )
            pages_fetched += 1
            if not page_posts:
                break
            posts.extend(page_posts)
            if len(page_posts) < DEFAULT_PER_PAGE:
                break
        return posts, "draft_list", {"pages": pages_fetched, "total": len(posts)}
    except Exception as e:
        print(f"[quality_monitor] tier1 status=draft fetch failed: {e!r}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        posts = []
        pages_fetched = 0

    # Tier 2: status=any, filter to draft
    try:
        for page in range(1, page_limit + 1):
            page_posts = wp.list_posts(
                status="any",
                per_page=DEFAULT_PER_PAGE,
                orderby="modified",
                order="desc",
                context="edit",
                page=page,
            )
            pages_fetched += 1
            if not page_posts:
                break
            drafts_only = [p for p in page_posts if str((p or {}).get("status") or "").lower() == "draft"]
            posts.extend(drafts_only)
            if len(page_posts) < DEFAULT_PER_PAGE:
                break
        return posts, "status_any_fallback", {"pages": pages_fetched, "total": len(posts)}
    except Exception as e:
        print(f"[quality_monitor] tier2 status=any fetch failed: {e!r}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return [], "fallback_failed", {"pages": 0, "total": 0}


def _evaluate_posts(
    posts: list[dict[str, Any]],
    now: datetime,
    touched_ids: set[int],
) -> list[dict[str, Any]]:
    flagged: list[dict[str, Any]] = []
    for post in posts:
        ok, reason = _draft_looks_editable(post, now, touched_ids)
        if ok:
            continue
        if reason in BENIGN_REASONS:
            continue
        try:
            post_id = int((post or {}).get("id"))
        except (TypeError, ValueError):
            continue
        flagged.append({
            "post_id": post_id,
            "status": str((post or {}).get("status") or ""),
            "title": _extract_title(post),
            "reason": reason,
            "severity": _severity_for(reason),
        })
    return flagged


def _append_raw_log(now: datetime, record: dict[str, Any]) -> None:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    date_str = now.strftime("%Y-%m-%d")
    path = LOG_ROOT / f"{date_str}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _emit_summary(
    *,
    target: str,
    scanned_count: int,
    flagged: list[dict[str, Any]],
    fetch_mode: str,
    stop_reason: str | None = None,
) -> None:
    severity_counter: Counter[str] = Counter(f["severity"] for f in flagged)
    summary: dict[str, Any] = {
        "target": target,
        "scanned_count": scanned_count,
        "flagged_count": len(flagged),
        "severity_counts": {
            "high": severity_counter.get("high", 0),
            "mid": severity_counter.get("mid", 0),
            "low": severity_counter.get("low", 0),
        },
        "fetch_mode": fetch_mode,
    }
    if stop_reason is not None:
        summary["stop_reason"] = stop_reason
    print(json.dumps(summary, ensure_ascii=False))


def _run_draft_scan(now: datetime, target: str, page_limit: int) -> int:
    try:
        wp = _make_wp_client()
    except Exception as e:
        print(f"failed to init WP client: {e}", file=sys.stderr)
        _append_raw_log(now, {
            "event": "quality_scan",
            "ts": now.isoformat(),
            "target": target,
            "scanned_count": 0,
            "flagged_posts": [],
            "pagination": {"pages": 0, "total": 0},
            "fetch_mode": "none",
            "stop_reason": "wp_init_failed",
        })
        _emit_summary(
            target=target,
            scanned_count=0,
            flagged=[],
            fetch_mode="none",
            stop_reason="wp_init_failed",
        )
        return EXIT_WP_GET_FAILED

    posts, fetch_mode, pagination = _fetch_drafts_paginated(wp, page_limit)

    if fetch_mode == "fallback_failed":
        _append_raw_log(now, {
            "event": "quality_scan",
            "ts": now.isoformat(),
            "target": target,
            "scanned_count": 0,
            "flagged_posts": [],
            "pagination": pagination,
            "fetch_mode": fetch_mode,
            "stop_reason": "wp_get_failed",
        })
        _emit_summary(
            target=target,
            scanned_count=0,
            flagged=[],
            fetch_mode=fetch_mode,
            stop_reason="wp_get_failed",
        )
        return EXIT_WP_GET_FAILED

    touched_ids = _read_recent_touched_post_ids(now)
    flagged = _evaluate_posts(posts, now, touched_ids)
    reason_counts = dict(Counter(f["reason"] for f in flagged))

    _append_raw_log(now, {
        "event": "quality_scan",
        "ts": now.isoformat(),
        "target": target,
        "scanned_count": len(posts),
        "flagged_posts": flagged,
        "pagination": pagination,
        "fetch_mode": fetch_mode,
        "reason_counts": reason_counts,
    })

    _emit_summary(
        target=target,
        scanned_count=len(posts),
        flagged=flagged,
        fetch_mode=fetch_mode,
    )
    return 0


def _run_stub(now: datetime, target: str) -> int:
    _append_raw_log(now, {
        "event": "quality_scan",
        "ts": now.isoformat(),
        "target": target,
        "scanned_count": 0,
        "flagged_posts": [],
        "pagination": {"pages": 0, "total": 0},
        "fetch_mode": "stub",
        "stop_reason": "published_stub",
    })
    _emit_summary(
        target=target,
        scanned_count=0,
        flagged=[],
        fetch_mode="stub",
        stop_reason="published_stub",
    )
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only quality monitor for WordPress drafts.",
    )
    parser.add_argument(
        "--target",
        choices=["draft", "published", "both"],
        default="draft",
    )
    parser.add_argument("--now-iso", default="")
    parser.add_argument("--page-limit", type=int, default=DEFAULT_PAGE_LIMIT)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    now = _now_jst(args.now_iso)
    page_limit = max(1, args.page_limit)

    if args.target == "draft":
        return _run_draft_scan(now, args.target, page_limit)
    # published / both: interface is defined, implementation is stub.
    return _run_stub(now, args.target)


if __name__ == "__main__":
    sys.exit(main())
