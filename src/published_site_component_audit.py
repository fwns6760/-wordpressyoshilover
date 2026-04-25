from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from src import guarded_publish_evaluator as evaluator
from src.pre_publish_fact_check import extractor


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_LIMIT = 50
HUMAN_PREVIEW_LIMIT = 10

SUMMARY_TYPE_ORDER = (
    "heading_sentence_as_h3",
    "dev_log_contamination",
    "weird_heading_label",
    "site_component_middle",
    "site_component_tail",
)
DETECTED_TYPE_ORDER = (
    "site_component_mixed_into_body_middle",
    "site_component_mixed_into_body_tail",
    "heading_sentence_as_h3",
    "dev_log_contamination",
    "weird_heading_label",
)


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_wp_datetime(value: Any, *, fallback_now: datetime | None = None) -> datetime:
    if not value:
        return _now_jst(fallback_now)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _published_at(raw_post: dict[str, Any], *, now: datetime | None = None) -> datetime:
    record = extractor.extract_post_record(raw_post)
    return _parse_wp_datetime(
        raw_post.get("date")
        or raw_post.get("date_gmt")
        or record.get("created_at")
        or raw_post.get("modified")
        or record.get("modified_at"),
        fallback_now=now,
    )


def _is_published_today(raw_post: dict[str, Any], *, now: datetime) -> bool:
    return _published_at(raw_post, now=now).date() == _now_jst(now).date()


def _sort_detected_types(values: Sequence[str]) -> list[str]:
    order = {name: index for index, name in enumerate(DETECTED_TYPE_ORDER)}
    return sorted(dict.fromkeys(values), key=lambda value: order.get(value, len(order)))


def _site_component_hits(body_text: str) -> list[dict[str, Any]]:
    if not body_text:
        return []

    total_chars = len(body_text)
    if total_chars <= 0:
        return []

    keyed_hits: dict[tuple[int, int, str], dict[str, Any]] = {}
    for label, pattern in evaluator.SITE_COMPONENT_PATTERNS:
        for match in pattern.finditer(body_text):
            matched_text = match.group(0)
            key = (match.start(), match.end(), matched_text)
            hit = keyed_hits.setdefault(
                key,
                {
                    "matched_text": matched_text,
                    "pattern_names": [],
                    "position_pct": round((match.start() / total_chars) * 100, 1),
                },
            )
            hit["pattern_names"].append(label)

    hits: list[dict[str, Any]] = []
    for (_, _, _), payload in sorted(keyed_hits.items(), key=lambda item: item[0][0]):
        position_pct = float(payload["position_pct"])
        verdict = "middle/Red" if position_pct < 70.0 else "tail/Yellow"
        hits.append(
            {
                "matched_text": payload["matched_text"],
                "pattern_names": sorted(dict.fromkeys(payload["pattern_names"])),
                "position_pct": position_pct,
                "verdict": verdict,
            }
        )
    return hits


def _site_component_detected_types(site_hits: Sequence[dict[str, Any]]) -> list[str]:
    detected: list[str] = []
    if any(str(hit.get("verdict") or "").startswith("middle") for hit in site_hits):
        detected.append("site_component_mixed_into_body_middle")
    if any(str(hit.get("verdict") or "").startswith("tail") for hit in site_hits):
        detected.append("site_component_mixed_into_body_tail")
    return detected


def _audit_post(raw_post: dict[str, Any]) -> dict[str, Any] | None:
    record = extractor.extract_post_record(raw_post)
    post_id = int(record["post_id"])
    title = str(record.get("title") or "")
    link = str((raw_post or {}).get("link") or "")
    modified = str(record.get("modified_at") or raw_post.get("modified") or "")
    body_html = str(record.get("body_html") or "")
    body_text = str(record.get("body_text") or "")

    detected_types: list[str] = []
    proposed_diff_preview: dict[str, list[dict[str, Any]]] = {}

    heading_hits = evaluator._heading_sentence_as_h3_hits(body_html)
    if heading_hits:
        from src import guarded_publish_runner as cleanup_runner

        cleaned_html, heading_actions = cleanup_runner._replace_heading_sentence_h3(body_html)
        if heading_actions and cleaned_html != body_html:
            detected_types.append("heading_sentence_as_h3")
            proposed_diff_preview["heading_sentence_as_h3"] = [
                {
                    "before_h3_text": hit["heading"],
                    "would_become": f"<p>{hit['heading']}</p>",
                }
                for hit in heading_hits
            ]

    clear_dev_log_blocks, _ = evaluator._detect_dev_log_blocks(body_html, body_text)
    if clear_dev_log_blocks:
        detected_types.append("dev_log_contamination")
        proposed_diff_preview["dev_log_contamination"] = [
            {
                "block_preview": str(block.get("preview") or ""),
                "block_type": str(block.get("block_type") or ""),
                "line_count": int(block.get("line_count") or 0),
                "categories": list(block.get("categories") or []),
                "would_delete": True,
            }
            for block in clear_dev_log_blocks
        ]

    weird_heading_hits = evaluator._weird_heading_labels(body_html)
    if weird_heading_hits:
        detected_types.append("weird_heading_label")
        proposed_diff_preview["weird_heading_label"] = [
            {
                "heading_text": hit["heading"],
                "would_require_manual_review": True,
            }
            for hit in weird_heading_hits
        ]

    site_hits = _site_component_hits(body_text)
    if site_hits:
        detected_types.extend(_site_component_detected_types(site_hits))
        proposed_diff_preview["site_component_mixed_into_body"] = site_hits

    detected_types = _sort_detected_types(detected_types)
    if not detected_types:
        return None

    return {
        "post_id": post_id,
        "title": title,
        "link": link,
        "modified": modified,
        "detected_types": detected_types,
        "proposed_diff_preview": proposed_diff_preview,
    }


def _empty_summary() -> dict[str, int]:
    return {key: 0 for key in SUMMARY_TYPE_ORDER}


def audit_published_posts(
    raw_posts: Sequence[dict[str, Any]],
    *,
    limit: int = DEFAULT_LIMIT,
    orderby: str = "modified",
    order: str = "desc",
    include_todays_publishes: bool = False,
    now: datetime | None = None,
    fetched_count: int | None = None,
    skipped_today_count: int = 0,
) -> dict[str, Any]:
    now_jst = _now_jst(now)
    scan_limit = max(1, min(int(limit), 100))
    selected_posts: list[dict[str, Any]] = []
    skipped_today = int(skipped_today_count)

    for raw_post in raw_posts:
        if len(selected_posts) >= scan_limit:
            break
        if not include_todays_publishes and _is_published_today(raw_post, now=now_jst):
            skipped_today += 1
            continue
        selected_posts.append(raw_post)

    cleanup_proposals: list[dict[str, Any]] = []
    clean_posts: list[int] = []
    by_type = _empty_summary()

    for raw_post in selected_posts:
        proposal = _audit_post(raw_post)
        if proposal is None:
            clean_posts.append(int((raw_post or {}).get("id") or extractor.extract_post_record(raw_post)["post_id"]))
            continue

        cleanup_proposals.append(proposal)
        unique_types = set(proposal["detected_types"])
        if "heading_sentence_as_h3" in unique_types:
            by_type["heading_sentence_as_h3"] += 1
        if "dev_log_contamination" in unique_types:
            by_type["dev_log_contamination"] += 1
        if "weird_heading_label" in unique_types:
            by_type["weird_heading_label"] += 1
        if "site_component_mixed_into_body_middle" in unique_types:
            by_type["site_component_middle"] += 1
        if "site_component_mixed_into_body_tail" in unique_types:
            by_type["site_component_tail"] += 1

    return {
        "scan_meta": {
            "limit": scan_limit,
            "orderby": orderby,
            "order": order,
            "include_todays_publishes": include_todays_publishes,
            "ts": now_jst.isoformat(),
            "fetched": int(fetched_count if fetched_count is not None else len(raw_posts)),
            "skipped_today": skipped_today,
            "scanned": len(selected_posts),
        },
        "cleanup_proposals": cleanup_proposals,
        "clean_posts": clean_posts,
        "summary": {
            "total": len(selected_posts),
            "with_proposals": len(cleanup_proposals),
            "by_type": by_type,
        },
    }


def scan_wp_published_posts(
    wp_client: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    orderby: str = "modified",
    order: str = "desc",
    include_todays_publishes: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    now_jst = _now_jst(now)
    scan_limit = max(1, min(int(limit), 100))
    collected_posts: list[dict[str, Any]] = []
    fetched_count = 0
    skipped_today = 0
    page = 1

    while len(collected_posts) < scan_limit:
        batch = list(
            wp_client.list_posts(
                status="publish",
                per_page=min(100, scan_limit),
                page=page,
                orderby=orderby,
                order=order,
                context="edit",
            )
            or []
        )
        if not batch:
            break

        fetched_count += len(batch)
        for raw_post in batch:
            if len(collected_posts) >= scan_limit:
                break
            if not include_todays_publishes and _is_published_today(raw_post, now=now_jst):
                skipped_today += 1
                continue
            collected_posts.append(raw_post)

        if len(batch) < min(100, scan_limit):
            break
        page += 1

    return audit_published_posts(
        collected_posts,
        limit=scan_limit,
        orderby=orderby,
        order=order,
        include_todays_publishes=include_todays_publishes,
        now=now_jst,
        fetched_count=fetched_count,
        skipped_today_count=skipped_today,
    )


def render_human_report(report: dict[str, Any]) -> str:
    scan_meta = report["scan_meta"]
    summary = report["summary"]
    by_type = summary["by_type"]
    lines = [
        "Published Site Component Cleanup Audit",
        (
            f"limit={scan_meta['limit']} orderby={scan_meta['orderby']} order={scan_meta['order']} "
            f"scanned={scan_meta['scanned']} fetched={scan_meta['fetched']} "
            f"include_todays_publishes={scan_meta['include_todays_publishes']} "
            f"skipped_today={scan_meta['skipped_today']} ts={scan_meta['ts']}"
        ),
        "",
        "Summary",
        "metric                     count",
        f"{'total':<26} {summary['total']}",
        f"{'with_proposals':<26} {summary['with_proposals']}",
        f"{'clean_posts':<26} {len(report['clean_posts'])}",
        f"{'heading_sentence_as_h3':<26} {by_type['heading_sentence_as_h3']}",
        f"{'dev_log_contamination':<26} {by_type['dev_log_contamination']}",
        f"{'weird_heading_label':<26} {by_type['weird_heading_label']}",
        f"{'site_component_middle':<26} {by_type['site_component_middle']}",
        f"{'site_component_tail':<26} {by_type['site_component_tail']}",
        "",
        f"Cleanup Proposals (top {HUMAN_PREVIEW_LIMIT})",
    ]

    proposals = report["cleanup_proposals"][:HUMAN_PREVIEW_LIMIT]
    if not proposals:
        lines.append("- none")
    else:
        for proposal in proposals:
            lines.append(
                f"- {proposal['post_id']} | {proposal['title']} | {', '.join(proposal['detected_types'])}"
            )

    return "\n".join(lines) + "\n"


def dump_report(report: dict[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(report: dict[str, Any], *, fmt: str, output_path: str | None) -> str:
    rendered = dump_report(report, fmt=fmt)
    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


__all__ = [
    "DEFAULT_LIMIT",
    "audit_published_posts",
    "dump_report",
    "render_human_report",
    "scan_wp_published_posts",
    "write_report",
]
