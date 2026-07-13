"""451: tests for src.video_radar (X-buzz-post radar、 RSSHub read-only、 YouTube 不使用)。"""
from __future__ import annotations

import unittest

from src import video_radar as vr

_FEED = (
    "<rss><channel>"
    "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
    "<description>劇的な一打</description>"
    "<link>https://x.com/yomiuri_giants/status/111</link></item>"
    "<item><title>本日の練習について</title>"
    "<description>通常の連絡</description>"
    "<link>https://x.com/yomiuri_giants/status/222</link></item>"
    "</channel></rss>"
)


class ClassifyPostTests(unittest.TestCase):
    def test_buzz_player_top_score_and_tag(self):
        score, tag = vr.classify_post(
            "坂本勇人 サヨナラ満塁ホームラン", player="坂本勇人", buzz_players={"坂本勇人"}
        )
        self.assertEqual(tag, "Xで話題")
        self.assertGreaterEqual(score, 5)

    def test_nostalgia_tag(self):
        score, tag = vr.classify_post("あの日の名場面を振り返る", player="")
        self.assertGreaterEqual(score, 2)
        self.assertEqual(tag, "懐かし・名場面")

    def test_plain_low_score(self):
        score, _ = vr.classify_post("本日の練習について", player="")
        self.assertLess(score, 2)


class ExtractItemsTests(unittest.TestCase):
    def test_text_and_url(self):
        items = vr._extract_rss_items(_FEED)
        self.assertEqual(len(items), 2)
        self.assertIn("坂本勇人", items[0]["text"])
        self.assertEqual(items[0]["url"], "https://x.com/yomiuri_giants/status/111")


class FetchBuzzingPlayersTests(unittest.TestCase):
    def test_counts_and_threshold(self):
        feed = (
            "<rss><channel>"
            "<item><title>坂本勇人 好調</title><link>http://x/1</link></item>"
            "<item><title>坂本勇人 また安打</title><link>http://x/2</link></item>"
            "<item><title>戸郷翔征 完投</title><link>http://x/3</link></item>"
            "</channel></rss>"
        )
        def detect(t):
            for n in ("坂本勇人", "戸郷翔征"):
                if n[:3] in t:
                    return n
            return ""
        buzz = vr.fetch_buzzing_players(
            detect_player_fn=detect, fetch_fn=lambda u: feed,
            handles=["yomiuri_giants"], min_mentions=2,
        )
        self.assertEqual(buzz.get("坂本勇人"), 2)
        self.assertNotIn("戸郷翔征", buzz)

    def test_retweets_are_not_counted(self):
        feed = (
            "<rss><channel>"
            "<item><title>RT 小早川宗一郎: 坂本勇人 好調</title><link>http://x/1</link></item>"
            "<item><title>戸郷翔征 完投</title><link>http://x/2</link></item>"
            "</channel></rss>"
        )
        def detect(t):
            for n in ("坂本勇人", "戸郷翔征"):
                if n[:2] in t:
                    return n
            return ""
        buzz = vr.fetch_buzzing_players(
            detect_player_fn=detect, fetch_fn=lambda u: feed,
            handles=["hochi_giants"], min_mentions=1,
        )
        self.assertNotIn("坂本勇人", buzz)
        self.assertEqual(buzz.get("戸郷翔征"), 1)


class GatherBuzzPostsTests(unittest.TestCase):
    def test_filters_and_sorts_with_url(self):
        def detect(t):
            return "坂本勇人" if "坂本" in t else ""
        # この test は score フィルタの検証。 動画/鮮度ゲートは別 test で扱うため無効化。
        posts = vr.gather_buzz_posts(
            detect_player_fn=detect, fetch_fn=lambda u: _FEED,
            handles=["yomiuri_giants"], buzz_players={"坂本勇人"}, min_score=2,
            require_video=False, max_age_hours=1e9,
        )
        # 坂本のバズ投稿のみ残る (本日の練習は score<2)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["player"], "坂本勇人")
        self.assertEqual(posts[0]["url"], "https://x.com/yomiuri_giants/status/111")
        self.assertEqual(posts[0]["type_tag"], "Xで話題")

    def test_retweets_are_not_gathered(self):
        feed = (
            "<rss><channel>"
            "<item><title>RT 小早川宗一郎: 坂本勇人 サヨナラ満塁ホームラン</title>"
            "<description>劇的 &lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/1/img/a.jpg&quot;&gt;</description>"
            "<link>https://x.com/y/status/1</link></item>"
            "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
            "<description>劇的 &lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/2/img/b.jpg&quot;&gt;</description>"
            "<link>https://x.com/y/status/2</link></item>"
            "</channel></rss>"
        )
        det = lambda t: "坂本勇人" if "坂本" in t else ""  # noqa: E731
        posts = vr.gather_buzz_posts(
            detect_player_fn=det, fetch_fn=lambda u: feed, handles=["hochi_giants"],
            buzz_players={"坂本勇人"}, min_score=2, require_video=True, max_age_hours=1e9,
        )
        self.assertEqual([p["url"] for p in posts], ["https://x.com/y/status/2"])

    def test_require_video_keeps_only_video_posts(self):
        # 動画サムネ (amplify_video_thumb) を持つ投稿だけ残す。
        feed = (
            "<rss><channel>"
            "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
            "<description>劇的 &lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/1/img/a.jpg&quot;&gt;</description>"
            "<link>https://x.com/y/status/1</link></item>"
            "<item><title>坂本勇人 また活躍</title><description>写真のみ "
            "&lt;img src=&quot;https://pbs.twimg.com/media/b.jpg&quot;&gt;</description>"
            "<link>https://x.com/y/status/2</link></item>"
            "</channel></rss>"
        )
        det = lambda t: "坂本勇人" if "坂本" in t else ""  # noqa: E731
        posts = vr.gather_buzz_posts(
            detect_player_fn=det, fetch_fn=lambda u: feed, handles=["y"],
            buzz_players={"坂本勇人"}, min_score=2, require_video=True, max_age_hours=1e9,
        )
        self.assertEqual([p["url"] for p in posts], ["https://x.com/y/status/1"])
        self.assertTrue(posts[0]["has_video"])

    def test_max_age_hours_drops_old_posts(self):
        from datetime import datetime, timezone
        feed = (
            "<rss><channel>"
            "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
            "<description>新しい &lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/1/img/a.jpg&quot;&gt;</description>"
            "<link>https://x.com/y/status/1</link>"
            "<pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate></item>"
            "<item><title>坂本勇人 古い満塁ホームラン</title>"
            "<description>古い &lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/2/img/b.jpg&quot;&gt;</description>"
            "<link>https://x.com/y/status/2</link>"
            "<pubDate>Mon, 25 May 2026 09:00:00 GMT</pubDate></item>"
            "</channel></rss>"
        )
        det = lambda t: "坂本勇人" if "坂本" in t else ""  # noqa: E731
        now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)  # 6/1 09:00 から 3h
        posts = vr.gather_buzz_posts(
            detect_player_fn=det, fetch_fn=lambda u: feed, handles=["y"],
            buzz_players={"坂本勇人"}, min_score=2, require_video=True,
            now=now, max_age_hours=24,
        )
        # 24h 以内の 1 件のみ (5/25 の古い投稿は除外)
        self.assertEqual([p["url"] for p in posts], ["https://x.com/y/status/1"])

    def test_fetch_error_skipped(self):
        def boom(u):
            raise RuntimeError("down")
        posts = vr.gather_buzz_posts(
            detect_player_fn=lambda t: "", fetch_fn=boom, handles=["x"],
        )
        self.assertEqual(posts, [])


if __name__ == "__main__":
    unittest.main()


class PhotoAndArticleTests(unittest.TestCase):
    """2026-07-10 user「記事も。報知とか公式とかの記事や写真系」。"""

    _FEED3 = (
        "<rss><channel>"
        "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
        "<description>劇的 &lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/1/img/a.jpg&quot;&gt;</description>"
        "<link>https://x.com/y/status/1</link></item>"
        "<item><title>坂本勇人 練習の様子 衝撃</title><description>写真 "
        "&lt;img src=&quot;https://pbs.twimg.com/media/b.jpg&quot;&gt;</description>"
        "<link>https://x.com/y/status/2</link></item>"
        "<item><title>坂本勇人 劇的な独占インタビュー記事</title>"
        "<description>記事リンクのみ</description>"
        "<link>https://x.com/y/status/3</link></item>"
        "</channel></rss>"
    )

    def _gather(self, **kw):
        det = lambda t: "坂本勇人" if "坂本" in t else ""  # noqa: E731
        return vr.gather_buzz_posts(
            detect_player_fn=det, fetch_fn=lambda u: self._FEED3, handles=["y"],
            buzz_players={"坂本勇人"}, min_score=2, max_age_hours=1e9, **kw,
        )

    def test_flag_on_keeps_photo_but_drops_article(self):
        # 2026-07-13 user「巨人の記事型引用SNSはでてこなくていい」:
        # flag ON でも 記事📰 (メディア無し) は通さない。写真📷は通す。
        posts = self._gather(require_video=True, allow_photo_and_article=True)
        urls = [p["url"] for p in posts]
        self.assertIn("https://x.com/y/status/1", urls)  # 動画
        self.assertIn("https://x.com/y/status/2", urls)  # 写真
        self.assertNotIn("https://x.com/y/status/3", urls)  # 記事 (テキストのみ)
        photo = [p for p in posts if p["url"].endswith("/2")][0]
        self.assertFalse(photo["has_video"])
        self.assertTrue(photo["has_image"])

    def test_flag_off_keeps_video_only(self):
        posts = self._gather(require_video=True, allow_photo_and_article=False)
        self.assertEqual([p["url"] for p in posts], ["https://x.com/y/status/1"])
