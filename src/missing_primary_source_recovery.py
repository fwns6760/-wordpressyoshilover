from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from src import guarded_publish_evaluator as publish_gate
from src.pre_publish_fact_check import extractor
from src.tools import run_draft_body_editor_lane as source_lane


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_WINDOW_HOURS = 96
DEFAULT_MAX_POOL = 200
SAMPLE_LIMIT = 5

CAUSE_TAG_ORDER = (
    "no_source_anywhere",
    "source_name_only",
    "footer_only_no_url",
    "meta_only_no_body",
    "twitter_only",
    "social_news_subtype",
)
HUMAN_CAUSE_PREVIEW_LIMIT = 3
TITLE_PREVIEW_LIMIT = 80

X_DOMAINS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}
SOURCE_LABEL_RE = re.compile(r"参照元\s*[：:]", re.IGNORECASE)
META_URL_KEYS = (
    "source_urls",
    "yl_source_urls",
    "source_url",
    "_yoshilover_source_url",
    "yl_source_url",
    "canonical_source_url",
    "original_url",
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


def _extract_meta(post: Mapping[str, Any]) -> dict[str, Any]:
    meta = post.get("meta")
    if isinstance(meta, Mapping):
        return dict(meta)
    return {}


def _title_preview(title: str) -> str:
    clean = re.sub(r"\s+", " ", (title or "")).strip()
    if len(clean) <= TITLE_PREVIEW_LIMIT:
        return clean
    return clean[: TITLE_PREVIEW_LIMIT - 1].rstrip() + "…"


def _excerpt_text(post: Mapping[str, Any]) -> str:
    excerpt = post.get("excerpt")
    if isinstance(excerpt, Mapping):
        raw = excerpt.get("raw")
        if raw:
            return extractor._body_text_value(str(raw))
        rendered = excerpt.get("rendered")
        if rendered:
            return extractor._body_text_value(str(rendered))
    if isinstance(excerpt, str):
        return extractor._body_text_value(excerpt)
    return ""


def _normalize_url(url: str) -> str:
    return html.unescape((url or "").strip())


def _is_x_url(url: str) -> bool:
    try:
        hostname = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return hostname in X_DOMAINS


def _filter_primary_urls(urls: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen = set()
    for value in urls:
        url = _normalize_url(str(value))
        if not url or url in seen:
            continue
        if not source_lane._is_primary_source_url(url):
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _extract_meta_source_urls(post: Mapping[str, Any]) -> list[str]:
    meta = _extract_meta(post)
    candidates: list[str] = []

    for key in META_URL_KEYS:
        value = meta.get(key, post.get(key))
        if isinstance(value, str):
            candidates.extend(part for part in re.split(r"[\s,]+", value) if part.strip())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            candidates.extend(str(item) for item in value if str(item).strip())
    return _filter_primary_urls(candidates)


def _body_primary_urls(record: Mapping[str, Any]) -> list[str]:
    return _filter_primary_urls([str(url) for url in (record.get("source_urls") or [])])


def _source_name_hit(*texts: str) -> bool:
    joined = "\n".join(text for text in texts if text)
    return bool(publish_gate.PRIMARY_SRC_RE.search(joined))


def _is_social_news(post: Mapping[str, Any]) -> bool:
    meta = _extract_meta(post)
    source_type = str(meta.get("source_type") or post.get("source_type") or "").strip().lower()
    article_subtype = str(meta.get("article_subtype") or post.get("article_subtype") or "").strip().lower()
    return source_type == "social_news" or article_subtype == "social"


def _sample(post_id: int, title: str) -> dict[str, Any]:
    return {
        "post_id": int(post_id),
        "title": _title_preview(title),
    }


def _classify_post(raw_post: Mapping[str, Any]) -> tuple[str | None, dict[str, Any]] | None:
    record = extractor.extract_post_record(dict(raw_post))
    post_id = int(record["post_id"])
    title = str(record.get("title") or "")
    body_html = str(record.get("body_html") or "")
    body_text = str(record.get("body_text") or "")
    source_block = str(record.get("source_block") or "")
    excerpt_text = _excerpt_text(raw_post)

    strict_urls = source_lane._extract_source_urls(dict(raw_post))
    meta_urls = _extract_meta_source_urls(raw_post)
    body_urls = _body_primary_urls(record)

    strict_non_x = [url for url in strict_urls if not _is_x_url(url)]
    meta_non_x = [url for url in meta_urls if not _is_x_url(url)]
    body_non_x = [url for url in body_urls if not _is_x_url(url)]

    any_non_x_urls = list(dict.fromkeys(strict_non_x + meta_non_x + body_non_x))
    any_x_urls = list(
        dict.fromkeys(
            [url for url in strict_urls if _is_x_url(url)]
            + [url for url in meta_urls if _is_x_url(url)]
            + [url for url in body_urls if _is_x_url(url)]
        )
    )

    body_source_name_hit = _source_name_hit(body_text, source_block)
    source_name_anywhere = _source_name_hit(title, excerpt_text, body_text, source_block)
    has_source_footer = bool(source_block) or bool(SOURCE_LABEL_RE.search(body_html)) or bool(SOURCE_LABEL_RE.search(body_text))
    social_news = _is_social_news(raw_post)

    if social_news and not any_non_x_urls:
        return "social_news_subtype", _sample(post_id, title)
    if meta_non_x and not body_source_name_hit and not body_non_x:
        return "meta_only_no_body", _sample(post_id, title)
    if has_source_footer and body_non_x and not strict_non_x:
        return "footer_only_no_url", _sample(post_id, title)
    if any_x_urls and not any_non_x_urls:
        return "twitter_only", _sample(post_id, title)
    if source_name_anywhere and not any_non_x_urls and not any_x_urls:
        return "source_name_only", _sample(post_id, title)
    if not source_name_anywhere and not any_non_x_urls and not any_x_urls:
        return "no_source_anywhere", _sample(post_id, title)
    return None


def _empty_cause_table() -> dict[str, dict[str, Any]]:
    return {
        cause_tag: {
            "count": 0,
            "samples": [],
        }
        for cause_tag in CAUSE_TAG_ORDER
    }


def _candidate_catalog(counts: Mapping[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "cause_tag": "footer_only_no_url",
            "fix": "_extract_source_urls regex 強化 + footer multiline fallback 追加",
            "estimated_unblock": int(counts.get("footer_only_no_url", 0)),
            "priority": 0,
        },
        {
            "cause_tag": "meta_only_no_body",
            "fix": "meta source_url を body の参照元ブロックへ反映",
            "estimated_unblock": int(counts.get("meta_only_no_body", 0)),
            "priority": 1,
        },
        {
            "cause_tag": "source_name_only",
            "fix": "src/source_name_to_url.py 新規 mapping 追加",
            "estimated_unblock": int(counts.get("source_name_only", 0)),
            "priority": 2,
        },
        {
            "cause_tag": "social_news_subtype",
            "fix": "social_news -> primary 媒体 mapping / original_url 優先解決",
            "estimated_unblock": int(counts.get("social_news_subtype", 0)),
            "priority": 3,
        },
        {
            "cause_tag": "no_source_anywhere",
            "fix": "creator 側で primary source URL capture を必須化",
            "estimated_unblock": 0,
            "priority": 4,
        },
        {
            "cause_tag": "twitter_only",
            "fix": "original_url / canonical_source_url backfill があれば一次媒体 URL へ置換",
            "estimated_unblock": 0,
            "priority": 5,
        },
    ]


def _build_rescue_candidates(by_cause_tag: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = {cause_tag: int(payload.get("count") or 0) for cause_tag, payload in by_cause_tag.items()}
    catalog = _candidate_catalog(counts)
    active = [item for item in catalog if int(item["estimated_unblock"]) > 0]
    active.sort(key=lambda item: (-int(item["estimated_unblock"]), int(item["priority"])))
    if len(active) >= 5:
        return [{k: v for k, v in item.items() if k != "priority"} for item in active[:5]]
    if len(active) >= 3:
        return [{k: v for k, v in item.items() if k != "priority"} for item in active]

    inactive = [item for item in catalog if int(item["estimated_unblock"]) <= 0]
    inactive.sort(key=lambda item: int(item["priority"]))
    needed = max(0, 3 - len(active))
    selected = active + inactive[:needed]
    return [{k: v for k, v in item.items() if k != "priority"} for item in selected]


def audit_raw_posts(
    raw_posts: Sequence[Mapping[str, Any]],
    *,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    max_pool: int = DEFAULT_MAX_POOL,
    now: datetime | None = None,
    fetched_count: int | None = None,
) -> dict[str, Any]:
    now_jst = _now_jst(now)
    cutoff = now_jst - timedelta(hours=max(0, int(window_hours)))
    by_cause_tag = _empty_cause_table()
    scanned = 0

    for raw_post in list(raw_posts)[: max(0, int(max_pool))]:
        record = extractor.extract_post_record(dict(raw_post))
        modified_at = _parse_wp_datetime(record.get("modified_at") or raw_post.get("modified"), fallback_now=now_jst)
        if modified_at < cutoff:
            continue
        scanned += 1
        classified = _classify_post(raw_post)
        if not classified:
            continue
        cause_tag, sample = classified
        bucket = by_cause_tag[cause_tag]
        bucket["count"] = int(bucket["count"]) + 1
        if len(bucket["samples"]) < SAMPLE_LIMIT:
            bucket["samples"].append(sample)

    missing_primary_source_count = sum(int(bucket["count"]) for bucket in by_cause_tag.values())
    rescue_candidates = _build_rescue_candidates(by_cause_tag)
    rescue_total = sum(int(candidate["estimated_unblock"]) for candidate in rescue_candidates)
    rescue_pct = round((rescue_total / missing_primary_source_count) * 100, 1) if missing_primary_source_count else 0.0

    return {
        "scan_meta": {
            "window_hours": int(window_hours),
            "max_pool": int(max_pool),
            "fetched": int(fetched_count if fetched_count is not None else len(raw_posts)),
            "scanned": scanned,
            "ts": now_jst.isoformat(),
        },
        "missing_primary_source_count": missing_primary_source_count,
        "by_cause_tag": by_cause_tag,
        "rescue_candidates": rescue_candidates,
        "summary": {
            "total_drafts_in_pool": scanned,
            "no_primary_source_count": missing_primary_source_count,
            "rescue_pct": rescue_pct,
        },
    }


def scan_wp_drafts(
    wp_client,
    *,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    max_pool: int = DEFAULT_MAX_POOL,
    now: datetime | None = None,
) -> dict[str, Any]:
    limit = max(1, int(max_pool))
    posts: list[dict[str, Any]] = []
    page = 1
    while len(posts) < limit:
        remaining = limit - len(posts)
        page_posts = wp_client.list_posts(
            status="draft",
            per_page=min(100, remaining),
            page=page,
            orderby="modified",
            order="desc",
            context="edit",
        )
        if not page_posts:
            break
        posts.extend(list(page_posts))
        if len(page_posts) < min(100, remaining):
            break
        page += 1

    return audit_raw_posts(
        posts[:limit],
        window_hours=window_hours,
        max_pool=limit,
        now=now,
        fetched_count=len(posts[:limit]),
    )


def render_human_report(report: Mapping[str, Any]) -> str:
    scan_meta = report["scan_meta"]
    summary = report["summary"]
    by_cause_tag = report["by_cause_tag"]
    lines = [
        "Missing Primary Source Audit",
        (
            f"window_hours={scan_meta['window_hours']}  max_pool={scan_meta['max_pool']}  "
            f"fetched={scan_meta['fetched']}  scanned={scan_meta['scanned']}  ts={scan_meta['ts']}"
        ),
        "",
        "Summary",
        "metric                     value",
        f"total_drafts_in_pool       {summary['total_drafts_in_pool']}",
        f"missing_primary_source     {summary['no_primary_source_count']}",
        f"rescue_pct                 {summary['rescue_pct']}",
        "",
        "Cause Tags",
        "cause_tag                 count  samples",
    ]

    for cause_tag in CAUSE_TAG_ORDER:
        payload = by_cause_tag[cause_tag]
        samples = payload["samples"][:HUMAN_CAUSE_PREVIEW_LIMIT]
        preview = "; ".join(f"{sample['post_id']}:{sample['title']}" for sample in samples) if samples else "-"
        lines.append(f"{cause_tag:<24} {payload['count']:<5} {preview}")

    lines.extend(["", "Rescue Candidates"])
    for candidate in report["rescue_candidates"]:
        lines.append(
            f"- {candidate['cause_tag']}: {candidate['fix']} (estimated_unblock={candidate['estimated_unblock']})"
        )
    return "\n".join(lines) + "\n"


def dump_report(report: Mapping[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(report: Mapping[str, Any], *, fmt: str, output_path: str | None) -> str:
    rendered = dump_report(report, fmt=fmt)
    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


__all__ = [
    "audit_raw_posts",
    "dump_report",
    "render_human_report",
    "scan_wp_drafts",
    "write_report",
]
