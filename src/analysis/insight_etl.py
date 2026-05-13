"""INSIGHT-001 — fixture HTML → SQLite ETL + article_candidates.csv prototype.

This module is the smallest viable proof-of-concept for the
data-analysis article-candidate pipeline. It:

* Loads an NPB box-score HTML page (fixture file path; **does not** fetch
  any live URL) via the existing :func:`src.source_npb_postgame_extractor
  .parse_npb_box_html`.
* Upserts the parsed game, inning scores, batting logs, and pitching
  logs into ``data/insight/insight.db`` (SQLite, see
  ``data/insight/schema.sql``).
* Resolves player display names against ``config/giants_roster.json``
  where possible (last-name-only entries are kept as ``player_display``
  with a ``NULL`` canonical until a future enrichment pass).
* Emits a handful of **single-game** detector signals as
  ``article_candidates`` rows and exports them to
  ``data/insight/article_candidates.csv``.

The single-game detectors here are deliberately rudimentary — multi-game
trend detection (z-score, streaks, splits) is a follow-up phase once the
DB has ≥2 weeks of history. The point is to prove the data shape and the
end-to-end pipeline with the existing free fixture.

Hard constraints (per doc/active/INSIGHT-001-data-analysis-pipeline.md):
  * No live URL fetch.
  * No WordPress REST call.
  * No Gemini / X API call.
  * No write to existing logs/*.jsonl.
  * No env / Scheduler / deploy side effects.
  * SQLite + CSV file output only.

CLI::

    python3 -m src.analysis.insight_etl \\
        --fixture tests/fixtures/npb_score_2026_0510_d-g-08_box.html \\
        --game-id 2026-05-10:d-g-08 \\
        --game-date 2026-05-10
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_npb_postgame_extractor import parse_npb_box_html  # noqa: E402

DEFAULT_DB_PATH = ROOT / "data" / "insight" / "insight.db"
DEFAULT_SCHEMA = ROOT / "data" / "insight" / "schema.sql"
DEFAULT_CSV = ROOT / "data" / "insight" / "article_candidates.csv"
ROSTER_PATH = ROOT / "config" / "giants_roster.json"

CSV_COLUMNS = (
    "candidate_id",
    "run_ts",
    "game_id",
    "player_canonical",
    "player_display",
    "signal_type",
    "magnitude",
    "baseline_value",
    "current_value",
    "window_label",
    "comparison_target",
    "evidence_json",
    "priority",
    "status",
    "created_at",
    "notes",
)


# ─── roster lookup ──────────────────────────────────────────────────────────


def _load_roster_aliases() -> dict[str, str]:
    """Return ``{alias_or_name: canonical_name}`` from giants_roster.json.

    The roster file is a list of dicts with ``name`` (canonical) and
    ``aliases`` (list including the canonical itself). Surname-only
    keys (e.g. ``"吉川"``) are added when they uniquely identify a
    single active player; ambiguous surnames fall through unresolved.
    """
    if not ROSTER_PATH.exists():
        return {}
    try:
        roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    surname_buckets: dict[str, list[str]] = {}
    for row in roster:
        canon = (row.get("name") or "").strip()
        if not canon:
            continue
        out[canon] = canon
        for alias in row.get("aliases") or []:
            a = (alias or "").strip()
            if a:
                out.setdefault(a, canon)
        if row.get("active") and len(canon) >= 2:
            surname_buckets.setdefault(canon[:2], []).append(canon)
    for surname, cands in surname_buckets.items():
        if len(cands) == 1:
            out.setdefault(surname, cands[0])
    return out


def resolve_canonical(display: str, aliases: dict[str, str]) -> str | None:
    if not display:
        return None
    raw = display.strip()
    return aliases.get(raw)


# ─── parsers / helpers ──────────────────────────────────────────────────────


_IP_RE = re.compile(r"^\s*(\d+)(?:\.(\d))?\s*$")


def parse_ip(value: str | None) -> float | None:
    """投球回 "5.1" → 5.333, "5.2" → 5.667. Returns None on parse failure."""
    if value is None:
        return None
    m = _IP_RE.match(str(value))
    if not m:
        return None
    whole = int(m.group(1))
    third = int(m.group(2) or 0)
    if third > 2:
        return None
    return round(whole + third / 3.0, 3)


def _int_or_none(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def derive_result(giants_score: int | None, opp_score: int | None) -> str:
    if giants_score is None or opp_score is None:
        return "unknown"
    if giants_score > opp_score:
        return "win"
    if giants_score < opp_score:
        return "loss"
    return "draw"


# ─── DB helpers ─────────────────────────────────────────────────────────────


def open_db(db_path: Path = DEFAULT_DB_PATH, schema_path: Path = DEFAULT_SCHEMA) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if schema_path.exists():
        with schema_path.open(encoding="utf-8") as f:
            conn.executescript(f.read())
    return conn


def upsert_game(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    game_date: str,
    parsed: dict,
    source_url: str | None,
    source_kind: str,
    ingested_at: str,
) -> None:
    inning_scores = parsed.get("inning_score") or []
    giants_total = next((row.get("total") for row in inning_scores if "巨人" in str(row.get("name") or "")), None)
    opp_total = next((row.get("total") for row in inning_scores if "巨人" not in str(row.get("name") or "")), None)
    opp_name = parsed.get("opponent_team_name") or ""
    win = parsed.get("winning_pitcher") or {}
    loss = parsed.get("losing_pitcher") or {}
    save = parsed.get("save_pitcher") or {}
    conn.execute(
        """
        INSERT OR REPLACE INTO games (
            game_id, game_date, opponent, home_away,
            giants_score, opp_score, result,
            league_label, one_line_summary,
            winning_pitcher, losing_pitcher, save_pitcher,
            source_url, source_kind, ingested_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            game_id,
            game_date,
            opp_name,
            "unknown",
            giants_total,
            opp_total,
            derive_result(giants_total, opp_total),
            None,
            None,
            win.get("name"),
            loss.get("name"),
            save.get("name") if save else None,
            source_url,
            source_kind,
            ingested_at,
        ),
    )
    # inning_scores
    for row in inning_scores:
        role = "giants" if "巨人" in str(row.get("name") or "") else "opponent"
        conn.execute(
            """
            INSERT OR REPLACE INTO inning_scores (game_id, team_role, inning_json, total)
            VALUES (?,?,?,?)
            """,
            (
                game_id,
                role,
                json.dumps(row.get("innings") or [], ensure_ascii=False),
                int(row.get("total") or 0),
            ),
        )


def _upsert_batters(
    conn: sqlite3.Connection,
    game_id: str,
    team_role: str,
    rows: Iterable[dict],
    aliases: dict[str, str],
) -> int:
    n = 0
    # Each (slot_order, player_display) is unique. Substitutions reuse the slot.
    for row in rows:
        slot_raw = row.get("順")
        try:
            slot = int(slot_raw) if slot_raw else None
        except (TypeError, ValueError):
            slot = None
        if slot is None:
            continue
        display = (row.get("選手") or "").strip()
        if not display:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO batting_logs (
                game_id, team_role, slot_order, position,
                player_display, player_canonical, is_sub,
                AB, R, H, RBI, SB, atbats_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                team_role,
                slot,
                (row.get("守備") or "").strip() or None,
                display,
                resolve_canonical(display, aliases),
                int(bool(row.get("is_sub"))),
                _int_or_none(row.get("打数")),
                _int_or_none(row.get("得点")),
                _int_or_none(row.get("安打")),
                _int_or_none(row.get("打点")),
                _int_or_none(row.get("盗塁")),
                json.dumps(row.get("atbats") or [], ensure_ascii=False),
            ),
        )
        n += 1
    return n


_PITCHER_AGGREGATE_LABELS = {"チーム計", "計", "合計", "全体"}


def _upsert_pitchers(
    conn: sqlite3.Connection,
    game_id: str,
    team_role: str,
    rows: Iterable[dict],
    aliases: dict[str, str],
) -> int:
    n = 0
    order = 0
    for raw in rows:
        display = (raw.get("選手") or "").strip()
        if not display:
            continue
        # NPB box の最終行は「チーム計」集計行。投手 log には含めない。
        if display in _PITCHER_AGGREGATE_LABELS or display.startswith("チーム"):
            continue
        order += 1
        row = raw
        conn.execute(
            """
            INSERT OR REPLACE INTO pitching_logs (
                game_id, team_role, appearance_order,
                player_display, player_canonical,
                result_mark, pitches, BF, IP,
                H_allowed, HR_allowed, BB, HBP, K, WP, BK, R, ER
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                game_id,
                team_role,
                order,
                display,
                resolve_canonical(display, aliases),
                (row.get("result_mark") or "").strip() or None,
                _int_or_none(row.get("投球数")),
                _int_or_none(row.get("打者")),
                parse_ip(row.get("投球回")),
                _int_or_none(row.get("安打")),
                _int_or_none(row.get("本塁打")),
                _int_or_none(row.get("四球")),
                _int_or_none(row.get("死球")),
                _int_or_none(row.get("三振")),
                _int_or_none(row.get("暴投")),
                _int_or_none(row.get("ボーク")),
                _int_or_none(row.get("失点")),
                _int_or_none(row.get("自責点")),
            ),
        )
        n += 1
    return n


# ─── single-game detectors (stub-grade, multi-game logic is next phase) ─────


def detect_single_game_signals(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    run_id: str,
    created_at: str,
) -> list[dict]:
    """Emit MVP-grade signals from a single game's logs.

    These are intentionally simple — they exist to prove the
    article_candidates row shape end-to-end. Real signals (z-score,
    streaks, splits, lineup deltas) need a multi-game history and live
    in a follow-up phase.
    """
    out: list[dict] = []

    # batter signals (Giants only)
    for row in conn.execute(
        """
        SELECT player_display, player_canonical, slot_order, position,
               AB, R, H, RBI, SB, atbats_json
        FROM batting_logs
        WHERE game_id = ? AND team_role = 'giants'
        ORDER BY slot_order, player_display
        """,
        (game_id,),
    ):
        h = row["H"] or 0
        ab = row["AB"] or 0
        rbi = row["RBI"] or 0
        atbats = json.loads(row["atbats_json"] or "[]")
        had_hr = any("本" in str(a) for a in atbats)

        if had_hr:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="batter_homerun",
                magnitude=1.0,
                baseline_value=None,
                current_value=f"H{h}/AB{ab}, RBI{rbi}",
                window_label="single_game",
                comparison_target=None,
                evidence={"atbats": atbats, "slot": row["slot_order"], "pos": row["position"]},
                priority=2,
                created_at=created_at,
                notes="単発HR検知（MVP単試合）",
            ))
        if h >= 3:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="batter_multi_hit",
                magnitude=float(h),
                baseline_value=None,
                current_value=f"H{h}/AB{ab}",
                window_label="single_game",
                comparison_target=None,
                evidence={"atbats": atbats, "slot": row["slot_order"], "pos": row["position"]},
                priority=3,
                created_at=created_at,
                notes="マルチヒット検知（MVP単試合）",
            ))

    # pitcher signals (Giants only)
    for row in conn.execute(
        """
        SELECT player_display, player_canonical, appearance_order,
               result_mark, pitches, BF, IP,
               H_allowed, HR_allowed, BB, HBP, K, R, ER
        FROM pitching_logs
        WHERE game_id = ? AND team_role = 'giants'
        ORDER BY appearance_order
        """,
        (game_id,),
    ):
        ip = row["IP"] or 0.0
        er = row["ER"] or 0
        pitches = row["pitches"] or 0

        # QS proxy (≥6.0 IP, ≤3 ER) — pitcher が先発したかは appearance_order=1 で代用
        if row["appearance_order"] == 1 and ip >= 6.0 and er <= 3:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="starter_quality_start",
                magnitude=ip,
                baseline_value=None,
                current_value=f"{ip}IP / {er}ER / {pitches}P",
                window_label="single_game",
                comparison_target=None,
                evidence=dict(row),
                priority=3,
                created_at=created_at,
                notes="QS（IP≥6 ER≤3）— 連続性は多試合フェーズで判定",
            ))
        # high pitch count警戒
        if pitches >= 110:
            out.append(_candidate(
                run_id=run_id,
                game_id=game_id,
                player_display=row["player_display"],
                player_canonical=row["player_canonical"],
                signal_type="pitcher_high_pitch_count",
                magnitude=float(pitches),
                baseline_value=None,
                current_value=f"{pitches}球",
                window_label="single_game",
                comparison_target=None,
                evidence=dict(row),
                priority=2,
                created_at=created_at,
                notes="多球数検知（疲労蓄積観測のフラグ）",
            ))

    return out


def _candidate(**kw: Any) -> dict:
    evidence = kw.pop("evidence", None)
    if isinstance(evidence, dict):
        evidence_json = json.dumps(_jsonify(evidence), ensure_ascii=False)
    else:
        evidence_json = None
    return {
        "run_id": kw["run_id"],
        "game_id": kw.get("game_id"),
        "player_canonical": kw.get("player_canonical"),
        "player_display": kw.get("player_display"),
        "signal_type": kw["signal_type"],
        "magnitude": kw.get("magnitude"),
        "baseline_value": kw.get("baseline_value"),
        "current_value": kw.get("current_value"),
        "window_label": kw.get("window_label"),
        "comparison_target": kw.get("comparison_target"),
        "evidence_json": evidence_json,
        "priority": kw.get("priority", 3),
        "status": "NEW",
        "created_at": kw["created_at"],
        "notes": kw.get("notes"),
    }


def _jsonify(obj: Any) -> Any:
    """Coerce sqlite3.Row / nested rows into JSON-serializable shapes."""
    if isinstance(obj, sqlite3.Row):
        return {k: _jsonify(obj[k]) for k in obj.keys()}
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def insert_candidates(
    conn: sqlite3.Connection,
    candidates: list[dict],
) -> list[int]:
    ids: list[int] = []
    for c in candidates:
        cur = conn.execute(
            """
            INSERT INTO article_candidates (
                run_id, game_id, player_canonical, player_display,
                signal_type, magnitude, baseline_value, current_value,
                window_label, comparison_target, evidence_json,
                priority, status, created_at, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                c["run_id"], c["game_id"], c["player_canonical"], c["player_display"],
                c["signal_type"], c["magnitude"], c["baseline_value"], c["current_value"],
                c["window_label"], c["comparison_target"], c["evidence_json"],
                c["priority"], c["status"], c["created_at"], c["notes"],
            ),
        )
        ids.append(cur.lastrowid)
    return ids


def export_candidates_csv(conn: sqlite3.Connection, csv_path: Path, run_id: str | None = None) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # run_ts は insight_runs に住んでいるので JOIN で取得する。
    query = """
        SELECT ac.candidate_id,
               ir.run_ts AS run_ts,
               ac.game_id, ac.player_canonical, ac.player_display,
               ac.signal_type, ac.magnitude, ac.baseline_value, ac.current_value,
               ac.window_label, ac.comparison_target, ac.evidence_json,
               ac.priority, ac.status, ac.created_at, ac.notes
        FROM article_candidates ac
        LEFT JOIN insight_runs ir ON ir.run_id = ac.run_id
    """
    params: tuple = ()
    if run_id:
        query += " WHERE ac.run_id = ?"
        params = (run_id,)
    query += " ORDER BY ac.candidate_id"
    rows = list(conn.execute(query, params))
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] if k in r.keys() else None for k in CSV_COLUMNS})
    return len(rows)


# ─── ETL entry point ─────────────────────────────────────────────────────────


def etl_from_html(
    html: str,
    *,
    game_id: str,
    game_date: str,
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA,
    csv_path: Path = DEFAULT_CSV,
    source_url: str | None = None,
    source_kind: str = "html",
    notes: str | None = None,
    aliases: dict[str, str] | None = None,
) -> dict:
    """Run the full single-game ETL against a raw NPB box HTML string.

    Identical pipeline to :func:`etl_fixture` but accepts the HTML as a
    string so callers (nightly orchestrator) can pass live-fetched or
    cached content without writing it to a temp file first.
    """
    parsed = parse_npb_box_html(html)
    if parsed is None:
        raise ValueError(f"parse_npb_box_html returned None for game_id={game_id}")

    aliases = aliases or _load_roster_aliases()
    conn = open_db(db_path=db_path, schema_path=schema_path)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = str(uuid.uuid4())

    try:
        upsert_game(
            conn,
            game_id=game_id,
            game_date=game_date,
            parsed=parsed,
            source_url=source_url,
            source_kind=source_kind,
            ingested_at=now_iso,
        )
        n_g_bat = _upsert_batters(conn, game_id, "giants", parsed.get("giants_batters") or [], aliases)
        n_o_bat = _upsert_batters(conn, game_id, "opponent", parsed.get("opponent_batters") or [], aliases)
        n_g_pit = _upsert_pitchers(conn, game_id, "giants", parsed.get("giants_pitchers") or [], aliases)
        n_o_pit = _upsert_pitchers(conn, game_id, "opponent", parsed.get("opponent_pitchers") or [], aliases)

        conn.execute(
            "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, n_candidates, notes) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, now_iso, game_date, game_date, 0, notes or f"etl_from_html game_id={game_id}"),
        )

        candidates = detect_single_game_signals(
            conn,
            game_id=game_id,
            run_id=run_id,
            created_at=now_iso,
        )
        inserted = insert_candidates(conn, candidates)
        conn.execute(
            "UPDATE insight_runs SET n_candidates = ? WHERE run_id = ?",
            (len(inserted), run_id),
        )
        conn.commit()

        csv_rows = export_candidates_csv(conn, csv_path, run_id=run_id)
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "game_id": game_id,
        "batters_giants": n_g_bat,
        "batters_opponent": n_o_bat,
        "pitchers_giants": n_g_pit,
        "pitchers_opponent": n_o_pit,
        "candidates_inserted": len(candidates),
        "csv_rows_written": csv_rows,
        "db_path": str(db_path),
        "csv_path": str(csv_path),
    }


def etl_fixture(
    fixture_path: Path,
    *,
    game_id: str,
    game_date: str,
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA,
    csv_path: Path = DEFAULT_CSV,
    source_url: str | None = None,
    aliases: dict[str, str] | None = None,
) -> dict:
    """Run the full ETL on a fixture HTML file. Returns a summary dict
    that includes a ``fixture`` key (back-compat for INSIGHT-001 tests).
    Internally a thin wrapper over :func:`etl_from_html`."""
    html = fixture_path.read_text(encoding="utf-8")
    summary = etl_from_html(
        html,
        game_id=game_id,
        game_date=game_date,
        db_path=db_path,
        schema_path=schema_path,
        csv_path=csv_path,
        source_url=source_url,
        source_kind="fixture",
        notes=f"etl fixture {fixture_path.name}",
        aliases=aliases,
    )
    summary["fixture"] = str(fixture_path)
    return summary


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="INSIGHT-001 fixture ETL prototype (no live URL, no WP I/O)."
    )
    p.add_argument("--fixture", required=True, help="path to NPB box HTML fixture")
    p.add_argument("--game-id", required=True, help="e.g. '2026-05-10:d-g-08'")
    p.add_argument("--game-date", required=True, help="ISO date e.g. '2026-05-10'")
    p.add_argument("--db", default=str(DEFAULT_DB_PATH))
    p.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    p.add_argument("--csv", default=str(DEFAULT_CSV))
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="parse only; do not write to SQLite/CSV (default: write)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(json.dumps({"error": f"fixture not found: {fixture_path}"}), file=sys.stderr)
        return 2

    if args.dry_run:
        html = fixture_path.read_text(encoding="utf-8")
        parsed = parse_npb_box_html(html)
        summary = {
            "dry_run": True,
            "fixture": str(fixture_path),
            "parsed_keys": list(parsed.keys()) if parsed else [],
            "n_giants_batters": len((parsed or {}).get("giants_batters") or []),
            "n_giants_pitchers": len((parsed or {}).get("giants_pitchers") or []),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    summary = etl_fixture(
        fixture_path,
        game_id=args.game_id,
        game_date=args.game_date,
        db_path=Path(args.db),
        schema_path=Path(args.schema),
        csv_path=Path(args.csv),
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
