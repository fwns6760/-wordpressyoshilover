"""Regression contract for 2026-05-17 user-reported classification misses.

These cases pin source-derived routing. They intentionally do not depend on
LLM/self-evaluation so a future drift shows up as a test failure.
"""

import json
from pathlib import Path
import unittest

from src import rss_fetcher


ROOT = Path(__file__).resolve().parents[1]


def _resolve(
    *,
    title: str,
    summary: str,
    source_url: str,
    source_name: str,
    category: str = "試合速報",
    source_type: str = "social_news",
) -> dict[str, object]:
    return rss_fetcher._resolve_rss_story_type_context_v2(
        title=title,
        summary=summary,
        category=category,
        daily_has_game=True,
        source_type=source_type,
        source_url=source_url,
        source_name=source_name,
    )


class May17ClassificationRegressionTests(unittest.TestCase):
    def assert_not_silent_skip(self, ctx: dict[str, object]) -> None:
        self.assertEqual(ctx["v2_skip_reason"], "")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_hochi_urata_quote_post_is_player_info(self):
        ctx = _resolve(
            title="巨人・浦田俊輔、いとこもアスリート 東京ドームに招待し猛打賞「打ちました！あざっす」",
            summary="ジムで合同トレも行っていた。",
            source_url="https://x.com/hochi_giants/status/2055748471664078998",
            source_name="スポーツ報知巨人班X",
        )
        self.assert_not_silent_skip(ctx)
        self.assertEqual(ctx["template_selector_v2_key"], "player_quote_short")
        self.assertEqual(ctx["category"], "選手情報")
        self.assertEqual(ctx["title_subtype"], "player")
        self.assertEqual(ctx["validator_subtype"], "social_news")

    def test_hochi_takanashi_relief_family_story_is_player_info(self):
        ctx = _resolve(
            title="巨人・高梨雄平がお父さんでライデルはおじさん！？絆の救援リレー",
            summary="チーム5連勝中、救援陣が22人でわずか2失点に抑えた。",
            source_url="https://x.com/hochi_giants/status/2055745869941473424",
            source_name="スポーツ報知巨人班X",
        )
        self.assert_not_silent_skip(ctx)
        self.assertEqual(ctx["template_selector_v2_key"], "x_short_player")
        self.assertEqual(ctx["category"], "選手情報")
        self.assertEqual(ctx["title_subtype"], "x_short_player")
        self.assertEqual(ctx["validator_subtype"], "social_news")

    def test_tospo_hashigami_coach_quote_is_manager_info_not_lineup(self):
        ctx = _resolve(
            title="【巨人】橋上コーチ 泉口友汰の今季初2番起用を説明「打撃の調子があんまりよくないので…」",
            summary="東スポWEBが橋上コーチの起用意図を伝えた。",
            source_url="https://x.com/tospo_giants/status/2055775973594042741",
            source_name="東スポ巨人担当X",
        )
        self.assert_not_silent_skip(ctx)
        self.assertIn(ctx["template_selector_v2_key"], {"manager_quote_short", "manager_short", "manager"})
        self.assertEqual(ctx["category"], "首脳陣")
        self.assertEqual(ctx["title_subtype"], "manager")
        self.assertNotEqual(ctx["title_subtype"], "lineup")

    def test_lineup_post_still_routes_to_lineup(self):
        ctx = _resolve(
            title="【巨人】本日のスタメン",
            summary="1番センター丸、2番ショート泉口、先発メンバーを発表。",
            source_url="https://x.com/hochi_giants/status/2055740000000000000",
            source_name="スポーツ報知巨人班X",
        )
        self.assert_not_silent_skip(ctx)
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertEqual(ctx["category"], "試合速報")
        self.assertEqual(ctx["title_subtype"], "lineup")

    def test_news_postgame_score_still_routes_to_score(self):
        ctx = _resolve(
            title="【巨人】3-2 ヤクルト 岡本和真が決勝3ラン",
            summary="巨人はヤクルトに3-2で勝利した。岡本和真が決勝3ランを放った。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605170000001.html",
            source_name="日刊スポーツ",
        )
        self.assert_not_silent_skip(ctx)
        self.assertIn(ctx["template_selector_v2_key"], {"postgame_strict", "postgame_score_short"})
        self.assertEqual(ctx["category"], "試合速報")
        self.assertEqual(ctx["title_subtype"], "postgame")

    def test_tospo_giants_x_is_registered_article_source(self):
        sources = json.loads((ROOT / "config" / "rss_sources.json").read_text(encoding="utf-8"))
        tospo_sources = [
            source
            for source in sources
            if source.get("url") == "https://rsshub-487178857517.asia-northeast1.run.app/twitter/user/tospo_giants"
        ]
        self.assertEqual(len(tospo_sources), 1)
        self.assertEqual(tospo_sources[0]["name"], "東スポ巨人担当X")
        self.assertIn("article_source", tospo_sources[0]["role"])
        self.assertTrue(
            rss_fetcher._is_trusted_social_url_or_name(
                "https://x.com/tospo_giants/status/2055775973594042741",
                "東スポ巨人担当X",
            )
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
