"""INSIGHT-002 module 3 — lineup history + 起用 anomaly skeleton.

* NPB box の ``giants_batters`` 配列を ``lineups`` テーブルに upsert する
  (打順 1〜9 のみ、is_sub は除外。代打/代走 は lineup の遷移ではないので
  別 axis として将来扱う)。
* 過去 lineups と比較し、**slot_change_jump** (打順が前回試合から ≥ 3 段
  変化) と **first_appearance_in_slot** (この選手がこの打順での初出場)
  の 2 種の起用 anomaly を生成する。

Hard constraints:

* 読みのみ + lineups の upsert のみ。WP / Gemini / X API / live HTTP は
  呼ばない。
* 既存 ``games`` / ``batting_logs`` 等の row には書き込まない。
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.insight_etl import resolve_canonical, _load_roster_aliases  # noqa: E402


# ─── lineup upsert from NPB box ─────────────────────────────────────────────


def upsert_lineup_from_parsed_box(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    parsed: dict,
    aliases: Optional[dict[str, str]] = None,
) -> int:
    """``parsed`` は :func:`src.source_npb_postgame_extractor.parse_npb_box_html`
    の返り値。Giants 側スターター (is_sub=False の slot 1-9) を ``lineups``
    に upsert する。返り値 = 挿入/更新 行数。

    same-game の再呼び出しは PK 上書き (idempotent)。
    """
    aliases = aliases or _load_roster_aliases()
    n = 0
    for row in parsed.get("giants_batters") or []:
        if row.get("is_sub"):
            continue
        try:
            slot = int(row.get("順"))
        except (TypeError, ValueError):
            continue
        if not (1 <= slot <= 9):
            continue
        display = (row.get("選手") or "").strip()
        if not display:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO lineups (
                game_id, team_role, slot_order, player_display,
                player_canonical, position, batting_side
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                game_id,
                "giants",
                slot,
                display,
                resolve_canonical(display, aliases),
                (row.get("守備") or "").strip() or None,
                None,
            ),
        )
        n += 1
    return n


# ─── lineup anomaly detectors ───────────────────────────────────────────────


def _fetch_player_slot_history(
    conn: sqlite3.Connection, player_canonical: str
) -> list[dict]:
    cur = conn.execute(
        """
        SELECT l.game_id, g.game_date, l.slot_order, l.position
        FROM lineups l
        JOIN games g ON g.game_id = l.game_id
        WHERE l.team_role = 'giants'
          AND l.player_canonical = ?
        ORDER BY g.game_date ASC, l.game_id ASC
        """,
        (player_canonical,),
    )
    return [dict(zip([d[0] for d in cur.description], row)) for row in cur]


def detect_slot_change_jump(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
    min_jump: int = 3,
) -> Optional[dict]:
    """Latest slot − previous slot の絶対値が ``min_jump`` 以上なら
    起票。同一選手が連続スタメンしているケースのみ意味を持つ。"""
    history = _fetch_player_slot_history(conn, player_canonical)
    if len(history) < 2:
        return None
    last = history[-1]
    prev = history[-2]
    diff = (last["slot_order"] or 0) - (prev["slot_order"] or 0)
    if abs(diff) < min_jump:
        return None
    direction = "up" if diff < 0 else "down"  # slot 番号が小さい方が上位打順
    return {
        "player_canonical": player_canonical,
        "player_display": player_canonical,
        "signal_type": f"lineup_slot_jump_{direction}",
        "magnitude": float(abs(diff)),
        "baseline_value": f"前試合{prev['slot_order']}番",
        "current_value": f"今試合{last['slot_order']}番",
        "window_label": "last_2_starts",
        "comparison_target": "self_prior_lineup",
        "evidence": {
            "prev_game_id": prev["game_id"],
            "last_game_id": last["game_id"],
            "prev_slot": prev["slot_order"],
            "last_slot": last["slot_order"],
            "prev_position": prev["position"],
            "last_position": last["position"],
        },
        "priority": 1 if abs(diff) >= 4 else 2,
        "notes": (
            f"打順が前試合{prev['slot_order']}番 → 今試合{last['slot_order']}番に"
            f"{abs(diff)}段{'上昇' if diff < 0 else '下降'}"
        ),
    }


def detect_first_appearance_in_slot(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
) -> Optional[dict]:
    """その選手が当該 slot での初出場 (= 直近試合の slot が過去に登場せず)
    のとき起票。"""
    history = _fetch_player_slot_history(conn, player_canonical)
    if len(history) < 2:
        return None
    last = history[-1]
    prior_slots = {r["slot_order"] for r in history[:-1]}
    if last["slot_order"] in prior_slots:
        return None
    return {
        "player_canonical": player_canonical,
        "player_display": player_canonical,
        "signal_type": "lineup_first_slot_appearance",
        "magnitude": float(last["slot_order"] or 0),
        "baseline_value": f"過去スロット={sorted(prior_slots)}",
        "current_value": f"今試合{last['slot_order']}番",
        "window_label": "season_to_date",
        "comparison_target": "self_history",
        "evidence": {
            "last_game_id": last["game_id"],
            "prior_slots": sorted(prior_slots),
            "current_slot": last["slot_order"],
            "current_position": last["position"],
        },
        "priority": 2,
        "notes": (
            f"この選手が{last['slot_order']}番で出場するのは今季初 "
            f"(過去={sorted(prior_slots)})"
        ),
    }


def run_all_lineup_detectors(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    created_at: str,
) -> list[dict]:
    """Iterate Giants player_canonical values present in lineups, run
    both detectors, return finalized candidate dicts."""
    players = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT player_canonical FROM lineups "
            "WHERE team_role='giants' AND player_canonical IS NOT NULL"
        )
    ]
    candidates: list[dict] = []
    for p in players:
        for fn in (detect_slot_change_jump, detect_first_appearance_in_slot):
            r = fn(conn, player_canonical=p)
            if r:
                candidates.append(_finalize(r, run_id=run_id, created_at=created_at))
    return candidates


def _finalize(row: dict, *, run_id: str, created_at: str) -> dict:
    evidence = row.pop("evidence", None)
    return {
        "run_id": run_id,
        "game_id": None,
        "player_canonical": row.get("player_canonical"),
        "player_display": row.get("player_display"),
        "signal_type": row["signal_type"],
        "magnitude": row.get("magnitude"),
        "baseline_value": row.get("baseline_value"),
        "current_value": row.get("current_value"),
        "window_label": row.get("window_label"),
        "comparison_target": row.get("comparison_target"),
        "evidence_json": json.dumps(evidence, ensure_ascii=False) if evidence else None,
        "priority": row.get("priority", 3),
        "status": "NEW",
        "created_at": created_at,
        "notes": row.get("notes"),
    }
