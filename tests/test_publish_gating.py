import json
import unittest
from unittest.mock import Mock, patch

from src import rss_fetcher


class PublishGatingTests(unittest.TestCase):
    def test_resolve_publish_gate_subtype_keeps_manager_social_news_on_social_gate(self):
        subtype = rss_fetcher.resolve_publish_gate_subtype(
            "報知が阿部監督コメントを投稿",
            "報知のX投稿から記事化した。",
            "首脳陣",
            "manager",
            "social_news",
        )
        self.assertEqual(subtype, "social")

    def test_resolve_publish_gate_subtype_prefers_game_subtype_for_social_news(self):
        subtype = rss_fetcher.resolve_publish_gate_subtype(
            "【巨人】阪神に3-2で勝利　岡田が決勝打",
            "巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
            "試合速報",
            "postgame",
            "social_news",
        )
        self.assertEqual(subtype, "postgame")

    def test_resolve_publish_gate_subtype_prefers_farm_gate_for_social_news(self):
        subtype = rss_fetcher.resolve_publish_gate_subtype(
            "【二軍】巨人 4-0 ハヤテ　ティマが先制本塁打",
            "巨人二軍が4-0で勝利した。ティマが先制本塁打を放った。",
            "ドラフト・育成",
            "farm_lineup",
            "social_news",
        )
        self.assertEqual(subtype, "farm")

    def test_resolve_publish_gate_subtype_routes_notice_and_recovery_stories(self):
        notice_subtype = rss_fetcher.resolve_publish_gate_subtype(
            "【巨人】浅野翔吾が出場選手登録",
            "浅野翔吾外野手が出場選手登録された。",
            "選手情報",
            "player",
            "news",
        )
        recovery_subtype = rss_fetcher.resolve_publish_gate_subtype(
            "【巨人】西舘勇陽が実戦復帰へ",
            "西舘勇陽投手がブルペン投球を再開し、実戦復帰が近づいている。",
            "選手情報",
            "player",
            "news",
        )
        self.assertEqual(notice_subtype, "notice")
        self.assertEqual(recovery_subtype, "recovery")

    def test_resolve_publish_gate_subtype_maps_farm_lineup_and_game_note(self):
        farm_subtype = rss_fetcher.resolve_publish_gate_subtype(
            "【二軍】巨人 vs DeNA 18:00試合開始 1番浅野、4番ティマでスタメン",
            "二軍戦のスタメンが発表された。",
            "ドラフト・育成",
            "farm_lineup",
            "news",
        )
        general_subtype = rss_fetcher.resolve_publish_gate_subtype(
            "巨人戦 試合メモ",
            "試合前の見どころを整理した。",
            "試合速報",
            "game_note",
            "news",
        )
        self.assertEqual(farm_subtype, "farm")
        self.assertEqual(general_subtype, "general")

    def test_get_publish_skip_reasons_blocks_disabled_subtype_by_default(self):
        with patch.dict("os.environ", {"PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=123,
                article_subtype="postgame",
            )
        self.assertEqual(reasons, ["publish_disabled_for_subtype"])

    def test_live_update_never_publishes_even_if_general_flag_is_enabled(self):
        with patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_FOR_GENERAL": "1", "PUBLISH_REQUIRE_IMAGE": "1"},
            clear=False,
        ):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=123,
                article_subtype="live_update",
            )
        self.assertEqual(reasons, ["live_update_publish_disabled"])

    def test_get_publish_skip_reasons_allows_enabled_subtype(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_FOR_POSTGAME": "1", "PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=123,
                article_subtype="postgame",
            )
        self.assertEqual(reasons, [])

    def test_each_publish_flag_enables_its_target_subtype(self):
        cases = {
            "postgame": "ENABLE_PUBLISH_FOR_POSTGAME",
            "lineup": "ENABLE_PUBLISH_FOR_LINEUP",
            "manager": "ENABLE_PUBLISH_FOR_MANAGER",
            "notice": "ENABLE_PUBLISH_FOR_NOTICE",
            "pregame": "ENABLE_PUBLISH_FOR_PREGAME",
            "recovery": "ENABLE_PUBLISH_FOR_RECOVERY",
            "farm": "ENABLE_PUBLISH_FOR_FARM",
            "social": "ENABLE_PUBLISH_FOR_SOCIAL",
            "player": "ENABLE_PUBLISH_FOR_PLAYER",
            "general": "ENABLE_PUBLISH_FOR_GENERAL",
        }
        for article_subtype, env_name in cases.items():
            with self.subTest(article_subtype=article_subtype, env_name=env_name):
                with patch.dict("os.environ", {env_name: "1", "PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
                    reasons = rss_fetcher.get_publish_skip_reasons(
                        source_type="news",
                        draft_only=False,
                        featured_media=123,
                        article_subtype=article_subtype,
                    )
                self.assertEqual(reasons, [])

    def test_get_publish_skip_reasons_ignores_subtype_flags_in_draft_only_mode(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_FOR_POSTGAME": "0", "PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=True,
                featured_media=123,
                article_subtype="postgame",
            )
        self.assertEqual(reasons, ["draft_only"])

    def test_get_publish_observation_reasons_detects_missing_featured_media_in_draft_only_mode(self):
        with patch.dict("os.environ", {"PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_observation_reasons(
                source_type="news",
                draft_only=True,
                featured_media=0,
            )
        self.assertEqual(reasons, ["featured_media_observation_missing"])

    def test_get_publish_observation_reasons_skips_articles_with_featured_media(self):
        with patch.dict("os.environ", {"PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_observation_reasons(
                source_type="news",
                draft_only=True,
                featured_media=123,
            )
        self.assertEqual(reasons, [])

    def test_get_publish_observation_reasons_is_observation_only_when_not_draft_only(self):
        with patch.dict("os.environ", {"PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_observation_reasons(
                source_type="news",
                draft_only=False,
                featured_media=0,
            )
        self.assertEqual(reasons, [])

    def test_get_publish_skip_reasons_keeps_featured_media_guardrail(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_FOR_MANAGER": "1", "PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=0,
                article_subtype="manager",
            )
        self.assertEqual(reasons, ["featured_media_missing"])

    def test_get_publish_skip_reasons_allows_publish_without_image_when_guardrail_is_off(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_FOR_MANAGER": "1", "PUBLISH_REQUIRE_IMAGE": "0"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=0,
                article_subtype="manager",
            )
        self.assertEqual(reasons, [])

    def test_get_publish_skip_reasons_requires_both_subtype_and_image_when_both_gates_apply(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_FOR_MANAGER": "0", "PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=0,
                article_subtype="manager",
            )
        self.assertEqual(reasons, ["publish_disabled_for_subtype", "featured_media_missing"])

    def test_get_publish_skip_reasons_ignores_image_gate_in_draft_only_mode(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_FOR_MANAGER": "1", "PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=True,
                featured_media=0,
                article_subtype="manager",
            )
        self.assertEqual(reasons, ["draft_only"])

    def test_get_publish_skip_reasons_safe_default_holds_general_story(self):
        with patch.dict("os.environ", {"PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=123,
                article_subtype="general",
            )
        self.assertEqual(reasons, ["publish_disabled_for_subtype"])

    def test_unpublished_story_still_skips_x_post(self):
        with patch.dict(
            "os.environ",
            {
                "AUTO_TWEET_ENABLED": "1",
                "AUTO_TWEET_CATEGORIES": "試合速報,選手情報,首脳陣,ドラフト・育成",
            },
            clear=False,
        ):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="news",
                category="試合速報",
                article_subtype="postgame",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=False,
                article_url="https://yoshilover.com/1",
            )
        self.assertEqual(reasons, ["not_published"])

    def test_get_auto_tweet_skip_reasons_blocks_disabled_subtype_by_default(self):
        with patch.dict(
            "os.environ",
            {
                "AUTO_TWEET_ENABLED": "1",
                "AUTO_TWEET_CATEGORIES": "試合速報,選手情報,首脳陣,ドラフト・育成",
            },
            clear=False,
        ):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="news",
                category="試合速報",
                article_subtype="postgame",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
        self.assertEqual(reasons, ["x_post_disabled_for_subtype"])

    def test_get_auto_tweet_skip_reasons_allows_enabled_subtype(self):
        with patch.dict(
            "os.environ",
            {
                "AUTO_TWEET_ENABLED": "1",
                "AUTO_TWEET_CATEGORIES": "試合速報,選手情報,首脳陣,ドラフト・育成",
                "ENABLE_X_POST_FOR_POSTGAME": "1",
            },
            clear=False,
        ):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="news",
                category="試合速報",
                article_subtype="postgame",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
        self.assertEqual(reasons, [])

    def test_each_x_post_flag_enables_its_target_subtype(self):
        cases = {
            ("news", "試合速報", "postgame"): "ENABLE_X_POST_FOR_POSTGAME",
            ("news", "試合速報", "lineup"): "ENABLE_X_POST_FOR_LINEUP",
            ("news", "首脳陣", "manager"): "ENABLE_X_POST_FOR_MANAGER",
            ("news", "選手情報", "notice"): "ENABLE_X_POST_FOR_NOTICE",
            ("news", "試合速報", "pregame"): "ENABLE_X_POST_FOR_PREGAME",
            ("news", "選手情報", "recovery"): "ENABLE_X_POST_FOR_RECOVERY",
            ("news", "ドラフト・育成", "farm"): "ENABLE_X_POST_FOR_FARM",
            ("social_news", "試合速報", "social"): "ENABLE_X_POST_FOR_SOCIAL",
            ("news", "選手情報", "player"): "ENABLE_X_POST_FOR_PLAYER",
            ("news", "試合速報", "general"): "ENABLE_X_POST_FOR_GENERAL",
        }
        for (source_type, category, article_subtype), env_name in cases.items():
            with self.subTest(source_type=source_type, category=category, article_subtype=article_subtype):
                with patch.dict(
                    "os.environ",
                    {
                        "AUTO_TWEET_ENABLED": "1",
                        "AUTO_TWEET_CATEGORIES": "試合速報,選手情報,首脳陣,ドラフト・育成",
                        env_name: "1",
                    },
                    clear=False,
                ):
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

    def test_x_post_subtype_skipped_log_payload(self):
        logger = Mock()

        rss_fetcher._log_x_post_subtype_skipped(
            logger,
            123,
            "巨人ヤクルト戦 神宮18時開始",
            "試合速報",
            "pregame",
            "x_post_disabled_for_subtype",
        )

        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(
            payload,
            {
                "event": "x_post_subtype_skipped",
                "post_id": 123,
                "title": "巨人ヤクルト戦 神宮18時開始",
                "category": "試合速報",
                "article_subtype": "pregame",
                "reason": "x_post_disabled_for_subtype",
            },
        )

    def test_publish_gate_skipped_log_payload_uses_reason_as_event(self):
        logger = Mock()

        rss_fetcher._log_publish_gate_skipped(
            logger,
            456,
            "巨人戦の速報",
            "live_update",
            "試合速報",
            "live_update_publish_disabled",
        )

        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(
            payload,
            {
                "event": "live_update_publish_disabled",
                "skip_reason": "live_update_publish_disabled",
                "post_id": 456,
                "title": "巨人戦の速報",
                "article_subtype": "live_update",
                "category": "試合速報",
            },
        )

    def test_featured_media_observation_missing_log_payload(self):
        logger = Mock()

        rss_fetcher._log_featured_media_observation_missing(
            logger,
            789,
            "巨人スタメン 若手をどう並べたか",
            "farm",
            "ドラフト・育成",
        )

        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(
            payload,
            {
                "event": "featured_media_observation_missing",
                "observation_only": True,
                "post_id": 789,
                "title": "巨人スタメン 若手をどう並べたか",
                "article_subtype": "farm",
                "category": "ドラフト・育成",
            },
        )


if __name__ == "__main__":
    unittest.main()
