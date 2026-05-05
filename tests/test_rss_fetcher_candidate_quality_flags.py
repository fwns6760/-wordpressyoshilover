import json
import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


SOCIAL_BODY = "\n".join(
    [
        "【話題の要旨】",
        "スポーツ報知巨人班Xが阿部監督のコメントを伝えた。",
        "【発信内容の要約】",
        "原文のニュアンスを残しながら内容を整理する。",
        "【文脈と背景】",
        "試合後コメントとして出た投稿だった。",
        "【ファンの関心ポイント】",
        "次の起用にどうつながるかが焦点になる。",
    ]
)


class GenericTitleRepairFlagTests(unittest.TestCase):
    def test_flag_off_keeps_generic_title_unchanged(self):
        repaired, review = rss_fetcher._maybe_apply_generic_title_repair(
            rewritten_title="関連情報",
            source_title="【巨人】泉口友汰が一軍合流",
            summary="泉口友汰が一軍に合流した。",
            category="選手情報",
            article_subtype="player",
            logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            metadata={"player_name": "泉口友汰"},
        )

        self.assertEqual(repaired, "関連情報")
        self.assertIsNone(review)

    def test_flag_on_leaves_non_generic_title_unchanged(self):
        with patch.dict(os.environ, {"ENABLE_GENERIC_TITLE_REPAIR": "1"}, clear=False):
            repaired, review = rss_fetcher._maybe_apply_generic_title_repair(
                rewritten_title="泉口友汰、一軍合流 関連情報",
                source_title="【巨人】泉口友汰が一軍合流",
                summary="泉口友汰が一軍に合流した。",
                category="選手情報",
                article_subtype="player",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                metadata={"player_name": "泉口友汰"},
            )

        self.assertEqual(repaired, "泉口友汰、一軍合流 関連情報")
        self.assertIsNone(review)


class ShortSourceNarrowTemplateFlagTests(unittest.TestCase):
    def _build_short_social_body(self, env: dict[str, str], summary: str = "スポーツ報知巨人班Xが新フォトブースを紹介した。"):
        with patch.dict(os.environ, env, clear=False):
            return rss_fetcher._maybe_build_short_source_narrow_body(
                title="球団投稿が話題",
                summary=summary,
                category="コラム",
                body_subtype="social_news",
                source_url="https://twitter.com/hochi_giants/status/1",
                source_name="スポーツ報知巨人班X",
                source_day_label="",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )

    def test_flag_off_returns_none_and_keeps_existing_path_available(self):
        ai_body = self._build_short_social_body({})

        self.assertIsNone(ai_body)

    def test_flag_on_uses_short_social_template(self):
        ai_body = self._build_short_social_body({"ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1"})

        self.assertIn("【話題の要旨】", ai_body)
        self.assertIn("【ファンの関心ポイント】", ai_body)
        self.assertIn("出典: https://twitter.com/hochi_giants/status/1", ai_body)
        self.assertIn("コメントで教えてください", ai_body)

    def test_flag_on_respects_body_template_v2_headings(self):
        ai_body = self._build_short_social_body(
            {
                "ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1",
                "ENABLE_BODY_TEMPLATE_V2": "1",
            }
        )

        self.assertIn("【投稿で出ていた内容】", ai_body)
        self.assertIn("【この話が出た流れ】", ai_body)
        self.assertNotIn("【発信内容の要約】", ai_body)

    def test_flag_on_falls_back_for_long_source(self):
        long_summary = " ".join(["スポーツ報知巨人班Xが阿部監督のコメントを伝えた。"] * 18)
        ai_body = self._build_short_social_body(
            {"ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1"},
            summary=long_summary,
        )

        self.assertIsNone(ai_body)

    def test_flag_on_contract_blocked_falls_back_to_existing_path(self):
        with patch.dict(os.environ, {"ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1"}, clear=False):
            with patch.object(rss_fetcher, "_short_source_narrow_template_contract_ok", return_value=(False, ["social_required_headings"])):
                with self.assertLogs("rss_fetcher", level="WARNING") as cm:
                    ai_body = rss_fetcher._maybe_build_short_source_narrow_body(
                        title="球団投稿が話題",
                        summary="スポーツ報知巨人班Xが新フォトブースを紹介した。",
                        category="コラム",
                        body_subtype="social_news",
                        source_url="https://twitter.com/hochi_giants/status/1",
                        source_name="スポーツ報知巨人班X",
                        source_day_label="",
                        logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                    )

        self.assertIsNone(ai_body)
        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "short_template_blocked_by_contract")
        self.assertEqual(payload["severity"], "WARNING")

    def test_flag_on_uses_short_notice_template(self):
        with patch.dict(os.environ, {"ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1"}, clear=False):
            ai_body = rss_fetcher._maybe_build_short_source_narrow_body(
                title="【巨人】皆川岳飛が出場選手登録",
                summary="皆川岳飛外野手が出場選手登録された。",
                category="選手情報",
                body_subtype="player_notice",
                source_url="https://example.com/notice",
                source_name="スポーツ報知",
                source_day_label="",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )

        self.assertIn("【公示の要旨】", ai_body)
        self.assertIn("【今後の注目点】", ai_body)
        self.assertIn("出典: https://example.com/notice", ai_body)


class FarmSubtypeSplitFlagTests(unittest.TestCase):
    def test_flag_off_keeps_third_team_result_outside_farm_route(self):
        source_text = "【三軍】巨人 5-4 千曲川"
        category = rss_fetcher.classify_category(source_text, {})
        subtype = rss_fetcher._detect_article_subtype(source_text, "巨人三軍が千曲川に5-4で勝利した。", category, True)

        self.assertNotEqual(category, "ドラフト・育成")
        self.assertNotEqual(subtype, "farm")

    def test_flag_on_routes_third_team_result_to_farm(self):
        with patch.dict(os.environ, {"ENABLE_FARM_SUBTYPE_SPLIT": "1"}, clear=False):
            source_text = "【三軍】巨人 5-4 千曲川"
            category = rss_fetcher.classify_category(source_text, {})
            subtype = rss_fetcher._detect_article_subtype(source_text, "巨人三軍が千曲川に5-4で勝利した。", category, True)

        self.assertEqual(category, "ドラフト・育成")
        self.assertEqual(subtype, "farm")

    def test_flag_on_prefers_first_team_when_markers_coexist(self):
        with patch.dict(os.environ, {"ENABLE_FARM_SUBTYPE_SPLIT": "1"}, clear=False):
            subtype = rss_fetcher._detect_article_subtype(
                "【一軍】巨人 5-4 阪神 三軍から昇格した選手もベンチ入り",
                "東京ドームで巨人が阪神に5-4で勝利した。",
                "試合速報",
                True,
            )

        self.assertEqual(subtype, "postgame")

    def test_flag_on_preserves_existing_farm_lineup(self):
        with patch.dict(os.environ, {"ENABLE_FARM_SUBTYPE_SPLIT": "1"}, clear=False):
            subtype = rss_fetcher._detect_article_subtype(
                "【三軍】巨人スタメン",
                "三軍戦のスタメンが発表された。",
                "ドラフト・育成",
                True,
            )

        self.assertEqual(subtype, "farm_lineup")

    def test_flag_on_emits_structured_log_when_applied(self):
        with patch.dict(os.environ, {"ENABLE_FARM_SUBTYPE_SPLIT": "1"}, clear=False):
            with self.assertLogs("rss_fetcher", level="INFO") as cm:
                rss_fetcher._detect_article_subtype(
                    "【三軍】巨人 5-4 千曲川",
                    "巨人三軍が千曲川に5-4で勝利した。",
                    "コラム",
                    True,
                )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "farm_subtype_split_applied")
        self.assertEqual(payload["post_subtype"], "farm")
        self.assertIn("三軍", payload["keyword_hits"])


class BodyDupReductionFlagTests(unittest.TestCase):
    def test_flag_off_keeps_duplicate_intro(self):
        body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が起用意図を説明した記事です。",
                "この一言が次のスタメンにどうつながるかが焦点です。",
                "【次の注目】",
                "次戦の起用に注目です。",
            ]
        )
        reduced = rss_fetcher._maybe_reduce_body_intro_dup(
            body_text=body,
            article_title="阿部監督が起用意図を説明した記事です",
            article_subtype="social_news",
            logger=rss_fetcher.logging.getLogger("rss_fetcher"),
        )

        self.assertEqual(reduced, body)

    def test_flag_on_removes_duplicate_intro_sentence(self):
        body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が起用意図を説明した記事です。",
                "この一言が次のスタメンにどうつながるかが焦点です。",
                "【次の注目】",
                "次戦の起用に注目です。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_BODY_DUP_REDUCTION": "1"}, clear=False):
            with self.assertLogs("rss_fetcher", level="INFO") as cm:
                reduced = rss_fetcher._maybe_reduce_body_intro_dup(
                    body_text=body,
                    article_title="阿部監督が起用意図を説明した記事です",
                    article_subtype="social_news",
                    logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                )

        self.assertNotIn("阿部監督が起用意図を説明した記事です。", reduced)
        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "body_dup_reduction_applied")
        self.assertGreater(payload["removed_chars"], 0)

    def test_flag_on_leaves_single_sentence_section_unchanged(self):
        body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が起用意図を説明した記事です。",
                "【次の注目】",
                "次戦の起用に注目です。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_BODY_DUP_REDUCTION": "1"}, clear=False):
            reduced = rss_fetcher._maybe_reduce_body_intro_dup(
                body_text=body,
                article_title="阿部監督が起用意図を説明した記事です",
                article_subtype="social_news",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )

        self.assertEqual(reduced, body)

    def test_flag_on_build_news_block_reduces_title_intro_overlap(self):
        duplicate_social_body = "\n".join(
            [
                "【話題の要旨】",
                "阿部監督が起用意図を説明した記事です。",
                "若手起用への言及があった。",
                "【発信内容の要約】",
                "原文のニュアンスを残しながら内容を整理する。",
                "【文脈と背景】",
                "試合後コメントとして出た投稿だった。",
                "【ファンの関心ポイント】",
                "次の起用にどうつながるかが焦点になる。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_BODY_DUP_REDUCTION": "1"}, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=duplicate_social_body):
                    _blocks, ai_body = rss_fetcher.build_news_block(
                        title="阿部監督が起用意図を説明",
                        summary="スポーツ報知巨人班Xが阿部監督のコメントを伝えた。",
                        url="https://twitter.com/hochi_giants/status/1",
                        source_name="スポーツ報知巨人班X",
                        category="首脳陣",
                        has_game=False,
                        source_type="social_news",
                        rewritten_title="阿部監督が起用意図を説明した記事です",
                    )

        self.assertNotIn("阿部監督が起用意図を説明した記事です。", ai_body)
        self.assertIsNone(rss_fetcher.find_duplicate_sentence(ai_body))


class SocialTooWeakNarrowRescueFlagTests(unittest.TestCase):
    def test_flag_off_does_not_rescue_trusted_social_with_player_name_only(self):
        worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
            "【巨人】泉口友汰を撮影",
            "泉口友汰の写真が投稿された。",
            "選手情報",
            "player",
            source_name="スポーツ報知巨人班X",
            source_handle="@hochi_giants",
            source_url="https://twitter.com/hochi_giants/status/999",
        )

        self.assertFalse(worthy)
        self.assertIsNone(rescue_meta)

    def test_flag_on_rescues_trusted_social_with_player_name_keyword(self):
        with patch.dict(os.environ, {"ENABLE_SOCIAL_TOO_WEAK_NARROW_RESCUE": "1"}, clear=False):
            worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
                "【巨人】泉口友汰を撮影",
                "泉口友汰の写真が投稿された。",
                "選手情報",
                "player",
                source_name="スポーツ報知巨人班X",
                source_handle="@hochi_giants",
                source_url="https://twitter.com/hochi_giants/status/999",
            )

        self.assertTrue(worthy)
        self.assertEqual(rescue_meta["rescue_reason"], "social_too_weak_narrow_rescue")
        self.assertIn("泉口友汰", rescue_meta["keyword_hits"])
        self.assertEqual(rescue_meta["source_domain"], "hochi_giants")

    def test_flag_on_does_not_rescue_untrusted_domain(self):
        with patch.dict(os.environ, {"ENABLE_SOCIAL_TOO_WEAK_NARROW_RESCUE": "1"}, clear=False):
            worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
                "【巨人】泉口友汰を撮影",
                "泉口友汰の写真が投稿された。",
                "選手情報",
                "player",
                source_name="個人アカウント",
                source_handle="@fan_account",
                source_url="https://twitter.com/fan_account/status/999",
            )

        self.assertFalse(worthy)
        self.assertIsNone(rescue_meta)

    def test_flag_on_does_not_rescue_trusted_domain_without_keyword_hits(self):
        with patch.dict(os.environ, {"ENABLE_SOCIAL_TOO_WEAK_NARROW_RESCUE": "1"}, clear=False):
            worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
                "きょうの投稿",
                "リンクはこちら",
                "コラム",
                "general",
                source_name="スポーツ報知巨人班X",
                source_handle="@hochi_giants",
                source_url="https://twitter.com/hochi_giants/status/999",
            )

        self.assertFalse(worthy)
        self.assertIsNone(rescue_meta)

    def test_flag_on_emits_structured_log(self):
        with patch.dict(os.environ, {"ENABLE_SOCIAL_TOO_WEAK_NARROW_RESCUE": "1"}, clear=False):
            with self.assertLogs("rss_fetcher", level="INFO") as cm:
                rss_fetcher._evaluate_authoritative_social_entry(
                    "【巨人】泉口友汰を撮影",
                    "泉口友汰の写真が投稿された。",
                    "選手情報",
                    "player",
                    source_name="スポーツ報知巨人班X",
                    source_handle="@hochi_giants",
                    source_url="https://twitter.com/hochi_giants/status/999",
                )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "social_too_weak_narrow_rescued")
        self.assertEqual(payload["source_domain"], "hochi_giants")
        self.assertIn("泉口友汰", payload["keyword_hits"])


if __name__ == "__main__":
    unittest.main()
