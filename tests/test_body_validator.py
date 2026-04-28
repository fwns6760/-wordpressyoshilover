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

    def test_postgame_first_team_player_unverified_blocks(self):
        text = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利した。",
                "【ハイライト】",
                "終盤に岡本の決勝打が出た。",
                "【選手成績】",
                "先発の戸郷は7回1失点で好投した。",
                "【試合展開】",
                "中盤から流れを引き戻して逃げ切った。",
            ]
        )

        result = body_validator.validate_body_candidate(
            text,
            "postgame",
            rendered_html=SOURCE_HTML,
            source_context={
                "title": "試合結果 巨人 3-2 阪神",
                "summary": "4月21日、巨人が阪神に3-2で勝利した。戸郷翔征が7回1失点で試合をつくった。",
                "scoreline": "3-2",
                "opponent": "阪神",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "fail")
        self.assertIn("postgame_first_team_player_unverified", result["fail_axes"])
        self.assertEqual(result["stop_reason"], "postgame_first_team_player_unverified")

    def test_postgame_first_team_score_fabrication_blocks(self):
        text = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に19対1で勝利した。",
                "【ハイライト】",
                "終盤に勝ち越し打が出た。",
                "【選手成績】",
                "先発は7回1失点だった。",
                "【試合展開】",
                "中盤以降に試合の流れをつかんだ。",
            ]
        )

        result = body_validator.validate_body_candidate(
            text,
            "postgame",
            rendered_html=SOURCE_HTML,
            source_context={
                "title": "巨人阪神戦 試合結果",
                "summary": "4月21日、巨人が阪神に1-11で試合を終えた。",
                "scoreline": "1-11",
                "opponent": "阪神",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "fail")
        self.assertIn("postgame_first_team_score_fabrication", result["fail_axes"])
        self.assertEqual(result["stop_reason"], "postgame_first_team_score_fabrication")

    def test_postgame_with_full_source_facts_passes(self):
        text = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利した。",
                "【ハイライト】",
                "終盤に岡本の決勝打が出た。",
                "【選手成績】",
                "先発の戸郷は7回1失点で好投した。",
                "【試合展開】",
                "終盤の継投で逃げ切った。",
            ]
        )

        result = body_validator.validate_body_candidate(
            text,
            "postgame",
            rendered_html=SOURCE_HTML,
            source_context={
                "title": "試合結果 巨人 3-2 阪神",
                "summary": "4月21日、巨人が阪神に3-2で勝利した。戸郷翔征が7回1失点で試合をつくり、岡本和真が決勝打を放った。",
                "scoreline": "3-2",
                "opponent": "阪神",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "accept")
        self.assertNotIn("postgame_first_team_player_unverified", result["fail_axes"])
        self.assertNotIn("postgame_first_team_score_fabrication", result["fail_axes"])

    def test_postgame_with_farm_marker_skips_first_team_check(self):
        text = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人二軍が楽天に19対1で勝利した。",
                "【ハイライト】",
                "浅野の決勝打が出た。",
                "【選手成績】",
                "先発は7回1失点だった。",
                "【試合展開】",
                "終盤まで主導権を渡さなかった。",
            ]
        )

        result = body_validator.validate_body_candidate(
            text,
            "postgame",
            rendered_html=SOURCE_HTML,
            source_context={
                "title": "巨人二軍 試合結果",
                "summary": "巨人二軍の試合後記事を整理する。",
                "scoreline": "19-1",
                "opponent": "楽天",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "accept")
        self.assertNotIn("postgame_first_team_player_unverified", result["fail_axes"])
        self.assertNotIn("postgame_first_team_score_fabrication", result["fail_axes"])


class BodyValidatorSourceAttributionTests(unittest.TestCase):
    @staticmethod
    def _source_html(*items: tuple[str, str]) -> str:
        links = " / ".join(f'<a href="{url}">{name}</a>' for name, url in items)
        return (
            '<div class="yoshilover-article-source">記事元を読む</div>'
            f'<p style="font-size:0.8em;color:#999;">📰 参照元: {links}</p>'
        )

    def test_required_official_media_x_attribution_passes_when_source_block_names_it(self):
        rendered_html = self._source_html(
            ("スポーツ報知巨人班X", "https://twitter.com/hochi_giants/status/1"),
        )

        result = body_validator.validate_body_candidate(
            VALID_CASES["live_update"],
            "live_update",
            rendered_html=rendered_html,
            source_context={
                "source_name": "スポーツ報知巨人班X",
                "source_url": "https://twitter.com/hochi_giants/status/1",
                "source_type": "social_news",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "accept")
        self.assertTrue(result["source_attribution_required"])
        self.assertEqual(result["primary_source_kind"], "official_media_x")

    def test_required_official_x_missing_in_source_block_requests_reroll(self):
        rendered_html = self._source_html(
            ("スポーツ報知", "https://hochi.news/articles/20260421-OHT1T51111.html"),
        )

        result = body_validator.validate_body_candidate(
            VALID_CASES["pregame"],
            "pregame",
            rendered_html=rendered_html,
            source_context={
                "source_name": "巨人公式X",
                "source_url": "https://twitter.com/TokyoGiants/status/1",
                "source_type": "social_news",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "reroll")
        self.assertIn("source_attribution_missing", result["fail_axes"])
        self.assertEqual(result["missing_required_sources"], ["巨人公式X"])

    def test_postgame_allows_missing_x_attribution_when_t1_web_source_exists(self):
        rendered_html = self._source_html(
            ("スポーツ報知", "https://hochi.news/articles/20260421-OHT1T51111.html"),
        )

        result = body_validator.validate_body_candidate(
            VALID_CASES["postgame"],
            "postgame",
            rendered_html=rendered_html,
            source_context={
                "source_type": "social_news",
                "source_links": [
                    {"name": "巨人公式X", "url": "https://twitter.com/TokyoGiants/status/1"},
                    {"name": "スポーツ報知", "url": "https://hochi.news/articles/20260421-OHT1T51111.html"},
                ],
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "accept")
        self.assertFalse(result["source_attribution_required"])
        self.assertTrue(result["has_t1_web_source"])

    def test_ambiguous_x_source_is_hard_fail(self):
        rendered_html = self._source_html(
            ("球団X", "https://twitter.com/giants_info_clip/status/1"),
        )

        result = body_validator.validate_body_candidate(
            VALID_CASES["fact_notice"],
            "fact_notice",
            rendered_html=rendered_html,
            source_context={
                "source_name": "球団X",
                "source_url": "https://twitter.com/giants_info_clip/status/1",
                "source_type": "social_news",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "fail")
        self.assertIn("source_attribution_ambiguous", result["fail_axes"])
        self.assertEqual(result["stop_reason"], "source_attribution_ambiguous")

    def test_pregame_requires_x_attribution_even_when_t1_web_source_exists(self):
        rendered_html = self._source_html(
            ("スポーツ報知", "https://hochi.news/articles/20260421-OHT1T51111.html"),
        )

        result = body_validator.validate_body_candidate(
            VALID_CASES["pregame"],
            "pregame",
            rendered_html=rendered_html,
            source_context={
                "source_type": "social_news",
                "source_links": [
                    {"name": "巨人公式X", "url": "https://twitter.com/TokyoGiants/status/1"},
                    {"name": "スポーツ報知", "url": "https://hochi.news/articles/20260421-OHT1T51111.html"},
                ],
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "reroll")
        self.assertTrue(result["source_attribution_required"])
        self.assertIn("source_attribution_missing", result["fail_axes"])


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
