"""Tests for src.analysis.insight_markdown_summary."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.analysis import insight_etl, insight_markdown_summary as md

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "data" / "insight" / "schema.sql"


def _new_db(tmp_path: Path) -> Path:
    db = tmp_path / "insight.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return db


def _seed_run(db_path: Path, run_id: str, run_ts: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, n_candidates) "
        "VALUES (?,?,?,?,?)",
        (run_id, run_ts, None, None, 0),
    )
    conn.commit()
    conn.close()


def _seed_candidate(
    db_path: Path,
    *,
    run_id: str,
    signal_type: str,
    player: str,
    priority: int = 2,
    game_id: str = None,
    notes: str = "test",
    evidence: dict | None = None,
):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO article_candidates (
            run_id, game_id, player_canonical, player_display,
            signal_type, magnitude, baseline_value, current_value,
            window_label, comparison_target, evidence_json,
            priority, status, created_at, notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id, game_id, player, player,
            signal_type, 1.0, "base", "curr",
            "win", "tgt",
            json.dumps(evidence or {"k": "v"}, ensure_ascii=False),
            priority, "NEW", "2026-05-13T00:00:00+00:00", notes,
        ),
    )
    conn.commit()
    conn.close()


# ─── helpers ─────────────────────────────────────────────────────────────


def test_categorize_buckets():
    assert md._categorize("batter_homerun") == "batting"
    assert md._categorize("starter_quality_start") == "pitching"
    assert md._categorize("lineup_slot_jump_up") == "lineup"
    assert md._categorize("unknown_signal_xyz") == "other"


def test_excerpt_truncates_long_text():
    assert md._excerpt("a" * 200, 50).endswith("…")
    assert md._excerpt("short", 50) == "short"
    assert md._excerpt(None, 50) == ""


def test_format_evidence_handles_dict_json():
    ev = json.dumps({"x": 1, "y": "abc"}, ensure_ascii=False)
    out = md._format_evidence(ev)
    assert "x=1" in out


def test_format_evidence_handles_garbage():
    assert md._format_evidence("not json") == "not json"


# ─── render ──────────────────────────────────────────────────────────────


def test_render_digest_empty_input():
    md_text = md.render_digest_markdown([], game_date="2026-05-10")
    assert "2026-05-10" in md_text
    assert "候補なし" in md_text


def test_render_digest_categorizes_rows():
    rows = [
        {"signal_type": "batter_homerun", "priority": 1,
         "player_canonical": "ダルベック", "current_value": "H3/AB4",
         "baseline_value": None, "window_label": "single_game",
         "comparison_target": None, "notes": "MVP", "evidence_json": "{}"},
        {"signal_type": "pitcher_workload_warning", "priority": 1,
         "player_canonical": "ライデル", "current_value": "190 球",
         "baseline_value": "150", "window_label": "7days",
         "comparison_target": "threshold", "notes": "負荷", "evidence_json": "{}"},
        {"signal_type": "lineup_slot_jump_up", "priority": 2,
         "player_canonical": "佐々木", "current_value": "今試合1番",
         "baseline_value": "前6番", "window_label": "2starts",
         "comparison_target": "self", "notes": "起用", "evidence_json": "{}"},
    ]
    text = md.render_digest_markdown(rows, game_date="2026-05-10")
    assert "## 打撃シグナル" in text
    assert "## 投球シグナル" in text
    assert "## 起用シグナル" in text
    assert "ダルベック" in text
    assert "ライデル" in text
    assert "佐々木" in text


def test_render_digest_other_section_for_unknown_signals():
    rows = [
        {"signal_type": "totally_new_signal", "priority": 3,
         "player_canonical": "X", "current_value": "v",
         "baseline_value": None, "window_label": None,
         "comparison_target": None, "notes": "n", "evidence_json": None},
    ]
    text = md.render_digest_markdown(rows, game_date="2026-05-10")
    assert "## その他" in text
    assert "totally_new_signal" in text


# ─── DB-backed paths ─────────────────────────────────────────────────────


def test_fetch_candidates_filtered_by_game_date(tmp_path):
    db = _new_db(tmp_path)
    _seed_run(db, "r1", "2026-05-10T22:00:00+00:00")
    _seed_run(db, "r2", "2026-05-12T22:00:00+00:00")
    _seed_candidate(db, run_id="r1", signal_type="batter_homerun",
                    player="A", game_id="2026-05-10:d-g-08")
    _seed_candidate(db, run_id="r2", signal_type="batter_homerun",
                    player="B", game_id="2026-05-12:c-g-01")
    conn = sqlite3.connect(str(db))
    rows = md.fetch_candidates_for_digest(conn, game_date="2026-05-10")
    assert {r["player_canonical"] for r in rows} == {"A"}
    conn.close()


def test_fetch_candidates_filtered_by_since_run_ts(tmp_path):
    db = _new_db(tmp_path)
    _seed_run(db, "r1", "2026-05-10T22:00:00+00:00")
    _seed_run(db, "r2", "2026-05-12T22:00:00+00:00")
    _seed_candidate(db, run_id="r1", signal_type="batter_homerun", player="A")
    _seed_candidate(db, run_id="r2", signal_type="batter_homerun", player="B")
    conn = sqlite3.connect(str(db))
    rows = md.fetch_candidates_for_digest(
        conn, since_run_ts="2026-05-11T00:00:00+00:00"
    )
    assert {r["player_canonical"] for r in rows} == {"B"}
    conn.close()


def test_write_digest_creates_file_even_when_empty(tmp_path):
    out = tmp_path / "digest" / "2026-05-10.md"
    n = md.write_digest(
        db_path=tmp_path / "nonexistent.db",
        out_path=out,
        game_date="2026-05-10",
    )
    assert n == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "2026-05-10" in text


def test_write_digest_renders_real_rows(tmp_path):
    db = _new_db(tmp_path)
    _seed_run(db, "r1", "2026-05-10T22:00:00+00:00")
    _seed_candidate(db, run_id="r1", signal_type="batter_multi_hit",
                    player="ダルベック")
    out = tmp_path / "digest" / "2026-05-10.md"
    n = md.write_digest(db_path=db, out_path=out, game_date="2026-05-10")
    assert n == 1
    text = out.read_text(encoding="utf-8")
    assert "## 打撃シグナル" in text
    assert "ダルベック" in text


def test_write_digest_orders_by_priority_then_magnitude(tmp_path):
    db = _new_db(tmp_path)
    _seed_run(db, "r1", "2026-05-10T22:00:00+00:00")
    _seed_candidate(db, run_id="r1", signal_type="batter_homerun",
                    player="LowPri", priority=3)
    _seed_candidate(db, run_id="r1", signal_type="batter_homerun",
                    player="HighPri", priority=1)
    out = tmp_path / "digest" / "2026-05-10.md"
    md.write_digest(db_path=db, out_path=out, game_date="2026-05-10")
    text = out.read_text(encoding="utf-8")
    assert text.index("HighPri") < text.index("LowPri")
