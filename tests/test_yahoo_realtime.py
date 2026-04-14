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
    def test_extract_giants_game_from_team_schedule_html_uses_today_package(self):
        html = """
        <div class="bb-calendarTable__package bb-calendarTable__package--today">
          <div class="bb-calendarTable__wrap">
            <p class="bb-calendarTable__date">14</p>
            <div class="bb-calendarTable__versusTeam">
              <p class="bb-calendarTable__teamName">
                <a href="/npb/teams/5/top" class="bb-calendarTable__versusLogo bb-calendarTable__versusLogo--npbTeam5">阪神</a>
              </p>
            </div>
            <a class="bb-calendarTable__status" href="https://baseball.yahoo.co.jp/npb/game/2021038712/index">見どころ</a>
            <p class="bb-calendarTable__venue">甲子園</p>
          </div>
        </div>
        """

        game_id, opponent, venue = rss_fetcher._extract_giants_game_from_yahoo_team_schedule_html(html)

        self.assertEqual(game_id, "2021038712")
        self.assertEqual(opponent, "阪神")
        self.assertEqual(venue, "甲子園")

    def test_extract_giants_game_from_month_schedule_html_uses_today_rows(self):
        html = """
        <tbody>
          <tr class="bb-scheduleTable__row bb-scheduleTable__row--today">
            <td class="bb-scheduleTable__data">
              <div class="bb-scheduleTable__grid">
                <div class="bb-scheduleTable__home">
                  <div class="bb-scheduleTable__homeName"><a href="/npb/teams/5/index">阪神</a></div>
                </div>
                <div class="bb-scheduleTable__info">
                  <p class="bb-scheduleTable__status"><a href="/npb/game/2021038712/index">見どころ</a></p>
                </div>
                <div class="bb-scheduleTable__away">
                  <div class="bb-scheduleTable__awayName"><a href="/npb/teams/1/index">巨人</a></div>
                </div>
              </div>
            </td>
            <td class="bb-scheduleTable__data bb-scheduleTable__data--stadium">甲子園</td>
          </tr>
        </tbody>
        """

        game_id, opponent, venue = rss_fetcher._extract_giants_game_from_yahoo_month_schedule_html(html)

        self.assertEqual(game_id, "2021038712")
        self.assertEqual(opponent, "阪神")
        self.assertEqual(venue, "甲子園")

    def test_check_giants_game_today_fails_closed_when_all_sources_fail(self):
        with patch.object(rss_fetcher, "_check_giants_game_today_yahoo", return_value=(False, "", "")):
            with patch("urllib.request.urlopen", side_effect=OSError("network down")):
                has_game, opponent, venue = rss_fetcher.check_giants_game_today()

        self.assertFalse(has_game)
        self.assertEqual(opponent, "")
        self.assertEqual(venue, "")

    def test_build_yahoo_lineup_candidate_creates_lineup_entry(self):
        rows = [
            {"order": "1", "position": "中", "name": "丸佳浩", "avg": ".281", "hr": "3", "rbi": "12", "sb": "2"},
            {"order": "2", "position": "二", "name": "吉川尚輝", "avg": ".298", "hr": "1", "rbi": "8", "sb": "4"},
            {"order": "3", "position": "左", "name": "キャベッジ", "avg": ".301", "hr": "4", "rbi": "15", "sb": "1"},
            {"order": "4", "position": "一", "name": "岡田悠希", "avg": ".275", "hr": "5", "rbi": "18", "sb": "0"},
        ]

        with patch.object(rss_fetcher, "_find_today_giants_game_info_yahoo", return_value=("2021038712", "阪神", "甲子園")):
            candidate = rss_fetcher._build_yahoo_lineup_candidate("阪神", "甲子園", rows, 99)

        self.assertEqual(candidate["category"], "試合速報")
        self.assertEqual(candidate["source_name"], "Yahoo!プロ野球 スタメン")
        self.assertTrue(candidate["is_synthetic_lineup"])
        self.assertIn("スタメン", candidate["title"])
        self.assertIn("1番丸佳浩", candidate["title"])
        self.assertIn("巨人が阪神戦のスタメンを発表した。", candidate["summary"])
        self.assertEqual(candidate["post_url"], "https://baseball.yahoo.co.jp/npb/game/2021038712/top")
        self.assertEqual(candidate["history_urls"], ["https://baseball.yahoo.co.jp/npb/game/2021038712/top#lineup"])

    def test_parse_yahoo_game_status_detects_final_score(self):
        html = """
        <div id="async-gameDetail" class="bb-gameDetail">
          <div class="bb-gameTeam">
            <span class="bb-gameTeam__name">巨人</span>
          </div>
          <div class="bb-gameTeam__score">
            <p class="bb-gameCard__detail">
              <span class="bb-gameTeam__homeScore">2</span>
              <span class="bb-gameCard__time">-</span>
              <span class="bb-gameTeam__awayScore">0</span>
            </p>
            <p class="bb-gameCard__state">
              <span>試合終了</span>
            </p>
          </div>
          <div class="bb-gameTeam">
            <span class="bb-gameTeam__name">ヤクルト</span>
          </div>
        </div>
        <table id="ing_brd" class="bb-gameScoreTable">
          <tbody>
            <tr class="bb-gameScoreTable__row">
              <td class="bb-gameScoreTable__data bb-gameScoreTable__data--team">巨人</td>
              <td class="bb-gameScoreTable__data">0</td>
              <td class="bb-gameScoreTable__data">2</td>
              <td class="bb-gameScoreTable__total">2</td>
              <td class="bb-gameScoreTable__total bb-gameScoreTable__data--hits">11</td>
              <td class="bb-gameScoreTable__total bb-gameScoreTable__data--loss">0</td>
            </tr>
            <tr class="bb-gameScoreTable__row">
              <td class="bb-gameScoreTable__data bb-gameScoreTable__data--team">ヤクルト</td>
              <td class="bb-gameScoreTable__data">0</td>
              <td class="bb-gameScoreTable__data">0</td>
              <td class="bb-gameScoreTable__total">0</td>
              <td class="bb-gameScoreTable__total bb-gameScoreTable__data--hits">2</td>
              <td class="bb-gameScoreTable__total bb-gameScoreTable__data--loss">0</td>
            </tr>
          </tbody>
        </table>
        """

        status = rss_fetcher._parse_yahoo_game_status(html)

        self.assertTrue(status["ended"])
        self.assertEqual(status["state"], "試合終了")
        self.assertEqual(status["opponent"], "ヤクルト")
        self.assertEqual(status["giants_score"], "2")
        self.assertEqual(status["opponent_score"], "0")
        self.assertEqual(status["giants_hits"], "11")
        self.assertEqual(status["opponent_hits"], "2")

    def test_build_yahoo_postgame_candidate_creates_postgame_entry(self):
        game_status = {
            "ended": True,
            "opponent": "ヤクルト",
            "giants_score": "0",
            "opponent_score": "2",
            "giants_hits": "2",
            "opponent_hits": "11",
            "giants_errors": "0",
            "opponent_errors": "0",
            "post_url": "https://baseball.yahoo.co.jp/npb/game/2021038704/top",
            "game_id": "2021038704",
        }

        candidate = rss_fetcher._build_yahoo_postgame_candidate("ヤクルト", "神宮", game_status, 120)

        self.assertEqual(candidate["category"], "試合速報")
        self.assertEqual(candidate["source_name"], "Yahoo!プロ野球 試合結果")
        self.assertTrue(candidate["is_synthetic_postgame"])
        self.assertIn("0-2", candidate["title"])
        self.assertIn("敗戦", candidate["title"])
        self.assertIn("巨人がヤクルトに0-2で敗れた。", candidate["summary"])
        self.assertEqual(candidate["history_urls"], ["https://baseball.yahoo.co.jp/npb/game/2021038704/top#postgame"])

    def test_detect_live_update_reason_prefers_tie_and_lead_change(self):
        current = {"ended": False, "giants_score": "2", "opponent_score": "2"}
        previous = {"giants_score": "1", "opponent_score": "2"}
        self.assertEqual(rss_fetcher._detect_live_update_reason(current, previous), "tie_game")

        current2 = {"ended": False, "giants_score": "3", "opponent_score": "2"}
        previous2 = {"giants_score": "2", "opponent_score": "2"}
        self.assertEqual(rss_fetcher._detect_live_update_reason(current2, previous2), "lead_change")

    def test_build_yahoo_live_update_candidate_creates_midgame_entry(self):
        game_status = {
            "ended": False,
            "state": "6回表",
            "opponent": "阪神",
            "giants_score": "2",
            "opponent_score": "2",
            "giants_hits": "7",
            "opponent_hits": "5",
            "giants_errors": "0",
            "opponent_errors": "1",
            "post_url": "https://baseball.yahoo.co.jp/npb/game/2021038712/top",
            "game_id": "2021038712",
        }

        candidate = rss_fetcher._build_yahoo_live_update_candidate("阪神", "甲子園", game_status, 130, "tie_game")

        self.assertEqual(candidate["category"], "試合速報")
        self.assertEqual(candidate["source_name"], "Yahoo!プロ野球 途中経過")
        self.assertTrue(candidate["is_synthetic_live_update"])
        self.assertIn("同点", candidate["title"])
        self.assertIn("6回表", candidate["summary"])
        self.assertEqual(candidate["history_urls"], ["https://baseball.yahoo.co.jp/npb/game/2021038712/top#live-2-2"])

    def test_has_primary_lineup_candidate_detects_existing_rss_lineup(self):
        candidates = [
            {
                "source_type": "news",
                "category": "試合速報",
                "title": "【巨人】今日のスタメン発表 1番丸 4番岡田",
                "summary": "巨人が阪神戦のスタメンを発表した。",
                "entry_has_game": True,
            }
        ]

        self.assertTrue(rss_fetcher._has_primary_lineup_candidate(candidates))

    def test_has_primary_postgame_candidate_detects_existing_rss_result(self):
        candidates = [
            {
                "source_type": "news",
                "category": "試合速報",
                "title": "【巨人】ヤクルトに0-2で敗戦",
                "summary": "巨人がヤクルトに0-2で敗れた。",
                "entry_has_game": True,
            }
        ]

        self.assertTrue(rss_fetcher._has_primary_postgame_candidate(candidates))

    def test_has_primary_live_candidate_detects_existing_live_update(self):
        candidates = [
            {
                "source_type": "social_news",
                "category": "試合速報",
                "title": "【巨人途中経過】6回表 巨人2-2阪神と同点",
                "summary": "巨人が6回表に2-2の同点に持ち込んだ。",
                "entry_has_game": True,
            }
        ]

        self.assertTrue(rss_fetcher._has_primary_live_candidate(candidates))

    def test_authoritative_social_entry_worthy_for_manager_quote(self):
        self.assertTrue(
            rss_fetcher._is_authoritative_social_entry_worthy(
                "【巨人】阿部監督「結果残せば使います」",
                "若手起用と競争を促すコメント",
                "首脳陣",
                "normal",
            )
        )

    def test_authoritative_social_entry_rejects_weak_promotional_post(self):
        self.assertFalse(
            rss_fetcher._is_authoritative_social_entry_worthy(
                "本日も応援よろしくお願いします",
                "グッズ情報はこちら",
                "球団情報",
                "normal",
            )
        )


if __name__ == "__main__":
    unittest.main()
