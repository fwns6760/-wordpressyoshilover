"""巨人発メジャーリーガー page (data/mlb) の template / fetch 整形 test。"""

from __future__ import annotations

import unittest

from src.data_site_template_mlb import (
    render_mlb_excerpt,
    render_mlb_html,
    render_mlb_title,
)
from src.mlb_alumni_fetch import _extract_player, team_ja


def _hitting_payload():
    return {
        "stats": [
            {
                "type": {"displayName": "season"},
                "splits": [{"stat": {
                    "gamesPlayed": 67, "avg": ".230", "homeRuns": 13,
                    "rbi": 38, "ops": ".731", "hits": 56,
                }}],
            },
            {
                "type": {"displayName": "gameLog"},
                "splits": [{
                    "date": "2026-06-10",
                    "opponent": {"name": "Philadelphia Phillies"},
                    "stat": {"atBats": 3, "hits": 0, "homeRuns": 0, "rbi": 1},
                }],
            },
        ]
    }


class ExtractPlayerTests(unittest.TestCase):
    def test_extract_hitting_entry(self) -> None:
        info = {"people": [{"currentTeam": {"name": "Toronto Blue Jays"}}]}
        entry = _extract_player(
            _hitting_payload(), info, {"name": "岡本和真", "group": "hitting"}
        )
        self.assertEqual(entry["name"], "岡本和真")
        self.assertEqual(entry["team"], "ブルージェイズ")
        self.assertEqual(entry["season"]["hr"], 13)
        self.assertEqual(entry["last_game"]["opponent"], "フィリーズ")
        self.assertEqual(entry["last_game"]["rbi"], 1)

    def test_extract_returns_none_without_season(self) -> None:
        entry = _extract_player({"stats": []}, {}, {"name": "岡本和真", "group": "hitting"})
        self.assertIsNone(entry)

    def test_team_ja_falls_back_to_raw(self) -> None:
        self.assertEqual(team_ja("Colorado Rockies"), "ロッキーズ")
        self.assertEqual(team_ja("Unknown Team"), "Unknown Team")


class RenderMlbTests(unittest.TestCase):
    def _data(self):
        return {
            "season": 2026,
            "as_of": "2026-06-10",
            "players": [
                {
                    "name": "岡本和真", "group": "hitting", "team": "ブルージェイズ",
                    "season": {"games": 67, "avg": ".230", "hr": 13, "rbi": 38,
                               "ops": ".731", "hits": 56},
                    "last_game": {"date": "2026-06-10", "opponent": "フィリーズ",
                                  "ab": 3, "hits": 0, "hr": 0, "rbi": 1},
                },
                {
                    "name": "菅野智之", "group": "pitching", "team": "ロッキーズ",
                    "season": {"games": 13, "wins": 6, "losses": 4, "era": "4.08",
                               "ip": "68.1", "so": 39},
                    "last_game": {"date": "2026-06-09", "opponent": "カブス",
                                  "ip": "5.0", "runs": 3, "so": 3, "hits": 6},
                },
            ],
        }

    def test_render_mlb_html_shows_both_players(self) -> None:
        html = render_mlb_html(self._data())
        self.assertIn("巨人発メジャーリーガー", html)
        self.assertIn("岡本和真", html)
        self.assertIn("ブルージェイズ", html)
        self.assertIn("13本", html)
        self.assertIn("菅野智之", html)
        self.assertIn("6勝4敗", html)
        self.assertIn("現地6/10 vs フィリーズ", html)
        self.assertIn("3打数0安打1打点", html)
        self.assertIn("5.0回6被安打3失点3奪三振", html)
        self.assertIn("現地6/10 試合終了時点", html)
        self.assertIn('"@type": "BreadcrumbList"', html)

    def test_render_mlb_html_empty(self) -> None:
        html = render_mlb_html({"players": [], "as_of": ""})
        self.assertIn("集計中", html)

    def test_title_and_excerpt(self) -> None:
        self.assertIn("岡本和真・菅野智之", render_mlb_title())
        self.assertIn("岡本和真・菅野智之", render_mlb_excerpt(self._data()))


if __name__ == "__main__":
    unittest.main()
