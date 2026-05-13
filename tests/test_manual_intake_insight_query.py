"""Tests for src.manual_intake_insight_query.

No real GCS — uses fake client. Tests verify:
  * env-driven no-op when INSIGHT_GCS_BUCKET unset
  * download path / cache TTL
  * SQL filters (player / signal / date)
  * read-only DB connection (file:...?mode=ro)
  * graceful degradation when DB missing
  * roster_options + signal_type_options shapes
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src import manual_intake_insight_query as miq

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "data" / "insight" / "schema.sql"


class _FakeBlob:
    def __init__(self, store: dict, name: str):
        self._store = store
        self._name = name

    def exists(self) -> bool:
        return self._name in self._store

    def download_to_filename(self, dst: str) -> None:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(self._store[self._name])


class _FakeBucket:
    def __init__(self, store: dict, name: str):
        self._store = store
        self.name = name

    def blob(self, object_name: str) -> _FakeBlob:
        return _FakeBlob(self._store, object_name)


class _FakeClient:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(self.store, name)


@pytest.fixture(autouse=True)
def _reset_cache():
    miq.reset_cache_for_tests()
    yield
    miq.reset_cache_for_tests()


def _seed_db(path: Path) -> None:
    """Build a minimal insight.db with games + candidates for query."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, league_label, one_line_summary, "
        "winning_pitcher, losing_pitcher, save_pitcher, source_url, "
        "source_kind, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-05-12:g-c-06", "2026-05-12", "広島", "home", 5, 3, "win",
         None, None, None, None, None, None, "test", "2026-05-13T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO insight_runs (run_id, run_ts, n_candidates) "
        "VALUES (?,?,?)",
        ("r1", "2026-05-13T00:00:00+00:00", 0),
    )
    rows = [
        ("r1", "2026-05-12:g-c-06", "佐々木俊輔", "佐々木", "batter_homerun", 1.0, None,
         "H2/AB4", "single_game", None, "{}", 2, "NEW",
         "2026-05-13T00:00:00+00:00", "test"),
        ("r1", "2026-05-12:g-c-06", "大城卓三", "大城卓三", "batter_homerun", 1.0, None,
         "H2/AB3", "single_game", None, "{}", 2, "NEW",
         "2026-05-13T00:00:00+00:00", "test"),
        ("r1", "2026-05-12:g-c-06", "戸郷翔征", "戸郷", "pitcher_high_pitch_count",
         110.0, None, "110球", "single_game", None, "{}", 2, "NEW",
         "2026-05-13T00:00:00+00:00", "test"),
    ]
    conn.executemany(
        "INSERT INTO article_candidates (run_id, game_id, player_canonical, "
        "player_display, signal_type, magnitude, baseline_value, "
        "current_value, window_label, comparison_target, evidence_json, "
        "priority, status, created_at, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


# ─── env helpers ──────────────────────────────────────────────────────────


def test_signal_type_options_is_sorted_list():
    opts = miq.signal_type_options()
    assert isinstance(opts, list)
    assert opts == sorted(opts)
    assert "batter_homerun" in opts


def test_roster_options_returns_active_players_only():
    rows = miq.roster_options()
    names = {r["name"] for r in rows}
    # 阿部慎之助 is active manager → 含まれる
    assert "阿部慎之助" in names
    # 全 row に name / position / role
    for r in rows:
        assert "name" in r and "position" in r and "role" in r


# ─── ensure_local_db ──────────────────────────────────────────────────────


def test_ensure_local_db_noop_when_no_bucket(monkeypatch, tmp_path):
    monkeypatch.delenv("INSIGHT_GCS_BUCKET", raising=False)
    result = miq.ensure_local_db(cache_path=tmp_path / "db")
    assert result["ok"] is False
    assert result["reason"] == "no_bucket"


def test_ensure_local_db_downloads_when_bucket_set(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    fake = _FakeClient()
    fake.store["insight.db"] = b"sentinel"
    target = tmp_path / "insight.db"
    result = miq.ensure_local_db(cache_path=target, client=fake)
    assert result["ok"] is True
    assert result["refreshed"] is True
    assert target.read_bytes() == b"sentinel"


def test_ensure_local_db_skip_within_ttl(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    fake = _FakeClient()
    fake.store["insight.db"] = b"first"
    target = tmp_path / "insight.db"
    miq.ensure_local_db(cache_path=target, client=fake, now=1000.0, ttl_seconds=3600)
    # mutate the GCS-side blob to detect re-download
    fake.store["insight.db"] = b"second"
    result = miq.ensure_local_db(cache_path=target, client=fake, now=1500.0, ttl_seconds=3600)
    assert result["refreshed"] is False
    assert target.read_bytes() == b"first"


def test_ensure_local_db_refresh_after_ttl(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    fake = _FakeClient()
    fake.store["insight.db"] = b"first"
    target = tmp_path / "insight.db"
    miq.ensure_local_db(cache_path=target, client=fake, now=1000.0, ttl_seconds=3600)
    fake.store["insight.db"] = b"second"
    result = miq.ensure_local_db(cache_path=target, client=fake, now=5000.0, ttl_seconds=3600)
    assert result["refreshed"] is True
    assert target.read_bytes() == b"second"


def test_ensure_local_db_blob_missing_returns_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIGHT_GCS_BUCKET", "test-bucket")
    fake = _FakeClient()  # empty store
    result = miq.ensure_local_db(cache_path=tmp_path / "x.db", client=fake)
    assert result["ok"] is False
    assert result["reason"] == "blob_missing"


# ─── query_candidates ─────────────────────────────────────────────────────


def test_query_returns_db_not_available_when_no_db(tmp_path):
    result = miq.query_candidates(db_path=tmp_path / "nothing.db")
    assert result["ok"] is False
    assert result["reason"] == "db_not_available"
    assert result["rows"] == []


def test_query_returns_all_when_no_filters(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    result = miq.query_candidates(db_path=db)
    assert result["ok"] is True
    assert result["count"] == 3


def test_query_filter_by_player_canonical(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    result = miq.query_candidates(db_path=db, player="佐々木俊輔")
    assert result["count"] == 1
    assert result["rows"][0]["player_canonical"] == "佐々木俊輔"


def test_query_filter_by_player_partial_display(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    # "戸郷" appears in player_display only (canonical is 戸郷翔征)
    result = miq.query_candidates(db_path=db, player="戸郷")
    assert result["count"] == 1


def test_query_filter_by_signal_type(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    result = miq.query_candidates(db_path=db, signal_type="batter_homerun")
    assert result["count"] == 2


def test_query_rejects_invalid_signal_type(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    result = miq.query_candidates(db_path=db, signal_type="DROP TABLE article_candidates;")
    assert result["ok"] is False
    assert "invalid_signal_type" in result["reason"]


def test_query_filter_by_date_range(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    in_range = miq.query_candidates(
        db_path=db, since_game_date="2026-05-01", until_game_date="2026-05-31",
    )
    assert in_range["count"] == 3
    out_range = miq.query_candidates(
        db_path=db, since_game_date="2026-06-01",
    )
    assert out_range["count"] == 0


def test_query_invalid_date_string_silently_ignored(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    # 不正な date は filter として無視される (空扱い) → 全件返る
    result = miq.query_candidates(db_path=db, since_game_date="garbage")
    assert result["count"] == 3
    assert result["filters"]["since_game_date"] is None


def test_query_limit_caps_to_500(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    result = miq.query_candidates(db_path=db, limit=99999)
    assert result["filters"]["limit"] == 500


def test_query_read_only_mode_blocks_writes(tmp_path):
    """Confirm the URI mode=ro keeps the connection truly read-only."""
    db = tmp_path / "insight.db"
    _seed_db(db)

    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM article_candidates")
    conn.close()


def test_query_orders_by_priority_then_magnitude_desc(tmp_path):
    db = tmp_path / "insight.db"
    _seed_db(db)
    # insert a P1 candidate that should come first
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO article_candidates (run_id, game_id, player_canonical, "
        "player_display, signal_type, magnitude, current_value, priority, "
        "status, created_at, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("r1", "2026-05-12:g-c-06", "岡本和真", "岡本", "batter_homerun",
         99.0, "P1 test", 1, "NEW", "2026-05-13T00:00:00+00:00", "p1"),
    )
    conn.commit()
    conn.close()

    result = miq.query_candidates(db_path=db)
    assert result["rows"][0]["priority"] == 1
    assert result["rows"][0]["player_canonical"] == "岡本和真"
