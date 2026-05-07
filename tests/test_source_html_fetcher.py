"""Tests for src/source_html_fetcher.py — NOMOTOKE-BODY-EXTRACT-001 Phase 1A.

Acceptance gate (zero real network):

- HTTP is supplied via DI (``http_client`` arg). The default ``RequestsHttpClient``
  is **never instantiated** in any Phase 1A test.
- Robots allow / deny / unavailable-defaults-allow paths are exercised via
  ``FakeHttpClient`` returning canned ``robots.txt`` payloads.
- 4xx / 5xx → ``fetch_forbidden`` skip with status_code preserved.
- URL cache: hit returns the previously cached FetchResult flagged
  ``cache_hit=True``; expired TTL re-fetches via the http_client.
- Per-host rate limiter calls clock.sleep() the right amount and records
  per-host last-fetch times.
- User-Agent header is fixed at ``YoshiloverBot/1.0`` on every GET.
- Module source is asserted to NOT pull ``requests`` at import time
  (RequestsHttpClient defers the import to ``__init__``).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.source_html_fetcher import (  # noqa: E402
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_PER_HOST_RATE_INTERVAL_SECONDS,
    SKIP_REASON_FETCH_FORBIDDEN,
    SKIP_REASON_META_UNAVAILABLE_OUT,
    SKIP_REASON_ROBOTS_BLOCKED,
    USER_AGENT,
    Clock,
    FetchCache,
    FetchResult,
    HttpClient,
    HttpResponse,
    RobotsChecker,
    RobotsDecision,
    _DefaultRobotsChecker,
    _PerHostRateLimiter,
    fetch_source_meta,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "source_html"


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeClock:
    """Manually-advanced clock for cache TTL + rate-limiter assertions."""

    def __init__(self, t0: float = 1000.0) -> None:
        self.t = t0
        self.sleep_calls: List[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        # Record but do NOT actually sleep — tests must not block.
        if seconds > 0:
            self.sleep_calls.append(seconds)
            self.t += seconds


class FakeHttpClient:
    """Deterministic in-memory HTTP. Maps url → HttpResponse and records
    every GET so tests can assert UA / call count / order.
    """

    def __init__(self) -> None:
        self._routes: Dict[str, HttpResponse] = {}
        self._exception_routes: Dict[str, Exception] = {}
        self.calls: List[Dict[str, object]] = []

    def add(self, url: str, *, status_code: int, text: str = "", headers: Optional[Dict[str, str]] = None) -> None:
        self._routes[url] = HttpResponse(
            status_code=status_code,
            text=text,
            headers=headers or {},
            final_url=url,
        )

    def add_error(self, url: str, exc: Exception) -> None:
        self._exception_routes[url] = exc

    def get(self, url: str, *, headers: Dict[str, str], timeout: float) -> HttpResponse:
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        if url in self._exception_routes:
            raise self._exception_routes[url]
        if url not in self._routes:
            return HttpResponse(status_code=404, text="", headers={}, final_url=url)
        return self._routes[url]


class AlwaysAllowRobots:
    def is_allowed(self, *, url: str, user_agent: str) -> RobotsDecision:
        return RobotsDecision(allowed=True, reason="")


class AlwaysDenyRobots:
    def is_allowed(self, *, url: str, user_agent: str) -> RobotsDecision:
        return RobotsDecision(allowed=False, reason="robots_disallow")


class RecordingRateLimiter:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def acquire(self, *, host: str) -> None:
        self.calls.append(host)


# ---------------------------------------------------------------------------
# Robots: allow / deny / unavailable
# ---------------------------------------------------------------------------


class RobotsAllowDenyTests(unittest.TestCase):
    def test_robots_disallow_short_circuits_with_robots_blocked(self):
        http = FakeHttpClient()
        http.add(
            "https://example.com/article",
            status_code=200,
            text=_load_fixture("hochi_news_sample.html"),
        )
        clock = FakeClock()
        rl = RecordingRateLimiter()
        result = fetch_source_meta(
            "https://example.com/article",
            http_client=http,
            robots_checker=AlwaysDenyRobots(),
            rate_limiter=rl,
            clock=clock,
        )
        self.assertTrue(result.is_skipped())
        self.assertEqual(result.skip_reason, SKIP_REASON_ROBOTS_BLOCKED)
        self.assertEqual(result.robots_decision_reason, "robots_disallow")
        # No GET issued when robots blocks; no rate-limiter acquire either.
        self.assertEqual(http.calls, [])
        self.assertEqual(rl.calls, [])

    def test_robots_allow_proceeds_to_get(self):
        http = FakeHttpClient()
        http.add(
            "https://example.com/article",
            status_code=200,
            text=_load_fixture("hochi_news_sample.html"),
        )
        clock = FakeClock()
        result = fetch_source_meta(
            "https://example.com/article",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            rate_limiter=RecordingRateLimiter(),
            clock=clock,
        )
        self.assertFalse(result.is_skipped(), result.to_dict())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(http.calls), 1)

    def test_robots_unavailable_default_allow_via_robots_checker(self):
        # The DefaultRobotsChecker decides the policy; its
        # ``robots_unavailable_default_allow`` reason flows through to the
        # FetchResult when we use its decision directly.
        class FakeRobots(RobotsChecker):
            def is_allowed(self, *, url, user_agent):
                return RobotsDecision(
                    allowed=True, reason="robots_unavailable_default_allow"
                )

        http = FakeHttpClient()
        http.add(
            "https://example.com/article",
            status_code=200,
            text=_load_fixture("hochi_news_sample.html"),
        )
        result = fetch_source_meta(
            "https://example.com/article",
            http_client=http,
            robots_checker=FakeRobots(),
            clock=FakeClock(),
        )
        self.assertFalse(result.is_skipped())
        # Decision reason is recorded only on blocked path; pass-through
        # FetchResult does not carry it.
        self.assertEqual(result.skip_reason, "")


# ---------------------------------------------------------------------------
# DefaultRobotsChecker (parses robots.txt via injected HTTP)
# ---------------------------------------------------------------------------


class DefaultRobotsCheckerTests(unittest.TestCase):
    def _checker(self, robots_text: str, *, status: int = 200) -> _DefaultRobotsChecker:
        http = FakeHttpClient()
        http.add(
            "https://example.com/robots.txt",
            status_code=status,
            text=robots_text,
        )
        self._http = http
        return _DefaultRobotsChecker(http_client=http)

    def test_robots_disallow_for_yoshilover_bot(self):
        rp = self._checker(
            "User-agent: YoshiloverBot\nDisallow: /\n"
        )
        decision = rp.is_allowed(
            url="https://example.com/article", user_agent=USER_AGENT
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "robots_disallow")

    def test_robots_disallow_for_star_default(self):
        rp = self._checker(
            "User-agent: *\nDisallow: /private/\n"
        )
        decision = rp.is_allowed(
            url="https://example.com/private/article",
            user_agent=USER_AGENT,
        )
        self.assertFalse(decision.allowed)

    def test_robots_allows_when_no_relevant_rule(self):
        rp = self._checker(
            "User-agent: Googlebot\nDisallow: /private/\n"
        )
        decision = rp.is_allowed(
            url="https://example.com/article", user_agent=USER_AGENT
        )
        self.assertTrue(decision.allowed)

    def test_robots_unavailable_defaults_to_allow(self):
        rp = self._checker("", status=404)
        decision = rp.is_allowed(
            url="https://example.com/article", user_agent=USER_AGENT
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "robots_unavailable_default_allow")

    def test_robots_check_caches_per_host(self):
        rp = self._checker("User-agent: *\nDisallow: /private/\n")
        rp.is_allowed(url="https://example.com/a", user_agent=USER_AGENT)
        rp.is_allowed(url="https://example.com/b", user_agent=USER_AGENT)
        # Only ONE GET to robots.txt across two checks.
        robots_calls = [c for c in self._http.calls if c["url"].endswith("/robots.txt")]
        self.assertEqual(len(robots_calls), 1)


# ---------------------------------------------------------------------------
# 403 / 404 / 5xx → fetch_forbidden
# ---------------------------------------------------------------------------


class FetchForbiddenTests(unittest.TestCase):
    def test_403_marks_fetch_forbidden(self):
        http = FakeHttpClient()
        http.add("https://giants.jp/G/news.html", status_code=403, text="forbidden")
        result = fetch_source_meta(
            "https://giants.jp/G/news.html",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=FakeClock(),
        )
        self.assertTrue(result.is_skipped())
        self.assertEqual(result.skip_reason, SKIP_REASON_FETCH_FORBIDDEN)
        self.assertEqual(result.status_code, 403)

    def test_500_marks_fetch_forbidden(self):
        http = FakeHttpClient()
        http.add("https://example.com/x", status_code=500, text="boom")
        result = fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=FakeClock(),
        )
        self.assertEqual(result.skip_reason, SKIP_REASON_FETCH_FORBIDDEN)

    def test_get_exception_marks_fetch_forbidden(self):
        http = FakeHttpClient()
        http.add_error("https://example.com/x", ConnectionError("net down"))
        result = fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=FakeClock(),
        )
        self.assertEqual(result.skip_reason, SKIP_REASON_FETCH_FORBIDDEN)


# ---------------------------------------------------------------------------
# meta_unavailable propagated from extractor
# ---------------------------------------------------------------------------


class MetaUnavailableTests(unittest.TestCase):
    def test_meta_unavailable_when_response_has_no_og_no_jsonld(self):
        http = FakeHttpClient()
        http.add(
            "https://example.com/x",
            status_code=200,
            text=_load_fixture("meta_unavailable_sample.html"),
        )
        result = fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=FakeClock(),
        )
        self.assertEqual(result.skip_reason, SKIP_REASON_META_UNAVAILABLE_OUT)
        self.assertEqual(result.status_code, 200)


# ---------------------------------------------------------------------------
# Cache hit + TTL expiry
# ---------------------------------------------------------------------------


class CacheTests(unittest.TestCase):
    def test_cache_hit_returns_immediately_without_get(self):
        http = FakeHttpClient()
        http.add(
            "https://example.com/x",
            status_code=200,
            text=_load_fixture("hochi_news_sample.html"),
        )
        clock = FakeClock()
        cache = FetchCache(clock=clock)
        # First fetch: cache miss → 1 GET.
        r1 = fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=clock,
            cache=cache,
        )
        self.assertFalse(r1.cache_hit)
        self.assertEqual(len(http.calls), 1)
        # Second fetch within TTL: cache hit → 0 additional GETs.
        r2 = fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=clock,
            cache=cache,
        )
        self.assertTrue(r2.cache_hit)
        self.assertEqual(len(http.calls), 1)

    def test_cache_expired_after_ttl_re_fetches(self):
        http = FakeHttpClient()
        http.add(
            "https://example.com/x",
            status_code=200,
            text=_load_fixture("hochi_news_sample.html"),
        )
        clock = FakeClock()
        cache = FetchCache(clock=clock, ttl_seconds=10)
        fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=clock,
            cache=cache,
        )
        clock.t += 11  # past TTL
        r2 = fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=clock,
            cache=cache,
        )
        self.assertFalse(r2.cache_hit)
        self.assertEqual(len(http.calls), 2)

    def test_cache_default_ttl_is_six_hours(self):
        self.assertEqual(DEFAULT_CACHE_TTL_SECONDS, 6 * 60 * 60)

    def test_robots_blocked_result_is_cached_to_avoid_repeat_robots_check(self):
        # Even a denial entry should be cached; otherwise we re-check
        # robots.txt (and thus issue a GET to robots.txt) every time.
        http = FakeHttpClient()
        clock = FakeClock()
        cache = FetchCache(clock=clock)
        fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysDenyRobots(),
            clock=clock,
            cache=cache,
        )
        r2 = fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysDenyRobots(),
            clock=clock,
            cache=cache,
        )
        self.assertTrue(r2.cache_hit)
        self.assertEqual(r2.skip_reason, SKIP_REASON_ROBOTS_BLOCKED)


# ---------------------------------------------------------------------------
# Per-host rate limiter
# ---------------------------------------------------------------------------


class RateLimiterTests(unittest.TestCase):
    def test_first_call_does_not_sleep(self):
        clock = FakeClock(t0=100.0)
        rl = _PerHostRateLimiter(clock=clock, interval_seconds=1.0)
        rl.acquire(host="hochi.news")
        self.assertEqual(clock.sleep_calls, [])

    def test_second_call_inside_interval_sleeps_remaining(self):
        clock = FakeClock(t0=100.0)
        rl = _PerHostRateLimiter(clock=clock, interval_seconds=1.0)
        rl.acquire(host="hochi.news")
        clock.t = 100.3  # only 0.3s passed
        rl.acquire(host="hochi.news")
        # FakeClock records the sleep amount; should be ~0.7s (1.0 - 0.3).
        self.assertEqual(len(clock.sleep_calls), 1)
        self.assertAlmostEqual(clock.sleep_calls[0], 0.7, places=2)

    def test_separate_hosts_do_not_block_each_other(self):
        clock = FakeClock(t0=100.0)
        rl = _PerHostRateLimiter(clock=clock, interval_seconds=1.0)
        rl.acquire(host="hochi.news")
        rl.acquire(host="sanspo.com")
        # Different host → no sleep.
        self.assertEqual(clock.sleep_calls, [])

    def test_default_interval_is_one_second(self):
        self.assertEqual(DEFAULT_PER_HOST_RATE_INTERVAL_SECONDS, 1.0)

    def test_rate_limiter_is_acquired_on_each_live_fetch(self):
        http = FakeHttpClient()
        http.add(
            "https://example.com/x",
            status_code=200,
            text=_load_fixture("hochi_news_sample.html"),
        )
        rl = RecordingRateLimiter()
        fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            rate_limiter=rl,
            clock=FakeClock(),
        )
        self.assertEqual(rl.calls, ["example.com"])


# ---------------------------------------------------------------------------
# UA fixed at YoshiloverBot/1.0
# ---------------------------------------------------------------------------


class UserAgentFixedTests(unittest.TestCase):
    def test_user_agent_constant_value(self):
        self.assertEqual(USER_AGENT, "YoshiloverBot/1.0 (+https://yoshilover.com/)")

    def test_get_call_sends_yoshilover_bot_user_agent(self):
        http = FakeHttpClient()
        http.add(
            "https://example.com/x",
            status_code=200,
            text=_load_fixture("hochi_news_sample.html"),
        )
        fetch_source_meta(
            "https://example.com/x",
            http_client=http,
            robots_checker=AlwaysAllowRobots(),
            clock=FakeClock(),
        )
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(http.calls[0]["headers"]["User-Agent"], USER_AGENT)


# ---------------------------------------------------------------------------
# No real network in the fetcher module's import surface
# ---------------------------------------------------------------------------


class NoLiveNetworkAtImportTests(unittest.TestCase):
    """Phase 1A acceptance: importing the module must not pull ``requests``
    into the process. The live ``RequestsHttpClient`` defers ``import
    requests`` to ``__init__`` so simply importing src.source_html_fetcher
    does not load it.
    """

    def test_module_does_not_top_level_import_requests(self):
        src = (ROOT / "src" / "source_html_fetcher.py").read_text(
            encoding="utf-8"
        )
        # Must not have a top-level ``import requests`` line at column 0.
        for line in src.splitlines():
            if line.startswith("import requests") or line.startswith("from requests"):
                self.fail(
                    "Phase 1A must defer ``requests`` import; found top-level: "
                    + line
                )

    def test_no_eager_pipeline_construction_at_import(self):
        src = (ROOT / "src" / "source_html_fetcher.py").read_text(
            encoding="utf-8"
        )
        # ``RequestsHttpClient`` / ``build_default_pipeline`` must not be
        # invoked at module top level.
        for needle in (
            "\nRequestsHttpClient()",
            "\nbuild_default_pipeline()",
        ):
            self.assertNotIn(
                needle,
                src,
                "Phase 1A must not eagerly build a live pipeline at import",
            )


# ---------------------------------------------------------------------------
# URL guard
# ---------------------------------------------------------------------------


class UrlGuardTests(unittest.TestCase):
    def test_empty_url_skips(self):
        result = fetch_source_meta(
            "",
            http_client=FakeHttpClient(),
            robots_checker=AlwaysAllowRobots(),
            clock=FakeClock(),
        )
        self.assertEqual(result.skip_reason, SKIP_REASON_FETCH_FORBIDDEN)

    def test_unsafe_scheme_skips(self):
        result = fetch_source_meta(
            "javascript:alert(1)",
            http_client=FakeHttpClient(),
            robots_checker=AlwaysAllowRobots(),
            clock=FakeClock(),
        )
        self.assertEqual(result.skip_reason, SKIP_REASON_FETCH_FORBIDDEN)


if __name__ == "__main__":
    unittest.main()
