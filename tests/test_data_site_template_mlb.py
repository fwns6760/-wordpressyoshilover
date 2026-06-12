"""巨人発メジャーリーガー page (data/mlb) の template / fetch 整形 test。"""

from __future__ import annotations

import unittest

from src.data_site_template_mlb import (
    render_mlb_excerpt,
    render_mlb_html,
    render_mlb_title,
)
from src.data_site_template_mlb_player import (
    render_mlb_player_excerpt,
    render_mlb_player_html,
    render_mlb_player_title,
)
from src.mlb_alumni_fetch import _extract_player, pa_event_ja, team_ja


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


class RenderMlbPlayerTests(unittest.TestCase):
    def _hitter_detail(self):
        return {
            "name": "岡本和真", "slug": "okamoto-kazuma", "group": "hitting",
            "team": "ブルージェイズ", "debut": "2026-03-26",
            "seasons": [{
                "season": 2026,
                "summary": {"games": 67, "avg": ".230", "hr": 13, "rbi": 38,
                            "ops": ".731", "hits": 56},
                "games": [
                    {"date": "2026-06-10", "opponent": "フィリーズ", "home": True,
                     "ab": 3, "hits": 0, "hr": 0, "rbi": 1},
                    {"date": "2026-06-09", "opponent": "フィリーズ", "home": True,
                     "ab": 4, "hits": 2, "hr": 1, "rbi": 2},
                ],
            }],
            "pa_log": {"date": "2026-06-10", "opponent": "フィリーズ",
                       "events": ["三振", "四球", "犠飛"]},
        }

    def _pitcher_detail(self):
        return {
            "name": "菅野智之", "slug": "sugano-tomoyuki", "group": "pitching",
            "team": "ロッキーズ", "debut": "2025-03-30",
            "seasons": [
                {"season": 2026,
                 "summary": {"games": 13, "wins": 6, "losses": 4, "era": "4.08",
                             "ip": "68.1", "so": 39},
                 "games": [{"date": "2026-06-09", "opponent": "カブス", "home": True,
                            "ip": "5.0", "hits": 6, "runs": 3, "so": 3, "bb": 1,
                            "pitches": 88, "decision": "－"}]},
                {"season": 2025,
                 "summary": {"games": 30, "wins": 10, "losses": 10, "era": "4.64",
                             "ip": "157.0", "so": 109},
                 "games": [{"date": "2025-09-27", "opponent": "ヤンキース", "home": False,
                            "ip": "4.1", "hits": 5, "runs": 4, "so": 3, "bb": 0,
                            "pitches": 73, "decision": "●"}]},
            ],
        }

    def test_render_hitter_page_with_pa_log(self) -> None:
        html = render_mlb_player_html(self._hitter_detail())
        self.assertIn("岡本和真 メジャー全成績", html)
        self.assertIn("第1打席", html)
        self.assertIn("三振", html)
        self.assertIn("犠飛", html)
        self.assertIn("2026年", html)
        self.assertIn("6/9", html)
        self.assertIn("2026年メジャーデビュー", html)

    def test_render_pitcher_page_all_seasons(self) -> None:
        html = render_mlb_player_html(self._pitcher_detail())
        self.assertIn("菅野智之 メジャー全成績", html)
        self.assertIn("2026年", html)
        self.assertIn("2025年", html)
        self.assertIn("ヤンキース", html)
        self.assertIn("88球", html)
        self.assertIn("●", html)

    def test_player_title_and_excerpt(self) -> None:
        self.assertIn("岡本和真", render_mlb_player_title(self._hitter_detail()))
        self.assertIn("全2試合", render_mlb_player_excerpt(self._hitter_detail()))

    def test_pa_event_ja_mapping(self) -> None:
        self.assertEqual(pa_event_ja("home_run"), "本塁打")
        self.assertEqual(pa_event_ja("strikeout"), "三振")
        self.assertEqual(pa_event_ja("unknown_evt"), "unknown_evt")


if __name__ == "__main__":
    unittest.main()
