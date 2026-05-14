"""Tests for _is_non_giants_mlb_primary_subject (大谷翔平 skip / 元巨人 OB keep)."""

from __future__ import annotations

import unittest

from src import rss_fetcher


class NonGiantsMlbPrimarySubjectSkipTests(unittest.TestCase):
    def test_otani_main_subject_skipped(self):
        # post 67255 reproduce
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "大谷翔平、投手専念でジャイアンツ戦 ３勝目なるか／速報中",
            "大谷翔平 ドジャース 投手として登板",
        )
        self.assertEqual(result, "大谷翔平")

    def test_otani_with_giants_player_kept(self):
        # post 67209 reproduce: 坂本300号 + 大谷比較
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "【巨人】坂本勇人３００号は逆転サヨナラ弾　台湾でも大谷翔平と引けを取らぬ「顔」の底力",
            "巨人・坂本勇人が逆転サヨナラ。",
        )
        self.assertEqual(result, "")

    def test_sugano_ex_giants_ob_kept(self):
        # 元巨人 OB MLB 主役記事 (allowlist)
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "菅野智之、ヤンキースで初先発 6回1失点",
            "菅野智之がメジャー初登板で好投",
        )
        self.assertEqual(result, "")

    def test_okamoto_ex_giants_ob_kept(self):
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "岡本和真、ドジャースでオープン戦HR",
            "岡本和真がドジャースでホームラン",
        )
        self.assertEqual(result, "")

    def test_okamoto_with_otani_kept(self):
        # 元巨人 OB と大谷の両方言及 → OB allowlist で keep
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "岡本和真と大谷翔平の対戦が実現",
            "岡本和真がドジャースの大谷翔平と初対戦",
        )
        self.assertEqual(result, "")

    def test_yamamoto_yoshinobu_skipped(self):
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "山本由伸、6回無失点で勝利投手",
            "山本由伸がドジャースでQS達成",
        )
        self.assertEqual(result, "山本由伸")

    def test_darvish_skipped(self):
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "ダルビッシュ有、パドレスで完封勝利",
            "ダルビッシュがメジャーで完封",
        )
        self.assertIn(result, ("ダルビッシュ", "ダルビッシュ有"))

    def test_no_mlb_subject_kept(self):
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "巨人・戸郷翔征が完封勝利",
            "戸郷が巨人勝利を導く",
        )
        self.assertEqual(result, "")

    def test_otani_with_sakamoto_active_giants_kept(self):
        # 現役 巨人 player roster hit で keep
        result = rss_fetcher._is_non_giants_mlb_primary_subject(
            "大谷翔平が活躍",
            "大谷翔平がHR、巨人・坂本勇人も応援",
        )
        self.assertEqual(result, "")

    def test_empty_input_safe(self):
        self.assertEqual(rss_fetcher._is_non_giants_mlb_primary_subject("", ""), "")
        self.assertEqual(rss_fetcher._is_non_giants_mlb_primary_subject(None, None), "")


if __name__ == "__main__":
    unittest.main()
