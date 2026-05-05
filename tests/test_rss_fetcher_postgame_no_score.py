import json
import logging
import os
import unittest
from unittest.mock import patch

from src import rss_fetcher
from src.postgame_strict_fact_recovery import ENABLE_POSTGAME_STRICT_FACT_RECOVERY_ENV
from src.postgame_strict_template import POSTGAME_STRICT_FEATURE_FLAG_ENV


FLAG = rss_fetcher.ENABLE_POSTGAME_NO_SCORE_SHORT_COMMENT_REROUTE_ENV_FLAG


class PostgameNoScoreShortCommentRerouteTests(unittest.TestCase):
    def strict_env(self, flag: str) -> dict[str, str]:
        return {
            "STRICT_FACT_MODE": "1",
            POSTGAME_STRICT_FEATURE_FLAG_ENV: "1",
            ENABLE_POSTGAME_STRICT_FACT_RECOVERY_ENV: "0",
            "GEMINI_API_KEY": "dummy-key",
            FLAG: flag,
        }

    @staticmethod
    def missing_score_payload() -> dict[str, object]:
        return {
            "game_date": "2026-05-05",
            "opponent": "",
            "giants_score": None,
            "opponent_score": None,
            "result": "",
            "key_events": [],
            "confidence": "medium",
            "evidence_text": ["戸郷翔征は試合後に振り返った。"],
        }

    def _call_postgame_parts(
        self,
        *,
        title: str,
        summary: str,
        flag: str,
        raw_text: str | None = None,
        validate_result: tuple[bool, list[str]] | None = None,
        has_sufficient: bool = True,
        render_result: str = "【試合結果】\n5月5日、巨人がヤクルトに3-2で勝利しました。",
        contract_ok: bool = True,
        fail_axes: list[str] | None = None,
    ):
        logger = logging.getLogger("rss_fetcher")
        raw_text = raw_text or json.dumps(self.missing_score_payload(), ensure_ascii=False)

        with patch.dict(os.environ, self.strict_env(flag), clear=False):
            with patch.object(rss_fetcher, "_detect_article_subtype", return_value="postgame"):
                with patch.object(rss_fetcher, "_gemini_text_with_cache", return_value=(raw_text, {})) as mock_gemini:
                    validate_ctx = (
                        patch.object(rss_fetcher, "_postgame_strict_validate", return_value=validate_result)
                        if validate_result is not None
                        else patch.object(rss_fetcher, "_postgame_strict_validate", wraps=rss_fetcher._postgame_strict_validate)
                    )
                    with validate_ctx:
                        with patch.object(rss_fetcher, "_postgame_strict_has_sufficient_for_render", return_value=has_sufficient):
                            with patch.object(rss_fetcher, "_postgame_strict_render", return_value=render_result):
                                with patch.object(
                                    rss_fetcher,
                                    "_validate_body_candidate",
                                    return_value={"ok": contract_ok, "fail_axes": fail_axes or []},
                                ):
                                    result = rss_fetcher._maybe_render_postgame_article_parts(
                                        title=title,
                                        summary=summary,
                                        category="試合速報",
                                        has_game=True,
                                        source_name="スポーツ報知",
                                        source_url="https://example.com/postgame-no-score",
                                        source_type="news",
                                        source_entry={},
                                        win_loss_hint="※この試合の勝敗は source 由来のみで扱う",
                                        logger=logger,
                                    )
        return result, mock_gemini

    def test_flag_off_keeps_postgame_strict_review_when_no_score(self):
        result, mock_gemini = self._call_postgame_parts(
            title="巨人ヤクルト戦 戸郷翔征の試合後発言整理",
            summary="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と試合を振り返った。",
            flag="0",
        )

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertIn("required_facts_missing:giants_score", result.reason)
        mock_gemini.assert_called_once()

    def test_flag_on_reroutes_to_short_comment_when_player_and_quote_keyword_present(self):
        routing_context = {
            "category": "試合速報",
            "title_subtype": "postgame",
            "body_subtype": "postgame",
            "validator_subtype": "postgame",
            "effective_generation_category": "試合速報",
        }

        with patch.dict(os.environ, self.strict_env("1"), clear=False):
            with patch.object(rss_fetcher, "_detect_article_subtype", return_value="postgame"):
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                        with patch.object(rss_fetcher, "_gemini_text_with_cache") as mock_gemini:
                            _content, ai_body = rss_fetcher.build_news_block(
                                title="巨人ヤクルト戦 戸郷翔征の試合後発言整理",
                                summary="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と試合を振り返った。",
                                url="https://example.com/postgame-no-score",
                                source_name="スポーツ報知",
                                category="試合速報",
                                has_game=True,
                                article_ai_mode_override="gemini",
                                source_type="news",
                                duplicate_guard_context={},
                                routing_context=routing_context,
                            )

        self.assertEqual(routing_context["body_subtype"], "social_news")
        self.assertEqual(routing_context["validator_subtype"], "social_news")
        self.assertEqual(routing_context["postgame_rerouted_subtype"], "postgame_short_comment")
        self.assertIn("【話題の要旨】", ai_body)
        self.assertNotRegex(ai_body, r"\d{1,2}\s*[-－–]\s*\d{1,2}")
        mock_gemini.assert_not_called()

    def test_flag_on_keeps_review_when_no_player_name(self):
        result, mock_gemini = self._call_postgame_parts(
            title="巨人ヤクルト戦 試合後整理",
            summary="ベンチは「不用意な1球を減らしていけばまた勝てる」と試合を振り返った。",
            flag="1",
        )

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertIn("required_facts_missing:giants_score", result.reason)
        mock_gemini.assert_called_once()

    def test_flag_on_keeps_review_when_no_quote_keyword(self):
        result, mock_gemini = self._call_postgame_parts(
            title="巨人ヤクルト戦 戸郷翔征の試合後整理",
            summary="戸郷翔征の試合後の様子を伝えた。",
            flag="1",
        )

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertIn("required_facts_missing:giants_score", result.reason)
        mock_gemini.assert_called_once()

    def test_flag_on_does_not_intercept_when_score_present(self):
        payload = {
            "game_date": "2026-05-05",
            "opponent": "ヤクルト",
            "giants_score": 3,
            "opponent_score": 2,
            "result": "win",
            "key_events": [{"type": "batting", "text": "戸郷翔征が試合後にコメント", "evidence": "戸郷翔征が試合後にコメント"}],
        }
        result, mock_gemini = self._call_postgame_parts(
            title="巨人 3-2 ヤクルト 戸郷翔征が試合後にコメント",
            summary="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と試合を振り返った。",
            flag="1",
            raw_text=json.dumps(payload, ensure_ascii=False),
            validate_result=(True, []),
            has_sufficient=True,
            render_result="【試合結果】\n5月5日、巨人がヤクルトに3-2で勝利しました。\n【ハイライト】\n・戸郷翔征が試合後にコメントしました。",
            contract_ok=True,
        )

        self.assertIsInstance(result, tuple)
        body_text, _rendered_html = result
        self.assertIn("3-2", body_text)
        mock_gemini.assert_called_once()

    def test_flag_on_emits_structured_log(self):
        with patch.dict(os.environ, self.strict_env("1"), clear=False):
            with self.assertLogs("rss_fetcher", level="INFO") as captured:
                result = rss_fetcher._maybe_reroute_postgame_no_score_short_comment(
                    title="巨人ヤクルト戦 戸郷翔征の試合後発言整理",
                    summary="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と試合を振り返った。",
                    category="試合速報",
                    source_url="https://example.com/postgame-no-score",
                    source_name="スポーツ報知",
                    logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                )

        self.assertIsInstance(result, rss_fetcher._PostgameNoScoreShortCommentReroute)
        self.assertNotRegex(result.body_text, r"\d{1,2}\s*[-－–]\s*\d{1,2}")
        payload = json.loads(captured.records[-1].getMessage())
        self.assertEqual(payload["event"], "postgame_no_score_short_comment_rerouted")
        self.assertEqual(payload["source_url"], "https://example.com/postgame-no-score")
        self.assertEqual(payload["original_subtype"], "postgame")
        self.assertEqual(payload["rerouted_subtype"], "postgame_short_comment")
        self.assertEqual(payload["player_name"], "戸郷翔征")
        self.assertTrue(payload["has_quote_keyword"])

    def test_flag_on_does_not_relax_required_facts_threshold(self):
        result = rss_fetcher._validate_body_candidate(
            "\n".join(
                [
                    "【試合結果】",
                    "5月5日、巨人がヤクルトに勝利した。",
                    "【ハイライト】",
                    "戸郷翔征が試合後に振り返った。",
                    "【選手成績】",
                    "主な内容を整理した。",
                    "【試合展開】",
                    "終盤の流れを確認した。",
                ]
            ),
            "postgame",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stop_reason"], "postgame_score_missing")
        self.assertIn("postgame_score_missing", result["fail_axes"])


if __name__ == "__main__":
    unittest.main()
