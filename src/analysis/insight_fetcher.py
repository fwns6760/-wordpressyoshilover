"""INSIGHT-002 module 1 — polite NPB box live fetch + cache.

* Cache 先行: `data/insight/raw_html/<slug>.html` が存在すればそれを返す。
* Cache miss + `--live` opt-in のときだけ live HTTP を行う。Claude
  自身は本セッション中 live HTTP を実行しない (user CLI 操作のみ)。
* Polite ルール:
  - User-Agent = ``yoshilover-insight/0.1 (+npb.jp polite scrape)``
  - 同一プロセス内の連続呼び出しは ``MIN_INTERVAL_SECONDS = 5.0`` 秒空ける
  - robots.txt を **取得時** に必ず確認、disallow なら fetch せず例外
  - ``If-Modified-Since`` を cache mtime から付与
  - HTTP 4xx/5xx は retry せず即例外（負荷をかけない）

CLI::

    # cache-only (Claude が安全に呼べる、live HTTP なし)
    python3 -m src.analysis.insight_fetcher --slug 2026/0510/d-g-08

    # live HTTP (user 実行用、明示 --live が必要)
    python3 -m src.analysis.insight_fetcher --slug 2026/0510/d-g-08 --live
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NPB_BASE = "https://npb.jp"
NPB_BOX_TEMPLATE = NPB_BASE + "/scores/{slug}/box.html"
DEFAULT_CACHE_DIR = ROOT / "data" / "insight" / "raw_html"
USER_AGENT = "yoshilover-insight/0.1 (+npb.jp polite scrape; contact: yoshilover.com)"
MIN_INTERVAL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 15
ROBOTS_URL = NPB_BASE + "/robots.txt"

_LAST_FETCH_AT: float = 0.0  # process-local 最終 fetch 時刻


class FetchBlocked(RuntimeError):
    """fetch をブロックすべき条件 (robots disallow / live フラグなし) で raise"""


def _slug_to_url(slug: str) -> str:
    """``2026/0510/d-g-08`` → ``https://npb.jp/scores/2026/0510/d-g-08/box.html``"""
    s = slug.strip("/")
    return NPB_BOX_TEMPLATE.format(slug=s)


def slug_to_cache_filename(slug: str) -> str:
    """URL safe な cache filename を返す。"""
    return slug.strip("/").replace("/", "_") + "_box.html"


def cache_path(slug: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    return cache_dir / slug_to_cache_filename(slug)


def read_cache(slug: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Optional[str]:
    p = cache_path(slug, cache_dir)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def write_cache(slug: str, html: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_path(slug, cache_dir)
    p.write_text(html, encoding="utf-8")
    return p


def _check_robots(http_get) -> None:
    """robots.txt を取得して NPB_BOX_TEMPLATE の path が disallow されて
    いないか確認する。disallow なら :class:`FetchBlocked` を raise。

    `http_get` は :func:`requests.get` 互換 (依存注入で test 可能)。
    """
    sample_url = NPB_BOX_TEMPLATE.format(slug="2026/0101/x-g-01")
    try:
        resp = http_get(ROBOTS_URL, timeout=DEFAULT_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
    except Exception as exc:
        raise FetchBlocked(f"robots_fetch_failed: {exc!r}") from exc
    if resp.status_code == 404:
        # robots.txt がない = 制約なし扱い
        return
    if resp.status_code >= 400:
        raise FetchBlocked(f"robots_fetch_http_{resp.status_code}")
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(resp.text.splitlines())
    if not rp.can_fetch(USER_AGENT, sample_url):
        raise FetchBlocked(f"robots_disallow:{sample_url}")


def _enforce_min_interval(now: Optional[float] = None) -> None:
    """同一プロセス内連続 fetch の間隔を MIN_INTERVAL_SECONDS 以上に保つ。"""
    global _LAST_FETCH_AT
    current = now if now is not None else time.monotonic()
    elapsed = current - _LAST_FETCH_AT
    if _LAST_FETCH_AT > 0 and elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _LAST_FETCH_AT = time.monotonic()


def reset_min_interval_clock() -> None:
    """テスト用。process-local 最終 fetch 時刻を 0 に戻す。"""
    global _LAST_FETCH_AT
    _LAST_FETCH_AT = 0.0


def live_fetch(
    slug: str,
    *,
    http_get=None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    if_modified_since: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[str, dict]:
    """NPB box.html を live HTTP で取得。

    - robots.txt 確認 → disallow なら ``FetchBlocked``
    - 連続呼び出しは MIN_INTERVAL_SECONDS 強制
    - 取得した HTML を cache に書く
    - 戻り値: (html, meta dict)

    ``http_get`` は :func:`requests.get` 互換。テストは mock を渡す。
    本番呼び出しは CLI で ``--live`` 明示時のみ。
    """
    if http_get is None:
        import requests  # vendor / system

        http_get = requests.get
    _check_robots(http_get)
    _enforce_min_interval()
    url = _slug_to_url(slug)
    headers = {"User-Agent": USER_AGENT}
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since
    resp = http_get(url, timeout=timeout, headers=headers)
    if resp.status_code == 304:
        cached = read_cache(slug, cache_dir)
        if cached is None:
            raise FetchBlocked("server_304_but_no_cache")
        return cached, {
            "url": url,
            "status_code": 304,
            "from_cache": True,
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    if resp.status_code >= 400:
        raise FetchBlocked(f"http_{resp.status_code}")
    html = resp.text
    write_cache(slug, html, cache_dir)
    return html, {
        "url": url,
        "status_code": resp.status_code,
        "from_cache": False,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def cache_or_fetch(
    slug: str,
    *,
    allow_live: bool = False,
    http_get=None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> tuple[str, dict]:
    """Cache 先行。miss 時は ``allow_live`` が True のときだけ live fetch。

    既定 ``allow_live=False`` で Claude 自身は live HTTP を呼べない安全側。
    CLI ``--live`` が True を渡したときのみ live fetch が走る。
    """
    cached = read_cache(slug, cache_dir)
    if cached is not None:
        return cached, {
            "url": _slug_to_url(slug),
            "status_code": 200,
            "from_cache": True,
            "fetched_at": None,
        }
    if not allow_live:
        raise FetchBlocked(
            f"cache_miss_and_live_disabled: slug={slug} "
            f"(rerun with --live to allow real HTTP)"
        )
    return live_fetch(slug, http_get=http_get, cache_dir=cache_dir)


# ─── CLI ────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="INSIGHT-002 NPB box polite fetcher (cache-first; --live for real HTTP)."
    )
    p.add_argument(
        "--slug",
        required=True,
        help="NPB score slug, e.g. '2026/0510/d-g-08'",
    )
    p.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help="cache directory (default: data/insight/raw_html)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="allow real HTTP on cache miss (default: cache-only, fail on miss)",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    cache_dir = Path(args.cache_dir)
    try:
        html, meta = cache_or_fetch(args.slug, allow_live=args.live, cache_dir=cache_dir)
    except FetchBlocked as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    out = {
        "status": "ok",
        "slug": args.slug,
        "html_chars": len(html),
        "meta": meta,
        "cache_path": str(cache_path(args.slug, cache_dir)),
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
