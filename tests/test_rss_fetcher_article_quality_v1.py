import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


class RssFetcherArticleQualityV1Tests(unittest.TestCase):
    def test_player_status_template_keeps_generic_source_on_existing_path(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_TITLE_GENERIC_COMPOUND_GUARD": "0",
                "ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "0",
            },
            clear=False,
        ):
            title, template_key = rss_fetcher._rewrite_display_title_with_template(
                "実施選手が昇格へ",
                "実施選手が一軍に昇格する見込み",
                "選手情報",
                False,
            )

        self.assertEqual(title, "実施選手、一軍合流 関連情報")
        self.assertEqual(template_key, "player_status_join")

    def test_player_status_template_passthroughs_generic_compound_when_flag_is_on(self):
        with patch.dict(os.environ, {"ENABLE_TITLE_GENERIC_COMPOUND_GUARD": "1"}, clear=False):
            title, template_key = rss_fetcher._rewrite_display_title_with_template(
                "実施選手が昇格へ",
                "実施選手が一軍に昇格する見込み",
                "選手情報",
                False,
            )

        self.assertEqual(title, "実施選手が昇格へ")
        self.assertEqual(template_key, "player_status_generic_subject_passthrough")

    def test_player_status_template_passthroughs_non_giants_team_prefix_when_flag_is_on(self):
        with patch.dict(os.environ, {"ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "1"}, clear=False):
            title, template_key = rss_fetcher._rewrite_display_title_with_template(
                "ブルージェイズ・岡本和真が実戦復帰へ",
                "ブルージェイズ・岡本和真が実戦復帰へ前進",
                "選手情報",
                False,
            )

        self.assertEqual(title, "ブルージェイズ・岡本和真が実戦復帰へ")
        self.assertEqual(template_key, "player_status_entity_conflict_passthrough")

    def test_article_body_quality_sanitizer_is_flag_gated(self):
        sample = "【文脈と背景】\nこの表現は目を引きます。"

        with patch.dict(os.environ, {"ENABLE_FORBIDDEN_PHRASE_FILTER": "0"}, clear=False):
            off_text = rss_fetcher._apply_article_body_quality_sanitizer(sample)
        with patch.dict(os.environ, {"ENABLE_FORBIDDEN_PHRASE_FILTER": "1"}, clear=False):
            on_text = rss_fetcher._apply_article_body_quality_sanitizer(sample)

        self.assertEqual(off_text, sample)
        self.assertIn("【この話が出た流れ】", on_text)
        self.assertNotIn("目を引きます", on_text)

    def test_generic_title_repair_uses_specific_source_title_when_flag_is_on(self):
        with patch.dict(os.environ, {"ENABLE_GENERIC_TITLE_REPAIR": "1"}, clear=False):
            repaired, review = rss_fetcher._maybe_apply_generic_title_repair(
                rewritten_title="関連情報",
                source_title="【巨人】泉口友汰が打球顔面直撃から復帰初球安打",
                summary="泉口友汰が復帰戦で初球安打を放った。",
                category="選手情報",
                article_subtype="player",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                metadata={"player_name": "泉口友汰"},
            )

        self.assertEqual(repaired, "泉口友汰が打球顔面直撃から復帰初球安打")
        self.assertIsNone(review)

    def test_generic_title_repair_builds_subject_and_action_when_flag_is_on(self):
        with patch.dict(os.environ, {"ENABLE_GENERIC_TITLE_REPAIR": "1"}, clear=False):
            repaired, review = rss_fetcher._maybe_apply_generic_title_repair(
                rewritten_title="関連情報",
                source_title="【巨人】阿部監督が起用方針を説明",
                summary="阿部監督が試合後に起用方針について話した。",
                category="首脳陣",
                article_subtype="manager",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                metadata={"manager_name": "阿部監督"},
            )

        self.assertEqual(repaired, "阿部監督、発言 関連情報")
        self.assertIsNone(review)

    def test_generic_title_repair_routes_to_review_when_subject_and_action_are_missing(self):
        with patch.dict(os.environ, {"ENABLE_GENERIC_TITLE_REPAIR": "1"}, clear=False):
            repaired, review = rss_fetcher._maybe_apply_generic_title_repair(
                rewritten_title="関連情報",
                source_title="巨人ニュース",
                summary="続報を確認中",
                category="コラム",
                article_subtype="general",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                metadata={},
            )

        self.assertEqual(repaired, "関連情報")
        self.assertIsInstance(review, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(review.reason, "generic_title_repair_review")

    def test_third_team_result_routes_to_farm_article_shape_when_flag_is_on(self):
        with patch.dict(os.environ, {"ENABLE_FARM_SUBTYPE_SPLIT": "1"}, clear=False):
            source_text = "【三軍】巨人 5-4 千曲川　育成右腕が好投"
            category = rss_fetcher.classify_category(source_text, {})
            subtype = rss_fetcher._detect_article_subtype(source_text, "巨人三軍が千曲川に5-4で勝利した。", category, True)

        self.assertEqual(category, "ドラフト・育成")
        self.assertEqual(subtype, "farm")

    def test_trusted_social_third_team_result_is_worthy_narrowly_when_flag_is_on(self):
        with patch.dict(os.environ, {"ENABLE_SOCIAL_TOO_WEAK_NARROW_RESCUE": "1"}, clear=False):
            worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
                "【三軍】巨人 5-4 千曲川",
                "巨人三軍が千曲川に5-4で勝利した。",
                "ドラフト・育成",
                "farm",
                source_name="スポーツ報知巨人班X",
                source_handle="@hochi_giants",
                source_url="https://twitter.com/hochi_giants/status/123",
            )

        self.assertTrue(worthy)
        self.assertEqual(rescue_meta["rescue_reason"], "social_too_weak_narrow_rescue")
        self.assertEqual(rescue_meta["matched_word"], "三軍")


if __name__ == "__main__":
    unittest.main()
