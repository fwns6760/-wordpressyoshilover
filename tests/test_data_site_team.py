"""Tests for data/team page (Phase B 452)."""
from __future__ import annotations
import unittest
from src.data_site_template_team import (
    render_team_html, render_team_title, render_team_excerpt,
    render_ranking_html, render_ranking_title, render_ranking_excerpt,
)
from src.data_site_query import LeaderEntry


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

    def test_team_record_card(self) -> None:
        rec = {"wins": 26, "losses": 24, "draws": 2, "win_pct": 0.520,
               "runs_for": 157, "runs_against": 174, "run_diff": -17,
               "streak": 1, "streak_kind": "L", "home": (13, 14), "away": (13, 10)}
        html = render_team_html(self._rk(), team_record=rec)
        self.assertIn("巨人 チーム成績", html)
        self.assertIn("26-24-2", html)
        self.assertIn(".520", html)
        self.assertIn("1連敗", html)


class RankingTemplateTests(unittest.TestCase):
    """462: 選手ランキング HUB。"""

    def _leaders(self):
        return {
            "本塁打": [LeaderEntry("吉川尚輝", 5.0, "5本"), LeaderEntry("丸佳浩", 4.0, "4本")],
            "防御率": [LeaderEntry("戸郷翔征", 3.38, "3.38")],
        }

    def test_render_has_categories_and_pillar_link(self) -> None:
        html = render_ranking_html(self._leaders())
        self.assertIn("巨人 本塁打 ランキング", html)
        self.assertIn("巨人 防御率 ランキング", html)
        self.assertIn("吉川尚輝", html)
        self.assertIn("/data/yoshikawa-naoki/", html)

    def test_title_excerpt(self) -> None:
        self.assertIn("ランキング", render_ranking_title())
        self.assertIn("本塁打", render_ranking_excerpt(self._leaders()))

    def test_empty_safe(self) -> None:
        self.assertIn("データ準備中", render_ranking_html({}))


if __name__ == "__main__":
    unittest.main()
