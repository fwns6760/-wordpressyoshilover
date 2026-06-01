"""Tests for data/leaders ranking page (Phase B 452)."""
from __future__ import annotations
import unittest
from src.data_site_query import LeaderEntry
from src.data_site_template_leaders import render_leaders_html, render_leaders_title, render_leaders_excerpt


class LeadersTemplateTests(unittest.TestCase):
    def _leaders(self):
        return {
            "本塁打": [LeaderEntry("岡本 和真", 12, "12本"), LeaderEntry("キャベッジ", 9, "9本")],
            "防御率": [LeaderEntry("田和 廉", 1.40, "1.40")],
        }

    def test_render_has_ranking_and_names(self) -> None:
        html = render_leaders_html(self._leaders())
        self.assertIn("巨人 本塁打 ランキング", html)
        self.assertIn("岡本和真", html)   # 空白除去表示
        self.assertIn("12本", html)
        self.assertIn("巨人 防御率 ランキング", html)
        self.assertIn("選手別ランキング", html)

    def test_title_excerpt(self) -> None:
        self.assertIn("ランキング", render_leaders_title())
        self.assertIn("本塁打12本", render_leaders_excerpt(self._leaders()))

    def test_empty_safe(self) -> None:
        html = render_leaders_html({})
        self.assertIn("選手別ランキング", html)  # 空でも崩れない


if __name__ == "__main__":
    unittest.main()
