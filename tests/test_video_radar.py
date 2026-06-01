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


class GatherBuzzPostsTests(unittest.TestCase):
    def test_filters_and_sorts_with_url(self):
        def detect(t):
            return "坂本勇人" if "坂本" in t else ""
        posts = vr.gather_buzz_posts(
            detect_player_fn=detect, fetch_fn=lambda u: _FEED,
            handles=["yomiuri_giants"], buzz_players={"坂本勇人"}, min_score=2,
        )
        # 坂本のバズ投稿のみ残る (本日の練習は score<2)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["player"], "坂本勇人")
        self.assertEqual(posts[0]["url"], "https://x.com/yomiuri_giants/status/111")
        self.assertEqual(posts[0]["type_tag"], "Xで話題")

    def test_fetch_error_skipped(self):
        def boom(u):
            raise RuntimeError("down")
        posts = vr.gather_buzz_posts(
            detect_player_fn=lambda t: "", fetch_fn=boom, handles=["x"],
        )
        self.assertEqual(posts, [])


if __name__ == "__main__":
    unittest.main()
