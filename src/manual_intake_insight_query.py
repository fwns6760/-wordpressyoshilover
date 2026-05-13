"""INSIGHT-006 — insight DB query helper for manual_intake_service UI.

The manual-intake-service runs in a Cloud Run service container that
does NOT execute the nightly ETL — it only serves the form. To let
operators inspect ``article_candidates`` from the browser we:

1. Lazily download ``insight.db`` from the configured GCS bucket
   (``INSIGHT_GCS_BUCKET``) into a local cache path on the container's
   ephemeral disk.
2. Refresh the cache once the TTL elapses (default 1 hour) so each
   nightly run's accumulated data shows up the next morning.
3. Run **read-only** SQL with safe parameter binding against the cached
   DB and return rows as JSON-serialisable dicts.

This module never:

* Writes to GCS.
* Calls WordPress / Gemini / X API.
* Mutates the DB it downloads (file opened read-only).

If GCS is unconfigured or the download fails the module returns an
empty result set without raising — the new tab degrades gracefully so
the existing manual-intake tab is unaffected.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path(
    os.environ.get("INSIGHT_DB_CACHE_PATH", "/tmp/insight_cache/insight.db")
)
DEFAULT_TTL_SECONDS = int(os.environ.get("INSIGHT_DB_CACHE_TTL_SECONDS", "3600"))
ALLOWED_SIGNAL_TYPES = {
    "batter_homerun",
    "batter_multi_hit",
    "batter_recent_hot",
    "batter_recent_cold",
    "batter_hit_streak",
    "starter_quality_start",
    "pitcher_high_pitch_count",
    "pitcher_workload_warning",
    "pitcher_rest_days_back_to_back",
    "pitcher_rest_days_extended_layoff",
    "lineup_slot_jump_up",
    "lineup_slot_jump_down",
    "lineup_first_slot_appearance",
}


# ─── cache state ────────────────────────────────────────────────────────────


@dataclass
class CacheState:
    path: Path
    refreshed_at: float = 0.0
    last_error: Optional[str] = None


_CACHE = CacheState(path=DEFAULT_CACHE_PATH)


def reset_cache_for_tests() -> None:
    """Reset module-level cache between unit tests."""
    global _CACHE
    _CACHE = CacheState(path=DEFAULT_CACHE_PATH)


# ─── GCS download ───────────────────────────────────────────────────────────


def _bucket_name() -> Optional[str]:
    name = (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()
    return name or None


def _gcs_prefix() -> str:
    return (os.environ.get("INSIGHT_GCS_PREFIX") or "").strip().strip("/")


def _build_client():
    from google.cloud import storage  # noqa: WPS433

    return storage.Client()


def ensure_local_db(
    *,
    now: Optional[float] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    cache_path: Optional[Path] = None,
    client=None,
) -> dict:
    """Download (or refresh) the insight.db cache file. Returns a
    summary dict with ``ok`` / ``path`` / ``refreshed`` / ``reason``."""
    target = cache_path or _CACHE.path
    bucket_name = _bucket_name()
    if not bucket_name:
        return {
            "ok": False,
            "path": str(target),
            "refreshed": False,
            "reason": "no_bucket",
        }
    now = now if now is not None else time.time()
    if target.exists() and (now - _CACHE.refreshed_at) < ttl_seconds:
        return {
            "ok": True,
            "path": str(target),
            "refreshed": False,
            "reason": "cache_fresh",
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = _gcs_prefix()
    object_name = f"{prefix}/insight.db" if prefix else "insight.db"
    try:
        gcs_client = client or _build_client()
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        if not blob.exists():
            _CACHE.last_error = "blob_missing"
            return {
                "ok": False,
                "path": str(target),
                "refreshed": False,
                "reason": "blob_missing",
            }
        blob.download_to_filename(str(target))
    except Exception as exc:  # noqa: BLE001
        logger.exception("insight_query_gcs_download_failed")
        _CACHE.last_error = f"download_error:{exc!r}"
        return {
            "ok": False,
            "path": str(target),
            "refreshed": False,
            "reason": f"download_error:{exc!r}",
        }
    _CACHE.refreshed_at = now
    _CACHE.last_error = None
    return {
        "ok": True,
        "path": str(target),
        "refreshed": True,
        "reason": "downloaded",
    }


# ─── SQL ────────────────────────────────────────────────────────────────────


def _validate_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    # ISO date format YYYY-MM-DD only
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    y, m, d = s[:4], s[5:7], s[8:10]
    if not (y.isdigit() and m.isdigit() and d.isdigit()):
        return None
    return s


def query_candidates(
    *,
    player: Optional[str] = None,
    signal_type: Optional[str] = None,
    since_game_date: Optional[str] = None,
    until_game_date: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> dict:
    """Read-only SELECT against article_candidates joined with games and
    insight_runs. All filters are optional and parameter-bound.

    Returns ``{"ok": bool, "rows": [...], "count": N, "filters": {...}}``.
    """
    target = db_path or _CACHE.path
    filters = {
        "player": (player or "").strip() or None,
        "signal_type": (signal_type or "").strip() or None,
        "since_game_date": _validate_date(since_game_date),
        "until_game_date": _validate_date(until_game_date),
        "limit": max(1, min(int(limit), 500)),
    }
    if filters["signal_type"] and filters["signal_type"] not in ALLOWED_SIGNAL_TYPES:
        return {
            "ok": False,
            "reason": f"invalid_signal_type:{filters['signal_type']}",
            "rows": [],
            "count": 0,
            "filters": filters,
        }
    if not target.exists():
        return {
            "ok": False,
            "reason": "db_not_available",
            "rows": [],
            "count": 0,
            "filters": filters,
        }

    where: list[str] = []
    params: list = []
    if filters["player"]:
        where.append(
            "(ac.player_canonical = ? OR ac.player_display LIKE ?)"
        )
        params.extend([filters["player"], f"%{filters['player']}%"])
    if filters["signal_type"]:
        where.append("ac.signal_type = ?")
        params.append(filters["signal_type"])
    if filters["since_game_date"]:
        where.append(
            "(g.game_date >= ? OR substr(ir.run_ts, 1, 10) >= ?)"
        )
        params.extend([filters["since_game_date"], filters["since_game_date"]])
    if filters["until_game_date"]:
        where.append(
            "(g.game_date <= ? OR substr(ir.run_ts, 1, 10) <= ?)"
        )
        params.extend([filters["until_game_date"], filters["until_game_date"]])

    sql = (
        "SELECT ac.candidate_id, ac.player_canonical, ac.player_display, "
        "ac.signal_type, ac.magnitude, ac.baseline_value, ac.current_value, "
        "ac.window_label, ac.comparison_target, ac.priority, ac.status, "
        "ac.notes, ac.evidence_json, ac.game_id, g.game_date, g.opponent, "
        "g.result, ir.run_ts "
        "FROM article_candidates ac "
        "LEFT JOIN games g ON g.game_id = ac.game_id "
        "LEFT JOIN insight_runs ir ON ir.run_id = ac.run_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ac.priority ASC, ac.magnitude DESC, ac.candidate_id DESC"
    sql += f" LIMIT {filters['limit']}"

    # Read-only URI keeps the DB safe even on bugged code paths.
    uri = f"file:{target}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()

    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
        "filters": filters,
    }


# ─── helpers for the front-end ──────────────────────────────────────────────


def signal_type_options() -> list[str]:
    """Return the curated list of signal_types the UI exposes."""
    return sorted(ALLOWED_SIGNAL_TYPES)


def roster_options() -> list[dict]:
    """Read ``config/giants_roster.json`` and return active players as
    ``{name, position, role}``. Empty list when the file is missing."""
    roster_path = Path(__file__).resolve().parent.parent / "config" / "giants_roster.json"
    if not roster_path.exists():
        return []
    import json

    try:
        rows = json.loads(roster_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for r in rows:
        if not r.get("active"):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "position": r.get("position") or "",
            "role": r.get("role") or "",
        })
    out.sort(key=lambda x: x["name"])
    return out
