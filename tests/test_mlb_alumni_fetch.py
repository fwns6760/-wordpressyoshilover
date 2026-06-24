"""mlb_alumni_fetch の fact line 整形 (network 不要の純粋関数) test。

2026-06-24: 巨人発 MLB OB (岡本和真 / 菅野智之) の MLB 成績を X 投稿の
verified fact line に供給する配線のための整形関数。
"""

import unittest

from src import mlb_alumni_fetch as mlb


class FormatMlbAlumniFactLineTests(unittest.TestCase):
    def test_hitting_entry_includes_mlb_tag_and_stats(self):
        entry = {
            "name": "岡本和真",
            "group": "hitting",
            "team": "ドジャース",
            "season": {"games": 70, "avg": ".291", "hr": 18, "rbi": 52, "ops": ".910", "hits": 80},
            "last_game": {"date": "2026-06-23", "opponent": "パドレス", "ab": 4, "hits": 2, "hr": 1, "rbi": 3},
        }
        line = mlb.format_mlb_alumni_fact_line(entry)
        self.assertIn("岡本和真", line)
        self.assertIn("MLB ドジャース", line)
        self.assertIn("打率.291", line)
        self.assertIn("18本塁打", line)
        self.assertIn("OPS.910", line)
        # 直近試合
        self.assertIn("直近(2026-06-23 対パドレス)", line)
        self.assertIn("4打数2安打", line)

    def test_pitching_entry_includes_era_and_record(self):
        entry = {
            "name": "菅野智之",
            "group": "pitching",
            "team": "オリオールズ",
            "season": {"games": 15, "wins": 8, "losses": 4, "era": "3.21", "ip": "92.1", "so": 70},
            "last_game": {"date": "2026-06-20", "opponent": "ヤンキース", "ip": "6.0", "runs": 2, "so": 7},
        }
        line = mlb.format_mlb_alumni_fact_line(entry)
        self.assertIn("菅野智之", line)
        self.assertIn("MLB オリオールズ", line)
        self.assertIn("8勝4敗", line)
        self.assertIn("防御率3.21", line)
        self.assertIn("92.1回", line)
        self.assertIn("70奪三振", line)
        self.assertIn("直近(2026-06-20 対ヤンキース)", line)

    def test_empty_or_no_season_returns_blank(self):
        self.assertEqual(mlb.format_mlb_alumni_fact_line({}), "")
        self.assertEqual(mlb.format_mlb_alumni_fact_line({"name": "岡本和真", "group": "hitting"}), "")

    def test_no_last_game_only_season_line(self):
        entry = {
            "name": "岡本和真", "group": "hitting", "team": "ドジャース",
            "season": {"games": 70, "avg": ".291", "hr": 18, "rbi": 52, "ops": ".910"},
        }
        line = mlb.format_mlb_alumni_fact_line(entry)
        self.assertEqual(len(line.splitlines()), 1)
        self.assertIn("今季70試合", line)


class MlbAlumniFactLineLookupTests(unittest.TestCase):
    DATA = {
        "season": 2026,
        "players": [
            {"name": "岡本和真", "group": "hitting", "team": "ドジャース",
             "season": {"games": 70, "avg": ".291", "hr": 18, "rbi": 52, "ops": ".910"}},
            {"name": "菅野智之", "group": "pitching", "team": "オリオールズ",
             "season": {"games": 15, "wins": 8, "losses": 4, "era": "3.21", "ip": "92.1", "so": 70}},
        ],
    }

    def test_lookup_matches_whitespace_insensitive(self):
        self.assertIn("ドジャース", mlb.mlb_alumni_fact_line("岡本 和真", self.DATA))
        self.assertIn("オリオールズ", mlb.mlb_alumni_fact_line("菅野智之", self.DATA))

    def test_unknown_player_returns_blank(self):
        self.assertEqual(mlb.mlb_alumni_fact_line("戸郷翔征", self.DATA), "")

    def test_empty_data_returns_blank(self):
        self.assertEqual(mlb.mlb_alumni_fact_line("岡本和真", {}), "")
        self.assertEqual(mlb.mlb_alumni_fact_line("", self.DATA), "")


if __name__ == "__main__":
    unittest.main()
