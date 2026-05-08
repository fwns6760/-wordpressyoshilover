"""Tests for src/tools/digest_daily_morning.py."""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from src.tools.digest_daily_morning import (
    build_digest_body,
    build_digest_slug,
    build_digest_title,
)


class TestTitleSlug(unittest.TestCase):
    def test_title_includes_date_and_keywords(self):
        title = build_digest_title()
        # 当日日付が含まれる、巨人 / 順位 / 前日試合 / 翌日予定 keyword
        self.assertIn("朝まとめ", title)
        self.assertIn("巨人", title)
        self.assertRegex(title, r"\d+月\d+日")

    def test_title_uses_today_jp_argument(self):
        title = build_digest_title(today_jp="5月9日")
        self.assertIn("5月9日", title)

    def test_slug_format(self):
        slug = build_digest_slug()
        self.assertRegex(slug, r"^morning-digest-\d{4}-\d{2}-\d{2}$")


class TestBodyComposition(unittest.TestCase):
    def test_body_has_nomotoke_marker_for_enrichment_gate(self):
        body = build_digest_body()
        self.assertIn("nomotoke-card-divider", body)

    def test_body_has_lead_h3_and_source(self):
        body = build_digest_body()
        self.assertIn('class="nomotoke-lead"', body)
        self.assertIn("<h3>📋 事実カード</h3>", body)
        self.assertIn("<h3>🔗 出典記事</h3>", body)

    def test_body_has_cta_footer(self):
        body = build_digest_body()
        self.assertIn("nomotoke-card-footer", body)
        self.assertIn("💬 コメントする", body)

    def test_body_uses_today_jp_argument(self):
        body = build_digest_body(today_jp="5月9日")
        self.assertIn("5月9日", body)

    def test_body_includes_blocks_when_helpers_return_data(self):
        # Mock helpers to return non-empty
        from src.tools import digest_daily_morning as ddm

        with patch.object(
            ddm,
            "build_digest_body",
            wraps=ddm.build_digest_body,
        ):
            with patch(
                "src.tools.manual_intake._build_recent_games_block",
                return_value="<aside>recent</aside>",
            ), patch(
                "src.tools.manual_intake._build_next_game_block",
                return_value="<aside>next</aside>",
            ), patch(
                "src.tools.manual_intake._build_standings_block",
                return_value="<aside>standings</aside>",
            ), patch(
                "src.tools.manual_intake._build_x_embeds_block",
                return_value="<aside>x</aside>",
            ):
                body = build_digest_body()
                self.assertIn("<aside>recent</aside>", body)
                self.assertIn("<aside>next</aside>", body)
                self.assertIn("<aside>standings</aside>", body)
                self.assertIn("<aside>x</aside>", body)

    def test_body_skips_blocks_when_helpers_return_empty(self):
        with patch(
            "src.tools.manual_intake._build_recent_games_block",
            return_value="",
        ), patch(
            "src.tools.manual_intake._build_next_game_block",
            return_value="",
        ), patch(
            "src.tools.manual_intake._build_standings_block",
            return_value="",
        ), patch(
            "src.tools.manual_intake._build_x_embeds_block",
            return_value="",
        ):
            body = build_digest_body()
            # 空でも core structure (lead + h3 + footer) は維持
            self.assertIn("nomotoke-lead", body)
            self.assertIn("nomotoke-card-divider", body)


class TestSelectiveInclude(unittest.TestCase):
    def test_disable_individual_sections(self):
        with patch(
            "src.tools.manual_intake._build_recent_games_block",
            return_value="<aside>recent</aside>",
        ), patch(
            "src.tools.manual_intake._build_next_game_block",
            return_value="<aside>next</aside>",
        ), patch(
            "src.tools.manual_intake._build_standings_block",
            return_value="<aside>standings</aside>",
        ), patch(
            "src.tools.manual_intake._build_x_embeds_block",
            return_value="<aside>x</aside>",
        ):
            body = build_digest_body(
                include_recent_games=False,
                include_standings=False,
                include_next_game=False,
                include_x_embeds=False,
            )
            self.assertNotIn("<aside>recent</aside>", body)
            self.assertNotIn("<aside>next</aside>", body)
            self.assertNotIn("<aside>standings</aside>", body)
            self.assertNotIn("<aside>x</aside>", body)


class TestThinBodyValidation(unittest.TestCase):
    def test_body_passes_thin_body_validator(self):
        from src.thin_body_validator import is_thin_body

        body = build_digest_body()
        result = is_thin_body(body)
        self.assertFalse(result.is_thin, msg=f"unexpected: {result.reason}")


if __name__ == "__main__":
    unittest.main()
