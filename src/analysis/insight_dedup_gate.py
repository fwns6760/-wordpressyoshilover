"""DATA-INSIGHT duplicate cooldown gate.

This module keeps the duplicate decision in one place.  It uses the existing
``article_candidates`` table as a small publish ledger, so no schema migration
is needed.
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import insight_whitelist as _wl  # noqa: E402


SIGNAL_DEDUP_HISTORY = "data_insight_dedup_history"
DEFAULT_COOLDOWN_DAYS = 7
DEFAULT_DELTA_RATIO = 0.05
DEFAULT_RANK_BANDS = (1, 5, 10, 30)
DEFAULT_SCOPE_FAMILY = "metric_all_periods"
LEDGER_STATUSES = ("DRAFTED", "PUBLISHED")
DEFAULT_PLAYER_DAILY_CAP = 2
TEAM_SUBJECT_PREFIX = "team:"
JST = dt.timezone(dt.timedelta(hours=9))


def _dedup_config() -> dict[str, Any]:
    cfg = _wl.load_whitelist_config() or {}
    return cfg.get("dedup", {}) if isinstance(cfg.get("dedup", {}), dict) else {}


def cooldown_days() -> int:
    cfg = _dedup_config()
    return int(cfg.get("cooldown_days", DEFAULT_COOLDOWN_DAYS) or DEFAULT_COOLDOWN_DAYS)


def delta_ratio() -> float:
    cfg = _dedup_config()
    return float(cfg.get("delta_ratio", DEFAULT_DELTA_RATIO) or DEFAULT_DELTA_RATIO)


def rank_bands() -> tuple[int, ...]:
    cfg = _dedup_config()
    raw = cfg.get("rank_bands", DEFAULT_RANK_BANDS)
    try:
        bands = tuple(sorted(int(x) for x in raw))
    except (TypeError, ValueError):
        bands = DEFAULT_RANK_BANDS
    return bands or DEFAULT_RANK_BANDS


def scope_family_for(_scope: Optional[str]) -> str:
    cfg = _dedup_config()
    return str(cfg.get("scope_family") or DEFAULT_SCOPE_FAMILY)


def player_daily_cap() -> int:
    cfg = _dedup_config()
    raw = cfg.get("player_daily_cap", DEFAULT_PLAYER_DAILY_CAP)
    try:
        cap = int(raw)
    except (TypeError, ValueError):
        cap = DEFAULT_PLAYER_DAILY_CAP
    return cap if cap > 0 else DEFAULT_PLAYER_DAILY_CAP


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_ts(value: Any) -> Optional[dt.datetime]:
    if not value:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _kv_blob(**items: Any) -> str:
    parts = []
    for key, value in items.items():
        if value is None:
            continue
        text = str(value).replace(" ", "_")
        parts.append(f"{key}={text}")
    return " ".join(parts)


def _parse_kv(blob: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(blob or "").split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key:
            out[key] = value
    return out


def parse_first_number(text: Any, *, preferred_key: Optional[str] = None) -> Optional[float]:
    raw = str(text or "")
    if preferred_key:
        m = re.search(rf"\b{re.escape(preferred_key)}=([-+]?\d+(?:\.\d+)?)", raw)
        if m:
            return float(m.group(1))
    m = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    return float(m.group(0)) if m else None


def parse_rank(text: Any) -> Optional[int]:
    raw = str(text or "")
    m = re.search(r"\brank=([0-9]+)", raw)
    if not m:
        m = re.search(r"\brank\s+([0-9]+)", raw)
    return int(m.group(1)) if m else None


def rank_band(rank: Optional[int], total: Optional[int] = None) -> str:
    """順位 → band。spec(data-insight.md)の絶対順位 band [1,5,10,30] に統一。

    旧実装は total があると percentile 判定だったが、total=30 で rank 3(10%)↔4(13%)
    が 10% 境界をまたいで band 反転 → 7日 cooldown をすり抜けて連日 publish される
    事故源(大城 対右投手 rank 3→4→6 で 5/31・6/2 連日掲載)だった。絶対 band なら
    rank 3,4 はともに top_5 で同一 band となり、値変化 <5% は cooldown でブロックされる。
    ``total`` は署名互換のため残すが band 判定には用いない。
    """
    if not rank or rank <= 0:
        return "unknown"
    for boundary in rank_bands():
        if rank <= boundary:
            return f"top_{boundary}"
    return "field"


def _history_window_label(metric_name: str, scope_family: str) -> str:
    return f"dedup:{metric_name}:{scope_family}"


def _ensure_run(conn: sqlite3.Connection, run_id: str) -> None:
    existing = conn.execute(
        "SELECT 1 FROM insight_runs WHERE run_id = ? LIMIT 1", (run_id,),
    ).fetchone()
    if existing:
        return
    now_iso = _now_utc().isoformat()
    conn.execute(
        "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, "
        "n_candidates, notes) VALUES (?, ?, NULL, NULL, 0, ?)",
        (run_id, now_iso, "data-insight dedup history"),
    )


def _jst_day_bounds_utc(now_utc: dt.datetime) -> tuple[str, str]:
    """Return [start, end) ISO timestamps (UTC) covering the JST calendar day of ``now_utc``."""
    jst_date = now_utc.astimezone(JST).date()
    start_jst = dt.datetime.combine(jst_date, dt.time(0, 0), tzinfo=JST)
    end_jst = start_jst + dt.timedelta(days=1)
    return start_jst.astimezone(dt.timezone.utc).isoformat(), end_jst.astimezone(dt.timezone.utc).isoformat()


def _count_subject_publishes_today(
    conn: sqlite3.Connection,
    *,
    subject_key: str,
    now_utc: dt.datetime,
) -> int:
    """Count today's (JST) DRAFTED+PUBLISHED dedup history rows for the subject across all metrics."""
    start_iso, end_iso = _jst_day_bounds_utc(now_utc)
    placeholders = ",".join("?" * len(LEDGER_STATUSES))
    row = conn.execute(
        f"SELECT COUNT(*) FROM article_candidates "
        f"WHERE signal_type = ? AND player_canonical = ? "
        f"AND status IN ({placeholders}) "
        f"AND created_at >= ? AND created_at < ?",
        (SIGNAL_DEDUP_HISTORY, subject_key, *LEDGER_STATUSES, start_iso, end_iso),
    ).fetchone()
    return int(row[0]) if row else 0


def _latest_history(
    conn: sqlite3.Connection,
    *,
    subject_key: str,
    metric_name: str,
    scope_family: str,
) -> Optional[dict[str, Any]]:
    placeholders = ",".join("?" * len(LEDGER_STATUSES))
    row = conn.execute(
        f"SELECT candidate_id, current_value, created_at, notes, status "
        f"FROM article_candidates "
        f"WHERE signal_type = ? AND player_canonical = ? AND window_label = ? "
        f"AND status IN ({placeholders}) "
        f"ORDER BY created_at DESC, candidate_id DESC LIMIT 1",
        (
            SIGNAL_DEDUP_HISTORY,
            subject_key,
            _history_window_label(metric_name, scope_family),
            *LEDGER_STATUSES,
        ),
    ).fetchone()
    if not row:
        return None
    cols = ("candidate_id", "current_value", "created_at", "notes", "status")
    return dict(zip(cols, row))


def evaluate_metric_cooldown(
    conn: sqlite3.Connection,
    *,
    subject_key: str,
    metric_name: str,
    scope: str,
    value: Optional[float] = None,
    rank: Optional[int] = None,
    total: Optional[int] = None,
    now: Optional[dt.datetime] = None,
    cooldown_days_value: Optional[int] = None,
    delta_ratio_value: Optional[float] = None,
    scope_family: Optional[str] = None,
) -> dict[str, Any]:
    """Return an allow/block decision for a subject + metric.

    Inside the cooldown, the candidate is allowed only when the value changed
    enough or the rank band changed.  Scope is intentionally collapsed by
    default, because week/month/season versions of the same metric should not
    all publish together.
    """
    subject = (subject_key or "").strip()
    metric = (metric_name or "").strip()
    if not subject or not metric:
        return {"allowed": True, "reason": "missing_dedup_key"}
    family = scope_family or scope_family_for(scope)
    current_band = rank_band(rank, total)
    now_dt = (now or _now_utc()).astimezone(dt.timezone.utc)
    now_jst_date = now_dt.astimezone(JST).date()

    # Per-player daily cap (Type B): skip for team-level subjects since each
    # team metric is independent (cap C is handled by same-day block below).
    if not subject.startswith(TEAM_SUBJECT_PREFIX):
        cap = player_daily_cap()
        today_count = _count_subject_publishes_today(
            conn, subject_key=subject, now_utc=now_dt,
        )
        if today_count >= cap:
            return {
                "allowed": False,
                "reason": "player_daily_cap",
                "today_count": today_count,
                "cap": cap,
                "scope_family": family,
                "current_band": current_band,
            }

    previous = _latest_history(
        conn, subject_key=subject, metric_name=metric, scope_family=family,
    )
    if previous is None:
        return {
            "allowed": True,
            "reason": "no_history",
            "scope_family": family,
            "current_band": current_band,
        }

    prev_ts = _parse_ts(previous.get("created_at"))
    cd_days = cooldown_days_value if cooldown_days_value is not None else cooldown_days()
    if prev_ts is None:
        return {
            "allowed": False,
            "reason": "cooldown_recent_unknown_timestamp",
            "previous_candidate_id": previous.get("candidate_id"),
            "scope_family": family,
            "current_band": current_band,
        }

    # Same JST calendar day for same subject+metric: hard block regardless of
    # value_delta / rank_band bypass. Catches Type A (player same-day dup) and
    # Type C (team ranking same-day dup, e.g. TEAM_ERA twice on 5/21).
    prev_jst_date = prev_ts.astimezone(JST).date()
    if prev_jst_date == now_jst_date:
        return {
            "allowed": False,
            "reason": "same_day_block",
            "previous_candidate_id": previous.get("candidate_id"),
            "scope_family": family,
            "current_band": current_band,
        }

    age_days = (now_dt - prev_ts).total_seconds() / 86400.0
    if age_days >= cd_days:
        return {
            "allowed": True,
            "reason": "cooldown_expired",
            "age_days": round(age_days, 3),
            "previous_candidate_id": previous.get("candidate_id"),
            "scope_family": family,
            "current_band": current_band,
        }

    prev_kv = _parse_kv(previous.get("current_value"))
    prev_value = parse_first_number(prev_kv.get("value"))
    prev_band = prev_kv.get("rank_band") or "unknown"
    ratio = delta_ratio_value if delta_ratio_value is not None else delta_ratio()
    if value is not None and prev_value is not None:
        diff = abs(float(value) - float(prev_value))
        threshold = max(abs(float(prev_value)) * ratio, ratio if prev_value == 0 else 0.0)
        if diff >= threshold:
            return {
                "allowed": True,
                "reason": "value_delta",
                "delta": round(diff, 6),
                "delta_threshold": round(threshold, 6),
                "age_days": round(age_days, 3),
                "previous_candidate_id": previous.get("candidate_id"),
                "scope_family": family,
                "previous_band": prev_band,
                "current_band": current_band,
            }
    if current_band != "unknown" and prev_band != "unknown" and current_band != prev_band:
        return {
            "allowed": True,
            "reason": "rank_band_changed",
            "age_days": round(age_days, 3),
            "previous_candidate_id": previous.get("candidate_id"),
            "scope_family": family,
            "previous_band": prev_band,
            "current_band": current_band,
        }
    return {
        "allowed": False,
        "reason": "cooldown_active",
        "age_days": round(age_days, 3),
        "cooldown_days": cd_days,
        "previous_candidate_id": previous.get("candidate_id"),
        "scope_family": family,
        "previous_band": prev_band,
        "current_band": current_band,
    }


def record_metric_publish(
    conn: sqlite3.Connection,
    *,
    subject_key: str,
    metric_name: str,
    scope: str,
    value: Optional[float] = None,
    rank: Optional[int] = None,
    total: Optional[int] = None,
    title: str = "",
    post_id: Optional[int] = None,
    wp_status: str = "draft",
    now: Optional[dt.datetime] = None,
    scope_family: Optional[str] = None,
    run_id: Optional[str] = None,
) -> int:
    """Append a dedup history row to ``article_candidates``."""
    subject = (subject_key or "").strip()
    metric = (metric_name or "").strip()
    if not subject or not metric:
        return 0
    family = scope_family or scope_family_for(scope)
    rid = run_id or str(uuid.uuid4())
    _ensure_run(conn, rid)
    now_dt = (now or _now_utc()).astimezone(dt.timezone.utc)
    status = "PUBLISHED" if wp_status == "publish" else "DRAFTED"
    band = rank_band(rank, total)
    current = _kv_blob(
        metric=metric,
        scope=scope,
        scope_family=family,
        value=value,
        rank=rank,
        total=total,
        rank_band=band,
    )
    notes = _kv_blob(
        metric=metric,
        scope=scope,
        scope_family=family,
        post_id=post_id,
        title=title[:80],
    )
    cur = conn.execute(
        "INSERT INTO article_candidates "
        "(run_id, player_canonical, player_display, signal_type, magnitude, "
        "baseline_value, current_value, window_label, comparison_target, "
        "evidence_json, priority, status, created_at, notes) "
        "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, NULL, 5, ?, ?, ?)",
        (
            rid,
            subject,
            SIGNAL_DEDUP_HISTORY,
            float(value) if value is not None else None,
            f"cooldown_days={cooldown_days()} delta_ratio={delta_ratio()}",
            current,
            _history_window_label(metric, family),
            scope,
            status,
            now_dt.isoformat(),
            notes,
        ),
    )
    conn.commit()
    return int(cur.lastrowid or 0)
