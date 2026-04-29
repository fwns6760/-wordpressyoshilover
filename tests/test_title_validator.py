import json
import unittest
from unittest.mock import patch

from src import rss_fetcher
from src import title_validator


class TitleValidatorTests(unittest.TestCase):
    def test_title_validator_accepts_matching_lineup_title(self):
        result = title_validator.validate_title_candidate(
            "巨人スタメン ドラフト4位・皆川岳飛が「7番・右翼」でプロ初スタ",
            "lineup",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["inferred_subtype"], "lineup")
        self.assertEqual(result["fail_axes"], [])

    def test_title_validator_rejects_inverse_subtype_mismatch(self):
        result = title_validator.validate_title_candidate(
            "試合結果 巨人3-2 勝利の分岐点",
            "pregame",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["inferred_subtype"], "postgame")
        self.assertIn("title_subtype_mismatch", result["fail_axes"])

    def test_title_validator_rejects_sokuho_prefix_for_non_live_update(self):
        result = title_validator.validate_title_candidate(
            "速報 巨人3-2 勝利の分岐点",
            "postgame",
        )

        self.assertFalse(result["ok"])
        self.assertIn("sokuho_prefix_forbidden", result["fail_axes"])

    def test_title_validator_flags_body_conflict_for_strong_live_title(self):
        result = title_validator.validate_title_candidate(
            "速報 6回表 巨人3-2 途中経過",
            "pregame",
        )

        self.assertFalse(result["ok"])
        self.assertIn("strong_live_title_body_conflict", result["fail_axes"])
        self.assertEqual(result["expected_first_block"], "【変更情報の要旨】")

    def test_rewrite_display_title_guard_rerolls_with_warning(self):
        logger = rss_fetcher.logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="WARNING") as cm:
            with patch.object(
                rss_fetcher,
                "_rewrite_display_title_with_template",
                return_value=("速報 6回表 巨人3-2 途中経過", "forced_bad_title"),
            ):
                rewritten_title, template_key = rss_fetcher._rewrite_display_title_with_guard(
                    "元タイトル",
                    "元要約",
                    "試合速報",
                    True,
                    article_subtype="postgame",
                    logger=logger,
                    source_url="https://example.com/post",
                )

        self.assertEqual(rewritten_title, "試合結果 巨人3-2")
        self.assertEqual(template_key, "forced_bad_title_title_reroll")
        payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(payload["event"], "title_validator_reroll")
        self.assertEqual(payload["article_subtype"], "postgame")
        self.assertEqual(payload["candidate_title"], "速報 6回表 巨人3-2 途中経過")
        self.assertEqual(payload["rerolled_title"], "試合結果 巨人3-2")

    def test_is_weak_generated_title_short_title(self):
        is_weak, reason = title_validator.is_weak_generated_title("岡本2安打")

        self.assertTrue(is_weak)
        self.assertEqual(reason, "title_too_short")

    def test_is_weak_generated_title_blacklist_phrase(self):
        is_weak, reason = title_validator.is_weak_generated_title("前日コメント整理 ベンチ関連の発言ポイント")

        self.assertTrue(is_weak)
        self.assertEqual(reason, "blacklist_phrase:前日コメント整理")

    def test_is_weak_generated_title_no_strong_marker(self):
        is_weak, reason = title_validator.is_weak_generated_title("前向きな材料を整理して見どころを確認")

        self.assertTrue(is_weak)
        self.assertEqual(reason, "no_strong_marker")

    def test_is_weak_generated_title_normal_title_passes(self):
        is_weak, reason = title_validator.is_weak_generated_title("巨人 vs 阪神 戸郷が好投")

        self.assertFalse(is_weak)
        self.assertEqual(reason, "")

    def test_is_weak_generated_title_player_name_passes(self):
        is_weak, reason = title_validator.is_weak_generated_title("岡本和真が2安打で勝利に貢献")

        self.assertFalse(is_weak)
        self.assertEqual(reason, "")

    def test_is_weak_generated_title_empty_returns_weak(self):
        is_weak, reason = title_validator.is_weak_generated_title("")

        self.assertTrue(is_weak)
        self.assertEqual(reason, "title_empty")


if __name__ == "__main__":
    unittest.main()
