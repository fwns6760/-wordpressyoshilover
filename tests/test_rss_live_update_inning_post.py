"""RSS-253: live_update inning post body_contract tune tests.

「【五回表】」「【四回裏】」等の漢数字 inning post が:
1. has_live_update_fragment で検出されること
2. _select_template_v2 で live_update_short に振られること (postgame_strict より先)
3. _resolve_rss_story_type_context_v2 で title_subtype="live_update", validator_subtype="social_news"
4. ENABLE_LIVE_UPDATE_ARTICLES=0 既定で _evaluate_authoritative_social_entry が
   live_update を skip (worthy=False) → body_contract_validate に到達しない

これらを fixture で pin する。body_validator.py / BODY_CONTRACTS / publish gate 不変。
"""

import os
import unittest
from unittest.mock import patch

from src import body_validator, rss_fetcher


def _resolve(*, title: str, summary: str, source_type: str = "social_news", source_url: str = "https://x.com/hochi_giants/status/1", source_name: str = "スポーツ報知巨人班X", category: str = "試合速報"):
    return rss_fetcher._resolve_rss_story_type_context_v2(
        title=title,
        summary=summary,
        category=category,
        daily_has_game=True,
        source_type=source_type,
        source_url=source_url,
        source_name=source_name,
    )


class LiveUpdateInningRegexExpansionTests(unittest.TestCase):
    """LIVE_UPDATE_INNING_RE が漢数字 / 半角 / 全角の 1-12 回 にマッチすること."""

    def test_kanji_inning_one_through_nine(self):
        for kanji in ("一", "二", "三", "四", "五", "六", "七", "八", "九"):
            with self.subTest(kanji=kanji):
                self.assertTrue(rss_fetcher._has_live_update_fragment(f"【{kanji}回表】巨人 0-2 ヤクルト 内野安打"))

    def test_kanji_inning_ten_eleven_twelve(self):
        for kanji in ("十", "十一", "十二"):
            with self.subTest(kanji=kanji):
                self.assertTrue(rss_fetcher._has_live_update_fragment(f"【{kanji}回表】巨人 0-2 ヤクルト 試合継続中"))

    def test_kanji_inning_ura_uragyaku(self):
        for kanji in ("一", "三", "五", "七", "九"):
            with self.subTest(kanji=kanji):
                self.assertTrue(rss_fetcher._has_live_update_fragment(f"【{kanji}回裏】内野安打"))

    def test_arabic_inning_still_works(self):
        # 既存挙動の baseline 維持
        for arabic in ("1", "5", "9", "10", "11"):
            with self.subTest(arabic=arabic):
                self.assertTrue(rss_fetcher._has_live_update_fragment(f"【{arabic}回表】内野安打"))

    def test_zenkaku_inning_still_works(self):
        for zenkaku in ("１", "５", "９"):
            with self.subTest(zenkaku=zenkaku):
                self.assertTrue(rss_fetcher._has_live_update_fragment(f"【{zenkaku}回表】内野安打"))

    def test_no_inning_no_match(self):
        # inning 表記 / フラグメント無しは false
        self.assertFalse(rss_fetcher._has_live_update_fragment("巨人勝利"))
        self.assertFalse(rss_fetcher._has_live_update_fragment("選手のコメント"))


class LiveUpdateRoutingPriorityTests(unittest.TestCase):
    """inning post が live_update_short routing に振られ、postgame_strict より優先."""

    def test_kanji_inning_post_routes_to_live_update_short(self):
        ctx = _resolve(
            title="【五回表】巨人 0-2 ヤクルト 2つのゴロを捌いた、サード 選手",
            summary="五回表 巨人 0-2 ヤクルト 試合継続中",
            source_url="https://x.com/hochi_giants/status/2053000000000000001",
            source_name="スポーツ報知巨人班X",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "live_update_short")
        self.assertEqual(ctx["title_subtype"], "live_update")
        self.assertEqual(ctx["body_subtype"], "live_update")
        # validator_subtype は緩い social_news (BODY_CONTRACTS["live_update"] heavy 回避)
        self.assertEqual(ctx["validator_subtype"], "social_news")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_kanji_inning_ura_routes_to_live_update_short(self):
        ctx = _resolve(
            title="【四回裏】巨人 0-2 ヤクルト 選手の内野安打で満塁！",
            summary="四回裏 巨人 0-2 ヤクルト 内野安打",
            source_url="https://x.com/TokyoGiants/status/2053000000000000002",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "live_update_short")
        self.assertEqual(ctx["title_subtype"], "live_update")

    def test_inning_post_does_not_fall_to_postgame_strict(self):
        # inning post は postgame_strict (decisive event 強) より先に live_update_short へ
        # 内野安打 (decisive event の一部) があっても live_update_short が先
        ctx = _resolve(
            title="【六回表】巨人 0-2 ヤクルト 内野安打で先制",
            summary="先発戸郷が好投。内野安打で先制点。",
            source_url="https://x.com/hochi_giants/status/2053000000000000003",
            source_name="スポーツ報知巨人班X",
        )
        self.assertNotEqual(ctx["template_selector_v2_key"], "postgame_strict")
        self.assertEqual(ctx["title_subtype"], "live_update")

    def test_postgame_without_inning_still_routes_to_postgame_strict(self):
        # inning 表記なし、決勝打あり → 既存 postgame_strict 維持 (regression baseline)
        ctx = _resolve(
            title="【巨人】3-2 ヤクルト 岡本和真が決勝3ランホームラン",
            summary="岡本和真選手が試合終盤に決勝の3ランホームラン。試合を決めた。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000020.html",
            source_name="日刊スポーツ",
        )
        # decisive_event 強 + inning 表記なし → postgame_strict
        self.assertEqual(ctx["template_selector_v2_key"], "postgame_strict")
        self.assertEqual(ctx["title_subtype"], "postgame")


class LiveUpdateAnalysisHasFragmentFlagTests(unittest.TestCase):
    """analysis dict に has_live_update_fragment が含まれること."""

    def test_analysis_has_live_update_fragment_true(self):
        analysis = rss_fetcher._analyze_source(
            {
                "title": "【五回表】巨人 0-2 ヤクルト 内野安打",
                "summary": "試合継続中",
                "source_type": "social_news",
                "source_url": "https://x.com/hochi_giants/status/2053000000000000010",
                "source_name": "スポーツ報知巨人班X",
            }
        )
        self.assertTrue(analysis.get("has_live_update_fragment"))

    def test_analysis_has_live_update_fragment_false(self):
        analysis = rss_fetcher._analyze_source(
            {
                "title": "巨人 vs ヤクルト 試合終了",
                "summary": "巨人勝利",
                "source_type": "social_news",
                "source_url": "https://x.com/hochi_giants/status/2053000000000000011",
                "source_name": "スポーツ報知巨人班X",
            }
        )
        self.assertFalse(analysis.get("has_live_update_fragment"))


class LiveUpdateDisabledSkipPathTests(unittest.TestCase):
    """ENABLE_LIVE_UPDATE_ARTICLES=0 既定で live_update が skip されること.

    これにより body_contract_validate に到達しない (= live_update 起因の
    body_contract_validate fail が消える)。
    """

    def test_evaluate_authoritative_social_entry_returns_false_for_live_update(self):
        # ENABLE_LIVE_UPDATE_ARTICLES default=0 → live_update は worthy=False
        with patch.object(rss_fetcher, "ENABLE_LIVE_UPDATE_ARTICLES", False):
            worthy, meta = rss_fetcher._evaluate_authoritative_social_entry(
                title="【五回表】巨人 0-2 ヤクルト 内野安打",
                summary="試合継続中",
                category="試合速報",
                article_subtype="live_update",
                source_name="スポーツ報知巨人班X",
                source_handle="hochi_giants",
                source_url="https://x.com/hochi_giants/status/2053000000000000020",
            )
        self.assertFalse(worthy)
        self.assertIsNone(meta)

    def test_evaluate_authoritative_social_entry_returns_true_when_live_update_enabled(self):
        # 将来 ENABLE_LIVE_UPDATE_ARTICLES=1 になった場合は worthy=True に転じる
        with patch.object(rss_fetcher, "ENABLE_LIVE_UPDATE_ARTICLES", True):
            worthy, meta = rss_fetcher._evaluate_authoritative_social_entry(
                title="【五回表】巨人 0-2 ヤクルト 内野安打",
                summary="試合継続中",
                category="試合速報",
                article_subtype="live_update",
                source_name="スポーツ報知巨人班X",
                source_handle="hochi_giants",
                source_url="https://x.com/hochi_giants/status/2053000000000000021",
            )
        self.assertTrue(worthy)


class BodyValidatorContractsLiveUpdateUnchangedTests(unittest.TestCase):
    """BODY_CONTRACTS["live_update"] は変更されていない (regression baseline)."""

    def test_body_contracts_live_update_keeps_3_headings(self):
        contract = body_validator.BODY_CONTRACTS.get("live_update")
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract), 3)
        for heading in (
            "【いま起きていること】",
            "【流れが動いた場面】",
            "【次にどこを見るか】",
        ):
            self.assertIn(heading, contract)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
