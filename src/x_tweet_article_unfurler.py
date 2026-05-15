"""Tweet → outbound news-article unfurler for the source-body excerpt block.

For posts whose source is a tweet on twitter.com / x.com, this helper tries to
follow the chain
    tweet URL → oEmbed → t.co short link → final article URL
and, when the final URL points to a whitelisted news publisher, fetches the
article HTML so the standard source-body excerpt block can be inserted by the
existing helper. The function is read-only (no WP writes) and silently returns
empty values on any failure so the caller's fall-through behaviour is
preserved.

Network calls:
    - GET https://publish.twitter.com/oembed (no auth)
    - HEAD t.co/<short>  (follow one redirect)
    - GET <article-url>  (only when host ∈ ALLOWED_ARTICLE_HOSTS)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Tuple
from urllib.parse import urlparse

import requests

ARTICLE_HOST_TO_SOURCE_NAME: dict[str, str] = {
    # 既存 5 媒体 (実機抽出 OK 確認済)
    "hochi.news": "スポーツ報知",
    "www.hochi.news": "スポーツ報知",
    "sanspo.com": "サンスポ",
    "www.sanspo.com": "サンスポ",
    "daily.co.jp": "デイリースポーツ",
    "www.daily.co.jp": "デイリースポーツ",
    "nikkansports.com": "日刊スポーツ",
    "www.nikkansports.com": "日刊スポーツ",
    "sponichi.co.jp": "スポニチ",
    "www.sponichi.co.jp": "スポニチ",
    # 2026-05-15 新規追加: 実機 verify で本文 590/570 字抽出確認
    "full-count.jp": "Full-Count",
    "www.full-count.jp": "Full-Count",
    "news.yahoo.co.jp": "Yahoo!ニュース",
    # 2026-05-15 forward-coverage 追加 (現時点 extractor は body 0 だが、
    # 将来 JSON-LD 対応 or 個別 selector 追加で extractor 改善時に効く):
    "giants.jp": "読売ジャイアンツ公式",
    "www.giants.jp": "読売ジャイアンツ公式",
    "npb.jp": "NPB公式",
    "www.npb.jp": "NPB公式",
    "mainichi.jp": "毎日新聞",
    "www.mainichi.jp": "毎日新聞",
    "asahi.com": "朝日新聞",
    "www.asahi.com": "朝日新聞",
    "sankei.com": "産経新聞",
    "www.sankei.com": "産経新聞",
    "chunichi.co.jp": "中日スポーツ",
    "www.chunichi.co.jp": "中日スポーツ",
    "number.bunshun.jp": "Number Web",
}
ALLOWED_ARTICLE_HOSTS = frozenset(ARTICLE_HOST_TO_SOURCE_NAME.keys())


def source_name_for_article_url(article_url: str) -> str:
    try:
        host = urlparse(article_url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
    return ARTICLE_HOST_TO_SOURCE_NAME.get(host, "")

_TWEET_HOST_RE = re.compile(r"^(?:[a-z0-9-]+\.)?(?:twitter\.com|x\.com)$", re.I)
_TCO_HREF_RE = re.compile(r'href="(https?://t\.co/[A-Za-z0-9]+)"')

_OEMBED_URL = "https://publish.twitter.com/oembed"
_HTTP_TIMEOUT = 8.0
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; yoshilover-fetcher/1.0; "
        "+https://yoshilover.com)"
    ),
}


def is_tweet_url(url: str) -> bool:
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return False
    return bool(_TWEET_HOST_RE.match(host))


def _fetch_tweet_oembed_html(tweet_url: str, logger: logging.Logger) -> str:
    params = {
        "url": tweet_url,
        "omit_script": "true",
        "hide_thread": "true",
        "dnt": "true",
    }
    try:
        r = requests.get(
            _OEMBED_URL,
            params=params,
            headers=_HTTP_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.info("x_unfurl_skip reason=oembed_request_failed err=%s", exc)
        return ""
    if r.status_code != 200:
        logger.info(
            "x_unfurl_skip reason=oembed_http_status status=%d", r.status_code
        )
        return ""
    try:
        payload = r.json()
    except (ValueError, json.JSONDecodeError) as exc:
        logger.info("x_unfurl_skip reason=oembed_json_decode err=%s", exc)
        return ""
    return str(payload.get("html") or "")


def _extract_tco_links(oembed_html: str) -> list[str]:
    return list(dict.fromkeys(_TCO_HREF_RE.findall(oembed_html)))


def _resolve_short_url(short_url: str, logger: logging.Logger) -> str:
    try:
        r = requests.head(
            short_url,
            headers=_HTTP_HEADERS,
            timeout=_HTTP_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        logger.info(
            "x_unfurl_skip reason=tco_head_failed short=%s err=%s",
            short_url,
            exc,
        )
        return ""
    location = r.headers.get("Location", "") or ""
    if not location:
        logger.info("x_unfurl_skip reason=tco_no_location short=%s", short_url)
        return ""
    return location


def _is_allowed_article_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return False
    return host in ALLOWED_ARTICLE_HOSTS


def _fetch_article_html(url: str, logger: logging.Logger) -> str:
    try:
        r = requests.get(url, headers=_HTTP_HEADERS, timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.info(
            "x_unfurl_skip reason=article_get_failed url=%s err=%s", url, exc
        )
        return ""
    if r.status_code != 200:
        logger.info(
            "x_unfurl_skip reason=article_http_status status=%d url=%s",
            r.status_code,
            url,
        )
        return ""
    return r.text


def fetch_outbound_article_for_tweet(
    tweet_url: str, logger: logging.Logger
) -> Tuple[str, str]:
    """Return ``(article_url, article_html)`` for the first whitelisted
    outbound article reachable from ``tweet_url``, or empty strings.
    """
    if not is_tweet_url(tweet_url):
        return "", ""
    oembed_html = _fetch_tweet_oembed_html(tweet_url, logger)
    if not oembed_html:
        return "", ""
    short_links = _extract_tco_links(oembed_html)
    if not short_links:
        logger.info("x_unfurl_skip reason=no_tco_links tweet=%s", tweet_url)
        return "", ""
    for short in short_links:
        resolved = _resolve_short_url(short, logger)
        if not resolved:
            continue
        if not _is_allowed_article_url(resolved):
            logger.info(
                "x_unfurl_skip reason=host_not_allowed url=%s", resolved
            )
            continue
        article_html = _fetch_article_html(resolved, logger)
        if not article_html:
            continue
        logger.info(
            "x_unfurl_article_found tweet=%s article=%s len=%d",
            tweet_url,
            resolved,
            len(article_html),
        )
        return resolved, article_html
    return "", ""
