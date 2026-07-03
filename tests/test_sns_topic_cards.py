"""451/SNS: tests for src.sns_topic_cards (RSSキーワード→カード自動生成)。"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from src import sns_topic_cards as tc


class HeadlineTests(unittest.TestCase):
    def test_mapping(self):
        # 2026-06-11: 複合 claim は source_text の literal 連続語が必要 (token 合成禁止)
        self.assertEqual(tc.headline_from_events(["完投", "初"]), "完投！")
        self.assertEqual(tc.headline_from_events(["完投"], "プロ初完投の快投"), "プロ初完投！")
        self.assertEqual(tc.headline_from_events(["完投"]), "完投！")
        self.assertEqual(
            tc.headline_from_events(["ホームラン", "復帰"], "復帰した男が一発"), "復帰即アーチ！")
        self.assertEqual(tc.headline_from_events(["ホームラン", "復帰"]), "一発！")
        self.assertEqual(
            tc.headline_from_events(["勝利", "初"], "今季初勝利を挙げた"), "今季初勝利！")
        self.assertEqual(tc.headline_from_events(["好投"]), "好投！")
        self.assertEqual(tc.headline_from_events([]), "注目！")

    def test_no_fabricated_first_win_from_token_bag(self):
        """報知「古巣楽天と初対決 勝てば…12球団勝利」→「今季初勝利！」事故の回帰。

        「初」(初対決) と「勝利」(勝てば〜勝利) が別文脈で同居しても合成しない。
        """
        title = "「さまざまな思い出のある球場」巨人・田中将大が古巣楽天と初対決 勝てば則本に続き１２球団勝利"
        events = [e for e in tc._EVENT_WORDS if e in title]
        self.assertIn("初", events)
        self.assertIn("勝利", events)
        self.assertNotEqual(tc.headline_from_events(events, title), "今季初勝利！")


class ReplyFallbackVariationTests(unittest.TestCase):
    """2026-06-11 user「同じような文章が多い。AIっぽい」: プール選択の検証。"""

    def _db(self):
        import tempfile
        path = tempfile.mktemp(suffix=".db")
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE batting_logs (game_id TEXT, player_canonical TEXT,"
            " team_name TEXT, AB INT, H INT, RBI INT);"
            "CREATE TABLE pitching_logs (game_id TEXT, player_canonical TEXT,"
            " team_name TEXT, result_mark TEXT, K INT, IP REAL, ER INT);"
        )
        conn.commit(); conn.close()
        return path

    def test_deterministic_per_post(self):
        db = self._db()
        a1 = tc._yoshilover_reply_fallback(db, "岡本和真", ["起用"], "岡本和真をスタメン起用")
        a2 = tc._yoshilover_reply_fallback(db, "岡本和真", ["起用"], "岡本和真をスタメン起用")
        self.assertEqual(a1, a2)  # 同じ親投稿 → 常に同じ文 (dedup 安定)

    def test_varies_across_posts(self):
        db = self._db()
        outs = {
            tc._yoshilover_reply_fallback(db, "岡本和真", ["起用"], f"スタメン起用 その{i}")
            for i in range(8)
        }
        self.assertGreaterEqual(len(outs), 2)  # 8 投稿で最低 2 種以上の文面

    def test_no_hedge_phrases(self):
        db = self._db()
        for i in range(8):
            for ev in (["起用"], ["昇格"], ["復帰"], []):
                t = tc._yoshilover_reply_fallback(db, "岡本和真", ev, f"親投稿 {ev} {i}")
                self.assertNotIn("見方が分かれ", t)
                self.assertNotIn("見たいです", t)
                self.assertLessEqual(len(t), 180)


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
        conn.execute("INSERT INTO batting_logs VALUES ('g1','巨人','坂本勇人',100,25,10)")
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
            handles=["hochi_giants"],
        )
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["tweet_id"], "12345")     # 返信先 tweet id
        self.assertEqual(reps[0]["handle"], "hochi_giants")
        self.assertIn("status/12345", reps[0]["url"])
        self.assertIn("プロ初完投", reps[0]["reply"])       # 同じ声
        self.assertIn("10K", reps[0]["reply"])             # データ
        self.assertTrue(any(k in reps[0]["reply"] for k in
            ("数字は嘘をつかない", "文句を言える人はいない", "先発の柱", "ローテの軸")),
            reps[0]["reply"])  # 投手プール 4 案のどれか (断定形)
        self.assertNotIn("http", reps[0]["reply"])
        self.assertNotIn("#", reps[0]["reply"])
        self.assertNotIn("報知", reps[0]["reply"])

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
            handles=["hochi_giants"],
        )
        self.assertEqual(len(reps), 1)
        self.assertIn("中継ぎ温存", reps[0]["reply"])      # ボイス文が採用される
        self.assertNotIn("10K", reps[0]["reply"])          # 数字 1 行 fallback ではない
        self.assertIn("竹丸和幸", seen["player"])          # 親ツイート本文 + player が渡る
        self.assertIn("プロ初完投", seen["parent"])

    def test_reply_avoid_player_skips_before_voice_comment_fn(self):
        feed = ("<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
                "<link>https://x.com/hochi_giants/status/12345</link></item></channel></rss>")
        calls = []

        def _voice(parent_text, player):
            calls.append((parent_text, player))
            return "竹丸和幸、初完投か。次も見たい。"

        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: feed, max_replies=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
            comment_fn=_voice,
            handles=["hochi_giants"],
            avoid_player_names={"竹丸和幸"},
        )
        self.assertEqual(reps, [])
        self.assertEqual(calls, [])

    def test_reply_falls_back_when_comment_fn_empty(self):
        # comment_fn が空文字 (LLM 失敗 / safety NG) なら数字 1 行へ fallback。
        feed = ("<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
                "<link>https://x.com/hochi_giants/status/12345</link></item></channel></rss>")
        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: feed, max_replies=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
            comment_fn=lambda parent, player: "",
            handles=["hochi_giants"],
        )
        self.assertEqual(len(reps), 1)
        self.assertIn("10K", reps[0]["reply"])             # fallback の数字行
        self.assertTrue(any(k in reps[0]["reply"] for k in
            ("数字は嘘をつかない", "文句を言える人はいない", "先発の柱", "ローテの軸")),
            reps[0]["reply"])  # 投手プール 4 案のどれか (断定形)

    def test_reply_usage_template_invites_giants_fan_reaction(self):
        feed = (
            "<rss><channel><item><title>阿部監督が坂本勇人のスタメン起用と打順に言及</title>"
            "<link>https://x.com/hochi_giants/status/22345</link></item></channel></rss>"
        )
        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: feed, max_replies=3,
            detect_player_fn=lambda t: "坂本勇人" if "坂本" in t else "",
            handles=["hochi_giants"],
        )
        self.assertEqual(len(reps), 1)
        reply = reps[0]["reply"]
        self.assertTrue(reply.startswith("坂本勇人"), reply)
        self.assertIn("起用", reply)  # 起用プールの文 (2026-06-11 プール化で固定文言 assert 廃止)
        self.assertNotIn("阿部監督", reply)
        self.assertNotIn("今季打率", reply)  # 起用論点に無関係なDB数字は混ぜない

    def test_reply_can_target_hochi_only(self):
        hochi_feed = (
            "<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
            "<link>https://x.com/hochi_giants/status/12345</link></item></channel></rss>"
        )
        sanspo_feed = (
            "<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
            "<link>https://x.com/Sanspo_Giants/status/99999</link></item></channel></rss>"
        )

        def _fetch(url):
            if "hochi_giants" in url:
                return hochi_feed
            if "Sanspo_Giants" in url:
                return sanspo_feed
            return "<rss><channel></channel></rss>"

        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=_fetch, max_replies=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
            handles=["hochi_giants"],
        )
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["tweet_id"], "12345")
        self.assertEqual(reps[0]["handle"], "hochi_giants")

    def test_reply_can_target_tokyo_giants_official_posts(self):
        official_feed = (
            "<rss><channel><item><title>竹丸和幸 プロ初完投 8回10K</title>"
            "<link>https://x.com/TokyoGiants/status/67890</link></item></channel></rss>"
        )

        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: official_feed, max_replies=3,
            detect_player_fn=lambda t: "竹丸和幸" if "竹丸" in t else "",
            handles=["TokyoGiants"],
        )
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["tweet_id"], "67890")
        self.assertEqual(reps[0]["handle"], "TokyoGiants")
        self.assertIn("status/67890", reps[0]["url"])
        self.assertTrue(any(k in reps[0]["reply"] for k in
            ("数字は嘘をつかない", "文句を言える人はいない", "先発の柱", "ローテの軸")),
            reps[0]["reply"])  # 投手プール 4 案のどれか (断定形)

    def test_reply_intent_url(self):
        from src.x_post_mail_lane import encode_x_reply_intent_url
        u = encode_x_reply_intent_url("竹丸和幸 痺れた", "12345")
        self.assertIn("in_reply_to=12345", u)
        self.assertIn("text=", u)


class FanReplyTests(unittest.TestCase):
    """2026-06-05: ファンアカ (フーガ/缶詰) のカジュアル反応文を require_event=False で拾う。"""

    # 缶詰/フーガ風: 選手名はあるが媒体見出し語 (_EVENT_WORDS) が無い反応文。
    _FAN_FEED = (
        "<rss><channel>"
        "<item><title>坂本勇人！！！今日も繋いだ！これは強い</title>"
        "<link>https://x.com/kandume92/status/99001</link></item>"
        "</channel></rss>"
    )

    def _db(self):
        fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE batting_logs (game_id TEXT, team_name TEXT, player_canonical TEXT, AB INT, H INT, RBI INT)")
        conn.execute("CREATE TABLE pitching_logs (game_id TEXT, team_name TEXT, player_canonical TEXT, result_mark TEXT, K INT, IP REAL, ER INT)")
        conn.execute("INSERT INTO batting_logs VALUES ('g1','巨人','坂本勇人',100,25,10)")
        conn.commit(); conn.close()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_event_gate_drops_casual_fan_post_by_default(self):
        # require_event=True (default): 出来事語が無いファン反応文は弾かれる。
        kws = tc.extract_rss_keywords(
            detect_player_fn=lambda t: "坂本勇人" if "坂本" in t else "",
            fetch_fn=lambda u: self._FAN_FEED, handles=["kandume92"],
        )
        self.assertEqual(len(kws), 0)

    def test_require_event_false_picks_casual_fan_post(self):
        # require_event=False: 選手検出のみで拾う (ファンアカ用)。
        kws = tc.extract_rss_keywords(
            detect_player_fn=lambda t: "坂本勇人" if "坂本" in t else "",
            fetch_fn=lambda u: self._FAN_FEED, handles=["kandume92"],
            require_event=False,
        )
        self.assertEqual(len(kws), 1)
        self.assertEqual(kws[0]["player"], "坂本勇人")
        self.assertEqual(kws[0]["events"], [])  # 出来事語なしでも通る

    def test_fan_reply_uses_voice_and_skips_on_empty(self):
        # comment_fn (voice) があればそれを使う。 巨人選手検出 + _is_giants で関連性担保。
        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: self._FAN_FEED, max_replies=2,
            detect_player_fn=lambda t: "坂本勇人" if "坂本" in t else "",
            comment_fn=lambda parent, player: "坂本勇人ここで繋ぐのがデカい。下位打線の圧が違うわ。",
            handles=["kandume92"], require_event=False, skip_on_empty_comment=True,
        )
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["tweet_id"], "99001")
        self.assertIn("下位打線の圧", reps[0]["reply"])

    def test_fan_reply_skips_when_voice_empty(self):
        # skip_on_empty_comment=True: voice が空 (門番落ち) なら deterministic fallback を使わずスキップ。
        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: self._FAN_FEED, max_replies=2,
            detect_player_fn=lambda t: "坂本勇人" if "坂本" in t else "",
            comment_fn=lambda parent, player: "",
            handles=["kandume92"], require_event=False, skip_on_empty_comment=True,
        )
        self.assertEqual(len(reps), 0)

    def test_fan_reply_excludes_non_giants_player(self):
        # フーガの他球団ポスト想定: 巨人選手でなければ _is_giants で除外。
        feed = (
            "<rss><channel><item><title>牧すげえ 楽天同点</title>"
            "<link>https://x.com/EH87EazmV9D2eSw/status/99002</link></item></channel></rss>"
        )
        reps = tc.build_reply_candidates(
            self._db(), fetch_fn=lambda u: feed, max_replies=2,
            detect_player_fn=lambda t: "牧秀悟" if "牧" in t else "",
            comment_fn=lambda parent, player: "なんか言う",
            handles=["EH87EazmV9D2eSw"], require_event=False, skip_on_empty_comment=True,
        )
        self.assertEqual(len(reps), 0)


if __name__ == "__main__":
    unittest.main()


class ExtractFreshnessTests(unittest.TestCase):
    """2026-07-03 user「リプは相手の新しいポストに付けたい」: 鮮度ゲート + 新しい順。"""

    @staticmethod
    def _feed():
        return (
            "<rss><channel>"
            "<item><title>竹丸和幸がプロ初完投</title><link>http://x/old</link>"
            "<pubDate>Thu, 02 Jul 2026 10:00:00 +0900</pubDate></item>"
            "<item><title>岡本和真が復帰即アーチの一発</title><link>http://x/new</link>"
            "<pubDate>Fri, 03 Jul 2026 08:30:00 +0900</pubDate></item>"
            "<item><title>坂本勇人がサヨナラ勝利</title><link>http://x/nodate</link></item>"
            "</channel></rss>"
        )

    def _now(self):
        from datetime import datetime, timezone, timedelta
        return datetime(2026, 7, 3, 9, 0, tzinfo=timezone(timedelta(hours=9)))

    def test_age_gate_drops_old_and_undated(self):
        import src.sns_topic_cards as tc
        kws = tc.extract_rss_keywords(
            detect_player_fn=lambda t: t[:4] if any(
                n in t for n in ("竹丸", "岡本", "坂本")) else "",
            fetch_fn=lambda u: self._feed(), handles=["h"],
            max_age_hours=6.0, now=self._now(),
        )
        urls = [k["url"] for k in kws]
        self.assertEqual(urls, ["http://x/new"])  # 23h前と日付不明は落ちる

    def test_age_gate_disabled_keeps_legacy_behavior(self):
        import src.sns_topic_cards as tc
        kws = tc.extract_rss_keywords(
            detect_player_fn=lambda t: t[:4] if any(
                n in t for n in ("竹丸", "岡本", "坂本")) else "",
            fetch_fn=lambda u: self._feed(), handles=["h"],
        )
        self.assertEqual(len(kws), 3)  # 従来: 全部拾う

    def test_newest_first_within_handle(self):
        import src.sns_topic_cards as tc
        kws = tc.extract_rss_keywords(
            detect_player_fn=lambda t: t[:4] if any(
                n in t for n in ("竹丸", "岡本")) else "",
            fetch_fn=lambda u: self._feed(), handles=["h"],
            max_age_hours=48.0, now=self._now(),
        )
        self.assertEqual([k["url"] for k in kws], ["http://x/new", "http://x/old"])
