"""Tests for data/team page (Phase B 452)."""
from __future__ import annotations
import unittest
from src.data_site_template_team import (
    render_team_html, render_team_title, render_team_excerpt,
    render_ranking_html, render_ranking_title, render_ranking_excerpt,
    render_batting_ranking_html, render_batting_ranking_title, render_batting_ranking_excerpt,
    render_pitching_ranking_html, render_pitching_ranking_title, render_pitching_ranking_excerpt,
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
            "打率": [LeaderEntry("吉川尚輝", 0.312, ".312")],
            "本塁打": [LeaderEntry("吉川尚輝", 5.0, "5本"), LeaderEntry("丸佳浩", 4.0, "4本")],
            "打点": [LeaderEntry("丸佳浩", 21.0, "21")],
            "勝利": [LeaderEntry("戸郷翔征", 4.0, "4")],
            "奪三振": [LeaderEntry("戸郷翔征", 48.0, "48")],
            "防御率": [LeaderEntry("戸郷翔征", 3.38, "3.38")],
        }

    def _career(self):
        return {
            "通算安打": [LeaderEntry("坂本勇人", 2400.0, "2400")],
            "通算本塁打": [LeaderEntry("坂本勇人", 300.0, "300本")],
            "通算勝利": [LeaderEntry("田中将大", 197.0, "197勝")],
            "通算奪三振": [LeaderEntry("田中将大", 1600.0, "1600")],
        }

    def _alltime(self):
        return {
            "本塁打": [LeaderEntry("王貞治", 868.0, "868本")],
            "安打": [LeaderEntry("張本勲", 3085.0, "3085安打")],
            "勝利": [LeaderEntry("金田正一", 400.0, "400勝")],
            "奪三振": [LeaderEntry("金田正一", 4490.0, "4490奪三振")],
        }

    def test_render_has_categories_and_pillar_link(self) -> None:
        html = render_ranking_html(self._leaders())
        self.assertIn("打撃成績ランキング", html)
        self.assertIn("投手成績ランキング", html)
        self.assertIn("https://yoshilover.com/data/batting-ranking", html)
        self.assertIn("https://yoshilover.com/data/pitching-ranking", html)
        self.assertNotIn("巨人 本塁打 ランキング", html)
        self.assertNotIn("巨人 防御率 ランキング", html)

    def test_title_excerpt(self) -> None:
        self.assertIn("ランキング", render_ranking_title())
        self.assertIn("打撃成績ランキング", render_ranking_excerpt(self._leaders()))

    def test_empty_safe(self) -> None:
        self.assertIn("打撃成績ランキング", render_ranking_html({}))

    def test_batting_page_only_has_batting_rankings(self) -> None:
        html = render_batting_ranking_html(self._leaders(), self._career(), self._alltime())
        self.assertIn("巨人 打撃成績ランキング", html)
        self.assertIn("巨人 打率 ランキング", html)
        self.assertIn("巨人 本塁打 ランキング", html)
        self.assertIn("通算安打", html)
        self.assertIn("王貞治", html)
        self.assertIn("https://yoshilover.com/data/pitching-ranking", html)
        self.assertNotIn("巨人 防御率 ランキング", html)
        self.assertNotIn("巨人 勝利 ランキング", html)
        self.assertNotIn("通算勝利", html)
        self.assertNotIn("金田正一", html)

    def test_pitching_page_only_has_pitching_rankings(self) -> None:
        html = render_pitching_ranking_html(self._leaders(), self._career(), self._alltime())
        self.assertIn("巨人 投手成績ランキング", html)
        self.assertIn("巨人 防御率 ランキング", html)
        self.assertIn("巨人 勝利 ランキング", html)
        self.assertIn("通算勝利", html)
        self.assertIn("金田正一", html)
        self.assertIn("https://yoshilover.com/data/batting-ranking", html)
        self.assertNotIn("巨人 本塁打 ランキング", html)
        self.assertNotIn("巨人 打点 ランキング", html)
        self.assertNotIn("通算安打", html)
        self.assertNotIn("王貞治", html)

    def test_split_titles_and_excerpts(self) -> None:
        self.assertIn("打撃成績ランキング", render_batting_ranking_title())
        self.assertIn("投手成績ランキング", render_pitching_ranking_title())
        self.assertIn("投手成績とは別ページ", render_batting_ranking_excerpt(self._leaders()))
        self.assertIn("打撃成績とは別ページ", render_pitching_ranking_excerpt(self._leaders()))


class StandingsCardTests(unittest.TestCase):
    """459/C セ・リーグ順位表カード。"""

    def _st(self):
        return [
            {"rank": 1, "team": "ヤクルト", "g": "52", "w": "31", "l": "20", "t": "1", "pct": ".608", "gb": "--", "is_giants": False},
            {"rank": 3, "team": "巨人", "g": "52", "w": "27", "l": "25", "t": "0", "pct": ".519", "gb": "4.5", "is_giants": True},
        ]

    def test_render_standings(self) -> None:
        html = render_team_html(TeamTemplateTests()._rk(), standings=self._st())
        self.assertIn("セ・リーグ順位表", html)
        self.assertIn("巨人", html)
        self.assertIn(".519", html)
        self.assertIn("4.5", html)
        self.assertIn("NPB公式", html)

    def test_empty_safe(self) -> None:
        # standings 無しでも従来通り
        self.assertIn("球団成績", render_team_html(TeamTemplateTests()._rk(), standings=[]))


if __name__ == "__main__":
    unittest.main()
