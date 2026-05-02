import logging
import unittest
from unittest.mock import MagicMock, patch

from src import rss_fetcher
from src import title_validator
from src import weak_title_rescue


class WeakTitleRescueHelperTests(unittest.TestCase):
    def test_related_info_escape_rescues_izumiguchi_title(self):
        result = weak_title_rescue.rescue_related_info_escape(
            gen_title="泉口友汰、昇格・復帰 関連情報",
            source_title="【巨人】泉口友汰が屋外フリー打撃再開 バックスクリーン右横へ特大弾も披露 脳しんとうから1軍復帰へ前進",
            body="泉口友汰が屋外フリー打撃を再開し、1軍復帰へ前進した。",
            summary="泉口友汰が屋外フリー打撃を再開し、1軍復帰へ前進した。",
            metadata={"player_name": "泉口友汰", "role": "選手"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "泉口友汰選手、屋外フリー打撃再開 1軍復帰へ前進")
        self.assertEqual(result.strategy, "related_info_escape_single_name")

    def test_related_info_escape_rescues_two_name_recovery_title(self):
        result = weak_title_rescue.rescue_related_info_escape(
            gen_title="西舘勇陽、昇格・復帰 関連情報",
            source_title="巨人・山崎伊織と西舘勇陽が復帰へ前進",
            body="山崎伊織と西舘勇陽が復帰へ前進した。",
            summary="山崎伊織と西舘勇陽が復帰へ前進した。",
            metadata={"role": "投手"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "山崎伊織・西舘勇陽が復帰へ前進")
        self.assertEqual(result.strategy, "related_info_escape_multi_name")

    def test_related_info_escape_rescues_player_notice_from_summary_event(self):
        result = weak_title_rescue.rescue_related_info_escape(
            gen_title="戸郷翔征、昇格・復帰 関連情報",
            source_title="【巨人】戸郷翔征の最新情報",
            body="戸郷翔征はブルペンで本格的な投球練習を再開し、1軍復帰へ前進した。",
            summary="戸郷翔征はブルペンで本格的な投球練習を再開し、1軍復帰へ前進した。",
            metadata={"article_subtype": "player_notice", "player_name": "戸郷翔征", "role": "投手"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "戸郷翔征投手、ブルペンで本格的な投球練習を再開 1軍復帰へ前進")
        self.assertEqual(result.strategy, "related_info_escape_single_name")

    def test_blacklist_phrase_rescues_abe_message_title(self):
        result = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="阿部コメント整理 ベンチ関連の発言ポイント",
            source_title="【巨人評論】5回のピンチは阿部監督から竹丸へのメッセージ ハーラートップに並ぶ白星で新人王狙えると宮本和知氏",
            body="阿部監督から竹丸へのメッセージについて、宮本和知氏が語った。",
            summary="阿部監督から竹丸へのメッセージについて、宮本和知氏が語った。",
            metadata={"speaker": "阿部", "role": "監督"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "阿部監督から竹丸へのメッセージ 宮本和知氏")
        self.assertEqual(result.strategy, "blacklist_phrase_message")

    def test_blacklist_phrase_rescues_hirayama_quote_title(self):
        result = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="首脳陣「左手おとりに使って…」ベンチ関連発言",
            source_title="「左手おとりに使って右手出す練習やっていた」タッチかわし神生還",
            body="平山功太が左手をおとりに使って神生還した。",
            summary="平山功太が左手をおとりに使って神生還した。",
            metadata={"player_name": "平山功太", "role": "選手"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "平山功太「左手おとりに使って右手出す練習やっていた」神生還")
        self.assertEqual(result.strategy, "blacklist_phrase_quote_event")

    def test_blacklist_phrase_rescues_from_summary_when_source_title_is_generic(self):
        result = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="平山功太 コメント整理 ベンチ関連発言",
            source_title="【巨人】平山功太が試合を振り返る",
            body="平山功太は「左手をおとりに使った」と振り返り、神生還につなげた。",
            summary="平山功太は「左手をおとりに使った」と振り返り、神生還につなげた。",
            metadata={"article_subtype": "player", "player_name": "平山功太", "role": "選手"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "平山功太「左手をおとりに使った」神生還")
        self.assertEqual(result.strategy, "blacklist_phrase_quote_event")

    def test_blacklist_phrase_rescues_takemaru_birthday_title(self):
        result = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="内海「今日俺の誕生日」 関連発言",
            source_title="【巨人】竹丸和幸、内海投手コーチの誕生日に4勝目「今日俺の誕生日」と何度も伝えられ…",
            body="竹丸和幸が内海投手コーチの誕生日に4勝目を挙げた。",
            summary="竹丸和幸が内海投手コーチの誕生日に4勝目を挙げた。",
            metadata={"player_name": "竹丸和幸", "role": "投手"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "竹丸和幸、内海投手コーチの誕生日に4勝目")
        self.assertEqual(result.strategy, "blacklist_phrase_named_event")

    def test_related_info_escape_does_not_rescue_merchandise_or_mlb(self):
        related = weak_title_rescue.rescue_related_info_escape(
            gen_title="又木鉄平、昇格・復帰 関連情報",
            source_title="又木鉄平の初勝利記念グッズが発売",
            body="グッズ販売の告知。",
            summary="グッズ販売の告知。",
            metadata={"player_name": "又木鉄平", "merchandise": True},
        )
        mlb = weak_title_rescue.rescue_related_info_escape(
            gen_title="菅野智之、昇格・復帰 関連情報",
            source_title="ロッキーズ・菅野智之が次回登板へ調整",
            body="ロッキーズで調整した。",
            summary="ロッキーズで調整した。",
            metadata={"player_name": "菅野智之"},
        )

        self.assertIsNone(related)
        self.assertIsNone(mlb)

    def test_related_info_escape_does_not_rescue_postgame_or_mixed_team_cases(self):
        postgame = weak_title_rescue.rescue_related_info_escape(
            gen_title="戸郷翔征、昇格・復帰 関連情報",
            source_title="【巨人】戸郷翔征がブルペンで本格的な投球練習を再開 1軍復帰へ前進",
            body="戸郷翔征がブルペンで本格的な投球練習を再開し、1軍復帰へ前進した。",
            summary="戸郷翔征がブルペンで本格的な投球練習を再開し、1軍復帰へ前進した。",
            metadata={"article_subtype": "postgame", "player_name": "戸郷翔征", "role": "投手"},
        )
        mixed_team = weak_title_rescue.rescue_related_info_escape(
            gen_title="戸郷翔征、昇格・復帰 関連情報",
            source_title="【巨人】戸郷翔征がブルペンで本格的な投球練習を再開 1軍復帰へ前進",
            body="戸郷翔征がブルペンで本格的な投球練習を再開し、1軍復帰へ前進した。",
            summary="戸郷翔征がブルペンで本格的な投球練習を再開し、1軍復帰へ前進した。",
            metadata={"player_name": "戸郷翔征", "role": "投手", "team_scope": "mixed"},
        )

        self.assertIsNone(postgame)
        self.assertIsNone(mixed_team)

    def test_blacklist_phrase_does_not_rescue_duplicate_or_hard_stop_cases(self):
        duplicate = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="首脳陣コメント整理 ベンチ関連の発言ポイント",
            source_title="【巨人】阿部監督が起用意図を説明",
            body="阿部監督が起用意図を説明した。",
            summary="阿部監督が起用意図を説明した。",
            metadata={"speaker": "阿部", "guard_outcome": "skip"},
        )
        hard_stop = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="首脳陣コメント整理 ベンチ関連の発言ポイント",
            source_title="【巨人】選手が救急搬送されたことに阿部監督が言及",
            body="救急搬送に言及した。",
            summary="救急搬送に言及した。",
            metadata={"speaker": "阿部"},
        )

        self.assertIsNone(duplicate)
        self.assertIsNone(hard_stop)

    def test_blacklist_phrase_does_not_rescue_stale_case(self):
        result = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="平山功太 コメント整理 ベンチ関連発言",
            source_title="【巨人】平山功太が試合を振り返る",
            body="平山功太は「左手をおとりに使った」と振り返り、神生還につなげた。",
            summary="平山功太は「左手をおとりに使った」と振り返り、神生還につなげた。",
            metadata={"article_subtype": "player", "player_name": "平山功太", "role": "選手", "stale": True},
        )

        self.assertIsNone(result)

    def test_blacklist_phrase_does_not_invent_missing_name(self):
        result = weak_title_rescue.rescue_blacklist_phrase(
            gen_title="首脳陣コメント整理 ベンチ関連発言",
            source_title="「切り替えていく」だけを残した",
            body="談話だけが残っている。",
            summary="談話だけが残っている。",
            metadata={},
        )

        self.assertIsNone(result)


class WeakTitleStrongMarkerTests(unittest.TestCase):
    def test_name_and_event_exception_allows_hirayama_swim_title(self):
        self.assertTrue(
            weak_title_rescue.is_strong_with_name_and_event("平山功太が神走塁「スイム」を成功したワケ")
        )

        is_weak, reason = title_validator.is_weak_generated_title("平山功太が神走塁「スイム」を成功したワケ")
        self.assertFalse(is_weak)
        self.assertEqual(reason, "")

    def test_name_and_event_exception_detects_strong_source_but_not_generic_comment_title(self):
        self.assertTrue(
            weak_title_rescue.is_strong_with_name_and_event(
                "巨人・平山功太が好走塁で魅せる！ 神業スライディングに片岡氏「タイミングは完全にアウトだと思ったんですが…」と感嘆"
            )
        )
        self.assertFalse(weak_title_rescue.is_strong_with_name_and_event("巨人戦 平山功太の試合後発言整理"))

    def test_name_and_event_exception_stays_narrow(self):
        self.assertFalse(weak_title_rescue.is_strong_with_name_and_event("内海「今日俺の誕生日」 関連発言"))
        self.assertFalse(weak_title_rescue.is_strong_with_name_and_event("前向きな材料を整理して見どころを確認"))


class WeakTitleRescueFetcherTests(unittest.TestCase):
    def test_fetcher_rescue_flag_defaults_off(self):
        with patch.dict("os.environ", {}, clear=False):
            title, reason = rss_fetcher._maybe_apply_weak_title_rescue(
                rewritten_title="泉口友汰、昇格・復帰 関連情報",
                source_title="【巨人】泉口友汰が屋外フリー打撃再開 バックスクリーン右横へ特大弾も披露 脳しんとうから1軍復帰へ前進",
                source_body="泉口友汰が屋外フリー打撃を再開し、1軍復帰へ前進した。",
                summary="泉口友汰が屋外フリー打撃を再開し、1軍復帰へ前進した。",
                category="選手情報",
                article_subtype="player",
                notice_subject="泉口友汰",
                logger=logging.getLogger("rss_fetcher"),
                source_name="報知 巨人",
                source_url="https://example.com/izumiguchi",
            )

        self.assertEqual(title, "泉口友汰、昇格・復帰 関連情報")
        self.assertIsNone(reason)

    def test_fetcher_rescue_flag_on_rewrites_title_and_logs_reason(self):
        logger = logging.getLogger("test_weak_title_rescue_flag_on")
        logger.info = MagicMock()

        with patch.dict("os.environ", {rss_fetcher.WEAK_TITLE_RESCUE_ENV_FLAG: "1"}, clear=False):
            title, reason = rss_fetcher._maybe_apply_weak_title_rescue(
                rewritten_title="泉口友汰、昇格・復帰 関連情報",
                source_title="【巨人】泉口友汰が屋外フリー打撃再開 バックスクリーン右横へ特大弾も披露 脳しんとうから1軍復帰へ前進",
                source_body="泉口友汰が屋外フリー打撃を再開し、1軍復帰へ前進した。",
                summary="泉口友汰が屋外フリー打撃を再開し、1軍復帰へ前進した。",
                category="選手情報",
                article_subtype="player",
                notice_subject="泉口友汰",
                logger=logger,
                source_name="報知 巨人",
                source_url="https://example.com/izumiguchi",
            )

        self.assertEqual(title, "泉口友汰選手、屋外フリー打撃再開 1軍復帰へ前進")
        self.assertEqual(reason, "weak_subject_title:related_info_escape")
        self.assertTrue(logger.info.called)
        self.assertIn("weak_title_rescued", logger.info.call_args.args[0])

    def test_fetcher_rescue_respects_duplicate_guard_and_review_paths(self):
        with patch.dict("os.environ", {rss_fetcher.WEAK_TITLE_RESCUE_ENV_FLAG: "1"}, clear=False):
            title, reason = rss_fetcher._maybe_apply_weak_title_rescue(
                rewritten_title="阿部コメント整理 ベンチ関連の発言ポイント",
                source_title="【巨人評論】5回のピンチは阿部監督から竹丸へのメッセージ ハーラートップに並ぶ白星で新人王狙えると宮本和知氏",
                source_body="阿部監督から竹丸へのメッセージについて、宮本和知氏が語った。",
                summary="阿部監督から竹丸へのメッセージについて、宮本和知氏が語った。",
                category="首脳陣",
                article_subtype="manager",
                manager_subject="阿部監督",
                logger=logging.getLogger("rss_fetcher"),
                source_name="報知 巨人",
                source_url="https://example.com/abe",
            )

        self.assertEqual(title, "阿部監督から竹丸へのメッセージ 宮本和知氏")
        self.assertEqual(reason, "weak_generated_title:blacklist_phrase:ベンチ関連の発言ポイント")


if __name__ == "__main__":
    unittest.main()
