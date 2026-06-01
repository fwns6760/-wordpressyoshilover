"""451: tests for src.video_radar (動画レーダー、 公式/OB YouTube RSS read-only)。"""
from __future__ import annotations

import unittest

from src import video_radar as vr

_FIXTURE_FEED = """<?xml version='1.0'?>
<feed xmlns:yt='http://www.youtube.com/xml/schemas/2015'>
  <title>巨人公式YouTube</title>
  <entry>
    <yt:videoId>VIDNOSTALGIA</yt:videoId>
    <title>【名場面】2013年 坂本勇人の伝説のサヨナラ弾</title>
    <published>2026-05-30T10:00:00+00:00</published>
  </entry>
  <entry>
    <yt:videoId>VIDPLAIN</yt:videoId>
    <title>本日のお知らせ</title>
    <published>2026-05-31T10:00:00+00:00</published>
  </entry>
</feed>"""


class ClassifyVideoTests(unittest.TestCase):
    def test_nostalgia_title_scores_and_tags(self):
        score, tag = vr.classify_video(
            "【名場面】2013年 坂本勇人の伝説のサヨナラ弾",
            role="official",
            player="坂本勇人",
        )
        self.assertGreaterEqual(score, 2)
        self.assertIn(tag, ("名場面回顧", "OB・懐かし", "過去ハイライト", "今日とつながる"))

    def test_ob_channel_boost(self):
        # OB 本人チャンネルは懐かし寄りで加点
        s_ob, _ = vr.classify_video("現役時代の思い出を語る", role="giants_ob", player="")
        s_plain, _ = vr.classify_video("現役時代の思い出を語る", role="media", player="")
        self.assertGreater(s_ob, s_plain)

    def test_today_context_tag(self):
        score, tag = vr.classify_video(
            "坂本勇人 好プレー集",
            role="official",
            player="坂本勇人",
            today_players={"坂本勇人"},
        )
        self.assertEqual(tag, "今日とつながる")

    def test_plain_title_low_score(self):
        score, _ = vr.classify_video("本日のお知らせ", role="media", player="")
        self.assertLess(score, 2)


class GatherRadarVideosTests(unittest.TestCase):
    def test_filters_low_score_and_sorts(self):
        def detect(title):
            return "坂本勇人" if "坂本" in title else ""

        out = vr.gather_radar_videos(
            channels=[{"channel_id": "UCtest", "name": "巨人公式", "role": "official", "status": "confirmed"}],
            detect_player_fn=detect,
            fetch_fn=lambda url: _FIXTURE_FEED,
            min_score=2,
        )
        # nostalgia entry のみ残る (plain は score<2 で落ちる)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["video_id"], "VIDNOSTALGIA")
        self.assertEqual(out[0]["player"], "坂本勇人")
        self.assertIn("watch?v=VIDNOSTALGIA", out[0]["video_url"])
        self.assertGreaterEqual(out[0]["score"], 2)

    def test_fetch_error_channel_skipped(self):
        def boom(url):
            raise RuntimeError("network down")

        out = vr.gather_radar_videos(
            channels=[{"channel_id": "UCx", "name": "x", "role": "ob", "status": "candidate"}],
            detect_player_fn=lambda t: "",
            fetch_fn=boom,
        )
        self.assertEqual(out, [])


class LoadRadarChannelsTests(unittest.TestCase):
    def test_loads_all_but_excludes_excluded(self):
        chans = vr.load_radar_channels()
        ids = {c["channel_id"] for c in chans}
        # confirmed 公式は含む
        self.assertIn("UCXxg0igSYUp0tqdd6luPEnQ", ids)
        # status=excluded のサンプルは除外
        self.assertNotIn("UC0000000000000000000000", ids)
        # candidate な OB チャンネルも「全部」方針で含む
        self.assertIn("UCGynN2H7DcNjpN7Qng4dZmg", ids)  # 上原浩治の雑談魂


if __name__ == "__main__":
    unittest.main()
