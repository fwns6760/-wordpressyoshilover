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


class QuoteCaptionsTests(unittest.TestCase):
    def _db(self):
        fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE batting_logs (game_id TEXT, team_name TEXT, player_canonical TEXT, AB INT, H INT, RBI INT)")
        conn.execute("CREATE TABLE pitching_logs (game_id TEXT, team_name TEXT, player_canonical TEXT, result_mark TEXT, K INT, IP REAL, ER INT)")
        # 巨人投手 + 他球団投手(NER誤検出想定)
        conn.executemany("INSERT INTO pitching_logs VALUES (?,?,?,?,?,?,?)", [
            ("g1", "巨人", "竹丸和幸", "○", 10, 8.0, 1),
            ("g2", "楽天", "他球団投手", "○", 9, 6.0, 2),
        ])
        conn.commit(); conn.close()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_caption_giants_only_with_data(self):
        feed = (
            "<rss><channel>"
            "<item><title>竹丸和幸 プロ初完投 8回10K</title><link>http://x/1</link></item>"
            "<item><title>他球団投手 完投</title><link>http://x/2</link></item>"
            "</channel></rss>"
        )
        caps = tc.build_quote_captions(
            self._db(), fetch_fn=lambda u: feed, max_captions=5,
            detect_player_fn=lambda t: ("竹丸和幸" if "竹丸" in t else ("他球団投手" if "他球団" in t else "")),
        )
        names = [c["player"] for c in caps]
        self.assertIn("竹丸和幸", names)        # 巨人=残る
        self.assertNotIn("他球団投手", names)   # 他球団=除外 (giants verify)
        cap = next(c for c in caps if c["player"] == "竹丸和幸")["caption"]
        self.assertIn("プロ初完投", cap)
        self.assertIn("10K", cap)              # データ行 (pitching_logs K=10)


class ReplyCandidatesTests(unittest.TestCase):
    def _db(self):
        fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE batting_logs (game_id TEXT, team_name TEXT, player_canonical TEXT, AB INT, H INT, RBI INT)")
        conn.execute("CREATE TABLE pitching_logs (game_id TEXT, team_name TEXT, player_canonical TEXT, result_mark TEXT, K INT, IP REAL, ER INT)")
        conn.execute("INSERT INTO pitching_logs VALUES ('g1','巨人','竹丸和幸','○',10,8.0,1)")
        conn.commit(); conn.close()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_reply_candidate_keeps_target_url_and_voice(self):
        feed = ("<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
                "<link>https://x.com/hochi_giants/status/12345</link></item></channel></rss>")
        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: feed, max_replies=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
        )
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["tweet_id"], "12345")     # 返信先 tweet id
        self.assertIn("status/12345", reps[0]["url"])
        self.assertIn("プロ初完投", reps[0]["reply"])       # 同じ声
        self.assertIn("10K", reps[0]["reply"])             # データ

    def test_reply_uses_voice_comment_fn_when_given(self):
        # ③ 順位燃料: comment_fn (ヨシラバーボイス) が返れば数字 1 行でなくその文を使う。
        feed = ("<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
                "<link>https://x.com/hochi_giants/status/12345</link></item></channel></rss>")
        seen = {}

        def _voice(parent_text, player):
            seen["parent"] = parent_text
            seen["player"] = player
            return "竹丸和幸、初完投か。球数は嵩んだけど中継ぎ温存できたのがデカい。次も任せたいわ。"

        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: feed, max_replies=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
            comment_fn=_voice,
        )
        self.assertEqual(len(reps), 1)
        self.assertIn("中継ぎ温存", reps[0]["reply"])      # ボイス文が採用される
        self.assertNotIn("10K", reps[0]["reply"])          # 数字 1 行 fallback ではない
        self.assertIn("竹丸和幸", seen["player"])          # 親ツイート本文 + player が渡る
        self.assertIn("プロ初完投", seen["parent"])

    def test_reply_falls_back_when_comment_fn_empty(self):
        # comment_fn が空文字 (LLM 失敗 / safety NG) なら数字 1 行へ fallback。
        feed = ("<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
                "<link>https://x.com/hochi_giants/status/12345</link></item></channel></rss>")
        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: feed, max_replies=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
            comment_fn=lambda parent, player: "",
        )
        self.assertEqual(len(reps), 1)
        self.assertIn("10K", reps[0]["reply"])             # fallback の数字行

    def test_reply_intent_url(self):
        from src.x_post_mail_lane import encode_x_reply_intent_url
        u = encode_x_reply_intent_url("竹丸和幸 痺れた", "12345")
        self.assertIn("in_reply_to=12345", u)
        self.assertIn("text=", u)


if __name__ == "__main__":
    unittest.main()
