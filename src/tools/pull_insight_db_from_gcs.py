"""Pull the production insight.db to a local read-only verification path.

This operator tool is intentionally one-way:

* downloads ``insight.db`` from the configured production GCS bucket
* writes only to the requested local file path
* never uploads to GCS
* never calls WordPress, X, Gmail, Gemini, Scheduler, or Cloud Run

Default output is under ``/tmp`` so the repo-local generated DB is not
overwritten by accident. Use ``--replace-local`` only when an operator
explicitly wants ``data/insight/insight.db`` refreshed for local checks.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional, Sequence, TextIO
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]

from src import manual_intake_insight_query as miq  # noqa: E402
from src.cloud_run_persistence import GCSAccessError, GCSStateManager  # noqa: E402


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_PRODUCTION_BUCKET = "baseballsite-yoshilover-insight"
DEFAULT_PROJECT_ID = "baseballsite"
DEFAULT_TARGET = Path("/tmp/yoshilover-insight-latest.db")
REPO_LOCAL_DB = REPO_ROOT / "data" / "insight" / "insight.db"
_GIANTS_ALIASES = (
    "G",
    "GIANTS",
    "Giants",
    "g",
    "ジャイアンツ",
    "巨人",
    "読売",
    "読売ジャイアンツ",
)


@contextmanager
def _temporary_bucket_env(bucket_name: str) -> Iterator[None]:
    previous = os.environ.get("INSIGHT_GCS_BUCKET")
    os.environ["INSIGHT_GCS_BUCKET"] = bucket_name
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("INSIGHT_GCS_BUCKET", None)
        else:
            os.environ["INSIGHT_GCS_BUCKET"] = previous


def _bucket_name(override: Optional[str]) -> str:
    return (
        (override or "").strip()
        or (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()
        or DEFAULT_PRODUCTION_BUCKET
    )


def _gcs_prefix() -> str:
    return (os.environ.get("INSIGHT_GCS_PREFIX") or "").strip().strip("/")


def _project_id() -> str:
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "PROJECT_ID"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return DEFAULT_PROJECT_ID


def _python_storage_missing(download: dict) -> bool:
    reason = str(download.get("reason") or "")
    return "ModuleNotFoundError" in reason and "google" in reason


def _python_storage_available() -> bool:
    try:
        from google.cloud import storage as _storage  # noqa: F401,WPS433
    except (ImportError, ModuleNotFoundError):
        return False
    return True


def _download_with_python_storage(
    *,
    target: Path,
    bucket: str,
    ttl_seconds: int,
    client=None,
) -> dict:
    with _temporary_bucket_env(bucket):
        download = miq.ensure_local_db(
            cache_path=target,
            client=client,
            ttl_seconds=ttl_seconds,
        )
    download = dict(download)
    download["transport"] = "python_storage"
    return download


def _download_with_gcloud_storage(*, target: Path, bucket: str) -> dict:
    manager = GCSStateManager(
        bucket_name=bucket,
        prefix=_gcs_prefix(),
        project_id=_project_id(),
    )
    try:
        ok = manager.download("insight.db", target, retries=1)
    except GCSAccessError as exc:
        return {
            "ok": False,
            "path": str(target),
            "refreshed": False,
            "reason": f"gcloud_download_error:{exc.detail}",
            "transport": "gcloud_storage",
        }
    if not ok:
        return {
            "ok": False,
            "path": str(target),
            "refreshed": False,
            "reason": "blob_missing",
            "transport": "gcloud_storage",
        }
    return {
        "ok": True,
        "path": str(target),
        "refreshed": True,
        "reason": "downloaded_gcloud",
        "transport": "gcloud_storage",
    }


def _staleness_days(latest_game_date: Optional[str], *, now: datetime) -> Optional[int]:
    if not latest_game_date:
        return None
    try:
        latest = date.fromisoformat(latest_game_date)
    except ValueError:
        return None
    return (now.astimezone(JST).date() - latest).days


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _count_if_exists(conn: sqlite3.Connection, name: str) -> Optional[int]:
    if not _table_exists(conn, name):
        return None
    row = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
    return int(row[0]) if row else 0


def _max_game_date(conn: sqlite3.Connection) -> Optional[str]:
    if not _table_exists(conn, "games"):
        return None
    row = conn.execute(
        "SELECT MAX(game_date) FROM games WHERE game_date IS NOT NULL"
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _max_giants_game_date(conn: sqlite3.Connection) -> Optional[str]:
    if not (_table_exists(conn, "games") and _table_exists(conn, "batting_logs")):
        return None
    placeholders = ",".join("?" for _ in _GIANTS_ALIASES)
    row = conn.execute(
        "SELECT MAX(g.game_date) "
        "FROM games g "
        "WHERE g.game_date IS NOT NULL "
        "AND EXISTS ("
        "  SELECT 1 FROM batting_logs b "
        "  WHERE b.game_id = g.game_id "
        f" AND b.team_name IN ({placeholders})"
        ")",
        _GIANTS_ALIASES,
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def inspect_local_db(db_path: Path, *, now: Optional[datetime] = None) -> dict:
    """Return a small read-only freshness summary for a local insight DB."""
    now = now or datetime.now(JST)
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        latest_game_date = _max_game_date(conn)
        latest_giants_game_date = _max_giants_game_date(conn)
        return {
            "path": str(db_path),
            "size_bytes": db_path.stat().st_size,
            "latest_game_date": latest_game_date,
            "latest_giants_game_date": latest_giants_game_date,
            "staleness_days": _staleness_days(latest_game_date, now=now),
            "giants_staleness_days": _staleness_days(
                latest_giants_game_date,
                now=now,
            ),
            "tables": {
                "games": _count_if_exists(conn, "games"),
                "batting_logs": _count_if_exists(conn, "batting_logs"),
                "pitching_logs": _count_if_exists(conn, "pitching_logs"),
                "advanced_metric_snapshots": _count_if_exists(
                    conn,
                    "advanced_metric_snapshots",
                ),
                "article_candidates": _count_if_exists(conn, "article_candidates"),
            },
        }
    finally:
        conn.close()


def pull_latest_insight_db(
    *,
    target: Path = DEFAULT_TARGET,
    bucket_name: Optional[str] = None,
    ttl_seconds: int = 0,
    now: Optional[datetime] = None,
    client=None,
) -> dict:
    """Download production ``insight.db`` and summarize it.

    ``ttl_seconds=0`` forces a fresh download. This is the default because
    the tool is meant to answer "what is production right now?"
    """
    bucket = _bucket_name(bucket_name)
    target = target.expanduser()
    if client is None and not _python_storage_available():
        download = _download_with_gcloud_storage(target=target, bucket=bucket)
    else:
        download = _download_with_python_storage(
            target=target,
            bucket=bucket,
            ttl_seconds=ttl_seconds,
            client=client,
        )
    if not download.get("ok") and client is None and _python_storage_missing(download):
        download = _download_with_gcloud_storage(target=target, bucket=bucket)
    result = {
        "ok": bool(download.get("ok")),
        "source": {
            "bucket": bucket,
            "object": "insight.db",
            "mode": "download_only",
        },
        "download": download,
    }
    if not download.get("ok"):
        return result
    result["summary"] = inspect_local_db(target, now=now)
    return result


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download production insight.db for local verification.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"Local output path. Default: {DEFAULT_TARGET}",
    )
    parser.add_argument(
        "--replace-local",
        action="store_true",
        help=f"Explicitly overwrite repo-local generated DB: {REPO_LOCAL_DB}",
    )
    parser.add_argument(
        "--bucket",
        help=(
            "GCS bucket. Defaults to INSIGHT_GCS_BUCKET env, then "
            f"{DEFAULT_PRODUCTION_BUCKET}."
        ),
    )
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=0,
        help="Cache TTL passed to ensure_local_db. 0 forces download.",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    client=None,
    stdout: Optional[TextIO] = None,
) -> int:
    args = _parse_args(argv)
    out = stdout or sys.stdout
    target = REPO_LOCAL_DB if args.replace_local else args.target
    result = pull_latest_insight_db(
        target=target,
        bucket_name=args.bucket,
        ttl_seconds=max(0, args.ttl_seconds),
        client=client,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), file=out)
    return 0 if result.get("ok") else 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
