"""Tests for data/team page (Phase B 452)."""
from __future__ import annotations
import unittest
from src.data_site_template_team import render_team_html, render_team_title, render_team_excerpt


class TeamTemplateTests(unittest.TestCase):
    def _rk(self):
        return {
            "打率": [("阪神", ".251", 1, False), ("巨人", ".231", 5, True)],
            "本塁打": [("巨人", "35本", 3, True)],
            "防御率": [("広島", "3.02", 1, False), ("巨人", "3.24", 4, True)],
        }

    def test_render(self) -> None:
        html = render_team_html(self._rk())
        self.assertIn("セ・リーグ 球団打率 ランキング", html)
        self.assertIn("巨人（巨人）", html)   # ハイライト行
        self.assertIn(".231", html)
        self.assertIn("セ・リーグ 球団防御率 ランキング", html)
        self.assertIn("球団成績", html)

    def test_excerpt_has_giants_ranks(self) -> None:
        ex = render_team_excerpt(self._rk())
        self.assertIn("打率セ5位", ex)
        self.assertIn("防御率セ4位", ex)

    def test_empty_safe(self) -> None:
        self.assertIn("球団成績", render_team_html({}))


if __name__ == "__main__":
    unittest.main()
