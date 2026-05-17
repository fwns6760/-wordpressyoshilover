import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import json

from src import rss_fetcher, x_post_generator


class CostModeTests(unittest.TestCase):
    def test_low_cost_article_categories_default_to_selected_subset(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertTrue(rss_fetcher.should_use_ai_for_category("試合速報"))
            self.assertTrue(rss_fetcher.should_use_ai_for_category("選手情報"))
            self.assertTrue(rss_fetcher.should_use_ai_for_category("首脳陣"))
            self.assertFalse(rss_fetcher.should_use_ai_for_category("コラム"))

    def test_notice_like_column_routes_to_player_ai_category(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣"}, clear=False):
            use_ai, effective_category, reason = rss_fetcher._resolve_article_ai_strategy(
                "コラム",
                "【巨人】皆川岳飛が初１軍合流「やってやろうという気持ち」",
                "皆川岳飛が初１軍合流となり、試合前に抱負を語った。",
                has_game=False,
                article_subtype="general",
            )
            self.assertTrue(use_ai)
            self.assertEqual(effective_category, "選手情報")
            self.assertEqual(reason, "player_notice_route")

    def test_recovery_like_column_routes_to_player_ai_category(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣"}, clear=False):
            use_ai, effective_category, reason = rss_fetcher._resolve_article_ai_strategy(
                "コラム",
                "【巨人】西舘勇陽がコンディション不良からの復帰へ向けてブルペン投球再開",
                "西舘勇陽投手がコンディション不良からの復帰へ向けてブルペンで投球練習を再開した。",
                has_game=False,
                article_subtype="general",
            )
            self.assertTrue(use_ai)
            self.assertEqual(effective_category, "選手情報")
            self.assertEqual(reason, "player_recovery_route")

    def test_farm_articles_can_use_ai_even_when_category_is_not_enabled(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣"}, clear=False):
            use_ai, effective_category, reason = rss_fetcher._resolve_article_ai_strategy(
                "ドラフト・育成",
                "【二軍】巨人 3-1 ハヤテ（5回降雨コールド）",
                "巨人が3-1で勝利し、若手が本塁打を放った。",
                has_game=False,
                article_subtype="farm",
            )
            self.assertTrue(use_ai)
            self.assertEqual(effective_category, "ドラフト・育成")
            self.assertEqual(reason, "farm_article_route")

    def test_player_status_accepts_shorter_strict_output(self):
        self.assertEqual(
            rss_fetcher._get_gemini_strict_min_chars(
                "選手情報",
                "【巨人】中山礼都が登録抹消",
                "中山礼都が出場選手登録を抹消された。",
            ),
            160,
        )
        self.assertEqual(
            rss_fetcher._get_gemini_strict_min_chars(
                "選手情報",
                "【巨人】田中将大「打線を線にしない」",
                "田中将大が阪神戦前にコメントした。",
            ),
            220,
        )

    def test_article_categories_can_be_overridden(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,補強・移籍"}, clear=False):
            self.assertTrue(rss_fetcher.should_use_ai_for_category("補強・移籍"))
            self.assertFalse(rss_fetcher.should_use_ai_for_category("選手情報"))

    def test_low_cost_x_post_ai_defaults_to_off(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertEqual(x_post_generator.get_x_post_ai_mode(), "none")
            self.assertTrue(x_post_generator.should_use_ai_for_x_post("試合速報"))
            self.assertFalse(x_post_generator.should_use_ai_for_x_post("コラム"))

    def test_x_post_ai_mode_can_be_enabled_for_selected_categories(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "gemini", "X_POST_AI_CATEGORIES": "試合速報,首脳陣"}, clear=False):
            self.assertEqual(x_post_generator.get_x_post_ai_mode(), "gemini")
            self.assertTrue(x_post_generator.should_use_ai_for_x_post("首脳陣"))
            self.assertFalse(x_post_generator.should_use_ai_for_x_post("選手情報"))

    def test_auto_tweet_categories_default_to_selected_subset(self):
        with patch.dict("os.environ", {}, clear=False):
            self.assertTrue("試合速報" in rss_fetcher.get_auto_tweet_categories())
            self.assertTrue("首脳陣" in rss_fetcher.get_auto_tweet_categories())
            self.assertTrue("ドラフト・育成" in rss_fetcher.get_auto_tweet_categories())
            self.assertFalse("コラム" in rss_fetcher.get_auto_tweet_categories())

    def test_auto_tweet_skip_reasons_explain_disabled_state(self):
        with patch.dict("os.environ", {"AUTO_TWEET_ENABLED": "0"}, clear=False):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="news",
                category="試合速報",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
            self.assertEqual(reasons, ["auto_tweet_disabled"])

    def test_auto_tweet_accepts_social_news_when_enabled(self):
        with patch.dict(
            "os.environ",
            {
                "AUTO_TWEET_ENABLED": "1",
                "AUTO_TWEET_CATEGORIES": "ドラフト・育成",
                "ENABLE_X_POST_FOR_SOCIAL": "1",
            },
            clear=False,
        ):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="social_news",
                category="ドラフト・育成",
                article_subtype="social",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
            self.assertEqual(reasons, [])

    def test_live_update_x_post_is_disabled_by_default(self):
        with patch.dict("os.environ", {"AUTO_TWEET_ENABLED": "1", "AUTO_TWEET_CATEGORIES": "試合速報"}, clear=False):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="news",
                category="試合速報",
                article_subtype="live_update",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
            self.assertEqual(reasons, ["live_update_x_post_disabled"])

    def test_live_update_x_post_can_be_enabled(self):
        with patch.dict(
            "os.environ",
            {
                "AUTO_TWEET_ENABLED": "1",
                "AUTO_TWEET_CATEGORIES": "試合速報",
                "ENABLE_X_POST_FOR_LIVE_UPDATE": "1",
            },
            clear=False,
        ):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="news",
                category="試合速報",
                article_subtype="live_update",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
            self.assertEqual(reasons, [])

    def test_non_live_update_subtypes_are_not_affected_by_live_update_flag(self):
        cases = [
            ("news", "試合速報", "lineup"),
            ("news", "試合速報", "postgame"),
            ("news", "試合速報", "pregame"),
            ("news", "首脳陣", "manager"),
            ("news", "選手情報", "notice"),
            ("news", "選手情報", "recovery"),
            ("news", "ドラフト・育成", "farm"),
            ("social_news", "試合速報", "social"),
            ("news", "選手情報", "player"),
        ]
        with patch.dict(
            "os.environ",
            {
                "AUTO_TWEET_ENABLED": "1",
                "AUTO_TWEET_CATEGORIES": "試合速報,選手情報,首脳陣,ドラフト・育成",
                "ENABLE_X_POST_FOR_LINEUP": "1",
                "ENABLE_X_POST_FOR_POSTGAME": "1",
                "ENABLE_X_POST_FOR_PREGAME": "1",
                "ENABLE_X_POST_FOR_MANAGER": "1",
                "ENABLE_X_POST_FOR_NOTICE": "1",
                "ENABLE_X_POST_FOR_RECOVERY": "1",
                "ENABLE_X_POST_FOR_FARM": "1",
                "ENABLE_X_POST_FOR_SOCIAL": "1",
                "ENABLE_X_POST_FOR_PLAYER": "1",
            },
            clear=False,
        ):
            for source_type, category, article_subtype in cases:
                with self.subTest(source_type=source_type, category=category, article_subtype=article_subtype):
                    reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                        source_type=source_type,
                        category=category,
                        article_subtype=article_subtype,
                        draft_only=False,
                        x_post_count=0,
                        x_post_daily_limit=5,
                        featured_media=123,
                        published=True,
                        article_url="https://yoshilover.com/1",
                    )
                    self.assertEqual(reasons, [])

    def test_gemini_cli_for_x_post_defaults_to_off(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertFalse(x_post_generator.allow_gemini_cli_for_x_post())

    def test_gemini_cli_for_x_post_can_be_opted_in(self):
        with patch.dict("os.environ", {"X_POST_GEMINI_ALLOW_CLI": "1"}, clear=False):
            self.assertTrue(x_post_generator.allow_gemini_cli_for_x_post())

    def test_article_ai_mode_can_be_overridden_for_this_run(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "none"}, clear=False):
            self.assertEqual(rss_fetcher.get_article_ai_mode(True, override="grok"), "grok")
            self.assertEqual(rss_fetcher.get_article_ai_mode(False, override="grok"), "grok")

    def test_offday_article_ai_mode_defaults_to_gemini_in_low_cost_mode(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=True):
            self.assertEqual(rss_fetcher.get_article_ai_mode(False), "gemini")

    def test_stale_player_status_entry_is_skipped_after_24_hours(self):
        old_dt = datetime.now(timezone.utc) - timedelta(hours=25)
        self.assertTrue(
            rss_fetcher._should_skip_stale_player_status_entry(
                "選手情報",
                "【巨人】佐々木俊輔が登録抹消",
                "佐々木俊輔外野手が出場選手登録を抹消された。",
                old_dt,
            )
        )
        fresh_dt = datetime.now(timezone.utc) - timedelta(hours=2)
        self.assertFalse(
            rss_fetcher._should_skip_stale_player_status_entry(
                "選手情報",
                "【巨人】佐々木俊輔が登録抹消",
                "佐々木俊輔外野手が出場選手登録を抹消された。",
                fresh_dt,
            )
        )

    def test_yesterdays_postgame_entry_is_skipped(self):
        yesterday_local = datetime.now(rss_fetcher.JST) - timedelta(hours=12)
        if yesterday_local.date() == datetime.now(rss_fetcher.JST).date():
            yesterday_local = yesterday_local - timedelta(days=1)
        self.assertTrue(
            rss_fetcher._should_skip_stale_postgame_entry(
                "試合速報",
                "巨人4-0勝利",
                "松本剛が決勝打で巨人が4-0で勝利した。",
                yesterday_local.astimezone(timezone.utc),
            )
        )

    def test_todays_postgame_entry_is_not_skipped(self):
        now_local = datetime.now(rss_fetcher.JST)
        fresh_local = now_local - timedelta(hours=2)
        if fresh_local.date() != now_local.date():
            fresh_local = now_local - timedelta(minutes=min(5, now_local.minute))
        fresh_dt = fresh_local.astimezone(timezone.utc)
        self.assertFalse(
            rss_fetcher._should_skip_stale_postgame_entry(
                "試合速報",
                "巨人4-0勝利",
                "松本剛が決勝打で巨人が4-0で勝利した。",
                fresh_dt,
            )
        )

    def test_win_milestone_story_is_classified_as_postgame(self):
        self.assertEqual(
            rss_fetcher._detect_article_subtype(
                "巨人・田中将大、“熟練の投球術”で2勝目",
                "田中将大が熟練の投球術で今季2勝目を挙げた。",
                "試合速報",
                True,
            ),
            "postgame",
        )

    def test_started_game_skips_same_day_pregame_entry(self):
        self.assertTrue(
            rss_fetcher._should_skip_started_pregame_entry(
                "試合速報",
                "巨人阪神戦 田中将大先発でどこを見たいか",
                "田中将大が阪神戦に先発する予定だった。",
                True,
                {"state": "6回表", "ended": False},
            )
        )

    def test_future_day_pregame_preview_is_not_skipped_after_current_game_start(self):
        self.assertFalse(
            rss_fetcher._should_skip_started_pregame_entry(
                "試合速報",
                "あす巨人ヤクルト戦 田中将大先発でどこを見たいか",
                "あすのヤクルト戦で田中将大が先発する見込みだ。",
                True,
                {"state": "6回表", "ended": False},
            )
        )

    def test_pregame_started_skip_bypassed_for_mid_game_progress_marker(self):
        # 則本昂大 hochi article style: classifier mis-labels as pregame
        # (no score yet) but title carries explicit mid-game progress marker.
        # Skip must NOT fire in this case so the news article can proceed.
        self.assertFalse(
            rss_fetcher._should_skip_started_pregame_entry(
                "試合速報",
                "【巨人】則本昂大が２回まで無失点でスタート　５度目の挑戦で初勝利へ　相手は前回５失点の広島",
                "",
                True,
                {"state": "4回表", "ended": False},
            )
        )

    def test_pregame_started_skip_still_fires_for_genuine_pregame(self):
        # Regression guard: titles without mid-game markers still skip when
        # the game has already started.
        self.assertTrue(
            rss_fetcher._should_skip_started_pregame_entry(
                "試合速報",
                "巨人阪神戦 戸郷翔征先発でどこを見たいか",
                "戸郷翔征が阪神戦に先発する予定だ。",
                True,
                {"state": "4回表", "ended": False},
            )
        )

    def test_no_entity_non_game_skip_fires_for_promotional_title(self):
        # 66951 type: official @TokyoGiants RT, no player, promo markers
        reason = rss_fetcher._should_skip_no_entity_non_game(
            "RT 【公式】ジャイアンツタウンスタジアム: ／ 締め切り間近！販売は5/1",
            "",
        )
        self.assertEqual(reason, "promotional_no_entity")

    def test_no_entity_non_game_skip_fires_for_umpire_title(self):
        # 66941 type: umpire roster, no Giants player
        reason = rss_fetcher._should_skip_no_entity_non_game(
            "福井 セーレン・ドリームスタジアム 本日の審判団 球審 嶋田 一塁 土山 二",
            "",
        )
        self.assertEqual(reason, "umpire_info_no_entity")

    def test_no_entity_non_game_skip_passes_when_player_present(self):
        # 66943 type: 大勢 (alias 翁田大勢) survives even with promo-like phrasing
        reason = rss_fetcher._should_skip_no_entity_non_game(
            "福井 セーレン・ドリームスタジアム 巨人ベンチ入り控え選手 大勢 田和 赤星",
            "",
        )
        self.assertEqual(reason, "")

    def test_no_entity_non_game_skip_passes_for_player_with_goods_news(self):
        # Player news that happens to mention グッズ販売 should still pass:
        # entity present means the article carries player context.
        reason = rss_fetcher._should_skip_no_entity_non_game(
            "【巨人】戸郷翔征グッズ販売開始",
            "",
        )
        self.assertEqual(reason, "")

    def test_unfinished_postgame_skip_fires_when_game_in_progress(self):
        # post 66993 type: 試合中なのに postgame source が取り込まれ
        # 「白星」narrative の事実誤認 article が公開された事象を防ぐ。
        self.assertTrue(
            rss_fetcher._should_skip_unfinished_postgame_entry(
                "試合速報",
                "【巨人】則本昂大が７回無失点の熱投、今季最多99球　８回に大勢ソロ被弾で移籍後初勝利は消滅",
                "",
                True,
                {"state": "8回裏", "ended": False},
            )
        )

    def test_unfinished_postgame_skip_passes_when_game_ended(self):
        # 試合終了確認後の postgame は従来通り通す。
        self.assertFalse(
            rss_fetcher._should_skip_unfinished_postgame_entry(
                "試合速報",
                "【巨人】則本昂大が７回無失点の熱投、今季最多99球　８回に大勢ソロ被弾で移籍後初勝利は消滅",
                "",
                True,
                {"state": "試合終了", "ended": True},
            )
        )

    def test_unfinished_postgame_skip_only_applies_to_postgame_subtype(self):
        # pregame subtype は対象外 (pregame_started_skip が担当)。
        self.assertFalse(
            rss_fetcher._should_skip_unfinished_postgame_entry(
                "試合速報",
                "あす巨人ヤクルト戦 戸郷翔征が先発で意気込み",
                "",
                True,
                {"state": "試合前", "ended": False},
            )
        )

    def test_unfinished_postgame_skip_handles_empty_game_status(self):
        # game_status が空 (試合がない日 / 取得失敗) は safety 側で skip。
        self.assertTrue(
            rss_fetcher._should_skip_unfinished_postgame_entry(
                "試合速報",
                "巨人広島戦 競り勝って白星",
                "",
                True,
                {},
            )
        )

    def test_unfinished_postgame_skip_does_not_apply_today_status_to_previous_day_source(self):
        # 5/17 朝に 5/16 試合後記事を処理する場合、5/17 の試合前
        # Yahoo state (見どころ / ended=False) を前日 postgame に当てない。
        self.assertFalse(
            rss_fetcher._should_skip_unfinished_postgame_entry(
                "試合速報",
                "【巨人】破竹の今季最長５連勝　２度追いつき、仕掛けて勝ち越し",
                "",
                True,
                {"state": "見どころ", "ended": False},
                source_published_at=datetime(2026, 5, 16, 22, 12, tzinfo=rss_fetcher.JST),
                now_jst=datetime(2026, 5, 17, 4, 31, tzinfo=rss_fetcher.JST),
            )
        )

    def test_too_short_title_skip_fires(self):
        # 66931 type: title sanitize の過剰削除で 1 単語 (「探せ」) だけ残った
        self.assertTrue(rss_fetcher._should_skip_too_short_title("探せ"))
        self.assertTrue(rss_fetcher._should_skip_too_short_title("打撃"))
        self.assertTrue(rss_fetcher._should_skip_too_short_title(""))

    def test_too_short_title_skip_passes_for_normal_titles(self):
        self.assertFalse(
            rss_fetcher._should_skip_too_short_title(
                "【巨人】則本昂大が２回まで無失点でスタート"
            )
        )
        self.assertFalse(
            rss_fetcher._should_skip_too_short_title("内海コーチ「状態非常に良い」")
        )

    def test_quote_only_no_subject_skip_fires(self):
        # 66960 type: 役職名「引用」だけで主語抜け
        self.assertTrue(
            rss_fetcher._should_skip_quote_only_no_subject_title(
                "内海コーチ「状態非常に良い」"
            )
        )
        self.assertTrue(
            rss_fetcher._should_skip_quote_only_no_subject_title(
                "阿部監督「今の流れを象徴」"
            )
        )

    def test_quote_only_no_subject_skip_passes_when_subject_present(self):
        # 主語付き quote は通常 publish OK
        self.assertFalse(
            rss_fetcher._should_skip_quote_only_no_subject_title(
                "【巨人】気迫全開　則本昂大５回まで０封　内海コーチ「状態非常に良い」"
            )
        )
        # スタメン発表型 (player + position 引用) は対象外
        self.assertFalse(
            rss_fetcher._should_skip_quote_only_no_subject_title(
                "巨人スタメン キャベッジが先制６号ソロ"
            )
        )

    def test_dedupe_entity_in_title_removes_second_occurrence(self):
        # 66939 type: 同 player name 2 回 → 1 回に dedup
        result = rss_fetcher._dedupe_entity_in_title(
            "平山功太「平山功太選手はコンディションを考慮してベンチ外となりました」"
        )
        # 「平山功太」が 1 回だけ残る
        self.assertEqual(result.count("平山功太"), 1)
        # 引用部分の内容は保持
        self.assertIn("コンディション", result)

    def test_dedupe_entity_in_title_no_op_when_unique(self):
        original = "【巨人】戸郷翔征が無失点投球"
        self.assertEqual(
            rss_fetcher._dedupe_entity_in_title(original),
            original,
        )

    def test_yoshilover_prefix_postgame_with_stats(self):
        # 則本記事 type: 投球内容 (回数/球数/失点) が title に含まれる
        prefix = rss_fetcher._build_yoshilover_structured_prefix(
            "【巨人】則本昂大が初勝利の権利ゲット　7回無失点 99球　被安打5 奪三振7",
            "",
            "postgame",
        )
        self.assertIn("📊 試合まとめ", prefix)
        self.assertIn("7回", prefix)
        self.assertIn("99球", prefix)
        self.assertIn("無失点", prefix)
        self.assertIn("被安打", prefix)
        self.assertIn("奪三振", prefix)
        self.assertIn("📝 ヨシラバー的に", prefix)
        self.assertIn("則本昂大", prefix)  # narrative に player 名

    def test_yoshilover_prefix_non_postgame_returns_empty(self):
        # pregame / lineup / manager 等は prefix 不要
        self.assertEqual(
            rss_fetcher._build_yoshilover_structured_prefix(
                "巨人スタメン 戸郷翔征が先発", "", "pregame"
            ),
            "",
        )
        self.assertEqual(
            rss_fetcher._build_yoshilover_structured_prefix(
                "阿部監督「今の流れを象徴」", "", "manager"
            ),
            "",
        )

    def test_yoshilover_prefix_no_facts_returns_empty(self):
        # 事実 fact 抽出不能の title は prefix なし (元 body のまま)
        self.assertEqual(
            rss_fetcher._build_yoshilover_structured_prefix(
                "巨人広島戦の試合", "", "postgame"
            ),
            "",
        )

    def test_yoshilover_prefix_narrative_uses_player_for_no_runs(self):
        prefix = rss_fetcher._build_yoshilover_structured_prefix(
            "【巨人】戸郷翔征が7回無失点の熱投", "", "postgame"
        )
        self.assertIn("戸郷翔征", prefix)
        self.assertIn("好投", prefix)

    def test_prior_event_keyword_skip_fires_for_凱旋(self):
        # 67027 type: 「凱旋」marker で過去 event の retrospective
        self.assertTrue(
            rss_fetcher._should_skip_prior_event_postgame(
                "選手情報",
                "巨人・吉川が岐阜凱旋　小中学生と交流、質問攻めに",
                "",
                True,
            )
        )

    def test_prior_event_keyword_skip_fires_for_昨夜(self):
        self.assertTrue(
            rss_fetcher._should_skip_prior_event_postgame(
                "試合速報",
                "昨夜のサヨナラ勝ちを振り返る",
                "",
                True,
            )
        )

    def test_prior_event_keyword_skip_passes_for_normal_title(self):
        self.assertFalse(
            rss_fetcher._should_skip_prior_event_postgame(
                "試合速報",
                "巨人広島戦 戸郷翔征が先発",
                "",
                True,
            )
        )

    def test_mismatched_today_game_result_marker(self):
        # 67024 type: title「サヨナラ弾」 + yahoo「試合終了 0-1」 (サヨナラ無し)
        # → 別試合の記事と判定
        skip, reason = rss_fetcher._should_skip_mismatched_today_game(
            category="試合速報",
            title="巨人・佐々木　自身初サヨナラ弾",
            summary="",
            article_subtype="postgame",
            yahoo_game_status={
                "ended": True,
                "state": "試合終了",
                "opponent": "広島",
            },
        )
        self.assertTrue(skip)
        self.assertTrue(reason.startswith("result_marker_mismatch"))

    def test_mismatched_today_game_opponent_mismatch(self):
        # title に「阪神」 (今日は広島戦) → 別カード記事
        skip, reason = rss_fetcher._should_skip_mismatched_today_game(
            category="試合速報",
            title="巨人阪神戦 戸郷7回無失点で勝利",
            summary="",
            article_subtype="postgame",
            yahoo_game_status={
                "ended": True,
                "state": "試合終了",
                "opponent": "広島",
            },
        )
        self.assertTrue(skip)
        self.assertTrue(reason.startswith("opponent_mismatch"))

    def test_mismatched_today_game_passes_when_game_unfinished(self):
        # 試合中は postgame_unfinished_skip が担当、ここでは判定しない
        skip, reason = rss_fetcher._should_skip_mismatched_today_game(
            category="試合速報",
            title="巨人・佐々木　自身初サヨナラ弾",
            summary="",
            article_subtype="postgame",
            yahoo_game_status={
                "ended": False,
                "state": "8回裏",
                "opponent": "広島",
            },
        )
        self.assertFalse(skip)

    def test_mismatched_today_game_passes_when_no_yahoo_status(self):
        # yahoo state 取得失敗時は判定不能で許可側
        skip, reason = rss_fetcher._should_skip_mismatched_today_game(
            category="試合速報",
            title="サヨナラ勝ち",
            summary="",
            article_subtype="postgame",
            yahoo_game_status=None,
        )
        self.assertFalse(skip)

    def test_pregame_started_skip_log_contains_title_and_timestamps(self):
        now = datetime(2026, 4, 19, 11, 30, tzinfo=rss_fetcher.JST)
        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_pregame_started_skip(
                "巨人ヤクルト戦 18:00試合開始 先発は戸郷翔征",
                "神宮で18:00開始予定。戸郷翔征投手が先発予定。",
                "https://example.com/pregame",
                {"state": "6回表", "ended": False},
                now=now,
            )
        payload = json.loads(cm.output[0].split("INFO:rss_fetcher:", 1)[1])
        self.assertEqual(payload["event"], "pregame_started_skip")
        self.assertEqual(payload["title"], "巨人ヤクルト戦 18:00試合開始 先発は戸郷翔征")
        self.assertEqual(payload["post_url"], "https://example.com/pregame")
        self.assertEqual(payload["first_pitch_time"], "18:00")
        self.assertEqual(payload["now"], "2026-04-19T11:30:00+09:00")
        self.assertEqual(payload["game_state"], "6回表")

    def test_gemini_attempt_limits_default_to_three_in_low_cost_mode(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=True), 3)
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=False), 1)

    def test_gemini_attempt_limits_can_be_overridden(self):
        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "GEMINI_STRICT_MAX_ATTEMPTS": "2", "GEMINI_GROUNDED_MAX_ATTEMPTS": "2"},
            clear=False,
        ):
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=True), 2)
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=False), 2)


if __name__ == "__main__":
    unittest.main()
