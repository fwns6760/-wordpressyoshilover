"""tag_page_scraper の unit test (RELIABILITY-2026-05-08-A)."""

import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src import tag_page_scraper as scraper


JST = timezone(timedelta(hours=9))


def _make_response(status_code: int, text: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class OgMetaExtractorTests(unittest.TestCase):
    def test_extract_basic_meta(self):
        html = """
        <html><head>
        <meta property="og:title" content="テスト記事タイトル - スポーツ報知">
        <meta property="og:description" content="本文の lead テキスト 200 chars 程度。">
        <meta property="article:published_time" content="2026-05-08T06:00:00+09:00">
        <meta name="description" content="meta description fallback">
        </head><body>本文</body></html>
        """
        meta = scraper._extract_og_meta(html)
        self.assertEqual(meta.get("og:title"), "テスト記事タイトル - スポーツ報知")
        self.assertEqual(meta.get("og:description"), "本文の lead テキスト 200 chars 程度。")
        self.assertEqual(meta.get("article:published_time"), "2026-05-08T06:00:00+09:00")
        self.assertEqual(meta.get("description"), "meta description fallback")

    def test_first_value_wins_on_duplicate_keys(self):
        html = (
            '<meta property="og:title" content="first">'
            '<meta property="og:title" content="second">'
        )
        self.assertEqual(scraper._extract_og_meta(html).get("og:title"), "first")


class ParseIso8601Tests(unittest.TestCase):
    def test_parses_jst_offset(self):
        st = scraper._parse_iso8601_to_struct_time("2026-05-08T06:00:00+09:00")
        self.assertIsNotNone(st)
        # +09:00 → UTC で 5/7 21:00
        self.assertEqual(st.tm_year, 2026)
        self.assertEqual(st.tm_mon, 5)
        self.assertEqual(st.tm_mday, 7)
        self.assertEqual(st.tm_hour, 21)

    def test_parses_zulu(self):
        st = scraper._parse_iso8601_to_struct_time("2026-05-08T00:00:00Z")
        self.assertIsNotNone(st)
        self.assertEqual(st.tm_hour, 0)

    def test_invalid_returns_none(self):
        self.assertIsNone(scraper._parse_iso8601_to_struct_time(""))
        self.assertIsNone(scraper._parse_iso8601_to_struct_time("not-a-date"))


class IsYmdWithinWindowTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=JST)

    def test_today_within_window(self):
        self.assertTrue(
            scraper._is_ymd_within_window("20260508", max_age_days=7, now=self.now)
        )

    def test_5_days_ago_within_window(self):
        self.assertTrue(
            scraper._is_ymd_within_window("20260503", max_age_days=7, now=self.now)
        )

    def test_8_days_ago_outside_window(self):
        self.assertFalse(
            scraper._is_ymd_within_window("20260430", max_age_days=7, now=self.now)
        )

    def test_invalid_format(self):
        self.assertFalse(
            scraper._is_ymd_within_window("not-a-date", max_age_days=7, now=self.now)
        )
        self.assertFalse(
            scraper._is_ymd_within_window("", max_age_days=7, now=self.now)
        )

    def test_old_evergreen_article_excluded(self):
        # 2024/10/01 のような古い article は今日からみて 200 日前 → 範囲外
        self.assertFalse(
            scraper._is_ymd_within_window("20241001", max_age_days=7, now=self.now)
        )


class FetchHochiGiantsEntriesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=JST)

    def _build_tag_page_html(self, article_dates: list[tuple[str, str]]) -> str:
        """date+code のリストから tag page 風 HTML を組む。"""
        anchors = "".join(
            f'<a href="/articles/{date}-{code}.html">title-{date}-{code}</a>'
            for date, code in article_dates
        )
        return f"<html><body><div class='articles'>{anchors}</div></body></html>"

    def _build_article_html(self, *, title: str, desc: str, published_iso: str) -> str:
        return f"""
        <html><head>
        <meta property="og:title" content="{title}">
        <meta property="og:description" content="{desc}">
        <meta property="article:published_time" content="{published_iso}">
        </head><body></body></html>
        """

    def test_filters_old_articles_from_tag_page(self):
        # tag page に 5/8 / 5/7 / 2024/10/01 (evergreen) の 3 件
        tag_html = self._build_tag_page_html(
            [
                ("20260508", "OHT1T51001"),
                ("20260507", "OHT1T51002"),
                ("20241001", "OHT1T51122"),  # evergreen / 古い
            ]
        )
        article_html = self._build_article_html(
            title="サンプル記事 - スポーツ報知",
            desc="lead",
            published_iso="2026-05-08T06:00:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if "tag" in url:
                return _make_response(200, tag_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_hochi_giants_entries(
            tag_url="https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
            max_age_days=7,
            article_limit=10,
            now=self.now,
            fetcher=fake_fetcher,
        )
        urls = [e["link"] for e in entries]
        self.assertIn("https://hochi.news/articles/20260508-OHT1T51001.html", urls)
        self.assertIn("https://hochi.news/articles/20260507-OHT1T51002.html", urls)
        self.assertNotIn(
            "https://hochi.news/articles/20241001-OHT1T51122.html",
            urls,
            "evergreen 古い article は除外されるべき",
        )

    def test_strips_hochi_brand_suffix_from_title(self):
        tag_html = self._build_tag_page_html([("20260508", "OHT1T51001")])
        article_html = self._build_article_html(
            title="記事タイトル本体 - スポーツ報知",
            desc="summary",
            published_iso="2026-05-08T06:00:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if "tag" in url:
                return _make_response(200, tag_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_hochi_giants_entries(
            tag_url="https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "記事タイトル本体")

    def test_fallback_to_url_date_when_meta_missing(self):
        tag_html = self._build_tag_page_html([("20260508", "OHT1T51001")])
        # article_html に article:published_time なし
        article_html = """
        <html><head>
        <meta property="og:title" content="記事 - スポーツ報知">
        <meta property="og:description" content="summary">
        </head></html>
        """

        def fake_fetcher(url, **kwargs):
            if "tag" in url:
                return _make_response(200, tag_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_hochi_giants_entries(
            tag_url="https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        e = entries[0]
        # URL date (5/8) → 12:00 JST → UTC 03:00
        st = e["published_parsed"]
        self.assertEqual(st.tm_year, 2026)
        self.assertEqual(st.tm_mon, 5)
        self.assertEqual(st.tm_mday, 8)
        self.assertEqual(st.tm_hour, 3)

    def test_tag_page_404_returns_empty(self):
        def fake_fetcher(url, **kwargs):
            return _make_response(404, "")

        entries = scraper.fetch_hochi_giants_entries(
            tag_url="https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(entries, [])

    def test_returns_feedparser_compatible_keys(self):
        tag_html = self._build_tag_page_html([("20260508", "OHT1T51001")])
        article_html = self._build_article_html(
            title="記事 - スポーツ報知",
            desc="summary text",
            published_iso="2026-05-08T06:00:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if "tag" in url:
                return _make_response(200, tag_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_hochi_giants_entries(
            tag_url="https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        e = entries[0]
        # rss_fetcher が entry.get(...) で読む key を 1 つずつ confirm
        self.assertEqual(e["link"], "https://hochi.news/articles/20260508-OHT1T51001.html")
        self.assertEqual(e["id"], e["link"])
        self.assertEqual(e["title"], "記事")
        self.assertEqual(e["summary"], "summary text")
        self.assertEqual(e["description"], "summary text")
        self.assertIsInstance(e["published_parsed"], time.struct_time)
        self.assertTrue(e["published"])

    def test_article_limit_truncates(self):
        tag_html = self._build_tag_page_html(
            [("20260508", f"CODE{i:03d}") for i in range(20)]
        )
        article_html = self._build_article_html(
            title="記事 - スポーツ報知",
            desc="d",
            published_iso="2026-05-08T06:00:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if "tag" in url:
                return _make_response(200, tag_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_hochi_giants_entries(
            tag_url="https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
            article_limit=5,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 5)


class FetchTagPageEntriesDispatchTests(unittest.TestCase):
    def test_unknown_scraper_returns_empty(self):
        entries = scraper.fetch_tag_page_entries(
            scraper="not_registered_kind",
            url="https://example.com/",
            now=datetime(2026, 5, 8, 12, 0, 0, tzinfo=JST),
        )
        self.assertEqual(entries, [])

    def test_known_scraper_dispatches(self):
        called = {"flag": False}

        def fake_fetcher(url, **kwargs):
            called["flag"] = True
            return _make_response(200, "<html></html>")

        scraper.fetch_tag_page_entries(
            scraper="hochi_giants_tag",
            url="https://hochi.news/tag/%E5%B7%A8%E4%BA%BA",
            now=datetime(2026, 5, 8, 12, 0, 0, tzinfo=JST),
            fetcher=fake_fetcher,
        )
        self.assertTrue(called["flag"], "registered scraper should be invoked")

    def test_list_scraper_kinds_includes_hochi_and_daily(self):
        kinds = list(scraper.list_scraper_kinds())
        self.assertIn("hochi_giants_tag", kinds)
        self.assertIn("daily_giants_tag", kinds)


class FetchDailyGiantsEntriesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=JST)

    def _build_index_html(self, articles: list[tuple[str, str, str, str]]) -> str:
        """articles: list of (year, month, day, code)."""
        anchors = "".join(
            f'<a href="https://www.daily.co.jp/baseball/{y}/{m}/{d}/{c}.shtml">title-{y}{m}{d}-{c}</a>'
            for y, m, d, c in articles
        )
        return f"<html><body>{anchors}</body></html>"

    def _build_article_html(
        self,
        *,
        title: str,
        desc: str,
        published_iso: str = "",
        time_datetime: str = "",
    ) -> str:
        meta = f'<meta property="og:title" content="{title}">' \
            f'<meta property="og:description" content="{desc}">'
        if published_iso:
            meta += f'<meta property="article:published_time" content="{published_iso}">'
        body_extra = ""
        if time_datetime:
            body_extra = f'<time datetime="{time_datetime}">label</time>'
        return f"<html><head>{meta}</head><body>{body_extra}</body></html>"

    def test_strips_daily_brand_suffix(self):
        index_html = self._build_index_html([("2026", "05", "08", "0020326769")])
        article_html = self._build_article_html(
            title="復活見えた？巨人・田中将が今季３勝/デイリースポーツ online",
            desc="lead",
            published_iso="2026-05-08T06:00:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("/index.shtml"):
                return _make_response(200, index_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_daily_giants_entries(
            tag_url="https://www.daily.co.jp/baseball/giants/index.shtml",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["title"], "復活見えた？巨人・田中将が今季３勝"
        )

    def test_falls_back_to_url_date_at_noon_jst_when_meta_and_time_tag_missing(self):
        index_html = self._build_index_html([("2026", "05", "08", "0020326769")])
        # article:published_time なし、<time datetime> も日付のみ (時刻情報なし) なので
        # URL の date 部分を使った 12:00 JST = 03:00 UTC の fallback が当たる。
        article_html = self._build_article_html(
            title="記事/デイリースポーツ online",
            desc="lead",
            time_datetime="2026-05-08",
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("/index.shtml"):
                return _make_response(200, index_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_daily_giants_entries(
            tag_url="https://www.daily.co.jp/baseball/giants/index.shtml",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        st = entries[0]["published_parsed"]
        # 12:00 JST = 03:00 UTC、UTC struct_time なので mday=8 hour=3
        self.assertEqual(st.tm_year, 2026)
        self.assertEqual(st.tm_mon, 5)
        self.assertEqual(st.tm_mday, 8)
        self.assertEqual(st.tm_hour, 3)

    def test_old_articles_filtered_out(self):
        # 5/1 (8d 前) と 5/8 (today) の article、5/1 は max_age_days=7 で外れる
        index_html = self._build_index_html(
            [
                ("2026", "05", "01", "0020100001"),
                ("2026", "05", "08", "0020100002"),
            ]
        )
        article_html = self._build_article_html(
            title="記事/デイリースポーツ online",
            desc="lead",
            published_iso="2026-05-08T06:00:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("/index.shtml"):
                return _make_response(200, index_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_daily_giants_entries(
            tag_url="https://www.daily.co.jp/baseball/giants/index.shtml",
            max_age_days=7,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertIn(
            "2026/05/08", entries[0]["link"], "5/8 article should be kept, 5/1 dropped"
        )


if __name__ == "__main__":
    unittest.main()
