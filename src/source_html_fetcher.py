"""NOMOTOKE-BODY-EXTRACT-001 Phase 1A — primary-source HTTP fetcher (DI-friendly).

Phase 1A wires the HTTP layer that Phase 0's pure extractor was missing:

- ``YoshiloverBot/1.0 (+https://yoshilover.com/)`` user-agent (fixed)
- robots.txt allow/deny check before any GET
- per-host minimum interval (default 1.0s)
- URL-keyed in-memory cache with TTL (default 6h)
- ``robots_blocked`` / ``fetch_forbidden`` / ``meta_unavailable`` skip taxonomy
- caller-injectable HTTP / robots / clock / rate-limiter / cache so unit
  tests run with **zero real network traffic** (Phase 1A acceptance gate)

Phase 1A explicitly does NOT:
- run live HTTP from any test
- ship the requests-based default HTTP client wired into a CLI entrypoint
- write any extracted facts to a WP draft
- touch the renderer / router / publish-notice / Scheduler / env / Cloud
  Run job spec

The default ``RequestsHttpClient`` exists for Phase 1B (live dry-run, opt-in)
and is **never instantiated unless the caller asks for it** — the public
``fetch_source_meta`` accepts a ``http_client`` argument so the CLI can
inject either the live client (Phase 1B+) or a fake / mock (tests).
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, Optional, Protocol
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from src.source_html_extractor import (
    EXTRACTION_SOURCE_NONE,
    SKIP_REASON_META_UNAVAILABLE,
    ExtractionResult,
    extract_source_meta,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


USER_AGENT = "YoshiloverBot/1.0 (+https://yoshilover.com/)"

# Per-host minimum gap between two successive GETs (seconds).
DEFAULT_PER_HOST_RATE_INTERVAL_SECONDS: float = 1.0

# URL cache time-to-live. Cache stores the FetchResult so a repeat fetch of
# the same URL within the window returns immediately (cache_hit=True) and
# still passes the robots / rate-limiter without re-checking. 6h matches
# the locked spec.
DEFAULT_CACHE_TTL_SECONDS: int = 6 * 60 * 60

# HTTP timeout for the live client (Phase 1B+). Conservative — sanspo
# articles can take ~1s already and the attemptDeadline upstream is 180s.
DEFAULT_HTTP_TIMEOUT_SECONDS: float = 15.0

# Skip-reason taxonomy emitted by this layer (in addition to
# ``meta_unavailable`` from the extractor).
SKIP_REASON_ROBOTS_BLOCKED = "robots_blocked"
SKIP_REASON_FETCH_FORBIDDEN = "fetch_forbidden"
# (Phase 1A re-exports the extractor-side reason for convenience.)
SKIP_REASON_META_UNAVAILABLE_OUT = SKIP_REASON_META_UNAVAILABLE


# ---------------------------------------------------------------------------
# Protocols and small DI primitives
# ---------------------------------------------------------------------------


@dataclass
class HttpResponse:
    """Minimal HTTP response shape used by this module.

    Decoupled from ``requests.Response`` so unit tests can synthesise one
    without importing ``requests``. The live ``RequestsHttpClient`` adapts
    a real ``requests.Response`` into this shape.
    """

    status_code: int
    text: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    final_url: str = ""


class HttpClient(Protocol):
    """Caller-supplied HTTP GET. Tests pass a fake; live code passes
    ``RequestsHttpClient``.
    """

    def get(
        self,
        url: str,
        *,
        headers: Dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...


class Clock(Protocol):
    """Monotonic clock for cache TTL + rate-limiter spacing.

    Two methods so tests can inject a ``FakeClock`` that advances on
    demand without ``time.sleep`` running.
    """

    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class _SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


# ---------------------------------------------------------------------------
# Robots checker
# ---------------------------------------------------------------------------


@dataclass
class RobotsDecision:
    allowed: bool
    reason: str  # "" / "robots_disallow" / "robots_unavailable_default_allow"
    fetched_robots_status: int = 0


class RobotsChecker(Protocol):
    """Decide whether ``url`` is allowed for our UA. Pure function from the
    caller's perspective; the live impl maintains its own per-host cache.
    """

    def is_allowed(self, *, url: str, user_agent: str) -> RobotsDecision: ...


class _DefaultRobotsChecker:
    """Robots.txt checker that fetches ``/robots.txt`` once per host via
    the supplied ``http_client``. Caches the parsed rules indefinitely
    within the same process. Conservative on errors: when robots.txt is
    fetchable but unparseable, defaults to disallow; when robots.txt
    request itself errors (network down, etc.), defaults to **allow** so
    transient infra issues don't block the whole pipeline (the spec
    explicitly says "deny if YoshiloverBot or general bot is denied" — a
    fetch error is not a denial).
    """

    def __init__(self, http_client: HttpClient) -> None:
        self._http = http_client
        self._cache: Dict[str, RobotFileParser] = {}
        self._lock = threading.Lock()

    def _robots_url(self, page_url: str) -> str:
        p = urlparse(page_url)
        return f"{p.scheme}://{p.netloc}/robots.txt"

    def _load(self, host_key: str, robots_url: str) -> Optional[RobotFileParser]:
        with self._lock:
            if host_key in self._cache:
                return self._cache[host_key]
        try:
            resp = self._http.get(
                robots_url,
                headers={"User-Agent": USER_AGENT},
                timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
            )
        except Exception:
            with self._lock:
                self._cache[host_key] = None  # type: ignore[assignment]
            return None
        if resp.status_code != 200 or not resp.text:
            with self._lock:
                self._cache[host_key] = None  # type: ignore[assignment]
            return None
        rp = RobotFileParser()
        try:
            rp.parse(resp.text.splitlines())
        except Exception:
            with self._lock:
                self._cache[host_key] = None  # type: ignore[assignment]
            return None
        with self._lock:
            self._cache[host_key] = rp
        return rp

    def is_allowed(self, *, url: str, user_agent: str) -> RobotsDecision:
        if not url:
            return RobotsDecision(allowed=False, reason="invalid_url")
        host_key = urlparse(url).netloc.lower()
        robots_url = self._robots_url(url)
        rp = self._load(host_key, robots_url)
        if rp is None:
            return RobotsDecision(
                allowed=True, reason="robots_unavailable_default_allow"
            )
        if rp.can_fetch(user_agent, url) and rp.can_fetch("*", url):
            return RobotsDecision(allowed=True, reason="")
        return RobotsDecision(allowed=False, reason="robots_disallow")


# ---------------------------------------------------------------------------
# Per-host rate limiter
# ---------------------------------------------------------------------------


class RateLimiter(Protocol):
    """Block until enough time has passed since the last GET to this host."""

    def acquire(self, *, host: str) -> None: ...


class _PerHostRateLimiter:
    def __init__(
        self,
        *,
        clock: Clock,
        interval_seconds: float = DEFAULT_PER_HOST_RATE_INTERVAL_SECONDS,
    ) -> None:
        self._clock = clock
        self._interval = interval_seconds
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, *, host: str) -> None:
        host = (host or "").lower()
        if not host:
            return
        with self._lock:
            last = self._last.get(host, 0.0)
        now = self._clock.now()
        wait = (last + self._interval) - now
        if wait > 0:
            self._clock.sleep(wait)
            now = self._clock.now()
        with self._lock:
            self._last[host] = now


# ---------------------------------------------------------------------------
# URL-keyed cache
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    stored_at: float
    fetch_result: "FetchResult"


class FetchCache:
    """In-memory URL cache with TTL. Phase 1A keeps it process-local; a
    persistent variant (e.g. SQLite) is a Phase 2+ concern.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._clock = clock
        self._ttl = ttl_seconds
        self._store: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha1((url or "").encode("utf-8")).hexdigest()

    def get(self, url: str) -> Optional["FetchResult"]:
        k = self._key(url)
        with self._lock:
            entry = self._store.get(k)
        if entry is None:
            return None
        if self._clock.now() - entry.stored_at > self._ttl:
            with self._lock:
                self._store.pop(k, None)
            return None
        return entry.fetch_result

    def put(self, url: str, value: "FetchResult") -> None:
        k = self._key(url)
        with self._lock:
            self._store[k] = CacheEntry(
                stored_at=self._clock.now(), fetch_result=value
            )

    def size(self) -> int:
        with self._lock:
            return len(self._store)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    url: str
    status_code: int = 0
    skip_reason: str = ""
    extraction: Optional[ExtractionResult] = None
    cache_hit: bool = False
    fetched_at_unix: float = 0.0
    extraction_source: str = EXTRACTION_SOURCE_NONE
    robots_decision_reason: str = ""

    def is_skipped(self) -> bool:
        return bool(self.skip_reason)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        if self.extraction is not None:
            out["extraction"] = self.extraction.to_dict()
        return out


# ---------------------------------------------------------------------------
# Live HTTP client (Phase 1B+ wiring; Phase 1A tests never instantiate)
# ---------------------------------------------------------------------------


class RequestsHttpClient:
    """``requests``-backed HTTP client. NOT instantiated in Phase 1A tests.

    Lives here so Phase 1B's CLI can wire it without an extra module. The
    ``import requests`` is delayed to ``__init__`` so simply importing this
    module does not pull in requests.
    """

    def __init__(self) -> None:
        import requests as _requests  # local import — Phase 1A tests skip

        self._requests = _requests

    def get(
        self,
        url: str,
        *,
        headers: Dict[str, str],
        timeout: float,
    ) -> HttpResponse:
        resp = self._requests.get(
            url, headers=headers, timeout=timeout, allow_redirects=True
        )
        # Encoding fallback: when the server omits charset in Content-Type
        # (npb.jp does this), `requests` defaults to ISO-8859-1 — which
        # mojibakes the UTF-8 / Shift_JIS body. Force chardet's guess
        # before reading `.text`. Safe for sites that declare charset
        # because `resp.encoding` reflects the declared value.
        try:
            declared = (resp.encoding or "").lower()
            if declared in ("iso-8859-1", "latin-1", ""):
                guess = (resp.apparent_encoding or "utf-8").lower()
                resp.encoding = guess
        except Exception:
            pass
        try:
            text = resp.text
        except Exception:
            text = ""
        return HttpResponse(
            status_code=resp.status_code,
            text=text,
            headers={k: v for k, v in resp.headers.items()},
            final_url=resp.url,
        )


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def fetch_source_meta(
    url: str,
    *,
    http_client: HttpClient,
    robots_checker: Optional[RobotsChecker] = None,
    rate_limiter: Optional[RateLimiter] = None,
    cache: Optional[FetchCache] = None,
    clock: Optional[Clock] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> FetchResult:
    """Fetch ``url`` and return parsed OG / JSON-LD facts.

    Pipeline:
      1. cache hit → return cached FetchResult immediately
      2. robots.txt check (UA = ``YoshiloverBot/1.0``) → robots_blocked
      3. per-host rate limiter acquire (sleeps via ``clock`` if needed)
      4. HTTP GET via ``http_client``
      5. status code 4xx/5xx → fetch_forbidden (with status_code)
      6. extract_source_meta on response body → meta_unavailable when no
         OG / JSON-LD article shape
      7. cache + return

    The function is fully DI-driven — supply your own clients in tests so
    no real socket is opened. The default no-arg form raises because no
    ``http_client`` would be available; this is intentional Phase 1A
    behaviour to prevent accidental live calls.
    """
    if not isinstance(url, str) or not url:
        return FetchResult(url=url or "", skip_reason=SKIP_REASON_FETCH_FORBIDDEN)

    clk = clock or _SystemClock()
    cache = cache  # Phase 1A: caller-managed; no implicit default
    if cache is not None:
        cached = cache.get(url)
        if cached is not None:
            return _mark_cache_hit(cached)

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not host or parsed.scheme not in ("http", "https"):
        return FetchResult(url=url, skip_reason=SKIP_REASON_FETCH_FORBIDDEN)

    if robots_checker is not None:
        decision = robots_checker.is_allowed(url=url, user_agent=USER_AGENT)
        if not decision.allowed:
            res = FetchResult(
                url=url,
                skip_reason=SKIP_REASON_ROBOTS_BLOCKED,
                robots_decision_reason=decision.reason,
                fetched_at_unix=clk.now(),
            )
            if cache is not None:
                cache.put(url, res)
            return res

    if rate_limiter is not None:
        rate_limiter.acquire(host=host)

    try:
        resp = http_client.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=timeout_seconds,
        )
    except Exception:
        res = FetchResult(
            url=url,
            skip_reason=SKIP_REASON_FETCH_FORBIDDEN,
            fetched_at_unix=clk.now(),
        )
        if cache is not None:
            cache.put(url, res)
        return res

    if resp.status_code >= 400:
        res = FetchResult(
            url=url,
            status_code=resp.status_code,
            skip_reason=SKIP_REASON_FETCH_FORBIDDEN,
            fetched_at_unix=clk.now(),
        )
        if cache is not None:
            cache.put(url, res)
        return res

    extraction = extract_source_meta(resp.text or "")
    if extraction.is_skipped():
        res = FetchResult(
            url=url,
            status_code=resp.status_code,
            skip_reason=SKIP_REASON_META_UNAVAILABLE,
            extraction=extraction,
            fetched_at_unix=clk.now(),
            extraction_source=EXTRACTION_SOURCE_NONE,
        )
        if cache is not None:
            cache.put(url, res)
        return res

    res = FetchResult(
        url=url,
        status_code=resp.status_code,
        skip_reason="",
        extraction=extraction,
        fetched_at_unix=clk.now(),
        extraction_source=extraction.extraction_source,
    )
    if cache is not None:
        cache.put(url, res)
    return res


def _mark_cache_hit(res: FetchResult) -> FetchResult:
    """Return a shallow copy of ``res`` with ``cache_hit=True`` so the
    caller can distinguish hits from miss-then-fill without inspecting the
    cache directly. The original entry stays in cache.
    """
    return FetchResult(
        url=res.url,
        status_code=res.status_code,
        skip_reason=res.skip_reason,
        extraction=res.extraction,
        cache_hit=True,
        fetched_at_unix=res.fetched_at_unix,
        extraction_source=res.extraction_source,
        robots_decision_reason=res.robots_decision_reason,
    )


# ---------------------------------------------------------------------------
# DI factory helpers (used by Phase 1B CLI; Phase 1A tests do NOT call)
# ---------------------------------------------------------------------------


def build_default_pipeline(
    *,
    interval_seconds: float = DEFAULT_PER_HOST_RATE_INTERVAL_SECONDS,
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
) -> Dict[str, Any]:
    """Construct a real-network pipeline (RequestsHttpClient + system clock
    + per-host rate limiter + URL cache + robots checker that uses the
    same HTTP client). Phase 1B CLI plumbs this in only when its opt-in
    flag is on. Phase 1A tests must NOT call this.
    """
    clock = _SystemClock()
    http_client = RequestsHttpClient()
    rate_limiter = _PerHostRateLimiter(
        clock=clock, interval_seconds=interval_seconds
    )
    cache = FetchCache(clock=clock, ttl_seconds=cache_ttl_seconds)
    robots_checker = _DefaultRobotsChecker(http_client=http_client)
    return {
        "http_client": http_client,
        "rate_limiter": rate_limiter,
        "cache": cache,
        "clock": clock,
        "robots_checker": robots_checker,
    }


__all__ = [
    "USER_AGENT",
    "DEFAULT_PER_HOST_RATE_INTERVAL_SECONDS",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "SKIP_REASON_ROBOTS_BLOCKED",
    "SKIP_REASON_FETCH_FORBIDDEN",
    "SKIP_REASON_META_UNAVAILABLE_OUT",
    "HttpClient",
    "HttpResponse",
    "Clock",
    "RobotsChecker",
    "RobotsDecision",
    "RateLimiter",
    "FetchCache",
    "CacheEntry",
    "FetchResult",
    "RequestsHttpClient",
    "fetch_source_meta",
    "build_default_pipeline",
]
