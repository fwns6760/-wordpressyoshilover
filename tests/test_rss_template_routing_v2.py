import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


KEYWORDS = json.loads(
    (Path(__file__).resolve().parent.parent / "config" / "keywords.json").read_text(encoding="utf-8")
)
FLAG = rss_fetcher.ENABLE_RSS_TEMPLATE_ROUTING_V2_ENV_FLAG


class RSSTemplateRoutingV2Tests(unittest.TestCase):
    def _analyze(
        self,
        *,
        title: str,
        summary: str,
        source_type: str = "news",
        source_url: str = "https://example.com/story",
        source_name: str = "スポーツ報知",
        category: str = "",
    ) -> dict[str, object]:
        return rss_fetcher._analyze_source(
            {
                "title": title,
                "summary": summary,
                "source_type": source_type,
                "source_url": source_url,
                "source_name": source_name,
                "category": category,
            }
        )

    def test_analyze_x_post_with_score_and_opponent(self):
        analysis = self._analyze(
            title="巨人 3-2 ヤクルト 戸郷翔征が試合後にコメント",
            summary="戸郷翔征は「不用意な1球を減らしたい」と振り返った。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2053000000000000001",
            source_name="スポーツ報知巨人班X",
        )

        self.assertEqual(analysis["source_type"], "x_post")
        self.assertTrue(analysis["has_score"])
        self.assertTrue(analysis["has_opponent"])

    def test_analyze_short_x_post(self):
        analysis = self._analyze(
            title="巨人公式Xが練習風景を投稿",
            summary="短いお知らせです。",
            source_type="social_news",
            source_url="https://x.com/TokyoGiants/status/2053000000000000002",
            source_name="巨人公式X",
        )

        self.assertEqual(analysis["source_type"], "x_post")
        self.assertLess(int(analysis["source_text_length"]), 100)

    def test_analyze_hochi_news_manager_quote(self):
        analysis = self._analyze(
            title="【巨人】阿部監督「次戦は1軍で」",
            summary="阿部監督が「次戦は1軍で」と起用方針を明かした。",
            source_type="news",
            source_url="https://hochi.news/articles/20260505-OHT1T51000.html",
            source_name="スポーツ報知",
            category="首脳陣",
        )

        self.assertEqual(analysis["source_type"], "hochi_news")
        self.assertEqual(analysis["actor_kind"], "manager")
        self.assertTrue(analysis["has_quote"])

    def test_analyze_farm_three_team(self):
        analysis = self._analyze(
            title="【三軍】巨人がJABA新潟大会へ",
            summary="三軍がJABA新潟大会に参加し、育成選手も帯同する。",
            source_type="news",
            source_url="https://example.com/farm/jaba",
            source_name="スポーツ報知",
        )

        self.assertTrue(analysis["has_farm_or_third_team"])

    def test_analyze_recovery_post(self):
        analysis = self._analyze(
            title="【巨人】西舘勇陽が術後初の復帰登板へ 1軍合流も視野",
            summary="西舘勇陽投手がリハビリを経て復帰登板へ。一軍合流も視野に入った。",
            source_type="news",
            source_url="https://example.com/recovery",
            source_name="スポーツ報知",
        )

        self.assertTrue(analysis["has_recovery_or_injury"])

    def test_analyze_roster_notice(self):
        analysis = self._analyze(
            title="◇セ・リーグ公示 巨人・中山礼都が登録抹消",
            summary="中山礼都内野手が登録抹消となった。",
            source_type="news",
            source_url="https://example.com/npb/kouji",
            source_name="NPB公示",
        )

        self.assertTrue(analysis["has_roster_notice"])

    def test_select_postgame_strict_only_when_full_facts(self):
        analysis = self._analyze(
            title="巨人 3-2 ヤクルト 岡本和真が決勝打",
            summary="岡本和真が決勝打を放ち、戸郷翔征は6回2失点で勝利に貢献した。",
            source_type="news",
            source_url="https://example.com/postgame",
            source_name="スポーツ報知",
        )

        template_key, subtype = rss_fetcher._select_template_v2(analysis, {})
        self.assertEqual(template_key, "postgame_strict")
        self.assertEqual(subtype, "postgame")

    def test_select_score_lite_when_score_only(self):
        analysis = self._analyze(
            title="巨人 3-2 試合結果メモ",
            summary="終盤にスコアが動いた。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2053000000000000003",
            source_name="スポーツ報知巨人班X",
        )

        template_key, subtype = rss_fetcher._select_template_v2(analysis, {})
        self.assertEqual(template_key, "score_lite")
        self.assertEqual(subtype, "social_news")

    def test_select_short_comment_when_quote_only(self):
        analysis = self._analyze(
            title="【巨人】戸郷翔征が試合後にコメント",
            summary="戸郷翔征は「次は先頭打者を抑えたい」と振り返った。",
            source_type="news",
            source_url="https://example.com/player-comment",
            source_name="スポーツ報知",
            category="選手情報",
        )

        template_key, subtype = rss_fetcher._select_template_v2(analysis, {})
        self.assertEqual(template_key, "player_quote_short")
        self.assertEqual(subtype, "player")

    def test_select_farm_short_when_farm_and_short_source(self):
        analysis = self._analyze(
            title="【二軍】巨人 4-0 ハヤテ",
            summary="巨人二軍が4-0で勝利した。",
            source_type="social_news",
            source_url="https://x.com/TokyoGiants/status/2053000000000000004",
            source_name="巨人公式X",
            category="ドラフト・育成",
        )

        template_key, subtype = rss_fetcher._select_template_v2(analysis, {})
        self.assertEqual(template_key, "farm_short")
        self.assertEqual(subtype, "farm")

    def test_select_player_notice_short_when_roster(self):
        analysis = self._analyze(
            title="◇セ・リーグ公示 巨人・中山礼都が登録抹消",
            summary="中山礼都内野手が登録抹消となった。",
            source_type="news",
            source_url="https://example.com/npb/kouji-2",
            source_name="NPB公示",
            category="選手情報",
        )

        template_key, subtype = rss_fetcher._select_template_v2(analysis, {})
        self.assertEqual(template_key, "notice_short")
        self.assertEqual(subtype, "player_notice")

    def test_select_review_when_facts_insufficient(self):
        analysis = {
            "has_giants_relevance": True,
            "has_farm_or_third_team": False,
            "has_recovery_or_injury": False,
            "has_roster_notice": False,
            "actor_kind": "",
            "actor_name": "",
            "has_quote": False,
            "has_score": False,
            "has_opponent": False,
            "source_text_length": 180,
            "decisive_event_text": "",
        }

        template_key, subtype = rss_fetcher._select_template_v2(analysis, {})
        self.assertEqual(template_key, "review")
        self.assertEqual(subtype, "review_with_reason")

    def test_finalize_title_rewrites_bench_comment(self):
        rewritten, review = rss_fetcher._finalize_title(
            "首脳陣コメント整理 ベンチ関連の発言ポイント",
            source_title="【巨人】阿部監督「次戦は1軍で」",
            summary="阿部監督が「次戦は1軍で」と起用方針を明かした。",
            analysis={"actor_name": "阿部監督", "actor_kind": "manager"},
        )

        self.assertEqual(rewritten, "阿部監督「次戦は1軍で」")
        self.assertIsNone(review)

    def test_finalize_title_routes_to_review_when_actor_missing(self):
        rewritten, review = rss_fetcher._finalize_title(
            "首脳陣コメント整理 ベンチ関連の発言ポイント",
            source_title="【巨人】ベンチの動きを整理",
            summary="続報を確認中。",
            analysis={},
        )

        self.assertEqual(rewritten, "首脳陣コメント整理 ベンチ関連の発言ポイント")
        self.assertIsInstance(review, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(review.reason, "blacklist_phrase:ベンチ関連の発言ポイント")

    def test_flag_off_preserves_existing_routing(self):
        title = "【巨人】阿部監督「次戦は1軍で」"
        summary = "巨人が阪神に3-2で勝利。阿部監督が「次戦は1軍で」と話し、起用方針を明言した。"
        category = rss_fetcher.classify_category(f"{title} {summary}", KEYWORDS)

        with patch.dict(os.environ, {FLAG: "0"}, clear=False):
            context = rss_fetcher._resolve_rss_story_type_context(
                title=title,
                summary=summary,
                category=category,
                daily_has_game=True,
                source_type="news",
                source_url="https://www.nikkansports.com/baseball/news/202605040001638.html",
                source_name="日刊スポーツ",
            )

        self.assertEqual(category, "試合速報")
        self.assertEqual(context["category"], "試合速報")
        self.assertEqual(context["title_subtype"], "postgame")
        self.assertEqual(context["body_subtype"], "postgame")
        self.assertEqual(context["validator_subtype"], "postgame")


if __name__ == "__main__":
    unittest.main()
