from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src import guarded_publish_runner as publish_runner
from src.pre_publish_fact_check import extractor
from src.tools.draft_body_editor import _extract_prose_text


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_WINDOW_HOURS = 72
DEFAULT_MAX_POOL = 200
HUMAN_PREVIEW_LIMIT = 20

DISTRIBUTION_ORDER = ("<500", "500-1000", "1000-2000", "2000-3500", ">3500")
AXIS_ORDER = ("ai_tone", "related_articles", "twitter_url", "lineup_duplication", "generality")
POLICY_ORDER = (
    "lineup",
    "postgame",
    "farm",
    "comment",
    "notice",
    "pregame",
    "probable_starter",
    "program",
    "injury",
)

SUBTYPE_POLICY: dict[str, dict[str, Any]] = {
    "lineup": {
        "limit": 3500,
        "compressibility": "high",
        "exclude_condition": "compressed>3500",
        "note": "AI tone / 関連記事 / Twitter / lineup 重複を優先圧縮",
    },
    "postgame": {
        "limit": 3500,
        "compressibility": "medium",
        "exclude_condition": "compressed>3500",
        "note": "scoreline と主 play を残し、一般論だけ削る",
    },
    "farm": {
        "limit": 2500,
        "compressibility": "high",
        "exclude_condition": "compressed>2500",
        "note": "短報中心のため AI tone 比率が高ければ圧縮余地あり",
    },
    "comment": {
        "limit": 2000,
        "compressibility": "low",
        "exclude_condition": "compressed>2000",
        "note": "quote 主体。削り過ぎると記事核を失う",
    },
    "notice": {
        "limit": 1500,
        "compressibility": "high",
        "exclude_condition": "compressed>1500",
        "note": "告知・昇格系は boilerplate を優先削除",
    },
    "pregame": {
        "limit": 1500,
        "compressibility": "medium",
        "exclude_condition": "compressed>1500",
        "note": "speculative な一般論を削っても超えるなら hold",
    },
    "probable_starter": {
        "limit": 1500,
        "compressibility": "high",
        "exclude_condition": "compressed>1500",
        "note": "投手紹介・統計以外を削る",
    },
    "program": {
        "limit": 1500,
        "compressibility": "high",
        "exclude_condition": "compressed>1500",
        "note": "放送情報に不要な prose を残さない",
    },
    "injury": {
        "limit": None,
        "compressibility": "hold",
        "exclude_condition": "PUB-002-A R5 hold",
        "note": "長さではなく injury hold を優先",
    },
}

SUBTYPE_ALIASES = {
    "comment_notice": "comment",
    "farm_result": "farm",
    "injury_notice": "injury",
    "lineup_notice": "lineup",
    "manager": "comment",
    "off_field": "notice",
    "postgame_result": "postgame",
    "program_notice": "program",
    "probable_pitcher": "probable_starter",
    "transaction_notice": "notice",
}

RELATED_BLOCK_RE = re.compile(
    r'(?is)<div\b[^>]*class=["\'][^"\']*yoshilover-related-posts[^"\']*["\'][^>]*>.*?</div>'
)
X_URL_RE = re.compile(r"https?://(?:www\.)?(?:x\.com|twitter\.com|mobile\.twitter\.com)/[^\s\"'<>]+", re.IGNORECASE)
AI_TONE_HEADING_RE = re.compile(
    r"^(?:💬.*|【(?:注目ポイント|今日のポイント|このニュース、どう見る|先に予想を書く|みんなの本音は|先発投手)】)$"
)
AI_TONE_LINE_RE = re.compile(
    r"(どう見る|本音|気になる|見どころ|注目したい|鍵になりそう|でしょう|かもしれません|と言えそうです|と言えるでしょう)"
)
GENERALITY_LINE_RE = re.compile(
    r"(押さえておきたい|したいところ|見ておきたい|と言えるでしょう|かもしれません|なりそうです|注目したい|期待したい|"
    r"元記事で確認できる範囲|まずは|流れをつかみたい|鍵になりそう)"
)
LINEUP_SLOT_RE = re.compile(r"^(?P<slot>[1-9１-９])(?:番|[\.．])")
SOURCE_LABEL_RE = re.compile(r"^(?:参照元|引用元|出典|参考|参照元|source)\s*[:：]", re.IGNORECASE)


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


def _normalize_subtype_token(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    if token in SUBTYPE_ALIASES:
        return SUBTYPE_ALIASES[token]
    if token in SUBTYPE_POLICY:
        return token
    if "injury" in token:
        return "injury"
    if "lineup" in token:
        return "lineup"
    if "probable" in token or "starter" in token or "pitcher" in token:
        return "probable_starter"
    if "farm" in token:
        return "farm"
    if "postgame" in token or token.endswith("_result") or token == "result":
        return "postgame"
    if "program" in token or "broadcast" in token:
        return "program"
    if "pregame" in token:
        return "pregame"
    if "comment" in token or "manager" in token:
        return "comment"
    if "notice" in token or "roster" in token or "transaction" in token or "off_field" in token:
        return "notice"
    return ""


def _resolve_subtype(raw_post: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    meta = _extract_meta(raw_post)
    for candidate in (
        meta.get("article_subtype"),
        raw_post.get("article_subtype"),
        record.get("inferred_subtype"),
        extractor.infer_subtype(str(record.get("title") or "")),
    ):
        normalized = _normalize_subtype_token(str(candidate or ""))
        if normalized:
            return normalized
    return "other"


def _empty_distribution() -> dict[str, int]:
    return {label: 0 for label in DISTRIBUTION_ORDER}


def _bucket_label(prose_len: int) -> str:
    if prose_len < 500:
        return "<500"
    if prose_len <= 1000:
        return "500-1000"
    if prose_len <= 2000:
        return "1000-2000"
    if prose_len <= 3500:
        return "2000-3500"
    return ">3500"


def _empty_axis_summary() -> dict[str, dict[str, int]]:
    return {axis: {"posts": 0, "hits": 0, "chars": 0} for axis in AXIS_ORDER}


def _empty_subtype_summary() -> dict[str, dict[str, int]]:
    summary = {
        subtype: {"count": 0, "over_limit": 0, "compressible": 0, "exclude": 0}
        for subtype in POLICY_ORDER
    }
    summary["other"] = {"count": 0, "over_limit": 0, "compressible": 0, "exclude": 0}
    return summary


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "")).strip()


def _extract_lines(record: Mapping[str, Any]) -> list[str]:
    body_text = str(record.get("body_text") or "")
    return [line for line in (_normalize_line(raw) for raw in body_text.splitlines()) if line]


def _is_url_only(line: str) -> bool:
    return bool(publish_runner.SOURCE_URL_RE.fullmatch(line))


def _is_x_url_only(line: str) -> bool:
    return bool(X_URL_RE.fullmatch(line))


def _is_source_line(line: str) -> bool:
    return bool(SOURCE_LABEL_RE.search(line))


def _related_block_lines(body_html: str) -> list[str]:
    block_lines: list[str] = []
    for match in RELATED_BLOCK_RE.finditer(body_html or ""):
        text = publish_runner._strip_html(match.group(0))
        for raw_line in text.splitlines():
            line = _normalize_line(raw_line)
            if line and line not in block_lines:
                block_lines.append(line)
    return block_lines


def _match_block_lines(lines: Sequence[str], block_lines: Sequence[str]) -> set[int]:
    matched: set[int] = set()
    start = 0
    for block_line in block_lines:
        for idx in range(start, len(lines)):
            if _normalize_line(lines[idx]) == _normalize_line(block_line):
                matched.add(idx)
                start = idx + 1
                break
    return matched


def _fallback_related_indices(lines: Sequence[str]) -> set[int]:
    indices: set[int] = set()
    for idx, line in enumerate(lines):
        if "【関連記事】" not in line:
            continue
        indices.add(idx)
        for follow in range(idx + 1, min(len(lines), idx + 6)):
            candidate = lines[follow]
            if candidate.startswith("【") or candidate.startswith("💬") or _is_source_line(candidate):
                break
            if _is_url_only(candidate):
                break
            indices.add(follow)
    return indices


def _is_ai_tone_line(line: str) -> bool:
    if not line or _is_source_line(line):
        return False
    if "【関連記事】" in line:
        return False
    if AI_TONE_HEADING_RE.search(line):
        return True
    if line.startswith("💬"):
        return True
    if any(pattern.search(line) for pattern in publish_runner.SITE_COMPONENT_PATTERNS) and "関連記事" not in line:
        return True
    return bool(AI_TONE_LINE_RE.search(line))


def _is_generality_line(line: str) -> bool:
    if not line or _is_source_line(line) or _is_url_only(line):
        return False
    if _is_ai_tone_line(line):
        return False
    return bool(GENERALITY_LINE_RE.search(line))


def _normalize_slot(slot: str) -> str:
    translated = slot.translate(str.maketrans("１２３４５６７８９", "123456789"))
    return translated.strip()


def _lineup_duplicate_indices(lines: Sequence[str], subtype: str) -> tuple[set[int], int]:
    if subtype != "lineup":
        return set(), 0
    seen_slots: set[str] = set()
    duplicate_indices: set[int] = set()
    hit_count = 0
    for idx, raw_line in enumerate(lines):
        line = re.sub(r"\s+", "", raw_line)
        match = LINEUP_SLOT_RE.match(line)
        if not match:
            continue
        slot = _normalize_slot(match.group("slot"))
        if slot in seen_slots:
            duplicate_indices.add(idx)
            hit_count += 1
            continue
        seen_slots.add(slot)
    return duplicate_indices, hit_count


def _collect_axis_details(
    *,
    body_html: str,
    lines: Sequence[str],
    subtype: str,
) -> dict[str, dict[str, Any]]:
    details = {axis: {"indices": set(), "hit_count": 0, "chars": 0} for axis in AXIS_ORDER}

    related_lines = _related_block_lines(body_html)
    related_indices = _match_block_lines(lines, related_lines) | _fallback_related_indices(lines)
    details["related_articles"]["indices"] = related_indices
    details["related_articles"]["hit_count"] = len(related_indices)

    ai_indices = {idx for idx, line in enumerate(lines) if _is_ai_tone_line(line)}
    details["ai_tone"]["indices"] = ai_indices
    details["ai_tone"]["hit_count"] = len(ai_indices)

    twitter_indices = {idx for idx, line in enumerate(lines) if _is_x_url_only(line)}
    details["twitter_url"]["indices"] = twitter_indices
    details["twitter_url"]["hit_count"] = len(twitter_indices)

    lineup_indices, lineup_hits = _lineup_duplicate_indices(lines, subtype)
    details["lineup_duplication"]["indices"] = lineup_indices
    details["lineup_duplication"]["hit_count"] = lineup_hits

    generality_indices = {idx for idx, line in enumerate(lines) if _is_generality_line(line)}
    details["generality"]["indices"] = generality_indices
    details["generality"]["hit_count"] = len(generality_indices)

    for axis in AXIS_ORDER:
        indices = details[axis]["indices"]
        details[axis]["chars"] = sum(len(lines[idx]) for idx in indices)
    return details


def _estimated_after_compress(lines: Sequence[str], axis_details: Mapping[str, Mapping[str, Any]]) -> int:
    drop_indices: set[int] = set()
    for axis in AXIS_ORDER:
        drop_indices.update(int(index) for index in axis_details[axis]["indices"])
    kept = [line for idx, line in enumerate(lines) if idx not in drop_indices]
    return len(" ".join(kept).strip())


def _compress_targets(axis_details: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return [axis for axis in AXIS_ORDER if int(axis_details[axis]["hit_count"]) > 0]


def _policy_table() -> dict[str, dict[str, Any]]:
    return {subtype: dict(SUBTYPE_POLICY[subtype]) for subtype in POLICY_ORDER}


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
    distribution = _empty_distribution()
    by_subtype = _empty_subtype_summary()
    axis_counts = _empty_axis_summary()
    compressible_candidates: list[dict[str, Any]] = []
    exclude_candidates: list[dict[str, Any]] = []
    scanned = 0

    for raw_post in list(raw_posts)[: max(0, int(max_pool))]:
        record = extractor.extract_post_record(dict(raw_post))
        modified_at = _parse_wp_datetime(record.get("modified_at") or raw_post.get("modified"), fallback_now=now_jst)
        if modified_at < cutoff:
            continue

        scanned += 1
        subtype = _resolve_subtype(raw_post, record)
        bucket = by_subtype.setdefault(subtype, {"count": 0, "over_limit": 0, "compressible": 0, "exclude": 0})
        bucket["count"] += 1

        body_html = str(record.get("body_html") or "")
        prose_len = len(_extract_prose_text(body_html))
        distribution[_bucket_label(prose_len)] += 1

        policy = SUBTYPE_POLICY.get(subtype)
        if not policy:
            continue

        limit = policy["limit"]
        if limit is None:
            continue
        if prose_len <= int(limit):
            continue

        bucket["over_limit"] += 1
        lines = _extract_lines(record)
        axis_details = _collect_axis_details(body_html=body_html, lines=lines, subtype=subtype)
        estimated_after = _estimated_after_compress(lines, axis_details)
        targets = _compress_targets(axis_details)

        for axis in AXIS_ORDER:
            if int(axis_details[axis]["hit_count"]) <= 0:
                continue
            axis_counts[axis]["posts"] += 1
            axis_counts[axis]["hits"] += int(axis_details[axis]["hit_count"])
            axis_counts[axis]["chars"] += int(axis_details[axis]["chars"])

        candidate = {
            "post_id": int(record["post_id"]),
            "title": str(record.get("title") or ""),
            "subtype": subtype,
            "limit": int(limit),
            "prose_len": prose_len,
            "estimated_after_compress": estimated_after,
            "compress_targets": targets,
        }

        if targets and estimated_after <= int(limit):
            bucket["compressible"] += 1
            compressible_candidates.append(candidate)
            continue

        bucket["exclude"] += 1
        exclude_reason = "after_compress_still_over_limit"
        if not targets:
            exclude_reason = "no_safe_compression_target"
        exclude_candidates.append({**candidate, "reason": exclude_reason})

    compressible_candidates.sort(key=lambda item: (item["estimated_after_compress"], item["post_id"]))
    exclude_candidates.sort(key=lambda item: (-item["prose_len"], item["post_id"]))
    policy_rows = _policy_table()

    return {
        "scan_meta": {
            "window_hours": int(window_hours),
            "max_pool": int(max_pool),
            "fetched": int(fetched_count if fetched_count is not None else len(raw_posts)),
            "scanned": scanned,
            "ts": now_jst.isoformat(),
            "wp_write_operations": 0,
        },
        "prose_length_distribution": distribution,
        "by_subtype": by_subtype,
        "compressible_candidates": compressible_candidates,
        "exclude_candidates": exclude_candidates,
        "summary": {
            "total_drafts_in_pool": scanned,
            "over_limit_total": len(compressible_candidates) + len(exclude_candidates),
            "compressible_total": len(compressible_candidates),
            "exclude_total": len(exclude_candidates),
            "injury_hold_count": by_subtype.get("injury", {}).get("count", 0),
            "structure_axes": axis_counts,
            "subtype_policy": policy_rows,
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
    distribution = report["prose_length_distribution"]
    by_subtype = report["by_subtype"]
    summary = report["summary"]
    axis_counts = summary["structure_axes"]
    subtype_policy = summary["subtype_policy"]

    lines = [
        "Long Body Compression Audit",
        (
            f"window_hours={scan_meta['window_hours']}  max_pool={scan_meta['max_pool']}  "
            f"fetched={scan_meta['fetched']}  scanned={scan_meta['scanned']}  ts={scan_meta['ts']}"
        ),
        "",
        "Summary",
        "metric                     value",
        f"total_drafts_in_pool       {summary['total_drafts_in_pool']}",
        f"over_limit_total           {summary['over_limit_total']}",
        f"compressible_total         {summary['compressible_total']}",
        f"exclude_total              {summary['exclude_total']}",
        f"injury_hold_count          {summary['injury_hold_count']}",
        f"wp_write_operations        {scan_meta['wp_write_operations']}",
        "",
        "Prose Length Distribution",
        "bucket                    count",
    ]
    for bucket_name in DISTRIBUTION_ORDER:
        lines.append(f"{bucket_name:<25} {distribution[bucket_name]}")

    lines.extend(["", "Structure Axes (over-limit drafts only)", "axis                      posts  hits  chars"])
    for axis in AXIS_ORDER:
        payload = axis_counts[axis]
        lines.append(f"{axis:<25} {payload['posts']:<5} {payload['hits']:<5} {payload['chars']}")

    lines.extend(["", "Subtype Policy", "subtype                limit   count  over  comp  excl  note"])
    subtype_rows = list(POLICY_ORDER)
    extra_subtypes = sorted(
        subtype for subtype in by_subtype.keys() if subtype not in POLICY_ORDER and subtype != "other"
    )
    subtype_rows.extend(extra_subtypes)
    subtype_rows.append("other")
    for subtype in subtype_rows:
        counts = by_subtype.get(subtype, {"count": 0, "over_limit": 0, "compressible": 0, "exclude": 0})
        policy = subtype_policy.get(subtype)
        limit = "-"
        note = "policy_unmapped"
        if policy:
            limit = "-" if policy["limit"] is None else str(policy["limit"])
            note = str(policy["note"])
        lines.append(
            f"{subtype:<22} {limit:<6} {counts['count']:<5} {counts['over_limit']:<5} "
            f"{counts['compressible']:<5} {counts['exclude']:<5} {note}"
        )

    lines.extend(["", f"Compressible Candidates (top {HUMAN_PREVIEW_LIMIT})"])
    if not report["compressible_candidates"]:
        lines.append("- none")
    else:
        for item in report["compressible_candidates"][:HUMAN_PREVIEW_LIMIT]:
            lines.append(
                f"- {item['post_id']} | {item['subtype']} | {item['prose_len']} -> "
                f"{item['estimated_after_compress']} | {', '.join(item['compress_targets'])}"
            )

    lines.extend(["", f"Exclude Candidates (top {HUMAN_PREVIEW_LIMIT})"])
    if not report["exclude_candidates"]:
        lines.append("- none")
    else:
        for item in report["exclude_candidates"][:HUMAN_PREVIEW_LIMIT]:
            lines.append(
                f"- {item['post_id']} | {item['subtype']} | {item['prose_len']} -> "
                f"{item['estimated_after_compress']} | {item['reason']}"
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
    "DEFAULT_MAX_POOL",
    "DEFAULT_WINDOW_HOURS",
    "SUBTYPE_POLICY",
    "audit_raw_posts",
    "dump_report",
    "render_human_report",
    "scan_wp_drafts",
    "write_report",
]
