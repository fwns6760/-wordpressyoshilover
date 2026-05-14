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


_SCRAPER_REGISTRY: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "hochi_giants_tag": fetch_hochi_giants_entries,
    "daily_giants_tag": fetch_daily_giants_entries,
    "tokyo_sports_giants_label": fetch_tokyo_sports_giants_entries,
    "youtube_channel": fetch_youtube_channel_entries,
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
