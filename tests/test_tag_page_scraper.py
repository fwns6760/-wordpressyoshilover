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
        self.assertIn("friday_giants_tag", kinds)
        self.assertIn("ntv_news_giants_tag", kinds)
        self.assertIn("yomiuri_npb_giants_filter", kinds)
        self.assertIn("gendai_media_giants_search", kinds)
        self.assertIn("asagei_giants_search", kinds)


class FetchGeneralMagazineGiantsEntriesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=JST)

    def test_friday_requires_giants_topic_and_parses_article_meta(self):
        listing_html = """
        <a href="/article/426377">giants</a>
        <a href="/article/426999">non giants</a>
        """
        article_html = {
            "https://friday.kodansha.co.jp/article/426377": """
                <meta property="og:title" content="巨人・砂川リチャードの現在地 | FRIDAYデジタル">
                <meta property="og:description" content="ジャイアンツの話題">
                <meta property="article:published_time" content="2026-05-17T07:00:25+09:00">
            """,
            "https://friday.kodansha.co.jp/article/426999": """
                <meta property="og:title" content="阪神の話題 | FRIDAYデジタル">
                <meta property="og:description" content="他球団のみ">
                <meta property="article:published_time" content="2026-05-17T07:00:25+09:00">
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "/tag/" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_friday_giants_entries(
            tag_url="https://friday.kodansha.co.jp/tag/%E3%82%B8%E3%83%A3%E3%82%A4%E3%82%A2%E3%83%B3%E3%83%84",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["link"], "https://friday.kodansha.co.jp/article/426377")
        self.assertEqual(entries[0]["title"], "巨人・砂川リチャードの現在地")

    def test_smart_flash_strips_tracking_query_and_uses_json_ld_date(self):
        listing_html = """
        <a href="https://smart-flash.jp/sports/406275/?rf=2">giants</a>
        """
        article_html = """
            <meta property="og:title" content="巨人の補強が注目される | Smart FLASH/スマフラ[光文社週刊誌]">
            <meta property="og:description" content="巨人ファンが知りたい話題">
            <script type="application/ld+json">{"datePublished":"2026-05-05T11:00:00+09:00"}</script>
        """

        def fake_fetcher(url, **kwargs):
            if "/tag/" in url:
                return _make_response(200, listing_html)
            self.assertEqual(url, "https://smart-flash.jp/sports/406275/")
            return _make_response(200, article_html)

        entries = scraper.fetch_smart_flash_giants_entries(
            tag_url="https://smart-flash.jp/tag/%E5%B7%A8%E4%BA%BA/",
            max_age_days=30,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["link"], "https://smart-flash.jp/sports/406275/")

    def test_ntv_news_tag_scraper_uses_tag_article_urls(self):
        listing_html = '<a href="/category/sports/abcd1234">巨人記事</a>'
        article_html = """
            <meta property="og:title" content="【巨人】岸田行倫が攻守で存在感｜日テレNEWS NNN">
            <meta property="og:description" content="読売ジャイアンツの試合情報">
            <meta property="article:published_time" content="2026-05-18T10:00:00+09:00">
        """

        def fake_fetcher(url, **kwargs):
            if "/tag/" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_ntv_news_giants_entries(
            tag_url="https://news.ntv.co.jp/tag/%E5%B7%A8%E4%BA%BA",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["link"], "https://news.ntv.co.jp/category/sports/abcd1234")
        self.assertEqual(entries[0]["title"], "【巨人】岸田行倫が攻守で存在感")

    def test_yomiuri_npb_scraper_filters_to_giants_articles(self):
        listing_html = """
        <a href="/sports/npb/20260517-GYT1T00242/">giants</a>
        <a href="/sports/npb/20260517-GYT1T00118/">other</a>
        """
        article_html = {
            "https://www.yomiuri.co.jp/sports/npb/20260517-GYT1T00242/": """
                <meta property="og:title" content="スミ１で巨人を６連勝に導いた岸田行倫">
                <meta property="og:description" content="巨人１－０ＤｅＮＡ">
                <meta property="article:published_time" content="2026-05-18T06:00:00+09:00">
            """,
            "https://www.yomiuri.co.jp/sports/npb/20260517-GYT1T00118/": """
                <meta property="og:title" content="西武が今季初の首位浮上">
                <meta property="og:description" content="パ・リーグの話題">
                <meta property="article:published_time" content="2026-05-18T06:00:00+09:00">
            """,
        }

        def fake_fetcher(url, **kwargs):
            if url.endswith("/sports/npb/"):
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_yomiuri_npb_giants_entries(
            tag_url="https://www.yomiuri.co.jp/sports/npb/",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["link"],
            "https://www.yomiuri.co.jp/sports/npb/20260517-GYT1T00242/",
        )

    def test_gendai_media_search_filters_non_giants_results(self):
        listing_html = """
        <a href="/articles/-/167002?fromRanking=true">non giants</a>
        <a href="/articles/-/167777">giants</a>
        """
        article_html = {
            "https://gendai.media/articles/-/167002": """
                <meta property="og:title" content="メジャーで活躍する村上宗隆の英語力 | 現代ビジネス | 講談社">
                <meta property="og:description" content="一般的なメジャーの話題">
                <script type="application/ld+json">{"datePublished":"2026-05-17T21:00:00.000Z"}</script>
            """,
            "https://gendai.media/articles/-/167777": """
                <meta property="og:title" content="巨人・阿部監督の采配に注目 | 現代ビジネス | 講談社">
                <meta property="og:description" content="読売ジャイアンツの話題">
                <script type="application/ld+json">{"datePublished":"2026-05-17T21:00:00.000Z"}</script>
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "/search?" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_gendai_media_giants_entries(
            tag_url="https://gendai.media/search?fulltext=%E5%B7%A8%E4%BA%BA&media=gb",
            max_age_days=30,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["link"], "https://gendai.media/articles/-/167777")
        self.assertEqual(entries[0]["title"], "巨人・阿部監督の采配に注目")

    def test_asagei_search_uses_datetime_attr_when_meta_date_missing(self):
        listing_html = """
        <a href="https://www.asagei.com/excerpt/347876">giants</a>
        <a href="https://www.asagei.com/excerpt/347000">non giants</a>
        """
        article_html = {
            "https://www.asagei.com/excerpt/347876": """
                <meta property="og:title" content="巨人・坂本勇人の一打が注目される | アサ芸プラス">
                <meta property="og:description" content="ジャイアンツファンの話題">
                <div class="sp-posted-at" datetime="2026-05-18 11:30">2026年05月18日 11:30</div>
            """,
            "https://www.asagei.com/excerpt/347000": """
                <meta property="og:title" content="阪神の話題 | アサ芸プラス">
                <meta property="og:description" content="他球団のみ">
                <div class="sp-posted-at" datetime="2026-05-18 11:30">2026年05月18日 11:30</div>
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_asagei_giants_entries(
            tag_url="https://www.asagei.com/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=30,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["link"], "https://www.asagei.com/excerpt/347876")
        self.assertEqual(entries[0]["title"], "巨人・坂本勇人の一打が注目される")


# 384-INGEST: 産経新聞 (sankei.com) tag_scrape tests
class FetchSankeiGiantsEntriesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=JST)

    def test_sankei_meta_name_attribute_extracted(self):
        # 産経の meta は `name="article:published_time"` (`property=` でなく `name=`)
        listing_html = """
        <a href="https://www.sankei.com/article/20260519-A6XIRYB5NNLQVFENL4HBB33QSY/">giants</a>
        <a href="https://www.sankei.com/article/20260518-FZRESCZEBZC5LNXMFLMMJLPCCQ/">also giants</a>
        """
        article_html = {
            "https://www.sankei.com/article/20260519-A6XIRYB5NNLQVFENL4HBB33QSY/": """
                <meta property="og:title" content="巨人・戸郷翔征が完投勝利 - 産経ニュース">
                <meta property="og:description" content="ジャイアンツの先発が好投">
                <meta name="article:published_time" content="2026-05-19T05:30:00+09:00"/>
            """,
            "https://www.sankei.com/article/20260518-FZRESCZEBZC5LNXMFLMMJLPCCQ/": """
                <meta property="og:title" content="巨人・坂本勇人 通算300号 - 産経ニュース">
                <meta property="og:description" content="読売ジャイアンツの主将">
                <meta name="article:published_time" content="2026-05-18T20:00:00+09:00"/>
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_sankei_giants_entries(
            tag_url="https://www.sankei.com/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=7,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 2)
        # title suffix ` - 産経ニュース` が strip される
        self.assertEqual(entries[0]["title"], "巨人・戸郷翔征が完投勝利")
        self.assertEqual(entries[0]["link"],
            "https://www.sankei.com/article/20260519-A6XIRYB5NNLQVFENL4HBB33QSY/")

    def test_sankei_old_url_filtered_by_age(self):
        # 8 日前の URL → max_age_days=7 で article fetch 段階で age_filtered
        listing_html = """
        <a href="https://www.sankei.com/article/20260511-OLDHASH/">old giants</a>
        """
        article_html = {
            "https://www.sankei.com/article/20260511-OLDHASH/": """
                <meta property="og:title" content="巨人・古い記事 - 産経ニュース">
                <meta property="og:description" content="ジャイアンツ過去の話題">
                <meta name="article:published_time" content="2026-05-11T05:30:00+09:00"/>
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_sankei_giants_entries(
            tag_url="https://www.sankei.com/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=7,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 0)

    def test_sankei_non_giants_filtered(self):
        # 巨人 keyword 無しは post_filter で除外
        listing_html = """
        <a href="https://www.sankei.com/article/20260519-OTHERHASH/">non giants</a>
        """
        article_html = {
            "https://www.sankei.com/article/20260519-OTHERHASH/": """
                <meta property="og:title" content="阪神タイガースが勝利 - 産経ニュース">
                <meta property="og:description" content="セ・リーグ他球団の話題">
                <meta name="article:published_time" content="2026-05-19T05:30:00+09:00"/>
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_sankei_giants_entries(
            tag_url="https://www.sankei.com/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=7,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 0)


# 384-INGEST: 日刊SPA! (nikkan-spa.jp) tag_scrape tests
class FetchNikkanSpaGiantsEntriesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=JST)

    def test_nikkan_spa_property_attribute_extracted(self):
        # 日刊SPA は `property="article:published_time"` で取れる
        listing_html = """
        <a href="https://nikkan-spa.jp/2150000">giants article</a>
        <a href="https://nikkan-spa.jp/2150001">also giants</a>
        """
        article_html = {
            "https://nikkan-spa.jp/2150000": """
                <meta property="og:title" content="巨人の阿部監督が会見を拒否 | 日刊SPA!">
                <meta property="og:description" content="読売ジャイアンツの会見について">
                <meta property="article:published_time" content="2026-05-18T08:52:30+09:00">
            """,
            "https://nikkan-spa.jp/2150001": """
                <meta property="og:title" content="巨人のスター選手秘話 | 日刊SPA!">
                <meta property="og:description" content="ジャイアンツ歴代の名場面">
                <meta property="article:published_time" content="2026-05-17T08:52:30+09:00">
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_nikkan_spa_giants_entries(
            tag_url="https://nikkan-spa.jp/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=30,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 2)
        # title suffix ` | 日刊SPA!` が strip される
        self.assertEqual(entries[0]["title"], "巨人の阿部監督が会見を拒否")
        self.assertEqual(entries[0]["link"], "https://nikkan-spa.jp/2150000")

    def test_nikkan_spa_old_article_filtered_by_meta_age(self):
        # search 結果が日付 sort でない時、article fetch 後の meta age で 30 日超は filter
        listing_html = """
        <a href="https://nikkan-spa.jp/2137462">old giants</a>
        """
        article_html = {
            "https://nikkan-spa.jp/2137462": """
                <meta property="og:title" content="巨人の昔の話題 | 日刊SPA!">
                <meta property="og:description" content="ジャイアンツ過去記事">
                <meta property="article:published_time" content="2026-01-11T08:52:30+09:00">
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_nikkan_spa_giants_entries(
            tag_url="https://nikkan-spa.jp/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=30,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 0)


# 384-INGEST Phase 3: 中日スポーツ (chunichi `?s=巨人&genre=chuspo`) tag_scrape tests
class FetchChunichiChuspoGiantsEntriesTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=JST)

    def test_chunichi_chuspo_extracts_via_json_ld_date_published(self):
        # 中日スポーツは meta article:published_time 無し、JSON-LD datePublished 有り
        # → 既存 _extract_embedded_published_date で取れる
        listing_html = """
        <a href="https://www.chunichi.co.jp/article/1253368?genre=chuspo">giants</a>
        """
        article_html = {
            "https://www.chunichi.co.jp/article/1253368?genre=chuspo": """
                <meta property="og:title" content="巨人・戸郷翔征 中日戦で完投勝利：中日スポーツ・東京中日スポーツ">
                <meta property="og:description" content="読売ジャイアンツのエースが好投">
                <script type="application/ld+json">
                {"@context":"https://schema.org","@type":"NewsArticle",
                 "headline":"巨人・戸郷翔征 中日戦で完投勝利",
                 "datePublished":"2026-05-19T05:00:00+09:00",
                 "dateModified":"2026-05-19T07:30:00+09:00"}
                </script>
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url and "/article/" not in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_chunichi_chuspo_giants_entries(
            tag_url="https://www.chunichi.co.jp/?s=%E5%B7%A8%E4%BA%BA&genre=chuspo",
            max_age_days=14,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        # title suffix ` ：中日スポーツ・東京中日スポーツ` が strip される
        self.assertEqual(entries[0]["title"], "巨人・戸郷翔征 中日戦で完投勝利")

    def test_yahoo_passthrough_filters_existing_family_keeps_new_media(self):
        # Yahoo!ニュース sports RSS から passthrough 媒体 (産経 / 中日スポ / NHK) +
        # 巨人 keyword を含む item のみ通す
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<item>
  <title>巨人・戸郷翔征が完投勝利 ヤクルト戦で快投(産経新聞)</title>
  <link>https://news.yahoo.co.jp/articles/abc111</link>
  <pubDate>Mon, 19 May 2026 03:00:00 +0900</pubDate>
</item>
<item>
  <title>大谷翔平が今季初の盗塁失敗 ドジャース戦(日刊スポーツ)</title>
  <link>https://news.yahoo.co.jp/articles/abc222</link>
  <pubDate>Mon, 19 May 2026 04:00:00 +0900</pubDate>
</item>
<item>
  <title>巨人・坂本勇人が通算300号 ヤクルト戦で(中日スポーツ)</title>
  <link>https://news.yahoo.co.jp/articles/abc333</link>
  <pubDate>Mon, 19 May 2026 05:00:00 +0900</pubDate>
</item>
<item>
  <title>巨人・阿部監督の采配が議論を呼ぶ(NHK)</title>
  <link>https://news.yahoo.co.jp/articles/abc444</link>
  <pubDate>Mon, 19 May 2026 06:00:00 +0900</pubDate>
</item>
<item>
  <title>阪神タイガースが連勝 巨人を超える勢い(産経新聞)</title>
  <link>https://news.yahoo.co.jp/articles/abc555</link>
  <pubDate>Mon, 19 May 2026 07:00:00 +0900</pubDate>
</item>
<item>
  <title>巨人が逆転勝ち 5連勝(日刊スポーツ)</title>
  <link>https://news.yahoo.co.jp/articles/abc666</link>
  <pubDate>Mon, 19 May 2026 08:00:00 +0900</pubDate>
</item>
</channel>
</rss>"""

        def fake_fetcher(url, **kwargs):
            return _make_response(200, rss_xml)

        entries = scraper.fetch_yahoo_news_sports_giants_entries(
            tag_url="https://news.yahoo.co.jp/rss/categories/sports.xml",
            max_age_days=3,
            now=self.now,
            fetcher=fake_fetcher,
        )
        # passthrough かつ巨人 keyword:
        # - abc111 (産経 + 巨人戸郷) ✓
        # - abc333 (中日スポ + 巨人坂本) ✓
        # - abc444 (NHK + 巨人阿部) ✓
        # - abc555 (産経 + 巨人 keyword in title - 阪神...巨人を超える) ✓ (title に巨人含む)
        # 既存 family (日刊スポ): abc222 (大谷) / abc666 (巨人逆転) は skip (重複防止)
        self.assertEqual(len(entries), 4)
        links = [e["link"] for e in entries]
        self.assertIn("https://news.yahoo.co.jp/articles/abc111", links)
        self.assertIn("https://news.yahoo.co.jp/articles/abc333", links)
        self.assertIn("https://news.yahoo.co.jp/articles/abc444", links)
        self.assertNotIn("https://news.yahoo.co.jp/articles/abc222", links)
        self.assertNotIn("https://news.yahoo.co.jp/articles/abc666", links)

    def test_yahoo_passthrough_age_filter(self):
        # max_age_days 超の item は age_filtered で skip
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>巨人・坂本勇人が通算300号(産経新聞)</title>
  <link>https://news.yahoo.co.jp/articles/old111</link>
  <pubDate>Tue, 13 May 2026 05:00:00 +0900</pubDate>
</item>
</channel></rss>"""

        def fake_fetcher(url, **kwargs):
            return _make_response(200, rss_xml)

        entries = scraper.fetch_yahoo_news_sports_giants_entries(
            tag_url="https://news.yahoo.co.jp/rss/categories/sports.xml",
            max_age_days=3,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 0)

    def test_chunichi_non_giants_filtered(self):
        # 中日 specific (vs 阪神等) で巨人言及無い記事は post_filter で除外
        listing_html = """
        <a href="https://www.chunichi.co.jp/article/1253367?genre=chuspo">non giants</a>
        """
        article_html = {
            "https://www.chunichi.co.jp/article/1253367?genre=chuspo": """
                <meta property="og:title" content="中日・板山祐太郎、阪神戦で反攻打：中日スポーツ・東京中日スポーツ">
                <meta property="og:description" content="中日打線で最も乗っている男">
                <script type="application/ld+json">
                {"@context":"https://schema.org","@type":"NewsArticle",
                 "datePublished":"2026-05-18T23:03:00+09:00"}
                </script>
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url and "/article/" not in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_chunichi_chuspo_giants_entries(
            tag_url="https://www.chunichi.co.jp/?s=%E5%B7%A8%E4%BA%BA&genre=chuspo",
            max_age_days=14,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 0)


# 384-INGEST Phase 2: article:modified_time fallback regression test
class ModifiedTimeFallbackTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=JST)

    def test_modified_time_used_when_published_missing(self):
        # published_time 無し、modified_time あり → modified を fallback に使う
        listing_html = """
        <a href="https://www.asagei.com/excerpt/347876">giants</a>
        """
        article_html = {
            "https://www.asagei.com/excerpt/347876": """
                <meta property="og:title" content="巨人・坂本勇人の一打 | アサ芸プラス">
                <meta property="og:description" content="ジャイアンツの話題">
                <meta property="article:modified_time" content="2026-05-18T11:30:00+09:00">
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_asagei_giants_entries(
            tag_url="https://www.asagei.com/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=30,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "巨人・坂本勇人の一打")
        # published_parsed が modified_time の値 (2026-05-18) で立つ
        self.assertEqual(entries[0]["published_parsed"].tm_year, 2026)
        self.assertEqual(entries[0]["published_parsed"].tm_mon, 5)
        self.assertEqual(entries[0]["published_parsed"].tm_mday, 18)

    def test_published_time_preferred_over_modified_time(self):
        # published_time も modified_time もあれば published_time が優先
        # NOTE: published_parsed は UTC 換算 struct_time を返す設計 (l.101 astimezone(UTC))
        listing_html = """
        <a href="https://www.asagei.com/excerpt/347876">giants</a>
        """
        article_html = {
            "https://www.asagei.com/excerpt/347876": """
                <meta property="og:title" content="巨人・坂本勇人の一打 | アサ芸プラス">
                <meta property="og:description" content="ジャイアンツの話題">
                <meta property="article:published_time" content="2026-05-19T11:00:00+09:00">
                <meta property="article:modified_time" content="2026-05-17T11:30:00+09:00">
            """,
        }

        def fake_fetcher(url, **kwargs):
            if "?s=" in url:
                return _make_response(200, listing_html)
            return _make_response(200, article_html[url])

        entries = scraper.fetch_asagei_giants_entries(
            tag_url="https://www.asagei.com/?s=%E5%B7%A8%E4%BA%BA",
            max_age_days=30,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        # published 5/19 11:00 JST → UTC 5/19 02:00 → tm_mday=19
        # modified の場合は 5/17 11:30 JST → UTC 5/17 02:30 → tm_mday=17 になるはず
        self.assertEqual(entries[0]["published_parsed"].tm_year, 2026)
        self.assertEqual(entries[0]["published_parsed"].tm_mon, 5)
        self.assertEqual(entries[0]["published_parsed"].tm_mday, 19)


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


class FetchSponichiGiantsEntriesTests(unittest.TestCase):
    """337-INGEST Phase 2: sponichi /baseball/ top page + 巨人 filter scraper test。

    URL pattern `/baseball/news/YYYY/MM/DD/kiji/{ID}.html`、URL 内 date で age 判定、
    article 毎に og:title / og:description が「巨人」を含むか post-filter
    (「ジャイアンツ」「Giants」は MLB SF Giants 混入避けるため除外)。
    """

    def setUp(self):
        self.now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=JST)

    def _build_top_html(self, articles: list[tuple[str, str, str, str]]) -> str:
        """articles: list of (year, month, day, kiji_id)."""
        anchors = "".join(
            f'<a href="/baseball/news/{y}/{m}/{d}/kiji/{kid}.html">title-{y}{m}{d}-{kid}</a>'
            for y, m, d, kid in articles
        )
        return f"<html><body>{anchors}</body></html>"

    def _build_article_html(
        self,
        *,
        title: str,
        desc: str = "lead",
    ) -> str:
        meta = (
            f'<meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{desc}">'
        )
        return f"<html><head>{meta}</head><body></body></html>"

    def test_extracts_giants_article_strips_sponichi_brand(self):
        top_html = self._build_top_html(
            [("2026", "05", "14", "20260514s00001173060000c")]
        )
        article_html = self._build_article_html(
            title="巨人・坂本 延長12回に逆転サヨナラ通算300号！ - スポニチ Sponichi Annex 野球",
            desc="巨人・坂本勇人内野手が13日の広島戦でサヨナラ3ランを放った",
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("/baseball/"):
                return _make_response(200, top_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_sponichi_giants_entries(
            tag_url="https://www.sponichi.co.jp/baseball/",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        # sponichi suffix strip 確認
        self.assertEqual(
            entries[0]["title"], "巨人・坂本 延長12回に逆転サヨナラ通算300号！"
        )

    def test_filters_non_giants_articles_by_keyword(self):
        top_html = self._build_top_html(
            [
                ("2026", "05", "14", "ARTICLEa"),
                ("2026", "05", "14", "ARTICLEb"),
            ]
        )
        giants_article = self._build_article_html(
            title="巨人・坂本 サヨナラ300号",
            desc="巨人勝利",
        )
        # MLB SF Giants 文脈 (大谷 vs ジャイアンツ) は filter で除外されるべき
        mlb_giants_article = self._build_article_html(
            title="大谷翔平 ジャイアンツ戦先発",
            desc="ドジャースの大谷投手がジャイアンツ戦に登板",
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("/baseball/"):
                return _make_response(200, top_html)
            if "ARTICLEa" in url:
                return _make_response(200, giants_article)
            return _make_response(200, mlb_giants_article)

        entries = scraper.fetch_sponichi_giants_entries(
            tag_url="https://www.sponichi.co.jp/baseball/",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertIn("ARTICLEa", entries[0]["link"])
        self.assertIn("巨人", entries[0]["title"])

    def test_filters_articles_older_than_max_age_days(self):
        # 古い記事は URL date で age window 外として skip
        top_html = self._build_top_html(
            [
                ("2026", "04", "30", "OLD"),
                ("2026", "05", "14", "NEW"),
            ]
        )
        giants_article = self._build_article_html(
            title="巨人・坂本 サヨナラ", desc="巨人勝利"
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("/baseball/"):
                return _make_response(200, top_html)
            return _make_response(200, giants_article)

        entries = scraper.fetch_sponichi_giants_entries(
            tag_url="https://www.sponichi.co.jp/baseball/",
            max_age_days=7,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertIn("NEW", entries[0]["link"])

    def test_uses_url_date_at_noon_jst_for_published_time(self):
        # sponichi は published_time meta が無いので URL date / 12:00 JST fallback
        top_html = self._build_top_html(
            [("2026", "05", "14", "abc123")]
        )
        article_html = self._build_article_html(
            title="巨人・坂本 サヨナラ", desc="巨人勝利"
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("/baseball/"):
                return _make_response(200, top_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_sponichi_giants_entries(
            tag_url="https://www.sponichi.co.jp/baseball/",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        # 12:00 JST = 03:00 UTC, "Wed, 14 May 2026 03:00:00 GMT" 形式
        self.assertIn("14 May 2026 03:00:00", entries[0]["published"])

    def test_registered_in_scraper_kinds(self):
        self.assertIn("sponichi_giants_filter", list(scraper.list_scraper_kinds()))


class FetchTokyoSportsGiantsEntriesTests(unittest.TestCase):
    """337-INGEST Phase 1: tokyo-sports label page scraper test。

    URL pattern `/articles/-/{numeric_id}`、published time は meta property
    `article:published_time` の ISO8601 から取る。URL に date 無し。
    """

    def setUp(self):
        self.now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=JST)

    def _build_label_html(self, article_ids: list[str]) -> str:
        anchors = "".join(
            f'<a href="/articles/-/{aid}">title-{aid}</a>' for aid in article_ids
        )
        return f"<html><body>{anchors}</body></html>"

    def _build_article_html(
        self,
        *,
        title: str,
        desc: str = "lead",
        published_iso: str = "",
    ) -> str:
        meta = (
            f'<meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{desc}">'
        )
        if published_iso:
            meta += f'<meta property="article:published_time" content="{published_iso}">'
        return f"<html><head>{meta}</head><body></body></html>"

    def test_extracts_articles_and_strips_tospo_web_suffix(self):
        label_html = self._build_label_html(["388121"])
        article_html = self._build_article_html(
            title="【巨人】阿部監督 坂本勇人の逆転サヨナラ３ランから見いだした若手への教訓 | 東スポWEB",
            published_iso="2026-05-14T01:07:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("%E5%B7%A8%E4%BA%BA"):
                return _make_response(200, label_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_tokyo_sports_giants_entries(
            tag_url="https://www.tokyo-sports.co.jp/list/label/%E5%B7%A8%E4%BA%BA",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        # 「 | 東スポWEB」 suffix を strip
        self.assertEqual(
            entries[0]["title"],
            "【巨人】阿部監督 坂本勇人の逆転サヨナラ３ランから見いだした若手への教訓",
        )
        self.assertEqual(
            entries[0]["link"], "https://www.tokyo-sports.co.jp/articles/-/388121"
        )

    def test_filters_articles_older_than_max_age_days(self):
        label_html = self._build_label_html(["388100", "388121"])
        old_article = self._build_article_html(
            title="古い記事",
            published_iso="2026-04-30T10:00:00+09:00",  # 2 weeks old
        )
        new_article = self._build_article_html(
            title="新しい記事",
            published_iso="2026-05-14T01:07:00+09:00",
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("%E5%B7%A8%E4%BA%BA"):
                return _make_response(200, label_html)
            if "388100" in url:
                return _make_response(200, old_article)
            return _make_response(200, new_article)

        entries = scraper.fetch_tokyo_sports_giants_entries(
            tag_url="https://www.tokyo-sports.co.jp/list/label/%E5%B7%A8%E4%BA%BA",
            max_age_days=7,
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(len(entries), 1)
        self.assertIn("388121", entries[0]["link"])

    def test_drops_articles_without_published_time(self):
        # tokyo-sports は URL に date 無いので published_time meta 欠落 = age 判定不可
        # → age filtered として skip
        label_html = self._build_label_html(["388121"])
        article_html = self._build_article_html(
            title="published_time 無し記事 | 東スポWEB",
            published_iso="",  # no meta
        )

        def fake_fetcher(url, **kwargs):
            if url.endswith("%E5%B7%A8%E4%BA%BA"):
                return _make_response(200, label_html)
            return _make_response(200, article_html)

        entries = scraper.fetch_tokyo_sports_giants_entries(
            tag_url="https://www.tokyo-sports.co.jp/list/label/%E5%B7%A8%E4%BA%BA",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(entries, [])

    def test_registered_in_scraper_kinds(self):
        self.assertIn("tokyo_sports_giants_label", list(scraper.list_scraper_kinds()))


class FetchYoutubeChannelEntriesTests(unittest.TestCase):
    """RELIABILITY-2026-05-08-Y: YouTube channel page scraper test."""

    def setUp(self):
        self.now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=JST)

    def _build_channel_html(self, items: list[dict]) -> str:
        import json as _json

        data = {
            "contents": {
                "twoColumnBrowseResultsRenderer": {
                    "tabs": [
                        {
                            "tabRenderer": {
                                "selected": True,
                                "title": "動画",
                                "content": {
                                    "richGridRenderer": {
                                        "contents": [
                                            {
                                                "richItemRenderer": {
                                                    "content": {
                                                        "lockupViewModel": {
                                                            "contentId": item["id"],
                                                            "metadata": {
                                                                "lockupMetadataViewModel": {
                                                                    "title": {"content": item["title"]},
                                                                    "metadata": {
                                                                        "contentMetadataViewModel": {
                                                                            "metadataRows": [
                                                                                {
                                                                                    "metadataParts": [
                                                                                        {"text": {"content": item["age_text"]}}
                                                                                    ]
                                                                                }
                                                                            ]
                                                                        }
                                                                    },
                                                                }
                                                            },
                                                        }
                                                    }
                                                }
                                            }
                                            for item in items
                                        ]
                                    }
                                },
                            }
                        }
                    ]
                }
            }
        }
        return f"<html><body><script>var ytInitialData = {_json.dumps(data)};</script></body></html>"

    def test_extracts_video_entries_with_relative_time(self):
        html = self._build_channel_html(
            [
                {"id": "AAAAAAAAAAA", "title": "巨人 5/8 ニュース", "age_text": "1 日前"},
                {"id": "BBBBBBBBBBB", "title": "古い動画", "age_text": "30 日前"},
                {"id": "CCCCCCCCCCC", "title": "新しめ", "age_text": "3 時間前"},
            ]
        )

        def fake_fetcher(url, **kwargs):
            return _make_response(200, html)

        entries = scraper.fetch_youtube_channel_entries(
            tag_url="https://www.youtube.com/channel/UCxxxxxx/videos",
            max_age_days=14,
            now=self.now,
            fetcher=fake_fetcher,
        )
        # 1日前 と 3時間前 が pass、30日前は filter 外
        ids = [e["link"].split("=")[1] for e in entries]
        self.assertIn("AAAAAAAAAAA", ids)
        self.assertIn("CCCCCCCCCCC", ids)
        self.assertNotIn("BBBBBBBBBBB", ids)

    def test_skips_premiere_upcoming_entries(self):
        # premiere upcoming = relative time に「日前」等が含まれない → skip
        html = self._build_channel_html(
            [
                {
                    "id": "AAAAAAAAAAA",
                    "title": "予約配信",
                    "age_text": "2026/05/10 6:00 にプレミア公開",
                },
            ]
        )

        def fake_fetcher(url, **kwargs):
            return _make_response(200, html)

        entries = scraper.fetch_youtube_channel_entries(
            tag_url="https://www.youtube.com/channel/UCxxxxxx/videos",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(entries, [])

    def test_returns_empty_when_initial_data_missing(self):
        def fake_fetcher(url, **kwargs):
            return _make_response(200, "<html><body>no ytInitialData here</body></html>")

        entries = scraper.fetch_youtube_channel_entries(
            tag_url="https://www.youtube.com/channel/UCxxxxxx/videos",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(entries, [])

    def test_404_returns_empty(self):
        def fake_fetcher(url, **kwargs):
            return _make_response(404, "")

        entries = scraper.fetch_youtube_channel_entries(
            tag_url="https://www.youtube.com/channel/UCxxxxxx/videos",
            now=self.now,
            fetcher=fake_fetcher,
        )
        self.assertEqual(entries, [])

    def test_relative_time_parsing(self):
        from datetime import datetime as _dt

        now = _dt(2026, 5, 8, 12, 0, 0, tzinfo=JST)
        result = scraper._parse_youtube_relative_time("3 日前", now=now)
        self.assertIsNotNone(result)
        self.assertEqual(result.day, 5)

        result = scraper._parse_youtube_relative_time("10 時間前", now=now)
        self.assertIsNotNone(result)

        # 不明 / プレミア公開 → None
        self.assertIsNone(scraper._parse_youtube_relative_time("プレミア公開", now=now))
        self.assertIsNone(scraper._parse_youtube_relative_time("", now=now))


if __name__ == "__main__":
    unittest.main()
