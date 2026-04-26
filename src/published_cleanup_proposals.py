from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from src import guarded_publish_evaluator as evaluator
from src import guarded_publish_runner as cleanup_runner
from src import published_site_component_audit as site_audit
from src.pre_publish_fact_check import extractor


ROOT = Path(__file__).resolve().parent.parent
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
HUMAN_PREVIEW_LIMIT = 20
REPAIRABLE_ACTIONS = dict(cleanup_runner.REPAIRABLE_FLAG_ACTION_MAP)
WARNING_ONLY_REASON_BY_FLAG = {
    "missing_primary_source": "warning_only:legacy_repairable_missing_primary_source",
    "missing_featured_media": "warning_only:legacy_repairable_missing_featured_media",
    "title_body_mismatch_partial": "warning_only:legacy_repairable_title_body_mismatch_partial",
    "numerical_anomaly_low_severity": "warning_only:legacy_repairable_numerical_anomaly_low_severity",
    "stale_for_breaking_board": "freshness_audit_only_no_op",
    "expired_lineup_or_pregame": "freshness_audit_only_no_op",
    "expired_game_context": "freshness_audit_only_no_op",
}
HIGH_PRIORITY_FLAGS = frozenset(
    {
        "heading_sentence_as_h3",
        "dev_log_contamination",
        "weird_heading_label",
    }
)
MEDIUM_PRIORITY_FLAGS = frozenset(
    {
        "site_component_mixed_into_body",
        "light_structure_break",
        "weak_source_display",
        "subtype_unresolved",
        "long_body",
        "title_body_mismatch_partial",
    }
)


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_iso_to_jst(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _collapse(value: Any) -> str:
    return cleanup_runner._collapse_snippet(value)


def _read_history_rows(path: str | Path) -> list[dict[str, Any]]:
    target = _path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as handle:
        for index, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"history row must be an object: {target}:{index}")
            try:
                payload["_parsed_ts"] = _parse_iso_to_jst(payload["ts"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"history row missing valid ts: {target}:{index}") from exc
            rows.append(payload)
    rows.sort(key=lambda item: item["_parsed_ts"], reverse=True)
    return rows


def load_today_publish_post_ids(
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> list[int]:
    current_now = _now_jst(now)
    if limit is not None and int(limit) <= 0:
        raise ValueError("history limit must be > 0")

    post_ids: list[int] = []
    seen: set[int] = set()
    for row in _read_history_rows(history_path):
        if str(row.get("status") or "").strip().lower() != "sent":
            continue
        if row["_parsed_ts"].date() != current_now.date():
            continue
        try:
            post_id = int(row["post_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if post_id in seen:
            continue
        seen.add(post_id)
        post_ids.append(post_id)
        if limit is not None and len(post_ids) >= int(limit):
            break
    return post_ids


def _priority_for_flags(repairable_flags: Sequence[str], yellow_reasons: Sequence[str]) -> str:
    flags = {str(flag) for flag in repairable_flags}
    reasons = {str(reason) for reason in yellow_reasons}
    if HIGH_PRIORITY_FLAGS.intersection(flags):
        return "high"
    if "site_component_mixed_into_body_middle" in reasons:
        return "high"
    if MEDIUM_PRIORITY_FLAGS.intersection(flags):
        return "medium"
    if "site_component_mixed_into_body_tail" in reasons:
        return "medium"
    return "low"


def _site_component_reasons_from_html(body_html: str) -> list[str]:
    body = body_html or ""
    if not body:
        return []

    matches = list(cleanup_runner.RELATED_POSTS_BLOCK_RE.finditer(body))
    matches.extend(cleanup_runner.SITE_COMPONENT_LABEL_TAG_RE.finditer(body))
    if not matches:
        return []

    first_start = min(match.start() for match in matches)
    position_ratio = first_start / max(len(body), 1)
    if position_ratio < 0.7:
        return ["site_component_mixed_into_body_middle"]
    return ["site_component_mixed_into_body_tail"]


def _site_component_yellow_reasons(body_html: str, body_text: str) -> list[str]:
    site_hits = site_audit._site_component_hits(body_text)
    if site_hits:
        return site_audit._site_component_detected_types(site_hits)
    return _site_component_reasons_from_html(body_html)


def _warning_only_cleanup_actions(flag: str, raw_post: dict[str, Any], body_html: str) -> list[dict[str, str]]:
    reason = WARNING_ONLY_REASON_BY_FLAG.get(flag)
    if reason is None:
        raise cleanup_runner.CandidateRefusedError("cleanup_action_unmapped", f"cleanup_action_unmapped:{flag}")
    _, actions = cleanup_runner._warning_only_flag_cleanup(flag, raw_post, body_html, reason=reason)
    return actions


def _simulate_cleanup_actions(flag: str, raw_post: dict[str, Any], body_html: str) -> list[dict[str, str]]:
    if flag == "heading_sentence_as_h3":
        _, actions = cleanup_runner._replace_heading_sentence_h3(body_html)
        return actions
    if flag == "weird_heading_label":
        _, actions = cleanup_runner._remove_weird_heading_labels(body_html)
        return actions
    if flag == "dev_log_contamination":
        _, actions = cleanup_runner._remove_dev_log_contamination(body_html)
        return actions
    if flag == "site_component_mixed_into_body":
        _, actions = cleanup_runner._remove_site_component_mixed_into_body(body_html)
        return actions
    if flag == "ai_tone_heading_or_lead":
        _, actions = cleanup_runner._warning_only_ai_tone_cleanup(raw_post, body_html)
        return actions
    if flag == "light_structure_break":
        _, actions = cleanup_runner._remove_light_structure_breaks(body_html)
        return actions
    if flag == "weak_source_display":
        _, actions = cleanup_runner._append_weak_source_display(body_html, raw_post)
        return actions
    if flag == "subtype_unresolved":
        _, actions, _ = cleanup_runner._resolve_subtype_cleanup(raw_post, body_html)
        return actions
    if flag == "long_body":
        _, actions = cleanup_runner._compress_long_body(body_html, raw_post)
        return actions
    return _warning_only_cleanup_actions(flag, raw_post, body_html)


def _fallback_cleanup_item(flag: str, body_html: str, detail: str) -> dict[str, str]:
    action_name = REPAIRABLE_ACTIONS.get(flag, "manual_review")
    preview = _collapse(extractor._body_text_value(body_html) or body_html)
    return {
        "flag": flag,
        "before_excerpt": preview,
        "after_excerpt": preview,
        "action": f"{action_name}:manual_review",
        "detail": detail,
    }


def _cleanup_items_for_flag(flag: str, raw_post: dict[str, Any], body_html: str) -> list[dict[str, str]]:
    action_name = REPAIRABLE_ACTIONS.get(flag, "manual_review")
    try:
        actions = _simulate_cleanup_actions(flag, raw_post, body_html)
    except cleanup_runner.CandidateRefusedError as exc:
        return [_fallback_cleanup_item(flag, body_html, exc.detail)]

    if not actions:
        return [_fallback_cleanup_item(flag, body_html, "cleanup_action_empty")]

    items: list[dict[str, str]] = []
    for action in actions:
        items.append(
            {
                "flag": flag,
                "before_excerpt": str(action.get("before") or ""),
                "after_excerpt": str(action.get("after") or ""),
                "action": action_name,
                "detail": str(action.get("reason") or ""),
            }
        )
    return items


def _dedupe_items(items: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for item in items:
        key = (
            str(item.get("flag") or ""),
            str(item.get("before_excerpt") or ""),
            str(item.get("after_excerpt") or ""),
            str(item.get("action") or ""),
            str(item.get("detail") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(item))
    return deduped


def build_post_cleanup_proposal(raw_post: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any] | None:
    record = extractor.extract_post_record(raw_post)
    evaluation = evaluator._evaluate_record(raw_post, now=now)
    entry = evaluation["entry"]
    repairable_flags = list(dict.fromkeys(str(flag) for flag in entry.get("repairable_flags") or [] if str(flag)))

    body_html = str(record.get("body_html") or "")
    body_text = str(record.get("body_text") or "")
    yellow_reasons = list(dict.fromkeys(str(flag) for flag in entry.get("yellow_reasons") or [] if str(flag)))
    site_component_reasons = _site_component_yellow_reasons(body_html, body_text)
    if site_component_reasons and "site_component_mixed_into_body" not in repairable_flags:
        repairable_flags.append("site_component_mixed_into_body")
    for reason in site_component_reasons:
        if reason not in yellow_reasons:
            yellow_reasons.append(reason)
    if not repairable_flags:
        return None
    proposed_cleanups: list[dict[str, str]] = []
    for flag in repairable_flags:
        proposed_cleanups.extend(_cleanup_items_for_flag(flag, raw_post, body_html))
    proposed_cleanups = _dedupe_items(proposed_cleanups)
    if not proposed_cleanups:
        return None

    return {
        "post_id": int(record["post_id"]),
        "title": str(record.get("title") or ""),
        "priority": _priority_for_flags(repairable_flags, yellow_reasons),
        "repairable_flags": repairable_flags,
        "yellow_reasons": yellow_reasons,
        "hard_stop_flags": list(dict.fromkeys(str(flag) for flag in entry.get("hard_stop_flags") or [] if str(flag))),
        "proposed_cleanups": proposed_cleanups,
    }


def _resolve_target_post_ids(
    *,
    post_ids: Sequence[int] | None,
    from_history: int | None,
    history_path: str | Path,
    now: datetime | None,
) -> list[int]:
    if post_ids is not None and from_history is not None:
        raise ValueError("post_ids and from_history are mutually exclusive")
    if post_ids is not None:
        return [int(post_id) for post_id in post_ids]
    return load_today_publish_post_ids(history_path=history_path, now=now, limit=from_history)


def generate_cleanup_proposals(
    wp_client: Any,
    *,
    post_ids: Sequence[int] | None = None,
    from_history: int | None = None,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_now = _now_jst(now)
    target_post_ids = _resolve_target_post_ids(
        post_ids=post_ids,
        from_history=from_history,
        history_path=history_path,
        now=current_now,
    )

    cleanup_proposals: list[dict[str, Any]] = []
    clean_posts: list[int] = []
    skipped_posts: list[dict[str, Any]] = []
    by_flag: Counter[str] = Counter()

    for post_id in target_post_ids:
        raw_post = dict(wp_client.get_post(int(post_id)) or {})
        status = str(raw_post.get("status") or "").strip().lower()
        if status != "publish":
            skipped_posts.append({"post_id": int(post_id), "status": status or "missing"})
            continue
        proposal = build_post_cleanup_proposal(raw_post, now=current_now)
        if proposal is None:
            clean_posts.append(int(post_id))
            continue
        cleanup_proposals.append(proposal)
        for flag in proposal["repairable_flags"]:
            by_flag[str(flag)] += 1

    source = "explicit_post_ids" if post_ids is not None else "today_publish_history"
    return {
        "scan_meta": {
            "source": source,
            "target_post_ids": [int(post_id) for post_id in target_post_ids],
            "history_path": str(_path(history_path)),
            "from_history": int(from_history) if from_history is not None else None,
            "ts": current_now.isoformat(),
            "scanned": len(target_post_ids),
            "skipped_non_publish": len(skipped_posts),
        },
        "cleanup_proposals": cleanup_proposals,
        "clean_posts": clean_posts,
        "skipped_posts": skipped_posts,
        "summary": {
            "total": len(target_post_ids),
            "with_proposals": len(cleanup_proposals),
            "clean_count": len(clean_posts),
            "skipped_non_publish": len(skipped_posts),
            "by_flag": dict(sorted(by_flag.items())),
        },
    }


def render_human_report(report: dict[str, Any]) -> str:
    scan_meta = report["scan_meta"]
    summary = report["summary"]
    lines = [
        "Published Cleanup Proposals Audit",
        (
            f"source={scan_meta['source']} scanned={scan_meta['scanned']} "
            f"skipped_non_publish={scan_meta['skipped_non_publish']} ts={scan_meta['ts']}"
        ),
        "",
        "Summary",
        f"total={summary['total']}",
        f"with_proposals={summary['with_proposals']}",
        f"clean_count={summary['clean_count']}",
        f"skipped_non_publish={summary['skipped_non_publish']}",
        "",
        f"Cleanup Proposals (top {HUMAN_PREVIEW_LIMIT})",
    ]
    proposals = report["cleanup_proposals"][:HUMAN_PREVIEW_LIMIT]
    if not proposals:
        lines.append("- none")
    else:
        for proposal in proposals:
            lines.append(
                f"- {proposal['post_id']} | {proposal['priority']} | {proposal['title']} | "
                f"{', '.join(proposal['repairable_flags'])}"
            )
    return "\n".join(lines) + "\n"


def dump_report(report: dict[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(report: dict[str, Any], *, fmt: str, output_path: str | None) -> str:
    rendered = dump_report(report, fmt=fmt)
    if output_path:
        _path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


__all__ = [
    "DEFAULT_HISTORY_PATH",
    "build_post_cleanup_proposal",
    "dump_report",
    "generate_cleanup_proposals",
    "load_today_publish_post_ids",
    "render_human_report",
    "write_report",
]
