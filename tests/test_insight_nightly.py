"""Tests for src.analysis.insight_nightly (orchestrator).

CRITICAL invariant: no real HTTP. The fetcher cache is pre-populated so
``cache_or_fetch`` never reaches the network. ``allow_live=False`` is
the default.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis import insight_fetcher, insight_nightly

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "npb_score_2026_0510_d-g-08_box.html"


@pytest.fixture(autouse=True)
def _reset_min_interval():
    insight_fetcher.reset_min_interval_clock()
    yield
    insight_fetcher.reset_min_interval_clock()


# ─── slug helpers ──────────────────────────────────────────────────────────


def test_default_slug_game_id_format():
    assert insight_nightly._default_slug_game_id("2026/0510/d-g-08") == "2026-05-10:d-g-08"


def test_default_game_date_format():
    assert insight_nightly._default_game_date("2026/0510/d-g-08") == "2026-05-10"


def test_default_game_date_blank_on_bad_slug():
    assert insight_nightly._default_game_date("garbage") == ""


# ─── end-to-end orchestration (cache + fixture) ────────────────────────────


def _seed_cache_with_fixture(cache_dir: Path, slug: str = "2026/0510/d-g-08") -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = insight_fetcher.cache_path(slug, cache_dir)
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_nightly_runs_end_to_end_against_cached_html(tmp_path):
    cache_dir = tmp_path / "raw_html"
    _seed_cache_with_fixture(cache_dir)
    summary = insight_nightly.run_nightly(
        slug="2026/0510/d-g-08",
        allow_live=False,
        db_path=tmp_path / "insight.db",
        csv_path=tmp_path / "article_candidates.csv",
        cache_dir=cache_dir,
        digest_dir=tmp_path / "digest",
    )
    assert summary["game_id"] == "2026-05-10:d-g-08"
    assert summary["game_date"] == "2026-05-10"
    assert summary["fetch_meta"]["from_cache"] is True
    assert summary["etl"]["batters_giants"] == 9
    assert summary["lineup_rows"] == 9
    # at least the single-game candidates landed
    assert summary["csv_rows_total"] >= 1
    # digest file emitted
    digest = Path(summary["digest_path"])
    assert digest.exists()
    md = digest.read_text(encoding="utf-8")
    assert "data 分析" in md or "candidates" in md  # title fragment


def test_nightly_blocks_when_cache_miss_and_not_live(tmp_path):
    cache_dir = tmp_path / "raw_html"
    # no cache seeded
    with pytest.raises(insight_fetcher.FetchBlocked):
        insight_nightly.run_nightly(
            slug="2026/0510/d-g-08",
            allow_live=False,
            db_path=tmp_path / "insight.db",
            cache_dir=cache_dir,
            digest_dir=tmp_path / "digest",
        )


def test_nightly_accepts_fetched_html_override(tmp_path):
    """When caller already has HTML in memory, bypass the fetcher entirely."""
    html = FIXTURE.read_text(encoding="utf-8")
    summary = insight_nightly.run_nightly(
        slug="2026/0510/d-g-08",
        allow_live=False,
        fetched_html=html,
        db_path=tmp_path / "insight.db",
        csv_path=tmp_path / "article_candidates.csv",
        cache_dir=tmp_path / "raw_html",  # not used
        digest_dir=tmp_path / "digest",
    )
    assert summary["fetch_meta"]["from_cache"] is False
    assert summary["fetch_meta"]["url"] is None  # bypass mode
    assert summary["etl"]["batters_giants"] == 9


def test_nightly_no_digest_flag(tmp_path):
    cache_dir = tmp_path / "raw_html"
    _seed_cache_with_fixture(cache_dir)
    summary = insight_nightly.run_nightly(
        slug="2026/0510/d-g-08",
        allow_live=False,
        db_path=tmp_path / "insight.db",
        csv_path=tmp_path / "article_candidates.csv",
        cache_dir=cache_dir,
        digest_dir=tmp_path / "digest",
        write_digest=False,
    )
    assert summary["digest_path"] is None


# ─── HTTP invariant ─────────────────────────────────────────────────────────


def test_nightly_does_not_invoke_http_when_cache_hits(tmp_path, monkeypatch):
    """Spy on requests.get; any call must be zero."""
    cache_dir = tmp_path / "raw_html"
    _seed_cache_with_fixture(cache_dir)
    spy_calls = []

    def spy_get(url, **kwargs):
        spy_calls.append(url)
        raise RuntimeError("must not be called: cache should serve")

    import requests
    monkeypatch.setattr(requests, "get", spy_get)

    insight_nightly.run_nightly(
        slug="2026/0510/d-g-08",
        allow_live=False,
        db_path=tmp_path / "insight.db",
        csv_path=tmp_path / "article_candidates.csv",
        cache_dir=cache_dir,
        digest_dir=tmp_path / "digest",
    )
    assert spy_calls == []


# ─── CLI ────────────────────────────────────────────────────────────────────


def test_cli_blocks_on_cache_miss_without_live(tmp_path, capsys):
    rc = insight_nightly.main(
        [
            "--slug", "2026/0510/x-g-99",
            "--db", str(tmp_path / "insight.db"),
            "--csv", str(tmp_path / "candidates.csv"),
            "--cache-dir", str(tmp_path / "raw_html"),
            "--digest-dir", str(tmp_path / "digest"),
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert '"status": "blocked"' in captured.out
    assert "cache_miss_and_live_disabled" in captured.out


def test_cli_runs_with_cache_hit(tmp_path, capsys):
    cache_dir = tmp_path / "raw_html"
    _seed_cache_with_fixture(cache_dir)
    rc = insight_nightly.main(
        [
            "--slug", "2026/0510/d-g-08",
            "--db", str(tmp_path / "insight.db"),
            "--csv", str(tmp_path / "candidates.csv"),
            "--cache-dir", str(cache_dir),
            "--digest-dir", str(tmp_path / "digest"),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    body = json.loads(out.splitlines()[-1])
    assert body["status"] == "ok"
    assert body["game_id"] == "2026-05-10:d-g-08"
