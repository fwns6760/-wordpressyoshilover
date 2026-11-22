"""Build the small, read-only SQLite snapshot used by the public data site.

The canonical insight database also contains long-lived article candidates and
daily metric history.  Those tables are useful to the analysis lanes, but they
made the database exceed 400 MiB and caused the 512 MiB data-site Cloud Run Job
to be OOM-killed while downloading it to the in-memory filesystem.

This module keeps only the tables queried by ``src.data_site_query`` and only
the newest date for each advanced-metric scope.  It never mutates the canonical
database.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DATA_SITE_TABLES: tuple[str, ...] = (
    "games",
    "batting_logs",
    "pitching_logs",
    "at_bat_details",
    "defense_opportunities",
    "fielding_logs",
    "inning_scores",
    "lineups",
    "players",
    "teams",
    "standings_snapshots",
)
METRIC_TABLE = "advanced_metric_snapshots"


def _copy_rows(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    table: str,
    *,
    where: str = "",
    params: tuple[object, ...] = (),
    batch_size: int = 2_000,
) -> int:
    columns = [
        str(row[1])
        for row in source.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]
    if not columns:
        return 0
    quoted = ",".join(f'"{name}"' for name in columns)
    placeholders = ",".join("?" for _ in columns)
    cursor = source.execute(
        f'SELECT {quoted} FROM "{table}"' + (f" WHERE {where}" if where else ""),
        params,
    )
    inserted = 0
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        target.executemany(
            f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
            rows,
        )
        inserted += len(rows)
    return inserted


def build_compact_snapshot(
    source_path: str | os.PathLike[str],
    target_path: str | os.PathLike[str],
) -> dict[str, object]:
    """Create an atomic compact copy and return size/row diagnostics."""
    source_file = Path(source_path)
    target_file = Path(target_path)
    if not source_file.is_file():
        raise FileNotFoundError(source_file)
    if source_file.resolve() == target_file.resolve():
        raise ValueError("source and target snapshot paths must differ")

    target_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_file.with_name(target_file.name + ".tmp")
    temporary.unlink(missing_ok=True)

    source = sqlite3.connect(f"file:{source_file}?mode=ro", uri=True)
    target = sqlite3.connect(temporary)
    copied: dict[str, int] = {}
    try:
        target.execute("PRAGMA journal_mode=OFF")
        target.execute("PRAGMA synchronous=OFF")
        available = {
            str(row[0])
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        selected = [name for name in DATA_SITE_TABLES if name in available]
        if "games" not in selected or "batting_logs" not in selected:
            raise RuntimeError("canonical insight DB is missing required data-site tables")

        for table in (*selected, METRIC_TABLE):
            if table not in available:
                if table == METRIC_TABLE:
                    raise RuntimeError(f"canonical insight DB is missing {METRIC_TABLE}")
                continue
            schema_row = source.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not schema_row or not schema_row[0]:
                raise RuntimeError(f"schema unavailable for table {table}")
            target.execute(str(schema_row[0]))

        for table in selected:
            copied[table] = _copy_rows(source, target, table)

        copied[METRIC_TABLE] = 0
        latest_by_scope = source.execute(
            f"SELECT scope, MAX(snapshot_date) FROM {METRIC_TABLE} GROUP BY scope"
        ).fetchall()
        for scope, snapshot_date in latest_by_scope:
            copied[METRIC_TABLE] += _copy_rows(
                source,
                target,
                METRIC_TABLE,
                where="scope=? AND snapshot_date=?",
                params=(scope, snapshot_date),
            )

        copied_tables = set(copied)
        for index_name, table_name, sql in source.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master "
            "WHERE type='index' AND sql IS NOT NULL ORDER BY name"
        ):
            if str(table_name) in copied_tables and sql:
                target.execute(str(sql))

        target.commit()
        target.execute("ANALYZE")
        target.execute("VACUUM")
        target.commit()

        latest_game = str(
            target.execute("SELECT MAX(game_date) FROM games").fetchone()[0] or ""
        )
        if not latest_game:
            raise RuntimeError("compact data-site snapshot has no game date")
    except Exception:
        target.close()
        source.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        target.close()
        source.close()

    os.replace(temporary, target_file)
    return {
        "source_size": source_file.stat().st_size,
        "target_size": target_file.stat().st_size,
        "latest_game_date": latest_game[:10],
        "rows": copied,
    }
