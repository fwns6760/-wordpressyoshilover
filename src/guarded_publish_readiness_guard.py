from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"


@dataclass(frozen=True)
class ReadinessThresholds:
    sent_refused_ratio_threshold: float = 0.3
    cleanup_failure_streak_warning: int = 5
    hard_stop_imbalance_threshold: float = 0.8
    hard_stop_imbalance_min_sample: int = 5
    daily_cap: int = 100


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


def _read_history_rows(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    history_path = Path(path)
    for line_number, raw_line in enumerate(history_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid history JSONL at {history_path}:{line_number}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"history row must be an object: {history_path}:{line_number}")
        try:
            payload["_parsed_ts"] = _parse_iso_to_jst(payload["ts"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"history row missing valid ts: {history_path}:{line_number}") from exc
        rows.append(payload)
    rows.sort(key=lambda item: item["_parsed_ts"])
    return rows


def _status_count(rows: list[dict[str, Any]], status: str) -> int:
    return sum(1 for row in rows if str(row.get("status") or "").strip().lower() == status)


def _has_cleanup_failed_post_condition(row: dict[str, Any]) -> bool:
    hold_reason = str(row.get("hold_reason") or "").strip().lower()
    error = str(row.get("error") or "").strip().lower()
    return hold_reason == "cleanup_failed_post_condition" or error == "cleanup_failed_post_condition"


def _max_consecutive_cleanup_failures(rows: list[dict[str, Any]]) -> int:
    longest = 0
    current = 0
    for row in rows:
        if _has_cleanup_failed_post_condition(row):
            current += 1
            longest = max(longest, current)
            continue
        current = 0
    return longest


def _current_cleanup_failure_streak(rows: list[dict[str, Any]]) -> int:
    streak = 0
    for row in reversed(rows):
        if not _has_cleanup_failed_post_condition(row):
            break
        streak += 1
    return streak


def _extract_primary_hard_stop_flag(row: dict[str, Any]) -> str | None:
    error = str(row.get("error") or "").strip()
    if error.startswith("hard_stop:"):
        detail = error.split(":", 1)[1]
        for token in detail.split(","):
            flag = token.strip()
            if flag:
                return flag
    hold_reason = str(row.get("hold_reason") or "").strip()
    if hold_reason.startswith("hard_stop_"):
        return hold_reason[len("hard_stop_") :].strip() or None
    return None


def _count_postcheck_failures(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        error = str(row.get("error") or "").strip().lower()
        hold_reason = str(row.get("hold_reason") or "").strip().lower()
        if "postcheck" in error or "postcheck" in hold_reason:
            count += 1
    return count


def _daily_sent_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        if str(row.get("status") or "").strip().lower() != "sent":
            continue
        counts[row["_parsed_ts"].date().isoformat()] += 1
    return counts


def evaluate_guarded_publish_readiness(
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    *,
    window_hours: int = 24,
    now: datetime | None = None,
    thresholds: ReadinessThresholds | None = None,
) -> dict[str, Any]:
    if int(window_hours) <= 0:
        raise ValueError("--window-hours must be > 0")

    limits = thresholds or ReadinessThresholds()
    now_jst = _now_jst(now)
    window_start = now_jst - timedelta(hours=int(window_hours))
    history_rows = _read_history_rows(history_path)
    window_rows = [row for row in history_rows if window_start <= row["_parsed_ts"] <= now_jst]

    sent_count = _status_count(window_rows, "sent")
    refused_count = _status_count(window_rows, "refused")
    skipped_count = _status_count(window_rows, "skipped")
    cleanup_failed_total = sum(1 for row in window_rows if _has_cleanup_failed_post_condition(row))
    cleanup_failed_max_streak = _max_consecutive_cleanup_failures(window_rows)
    cleanup_failed_current_streak = _current_cleanup_failure_streak(window_rows)

    sent_refused_ratio = None if refused_count == 0 else sent_count / refused_count
    flag_counts = Counter(
        flag
        for flag in (_extract_primary_hard_stop_flag(row) for row in window_rows)
        if flag
    )
    hard_stop_total = sum(flag_counts.values())
    dominant_flag = None
    dominant_share = None
    if hard_stop_total:
        dominant_flag, dominant_count = flag_counts.most_common(1)[0]
        dominant_share = dominant_count / hard_stop_total

    daily_sent_by_date = _daily_sent_counts(history_rows)
    today_key = now_jst.date().isoformat()
    today_sent_count = daily_sent_by_date[today_key]
    cap_reached_dates = sorted(day for day, count in daily_sent_by_date.items() if count >= limits.daily_cap)
    next_reset_at = now_jst.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    daily_cap_exhausted = today_sent_count >= limits.daily_cap
    reset_pending = daily_cap_exhausted and now_jst < next_reset_at
    daily_cap_skip_count = sum(
        1
        for row in window_rows
        if str(row.get("hold_reason") or "").strip().lower() == "daily_cap"
        or str(row.get("error") or "").strip().lower() == "daily_cap"
    )
    postcheck_failure_count = _count_postcheck_failures(window_rows)

    status = "ok"
    warnings: list[dict[str, Any]] = []
    recommendations: list[str] = []

    if sent_refused_ratio is not None and sent_refused_ratio < limits.sent_refused_ratio_threshold:
        status = "regression"
        warnings.append(
            {
                "code": "high_refuse_ratio",
                "severity": "regression",
                "message": (
                    f"sent/refused ratio {sent_refused_ratio:.2f} fell below "
                    f"{limits.sent_refused_ratio_threshold:.2f} in the last {int(window_hours)}h."
                ),
            }
        )
        recommendations.append("Pause auto-publish activation and inspect refusal-heavy history before the next ramp.")

    if cleanup_failed_max_streak >= limits.cleanup_failure_streak_warning:
        if status == "ok":
            status = "warning"
        warnings.append(
            {
                "code": "cleanup_failed_post_condition_streak",
                "severity": "warning",
                "message": (
                    f"cleanup_failed_post_condition hit a max streak of {cleanup_failed_max_streak} "
                    f"(threshold {limits.cleanup_failure_streak_warning})."
                ),
            }
        )
        recommendations.append("Review cleanup rescue rules and the affected yellow candidates before another burst.")

    if (
        dominant_share is not None
        and dominant_flag is not None
        and hard_stop_total >= limits.hard_stop_imbalance_min_sample
        and dominant_share >= limits.hard_stop_imbalance_threshold
    ):
        if status == "ok":
            status = "warning"
        warnings.append(
            {
                "code": "hard_stop_flag_imbalance",
                "severity": "warning",
                "message": (
                    f"hard_stop flag {dominant_flag} accounts for {dominant_share:.1%} "
                    f"of windowed hard_stop rows."
                ),
                "flag": dominant_flag,
            }
        )
        recommendations.append(
            f"Re-audit the dominant hard_stop flag '{dominant_flag}' to confirm it is an intended safety gate."
        )

    if postcheck_failure_count > 0:
        if status == "ok":
            status = "warning"
        warnings.append(
            {
                "code": "postcheck_failures_visible",
                "severity": "warning",
                "message": f"Detected {postcheck_failure_count} postcheck-related failure rows in the window.",
            }
        )
        recommendations.append("Inspect postcheck-related failures before increasing live publish burst size.")

    if daily_cap_exhausted:
        recommendations.append(f"Wait for the next JST reset at {next_reset_at.isoformat()} before resuming live ramp.")

    if not recommendations:
        recommendations.append("Window looks stable; continue read-only monitoring before the next live decision.")

    metrics = {
        "history_path": str(Path(history_path)),
        "window_hours": int(window_hours),
        "window_start": window_start.isoformat(),
        "window_end": now_jst.isoformat(),
        "history_row_count": len(history_rows),
        "window_row_count": len(window_rows),
        "sent_count": sent_count,
        "refused_count": refused_count,
        "skipped_count": skipped_count,
        "sent_refused_ratio": sent_refused_ratio,
        "cleanup_failed_post_condition_total": cleanup_failed_total,
        "cleanup_failed_post_condition_max_streak": cleanup_failed_max_streak,
        "cleanup_failed_post_condition_current_streak": cleanup_failed_current_streak,
        "hard_stop_total": hard_stop_total,
        "hard_stop_flag_counts": dict(sorted(flag_counts.items())),
        "hard_stop_dominant_flag": dominant_flag,
        "hard_stop_dominant_share": dominant_share,
        "daily_cap": {
            "cap": limits.daily_cap,
            "today_sent_count": today_sent_count,
            "exhausted": daily_cap_exhausted,
            "reset_pending": reset_pending,
            "next_reset_at": next_reset_at.isoformat(),
            "cap_reached_dates": cap_reached_dates,
            "window_daily_cap_skip_count": daily_cap_skip_count,
        },
        "postcheck_failure_count": postcheck_failure_count,
    }
    return {
        "status": status,
        "metrics": metrics,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def render_human_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    daily_cap = metrics["daily_cap"]
    ratio = metrics["sent_refused_ratio"]
    ratio_text = "n/a" if ratio is None else f"{ratio:.2f}"
    dominant_flag = metrics["hard_stop_dominant_flag"] or "n/a"
    dominant_share = metrics["hard_stop_dominant_share"]
    dominant_share_text = "n/a" if dominant_share is None else f"{dominant_share:.1%}"

    lines = [
        "Guarded Publish Readiness Guard",
        f"status={report['status']}",
        (
            f"window={metrics['window_hours']}h  start={metrics['window_start']}  "
            f"end={metrics['window_end']}"
        ),
        f"history_path={metrics['history_path']}",
        "",
        (
            "summary: "
            f"sent={metrics['sent_count']} refused={metrics['refused_count']} skipped={metrics['skipped_count']} "
            f"sent/refused={ratio_text}"
        ),
        (
            "cleanup_failed_post_condition: "
            f"total={metrics['cleanup_failed_post_condition_total']} "
            f"max_streak={metrics['cleanup_failed_post_condition_max_streak']} "
            f"current_streak={metrics['cleanup_failed_post_condition_current_streak']}"
        ),
        (
            "hard_stop: "
            f"total={metrics['hard_stop_total']} dominant={dominant_flag} share={dominant_share_text}"
        ),
        (
            "daily_cap: "
            f"today_sent={daily_cap['today_sent_count']}/{daily_cap['cap']} "
            f"exhausted={daily_cap['exhausted']} reset_pending={daily_cap['reset_pending']}"
        ),
        f"postcheck_failures={metrics['postcheck_failure_count']}",
        "",
        "Warnings",
    ]
    if not report["warnings"]:
        lines.append("- none")
    else:
        for warning in report["warnings"]:
            lines.append(f"- {warning['code']} :: {warning['message']}")

    lines.extend(["", "Recommendations"])
    for item in report["recommendations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def dump_report(report: dict[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


__all__ = [
    "DEFAULT_HISTORY_PATH",
    "ReadinessThresholds",
    "dump_report",
    "evaluate_guarded_publish_readiness",
    "render_human_report",
]
