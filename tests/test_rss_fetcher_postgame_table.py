"""Bug reproduction: 報知 / スポニチ postgame articles render only a
prose body with no structured 試合結果 table.

Production sample id=66565 (2026-05-12, hochi.news 2軍 postgame):

  【巨人】"スミ１"の完封勝利で貯金６　又木鉄平が５回無失点で３勝目…２軍・ＤｅＮＡ戦
  body: 巨人２軍はＤｅＮＡに１―０で🏆 勝利した。

Phase 2D (NOMOTOKE-LINEUP-FROM-POSTGAME-001) adds:
- ``parse_postgame_facts`` that extracts score / winning pitcher /
  result-type / opponent from prose using regex patterns.
- 1軍 postgame can additionally use the existing
  ``source_yahoo_boxscore_extractor`` to render a full inning + box
  table (the A-fallback ships first; Yahoo box integration follows).
- 2軍 postgame always uses the A-fallback (Yahoo has no farm data).

Allowlist: 報知 + sponichi + 巨人公式X (reuses the hochi extractor
infrastructure for source / roster / opponent helpers).
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


# Production-shaped fixture (verified 2026-05-12 against id=66565).
HOCHI_FARM_POSTGAME_TITLE = (
    "【巨人】\"スミ１\"の完封勝利で貯金６　又木鉄平が５回無失点で３勝目…２軍・ＤｅＮＡ戦"
)
HOCHI_FARM_POSTGAME_SUMMARY = (
    "巨人２軍はＤｅＮＡに１―０で勝利した。"
    "又木鉄平が５回無失点で３勝目を挙げた。"
)

# Constructed 1軍 postgame fixture (similar shape, hochi-style).
HOCHI_FIRST_POSTGAME_TITLE = (
    "【巨人】戸郷翔征が８回１失点の力投で４勝目　巨人が中日に５―１で快勝"
)
HOCHI_FIRST_POSTGAME_SUMMARY = (
    "巨人は中日に５―１で勝利した。戸郷翔征が８回１失点で４勝目を挙げ、エースの仕事を果たした。"
)


class PostgameTableTests(unittest.TestCase):
    """Phase 2D bug reproduction. RED 前提 (実装前)。"""

    def _build(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        source_name: str,
        category: str,
        has_game: bool = True,
        source_type: str = "social_news",
    ) -> tuple[str, str]:
        patches = [
            patch.dict(os.environ, {"ENABLE_RSS_TEMPLATE_ROUTING_V2": "1"}),
            patch.object(
                rss_fetcher,
                "fetch_today_giants_lineup_stats_from_yahoo",
                return_value=[],
            ),
        ]
        for fn_name, return_value in (
            ("fetch_fan_reactions_from_yahoo", []),
            ("_fetch_fan_reactions_from_yahoo_safe", []),
            ("generate_article_with_gemini", ""),
            ("generate_article_with_grok", ("", [], "", "", "")),
        ):
            if hasattr(rss_fetcher, fn_name):
                patches.append(patch.object(rss_fetcher, fn_name, return_value=return_value))
        for p in patches:
            p.start()
        try:
            return rss_fetcher.build_news_block(
                title=title,
                summary=summary,
                url=url,
                source_name=source_name,
                category=category,
                has_game=has_game,
                source_type=source_type,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    def test_hochi_farm_postgame_emits_result_heading(self):
        """2軍 postgame で「試合結果」 heading 含む。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-farm.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        self.assertIn(
            "試合結果",
            blocks,
            "2軍 postgame で「試合結果」heading が出ない",
        )

    def test_hochi_farm_postgame_emits_table_marker(self):
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-farm.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        self.assertIn(
            "nomotoke-card-postgame-result",
            blocks,
            "2軍 postgame で table marker が出ない",
        )

    def test_hochi_farm_postgame_includes_score_and_winner(self):
        """body に スコア (1-0 or 1―0) と 勝利投手名 (又木鉄平 / 又木) 含む。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-farm.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        # スコア(1-0 or 1―0)
        self.assertTrue(
            "1-0" in blocks or "1―0" in blocks,
            "1-0 score が body に無い",
        )
        # 勝利投手名
        self.assertIn(
            "又木",
            blocks,
            "勝利投手 又木 が body に無い",
        )

    def test_hochi_first_team_postgame_emits_table(self):
        """1軍 postgame でも table 描画(Yahoo box 不在時の A-fallback)。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FIRST_POSTGAME_TITLE,
            summary=HOCHI_FIRST_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-first.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        self.assertIn(
            "nomotoke-card-postgame-result",
            blocks,
            "1軍 postgame で table が出ない",
        )
        self.assertIn("戸郷", blocks, "勝利投手 戸郷 が body に無い")

    def test_non_postgame_article_unchanged(self):
        """postgame でない記事(player comment 等)で発火しない。"""
        blocks, _ai_body = self._build(
            title="巨人・吉川尚輝が主将としての成長語る",
            summary="巨人の吉川尚輝が主将としての心構えを語った。",
            url="https://hochi.news/articles/20260512-OHT8888.html",
            source_name="スポーツ報知 巨人 tag",
            category="選手情報",
            source_type="news",
        )
        self.assertNotIn(
            "nomotoke-card-postgame-result",
            blocks,
            "non-postgame で postgame table が誤発火",
        )

    def test_non_hochi_postgame_source_unchanged(self):
        """non-hochi/sponichi/巨人公式X source では発火しない(allowlist gate)。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://example.com/articles/some.html",
            source_name="Yahoo!プロ野球",
            category="試合速報",
            source_type="news",
        )
        self.assertNotIn(
            "nomotoke-card-postgame-result",
            blocks,
            "non-allowlist source で postgame table が誤発火",
        )


if __name__ == "__main__":
    unittest.main()
