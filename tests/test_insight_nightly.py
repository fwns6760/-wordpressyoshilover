"""Tests for src.analysis.insight_nightly (orchestrator).

CRITICAL invariant: no real HTTP. The fetcher cache is pre-populated so
``cache_or_fetch`` never reaches the network. ``allow_live=False`` is
the default.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from src.analysis import insight_fetcher, insight_nightly, insight_schedule

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


def test_auto_target_date_uses_yesterday_before_afternoon():
    JST = dt.timezone(dt.timedelta(hours=9))
    target = insight_schedule.auto_target_jst_date(
        dt.datetime(2026, 5, 16, 12, 0, tzinfo=JST),
    )
    assert target == dt.date(2026, 5, 15)


def test_auto_target_date_uses_today_from_afternoon():
    JST = dt.timezone(dt.timedelta(hours=9))
    target = insight_schedule.auto_target_jst_date(
        dt.datetime(2026, 5, 16, 15, 0, tzinfo=JST),
    )
    assert target == dt.date(2026, 5, 16)


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


def test_cli_requires_slug_or_auto(tmp_path, capsys):
    rc = insight_nightly.main(["--db", str(tmp_path / "x.db")])
    assert rc == 2
    out = capsys.readouterr().out
    assert "must pass --slug or --auto" in out


def test_resolve_slug_auto_uses_cached_schedule(tmp_path):
    """slug 自動解決が cache から動くことを確認、実 HTTP 0 件。"""
    cache_dir = tmp_path / "raw_html"
    cache_dir.mkdir(parents=True)
    # monthly schedule cache を仕込む
    (cache_dir / "schedule_2026_05.html").write_text(
        '<a href="/scores/2026/0510/d-g-08/box.html">x</a>',
        encoding="utf-8",
    )
    slug = insight_nightly.resolve_slug_auto(
        target_date=dt.date(2026, 5, 10),
        allow_live=False,
        cache_dir=cache_dir,
    )
    assert slug == "2026/0510/d-g-08"


def test_resolve_slug_auto_falls_back_to_daily_cache(tmp_path):
    """月別 schedule が無くても日次 schedule cache から解決できる。"""
    cache_dir = tmp_path / "raw_html"
    cache_dir.mkdir(parents=True)
    (cache_dir / "schedule_2026-05-10_daily.html").write_text(
        '<a href="/scores/2026/0510/c-g-04/box.html">x</a>',
        encoding="utf-8",
    )
    slug = insight_nightly.resolve_slug_auto(
        target_date=dt.date(2026, 5, 10),
        allow_live=False,
        cache_dir=cache_dir,
    )
    assert slug == "2026/0510/c-g-04"


def test_resolve_slug_auto_fails_without_cache_and_not_live(tmp_path):
    with pytest.raises(insight_fetcher.FetchBlocked):
        insight_nightly.resolve_slug_auto(
            target_date=dt.date(2026, 5, 10),
            allow_live=False,
            cache_dir=tmp_path / "raw_html",
        )


def test_resolve_all_slugs_auto_no_game_day_from_readable_monthly_schedule(tmp_path):
    cache_dir = tmp_path / "raw_html"
    cache_dir.mkdir(parents=True)
    (cache_dir / "schedule_2026_05.html").write_text(
        '<a href="/scores/2026/0517/d-g-08/box.html">previous day</a>',
        encoding="utf-8",
    )
    with pytest.raises(insight_nightly.NoScheduledGames) as excinfo:
        insight_nightly.resolve_all_slugs_auto(
            target_date=dt.date(2026, 5, 18),
            allow_live=False,
            cache_dir=cache_dir,
        )
    assert excinfo.value.scope == "npb"
    assert excinfo.value.target_date == dt.date(2026, 5, 18)


def test_resolve_slug_auto_no_giants_game_when_other_games_exist(tmp_path):
    cache_dir = tmp_path / "raw_html"
    cache_dir.mkdir(parents=True)
    (cache_dir / "schedule_2026_05.html").write_text(
        '<a href="/scores/2026/0518/t-yb-08/box.html">阪神 vs DeNA</a>',
        encoding="utf-8",
    )
    with pytest.raises(insight_nightly.NoScheduledGames) as excinfo:
        insight_nightly.resolve_slug_auto(
            target_date=dt.date(2026, 5, 18),
            allow_live=False,
            cache_dir=cache_dir,
        )
    assert excinfo.value.scope == "giants"
    assert excinfo.value.target_date == dt.date(2026, 5, 18)


def test_cli_all_teams_no_game_day_returns_zero(tmp_path, capsys):
    cache_dir = tmp_path / "raw_html"
    cache_dir.mkdir(parents=True)
    (cache_dir / "schedule_2026_05.html").write_text(
        '<a href="/scores/2026/0517/d-g-08/box.html">previous day</a>',
        encoding="utf-8",
    )
    rc = insight_nightly.main([
        "--auto", "--all-teams",
        "--date", "2026-05-18",
        "--db", str(tmp_path / "db.sqlite"),
        "--csv", str(tmp_path / "candidates.csv"),
        "--cache-dir", str(cache_dir),
        "--digest-dir", str(tmp_path / "digest"),
    ])
    assert rc == 0
    body = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert body["status"] == "no_game_day"
    assert body["game_date"] == "2026-05-18"
    assert body["scope"] == "npb"
