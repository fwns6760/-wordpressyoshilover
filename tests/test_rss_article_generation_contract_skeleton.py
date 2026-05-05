from __future__ import annotations

import json
import os
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from src import article_quality_guards, body_validator, rss_fetcher


KEYWORDS = json.loads(
    (Path(__file__).resolve().parent.parent / "config" / "keywords.json").read_text(encoding="utf-8")
)
RELATED_POSTS = [
    {
        "title": "巨人の関連記事サンプル",
        "link": "https://yoshilover.com/archives/205100",
    }
]
BASE_FLAGS = {
    "ENABLE_BODY_TEMPLATE_V2": "1",
    "ENABLE_DUPLICATE_SENTENCE_GUARD": "1",
    "ENABLE_FARM_CATEGORY_NARROW_FIX": "1",
    "ENABLE_FARM_SHORT_POST_TEMPLATE": "0",
    "ENABLE_FARM_SUBTYPE_SPLIT": "1",
    "ENABLE_H3_COUNT_GUARD": "1",
    "ENABLE_RSS_MANAGER_COMMENT_KEEP": "1",
    "ENABLE_RSS_SHORT_SCORE_POST_REROUTE": "0",
    "ENABLE_RSS_SUBTYPE_CONSISTENCY_GUARD": "1",
    "ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1",
}
FIXTURE_CASES = {
    "kohama_home_steal_x": {
        "title": "【巨人】小浜佑斗が意表を突くホームスチール！２軍合流で再出発打→ヘッスラ生還",
        "summary": "【巨人】小浜佑斗が意表を突くホームスチール！２軍合流で再出発打→ヘッスラ生還",
        "source_url": "https://x.com/hochi_giants/status/2051533159368388916?s=20",
        "source_name": "スポーツ報知巨人取材班X",
        "source_type": "social_news",
        "has_game": False,
        "expected_category": "ドラフト・育成",
        "expected_subtype": "farm",
        "expected_template_key": "fallback_clean_title",
        "quote_expected": False,
        "baseline_fail_axis": "duplicate_sentence:near_duplicate_sentence",
        "body_contains": ["小浜佑斗", "ファーム"],
    },
    "roster_deregister": {
        "title": "◇セ・リーグ公示（5日） 巨人・中山礼都が登録抹消",
        "summary": "中山礼都内野手が登録抹消となった。今季23試合で打率.238。出場機会を見直す見通し。",
        "source_url": "https://example.com/npb/notice/20260505-nakayama",
        "source_name": "NPB公示",
        "source_type": "news",
        "has_game": False,
        "expected_category": "選手情報",
        "expected_subtype": "player_notice",
        "expected_template_key": "player_status_deregister",
        "quote_expected": False,
        "baseline_fail_axis": "close_marker",
        "body_contains": ["中山礼都", "登録抹消"],
    },
    "short_farm_result": {
        "title": "【二軍】巨人 4-0 ハヤテ",
        "summary": "巨人公式Xが二軍戦の4-0勝利を伝えた。",
        "source_url": "https://twitter.com/TokyoGiants/status/2051270170430345667",
        "source_name": "巨人公式X",
        "source_type": "social_news",
        "has_game": True,
        "expected_category": "ドラフト・育成",
        "expected_subtype": "farm",
        "expected_template_key": "farm_result_score",
        "quote_expected": False,
        "baseline_fail_axis": "close_marker",
        "body_contains": ["4-0", "ファーム"],
    },
    "third_team_result": {
        "title": "【三軍】巨人 5-4 千曲川",
        "summary": "巨人三軍が5-4で勝利した。育成選手の出場もあった。",
        "source_url": "https://twitter.com/TokyoGiants/status/2051271552688418866",
        "source_name": "巨人公式X",
        "source_type": "social_news",
        "has_game": True,
        "expected_category": "ドラフト・育成",
        "expected_subtype": "farm",
        "expected_template_key": "fallback_clean_title",
        "quote_expected": False,
        "baseline_fail_axis": "close_marker",
        "body_contains": ["三軍", "5-4"],
    },
    "development_player": {
        "title": "【巨人育成】山田龍聖が三軍戦で実戦復帰",
        "summary": "育成左腕の山田龍聖が三軍戦で実戦復帰した。次の登板時期も注目される。",
        "source_url": "https://example.com/farm/development/yamada-return",
        "source_name": "スポーツ報知",
        "source_type": "news",
        "has_game": False,
        "expected_category": "ドラフト・育成",
        "expected_subtype": "farm",
        "expected_template_key": "fallback_clean_title",
        "quote_expected": False,
        "baseline_fail_axis": "close_marker",
        "body_contains": ["山田龍聖", "実戦復帰"],
    },
    "manager_comment": {
        "title": "【巨人】阿部監督「次戦は1軍で」",
        "summary": "巨人が阪神に3-2で勝利。阿部監督が「次戦は1軍で」と話し、起用方針を明言した。",
        "source_url": "https://www.nikkansports.com/baseball/news/202605040001638.html",
        "source_name": "日刊スポーツ",
        "source_type": "news",
        "has_game": True,
        "expected_category": "試合速報",
        "expected_context_category": "首脳陣",
        "expected_subtype": "manager",
        "expected_template_key": "game_postgame_subject_comment",
        "quote_expected": True,
        "baseline_fail_axis": "close_marker",
        "body_contains": ["阿部監督", "次戦は1軍で"],
    },
    "coach_comment": {
        "title": "【巨人】川相コーチ「守備から入る」試合前コメント",
        "summary": "川相コーチが「守備から入る」と話し、守備面の狙いを説明した。",
        "source_url": "https://example.com/coach/kawai-comment",
        "source_name": "スポーツ報知",
        "source_type": "news",
        "has_game": False,
        "expected_category": "首脳陣",
        "expected_subtype": "manager",
        "expected_template_key": "manager_quote_generic",
        "quote_expected": True,
        "baseline_fail_axis": "close_marker",
        "body_contains": ["川相コーチ", "守備から入る"],
    },
}


class TestRSSArticleGenerationContractFixtures(unittest.TestCase):
    def _flags(self, **overrides: str) -> dict[str, str]:
        return {**BASE_FLAGS, **overrides}

    @staticmethod
    def _classification_text(case: dict[str, object]) -> str:
        return f"{case['title']} {case['summary']}".strip()

    def _render_case(
        self,
        case_name: str,
        *,
        source_link_only: bool,
        capture_logs: bool = False,
    ) -> dict[str, object]:
        case = FIXTURE_CASES[case_name]
        env = self._flags(
            ENABLE_SOURCE_LINK_ONLY_TEMPLATE="1" if source_link_only else "0",
        )
        logs: list[dict[str, object]] = []

        with patch.dict(os.environ, env, clear=False):
            category = rss_fetcher.classify_category(
                self._classification_text(case),
                KEYWORDS,
                source_url=str(case["source_url"]),
            )
            context = rss_fetcher._resolve_rss_story_type_context(
                title=str(case["title"]),
                summary=str(case["summary"]),
                category=category,
                daily_has_game=bool(case["has_game"]),
                source_type=str(case["source_type"]),
                source_url=str(case["source_url"]),
                source_name=str(case["source_name"]),
            )
            rewritten_title, template_key = rss_fetcher._rewrite_display_title_with_guard(
                str(case["title"]),
                str(case["summary"]),
                category,
                bool(case["has_game"]),
                article_subtype=str(context["title_subtype"]),
            )

            log_context = self.assertLogs("rss_fetcher", level="INFO") if capture_logs else nullcontext()
            with log_context as captured:
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=RELATED_POSTS):
                        with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                            with patch.object(rss_fetcher, "_apply_article_guardrails", side_effect=lambda *args: args[3]):
                                content, ai_body = rss_fetcher.build_news_block(
                                    title=str(case["title"]),
                                    summary=str(case["summary"]),
                                    url=str(case["source_url"]),
                                    source_name=str(case["source_name"]),
                                    category=category,
                                    has_game=bool(case["has_game"]),
                                    source_type=str(case["source_type"]),
                                    article_ai_mode_override="gemini",
                                    rewritten_title=rewritten_title,
                                    routing_context=context,
                                )

            if capture_logs:
                for record in captured.records:
                    message = record.getMessage()
                    if message.startswith("{"):
                        logs.append(json.loads(message))

            body_validation = body_validator.validate_body_candidate(
                ai_body,
                str(context["validator_subtype"]),
                rendered_html=content,
                source_context={
                    "title": rewritten_title,
                    "source_name": str(case["source_name"]),
                    "source_title": str(case["title"]),
                    "source_summary": str(case["summary"]),
                    "source_type": str(case["source_type"]),
                    "summary": str(case["summary"]),
                    "scoreline": rss_fetcher._extract_game_score_token(self._classification_text(case)),
                    "opponent": rss_fetcher._extract_game_opponent_label(self._classification_text(case)),
                    "source_url": str(case["source_url"]),
                },
            )
            preview_html = rss_fetcher._render_preview_body_html(ai_body)
            post_validation = rss_fetcher._evaluate_post_gen_validate(
                ai_body,
                article_subtype=str(context["validator_subtype"]),
                title=rewritten_title,
                rendered_html=preview_html,
            )

        return {
            "case": case,
            "category": category,
            "context": context,
            "rewritten_title": rewritten_title,
            "template_key": template_key,
            "content": content,
            "ai_body": ai_body,
            "body_validation": body_validation,
            "post_validation": post_validation,
            "logs": logs,
        }

    def _assert_source_link_only_passes(self, case_name: str) -> None:
        case = FIXTURE_CASES[case_name]
        baseline = self._render_case(case_name, source_link_only=False)
        self.assertEqual(baseline["category"], case["expected_category"])
        self.assertEqual(
            baseline["context"]["category"],
            case.get("expected_context_category", case["expected_category"]),
        )
        self.assertEqual(baseline["context"]["body_subtype"], case["expected_subtype"])
        self.assertEqual(baseline["template_key"], case["expected_template_key"])
        self.assertFalse(baseline["post_validation"]["ok"])
        self.assertIn(case["baseline_fail_axis"], baseline["post_validation"]["fail_axes"])

        rendered = self._render_case(case_name, source_link_only=True, capture_logs=True)
        self.assertEqual(rendered["category"], case["expected_category"])
        self.assertEqual(
            rendered["context"]["category"],
            case.get("expected_context_category", case["expected_category"]),
        )
        self.assertEqual(rendered["context"]["body_subtype"], case["expected_subtype"])
        self.assertEqual(rendered["template_key"], case["expected_template_key"])
        self.assertTrue(rendered["body_validation"]["ok"])
        self.assertTrue(rendered["post_validation"]["ok"])
        self.assertIsNone(article_quality_guards.find_duplicate_sentence(rendered["ai_body"]))
        self.assertIsNone(article_quality_guards.find_excessive_h3(rendered["content"]))
        self.assertIn("yoshilover-related-posts", rendered["content"])
        self.assertIn("📰 参照元:", rendered["content"])
        self.assertIn(str(case["source_url"]).replace("&", "&amp;"), rendered["content"])

        for expected_text in case["body_contains"]:
            self.assertIn(expected_text, rendered["ai_body"])

        if case["quote_expected"]:
            self.assertIn("引用: 「", rendered["ai_body"])
        else:
            self.assertNotIn("引用: 「", rendered["ai_body"])

        lead_line = rss_fetcher._first_body_content_line(rendered["ai_body"])
        self.assertTrue(lead_line)
        self.assertLess(
            rss_fetcher._body_dup_reduction_ngram_overlap(rendered["rewritten_title"], lead_line),
            0.55,
        )

        template_logs = [payload for payload in rendered["logs"] if payload.get("event") == "source_link_only_template_used"]
        self.assertEqual(len(template_logs), 1)
        self.assertEqual(template_logs[0]["source_url"], case["source_url"])
        self.assertLess(template_logs[0]["source_length"], 100)
        self.assertEqual(template_logs[0]["subtype"], case["expected_subtype"])
        self.assertEqual(template_logs[0]["body_length"], len(rendered["ai_body"]))

    def test_kohama_home_steal_x_routes_to_farm_player_short(self) -> None:
        self._assert_source_link_only_passes("kohama_home_steal_x")

    def test_roster_deregister_routes_to_player_notice(self) -> None:
        self._assert_source_link_only_passes("roster_deregister")

    def test_short_farm_result_routes_to_farm_result_short(self) -> None:
        self._assert_source_link_only_passes("short_farm_result")

    def test_third_team_result_routes_to_third_team_result_short(self) -> None:
        self._assert_source_link_only_passes("third_team_result")

    def test_development_player_note_routes_to_development_player_short(self) -> None:
        self._assert_source_link_only_passes("development_player")

    def test_manager_comment_stays_off_postgame_strict(self) -> None:
        self._assert_source_link_only_passes("manager_comment")

    def test_coach_comment_keeps_coach_specific_subtype(self) -> None:
        self._assert_source_link_only_passes("coach_comment")

    def test_true_duplicate_hits_history_duplicate_before_body_generation(self) -> None:
        history = {
            "https://x.com/hochi_giants/status/2051533159368388916?s=20": "2026-05-05T07:00:00+09:00"
        }
        is_duplicate = rss_fetcher._is_history_duplicate(
            "https://x.com/hochi_giants/status/2051533159368388916?s=20",
            "小浜佑斗二軍戦ホームスチール",
            history,
        )
        self.assertTrue(is_duplicate)


if __name__ == "__main__":
    unittest.main()
