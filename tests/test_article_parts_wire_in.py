import json
import unittest
from unittest.mock import patch

from src import rss_fetcher


class ArticlePartsWireInTests(unittest.TestCase):
    def legacy_ai_body(self) -> str:
        return "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利した。",
                "【ハイライト】",
                "終盤に岡田悠希の決勝打が飛び出した。",
                "【選手成績】",
                "決勝打を放った岡田悠希の名前が結果を分けた試合として残った。",
                "【試合展開】",
                "終盤の流れを次戦にも持ち込めるか気になります。",
            ]
        )

    def valid_parts_json(self) -> str:
        return json.dumps(
            {
                "title": "巨人が阪神に3-2で勝利 岡田悠希が決勝打",
                "fact_lead": "4月21日、巨人が阪神に3-2で勝利し、終盤に岡田悠希の決勝打が出た。",
                "body_core": [
                    "先発の田中将大投手は7回2失点で試合をつくった。",
                    "打線は終盤まで同点のまま進み、終盤に勝ち越した。",
                ],
                "game_context": "終盤まで拮抗した展開が続き、最後は勝ち越し点を守り切った。",
                "fan_view": "この勝ち方は次戦にもつながりそうです。",
                "source_attribution": {
                    "source_name": "日刊スポーツ",
                    "source_url": "https://example.com/postgame",
                },
            },
            ensure_ascii=False,
        )

    def _build_postgame_block(self, *, flag: str, gemini_return: str, parts_response: str | None, capture_logs: bool = False):
        env = {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "1",
            "ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME": flag,
            "GEMINI_API_KEY": "dummy-key",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "_fetch_team_stats_block_for_strict_article", return_value=""):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                        with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=gemini_return) as mock_legacy:
                            with patch.object(rss_fetcher, "_request_gemini_strict_text", return_value=parts_response or "") as mock_parts_request:
                                if capture_logs:
                                    with self.assertLogs("rss_fetcher", level="INFO") as logs:
                                        blocks, ai_body = rss_fetcher.build_news_block(
                                            title="【巨人】阪神に3-2で勝利　岡田が決勝打",
                                            summary="4月21日、巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
                                            url="https://example.com/postgame",
                                            source_name="日刊スポーツ",
                                            category="試合速報",
                                            has_game=True,
                                        )
                                    log_output = logs.output
                                else:
                                    blocks, ai_body = rss_fetcher.build_news_block(
                                        title="【巨人】阪神に3-2で勝利　岡田が決勝打",
                                        summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
                                        url="https://example.com/postgame",
                                        source_name="日刊スポーツ",
                                        category="試合速報",
                                        has_game=True,
                                    )
                                    log_output = []
        return blocks, ai_body, mock_legacy, mock_parts_request, log_output

    def test_flag_off_keeps_legacy_route_and_skips_parts_helpers(self):
        with patch.object(rss_fetcher, "_build_game_parts_prompt_postgame") as mock_prompt:
            with patch.object(rss_fetcher, "render_postgame") as mock_render:
                blocks, ai_body, mock_legacy, mock_parts_request, _logs = self._build_postgame_block(
                    flag="0",
                    gemini_return=self.legacy_ai_body(),
                    parts_response=self.valid_parts_json(),
                    capture_logs=False,
                )

        mock_legacy.assert_called_once()
        mock_parts_request.assert_not_called()
        mock_prompt.assert_not_called()
        mock_render.assert_not_called()
        self.assertIn("<h2>【試合結果】</h2>", blocks)
        self.assertIn("【試合展開】", ai_body)
        self.assertNotIn("yoshilover-article-source", blocks)

    def test_flag_on_postgame_applies_renderer_html_and_logs_event(self):
        blocks, ai_body, mock_legacy, _mock_parts_request, logs = self._build_postgame_block(
            flag="1",
            gemini_return=self.legacy_ai_body(),
            parts_response=self.valid_parts_json(),
            capture_logs=True,
        )

        mock_legacy.assert_not_called()
        self.assertIn('class="yoshilover-article-source"', blocks)
        self.assertIn("<h2>試合概要</h2>", blocks)
        self.assertIn("<h2>試合展開</h2>", blocks)
        self.assertIn("この勝ち方は次戦にもつながりそうです。", blocks)
        self.assertIn("【試合結果】", ai_body)
        self.assertTrue(any('"event": "article_parts_applied"' in line for line in logs))

    def test_flag_on_empty_response_falls_back_to_legacy_body(self):
        blocks, ai_body, mock_legacy, _mock_parts_request, logs = self._build_postgame_block(
            flag="1",
            gemini_return=self.legacy_ai_body(),
            parts_response="",
            capture_logs=True,
        )

        mock_legacy.assert_called_once()
        self.assertIn("<h2>【試合結果】</h2>", blocks)
        self.assertIn("終盤の流れを次戦にも持ち込めるか気になります。", ai_body)
        self.assertNotIn('class="yoshilover-article-source"', blocks)
        self.assertTrue(any('"event": "article_parts_fallback"' in line and '"reason": "empty_response"' in line for line in logs))

    def test_flag_on_json_parse_error_falls_back_and_logs_reason(self):
        blocks, ai_body, mock_legacy, _mock_parts_request, logs = self._build_postgame_block(
            flag="1",
            gemini_return=self.legacy_ai_body(),
            parts_response="{not-json",
            capture_logs=True,
        )

        mock_legacy.assert_called_once()
        self.assertIn("【試合結果】", ai_body)
        self.assertNotIn('class="yoshilover-article-source"', blocks)
        self.assertTrue(any('"event": "article_parts_fallback"' in line and "json_parse_error" in line for line in logs))

    def test_flag_on_schema_mismatch_falls_back_when_body_core_is_not_list(self):
        bad_parts = json.dumps(
            {
                "title": "巨人が勝利",
                "fact_lead": "巨人が勝利した。",
                "body_core": "これは文字列",
                "game_context": "終盤に流れが動いた。",
                "fan_view": "次戦にもつながりそうです。",
                "source_attribution": {"source_name": "日刊スポーツ", "source_url": "https://example.com/postgame"},
            },
            ensure_ascii=False,
        )
        blocks, ai_body, mock_legacy, _mock_parts_request, logs = self._build_postgame_block(
            flag="1",
            gemini_return=self.legacy_ai_body(),
            parts_response=bad_parts,
            capture_logs=True,
        )

        mock_legacy.assert_called_once()
        self.assertIn("【試合展開】", ai_body)
        self.assertNotIn('class="yoshilover-article-source"', blocks)
        self.assertTrue(any('"event": "article_parts_fallback"' in line and "schema_invalid:body_core_not_list" in line for line in logs))

    def test_flag_on_render_exception_falls_back_to_legacy_body(self):
        with patch.object(rss_fetcher, "render_postgame", side_effect=RuntimeError("boom")):
            blocks, ai_body, mock_legacy, _mock_parts_request, logs = self._build_postgame_block(
                flag="1",
                gemini_return=self.legacy_ai_body(),
                parts_response=self.valid_parts_json(),
                capture_logs=True,
            )

        mock_legacy.assert_called_once()
        self.assertIn("【試合結果】", ai_body)
        self.assertNotIn('class="yoshilover-article-source"', blocks)
        self.assertTrue(any('"event": "article_parts_fallback"' in line and "render_error:RuntimeError" in line for line in logs))

    def test_flag_on_non_postgame_keeps_legacy_route(self):
        lineup_ai_body = "\n".join(
            [
                "【試合概要】",
                "巨人は阪神戦に臨みます。",
                "【スタメン一覧】",
                "1番に丸佳浩、4番に岡田悠希が入った。",
                "【先発投手】",
                "先発は田中将大投手です。",
                "【注目ポイント】",
                "この並びが初回の入り方にどう出るか見たいところです。",
            ]
        )
        env = {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "1",
            "ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME": "1",
            "GEMINI_API_KEY": "dummy-key",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                        with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=lineup_ai_body) as mock_legacy:
                            with patch.object(rss_fetcher, "_request_gemini_strict_text") as mock_parts_request:
                                with patch.object(rss_fetcher, "_build_game_parts_prompt_postgame") as mock_prompt:
                                    with patch.object(rss_fetcher, "render_postgame") as mock_render:
                                        blocks, ai_body = rss_fetcher.build_news_block(
                                            title="【巨人】今日のスタメン発表　1番丸、4番岡田",
                                            summary="巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。",
                                            url="https://example.com/lineup",
                                            source_name="日刊スポーツ",
                                            category="試合速報",
                                            has_game=True,
                                        )

        mock_legacy.assert_called_once()
        mock_parts_request.assert_not_called()
        mock_prompt.assert_not_called()
        mock_render.assert_not_called()
        self.assertIn("【試合概要】", ai_body)
        self.assertIn("<h2>【試合概要】</h2>", blocks)


if __name__ == "__main__":
    unittest.main()
