import unittest
from unittest.mock import patch

from src import body_validator
from src import rss_fetcher


SOURCE_HTML = '<div class="yoshilover-article-source">記事元を読む</div>'

VALID_CASES = {
    "live_update": "\n".join(
        [
            "【いま起きていること】",
            "7回表で巨人が3-2とリードしています。",
            "【流れが動いた場面】",
            "6回に勝ち越し打が出ました。",
            "【次にどこを見るか】",
            "次の継投がポイントです。",
        ]
    ),
    "postgame": "\n".join(
        [
            "【試合結果】",
            "4月21日、巨人が阪神に3-2で勝利した。",
            "【ハイライト】",
            "終盤に岡田悠希の決勝打が出ました。",
            "【選手成績】",
            "先発は7回2失点でした。",
            "【試合展開】",
            "終盤の流れを守り切りました。",
        ]
    ),
    "pregame": "\n".join(
        [
            "【変更情報の要旨】",
            "雨天中止で先発がスライドします。",
            "【具体的な変更内容】",
            "開始時刻と先発見込みを整理します。",
            "【この変更が意味すること】",
            "試合前に見たい点は継投です。",
        ]
    ),
    "farm": "\n".join(
        [
            "【二軍結果・活躍の要旨】",
            "巨人二軍が勝ちました。",
            "【ファームのハイライト】",
            "若手の長打が出ました。",
            "【二軍個別選手成績】",
            "ティマが2安打3打点でした。",
            "【一軍への示唆】",
            "昇格争いを見たいところです。",
        ]
    ),
    "fact_notice": "\n".join(
        [
            "【訂正の対象】",
            "対象記事の誤記を整理します。",
            "【訂正内容】",
            "誤りと正しい内容を示します。",
            "【訂正元】",
            "球団発表を確認しました。",
            "【お詫び / ファン視点】",
            "確認できた範囲だけを短く整理します。",
        ]
    ),
}


class BodyValidatorTests(unittest.TestCase):
    def test_supported_subtypes_accept_matching_block_order(self):
        for subtype, text in VALID_CASES.items():
            with self.subTest(subtype=subtype):
                result = body_validator.validate_body_candidate(text, subtype, rendered_html=SOURCE_HTML)

                self.assertTrue(result["ok"])
                self.assertEqual(result["action"], "accept")
                self.assertEqual(result["fail_axes"], [])

    def test_first_block_mismatch_requests_reroll(self):
        text = "\n".join(
            [
                "【ハイライト】",
                "決勝打の場面です。",
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利した。",
                "【選手成績】",
                "先発は7回2失点でした。",
                "【試合展開】",
                "終盤の流れを守りました。",
            ]
        )

        result = body_validator.validate_body_candidate(text, "postgame", rendered_html=SOURCE_HTML)

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "reroll")
        self.assertIn("first_block_mismatch", result["fail_axes"])
        self.assertEqual(result["expected_first_block"], "【試合結果】")
        self.assertEqual(result["actual_first_block"], "【ハイライト】")

    def test_required_block_missing_requests_reroll(self):
        text = "\n".join(
            [
                "【二軍結果・活躍の要旨】",
                "巨人二軍が勝ちました。",
                "【ファームのハイライト】",
                "若手の長打が出ました。",
                "【一軍への示唆】",
                "昇格争いを見たいところです。",
            ]
        )

        result = body_validator.validate_body_candidate(text, "farm", rendered_html=SOURCE_HTML)

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "reroll")
        self.assertIn("required_block_missing", result["fail_axes"])
        self.assertEqual(result["missing_required_blocks"], ["【二軍個別選手成績】"])

    def test_block_order_mismatch_requests_reroll(self):
        text = "\n".join(
            [
                "【変更情報の要旨】",
                "雨天中止で先発がスライドします。",
                "【この変更が意味すること】",
                "試合前に見たい点は継投です。",
                "【具体的な変更内容】",
                "開始時刻と先発見込みを整理します。",
            ]
        )

        result = body_validator.validate_body_candidate(text, "pregame", rendered_html=SOURCE_HTML)

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "reroll")
        self.assertIn("block_order_mismatch", result["fail_axes"])

    def test_source_block_missing_is_hard_fail(self):
        result = body_validator.validate_body_candidate(VALID_CASES["live_update"], "live_update", rendered_html="")

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "fail")
        self.assertIn("source_block_missing", result["fail_axes"])
        self.assertFalse(result["has_source_block"])

    def test_postgame_abstract_lead_requests_reroll(self):
        text = "\n".join(
            [
                "【試合結果】",
                "激闘だった。4月21日、巨人が阪神に3-2で勝利した。",
                "【ハイライト】",
                "岡田悠希の決勝打で終盤に勝ち越した。",
                "【選手成績】",
                "先発は7回2失点でした。",
                "【試合展開】",
                "終盤の継投で逃げ切りました。",
            ]
        )

        result = body_validator.validate_body_candidate(text, "postgame", rendered_html=SOURCE_HTML)

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "reroll")
        self.assertIn("postgame_abstract_lead", result["fail_axes"])

    def test_postgame_score_missing_is_hard_fail(self):
        text = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に勝利した。",
                "【ハイライト】",
                "岡田悠希の決勝打で終盤に勝ち越した。",
                "【選手成績】",
                "先発は7回2失点でした。",
                "【試合展開】",
                "終盤の継投で逃げ切りました。",
            ]
        )

        result = body_validator.validate_body_candidate(text, "postgame", rendered_html=SOURCE_HTML)

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "fail")
        self.assertIn("postgame_score_missing", result["fail_axes"])
        self.assertEqual(result["stop_reason"], "postgame_score_missing")

    def test_postgame_decisive_event_missing_is_hard_fail(self):
        text = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利した。",
                "【ハイライト】",
                "終盤まで拮抗した展開が続いた。",
                "【選手成績】",
                "先発は7回2失点でした。",
                "【試合展開】",
                "終盤の継投で逃げ切りました。",
            ]
        )

        result = body_validator.validate_body_candidate(text, "postgame", rendered_html=SOURCE_HTML)

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "fail")
        self.assertIn("postgame_decisive_event_missing", result["fail_axes"])
        self.assertEqual(result["stop_reason"], "postgame_decisive_event_missing")

    def test_postgame_comment_slot_before_fact_kernel_requests_reroll(self):
        text = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利した。",
                "みなさんの意見はコメントで教えてください！",
                "【ハイライト】",
                "岡田悠希の決勝打で終盤に勝ち越した。",
                "【選手成績】",
                "先発は7回2失点でした。",
                "【試合展開】",
                "終盤の継投で逃げ切りました。",
            ]
        )

        result = body_validator.validate_body_candidate(text, "postgame", rendered_html=SOURCE_HTML)

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "reroll")
        self.assertIn("postgame_comment_slot_before_fact_kernel", result["fail_axes"])


class BodyValidatorWireInTests(unittest.TestCase):
    def test_build_news_block_rerolls_pregame_body_contract_to_safe_fallback(self):
        bad_body = "\n".join(
            [
                "【具体的な変更内容】",
                "開始時刻の変更を整理します。",
                "【変更情報の要旨】",
                "先発がスライドします。",
                "【この変更が意味すること】",
                "次に見るべき点を整理します。",
            ]
        )
        env = {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "0",
        }

        with patch.dict("os.environ", env, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=bad_body):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                        blocks, ai_body = rss_fetcher.build_news_block(
                            title="【巨人】雨天中止で先発予定だった田中将大は16日にスライド登板",
                            summary="巨人田中将大投手が雨天中止にともなってスライド登板することになった。",
                            url="https://example.com/pregame",
                            source_name="スポーツ報知",
                            category="試合速報",
                            has_game=True,
                        )

        self.assertEqual(ai_body.splitlines()[0], "【変更情報の要旨】")
        self.assertIn("【具体的な変更内容】", ai_body)
        self.assertIn("<h2>【変更情報の要旨】</h2>", blocks)


if __name__ == "__main__":
    unittest.main()
