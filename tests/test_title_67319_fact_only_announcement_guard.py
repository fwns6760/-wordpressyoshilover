"""Tests for 67319 fix: fact-only quote / announcement source guards (Pattern A skip)."""

from __future__ import annotations

import unittest

from src.title_template_assembler import (
    _is_fact_only_quote,
    _is_announcement_source,
    assemble_nomotoke_title,
)


class IsFactOnlyQuoteTests(unittest.TestCase):
    def test_tsuusan_300_homerun_is_fact(self):
        self.assertTrue(_is_fact_only_quote("通算300号本塁打"))

    def test_300_号_alone_is_fact(self):
        self.assertTrue(_is_fact_only_quote("300号"))

    def test_sayonara_homerun_is_fact(self):
        self.assertTrue(_is_fact_only_quote("サヨナラホームラン"))

    def test_zenkan_shouri_is_fact(self):
        self.assertTrue(_is_fact_only_quote("完封勝利"))

    def test_kanto_shouri_is_fact(self):
        self.assertTrue(_is_fact_only_quote("完投勝利"))

    def test_normal_selfie_quote_not_fact(self):
        self.assertFalse(_is_fact_only_quote("最後まで集中して振り切れたんじゃないかと思います"))

    def test_partial_fact_with_other_text_not_fact(self):
        # selfie quote の中に fact が含まれていても全体としては selfie
        self.assertFalse(_is_fact_only_quote("300号を打てて嬉しい"))

    def test_renpou_is_fact(self):
        self.assertTrue(_is_fact_only_quote("3連勝"))

    def test_dakkou_sanshin_is_fact(self):
        self.assertTrue(_is_fact_only_quote("10奪三振"))

    def test_emoji_decorated_fact_still_fact(self):
        self.assertTrue(_is_fact_only_quote("通算300号💥本塁打"))

    def test_empty_safe(self):
        self.assertFalse(_is_fact_only_quote(""))


class IsAnnouncementSourceTests(unittest.TestCase):
    def test_kinen_grouts_detected(self):
        self.assertTrue(
            _is_announcement_source(
                "RT 巨人公式: 坂本300号 記念グッズ販売開始",
                "",
                "",
            )
        )

    def test_giants_store_detected(self):
        self.assertTrue(
            _is_announcement_source(
                "",
                "GIANTS STORE で販売中",
                "",
            )
        )

    def test_normal_news_not_announcement(self):
        self.assertFalse(
            _is_announcement_source(
                "巨人・坂本が逆転サヨナラ３ラン",
                "",
                "「最後まで集中して振り切れた」と語った",
            )
        )

    def test_empty_safe(self):
        self.assertFalse(_is_announcement_source("", "", ""))


class AssembleNomotokeTitleGuardIntegrationTests(unittest.TestCase):
    def test_67319_actual_case_pattern_a_skipped(self):
        # post 67319 reproduce: 「通算300号本塁打」が quote だと Pattern A skip
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="坂本勇人「通算300号本塁打」",
            source_title='RT 読売巨人軍（ジャイアンツ）グッズ情報: ㊗🎉 坂本勇人 選手「通算300号💥 本塁打」 記念グッズ第1弾を販売開始',
            source_body="",
            summary="",
            player_name="坂本勇人",
            role="player",
        )
        # Pattern A skip → None or 異 pattern (Pattern A の "坂本勇人「通算300号本塁打」" は出ない)
        self.assertIsNone(result)

    def test_announcement_source_pattern_a_skipped(self):
        # source に「販売開始」keyword → Pattern A skip
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="既存 title",
            source_title="",
            source_body="坂本勇人「ファンの皆様へ」記念グッズ販売開始",
            summary="",
            player_name="坂本勇人",
            role="player",
        )
        self.assertIsNone(result)

    def test_normal_player_quote_still_works(self):
        # 通常の selfie quote は Pattern A が動作 (guard 影響なし)
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="dummy",
            source_title="",
            source_body="戸郷翔征「自分らしく投げるだけです」",
            summary="",
            player_name="戸郷翔征",
            role="player",
        )
        # Pattern A 発火 → "戸郷翔征「自分らしく投げるだけです」"
        self.assertEqual(result, "戸郷翔征「自分らしく投げるだけです」")


if __name__ == "__main__":
    unittest.main()
