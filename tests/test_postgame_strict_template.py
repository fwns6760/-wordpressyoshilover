import copy
import json
import logging
import unittest
from unittest.mock import patch

from src import rss_fetcher
from src.postgame_strict_template import (
    POSTGAME_STRICT_FEATURE_FLAG_ENV,
    has_sufficient_for_render,
    parse_postgame_strict_json,
    render_postgame_strict_body,
    validate_postgame_strict_payload,
)


class PostgameStrictTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_text = "\n".join(
            [
                "title: 【巨人】阪神に3-2で勝利　岡田悠希が決勝打",
                "summary: 2026年4月21日、巨人が阪神に3-2で勝利した。岡田悠希が8回に決勝打を放った。先発の山崎伊織は7回2失点。阿部監督は『終盤によく決めた』と振り返った。次戦は4月22日に阪神と東京ドームで18:00開始予定。",
                "[source_fact_block]",
                "- 2026年4月21日、巨人が阪神に3-2で勝利した。",
                "- 岡田悠希が8回に決勝打を放った。",
                "- 先発の山崎伊織は7回2失点。",
                "- 阿部監督は『終盤によく決めた』と振り返った。",
                "- 次戦は4月22日に阪神と東京ドームで18:00開始予定。",
            ]
        )

    def valid_payload(self) -> dict:
        return {
            "game_date": "2026-04-21",
            "opponent": "阪神",
            "giants_score": 3,
            "opponent_score": 2,
            "result": "win",
            "starter_name": "山崎伊織",
            "starter_innings": 7,
            "starter_hits": 5,
            "starter_runs": 2,
            "key_events": [
                {
                    "type": "other",
                    "text": "岡田悠希が8回に決勝打を放った。",
                    "evidence": "岡田悠希が8回に決勝打を放った。",
                },
                {
                    "type": "pitching",
                    "text": "先発の山崎伊織は7回2失点。",
                    "evidence": "先発の山崎伊織は7回2失点。",
                },
                {
                    "type": "batting",
                    "text": "巨人は終盤に勝ち越した。",
                    "evidence": "巨人が阪神に3-2で勝利した。",
                },
                {
                    "type": "comment",
                    "text": "阿部監督は『終盤によく決めた』と振り返った。",
                    "evidence": "阿部監督は『終盤によく決めた』と振り返った。",
                },
            ],
            "manager_comment": "阿部監督は『終盤によく決めた』と振り返った。",
            "next_game_info": {
                "date": "4月22日",
                "opponent": "阪神",
                "venue": "東京ドーム",
                "start_time": "18:00",
            },
            "confidence": "high",
            "evidence_text": [
                "2026年4月21日、巨人が阪神に3-2で勝利した。",
                "岡田悠希が8回に決勝打を放った。",
            ],
        }

    def legacy_ai_body(self) -> str:
        return "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利しました。",
                "【ハイライト】",
                "岡田悠希が終盤に決勝打を放ちました。",
                "【選手成績】",
                "先発は7回2失点でまとめました。",
                "【試合展開】",
                "更新があれば見たいところです。",
            ]
        )

    def strict_env(self, flag: str = "1") -> dict[str, str]:
        return {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "1",
            POSTGAME_STRICT_FEATURE_FLAG_ENV: flag,
            "ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME": "0",
            "GEMINI_API_KEY": "dummy-key",
        }

    def call_maybe_render_postgame_parts(
        self,
        *,
        raw_text: str,
        flag: str = "1",
        validate_result: tuple[bool, list[str]] = (True, []),
        has_sufficient: bool = True,
        render_result: str = "【試合結果】\n4月21日、巨人が阪神に3-2で勝利しました。",
        contract_ok: bool = True,
        fail_axes: list[str] | None = None,
    ):
        logger = logging.getLogger("test_postgame_strict")
        with patch.dict("os.environ", self.strict_env(flag), clear=False):
            with patch.object(rss_fetcher, "_build_source_fact_block", return_value=self.source_text):
                with patch.object(rss_fetcher, "_gemini_text_with_cache", return_value=(raw_text, {})):
                    with patch.object(rss_fetcher, "_postgame_strict_validate", return_value=validate_result):
                        with patch.object(rss_fetcher, "_postgame_strict_has_sufficient_for_render", return_value=has_sufficient):
                            with patch.object(rss_fetcher, "_postgame_strict_render", return_value=render_result):
                                with patch.object(
                                    rss_fetcher,
                                    "_validate_body_candidate",
                                    return_value={"ok": contract_ok, "fail_axes": fail_axes or []},
                                ):
                                    return rss_fetcher._maybe_render_postgame_article_parts(
                                        title="【巨人】阪神に3-2で勝利　岡田悠希が決勝打",
                                        summary="2026年4月21日、巨人が阪神に3-2で勝利した。岡田悠希が8回に決勝打を放った。",
                                        category="試合速報",
                                        has_game=True,
                                        source_name="日刊スポーツ",
                                        source_url="https://example.com/postgame",
                                        source_type="news",
                                        source_entry={},
                                        win_loss_hint="※この試合は巨人が3-2で【勝利】した試合です。",
                                        logger=logger,
                                    )

    def test_strict_json_validation_passes_with_required_facts(self):
        ok, errors = validate_postgame_strict_payload(self.valid_payload(), self.source_text)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_strict_json_validation_fails_when_score_missing(self):
        payload = self.valid_payload()
        payload["giants_score"] = None

        ok, errors = validate_postgame_strict_payload(payload, self.source_text)

        self.assertFalse(ok)
        self.assertIn("required_facts_missing:giants_score", errors)

    def test_strict_json_validation_fails_on_invalid_json(self):
        payload, reason = parse_postgame_strict_json("{not-json")

        self.assertIsNone(payload)
        self.assertIn("json_decode_error", reason)

    def test_parse_postgame_strict_json_accepts_fenced_json_wrapper(self):
        payload, reason = parse_postgame_strict_json("```json\n{\"key\":\"value\"}\n```")

        self.assertEqual(payload, {"key": "value"})
        self.assertEqual(reason, "")

    def test_parse_postgame_strict_json_accepts_plain_fenced_wrapper(self):
        payload, reason = parse_postgame_strict_json("```\n{\"key\":\"value\"}\n```")

        self.assertEqual(payload, {"key": "value"})
        self.assertEqual(reason, "")

    def test_parse_postgame_strict_json_accepts_pure_json_without_wrapper(self):
        payload, reason = parse_postgame_strict_json("{\"key\":\"value\"}")

        self.assertEqual(payload, {"key": "value"})
        self.assertEqual(reason, "")

    def test_parse_postgame_strict_json_accepts_fenced_json_with_trailing_whitespace(self):
        payload, reason = parse_postgame_strict_json("```json\n{\"key\":\"value\"}\n```  \n")

        self.assertEqual(payload, {"key": "value"})
        self.assertEqual(reason, "")

    def test_parse_postgame_strict_json_rejects_plain_text_without_json(self):
        payload, reason = parse_postgame_strict_json("just plain text without json")

        self.assertIsNone(payload)
        self.assertEqual(reason, "non_json_wrapper")

    def test_parse_postgame_strict_json_keeps_explanatory_wrapper_text_on_review_path(self):
        payload, reason = parse_postgame_strict_json(
            "Here is the response:\n```json\n{\"key\":\"value\"}\n```\nHope this helps."
        )

        self.assertIsNone(payload)
        self.assertEqual(reason, "non_json_wrapper")

    def test_parse_postgame_strict_json_preserves_response_not_string_reason(self):
        payload, reason = parse_postgame_strict_json(None)

        self.assertIsNone(payload)
        self.assertEqual(reason, "response_not_string")

    def test_parse_postgame_strict_json_preserves_empty_response_reason(self):
        payload, reason = parse_postgame_strict_json("   ")

        self.assertIsNone(payload)
        self.assertEqual(reason, "empty_response")

    def test_strict_template_renders_only_present_slots(self):
        payload = self.valid_payload()
        payload["starter_name"] = None
        payload["starter_innings"] = None
        payload["starter_hits"] = None
        payload["starter_runs"] = None
        payload["manager_comment"] = None
        payload["next_game_info"] = {}
        payload["key_events"] = [
            {
                "type": "batting",
                "text": "岡田悠希が8回に決勝打を放った。",
                "evidence": "岡田悠希が8回に決勝打を放った。",
            }
        ]

        rendered = render_postgame_strict_body(payload)

        self.assertIn("【試合結果】", rendered)
        self.assertIn("【ハイライト】", rendered)
        self.assertIn("【選手成績】", rendered)
        self.assertIn("【試合展開】", rendered)
        self.assertNotIn("投手:", rendered)
        self.assertNotIn("コメント:", rendered)
        self.assertNotIn("次戦情報:", rendered)

    def test_postgame_strict_html_v2_demotes_stat_heading(self):
        with patch.dict("os.environ", {"ENABLE_BODY_TEMPLATE_V2": "1"}, clear=False):
            blocks = rss_fetcher._render_postgame_strict_html(self.legacy_ai_body())

        self.assertIn("<h4>【選手成績】</h4>", blocks)
        self.assertEqual(blocks.count("<h3>"), 2)

    def test_strict_template_does_not_invent_pitcher_when_null(self):
        payload = self.valid_payload()
        payload["starter_name"] = None
        payload["starter_innings"] = None
        payload["starter_hits"] = None
        payload["starter_runs"] = None
        payload["key_events"] = [
            {
                "type": "other",
                "text": "岡田悠希が8回に決勝打を放った。",
                "evidence": "岡田悠希が8回に決勝打を放った。",
            }
        ]

        rendered = render_postgame_strict_body(payload)

        self.assertNotIn("山崎伊織", rendered)
        self.assertNotIn("投手:", rendered)

    def test_strict_template_renders_event_in_correct_block_by_type(self):
        rendered = render_postgame_strict_body(self.valid_payload())

        sections = {
            heading: body
            for heading, body in zip(
                [part.splitlines()[0] for part in rendered.split("\n\n")],
                rendered.split("\n\n"),
            )
        }
        self.assertIn("岡田悠希が8回に決勝打を放った。", sections["【ハイライト】"])
        self.assertIn("先発の山崎伊織は7回2失点。", sections["【選手成績】"])
        self.assertIn("巨人は終盤に勝ち越した。", sections["【選手成績】"])
        self.assertIn("阿部監督は『終盤によく決めた』と振り返った。", sections["【試合展開】"])

    def test_strict_template_dedupes_event_across_blocks(self):
        payload = self.valid_payload()
        payload["key_events"] = [
            {
                "type": "other",
                "text": "岡田悠希が8回に決勝打を放った。",
                "evidence": "岡田悠希が8回に決勝打を放った。",
            },
            {
                "type": "batting",
                "text": "岡田悠希が8回に決勝打を放った。",
                "evidence": "岡田悠希が8回に決勝打を放った。",
            },
        ]
        payload["starter_name"] = None
        payload["starter_innings"] = None
        payload["starter_hits"] = None
        payload["starter_runs"] = None
        payload["manager_comment"] = None
        payload["next_game_info"] = {}

        rendered = render_postgame_strict_body(payload)

        self.assertEqual(rendered.count("岡田悠希が8回に決勝打を放った。"), 1)

    def test_strict_evidence_must_exist_in_source(self):
        payload = self.valid_payload()
        payload["evidence_text"] = ["source にない根拠"]

        ok, errors = validate_postgame_strict_payload(payload, self.source_text)

        self.assertFalse(ok)
        self.assertIn("evidence_not_in_source:evidence_text[0]", errors)

    def test_strict_confidence_low_routes_to_review(self):
        payload = self.valid_payload()
        payload["confidence"] = "low"

        ok, errors = validate_postgame_strict_payload(payload, self.source_text)

        self.assertFalse(ok)
        self.assertIn("low_confidence_review", errors)

    def test_strict_required_only_routes_to_review(self):
        payload = self.valid_payload()
        payload["starter_name"] = None
        payload["starter_innings"] = None
        payload["starter_hits"] = None
        payload["starter_runs"] = None
        payload["key_events"] = []
        payload["manager_comment"] = None
        payload["next_game_info"] = {}

        self.assertFalse(has_sufficient_for_render(payload))

    def test_strict_next_game_info_only_facts_no_interpretation(self):
        payload = self.valid_payload()
        payload["starter_name"] = None
        payload["starter_innings"] = None
        payload["starter_hits"] = None
        payload["starter_runs"] = None
        payload["manager_comment"] = None
        payload["key_events"] = [
            {
                "type": "other",
                "text": "岡田悠希が8回に決勝打を放った。",
                "evidence": "岡田悠希が8回に決勝打を放った。",
            }
        ]

        rendered = render_postgame_strict_body(payload)

        self.assertIn("次戦情報:", rendered)
        self.assertIn("・日付: 4月22日", rendered)
        self.assertIn("・相手: 阪神", rendered)
        for banned in ("見方", "展望", "焦点", "明日の焦点", "次戦への見方"):
            self.assertNotIn(banned, rendered)

    def test_strict_feature_flag_on_postgame_uses_strict_template_path(self):
        env = {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "1",
            POSTGAME_STRICT_FEATURE_FLAG_ENV: "1",
            "ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME": "0",
            "GEMINI_API_KEY": "dummy-key",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                    with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=self.legacy_ai_body()) as mock_legacy:
                        with patch.object(
                            rss_fetcher,
                            "_gemini_text_with_cache",
                            return_value=(json.dumps(self.valid_payload(), ensure_ascii=False), {}),
                        ) as mock_request:
                            blocks, ai_body = rss_fetcher.build_news_block(
                                title="【巨人】阪神に3-2で勝利　岡田悠希が決勝打",
                                summary="2026年4月21日、巨人が阪神に3-2で勝利した。岡田悠希が8回に決勝打を放った。先発の山崎伊織は7回2失点。阿部監督は『終盤によく決めた』と振り返った。次戦は4月22日に阪神と東京ドームで18:00開始予定。",
                                url="https://example.com/postgame",
                                source_name="日刊スポーツ",
                                category="試合速報",
                                has_game=True,
                            )

        mock_legacy.assert_not_called()
        mock_request.assert_called_once()
        self.assertIn("【試合結果】", ai_body)
        self.assertIn("次戦情報:", ai_body)
        self.assertIn("更新があれば見たいところです。", ai_body)
        self.assertNotIn("この内容が次戦にも続くか。", blocks)

    def test_strict_feature_flag_off_uses_existing_path(self):
        env = {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "1",
            POSTGAME_STRICT_FEATURE_FLAG_ENV: "0",
            "ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME": "0",
            "GEMINI_API_KEY": "dummy-key",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                    with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=self.legacy_ai_body()) as mock_legacy:
                        with patch.object(rss_fetcher, "_gemini_text_with_cache") as mock_request:
                            _blocks, ai_body = rss_fetcher.build_news_block(
                                title="【巨人】阪神に3-2で勝利　岡田悠希が決勝打",
                                summary="2026年4月21日、巨人が阪神に3-2で勝利した。岡田悠希が8回に決勝打を放った。",
                                url="https://example.com/postgame",
                                source_name="日刊スポーツ",
                                category="試合速報",
                                has_game=True,
                            )

        mock_legacy.assert_called_once()
        mock_request.assert_not_called()
        self.assertIn("【試合展開】", ai_body)

    def test_strict_does_not_affect_other_subtypes(self):
        env = {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "1",
            POSTGAME_STRICT_FEATURE_FLAG_ENV: "1",
            "ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME": "0",
            "GEMINI_API_KEY": "dummy-key",
        }
        lineup_ai_body = "\n".join(
            [
                "【試合概要】",
                "巨人は阪神戦に臨みます。",
                "【スタメン一覧】",
                "1番に丸佳浩、4番に岡本和真が入りました。",
                "【先発投手】",
                "先発は戸郷翔征投手です。",
                "【注目ポイント】",
                "初回の入り方を見たいところです。",
            ]
        )
        with patch.dict("os.environ", env, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                        with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=lineup_ai_body) as mock_legacy:
                            with patch.object(rss_fetcher, "_gemini_text_with_cache") as mock_request:
                                _blocks, ai_body = rss_fetcher.build_news_block(
                                    title="【巨人】今日のスタメン発表　1番丸、4番岡本",
                                    summary="巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡本和真が入った。",
                                    url="https://example.com/lineup",
                                    source_name="日刊スポーツ",
                                    category="試合速報",
                                    has_game=True,
                                )

        mock_legacy.assert_called_once()
        mock_request.assert_not_called()
        self.assertIn("【試合概要】", ai_body)

    def test_strict_on_empty_response_returns_review_sentinel(self):
        result = self.call_maybe_render_postgame_parts(raw_text="")

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertEqual(result.reason, "strict_empty_response")

    def test_strict_on_parse_fail_returns_review_sentinel(self):
        result = self.call_maybe_render_postgame_parts(raw_text="not-json")

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertEqual(result.reason, "strict_parse_fail:non_json_wrapper")

    def test_strict_on_validation_fail_returns_review_sentinel(self):
        result = self.call_maybe_render_postgame_parts(
            raw_text=json.dumps(self.valid_payload(), ensure_ascii=False),
            validate_result=(False, ["schema_violation:key_events"]),
        )

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertEqual(result.reason, "strict_validation_fail:schema_violation:key_events")

    def test_strict_on_insufficient_returns_review_sentinel(self):
        result = self.call_maybe_render_postgame_parts(
            raw_text=json.dumps(self.valid_payload(), ensure_ascii=False),
            has_sufficient=False,
        )

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertEqual(result.reason, "strict_insufficient_for_render")

    def test_strict_on_body_validator_contract_fail_returns_review_sentinel(self):
        result = self.call_maybe_render_postgame_parts(
            raw_text=json.dumps(self.valid_payload(), ensure_ascii=False),
            contract_ok=False,
            fail_axes=["close_marker"],
        )

        self.assertIsInstance(result, rss_fetcher._PostgameStrictReviewFallback)
        self.assertEqual(result.reason, "strict_contract_fail:close_marker")

    def test_strict_off_falls_back_to_legacy_unchanged(self):
        with patch.dict("os.environ", self.strict_env("0"), clear=False):
            with patch.object(rss_fetcher, "_gemini_text_with_cache") as mock_request:
                result = rss_fetcher._maybe_render_postgame_article_parts(
                    title="【巨人】阪神に3-2で勝利　岡田悠希が決勝打",
                    summary="2026年4月21日、巨人が阪神に3-2で勝利した。岡田悠希が8回に決勝打を放った。",
                    category="試合速報",
                    has_game=True,
                    source_name="日刊スポーツ",
                    source_url="https://example.com/postgame",
                    source_type="news",
                    source_entry={},
                    win_loss_hint="※この試合は巨人が3-2で【勝利】した試合です。",
                    logger=logging.getLogger("test_postgame_strict"),
                )

        self.assertIsNone(result)
        mock_request.assert_not_called()

    def test_strict_on_success_returns_template_body_unchanged(self):
        expected_body = "\n".join(
            [
                "【試合結果】",
                "4月21日、巨人が阪神に3-2で勝利しました。",
                "【ハイライト】",
                "・岡田悠希が8回に決勝打を放ちました。",
            ]
        )

        result = self.call_maybe_render_postgame_parts(
            raw_text=json.dumps(self.valid_payload(), ensure_ascii=False),
            render_result=expected_body,
        )

        self.assertEqual(result, (expected_body, rss_fetcher._render_postgame_strict_html(expected_body)))

    def test_caller_routes_strict_review_sentinel_to_skip_path(self):
        duplicate_guard_context = {"guard_outcome": "allow"}
        sentinel = rss_fetcher._PostgameStrictReviewFallback("strict_empty_response")

        with patch.dict("os.environ", self.strict_env("1"), clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                    with patch.object(rss_fetcher, "_maybe_render_postgame_article_parts", return_value=sentinel):
                        with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=self.legacy_ai_body()) as mock_legacy:
                            result = rss_fetcher.build_news_block(
                                title="【巨人】阪神に3-2で勝利　岡田悠希が決勝打",
                                summary="2026年4月21日、巨人が阪神に3-2で勝利した。岡田悠希が8回に決勝打を放った。",
                                url="https://example.com/postgame",
                                source_name="日刊スポーツ",
                                category="試合速報",
                                has_game=True,
                                duplicate_guard_context=duplicate_guard_context,
                            )

        self.assertEqual(result, ("", ""))
        self.assertEqual(
            duplicate_guard_context.get("postgame_strict_review_reason"),
            "strict_empty_response",
        )
        mock_legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
