from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_json(relative_path: str):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class GameLiveSourcePolicyConfigTests(unittest.TestCase):
    def test_game_live_primary_sources_are_hochi_only(self):
        sources = _load_json("config/rss_sources.json")
        live_primary = {
            source["name"]
            for source in sources
            if "game_live_primary" in set(source.get("role") or [])
        }

        self.assertEqual(
            live_primary,
            {
                "スポーツ報知巨人班X",
                "スポーツ報知X",
                "報知野球X",
                "スポーツ報知 巨人 tag",
            },
        )

    def test_dazn_x_is_video_signal_not_article_source(self):
        sources = _load_json("config/rss_sources.json")
        dazn = next(source for source in sources if source["name"] == "DAZNベースボールX")
        roles = set(dazn["role"])

        self.assertEqual(
            dazn["url"],
            "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/DAZNJPNBaseball",
        )
        self.assertEqual(dazn["type"], "social_news")
        self.assertIn("game_live_video_signal", roles)
        self.assertIn("media_quote_only", roles)
        self.assertIn("review_only", roles)
        self.assertNotIn("article_source", roles)

    def test_postgame_video_sources_include_confirmed_official_broadcast_and_dazn(self):
        sources = _load_json("config/youtube_video_sources.json")
        by_name = {source["name"]: source for source in sources}

        self.assertEqual(
            by_name["巨人公式YouTube"]["url"],
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCXxg0igSYUp0tqdd6luPEnQ",
        )
        self.assertEqual(
            by_name["DRAMATIC BASEBALL"]["url"],
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCpj_nD9850tykDqIrjtIXdg",
        )
        self.assertEqual(
            by_name["DAZNベースボール"]["url"],
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCyeDNNizMGbVsn_8Ttc3FIw",
        )
        for source_name in ("巨人公式YouTube", "DRAMATIC BASEBALL", "DAZNベースボール"):
            self.assertIn("postgame_video_source", set(by_name[source_name]["role"]))
            self.assertIn("review_only", set(by_name[source_name]["role"]))


if __name__ == "__main__":
    unittest.main()
