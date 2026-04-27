from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from src import guarded_publish_evaluator as publish_evaluator
from src.pre_publish_fact_check import extractor


ROOT = Path(__file__).resolve().parent.parent
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
DEFAULT_YELLOW_LOG_PATH = ROOT / "logs" / "guarded_publish_yellow_log.jsonl"
DEFAULT_MAX_CANDIDATES = 50
DEFAULT_NEXT_ACTION = "halluc_lane_002_full_check"
VALID_PRIORITIES = ("high", "medium", "low")
PRIORITY_SORT_ORDER = {"high": 0, "medium": 1, "low": 2}
NUMERIC_TOKEN_RE = re.compile(r"\d+")

LOW_WARNING_FLAGS = frozenset(
    {
        "ai_tone_heading_or_lead",
        "heading_sentence_as_h3",
        "light_structure_break",
        "missing_featured_media",
    }
)
SOURCE_RISK_SIGNALS = frozenset(
    {
        "missing_primary_source",
        "source_missing",
        "source_weak",
        "source_anchor_missing",
        "source_url_missing",
        "title_subject_missing",
        "weak_source_display",
    }
)
STALE_BREAKING_SIGNALS = frozenset({"stale_for_breaking_board", "backlog_only"})
MEDICAL_ROSTER_SIGNALS = frozenset({"death_or_grave_incident", "injury_death", "roster_movement_yellow"})
HIGH_WEIGHT_BY_REASON = {
    "medical_roster_keyword": 120,
    "title_body_mismatch": 110,
    "dense_numeric_content": 100,
    "stale_breaking_board": 95,
}
MEDIUM_WEIGHT_BY_REASON = {
    "source_missing_or_weak": 80,
    "subtype_unresolved_cleanup_failed": 85,
    "awkward_role_phrasing": 70,
    "multiple_repairable_flags": 65,
}
LOW_WEIGHT_BY_REASON = {
    "ai_tone_heading_or_lead": 40,
    "heading_sentence_as_h3": 40,
    "light_structure_break": 45,
    "missing_featured_media": 35,
}
SIGNAL_LIST_KEYS = (
    "applied_flags",
    "yellow_reasons",
    "repairable_flags",
    "hard_stop_flags",
    "red_flags",
    "warning_flags",
)
FALLBACK_QUERY_URL = "https://yoshilover.com/?p={post_id}"
IGNORED_ROUTER_SIGNALS = frozenset(
    {
        "burst_cap",
        "daily_cap",
        "hourly_cap",
        "publish_failed",
        "cleanup_backup_failed",
        "backlog_deferred_for_fresh",
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


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
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
                raise ValueError(f"jsonl row must be an object: {target}:{index}")
            try:
                payload["_parsed_ts"] = _parse_iso_to_jst(payload["ts"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"jsonl row missing valid ts: {target}:{index}") from exc
            rows.append(payload)
    rows.sort(key=lambda item: item["_parsed_ts"], reverse=True)
    return rows


def _post_id_from_row(row: dict[str, Any]) -> int:
    try:
        return int(row["post_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"row missing valid post_id: {row!r}") from exc


def _split_error_tokens(value: Any) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    if raw.startswith("hard_stop:"):
        raw = raw.split(":", 1)[1]
    elif raw.startswith("warning_only:"):
        raw = raw.split(":", 1)[1]
    tokens = []
    for token in re.split(r"[,|]", raw):
        normalized = str(token).strip().lower()
        if normalized:
            tokens.append(normalized)
    return tokens


def _normalized_signal(value: Any) -> str:
    signal = str(value or "").strip().lower()
    if not signal:
        return ""
    if signal.startswith("hard_stop_"):
        return signal.removeprefix("hard_stop_")
    if signal.startswith("warning_only:"):
        signal = signal.split(":", 1)[1]
    if signal.startswith("cleanup_failed_post_condition:"):
        return "cleanup_failed_post_condition"
    if signal in {"site_component_mixed_into_body_middle", "site_component_mixed_into_body_tail"}:
        return "site_component_mixed_into_body"
    if signal == "speculative_title":
        return "ai_tone_heading_or_lead"
    return signal


def _iter_signal_values(row: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    for key in SIGNAL_LIST_KEYS:
        values = row.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for item in values:
                normalized = _normalized_signal(item)
                if normalized and normalized not in IGNORED_ROUTER_SIGNALS:
                    signals.append(normalized)
    for token in _split_error_tokens(row.get("error")):
        normalized = _normalized_signal(token)
        if normalized and normalized not in IGNORED_ROUTER_SIGNALS:
            signals.append(normalized)
    normalized_hold = _normalized_signal(row.get("hold_reason"))
    if normalized_hold and normalized_hold not in IGNORED_ROUTER_SIGNALS:
        signals.append(normalized_hold)
    normalized_manual_block = _normalized_signal(row.get("manual_x_post_block_reason"))
    if normalized_manual_block and normalized_manual_block not in IGNORED_ROUTER_SIGNALS:
        signals.append(normalized_manual_block)
    return signals


def _hard_stop_flags_for_row(row: dict[str, Any]) -> set[str]:
    error = str(row.get("error") or "").strip().lower()
    hold_reason = str(row.get("hold_reason") or "").strip().lower()
    flags: set[str] = set()
    if error.startswith("hard_stop:"):
        for token in _split_error_tokens(error):
            normalized = _normalized_signal(token)
            if normalized and normalized not in IGNORED_ROUTER_SIGNALS:
                flags.add(normalized)
    if hold_reason.startswith("hard_stop_"):
        normalized = _normalized_signal(hold_reason)
        if normalized and normalized not in IGNORED_ROUTER_SIGNALS:
            flags.add(normalized)
    for key in ("hard_stop_flags", "red_flags"):
        values = row.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for item in values:
                normalized = _normalized_signal(item)
                if normalized and normalized not in IGNORED_ROUTER_SIGNALS:
                    flags.add(normalized)
    return {flag for flag in flags if flag}


def _repairable_key(signal: str) -> str | None:
    normalized = _normalized_signal(signal)
    if not normalized:
        return None
    if normalized in publish_evaluator.REPAIRABLE_FLAGS:
        return normalized
    if normalized in SOURCE_RISK_SIGNALS:
        return "weak_source_display"
    if normalized == "subtype_unresolved_no_resolution":
        return "subtype_unresolved"
    return None


def _collect_body_text(entries: Sequence[dict[str, Any]]) -> str:
    for entry in entries:
        body_text = str(entry.get("body_text") or "").strip()
        if body_text:
            return body_text
        body_html = str(entry.get("body_html") or "").strip()
        if body_html:
            return extractor._body_text_value(body_html)
        content = entry.get("content")
        if isinstance(content, dict):
            raw = str(content.get("raw") or content.get("rendered") or "").strip()
            if raw:
                return extractor._body_text_value(raw)
        if isinstance(content, str) and content.strip():
            return extractor._body_text_value(content)
    return ""


def _first_non_empty(entries: Sequence[dict[str, Any]], keys: Sequence[str]) -> str:
    for entry in entries:
        for key in keys:
            value = entry.get(key)
            if isinstance(value, dict):
                raw = value.get("raw") or value.get("rendered")
                if raw:
                    return str(raw).strip()
            else:
                text = str(value or "").strip()
                if text:
                    return text
    return ""


def _infer_subtype(title: str, entries: Sequence[dict[str, Any]]) -> str:
    subtype = _first_non_empty(entries, ("resolved_subtype", "subtype", "article_subtype"))
    if subtype:
        return subtype.lower()
    inferred = extractor.infer_subtype(title)
    return inferred if inferred != "other" else ""


def _fallback_url(post_id: int) -> str:
    return FALLBACK_QUERY_URL.format(post_id=post_id) if post_id > 0 else ""


def _latest_entry_by_post_id(rows: Sequence[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for row in rows:
        post_id = _post_id_from_row(row)
        if post_id not in latest:
            latest[post_id] = row
    return latest


def _is_resolved(latest_history: dict[str, Any] | None, latest_yellow: dict[str, Any] | None) -> bool:
    if latest_history is None:
        return False
    status = str(latest_history.get("status") or "").strip().lower()
    if status != "sent":
        return False
    if latest_yellow is None:
        return True
    yellow_ts = latest_yellow["_parsed_ts"]
    history_ts = latest_history["_parsed_ts"]
    return yellow_ts < history_ts


def _has_medical_roster_signal(title: str, body_text: str, signals: set[str]) -> bool:
    if signals.intersection(MEDICAL_ROSTER_SIGNALS):
        return True
    combined = "\n".join(part for part in (title, body_text) if part).strip()
    if not combined:
        return False
    return bool(publish_evaluator.INJURY_ROSTER_SIGNAL_RE.search(combined)) or bool(
        publish_evaluator.DEATH_OR_GRAVE_INCIDENT_RE.search(combined)
    )


def _has_title_body_mismatch(signals: set[str], hard_stop_flags: set[str]) -> bool:
    if any("title_body_mismatch" in signal for signal in signals):
        return True
    return any("title_body_mismatch" in flag for flag in hard_stop_flags)


def _dense_numeric_content(body_text: str) -> bool:
    return len(NUMERIC_TOKEN_RE.findall(body_text)) >= 7


def _has_stale_breaking_signal(signals: set[str], hard_stop_flags: set[str]) -> bool:
    return bool(signals.intersection(STALE_BREAKING_SIGNALS) or hard_stop_flags.intersection(STALE_BREAKING_SIGNALS))


def _has_source_signal(signals: set[str]) -> bool:
    return bool(signals.intersection(SOURCE_RISK_SIGNALS))


def _cleanup_failed(history_entries: Sequence[dict[str, Any]], signals: set[str]) -> bool:
    if "cleanup_failed_post_condition" in signals or "subtype_unresolved_no_resolution" in signals:
        return True
    for entry in history_entries:
        if str(entry.get("hold_reason") or "").strip().lower() == "cleanup_failed_post_condition":
            return True
        if str(entry.get("error") or "").strip().lower() == "subtype_unresolved_no_resolution":
            return True
        if entry.get("cleanup_required") and entry.get("cleanup_success") is False:
            return True
    return False


def _repairable_signal_count(signals: set[str]) -> int:
    keys = {_repairable_key(signal) for signal in signals}
    return len({key for key in keys if key})


def _low_warning_matches(signals: set[str]) -> list[str]:
    matches: list[str] = []
    for signal in sorted(signals):
        normalized = _normalized_signal(signal)
        if normalized in LOW_WARNING_FLAGS:
            matches.append(normalized)
    return matches


def _risk_profile(
    *,
    title: str,
    body_text: str,
    signals: set[str],
    hard_stop_flags: set[str],
    cleanup_failed: bool,
    repairable_signal_count: int,
) -> tuple[str | None, list[str], int]:
    scored_reasons: list[tuple[int, str]] = []

    def add(reason: str, weight: int) -> None:
        if not any(existing_reason == reason for _, existing_reason in scored_reasons):
            scored_reasons.append((weight, reason))

    if _has_medical_roster_signal(title, body_text, signals):
        add("medical_roster_keyword", HIGH_WEIGHT_BY_REASON["medical_roster_keyword"])
    if _has_title_body_mismatch(signals, hard_stop_flags):
        add("title_body_mismatch", HIGH_WEIGHT_BY_REASON["title_body_mismatch"])
    if _dense_numeric_content(body_text):
        add("dense_numeric_content", HIGH_WEIGHT_BY_REASON["dense_numeric_content"])
    for flag in sorted(hard_stop_flags):
        add(f"hard_stop:{flag}", 115 if flag in {"unsupported_named_fact", "obvious_misinformation"} else 105)
    if _has_stale_breaking_signal(signals, hard_stop_flags):
        add("stale_breaking_board", HIGH_WEIGHT_BY_REASON["stale_breaking_board"])

    if _has_source_signal(signals):
        add("source_missing_or_weak", MEDIUM_WEIGHT_BY_REASON["source_missing_or_weak"])
    if "subtype_unresolved" in signals and cleanup_failed:
        add("subtype_unresolved_cleanup_failed", MEDIUM_WEIGHT_BY_REASON["subtype_unresolved_cleanup_failed"])
    if "awkward_role_phrasing" in signals:
        add("awkward_role_phrasing", MEDIUM_WEIGHT_BY_REASON["awkward_role_phrasing"])
    if repairable_signal_count >= 2:
        add("multiple_repairable_flags", MEDIUM_WEIGHT_BY_REASON["multiple_repairable_flags"])

    if not scored_reasons:
        for signal in _low_warning_matches(signals):
            add(signal, LOW_WEIGHT_BY_REASON[signal])

    if not scored_reasons:
        return None, [], 0

    scored_reasons.sort(key=lambda item: (-item[0], item[1]))
    reasons = [reason for _, reason in scored_reasons]
    score = sum(weight for weight, _ in scored_reasons)
    if any(reason.startswith("hard_stop:") for reason in reasons) or any(
        reason in HIGH_WEIGHT_BY_REASON for reason in reasons
    ):
        return "high", reasons, score
    if any(reason in MEDIUM_WEIGHT_BY_REASON for reason in reasons):
        return "medium", reasons, score
    return "low", reasons, score


def route_hallucination_candidates(
    history_rows: Sequence[dict[str, Any]],
    yellow_rows: Sequence[dict[str, Any]],
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    priorities: Sequence[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if int(max_candidates) <= 0:
        raise ValueError("max_candidates must be > 0")
    priority_filter = tuple(priorities or VALID_PRIORITIES)
    if any(priority not in VALID_PRIORITIES for priority in priority_filter):
        raise ValueError(f"priorities must be a subset of {VALID_PRIORITIES}")

    history_by_post_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    yellow_by_post_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in history_rows:
        history_by_post_id[_post_id_from_row(row)].append(row)
    for row in yellow_rows:
        yellow_by_post_id[_post_id_from_row(row)].append(row)

    latest_history = _latest_entry_by_post_id(history_rows)
    latest_yellow = _latest_entry_by_post_id(yellow_rows)
    all_post_ids = sorted(set(history_by_post_id) | set(yellow_by_post_id))

    candidates: list[dict[str, Any]] = []
    for post_id in all_post_ids:
        latest_history_row = latest_history.get(post_id)
        latest_yellow_row = latest_yellow.get(post_id)
        if _is_resolved(latest_history_row, latest_yellow_row):
            continue

        history_entries = history_by_post_id.get(post_id, [])
        yellow_entries = yellow_by_post_id.get(post_id, [])
        entries = [*yellow_entries, *history_entries]
        signals = {signal for entry in entries for signal in _iter_signal_values(entry) if signal}
        hard_stop_flags = {flag for entry in history_entries for flag in _hard_stop_flags_for_row(entry)}
        cleanup_failed = _cleanup_failed(history_entries, signals)
        repairable_signal_count = _repairable_signal_count(signals)
        title = _first_non_empty(yellow_entries, ("title",)) or _first_non_empty(
            history_entries,
            ("title", "summary"),
        )
        body_text = _collect_body_text(entries)
        priority, risk_reasons, score = _risk_profile(
            title=title,
            body_text=body_text,
            signals=signals,
            hard_stop_flags=hard_stop_flags,
            cleanup_failed=cleanup_failed,
            repairable_signal_count=repairable_signal_count,
        )
        if priority is None or priority not in priority_filter:
            continue

        url = _first_non_empty(yellow_entries, ("publish_link", "canonical_url", "url", "link")) or _first_non_empty(
            history_entries,
            ("publish_link", "canonical_url", "url", "link"),
        )
        source_parts = []
        if yellow_entries:
            source_parts.append("yellow_log")
        if history_entries:
            source_parts.append("history")
        latest_ts = max(entry["_parsed_ts"] for entry in entries)
        candidates.append(
            {
                "post_id": post_id,
                "title": title,
                "url": url or _fallback_url(post_id),
                "subtype": _infer_subtype(title, entries),
                "risk_reason": risk_reasons,
                "priority": priority,
                "source": " + ".join(source_parts),
                "next_action": DEFAULT_NEXT_ACTION,
                "recommended_next_action": DEFAULT_NEXT_ACTION,
                "_score": score,
                "_sort_ts": latest_ts.timestamp(),
            }
        )

    candidates.sort(
        key=lambda item: (
            PRIORITY_SORT_ORDER[item["priority"]],
            -int(item["_score"]),
            -float(item["_sort_ts"]),
            -int(item["post_id"]),
        )
    )
    trimmed = candidates[: int(max_candidates)]
    priority_counts = Counter(item["priority"] for item in trimmed)
    for priority in VALID_PRIORITIES:
        priority_counts.setdefault(priority, 0)

    return {
        "router_run_ts": _now_jst(now).isoformat(),
        "total_input": len(all_post_ids),
        "total_candidates": len(trimmed),
        "candidates": [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in trimmed
        ],
        "priority_counts": {priority: int(priority_counts[priority]) for priority in VALID_PRIORITIES},
    }


def build_hallucination_candidate_report(
    *,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    yellow_log_path: str | Path = DEFAULT_YELLOW_LOG_PATH,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    priorities: Sequence[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return route_hallucination_candidates(
        _read_jsonl(history_path),
        _read_jsonl(yellow_log_path),
        max_candidates=max_candidates,
        priorities=priorities,
        now=now,
    )


def dump_hallucination_candidate_report(report: dict[str, Any], *, fmt: str = "json") -> str:
    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if fmt != "tsv":
        raise ValueError("fmt must be json or tsv")

    header = "\t".join(
        (
            "priority",
            "post_id",
            "subtype",
            "title",
            "url",
            "risk_reason",
            "source",
            "next_action",
        )
    )
    lines = [header]
    for candidate in report.get("candidates") or []:
        lines.append(
            "\t".join(
                (
                    str(candidate.get("priority") or ""),
                    str(candidate.get("post_id") or ""),
                    str(candidate.get("subtype") or ""),
                    str(candidate.get("title") or "").replace("\t", " "),
                    str(candidate.get("url") or ""),
                    ",".join(str(reason) for reason in candidate.get("risk_reason") or []),
                    str(candidate.get("source") or ""),
                    str(candidate.get("next_action") or ""),
                )
            )
        )
    return "\n".join(lines) + "\n"
