import logging
import unittest
from unittest.mock import patch

from src import rss_fetcher


class YahooRealtimeParsingTests(unittest.TestCase):
    def test_extract_payload_falls_back_to_recursive_timeline_search(self):
        html = """
        <html><body>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "unexpected": {
            "deep": {
              "timeline": {
                "entry": [{"displayText": "巨人きたー", "url": "https://x.com/example/status/1"}]
              },
              "bestTweet": {"displayText": "巨人最高", "url": "https://x.com/example/status/2"}
            }
          }
        }
        </script>
        </body></html>
        """
        logger = logging.getLogger("rss_fetcher")

        entries, best_tweet = rss_fetcher._extract_yahoo_realtime_payload(html, logger, "test")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["displayText"], "巨人きたー")
        self.assertEqual(best_tweet["displayText"], "巨人最高")

    def test_extract_payload_logs_when_next_data_is_missing(self):
        logger = logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="WARNING") as logs:
            entries, best_tweet = rss_fetcher._extract_yahoo_realtime_payload("<html></html>", logger, "missing")

        self.assertEqual(entries, [])
        self.assertEqual(best_tweet, {})
        self.assertIn("__NEXT_DATA__ not found", "\n".join(logs.output))


class YahooFanReactionQueryTests(unittest.TestCase):
    def test_build_fan_reaction_queries_prefers_subject_keyword(self):
        queries = rss_fetcher._build_fan_reaction_queries(
            "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み",
            "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加した。",
            "選手情報",
        )

        self.assertIn("戸郷翔征投手 巨人", queries)
        self.assertIn("戸郷翔征 フォーム", queries)
        self.assertTrue(any("久保" in q or "助言" in q or "フォーム" in q for q in queries[:2]))
        self.assertNotEqual(queries[0], "巨人 大胆フォーム変更の戸郷翔征人の助言を取り")

    def test_fetch_fan_reactions_retries_with_multiple_queries(self):
        def fake_entries(keyword: str):
            if keyword == "戸郷翔征投手 巨人":
                return []
            if keyword == "戸郷翔征投手":
                return [
                    {"summary": "戸郷のフォーム修正、かなり良さそう。次の登板が楽しみ。", "link": "https://x.com/togofan/status/1"},
                    {"summary": "久保コーチと進めるフォーム変更、焦らず仕上げてほしい。", "link": "https://x.com/giants_love/status/2"},
                ]
            return []

        with patch.object(rss_fetcher, "fetch_yahoo_realtime_entries", side_effect=fake_entries):
            reactions = rss_fetcher.fetch_fan_reactions_from_yahoo(
                "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み",
                "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加した。",
                "選手情報",
            )

        self.assertEqual(len(reactions), 2)
        handles = {reaction["handle"] for reaction in reactions}
        self.assertEqual(handles, {"@togofan", "@giants_love"})
        self.assertTrue(any(reaction["url"] == "https://x.com/togofan/status/1" for reaction in reactions))
        self.assertTrue(any("戸郷のフォーム修正" in reaction["text"] for reaction in reactions))

    def test_fetch_fan_reactions_filters_stale_and_irrelevant_posts(self):
        fresh_ts = int(__import__("time").time()) - 3600
        stale_ts = int(__import__("time").time()) - 10 * 24 * 3600

        def fake_entries(keyword: str):
            return [
                {
                    "summary": "戸郷のフォーム修正、かなり良さそう。次の登板が楽しみ。",
                    "link": "https://x.com/togofan/status/1",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "戸郷翔征投手、お誕生日おめでとう！",
                    "link": "https://x.com/oldfan/status/2",
                    "created_at": stale_ts,
                },
                {
                    "summary": "戸郷くん応援してる！",
                    "link": "https://x.com/genericfan/status/3",
                    "created_at": fresh_ts,
                },
            ]

        with patch.object(rss_fetcher, "fetch_yahoo_realtime_entries", side_effect=fake_entries):
            reactions = rss_fetcher.fetch_fan_reactions_from_yahoo(
                "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み",
                "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加した。",
                "選手情報",
            )

        self.assertEqual(len(reactions), 1)
        self.assertEqual(reactions[0]["handle"], "@togofan")

    def test_extract_handle_from_tweet_url(self):
        self.assertEqual(
            rss_fetcher._extract_handle_from_tweet_url("https://x.com/yomiuri_status/status/12345"),
            "@yomiuri_status",
        )

    def test_fetch_fan_reactions_prefers_fan_voice_over_media_like_posts(self):
        fresh_ts = int(__import__("time").time()) - 1800

        def fake_entries(keyword: str):
            return [
                {
                    "summary": "【巨人】阿部監督コメント　詳しくはこちら",
                    "link": "https://x.com/Daily_Online/status/1",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "このコメント、次のスタメンをかなり動かしそうで気になる。",
                    "link": "https://x.com/gfan_note/status/2",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "阿部監督のこの一言、序列見直しのサインに見える。",
                    "link": "https://x.com/giants_talk/status/3",
                    "created_at": fresh_ts,
                },
            ]

        with patch.object(rss_fetcher, "fetch_yahoo_realtime_entries", side_effect=fake_entries):
            reactions = rss_fetcher.fetch_fan_reactions_from_yahoo(
                "【巨人】阿部監督が起用の狙いを説明",
                "阿部監督がスタメン起用の意図について説明した。今後の起用方針にも触れた。",
                "首脳陣",
            )

        self.assertGreaterEqual(len(reactions), 2)
        self.assertEqual(reactions[0]["handle"], "@gfan_note")
        self.assertEqual(reactions[1]["handle"], "@giants_talk")
        self.assertNotEqual(reactions[0]["handle"], "@Daily_Online")

    def test_fetch_fan_reactions_excludes_own_reply_and_headline_only_posts(self):
        fresh_ts = int(__import__("time").time()) - 1200

        def fake_entries(keyword: str):
            return [
                {
                    "summary": "阿部監督きたー！レギュラーは決まってません。結果残せば使います。全文はブログで👇 https://t.co/test",
                    "link": "https://x.com/yoshilover6760/status/1",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "@friend 阿部監督これ見ないかな？",
                    "link": "https://x.com/reply_giants/status/2",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待(日刊スポーツ) #Yahooニュース https://t.co/test",
                    "link": "https://x.com/share_only/status/3",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "レギュラー固定じゃないなら、門脇と浦田をもっとフラットに競わせてほしい。阿部監督の起用はそこを見たい。",
                    "link": "https://x.com/fan_voice/status/4",
                    "created_at": fresh_ts,
                },
            ]

        with patch.object(rss_fetcher, "fetch_yahoo_realtime_entries", side_effect=fake_entries):
            reactions = rss_fetcher.fetch_fan_reactions_from_yahoo(
                "【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待",
                "阿部監督がレギュラー固定ではなく、結果重視で若手起用の競争を促す考えを示した。",
                "首脳陣",
            )

        handles = [reaction["handle"] for reaction in reactions]
        self.assertEqual(handles, ["@fan_voice"])

    def test_fetch_fan_reactions_uses_reserve_candidates_to_fill_limit(self):
        fresh_ts = int(__import__("time").time()) - 900

        def fake_entries(keyword: str):
            return [
                {
                    "summary": "戸郷のフォーム修正、かなり良さそう。次の登板が楽しみ。",
                    "link": "https://x.com/togofan/status/1",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "戸郷はまだ時間かかるかも。でも応援したい。",
                    "link": "https://x.com/togo_note/status/2",
                    "created_at": fresh_ts,
                },
                {
                    "summary": "久保コーチとやってるのは分かるし、変化は見たい。",
                    "link": "https://x.com/giants_eye/status/3",
                    "created_at": fresh_ts,
                },
            ]

        with patch.object(rss_fetcher, "fetch_yahoo_realtime_entries", side_effect=fake_entries):
            with patch.object(rss_fetcher, "get_fan_reaction_limit", return_value=3):
                reactions = rss_fetcher.fetch_fan_reactions_from_yahoo(
                    "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み",
                    "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加した。",
                    "選手情報",
                )

        self.assertEqual(len(reactions), 3)
        self.assertEqual(reactions[0]["handle"], "@togofan")


class GameDayCheckTests(unittest.TestCase):
    def test_check_giants_game_today_fails_closed_when_all_sources_fail(self):
        with patch.object(rss_fetcher, "_check_giants_game_today_yahoo", return_value=(False, "", "")):
            with patch("urllib.request.urlopen", side_effect=OSError("network down")):
                has_game, opponent, venue = rss_fetcher.check_giants_game_today()

        self.assertFalse(has_game)
        self.assertEqual(opponent, "")
        self.assertEqual(venue, "")


if __name__ == "__main__":
    unittest.main()
