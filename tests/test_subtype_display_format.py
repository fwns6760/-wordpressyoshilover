"""Unit tests for subtype display format helpers — ticket 410 Phase 1.

Phase 1: builder helpers only (badge HTML + 出典帯 HTML)。
Phase 2 で draft 生成 path に inject する予定 (本 test では呼び出し path は test しない)。

See: docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md §4.6
"""

from __future__ import annotations

import unittest

from src.subtype_display_format import (
    SUPPORTED_SUBTYPES,
    build_source_attribution_block,
    build_subtype_badge_html,
    is_supported_subtype,
)


class BuildSubtypeBadgeHtmlTests(unittest.TestCase):
    def test_ob_badge(self):
        html = build_subtype_badge_html("ob")
        self.assertIsNotNone(html)
        assert html is not None
        self.assertIn('nomotoke-subtype-badge--ob', html)
        self.assertIn("元巨人", html)

    def test_farm2_result_badge(self):
        html = build_subtype_badge_html("farm2_result")
        self.assertIsNotNone(html)
        assert html is not None
        self.assertIn('nomotoke-subtype-badge--farm2', html)
        self.assertIn("2軍速報", html)

    def test_farm2_lineup_badge(self):
        html = build_subtype_badge_html("farm2_lineup")
        self.assertIsNotNone(html)
        assert html is not None
        self.assertIn('nomotoke-subtype-badge--farm2', html)
        self.assertIn("2軍スタメン", html)

    def test_farm3_practice_badge(self):
        html = build_subtype_badge_html("farm3_practice")
        self.assertIsNotNone(html)
        assert html is not None
        self.assertIn('nomotoke-subtype-badge--farm3', html)
        self.assertIn("3軍練習", html)

    def test_farm3_player_badge(self):
        html = build_subtype_badge_html("farm3_player")
        self.assertIsNotNone(html)
        assert html is not None
        self.assertIn('nomotoke-subtype-badge--farm3', html)
        self.assertIn("3軍選手", html)

    def test_non_supported_subtype_returns_none(self):
        self.assertIsNone(build_subtype_badge_html("postgame"))
        self.assertIsNone(build_subtype_badge_html("lineup"))
        self.assertIsNone(build_subtype_badge_html("manager"))
        self.assertIsNone(build_subtype_badge_html("farm"))  # 旧 farm は対象外
        self.assertIsNone(build_subtype_badge_html(""))
        self.assertIsNone(build_subtype_badge_html("unknown_subtype"))


class BuildSourceAttributionBlockTests(unittest.TestCase):
    def test_ob_without_current_team(self):
        html = build_source_attribution_block(
            "ob",
            "https://example.com/article",
            "スポーツ報知",
        )
        self.assertIn('nomotoke-source-attribution--ob', html)
        self.assertIn("元巨人", html)
        self.assertNotIn("現所属", html)
        self.assertIn("出典: スポーツ報知", html)
        self.assertIn('href="https://example.com/article"', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)

    def test_ob_with_current_team(self):
        html = build_source_attribution_block(
            "ob",
            "https://example.com/article",
            "スポーツ報知",
            ob_current_team="解説者",
        )
        self.assertIn("元巨人 / 現所属 解説者", html)

    def test_farm2_result_attribution(self):
        html = build_source_attribution_block(
            "farm2_result",
            "https://example.com/farm-result",
            "イースタン公式",
        )
        self.assertIn('nomotoke-source-attribution--farm2', html)
        self.assertIn("2軍 イースタン", html)
        self.assertIn("出典: イースタン公式", html)

    def test_farm2_lineup_attribution(self):
        html = build_source_attribution_block(
            "farm2_lineup",
            "https://example.com/farm-lineup",
            "巨人公式",
        )
        self.assertIn('nomotoke-source-attribution--farm2', html)
        self.assertIn("2軍 イースタン", html)

    def test_farm3_practice_attribution(self):
        html = build_source_attribution_block(
            "farm3_practice",
            "https://example.com/farm3",
            "巨人広報",
        )
        self.assertIn('nomotoke-source-attribution--farm3', html)
        self.assertIn("3軍 (※非公式)", html)
        self.assertIn("出典: 巨人広報", html)

    def test_farm3_player_attribution(self):
        html = build_source_attribution_block(
            "farm3_player",
            "",
            "現地リポート",
        )
        self.assertIn('nomotoke-source-attribution--farm3', html)
        self.assertIn("3軍 (※非公式)", html)
        # URL 無しなら span (link 化しない)
        self.assertIn("nomotoke-source-attribution__source", html)
        self.assertNotIn('href=', html)

    def test_non_supported_subtype_returns_empty_string(self):
        self.assertEqual(build_source_attribution_block("postgame", "u", "n"), "")
        self.assertEqual(build_source_attribution_block("lineup", "u", "n"), "")
        self.assertEqual(build_source_attribution_block("farm", "u", "n"), "")
        self.assertEqual(build_source_attribution_block("", "u", "n"), "")

    def test_html_escaping_prevents_injection(self):
        html = build_source_attribution_block(
            "ob",
            'javascript:alert(1)"onclick="x',
            "<script>alert(1)</script>",
        )
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


class IsSupportedSubtypeTests(unittest.TestCase):
    def test_supported_subtypes_include_5_targets(self):
        self.assertEqual(
            SUPPORTED_SUBTYPES,
            frozenset({"ob", "farm2_result", "farm2_lineup", "farm3_practice", "farm3_player"}),
        )

    def test_is_supported_subtype_positive(self):
        self.assertTrue(is_supported_subtype("ob"))
        self.assertTrue(is_supported_subtype("farm2_result"))
        self.assertTrue(is_supported_subtype("farm3_practice"))

    def test_is_supported_subtype_negative(self):
        self.assertFalse(is_supported_subtype("postgame"))
        self.assertFalse(is_supported_subtype("farm"))
        self.assertFalse(is_supported_subtype(""))


if __name__ == "__main__":
    unittest.main()
