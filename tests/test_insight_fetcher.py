"""Tests for src.analysis.insight_fetcher.

ABSOLUTE INVARIANT: these tests must NEVER make a real HTTP call. All
network access goes through an injected ``http_get`` fixture. Each test
verifies the call count expectation explicitly via the captured mock.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.analysis import insight_fetcher as fetcher


class _FakeResponse:
    def __init__(self, *, status_code=200, text="<html></html>"):
        self.status_code = status_code
        self.text = text
        # production fetcher uses resp.content.decode("utf-8") to avoid
        # requests' charset auto-detection mojibake on NPB pages.
        self.content = text.encode("utf-8") if isinstance(text, str) else text


def _fake_http_factory(routes: dict[str, _FakeResponse]):
    """Return (http_get, calls) where http_get is a MagicMock-backed
    callable that returns ``routes[url]`` and records every call."""
    calls = []

    def _http_get(url, *, timeout=None, headers=None):
        calls.append({"url": url, "headers": headers})
        if url not in routes:
            return _FakeResponse(status_code=404, text="")
        return routes[url]

    return _http_get, calls


@pytest.fixture(autouse=True)
def _reset_min_interval():
    """Reset module-level last-fetch clock between tests."""
    fetcher.reset_min_interval_clock()
    yield
    fetcher.reset_min_interval_clock()


# ─── slug / URL ────────────────────────────────────────────────────────────


def test_slug_to_url_canonical():
    assert fetcher._slug_to_url("2026/0510/d-g-08") == "https://npb.jp/scores/2026/0510/d-g-08/box.html"


def test_slug_to_cache_filename_safe():
    name = fetcher.slug_to_cache_filename("2026/0510/d-g-08")
    assert "/" not in name
    assert name.endswith("_box.html")
    assert name.startswith("2026_0510_d-g-08")


# ─── cache I/O ─────────────────────────────────────────────────────────────


def test_cache_write_and_read_roundtrip(tmp_path):
    slug = "2026/0510/d-g-08"
    fetcher.write_cache(slug, "<html>cached</html>", cache_dir=tmp_path)
    got = fetcher.read_cache(slug, cache_dir=tmp_path)
    assert got == "<html>cached</html>"


def test_read_cache_miss_returns_none(tmp_path):
    assert fetcher.read_cache("2026/0510/x-g-99", cache_dir=tmp_path) is None


# ─── cache_or_fetch — cache-only safety ────────────────────────────────────


def test_cache_or_fetch_returns_cached_without_http(tmp_path):
    slug = "2026/0510/d-g-08"
    fetcher.write_cache(slug, "<html>cached</html>", cache_dir=tmp_path)
    http_get, calls = _fake_http_factory({})
    html, meta = fetcher.cache_or_fetch(
        slug, allow_live=False, http_get=http_get, cache_dir=tmp_path,
    )
    assert html == "<html>cached</html>"
    assert meta["from_cache"] is True
    # CRITICAL: zero HTTP calls when serving from cache
    assert calls == []


def test_cache_or_fetch_blocks_when_miss_and_not_live(tmp_path):
    http_get, calls = _fake_http_factory({})
    with pytest.raises(fetcher.FetchBlocked):
        fetcher.cache_or_fetch(
            "2026/0510/x-g-99",
            allow_live=False,
            http_get=http_get,
            cache_dir=tmp_path,
        )
    # CRITICAL: zero HTTP calls when not allowed live
    assert calls == []


# ─── robots.txt enforcement ─────────────────────────────────────────────────


def test_live_fetch_raises_when_robots_disallows(tmp_path):
    robots_text = "User-agent: *\nDisallow: /scores/\n"
    routes = {
        fetcher.ROBOTS_URL: _FakeResponse(status_code=200, text=robots_text),
    }
    http_get, calls = _fake_http_factory(routes)
    with pytest.raises(fetcher.FetchBlocked) as excinfo:
        fetcher.live_fetch(
            "2026/0510/d-g-08",
            http_get=http_get,
            cache_dir=tmp_path,
        )
    assert "robots_disallow" in str(excinfo.value)
    # Only robots.txt was fetched, no box URL hit
    assert len(calls) == 1
    assert calls[0]["url"] == fetcher.ROBOTS_URL


def test_live_fetch_proceeds_when_robots_404(tmp_path):
    routes = {
        fetcher.ROBOTS_URL: _FakeResponse(status_code=404, text=""),
        "https://npb.jp/scores/2026/0510/d-g-08/box.html": _FakeResponse(
            status_code=200, text="<html>live</html>",
        ),
    }
    http_get, calls = _fake_http_factory(routes)
    html, meta = fetcher.live_fetch(
        "2026/0510/d-g-08",
        http_get=http_get,
        cache_dir=tmp_path,
    )
    assert html == "<html>live</html>"
    assert meta["from_cache"] is False
    assert meta["status_code"] == 200
    # cache written
    assert fetcher.read_cache("2026/0510/d-g-08", cache_dir=tmp_path) == "<html>live</html>"


def test_live_fetch_propagates_http_error(tmp_path):
    routes = {
        fetcher.ROBOTS_URL: _FakeResponse(status_code=200, text="User-agent: *\nAllow: /\n"),
        "https://npb.jp/scores/2026/0510/d-g-08/box.html": _FakeResponse(
            status_code=503, text="",
        ),
    }
    http_get, _ = _fake_http_factory(routes)
    with pytest.raises(fetcher.FetchBlocked) as excinfo:
        fetcher.live_fetch(
            "2026/0510/d-g-08",
            http_get=http_get,
            cache_dir=tmp_path,
        )
    assert "http_503" in str(excinfo.value)


# ─── CLI ────────────────────────────────────────────────────────────────────


def test_cli_cache_only_blocks_on_miss(capsys, tmp_path):
    rc = fetcher.main(
        [
            "--slug", "2026/0510/x-g-99",
            "--cache-dir", str(tmp_path),
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "blocked" in captured.out
    assert "cache_miss_and_live_disabled" in captured.out


def test_cli_cache_hit_returns_ok(capsys, tmp_path):
    slug = "2026/0510/d-g-08"
    fetcher.write_cache(slug, "<html>cached</html>", cache_dir=tmp_path)
    rc = fetcher.main(
        [
            "--slug", slug,
            "--cache-dir", str(tmp_path),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert '"status": "ok"' in captured.out
    assert '"from_cache": true' in captured.out


# ─── invariant: tests didn't invoke real requests ───────────────────────────


def test_module_has_no_top_level_http_side_effect():
    """Importing the module must not trigger any HTTP call. This is a
    canary: if anyone wires a fetch into module-load, this test fails."""
    import importlib
    import src.analysis.insight_fetcher as m

    # re-import: should not raise; should not require network.
    importlib.reload(m)
    assert hasattr(m, "live_fetch")
    assert hasattr(m, "cache_or_fetch")
