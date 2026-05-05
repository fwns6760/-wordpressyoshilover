import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher
KEYWORDS = json.loads(
    (Path(__file__).resolve().parent.parent / "config" / "keywords.json").read_text(encoding="utf-8")
)
RSS_LOGGER = rss_fetcher.logging.getLogger("rss_fetcher")
DEFAULT_NEW_FLAGS = {
    "ENABLE_RSS_SHORT_SCORE_POST_REROUTE": "0",
    "ENABLE_RSS_MANAGER_COMMENT_KEEP": "0",
    "ENABLE_RSS_SOCIAL_PLAYER_SUBROUTE": "0",
    "ENABLE_FARM_CATEGORY_NARROW_FIX": "0",
    "ENABLE_RSS_SUBTYPE_CONSISTENCY_GUARD": "0",
}
def _case(title: str, summary: str, source_type: str, source_url: str, source_name: str, daily_has_game: bool) -> dict[str, object]:
    return {"title": title, "summary": summary, "source_type": source_type, "source_url": source_url, "source_name": source_name, "daily_has_game": daily_has_game}

FARM_SCORE_CASE = _case("【二軍】巨人 4-0 ハヤテ", "巨人公式Xが二軍戦の4-0勝利を伝えた。", "social_news", "https://twitter.com/TokyoGiants/status/2051270170430345667", "巨人公式X", True)
MANAGER_CASE = _case("【巨人】阿部監督『次戦は1軍で』", "巨人が阪神に3-2で勝利。阿部監督が次戦の1軍起用を明言した。", "news", "https://www.nikkansports.com/baseball/news/202605040001638.html", "日刊スポーツ", True)
RECOVERY_SOCIAL_CASE = _case("【巨人】西舘勇陽が実戦復帰へ", "西舘勇陽投手がブルペン投球を再開し、実戦復帰が近づいている。", "social_news", "https://twitter.com/hochi_giants/status/2051392340326072563", "スポーツ報知巨人班X", False)
NOTICE_SOCIAL_CASE = _case("【巨人】浅野翔吾が昇格へ 一軍合流", "スポーツ報知巨人班Xが浅野翔吾外野手の一軍合流と昇格を伝えた。", "social_news", "https://twitter.com/hochi_giants/status/2051392340326072564", "スポーツ報知巨人班X", False)
RECOVERY_NEWS_CASE = _case("【巨人】山崎伊織が復帰へ前進", "山崎伊織投手が故障離脱からの復帰へ前進した。ブルペンで投球練習を再開した。", "news", "https://www.nikkansports.com/baseball/news/202605040001796.html", "日刊スポーツ", False)
class RSSFetcherTypeRoutingFlagTests(unittest.TestCase):
    def _flags(self, **overrides: str) -> dict[str, str]:
        return {**DEFAULT_NEW_FLAGS, **overrides}

    def _run_context(self, *, title: str, summary: str, source_type: str, source_url: str, source_name: str, daily_has_game: bool, flags: dict[str, str] | None = None, capture_logs: bool = False, classify_text: str | None = None):
        env = self._flags(**(flags or {}))
        classify_text = classify_text or f"{title} {summary}"
        routing_kwargs = {
            "title": title,
            "summary": summary,
            "daily_has_game": daily_has_game,
            "source_type": source_type,
            "source_url": source_url,
            "source_name": source_name,
        }
        with patch.dict(os.environ, env, clear=False):
            if capture_logs:
                with self.assertLogs("rss_fetcher", level="INFO") as cm:
                    category = rss_fetcher.classify_category(classify_text, KEYWORDS, source_url=source_url, logger=RSS_LOGGER)
                    context = rss_fetcher._resolve_rss_story_type_context(category=category, logger=RSS_LOGGER, **routing_kwargs)
                return category, context, json.loads(cm.output[0].split(":", 2)[2])
            category = rss_fetcher.classify_category(classify_text, KEYWORDS)
            context = rss_fetcher._resolve_rss_story_type_context(category=category, **routing_kwargs)
        return category, context

    def _assert_social_publish_gate(self, title: str, summary: str, category: str, subtype: str) -> None:
        self.assertEqual(rss_fetcher.resolve_publish_gate_subtype(title, summary, category, subtype, "social_news"), "social")
    def test_new_flags_default_off_preserve_current_routing_matrix(self):
        cases = (
            (
                MANAGER_CASE,
                "試合速報",
                {"category": "試合速報", "title_subtype": "postgame", "body_subtype": "postgame", "validator_subtype": "postgame"},
            ),
            (
                FARM_SCORE_CASE,
                "ドラフト・育成",
                {"title_subtype": "farm", "body_subtype": "farm", "validator_subtype": "farm"},
            ),
            (
                RECOVERY_SOCIAL_CASE,
                "選手情報",
                {"title_subtype": "player", "body_subtype": "social_news", "validator_subtype": "player"},
            ),
        )
        for case, expected_category, expected_fields in cases:
            with self.subTest(title=case["title"]):
                category, context = self._run_context(**case)
                self.assertEqual(category, expected_category)
                for field, expected_value in expected_fields.items():
                    self.assertEqual(context[field], expected_value)

    def test_short_score_reroute_on_routes_official_social_score_to_social(self):
        category, context, payload = self._run_context(
            **FARM_SCORE_CASE,
            flags={"ENABLE_RSS_SHORT_SCORE_POST_REROUTE": "1"},
            capture_logs=True,
        )
        self.assertEqual(payload["event"], "rss_short_score_rerouted")
        self.assertEqual(payload["pre_subtype"], "farm")
        self.assertEqual(payload["post_subtype"], "social_news")
        self.assertEqual(category, "ドラフト・育成")
        self.assertEqual(context["title_subtype"], "social_news")
        self.assertEqual(context["body_subtype"], "social_news")
        self.assertEqual(context["validator_subtype"], "social_news")
        self._assert_social_publish_gate(FARM_SCORE_CASE["title"], FARM_SCORE_CASE["summary"], category, context["title_subtype"])

    def test_short_score_reroute_on_keeps_long_social_result_on_existing_farm_route(self):
        long_summary = " ".join(["巨人公式Xが二軍戦の4-0勝利と選手コメントを詳しく伝えた。"] * 8)
        category, context = self._run_context(
            **{**FARM_SCORE_CASE, "summary": long_summary},
            flags={"ENABLE_RSS_SHORT_SCORE_POST_REROUTE": "1"},
        )
        self.assertEqual(category, "ドラフト・育成")
        self.assertEqual(context["title_subtype"], "farm")
        self.assertEqual(context["body_subtype"], "farm")
        self.assertEqual(context["validator_subtype"], "farm")
    def test_manager_comment_keep_on_reroutes_postgame_comment_story_to_manager(self):
        category, context, payload = self._run_context(
            **MANAGER_CASE,
            flags={"ENABLE_RSS_MANAGER_COMMENT_KEEP": "1"},
            capture_logs=True,
        )
        self.assertEqual(payload["event"], "rss_manager_comment_kept")
        self.assertEqual(category, "試合速報")
        self.assertEqual(context["category"], "首脳陣")
        self.assertEqual(context["title_subtype"], "manager")
        self.assertEqual(context["body_subtype"], "manager")
        self.assertEqual(context["validator_subtype"], "manager")
        category, context = self._run_context(
            title="【巨人】阪神に3-2で勝利 岡本和真が決勝打",
            summary="巨人が阪神に3-2で勝利した。岡本和真が決勝打を放った。",
            source_type="news",
            source_url="https://hochi.news/articles/20260505-OHT1T51111.html",
            source_name="スポーツ報知",
            daily_has_game=True,
            flags={"ENABLE_RSS_MANAGER_COMMENT_KEEP": "1"},
        )
        self.assertEqual(category, "試合速報")
        self.assertEqual(context["category"], "試合速報")
        self.assertEqual(context["title_subtype"], "postgame")
        self.assertEqual(context["body_subtype"], "postgame")
    def test_social_player_subroute_on_recovers_recovery_and_notice_subtypes(self):
        category, context, payload = self._run_context(
            **RECOVERY_SOCIAL_CASE,
            flags={"ENABLE_RSS_SOCIAL_PLAYER_SUBROUTE": "1"},
            capture_logs=True,
        )
        self.assertEqual(payload["event"], "rss_social_player_subrouted")
        self.assertEqual(payload["sub_subtype"], "social_player_recovery")
        self.assertEqual(category, "選手情報")
        self.assertEqual(context["title_subtype"], "player_recovery")
        self.assertEqual(context["body_subtype"], "player_recovery")
        self.assertEqual(context["validator_subtype"], "player_recovery")
        self.assertEqual(context["social_player_subroute"], "social_player_recovery")
        self._assert_social_publish_gate(RECOVERY_SOCIAL_CASE["title"], RECOVERY_SOCIAL_CASE["summary"], category, context["title_subtype"])
        _, context = self._run_context(
            **NOTICE_SOCIAL_CASE,
            flags={"ENABLE_RSS_SOCIAL_PLAYER_SUBROUTE": "1"},
        )
        self.assertEqual(context["generation_category"], "選手情報")
        self.assertEqual(context["title_subtype"], "player_notice")
        self.assertEqual(context["body_subtype"], "player_notice")
        self.assertEqual(context["validator_subtype"], "player_notice")
        self.assertEqual(context["social_player_subroute"], "social_player_notice")
    def test_farm_category_narrow_fix_on_reroutes_third_team_keyword_only_case(self):
        category, _, payload = self._run_context(
            title="【三軍】巨人 5-4 千曲川",
            summary="巨人三軍が5-4で勝利した。",
            source_type="social_news",
            source_url="https://twitter.com/TokyoGiants/status/2051271552688418866",
            source_name="巨人公式X",
            daily_has_game=True,
            flags={"ENABLE_FARM_CATEGORY_NARROW_FIX": "1"},
            capture_logs=True,
        )
        self.assertEqual(payload["event"], "rss_farm_category_rerouted")
        self.assertEqual(category, "ドラフト・育成")
        category, _ = self._run_context(
            title="【一軍】巨人 5-4 阪神",
            summary="東京ドームで巨人が5-4で勝利 三軍戦ではない",
            source_type="news",
            source_url="https://hochi.news/articles/20260505-OHT1T50000.html",
            source_name="スポーツ報知",
            daily_has_game=True,
            flags={"ENABLE_FARM_CATEGORY_NARROW_FIX": "1"},
        )
        self.assertEqual(category, "試合速報")
    def test_subtype_consistency_guard_tracks_existing_and_repaired_recovery_routes(self):
        category, context = self._run_context(**RECOVERY_NEWS_CASE)
        self.assertEqual(category, "選手情報")
        self.assertEqual(context["title_subtype"], "player")
        self.assertEqual(context["body_subtype"], "player_recovery")
        self.assertEqual(context["validator_subtype"], "player")
        category, context, payload = self._run_context(
            **RECOVERY_NEWS_CASE,
            flags={"ENABLE_RSS_SUBTYPE_CONSISTENCY_GUARD": "1"},
            capture_logs=True,
        )
        self.assertEqual(payload["event"], "rss_fetcher_subtype_mismatch_repaired")
        self.assertEqual(payload["body_subtype"], "player_recovery")
        self.assertEqual(payload["title_subtype"], "player")
        self.assertEqual(payload["repaired_to"], "player_recovery")
        self.assertEqual(category, "選手情報")
        self.assertEqual(context["title_subtype"], "player_recovery")
        self.assertEqual(context["body_subtype"], "player_recovery")
        self.assertEqual(context["validator_subtype"], "player_recovery")
    def test_short_score_reroute_interacts_with_short_source_template(self):
        flags = {
            "ENABLE_RSS_SHORT_SCORE_POST_REROUTE": "1",
            "ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1",
            "ENABLE_BODY_TEMPLATE_V2": "1",
        }
        with patch.dict(os.environ, self._flags(**flags), clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    _, ai_body = rss_fetcher.build_news_block(
                        title=FARM_SCORE_CASE["title"],
                        summary=FARM_SCORE_CASE["summary"],
                        url=FARM_SCORE_CASE["source_url"],
                        source_name=FARM_SCORE_CASE["source_name"],
                        category="ドラフト・育成",
                        has_game=True,
                        source_type="social_news",
                    )
        self.assertIn("【話題の要旨】", ai_body)
        self.assertIn("【投稿で出ていた内容】", ai_body)
        self.assertNotIn("【二軍結果・活躍の要旨】", ai_body)

if __name__ == "__main__":
    unittest.main()
