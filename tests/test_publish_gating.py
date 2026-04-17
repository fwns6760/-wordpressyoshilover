import unittest
from unittest.mock import patch

from src import rss_fetcher


class PublishGatingTests(unittest.TestCase):
    def test_resolve_publish_gate_subtype_routes_social_news_to_social(self):
        subtype = rss_fetcher.resolve_publish_gate_subtype(
            "報知が阿部監督コメントを投稿",
            "報知のX投稿から記事化した。",
            "首脳陣",
            "manager",
            "social_news",
        )
        self.assertEqual(subtype, "social")

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

    def test_get_publish_skip_reasons_keeps_featured_media_guardrail(self):
        with patch.dict("os.environ", {"ENABLE_PUBLISH_FOR_MANAGER": "1", "PUBLISH_REQUIRE_IMAGE": "1"}, clear=False):
            reasons = rss_fetcher.get_publish_skip_reasons(
                source_type="news",
                draft_only=False,
                featured_media=0,
                article_subtype="manager",
            )
        self.assertEqual(reasons, ["featured_media_missing"])

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


if __name__ == "__main__":
    unittest.main()
