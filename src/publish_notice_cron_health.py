"""Dry-run health checks for the publish-notice cron path."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_CRON_STALE_AFTER_MINUTES = 90
DEFAULT_HISTORY_TOO_LONG_ENTRIES = 1000
DEFAULT_HISTORY_TOO_OLD_DAYS = 7
DEFAULT_DUPLICATE_SKIP_SHARE_THRESHOLD = 0.95
DEFAULT_WP_URL = "https://yoshilover.com"
_RECENT_WINDOW = timedelta(hours=24)
_SCAN_RE = re.compile(
    r"^\[scan\]\s+emitted=(?P<emitted>\d+)\s+skipped=(?P<skipped>\d+)\s+cursor_before=(?P<before>\S+)\s+cursor_after=(?P<after>\S+)"
)
_STATUS_RE = re.compile(r"\bstatus=(?P<status>[A-Za-z_]+)")
_REASON_RE = re.compile(r"\breason=(?P<reason>\S+)")
_MESSAGE_RE = re.compile(r"\bmessage=(?P<message>.*)$")
_SKIP_RE = re.compile(r"^\[skip\]\s+post_id=(?P<post_id>\S+)\s+reason=(?P<reason>\S+)")
_CREDENTIAL_TOKENS = (
    "credential",
    "app password",
    "gmail app password",
    "mail_bridge_gmail_app_password",
    "smtp username",
    "mail_bridge_smtp_username",
)


class PublishNoticeHealthError(RuntimeError):
    """Raised when health inputs cannot be parsed."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CronLogAnalysis:
    last_tick_ts: str | None
    last_tick_age_min: int | None
    last_emit_count: int
    last_send_count: int
    last_skip_count: int
    verdict: str
    last_skip_reasons: dict[str, int]
    last_error_messages: list[str]
    last_status_counts: dict[str, int]


RunCommand = Callable[[Sequence[str]], CommandResult]
FetchPublishCount = Callable[[datetime], int]


def _coerce_now(now: Callable[[], datetime] | datetime | None = None) -> datetime:
    if callable(now):
        current = now()
    elif isinstance(now, datetime):
        current = now
    else:
        current = datetime.now(JST)
    if current.tzinfo is None:
        return current.replace(tzinfo=JST)
    return current.astimezone(JST)


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _parse_iso_to_jst(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        current = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if current.tzinfo is None:
        return current.replace(tzinfo=JST)
    return current.astimezone(JST)


def _isoformat_jst(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=JST).isoformat()
    return value.astimezone(JST).isoformat()


def _default_run_command(argv: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _resolve_wp_url(wp_url: str | None = None) -> str:
    if wp_url is not None and str(wp_url).strip():
        return str(wp_url).strip().rstrip("/")
    env_url = str(os.environ.get("WP_URL", "")).strip()
    if env_url:
        return env_url.rstrip("/")
    return DEFAULT_WP_URL


def _build_posts_endpoint(wp_url: str | None = None) -> str:
    return f"{_resolve_wp_url(wp_url)}/wp-json/wp/v2/posts"


def _fetch_publish_count_from_wp(after_dt: datetime, *, wp_url: str | None = None) -> int:
    endpoint = _build_posts_endpoint(wp_url)
    page = 1
    total = 0

    while True:
        response = requests.get(
            endpoint,
            params={
                "status": "publish",
                "after": after_dt.isoformat(),
                "per_page": 100,
                "page": page,
                "orderby": "date",
                "order": "desc",
                "_fields": "id",
            },
            timeout=30,
        )
        response.raise_for_status()

        total_header = str(response.headers.get("X-WP-Total", "")).strip()
        if total_header.isdigit():
            return int(total_header)

        payload = response.json()
        if not isinstance(payload, list):
            raise PublishNoticeHealthError("publish recent response must be a list")
        total += len(payload)
        if len(payload) < 100:
            return total
        page += 1


def check_cron_daemon(
    *,
    crontab_marker: str,
    run_command: RunCommand = _default_run_command,
) -> dict[str, Any]:
    systemctl = run_command(["systemctl", "is-active", "cron"])
    active = systemctl.returncode == 0 and systemctl.stdout.strip().lower() == "active"

    crontab = run_command(["crontab", "-l"])
    crontab_line_present = str(crontab_marker or "") in crontab.stdout

    if not active:
        verdict = "stopped"
    elif not crontab_line_present:
        verdict = "crontab_missing"
    else:
        verdict = "ok"

    return {
        "active": active,
        "crontab_line_present": crontab_line_present,
        "verdict": verdict,
    }


def check_publish_recent(
    *,
    now: Callable[[], datetime] | datetime | None = None,
    fetch_publish_count: FetchPublishCount | None = None,
    wp_url: str | None = None,
) -> dict[str, Any]:
    current_now = _coerce_now(now)
    after_dt = current_now - _RECENT_WINDOW
    fetcher = fetch_publish_count or (lambda after: _fetch_publish_count_from_wp(after, wp_url=wp_url))
    publishes_last_24h = int(fetcher(after_dt))
    return {
        "publishes_last_24h": publishes_last_24h,
        "verdict": "active" if publishes_last_24h > 0 else "idle",
    }


def _parse_cron_log(path: Path, *, now: datetime, stale_after_minutes: int) -> CronLogAnalysis:
    if not path.exists():
        return CronLogAnalysis(
            last_tick_ts=None,
            last_tick_age_min=None,
            last_emit_count=0,
            last_send_count=0,
            last_skip_count=0,
            verdict="no_log",
            last_skip_reasons={},
            last_error_messages=[],
            last_status_counts={},
        )

    lines = path.read_text(encoding="utf-8").splitlines()
    current_block: dict[str, Any] | None = None
    last_block: dict[str, Any] | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        scan_match = _SCAN_RE.match(line)
        if scan_match:
            current_block = {
                "emitted": int(scan_match.group("emitted")),
                "skipped": int(scan_match.group("skipped")),
                "sent": 0,
                "skip_reasons": Counter(),
                "status_counts": Counter(),
                "error_messages": [],
            }
            last_block = current_block
            continue

        if current_block is None:
            continue

        skip_match = _SKIP_RE.match(line)
        if skip_match:
            current_block["skip_reasons"][skip_match.group("reason")] += 1
            continue

        status_match = _STATUS_RE.search(line)
        if not status_match:
            continue
        status = status_match.group("status")
        current_block["status_counts"][status] += 1
        if status == "sent":
            current_block["sent"] += 1
        if status == "error":
            message_match = _MESSAGE_RE.search(line)
            if message_match:
                current_block["error_messages"].append(message_match.group("message").strip())

    if last_block is None:
        return CronLogAnalysis(
            last_tick_ts=None,
            last_tick_age_min=None,
            last_emit_count=0,
            last_send_count=0,
            last_skip_count=0,
            verdict="no_log",
            last_skip_reasons={},
            last_error_messages=[],
            last_status_counts={},
        )

    mtime = datetime.fromtimestamp(path.stat().st_mtime, JST)
    age_min = max(0, int((now - mtime).total_seconds() // 60))
    verdict = "stale_log" if age_min > stale_after_minutes else "ok"
    skip_reasons = dict(last_block["skip_reasons"])
    return CronLogAnalysis(
        last_tick_ts=mtime.isoformat(),
        last_tick_age_min=age_min,
        last_emit_count=int(last_block["emitted"]),
        last_send_count=int(last_block["sent"]),
        last_skip_count=max(int(last_block["skipped"]), sum(skip_reasons.values())),
        verdict=verdict,
        last_skip_reasons=skip_reasons,
        last_error_messages=list(last_block["error_messages"]),
        last_status_counts=dict(last_block["status_counts"]),
    )


def check_cron_log_recent(
    *,
    cron_log_path: str | Path,
    now: Callable[[], datetime] | datetime | None = None,
    stale_after_minutes: int = DEFAULT_CRON_STALE_AFTER_MINUTES,
) -> dict[str, Any]:
    analysis = _parse_cron_log(_path(cron_log_path), now=_coerce_now(now), stale_after_minutes=stale_after_minutes)
    return {
        "last_tick_ts": analysis.last_tick_ts,
        "last_tick_age_min": analysis.last_tick_age_min,
        "last_emit_count": analysis.last_emit_count,
        "last_send_count": analysis.last_send_count,
        "last_skip_count": analysis.last_skip_count,
        "verdict": analysis.verdict,
    }


def _load_queue_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _within_recent_window(recorded_at: Any, *, now: datetime) -> bool:
    parsed = _parse_iso_to_jst(recorded_at)
    if parsed is None:
        return False
    return now - parsed <= _RECENT_WINDOW


def _matches_credential_issue(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return any(token in lowered for token in _CREDENTIAL_TOKENS)


def _classify_smtp_verdict(
    *,
    suppressed_reasons: Counter[str],
    last_error_messages: Iterable[str],
    smtp_error_count: int,
) -> str:
    normalized_reasons = {str(reason or "").strip(): count for reason, count in suppressed_reasons.items() if count > 0}
    if normalized_reasons.get("NO_RECIPIENT", 0) > 0:
        return "no_recipient"
    if any(_matches_credential_issue(reason) for reason in normalized_reasons):
        return "credential_missing"
    if any(_matches_credential_issue(message) for message in last_error_messages):
        return "credential_missing"
    if smtp_error_count > 0:
        return "smtp_error"
    unexpected_suppressed = any(reason not in {"", "NO_RECIPIENT"} for reason in normalized_reasons)
    if unexpected_suppressed:
        return "smtp_error"
    return "ok"


def _load_history(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublishNoticeHealthError("publish notice history must be a JSON object")
    return {str(key): str(value) for key, value in payload.items()}


def check_smtp_send_health(
    *,
    queue_path: str | Path,
    cron_log_analysis: CronLogAnalysis,
    now: Callable[[], datetime] | datetime | None = None,
) -> dict[str, Any]:
    current_now = _coerce_now(now)
    recent_entries = [
        entry
        for entry in _load_queue_entries(_path(queue_path))
        if _within_recent_window(entry.get("recorded_at"), now=current_now)
    ]

    sent_24h = 0
    suppressed_24h = 0
    suppressed_reasons: Counter[str] = Counter()
    smtp_error_24h = int(cron_log_analysis.last_status_counts.get("error", 0))

    for entry in recent_entries:
        status = str(entry.get("status") or "").strip()
        if status == "sent":
            sent_24h += 1
        elif status == "suppressed":
            suppressed_24h += 1
            suppressed_reasons[str(entry.get("reason") or "").strip()] += 1
        elif status == "error":
            smtp_error_24h += 1

    verdict = _classify_smtp_verdict(
        suppressed_reasons=suppressed_reasons,
        last_error_messages=cron_log_analysis.last_error_messages,
        smtp_error_count=smtp_error_24h,
    )
    return {
        "sent_24h": sent_24h,
        "suppressed_24h": suppressed_24h,
        "suppressed_reasons": dict(sorted(suppressed_reasons.items())),
        "smtp_error_24h": smtp_error_24h,
        "verdict": verdict,
    }


def check_history_dedup_health(
    *,
    history_path: str | Path,
    cron_log_analysis: CronLogAnalysis,
    now: Callable[[], datetime] | datetime | None = None,
    too_long_entries: int = DEFAULT_HISTORY_TOO_LONG_ENTRIES,
    too_old_days: int = DEFAULT_HISTORY_TOO_OLD_DAYS,
    duplicate_skip_share_threshold: float = DEFAULT_DUPLICATE_SKIP_SHARE_THRESHOLD,
) -> dict[str, Any]:
    current_now = _coerce_now(now)
    history = _load_history(_path(history_path))
    parsed_entries = [
        parsed
        for parsed in (_parse_iso_to_jst(value) for value in history.values())
        if parsed is not None
    ]
    oldest = min(parsed_entries) if parsed_entries else None
    age_days = 0
    if oldest is not None:
        age_days = max(0, int((current_now - oldest).total_seconds() // 86400))

    duplicate_skip_24h = int(cron_log_analysis.last_skip_reasons.get("RECENT_DUPLICATE", 0))
    denominator = cron_log_analysis.last_emit_count + duplicate_skip_24h
    duplicate_skip_share = (duplicate_skip_24h / denominator) if denominator else 0.0

    verdict = "ok"
    if duplicate_skip_24h > 0 and duplicate_skip_share >= duplicate_skip_share_threshold:
        verdict = "all_duplicate_skip"
    elif len(history) > too_long_entries or age_days > too_old_days:
        verdict = "history_too_long"

    return {
        "history_entries_total": len(history),
        "history_oldest_ts": _isoformat_jst(oldest),
        "history_age_days": age_days,
        "duplicate_skip_24h": duplicate_skip_24h,
        "duplicate_skip_share": round(duplicate_skip_share, 4),
        "verdict": verdict,
    }


def check_env_presence_only() -> dict[str, bool]:
    return {
        "MAIL_BRIDGE_TO_set": bool(str(os.environ.get("MAIL_BRIDGE_TO", "")).strip()),
        "MAIL_BRIDGE_GMAIL_APP_PASSWORD_set": bool(str(os.environ.get("MAIL_BRIDGE_GMAIL_APP_PASSWORD", "")).strip()),
        "MAIL_BRIDGE_SMTP_USERNAME_set": bool(str(os.environ.get("MAIL_BRIDGE_SMTP_USERNAME", "")).strip()),
        "MAIL_BRIDGE_FROM_set": bool(str(os.environ.get("MAIL_BRIDGE_FROM", "")).strip()),
    }


def determine_overall_verdict(snapshot: dict[str, Any]) -> str:
    cron_daemon = snapshot["cron_daemon"]
    publish_recent = snapshot["publish_recent"]
    cron_log_recent = snapshot["cron_log_recent"]
    smtp_send_health = snapshot["smtp_send_health"]
    history_dedup_health = snapshot["history_dedup_health"]

    if cron_daemon["verdict"] != "ok":
        return "stopped"
    if cron_log_recent["verdict"] != "ok":
        return "investigate"
    if history_dedup_health["verdict"] == "all_duplicate_skip":
        return "dedup_misjudgment"

    if smtp_send_health["verdict"] in {"smtp_error", "no_recipient", "credential_missing"}:
        if (
            cron_log_recent["last_emit_count"] > 0
            or smtp_send_health["suppressed_24h"] > 0
            or smtp_send_health["smtp_error_24h"] > 0
            or publish_recent["verdict"] == "active"
        ):
            return "smtp_failure"

    if history_dedup_health["verdict"] == "history_too_long":
        return "investigate"

    if (
        publish_recent["verdict"] == "idle"
        and cron_log_recent["last_emit_count"] == 0
        and smtp_send_health["suppressed_24h"] == 0
        and smtp_send_health["smtp_error_24h"] == 0
    ):
        return "no_publish"

    return "healthy"


def build_overall_summary(snapshot: dict[str, Any]) -> str:
    verdict = snapshot["overall_verdict"]
    if verdict == "healthy":
        return "recent publish-notice signals look healthy"
    if verdict == "stopped":
        return "cron daemon or crontab marker needs recovery"
    if verdict == "no_publish":
        return "cron is alive and no recent publish candidates were found"
    if verdict == "smtp_failure":
        return "mail delivery path needs attention"
    if verdict == "dedup_misjudgment":
        return "history dedup likely skipped all recent candidates"
    return "manual investigation is required"


def collect_publish_notice_cron_health(
    *,
    cron_log_path: str | Path,
    queue_path: str | Path,
    history_path: str | Path,
    crontab_marker: str,
    now: Callable[[], datetime] | datetime | None = None,
    run_command: RunCommand = _default_run_command,
    fetch_publish_count: FetchPublishCount | None = None,
    wp_url: str | None = None,
    stale_after_minutes: int = DEFAULT_CRON_STALE_AFTER_MINUTES,
) -> dict[str, Any]:
    current_now = _coerce_now(now)
    cron_daemon = check_cron_daemon(crontab_marker=crontab_marker, run_command=run_command)
    publish_recent = check_publish_recent(now=current_now, fetch_publish_count=fetch_publish_count, wp_url=wp_url)
    cron_log_analysis = _parse_cron_log(
        _path(cron_log_path),
        now=current_now,
        stale_after_minutes=stale_after_minutes,
    )
    cron_log_recent = {
        "last_tick_ts": cron_log_analysis.last_tick_ts,
        "last_tick_age_min": cron_log_analysis.last_tick_age_min,
        "last_emit_count": cron_log_analysis.last_emit_count,
        "last_send_count": cron_log_analysis.last_send_count,
        "last_skip_count": cron_log_analysis.last_skip_count,
        "verdict": cron_log_analysis.verdict,
    }
    smtp_send_health = check_smtp_send_health(
        queue_path=queue_path,
        cron_log_analysis=cron_log_analysis,
        now=current_now,
    )
    history_dedup_health = check_history_dedup_health(
        history_path=history_path,
        cron_log_analysis=cron_log_analysis,
        now=current_now,
    )
    env_presence_only = check_env_presence_only()

    snapshot = {
        "ts": current_now.isoformat(),
        "cron_daemon": cron_daemon,
        "publish_recent": publish_recent,
        "cron_log_recent": cron_log_recent,
        "smtp_send_health": smtp_send_health,
        "history_dedup_health": history_dedup_health,
        "env_presence_only": env_presence_only,
    }
    snapshot["overall_verdict"] = determine_overall_verdict(snapshot)
    snapshot["overall_summary"] = build_overall_summary(snapshot)
    return snapshot


def render_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _flag(value: bool) -> str:
    return "set" if value else "unset"


def render_human(snapshot: dict[str, Any]) -> str:
    cron_daemon = snapshot["cron_daemon"]
    publish_recent = snapshot["publish_recent"]
    cron_log_recent = snapshot["cron_log_recent"]
    smtp_send_health = snapshot["smtp_send_health"]
    history_dedup_health = snapshot["history_dedup_health"]
    env_presence_only = snapshot["env_presence_only"]
    last_tick_text = cron_log_recent["last_tick_ts"] or "n/a"
    age_text = "n/a" if cron_log_recent["last_tick_age_min"] is None else f"{cron_log_recent['last_tick_age_min']} min"

    lines = [
        f"publish-notice cron health check  ts={snapshot['ts']}",
        "",
        f"(a) cron daemon:        {cron_daemon['verdict']:<15} (systemd active={cron_daemon['active']}, crontab marker present={cron_daemon['crontab_line_present']})",
        f"(b) publish recent:     {publish_recent['verdict']:<15} (publishes_last_24h={publish_recent['publishes_last_24h']})",
        f"(c) cron log recent:    {cron_log_recent['verdict']:<15} (last tick {last_tick_text}, age {age_text}, emitted={cron_log_recent['last_emit_count']}, sent={cron_log_recent['last_send_count']}, skipped={cron_log_recent['last_skip_count']})",
        f"(d) smtp send health:   {smtp_send_health['verdict']:<15} (sent_24h={smtp_send_health['sent_24h']}, suppressed_24h={smtp_send_health['suppressed_24h']}, smtp_error_24h={smtp_send_health['smtp_error_24h']})",
        f"(e) history dedup:      {history_dedup_health['verdict']:<15} (entries={history_dedup_health['history_entries_total']}, age={history_dedup_health['history_age_days']}d, duplicate_skip_share={history_dedup_health['duplicate_skip_share']:.2f})",
        f"(f) env presence:       MAIL_BRIDGE_TO={_flag(env_presence_only['MAIL_BRIDGE_TO_set'])} / GMAIL_APP_PASSWORD={_flag(env_presence_only['MAIL_BRIDGE_GMAIL_APP_PASSWORD_set'])} / SMTP_USERNAME={_flag(env_presence_only['MAIL_BRIDGE_SMTP_USERNAME_set'])} / FROM={_flag(env_presence_only['MAIL_BRIDGE_FROM_set'])}",
        "                        (実値は表示しない)",
        "",
        f"overall_verdict: {snapshot['overall_verdict']} ({snapshot['overall_summary']})",
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "CommandResult",
    "CronLogAnalysis",
    "DEFAULT_CRON_STALE_AFTER_MINUTES",
    "JST",
    "PublishNoticeHealthError",
    "build_overall_summary",
    "check_cron_daemon",
    "check_cron_log_recent",
    "check_env_presence_only",
    "check_history_dedup_health",
    "check_publish_recent",
    "check_smtp_send_health",
    "collect_publish_notice_cron_health",
    "determine_overall_verdict",
    "render_human",
    "render_json",
]
