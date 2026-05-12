"""Bug reproduction: 報知 starter-rotation tweets/articles (arrow-chain
form `<P1>→<P2>→<P3>`) do not render a structured rotation table.

Production sample id=66418 (2026-05-12):

  巨人が先発ローテ再編　１５日からのＤｅＮＡ３連戦は井上温大→ウィットリー→竹丸和幸
  フレッシュ布陣で貯金アップ

The body shows the rotation in prose only (eyecatch + lead + source
excerpt), with no structured table showing the order × pitcher pairing.
Phase 2C (NOMOTOKE-LINEUP-FROM-STARTER-ROTATION-001) adds a small
``parse_starter_rotation`` extractor that picks the arrow-chain out of
title / summary, validates each name against ``config/giants_roster.json``,
and renders a 「📋 先発ローテ予告」 mini-table.

Source allowlist: 報知 (hochi.news / 報知系X) + sponichi + 巨人公式X
(via the existing hochi+emoji infrastructure).
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


# Production-shaped fixture (verified 2026-05-12 against id=66418).
STARTER_ROTATION_TITLE = (
    "巨人が先発ローテ再編　１５日からのＤｅＮＡ３連戦は"
    "井上温大→ウィットリー→竹丸和幸　フレッシュ布陣で貯金アップ"
)
STARTER_ROTATION_SUMMARY = (
    "巨人が週末の先発ローテを再編したことが１１日、分かった。"
    "井上温大→ウィットリー→竹丸和幸の順で１５日からのＤｅＮＡ３連戦に臨む。"
)


class StarterRotationTableTests(unittest.TestCase):
    """Phase 2C bug reproduction. RED 前提 (実装前)。"""

    def _build(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        source_name: str,
        category: str,
        has_game: bool = True,
        source_type: str = "news",
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

    def test_starter_rotation_emits_rotation_heading(self):
        """報知 starter rotation 記事 → body に「先発ローテ」 heading 含む。"""
        blocks, _ai_body = self._build(
            title=STARTER_ROTATION_TITLE,
            summary=STARTER_ROTATION_SUMMARY,
            url="https://hochi.news/articles/20260511-OHT1T51280.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
        )
        self.assertIn(
            "先発ローテ",
            blocks,
            "starter rotation 記事で「先発ローテ」 heading が出ない",
        )

    def test_starter_rotation_emits_rotation_table_marker(self):
        """body に rotation table marker(`nomotoke-card-starter-rotation`)が含まれる。"""
        blocks, _ai_body = self._build(
            title=STARTER_ROTATION_TITLE,
            summary=STARTER_ROTATION_SUMMARY,
            url="https://hochi.news/articles/20260511-OHT1T51280.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
        )
        self.assertIn(
            "nomotoke-card-starter-rotation",
            blocks,
            "rotation table marker が body に無い",
        )

    def test_starter_rotation_includes_all_pitcher_names(self):
        """body に rotation の全投手名が含まれる(roster 照合済)。"""
        blocks, _ai_body = self._build(
            title=STARTER_ROTATION_TITLE,
            summary=STARTER_ROTATION_SUMMARY,
            url="https://hochi.news/articles/20260511-OHT1T51280.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
        )
        for name in ("井上温大", "ウィットリー", "竹丸和幸"):
            self.assertIn(name, blocks, f"pitcher name '{name}' missing from body")

    def test_no_arrow_chain_unchanged(self):
        """arrow chain 無い記事(普通の選手記事)では rotation table 発火しない。"""
        title = "巨人・吉川尚輝が逆転打 主将らしい一打で延長制す"
        summary = "巨人の吉川尚輝が延長戦で逆転打を放った。主将としての存在感を示した一打だった。"
        blocks, _ai_body = self._build(
            title=title,
            summary=summary,
            url="https://hochi.news/articles/20260511-OHT9999999.html",
            source_name="スポーツ報知 巨人 tag",
            category="選手情報",
        )
        self.assertNotIn(
            "nomotoke-card-starter-rotation",
            blocks,
            "arrow chain 無い記事で rotation table が誤発火",
        )

    def test_arrow_chain_without_giants_pitchers_unchanged(self):
        """arrow chain あるが 巨人 roster 該当者 0 の記事 → rotation table 不発火。"""
        title = "セ・リーグ予告先発　中日：高橋宏斗→大野雄大→金丸夢斗"
        summary = title
        blocks, _ai_body = self._build(
            title=title,
            summary=summary,
            url="https://hochi.news/articles/20260511-OHT-other.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
        )
        # 巨人 roster に居ない投手のみの arrow chain は発火しない
        self.assertNotIn(
            "nomotoke-card-starter-rotation",
            blocks,
            "巨人 roster 0 件マッチの arrow chain で誤発火",
        )


if __name__ == "__main__":
    unittest.main()
