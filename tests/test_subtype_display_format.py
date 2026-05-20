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
    maybe_prepend_subtype_display,
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


class MaybePrependSubtypeDisplayTests(unittest.TestCase):
    """Phase 2 wire-in helper: badge prepend + 出典帯 append + idempotent."""

    def test_ob_subtype_prepends_badge_and_appends_attribution(self):
        result = maybe_prepend_subtype_display(
            "<p>本文 here</p>",
            "ob",
            source_url="https://example.com/ob-article",
            source_name="スポーツ報知",
        )
        # badge は先頭付近
        self.assertIn('nomotoke-subtype-badge--ob', result)
        self.assertIn("元巨人", result)
        # 出典帯 は末尾付近
        self.assertIn('nomotoke-source-attribution--ob', result)
        # 既存本文 維持
        self.assertIn("<p>本文 here</p>", result)
        # 順番: badge → body → attribution
        badge_idx = result.index('nomotoke-subtype-badge--ob')
        body_idx = result.index("<p>本文 here</p>")
        attribution_idx = result.index('nomotoke-source-attribution--ob')
        self.assertLess(badge_idx, body_idx)
        self.assertLess(body_idx, attribution_idx)

    def test_farm3_practice_prepends_and_appends(self):
        result = maybe_prepend_subtype_display(
            "<p>3軍 練習試合の様子</p>",
            "farm3_practice",
            source_url="https://example.com/farm3",
            source_name="巨人広報",
        )
        self.assertIn("3軍練習", result)  # badge
        self.assertIn("3軍 (※非公式)", result)  # 出典帯

    def test_non_supported_subtype_returns_body_unchanged(self):
        body = "<p>postgame 試合結果</p>"
        result = maybe_prepend_subtype_display(
            body,
            "postgame",
            source_url="https://example.com/postgame",
            source_name="スポニチ",
        )
        self.assertEqual(result, body)  # 完全 byte-for-byte 一致

    def test_empty_subtype_returns_body_unchanged(self):
        body = "<p>一般記事</p>"
        result = maybe_prepend_subtype_display(body, "")
        self.assertEqual(result, body)

    def test_empty_body_supported_subtype_still_adds_badge_attribution(self):
        result = maybe_prepend_subtype_display(
            "",
            "ob",
            source_url="https://example.com/u",
            source_name="出典 X",
        )
        # 空 body でも badge + 出典帯 は追加される
        self.assertIn("元巨人", result)
        self.assertIn("出典: 出典 X", result)

    def test_idempotent_double_call_does_not_duplicate(self):
        once = maybe_prepend_subtype_display(
            "<p>OB voice</p>",
            "ob",
            source_url="https://example.com/u",
            source_name="X",
        )
        twice = maybe_prepend_subtype_display(
            once,
            "ob",
            source_url="https://example.com/u",
            source_name="X",
        )
        # 2 回呼んでも badge / 出典帯 が 1 個ずつ
        self.assertEqual(twice.count('nomotoke-subtype-badge--ob'), 1)
        self.assertEqual(twice.count('nomotoke-source-attribution--ob'), 1)

    def test_ob_with_current_team_renders_combined_label(self):
        result = maybe_prepend_subtype_display(
            "<p>OB 解説</p>",
            "ob",
            source_url="https://example.com/u",
            source_name="X",
            ob_current_team="解説者",
        )
        self.assertIn("元巨人 / 現所属 解説者", result)

    def test_farm2_result_attribution_label(self):
        result = maybe_prepend_subtype_display(
            "<p>イースタン公式戦結果</p>",
            "farm2_result",
            source_url="https://example.com/farm2",
            source_name="イースタン公式",
        )
        self.assertIn("2軍速報", result)
        self.assertIn("2軍 イースタン", result)


if __name__ == "__main__":
    unittest.main()
