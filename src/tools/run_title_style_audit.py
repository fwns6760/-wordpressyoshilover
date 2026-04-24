"""Read-only CLI to audit existing WordPress titles against ticket 086 rules."""

from __future__ import annotations

import argparse
import html
import json
import sys
from typing import Any, Sequence

from src.title_style_validator import (
    TITLE_STYLE_CLICKBAIT,
    TITLE_STYLE_FORBIDDEN_PREFIX,
    TITLE_STYLE_GENERIC,
    TITLE_STYLE_OUT_OF_LENGTH,
    TITLE_STYLE_SPECULATIVE,
    validate_title_style,
)
from src.tools.run_draft_body_editor_lane import (
    VALID_SUBTYPES,
    _infer_subtype,
    _make_wp_client,
)


DEFAULT_MAX_PAGES = 5
DEFAULT_PER_PAGE = 100
DEFAULT_SAMPLE_FAILURES = 10
LIST_FIELDS = ["id", "status", "title", "content", "meta"]
SKIP_REASON_SUBTYPE_UNSUPPORTED = "subtype_unsupported_for_audit"
REASON_CODES = (
    TITLE_STYLE_SPECULATIVE,
    TITLE_STYLE_GENERIC,
    TITLE_STYLE_CLICKBAIT,
    TITLE_STYLE_OUT_OF_LENGTH,
    TITLE_STYLE_FORBIDDEN_PREFIX,
)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"value must be > 0: {value!r}")
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"value must be >= 0: {value!r}")
    return parsed


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_title_style_audit",
        description="Read-only audit for WordPress titles against the ticket 086 style contract.",
    )
    parser.add_argument("--wp-status", choices=("draft", "publish"), default="draft")
    parser.add_argument("--max-pages", type=_positive_int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--per-page", type=_positive_int, default=DEFAULT_PER_PAGE)
    parser.add_argument("--sample-failures", type=_nonnegative_int, default=DEFAULT_SAMPLE_FAILURES)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable output")
    return parser.parse_args(argv)


def _extract_title(post: dict[str, Any]) -> str:
    title = (post or {}).get("title")
    if isinstance(title, dict):
        for key in ("raw", "rendered"):
            value = title.get(key)
            if value:
                return html.unescape(str(value))
    if isinstance(title, str):
        return html.unescape(title)
    return ""


def _resolve_audit_subtype(post: dict[str, Any]) -> str:
    inferred = _infer_subtype(post)
    if inferred in VALID_SUBTYPES:
        return inferred
    return "unknown"


def _percent(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 1)


def _empty_summary(
    *,
    wp_status: str,
    max_pages: int,
    per_page: int,
    sample_failures: int,
) -> dict[str, Any]:
    return {
        "wp_status": wp_status,
        "max_pages": max_pages,
        "per_page": per_page,
        "pages_fetched": 0,
        "total_scanned": 0,
        "audited_count": 0,
        "pass_count": 0,
        "pass_rate_pct": 0.0,
        "fail_count": 0,
        "fail_rate_pct": 0.0,
        "fail_by_reason": {reason: 0 for reason in REASON_CODES},
        "skipped_count": 0,
        "skipped_rate_pct": 0.0,
        "skipped_by_reason": {SKIP_REASON_SUBTYPE_UNSUPPORTED: 0},
        "by_subtype": {},
        "sample_failure_limit": sample_failures,
        "sample_failures": [],
        "write_operations": 0,
    }


def _subtype_bucket(summary: dict[str, Any], subtype: str) -> dict[str, int]:
    return summary["by_subtype"].setdefault(subtype, {"pass": 0, "fail": 0, "skipped": 0, "total": 0})


def _record_skip(summary: dict[str, Any], subtype: str) -> None:
    bucket = _subtype_bucket(summary, subtype)
    bucket["skipped"] += 1
    bucket["total"] += 1
    summary["skipped_count"] += 1
    summary["skipped_by_reason"][SKIP_REASON_SUBTYPE_UNSUPPORTED] += 1


def _record_pass(summary: dict[str, Any], subtype: str) -> None:
    bucket = _subtype_bucket(summary, subtype)
    bucket["pass"] += 1
    bucket["total"] += 1
    summary["audited_count"] += 1
    summary["pass_count"] += 1


def _record_failure(
    summary: dict[str, Any],
    *,
    post_id: Any,
    subtype: str,
    title: str,
    reason_code: str | None,
) -> None:
    bucket = _subtype_bucket(summary, subtype)
    bucket["fail"] += 1
    bucket["total"] += 1
    summary["audited_count"] += 1
    summary["fail_count"] += 1
    if reason_code in summary["fail_by_reason"]:
        summary["fail_by_reason"][reason_code] += 1
    if len(summary["sample_failures"]) < summary["sample_failure_limit"]:
        summary["sample_failures"].append(
            {
                "id": post_id,
                "subtype": subtype,
                "reason_code": reason_code,
                "title": title,
            }
        )


def _finalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    total = summary["total_scanned"]
    summary["pass_rate_pct"] = _percent(summary["pass_count"], total)
    summary["fail_rate_pct"] = _percent(summary["fail_count"], total)
    summary["skipped_rate_pct"] = _percent(summary["skipped_count"], total)
    summary["fail_by_subtype"] = {
        subtype: bucket["fail"]
        for subtype, bucket in sorted(summary["by_subtype"].items())
    }
    return summary


def run_audit(
    wp,
    *,
    wp_status: str = "draft",
    max_pages: int = DEFAULT_MAX_PAGES,
    per_page: int = DEFAULT_PER_PAGE,
    sample_failures: int = DEFAULT_SAMPLE_FAILURES,
) -> dict[str, Any]:
    summary = _empty_summary(
        wp_status=wp_status,
        max_pages=max_pages,
        per_page=per_page,
        sample_failures=sample_failures,
    )

    for page in range(1, max_pages + 1):
        try:
            posts = wp.list_posts(
                status=wp_status,
                per_page=per_page,
                page=page,
                orderby="modified",
                order="desc",
                context="edit",
                fields=LIST_FIELDS,
            )
        except Exception as exc:
            if "rest_post_invalid_page_number" in str(exc):
                summary["pages_fetched"] += 1
                break
            raise

        summary["pages_fetched"] += 1
        if not posts:
            break

        for post in posts:
            summary["total_scanned"] += 1
            subtype = _resolve_audit_subtype(post)
            title = _extract_title(post)
            post_id = (post or {}).get("id")

            if subtype not in VALID_SUBTYPES:
                _record_skip(summary, subtype)
                continue

            result = validate_title_style(title, subtype)
            if result.ok:
                _record_pass(summary, subtype)
                continue

            _record_failure(
                summary,
                post_id=post_id,
                subtype=subtype,
                title=title,
                reason_code=result.reason_code,
            )

    return _finalize_summary(summary)


def render_human_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"total_scanned: {summary['total_scanned']}",
        f"audited: {summary['audited_count']}",
        f"pass: {summary['pass_count']} ({summary['pass_rate_pct']:.1f}%)",
        f"fail: {summary['fail_count']} ({summary['fail_rate_pct']:.1f}%) — by reason_code:",
    ]
    for reason in REASON_CODES:
        lines.append(f"  {reason}: {summary['fail_by_reason'][reason]}")
    if summary["skipped_count"]:
        lines.append(
            f"skipped: {summary['skipped_count']} ({summary['skipped_rate_pct']:.1f}%) — by reason:"
        )
        lines.append(
            f"  {SKIP_REASON_SUBTYPE_UNSUPPORTED}: {summary['skipped_by_reason'][SKIP_REASON_SUBTYPE_UNSUPPORTED]}"
        )
    lines.append("by subtype (pass/fail):")
    for subtype, bucket in sorted(summary["by_subtype"].items()):
        line = f"  {subtype}: {bucket['pass']} / {bucket['fail']}"
        if bucket["skipped"]:
            line += f" (skipped {bucket['skipped']})"
        lines.append(line)
    lines.append(f"sample failures (first {summary['sample_failure_limit']}):")
    if not summary["sample_failures"]:
        lines.append("  none")
    else:
        for sample in summary["sample_failures"]:
            lines.append(
                f"  id={sample['id']} reason={sample['reason_code']} title={sample['title']!r}"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        wp = _make_wp_client()
        summary = run_audit(
            wp,
            wp_status=args.wp_status,
            max_pages=args.max_pages,
            per_page=args.per_page,
            sample_failures=args.sample_failures,
        )
    except Exception as exc:
        error_payload = {
            "error": str(exc),
            "wp_status": args.wp_status,
            "write_operations": 0,
        }
        if args.json:
            print(json.dumps(error_payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"audit_failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_human_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
