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
from html import unescape
from html.parser import HTMLParser
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

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
    """`article:published_time` の ISO8601 を time.struct_time (UTC) に変換。失敗時 None。

    naive datetime (tz 情報なし) は JST と解釈する。理由: scraping 対象は全て日本国内
    media で、og:meta / <time datetime="YYYY-MM-DD"> 等が JST 前提で書かれているため。
    実行環境の local TZ に依存しないために明示的に JST を assign。
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt.astimezone(timezone.utc).timetuple()


def _struct_time_to_rfc822(st: time.struct_time | None) -> str:
    if st is None:
        return ""
    try:
        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", st)
    except (TypeError, ValueError):
        return ""


def _is_ymd_within_window(yyyymmdd: str, *, max_age_days: int, now: datetime) -> bool:
    """URL から拾った YYYYMMDD が「今日から N 日以内」か判定 (cheap pre-filter)。

    age = (now JST date) - (article date); 0 <= age <= max_age_days で True。
    article が「今日」の場合 age=0、article が「max_age_days 日前」で境界 inclusive。
    article 日付が未来 (clock skew) の場合は許容しない (False)。
    """
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return False
    try:
        dt = datetime(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]), tzinfo=JST)
    except ValueError:
        return False
    age_days = (now.astimezone(JST).date() - dt.date()).days
    return 0 <= age_days < max_age_days


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


_GIANTS_TOPIC_KEYWORDS = ("巨人", "読売ジャイアンツ", "ジャイアンツ")
_EMBEDDED_PUBLISHED_DATE_RE = re.compile(
    r'"(?:datePublished|published_at|last_published_date|first_publish_date|original_first_publish_date)"\s*:\s*"([^"]+)"',
    flags=re.IGNORECASE,
)


def _has_giants_topic(title: str, summary: str) -> bool:
    haystack = f"{title} {summary}"
    return any(keyword in haystack for keyword in _GIANTS_TOPIC_KEYWORDS)


def _extract_embedded_published_date(html_text: str) -> str:
    match = _EMBEDDED_PUBLISHED_DATE_RE.search(html_text or "")
    return match.group(1).strip() if match else ""


def _extract_datetime_attr(html_text: str) -> str:
    match = re.search(
        r'\bdatetime=[\"\']([^\"\']{10,40})[\"\']',
        html_text or "",
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _canonical_article_url(raw_url: str, *, base_url: str, keep_query: bool = False) -> str:
    url = urljoin(base_url, unescape(str(raw_url or "").strip()))
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = parts.query if keep_query else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _published_struct_within_window(
    published_struct: time.struct_time,
    *,
    max_age_days: int,
    now: datetime,
) -> bool:
    pub_dt = datetime(*published_struct[:6], tzinfo=timezone.utc).astimezone(JST)
    return _is_ymd_within_window(
        pub_dt.strftime("%Y%m%d"), max_age_days=max_age_days, now=now
    )


def _fallback_struct_from_yyyymmdd(yyyymmdd: str) -> time.struct_time | None:
    if not yyyymmdd or len(yyyymmdd) != 8 or not yyyymmdd.isdigit():
        return None
    try:
        fallback_dt = datetime(
            int(yyyymmdd[:4]),
            int(yyyymmdd[4:6]),
            int(yyyymmdd[6:8]),
            12,
            0,
            0,
            tzinfo=JST,
        )
    except ValueError:
        return None
    return fallback_dt.astimezone(timezone.utc).timetuple()


def _extract_article_urls(
    html_text: str,
    *,
    url_pattern: re.Pattern[str],
    base_url: str,
    keep_query: bool = False,
    url_builder: Callable[[str, str], str] | None = None,
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    builder = url_builder or (
        lambda raw, base: _canonical_article_url(
            raw, base_url=base, keep_query=keep_query
        )
    )
    for match in url_pattern.finditer(html_text or ""):
        raw_url = next((group for group in match.groups() if group), "")
        article_url = builder(raw_url, base_url)
        if not article_url or article_url in seen:
            continue
        seen.add(article_url)
        out.append(article_url)
    return out


def _build_entry_from_article_meta(
    *,
    source: str,
    article_url: str,
    article_html: str,
    title_suffix_re: re.Pattern[str] | None,
    max_age_days: int,
    now: datetime,
    fallback_yyyymmdd: str = "",
    require_giants_topic: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    meta = _extract_og_meta(article_html)
    title = unescape(
        (
            meta.get("og:title")
            or meta.get("twitter:title")
            or meta.get("title")
            or ""
        ).strip()
    )
    if title_suffix_re is not None:
        title = title_suffix_re.sub("", title).strip()
    summary = unescape(
        (
            meta.get("og:description")
            or meta.get("description")
            or meta.get("twitter:description")
            or ""
        ).strip()
    )
    if require_giants_topic and not _has_giants_topic(title, summary):
        return None, "non_giants"
    published_struct = _parse_iso8601_to_struct_time(
        meta.get("article:published_time", "")
        or meta.get("date", "")
        or _extract_embedded_published_date(article_html)
        or _extract_datetime_attr(article_html)
    )
    if published_struct is None and fallback_yyyymmdd:
        published_struct = _fallback_struct_from_yyyymmdd(fallback_yyyymmdd)
    if published_struct is None:
        return None, "date_unknown"
    if not _published_struct_within_window(
        published_struct, max_age_days=max_age_days, now=now
    ):
        return None, "age_filtered"
    if not title:
        return None, "title_empty"
    entry: dict[str, Any] = {
        "link": article_url,
        "id": article_url,
        "title": title,
        "summary": summary,
        "description": summary,
        "published_parsed": published_struct,
        "published": _struct_time_to_rfc822(published_struct),
    }
    return entry, ""


def _fetch_generic_giants_entries(
    *,
    source: str,
    tag_url: str,
    article_url_pattern: re.Pattern[str],
    title_suffix_re: re.Pattern[str] | None,
    max_age_days: int,
    article_limit: int,
    logger: logging.Logger,
    now: datetime,
    fetcher: Callable[..., requests.Response] | None,
    keep_query: bool = False,
    url_date_re: re.Pattern[str] | None = None,
    require_giants_topic: bool = True,
    url_builder: Callable[[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    response = _http_get(tag_url, fetcher=fetcher)
    if response is None or response.status_code != 200:
        logger.warning(
            "tag_page_fetch_failed source=%s tag_url=%s status=%s",
            source,
            tag_url,
            getattr(response, "status_code", "ERR"),
        )
        return []

    article_urls = _extract_article_urls(
        response.text,
        url_pattern=article_url_pattern,
        base_url=tag_url,
        keep_query=keep_query,
        url_builder=url_builder,
    )[:article_limit]
    if not article_urls:
        logger.info("tag_page_no_recent_articles source=%s tag_url=%s", source, tag_url)
        return []

    entries: list[dict[str, Any]] = []
    filtered: dict[str, int] = {
        "non_giants": 0,
        "date_unknown": 0,
        "age_filtered": 0,
        "title_empty": 0,
        "fetch_failed": 0,
    }
    for article_url in article_urls:
        article_response = _http_get(article_url, fetcher=fetcher)
        if article_response is None or article_response.status_code != 200:
            filtered["fetch_failed"] += 1
            logger.info(
                "tag_page_article_fetch_failed source=%s url=%s status=%s",
                source,
                article_url,
                getattr(article_response, "status_code", "ERR"),
            )
            continue
        fallback_date = ""
        if url_date_re is not None:
            date_match = url_date_re.search(article_url)
            fallback_date = date_match.group(1) if date_match else ""
        entry, reason = _build_entry_from_article_meta(
            source=source,
            article_url=article_url,
            article_html=article_response.text,
            title_suffix_re=title_suffix_re,
            max_age_days=max_age_days,
            now=now,
            fallback_yyyymmdd=fallback_date,
            require_giants_topic=require_giants_topic,
        )
        if entry is None:
            filtered[reason] = filtered.get(reason, 0) + 1
            continue
        entries.append(entry)

    logger.info(
        "tag_page_entries_built source=%s count=%d candidates=%d filtered=%s",
        source,
        len(entries),
        len(article_urls),
        filtered,
    )
    return entries


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


_DAILY_ARTICLE_PATH_RE = re.compile(r"/baseball/(\d{4})/(\d{2})/(\d{2})/(\d{10})\.shtml")
_DAILY_TIME_TAG_RE = re.compile(
    r"<time[^>]+datetime=[\"\']([^\"\']+)[\"\']", flags=re.IGNORECASE
)


def fetch_daily_giants_entries(
    *,
    tag_url: str = "https://www.daily.co.jp/baseball/giants/index.shtml",
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    """daily.co.jp 巨人 index page から最近 N 日分の article entries を返す。

    URL pattern: /baseball/YYYY/MM/DD/NNNNNNNNNN.shtml
    Index page (`/baseball/giants/index.shtml`) は giants 限定 curate されている。
    individual article は og:title / og:description あり、article:published_time
    は無いので fallback で <time datetime="YYYY-MM-DD"> tag or URL date を使う。
    """
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    response = _http_get(tag_url, fetcher=fetcher)
    if response is None or response.status_code != 200:
        logger.warning(
            "tag_page_fetch_failed source=daily tag_url=%s status=%s",
            tag_url,
            getattr(response, "status_code", "ERR"),
        )
        return []

    text = response.text
    seen_urls: list[tuple[str, str]] = []  # (article_url, yyyymmdd)
    seen_set: set[str] = set()
    for match in _DAILY_ARTICLE_PATH_RE.finditer(text):
        year, month, day, code = match.groups()
        date_str = f"{year}{month}{day}"
        if not _is_ymd_within_window(date_str, max_age_days=max_age_days, now=reference_now):
            continue
        article_url = f"https://www.daily.co.jp/baseball/{year}/{month}/{day}/{code}.shtml"
        if article_url in seen_set:
            continue
        seen_set.add(article_url)
        seen_urls.append((article_url, date_str))

    if not seen_urls:
        logger.info("tag_page_no_recent_articles source=daily tag_url=%s", tag_url)
        return []

    seen_urls = seen_urls[:article_limit]
    logger.info(
        "tag_page_articles_extracted source=daily count=%d (after age %dd / limit %d)",
        len(seen_urls),
        max_age_days,
        article_limit,
    )

    entries: list[dict[str, Any]] = []
    for article_url, date_str in seen_urls:
        article_response = _http_get(article_url, fetcher=fetcher)
        if article_response is None or article_response.status_code != 200:
            logger.info(
                "tag_page_article_fetch_failed source=daily url=%s status=%s",
                article_url,
                getattr(article_response, "status_code", "ERR"),
            )
            continue
        meta = _extract_og_meta(article_response.text)
        title = (meta.get("og:title") or "").strip()
        # daily og:title は「... /デイリースポーツ online」末尾を持つので取る
        title = re.sub(
            r"\s*[/／]\s*デイリースポーツ\s*online\s*$", "", title, flags=re.IGNORECASE
        )
        summary = (meta.get("og:description") or meta.get("description") or "").strip()
        published_struct = _parse_iso8601_to_struct_time(
            meta.get("article:published_time", "")
        )
        if published_struct is None:
            # <time datetime="YYYY-MM-DDTHH:MM:..."> fallback (時刻情報あれば)
            time_tag_match = _DAILY_TIME_TAG_RE.search(article_response.text)
            if time_tag_match and "T" in time_tag_match.group(1):
                published_struct = _parse_iso8601_to_struct_time(time_tag_match.group(1))
        if published_struct is None:
            # 最終 fallback: URL の date 部分を使い、12:00 JST (article 本文 fetch
            # 直前の最新時点として保守的) を published 時刻として割り当てる。
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
            "published_parsed": published_struct,
            "published": _struct_time_to_rfc822(published_struct),
        }
        entries.append(entry)

    logger.info(
        "tag_page_entries_built source=daily count=%d (out of %d candidates)",
        len(entries),
        len(seen_urls),
    )
    return entries


_SANSPO_ARTICLE_PATH_RE = re.compile(r"/article/(\d{8})-([A-Z0-9]+)/")
_SANSPO_GIANTS_KEYWORDS = ("巨人", "ジャイアンツ", "Giants")


def fetch_sanspo_giants_entries(
    *,
    tag_url: str = "https://www.sanspo.com/?s=%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    """sanspo.com search page で `?s=巨人` 検索結果から巨人記事 entries を返す。

    sanspo は giants tag page を持たず、search のみが事実上の入口。検索結果には
    巨人 keyword を含む非巨人記事(他球団選手のコメントで「巨人」言及等)も混じる
    ため、article fetch 後に title / description が「巨人」または「ジャイアンツ」を
    含むかで post-filter する。
    URL pattern: /article/YYYYMMDD-CODE/
    """
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    response = _http_get(tag_url, fetcher=fetcher)
    if response is None or response.status_code != 200:
        logger.warning(
            "tag_page_fetch_failed source=sanspo tag_url=%s status=%s",
            tag_url,
            getattr(response, "status_code", "ERR"),
        )
        return []

    text = response.text
    seen_urls: list[tuple[str, str]] = []
    seen_set: set[str] = set()
    for match in _SANSPO_ARTICLE_PATH_RE.finditer(text):
        date_str, code = match.groups()
        if not _is_ymd_within_window(date_str, max_age_days=max_age_days, now=reference_now):
            continue
        article_url = f"https://www.sanspo.com/article/{date_str}-{code}/"
        if article_url in seen_set:
            continue
        seen_set.add(article_url)
        seen_urls.append((article_url, date_str))

    if not seen_urls:
        logger.info("tag_page_no_recent_articles source=sanspo tag_url=%s", tag_url)
        return []

    seen_urls = seen_urls[:article_limit]
    logger.info(
        "tag_page_articles_extracted source=sanspo count=%d (after age %dd / limit %d)",
        len(seen_urls),
        max_age_days,
        article_limit,
    )

    entries: list[dict[str, Any]] = []
    filtered_out = 0
    for article_url, date_str in seen_urls:
        article_response = _http_get(article_url, fetcher=fetcher)
        if article_response is None or article_response.status_code != 200:
            logger.info(
                "tag_page_article_fetch_failed source=sanspo url=%s status=%s",
                article_url,
                getattr(article_response, "status_code", "ERR"),
            )
            continue
        meta = _extract_og_meta(article_response.text)
        title = (meta.get("og:title") or "").strip()
        summary = (meta.get("og:description") or meta.get("description") or "").strip()
        # post-filter: title or summary に giants keyword 含むか
        haystack = f"{title} {summary}"
        if not any(keyword in haystack for keyword in _SANSPO_GIANTS_KEYWORDS):
            filtered_out += 1
            continue
        published_struct = _parse_iso8601_to_struct_time(
            meta.get("article:published_time", "")
        )
        if published_struct is None:
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
            "published_parsed": published_struct,
            "published": _struct_time_to_rfc822(published_struct),
        }
        entries.append(entry)

    logger.info(
        "tag_page_entries_built source=sanspo count=%d (out of %d candidates, %d filtered as non-giants)",
        len(entries),
        len(seen_urls),
        filtered_out,
    )
    return entries


# RELIABILITY-2026-05-08-Y: YouTube channel page (videos tab) scraper。
# YouTube 公式 RSS feed (`/feeds/videos.xml?channel_id=...`) は 2024 以降廃止
# (404)、RSSHub /youtube routes も 503。channel page (`/channel/UCxxx/videos`)
# は 200 OK で ytInitialData JSON に video list 含む = ここから extract する
# しかない。媒体形式 = video なので role=media_quote_only 想定 (article 化せず
# 他記事に embed する素材プール)。
_YOUTUBE_INITIAL_DATA_RE = re.compile(
    r"var ytInitialData = ({.+?});</script>", flags=re.DOTALL
)
_YOUTUBE_RELATIVE_TIME_PATTERNS = (
    (re.compile(r"(\d+)\s*分前"), "minutes"),
    (re.compile(r"(\d+)\s*時間前"), "hours"),
    (re.compile(r"(\d+)\s*日前"), "days"),
    (re.compile(r"(\d+)\s*週間前"), "weeks"),
    (re.compile(r"(\d+)\s*か月前"), "months"),
    (re.compile(r"(\d+)\s*年前"), "years"),
)


def _parse_youtube_relative_time(text: str, *, now: datetime) -> datetime | None:
    """「3 日前」「10 時間前」等の YouTube 相対時刻表記を datetime に変換。"""
    if not text:
        return None
    for pattern, unit in _YOUTUBE_RELATIVE_TIME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if unit == "minutes":
            return now - timedelta(minutes=value)
        if unit == "hours":
            return now - timedelta(hours=value)
        if unit == "days":
            return now - timedelta(days=value)
        if unit == "weeks":
            return now - timedelta(weeks=value)
        if unit == "months":
            return now - timedelta(days=value * 30)
        if unit == "years":
            return now - timedelta(days=value * 365)
    return None


def fetch_youtube_channel_entries(
    *,
    tag_url: str,
    max_age_days: int = 14,
    article_limit: int = 15,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    """YouTube channel videos page から最近 N 日分の video entries を返す。

    tag_url は `https://www.youtube.com/channel/UCxxxx/videos` 形式。
    video entry の形式は feedparser entries 互換 (link / title / summary /
    published_parsed / id) で、link は `https://www.youtube.com/watch?v=VIDEO_ID`。
    プレミア公開予約 (upcoming) entry は include しない (relative time が
    parse 失敗 = include 不能なので自然 filter)。
    """
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    response = _http_get(tag_url, fetcher=fetcher)
    if response is None or response.status_code != 200:
        logger.warning(
            "tag_page_fetch_failed source=youtube tag_url=%s status=%s",
            tag_url,
            getattr(response, "status_code", "ERR"),
        )
        return []

    text = response.text
    match = _YOUTUBE_INITIAL_DATA_RE.search(text)
    if not match:
        logger.warning("youtube_initial_data_not_found tag_url=%s", tag_url)
        return []

    try:
        import json as _json

        data = _json.loads(match.group(1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("youtube_initial_data_parse_failed url=%s reason=%s", tag_url, exc)
        return []

    try:
        tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
    except (KeyError, TypeError):
        logger.warning("youtube_tabs_not_found url=%s", tag_url)
        return []

    selected_tab = None
    for tab in tabs:
        tab_renderer = tab.get("tabRenderer") if isinstance(tab, dict) else None
        if tab_renderer and tab_renderer.get("selected"):
            selected_tab = tab_renderer
            break
    if selected_tab is None:
        logger.info("youtube_no_selected_tab url=%s", tag_url)
        return []

    grid_items = (
        selected_tab.get("content", {})
        .get("richGridRenderer", {})
        .get("contents", [])
    )
    if not grid_items:
        logger.info("youtube_grid_empty url=%s", tag_url)
        return []

    entries: list[dict[str, Any]] = []
    parsed_count = 0
    age_filtered = 0
    for grid_item in grid_items:
        if not isinstance(grid_item, dict):
            continue
        lockup = (
            grid_item.get("richItemRenderer", {})
            .get("content", {})
            .get("lockupViewModel", {})
        )
        if not lockup:
            continue
        video_id = str(lockup.get("contentId") or "").strip()
        if not video_id or len(video_id) != 11:
            continue
        metadata_view = (
            lockup.get("metadata", {}).get("lockupMetadataViewModel", {})
        )
        title = str(metadata_view.get("title", {}).get("content") or "").strip()
        if not title:
            continue
        # metadataRows から「N 日前」を探す
        relative_time_text = ""
        for row in (
            metadata_view.get("metadata", {})
            .get("contentMetadataViewModel", {})
            .get("metadataRows", [])
        ):
            for part in row.get("metadataParts", []):
                text_content = (
                    part.get("text", {}).get("content")
                    if isinstance(part.get("text"), dict)
                    else None
                )
                if text_content and any(
                    suffix in text_content
                    for suffix in ("分前", "時間前", "日前", "週間前", "か月前", "年前")
                ):
                    relative_time_text = text_content
                    break
            if relative_time_text:
                break
        published_dt = _parse_youtube_relative_time(
            relative_time_text, now=reference_now
        )
        if published_dt is None:
            # プレミア公開予約 / 古すぎ / 不明 → skip
            age_filtered += 1
            continue
        age_days = (reference_now.date() - published_dt.date()).days
        if age_days < 0 or age_days > max_age_days:
            age_filtered += 1
            continue
        parsed_count += 1
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        published_struct = published_dt.astimezone(timezone.utc).timetuple()
        entry: dict[str, Any] = {
            "link": watch_url,
            "id": watch_url,
            "title": title,
            "summary": "",
            "description": "",
            "published_parsed": published_struct,
            "published": _struct_time_to_rfc822(published_struct),
        }
        entries.append(entry)
        if len(entries) >= article_limit:
            break

    logger.info(
        "tag_page_entries_built source=youtube count=%d (parsed=%d age_filtered=%d total_grid=%d)",
        len(entries),
        parsed_count,
        age_filtered,
        len(grid_items),
    )
    return entries


_SPONICHI_ARTICLE_PATH_RE = re.compile(
    r'/baseball/news/(\d{4})/(\d{2})/(\d{2})/kiji/([a-zA-Z0-9]+)\.html'
)
_SPONICHI_GIANTS_KEYWORDS = ("巨人",)
# 「ジャイアンツ」「Giants」だけだと MLB SF Giants が混入する false positive (NPB
# Giants は sponichi 慣例で「巨人」prefix を title に持つ)。narrow に「巨人」一択。


def fetch_sponichi_giants_entries(
    *,
    tag_url: str = "https://www.sponichi.co.jp/baseball/",
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    """sponichi.co.jp 野球 top page から最近 N 日分の 巨人記事 entries を返す。

    sponichi は giants 専用 tag page を持たない (`/baseball/giants/` 等は 404 確認済)。
    `/baseball/` top page には野球全般の記事が並ぶため、article fetch 後に
    og:title / og:description が「巨人」or「ジャイアンツ」 keyword を含むかで post-filter。
    URL pattern: `/baseball/news/YYYY/MM/DD/kiji/{ID}.html`、URL 内 date で age window 判定
    (`<meta article:published_time>` が無いため URL date を fallback)。
    337-INGEST Phase 2 で追加 (2026-05-14)。
    """
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    response = _http_get(tag_url, fetcher=fetcher)
    if response is None or response.status_code != 200:
        logger.warning(
            "tag_page_fetch_failed source=sponichi tag_url=%s status=%s",
            tag_url,
            getattr(response, "status_code", "ERR"),
        )
        return []

    text = response.text
    seen_urls: list[tuple[str, str]] = []  # (article_url, yyyymmdd)
    seen_set: set[str] = set()
    for match in _SPONICHI_ARTICLE_PATH_RE.finditer(text):
        year, month, day, code = match.groups()
        date_str = f"{year}{month}{day}"
        if not _is_ymd_within_window(date_str, max_age_days=max_age_days, now=reference_now):
            continue
        article_url = (
            f"https://www.sponichi.co.jp/baseball/news/{year}/{month}/{day}/kiji/{code}.html"
        )
        if article_url in seen_set:
            continue
        seen_set.add(article_url)
        seen_urls.append((article_url, date_str))

    if not seen_urls:
        logger.info("tag_page_no_recent_articles source=sponichi tag_url=%s", tag_url)
        return []

    seen_urls = seen_urls[:article_limit]
    logger.info(
        "tag_page_articles_extracted source=sponichi count=%d (after age %dd / limit %d)",
        len(seen_urls),
        max_age_days,
        article_limit,
    )

    entries: list[dict[str, Any]] = []
    filtered_out = 0
    for article_url, date_str in seen_urls:
        article_response = _http_get(article_url, fetcher=fetcher)
        if article_response is None or article_response.status_code != 200:
            logger.info(
                "tag_page_article_fetch_failed source=sponichi url=%s status=%s",
                article_url,
                getattr(article_response, "status_code", "ERR"),
            )
            continue
        meta = _extract_og_meta(article_response.text)
        title = (meta.get("og:title") or "").strip()
        # sponichi og:title は「... - スポニチ Sponichi Annex 野球」suffix を持つので取る
        title = re.sub(
            r"\s*[-‐−–—ー]\s*スポニチ\s*Sponichi\s*Annex(\s*[^\s].*)?$",
            "",
            title,
            flags=re.IGNORECASE,
        )
        summary = (meta.get("og:description") or meta.get("description") or "").strip()
        # post-filter: title or summary に 巨人 keyword 含むか
        haystack = f"{title} {summary}"
        if not any(keyword in haystack for keyword in _SPONICHI_GIANTS_KEYWORDS):
            filtered_out += 1
            continue
        # sponichi article は published_time meta が無いので URL の date 部分から fallback
        # (12:00 JST を published 時刻として割り当て、daily と同じ pattern)
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
            "published_parsed": published_struct,
            "published": _struct_time_to_rfc822(published_struct),
        }
        entries.append(entry)

    logger.info(
        "tag_page_entries_built source=sponichi count=%d "
        "(out of %d candidates, %d filtered as non-giants)",
        len(entries),
        len(seen_urls),
        filtered_out,
    )
    return entries


_TOKYO_SPORTS_ARTICLE_PATH_RE = re.compile(r'/articles/-/(\d+)')


def fetch_tokyo_sports_giants_entries(
    *,
    tag_url: str = "https://www.tokyo-sports.co.jp/list/label/%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    """tokyo-sports.co.jp 巨人 label page から最近 N 日分の article entries を返す。

    URL pattern: `/articles/-/{numeric_id}`(URL に date 無し)。
    label page (`/list/label/巨人`) は東スポ自身が巨人記事を curate しているため
    post-filter (giants keyword check) は不要。article 毎に
    `<meta property="article:published_time">` ISO8601 を取って age window 判定。
    337-INGEST Phase 1 で追加 (2026-05-14)。
    """
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    response = _http_get(tag_url, fetcher=fetcher)
    if response is None or response.status_code != 200:
        logger.warning(
            "tag_page_fetch_failed source=tokyo_sports tag_url=%s status=%s",
            tag_url,
            getattr(response, "status_code", "ERR"),
        )
        return []

    text = response.text
    seen_urls: list[str] = []
    seen_set: set[str] = set()
    for match in _TOKYO_SPORTS_ARTICLE_PATH_RE.finditer(text):
        article_id = match.group(1)
        article_url = f"https://www.tokyo-sports.co.jp/articles/-/{article_id}"
        if article_url in seen_set:
            continue
        seen_set.add(article_url)
        seen_urls.append(article_url)

    if not seen_urls:
        logger.info("tag_page_no_recent_articles source=tokyo_sports tag_url=%s", tag_url)
        return []

    # tag page から取った 件数を article_limit で cap (article 毎に fetch するため
    # 上限超過は cost 増)
    seen_urls = seen_urls[:article_limit]
    logger.info(
        "tag_page_articles_extracted source=tokyo_sports count=%d (limit %d)",
        len(seen_urls),
        article_limit,
    )

    entries: list[dict[str, Any]] = []
    age_filtered_out = 0
    for article_url in seen_urls:
        article_response = _http_get(article_url, fetcher=fetcher)
        if article_response is None or article_response.status_code != 200:
            logger.info(
                "tag_page_article_fetch_failed source=tokyo_sports url=%s status=%s",
                article_url,
                getattr(article_response, "status_code", "ERR"),
            )
            continue
        meta = _extract_og_meta(article_response.text)
        title = (meta.get("og:title") or "").strip()
        # 東スポ og:title は「... | 東スポWEB」suffix を持つので取る
        title = re.sub(
            r"\s*[|｜]\s*東スポWEB\s*$", "", title, flags=re.IGNORECASE
        )
        summary = (meta.get("og:description") or meta.get("description") or "").strip()
        published_struct = _parse_iso8601_to_struct_time(
            meta.get("article:published_time", "")
        )
        if published_struct is None:
            # tokyo-sports は URL に date が無く、meta も取れなければ age 判定不可
            # = age window 外と扱って skip。
            age_filtered_out += 1
            continue
        # age window 判定 (published_time の YYYYMMDD を引っ張る)
        pub_dt = datetime(*published_struct[:6], tzinfo=timezone.utc).astimezone(JST)
        date_str = pub_dt.strftime("%Y%m%d")
        if not _is_ymd_within_window(date_str, max_age_days=max_age_days, now=reference_now):
            age_filtered_out += 1
            continue
        entry: dict[str, Any] = {
            "link": article_url,
            "id": article_url,
            "title": title,
            "summary": summary,
            "description": summary,
            "published_parsed": published_struct,
            "published": _struct_time_to_rfc822(published_struct),
        }
        entries.append(entry)

    logger.info(
        "tag_page_entries_built source=tokyo_sports count=%d "
        "(out of %d candidates, %d age-filtered)",
        len(entries),
        len(seen_urls),
        age_filtered_out,
    )
    return entries


_NTV_NEWS_ARTICLE_RE = re.compile(
    r'href=[\"\']([^\"\']*/category/sports/[0-9a-z]+(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_YOMIURI_NPB_ARTICLE_RE = re.compile(
    r'href=[\"\']([^\"\']*/sports/npb/\d{8}-[A-Z0-9]+/(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_FRIDAY_ARTICLE_RE = re.compile(
    r'href=[\"\']([^\"\']*/article/\d+(?:\?[^\"\']*)?)[\"\']|\"id\"\s*:\s*(\d{5,})',
    flags=re.IGNORECASE,
)
_SMART_FLASH_ARTICLE_RE = re.compile(
    r'href=[\"\'](https?://smart-flash\.jp/[a-z0-9_-]+/\d+/(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_JPRIME_ARTICLE_RE = re.compile(
    r'href=[\"\']([^\"\']*/articles/-/\d+(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_BUNSHUN_ARTICLE_RE = re.compile(
    r'href=[\"\']([^\"\']*/articles/-/\d+(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_NEWS_POSTSEVEN_ARTICLE_RE = re.compile(
    r'href=[\"\'](https?://www\.news-postseven\.com/archives/\d+_\d+\.html(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_DAILY_SHINCHO_ARTICLE_RE = re.compile(
    r'href=[\"\'](https?://www\.dailyshincho\.jp/article/\d{4}/\d{8}/(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_GENDAI_ARTICLE_RE = re.compile(
    r'href=[\"\']([^\"\']*/articles/-/\d+(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_ASAGEI_ARTICLE_RE = re.compile(
    r'href=[\"\'](https?://www\.asagei\.com/excerpt/\d+(?:\?[^\"\']*)?)[\"\']',
    flags=re.IGNORECASE,
)
_DAILY_SHINCHO_URL_DATE_RE = re.compile(r"/article/\d{4}/(\d{8})/")

_NTV_NEWS_TITLE_SUFFIX_RE = re.compile(
    r"(?:（\d{4}年\d{1,2}月\d{1,2}日掲載）)?\s*[|｜]\s*日テレNEWS\s*NNN.*$"
)
_FRIDAY_TITLE_SUFFIX_RE = re.compile(r"\s*[|｜]\s*FRIDAYデジタル\s*$")
_SMART_FLASH_TITLE_SUFFIX_RE = re.compile(
    r"\s*(?:[|｜]|[-‐−–—ー])\s*Smart FLASH.*$", re.IGNORECASE
)
_JPRIME_TITLE_SUFFIX_RE = re.compile(r"\s*[|｜]\s*週刊女性PRIME\s*$")
_BUNSHUN_TITLE_SUFFIX_RE = re.compile(r"\s*[|｜]\s*文春オンライン\s*$")
_NEWS_POSTSEVEN_TITLE_SUFFIX_RE = re.compile(r"\s*[|｜]\s*NEWSポストセブン\s*$")
_DAILY_SHINCHO_TITLE_SUFFIX_RE = re.compile(r"\s*[|｜]\s*デイリー新潮\s*$")
_GENDAI_TITLE_SUFFIX_RE = re.compile(r"\s*[|｜]\s*現代ビジネス(?:\s*[|｜]\s*講談社)?\s*$")
_ASAGEI_TITLE_SUFFIX_RE = re.compile(r"\s*[|｜]\s*アサ芸プラス\s*$")


def _friday_article_url(raw_url: str, base_url: str) -> str:
    raw = str(raw_url or "").strip()
    if raw.isdigit():
        return f"https://friday.kodansha.co.jp/article/{raw}"
    return _canonical_article_url(raw, base_url=base_url)


def fetch_ntv_news_giants_entries(
    *,
    tag_url: str = "https://news.ntv.co.jp/tag/%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="ntv_news",
        tag_url=tag_url,
        article_url_pattern=_NTV_NEWS_ARTICLE_RE,
        title_suffix_re=_NTV_NEWS_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_yomiuri_npb_giants_entries(
    *,
    tag_url: str = "https://www.yomiuri.co.jp/sports/npb/",
    max_age_days: int = 7,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="yomiuri_online",
        tag_url=tag_url,
        article_url_pattern=_YOMIURI_NPB_ARTICLE_RE,
        title_suffix_re=None,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_friday_giants_entries(
    *,
    tag_url: str = "https://friday.kodansha.co.jp/tag/%E3%82%B8%E3%83%A3%E3%82%A4%E3%82%A2%E3%83%B3%E3%83%84",
    max_age_days: int = 120,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="friday",
        tag_url=tag_url,
        article_url_pattern=_FRIDAY_ARTICLE_RE,
        title_suffix_re=_FRIDAY_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_smart_flash_giants_entries(
    *,
    tag_url: str = "https://smart-flash.jp/tag/%E5%B7%A8%E4%BA%BA/",
    max_age_days: int = 120,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="smart_flash",
        tag_url=tag_url,
        article_url_pattern=_SMART_FLASH_ARTICLE_RE,
        title_suffix_re=_SMART_FLASH_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_jprime_giants_entries(
    *,
    tag_url: str = "https://www.jprime.jp/list/tag/%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 180,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="jprime",
        tag_url=tag_url,
        article_url_pattern=_JPRIME_ARTICLE_RE,
        title_suffix_re=_JPRIME_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_bunshun_giants_entries(
    *,
    tag_url: str = "https://bunshun.jp/category/baseball-column-giants?page=1",
    max_age_days: int = 365,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="bunshun",
        tag_url=tag_url,
        article_url_pattern=_BUNSHUN_ARTICLE_RE,
        title_suffix_re=_BUNSHUN_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_news_postseven_giants_entries(
    *,
    tag_url: str = "https://www.news-postseven.com/?s=%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 180,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="news_postseven",
        tag_url=tag_url,
        article_url_pattern=_NEWS_POSTSEVEN_ARTICLE_RE,
        title_suffix_re=_NEWS_POSTSEVEN_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_daily_shincho_giants_entries(
    *,
    tag_url: str = "https://www.dailyshincho.jp/search/?fulltext=%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 180,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="daily_shincho",
        tag_url=tag_url,
        article_url_pattern=_DAILY_SHINCHO_ARTICLE_RE,
        title_suffix_re=_DAILY_SHINCHO_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
        url_date_re=_DAILY_SHINCHO_URL_DATE_RE,
    )


def fetch_gendai_media_giants_entries(
    *,
    tag_url: str = "https://gendai.media/search?fulltext=%E5%B7%A8%E4%BA%BA&media=gb",
    max_age_days: int = 180,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="gendai_media",
        tag_url=tag_url,
        article_url_pattern=_GENDAI_ARTICLE_RE,
        title_suffix_re=_GENDAI_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


def fetch_asagei_giants_entries(
    *,
    tag_url: str = "https://www.asagei.com/?s=%E5%B7%A8%E4%BA%BA",
    max_age_days: int = 180,
    article_limit: int = 30,
    logger: logging.Logger | None = None,
    now: datetime | None = None,
    fetcher: Callable[..., requests.Response] | None = None,
) -> list[dict[str, Any]]:
    logger = logger or logging.getLogger("tag_page_scraper")
    reference_now = (now or datetime.now(timezone.utc)).astimezone(JST)
    return _fetch_generic_giants_entries(
        source="asagei",
        tag_url=tag_url,
        article_url_pattern=_ASAGEI_ARTICLE_RE,
        title_suffix_re=_ASAGEI_TITLE_SUFFIX_RE,
        max_age_days=max_age_days,
        article_limit=article_limit,
        logger=logger,
        now=reference_now,
        fetcher=fetcher,
    )


_SCRAPER_REGISTRY: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "hochi_giants_tag": fetch_hochi_giants_entries,
    "daily_giants_tag": fetch_daily_giants_entries,
    "sponichi_giants_filter": fetch_sponichi_giants_entries,
    "tokyo_sports_giants_label": fetch_tokyo_sports_giants_entries,
    "sanspo_giants_search": fetch_sanspo_giants_entries,
    "youtube_channel": fetch_youtube_channel_entries,
    "ntv_news_giants_tag": fetch_ntv_news_giants_entries,
    "yomiuri_npb_giants_filter": fetch_yomiuri_npb_giants_entries,
    "friday_giants_tag": fetch_friday_giants_entries,
    "smart_flash_giants_tag": fetch_smart_flash_giants_entries,
    "jprime_giants_tag": fetch_jprime_giants_entries,
    "bunshun_giants_category": fetch_bunshun_giants_entries,
    "news_postseven_giants_search": fetch_news_postseven_giants_entries,
    "daily_shincho_giants_search": fetch_daily_shincho_giants_entries,
    "gendai_media_giants_search": fetch_gendai_media_giants_entries,
    "asagei_giants_search": fetch_asagei_giants_entries,
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
