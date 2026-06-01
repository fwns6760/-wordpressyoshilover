"""451/SNS: tests for src.sns_topic_cards (RSSキーワード→カード自動生成)。"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from src import sns_topic_cards as tc


class HeadlineTests(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(tc.headline_from_events(["完投", "初"]), "プロ初完投！")
        self.assertEqual(tc.headline_from_events(["完投"]), "完投！")
        self.assertEqual(tc.headline_from_events(["ホームラン", "復帰"]), "復帰即アーチ！")
        self.assertEqual(tc.headline_from_events(["勝利", "初"]), "今季初勝利！")
        self.assertEqual(tc.headline_from_events(["好投"]), "好投！")
        self.assertEqual(tc.headline_from_events([]), "注目！")


class ExtractTests(unittest.TestCase):
    _FEED = (
        "<rss><channel>"
        "<item><title>竹丸和幸がプロ初完投 8回111球10K</title><link>http://x/1</link></item>"
        "<item><title>本日の練習について</title><link>http://x/2</link></item>"
        "</channel></rss>"
    )

    def test_extract_player_and_events(self):
        kws = tc.extract_rss_keywords(
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
            fetch_fn=lambda u: self._FEED, handles=["h"],
        )
        self.assertEqual(len(kws), 1)
        self.assertEqual(kws[0]["player"], "竹丸和幸")
        self.assertIn("完投", kws[0]["events"])
        self.assertIn("初", kws[0]["events"])


class BuildTopicCardsTests(unittest.TestCase):
    def _db(self):
        fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE batting_logs (game_id TEXT, player_canonical TEXT, AB INT, H INT, RBI INT)")
        conn.execute("CREATE TABLE pitching_logs (game_id TEXT, player_canonical TEXT, result_mark TEXT, K INT, IP REAL, ER INT)")
        conn.executemany("INSERT INTO pitching_logs VALUES (?,?,?,?,?,?)", [
            ("g1", "竹丸和幸", "○", 10, 8.0, 1),
            ("g2", "竹丸和幸", "●", 9, 5.0, 3),
        ])
        conn.commit(); conn.close()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_pitcher_topic_card(self):
        feed = ("<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
                "<link>http://x/1</link></item></channel></rss>")
        cards = tc.build_topic_cards(
            self._db(), fetch_fn=lambda u: feed, max_cards=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
        )
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["kind"], "pitcher")
        self.assertEqual(cards[0]["headline"], "プロ初完投！")
        self.assertIn("プロ初完投", cards[0]["html"])
        self.assertIn("竹丸和幸", cards[0]["html"])


if __name__ == "__main__":
    unittest.main()
