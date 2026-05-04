import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


class RssFetcherArticleQualityV1Tests(unittest.TestCase):
    def test_player_status_template_keeps_existing_behavior_when_flags_are_off(self):
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


if __name__ == "__main__":
    unittest.main()
