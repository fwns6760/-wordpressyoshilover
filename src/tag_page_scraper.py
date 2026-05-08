"""Tag/index page scraper for trusted media that lack a working public RSS feed.

RELIABILITY-2026-05-08-A+B: hochi.news の RSS は 2024 以降 404 で死んでおり、
sponichi / sanspo / daily.co.jp は元々 RSS feed が公開されていない。X account 経由
でしか article を拾えていなかったのが yoshilover 流量低下の構造的真因。本 module
は各 trusted media の tag/index page を HTML 取得 → article URL 抽出 → 個別 article
metadata (og:title / og:description / article:published_time) 取得して feedparser
entries 互換 dict のリストを返す。

返り値の dict は src/rss_fetcher.py が `feed.entries` に対して使う key だけ埋める:
    - link: article 絶対 URL
    - title: og:title or タグ page anchor text
    - summary: og:description (article lead 200 chars 程度)
    - published_parsed: time.struct_time (article:published_time から)
    - published: RFC822 風 string
    - id: link と同じ

使用 module は標準 lib (requests / re / html.parser / time / datetime) のみ。
bs4 / lxml は導入していない。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from typing import Any, Callable, Iterable

import requests

JST = timezone(timedelta(hours=9))


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; yoshilover-fetcher/1.0; +https://yoshilover.com/)"
)


class _OgMetaExtractor(HTMLParser):
    """軽量 HTMLParser で <meta property="og:..."> / <meta name="..."> を全部拾う。

    bs4 / lxml なしで動かすため標準 lib のみ。tag page には大量の inline JS / GTM
    タグがあるが、無視して <meta> だけ拾えればよい。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        prop = attr_dict.get("property") or attr_dict.get("name")
        content = attr_dict.get("content")
        if not prop or content is None:
            return
        # 上書きしない (最初の値を keep) — hochi 等は同じ key を 2 回書くサイトもある
        if prop not in self.meta:
            self.meta[prop] = content


def _extract_og_meta(html_text: str) -> dict[str, str]:
    parser = _OgMetaExtractor()
    try:
        parser.feed(html_text)
    except Exception:  # noqa: BLE001 — HTMLParser が壊れた markup で raise した場合 fallback
        # regex fallback
        meta: dict[str, str] = {}
        for m in re.finditer(
            r'<meta[^>]+(?:property|name)=[\"\']([^\"\']+)[\"\'][^>]+content=[\"\']([^\"\']*)[\"\']',
            html_text,
            flags=re.IGNORECASE,
        ):
            key, val = m.group(1), m.group(2)
            if key not in meta:
                meta[key] = val
        return meta
    return parser.meta


def _parse_iso8601_to_struct_time(value: str) -> time.struct_time | None:
    """`article:published_time` の ISO8601 を time.struct_time に変換。失敗時 None。"""
    if not value:
        return None
    try:
        # python 3.11+ なら fromisoformat が tz 含み OK。fallback で `+00:00` 指定。
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.astimezone(timezone.utc).timetuple()


def _struct_time_to_rfc822(st: time.struct_time | None) -> str:
    if st is None:
        return ""
    try:
        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", st)
    except (TypeError, ValueError):
        return ""


def _is_ymd_within_window(yyyymmdd: str, *, max_age_days: int, now: datetime) -> bool:
    """URL から拾った YYYYMMDD が「今日から N 日以内」か判定 (cheap pre-filter)。"""
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return False
    try:
        dt = datetime(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]), tzinfo=JST)
    except ValueError:
        return False
    age = now.astimezone(JST) - dt
    return timedelta(0) <= age <= timedelta(days=max_age_days + 1)


def _http_get(
    url: str,
    *,
    timeout: float = 10.0,
    user_agent: str = _DEFAULT_USER_AGENT,
    fetcher: Callable[..., requests.Response] | None = None,
) -> requests.Response | None:
    fetcher = fetcher or requests.get
    try:
        response = fetcher(url, timeout=timeout, headers={"User-Agent": user_agent})
    except Exception:  # noqa: BLE001 — DNS / connection error 等は logger に任せて None 返す
        return None
    return response


# ──────────────────────────────────────────────────────────────────────────────
# scraper kind 別ロジック
# ──────────────────────────────────────────────────────────────────────────────


_HOCHI_ARTICLE_PATH_RE = re.compile(r"/articles/(\d{8})-([A-Z0-9_]+)\.html")


def fetch_hochi_giants_entries(
    *,
    tag_url: str = "https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    """hochi 巨人 tag page から最近 N 日分の article entries を返す。

    1. tag page 取得 → /articles/YYYYMMDD-CODE.html URL 一覧抽出
    2. URL の date 部分で max_age_days 内にフィルタ
    3. 上位 article_limit 件まで個別 article 取得 → og メタから entry dict 構成
    4. feedparser entries 互換のリスト返却 (link / title / summary /
       published_parsed / published / id)
    """
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    response = _http_get(tag_url, fetcher=fetcher)
    if response is None or response.status_code != 200:
        logger.warning(
            "tag_page_fetch_failed source=hochi tag_url=%s status=%s",
            tag_url,
            getattr(response, "status_code", "ERR"),
        )
        return []

    text = response.text
    seen_urls: list[str] = []
    seen_set: set[str] = set()
    for match in _HOCHI_ARTICLE_PATH_RE.finditer(text):
        date_str, code = match.group(1), match.group(2)
        if not _is_ymd_within_window(date_str, max_age_days=max_age_days, now=reference_now):
            continue
        article_url = f"https://hochi.news/articles/{date_str}-{code}.html"
        if article_url in seen_set:
            continue
        seen_set.add(article_url)
        seen_urls.append(article_url)

    if not seen_urls:
        logger.info("tag_page_no_recent_articles source=hochi tag_url=%s", tag_url)
        return []

    seen_urls = seen_urls[:article_limit]
    logger.info(
        "tag_page_articles_extracted source=hochi count=%d (after age %dd / limit %d)",
        len(seen_urls),
        max_age_days,
        article_limit,
    )

    entries: list[dict[str, Any]] = []
    for article_url in seen_urls:
        article_response = _http_get(article_url, fetcher=fetcher)
        if article_response is None or article_response.status_code != 200:
            logger.info(
                "tag_page_article_fetch_failed source=hochi url=%s status=%s",
                article_url,
                getattr(article_response, "status_code", "ERR"),
            )
            continue
        meta = _extract_og_meta(article_response.text)
        title = (meta.get("og:title") or "").strip()
        # hochi の og:title は「... - スポーツ報知」末尾を持つので取る
        title = re.sub(r"\s*[\-―ー]\s*スポーツ報知\s*$", "", title)
        summary = (meta.get("og:description") or meta.get("description") or "").strip()
        published_struct = _parse_iso8601_to_struct_time(
            meta.get("article:published_time", "")
        )
        if published_struct is None:
            # URL から日付を抽出して 12:00 JST を fallback published 時刻にする
            url_match = _HOCHI_ARTICLE_PATH_RE.search(article_url)
            if url_match:
                date_str = url_match.group(1)
                fallback_dt = datetime(
                    int(date_str[:4]),
                    int(date_str[4:6]),
                    int(date_str[6:8]),
                    12,
                    0,
                    0,
                    tzinfo=JST,
                )
                published_struct = fallback_dt.astimezone(timezone.utc).timetuple()
        entry: dict[str, Any] = {
            "link": article_url,
            "id": article_url,
            "title": title,
            "summary": summary,
            "description": summary,
        }
        if published_struct is not None:
            entry["published_parsed"] = published_struct
            entry["published"] = _struct_time_to_rfc822(published_struct)
        entries.append(entry)

    logger.info(
        "tag_page_entries_built source=hochi count=%d (out of %d candidates)",
        len(entries),
        len(seen_urls),
    )
    return entries


# ──────────────────────────────────────────────────────────────────────────────
# scraper dispatch table
# ──────────────────────────────────────────────────────────────────────────────


_SCRAPER_REGISTRY: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "hochi_giants_tag": fetch_hochi_giants_entries,
}


def fetch_tag_page_entries(
    *,
    scraper: str,
    url: str,
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    """rss_fetcher から呼ばれる top-level dispatch。scraper 名で実装を選ぶ。"""
    logger = logger or logging.getLogger("tag_page_scraper")
    fn = _SCRAPER_REGISTRY.get(scraper)
    if fn is None:
        logger.warning("tag_page_scraper_unknown scraper=%s url=%s", scraper, url)
        return []
    return fn(
        tag_url=url,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=now,
        fetcher=fetcher,
    )


def list_scraper_kinds() -> Iterable[str]:
    return tuple(_SCRAPER_REGISTRY.keys())
