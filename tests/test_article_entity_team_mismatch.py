import unittest

from src.article_entity_team_mismatch import detect_other_team_player_in_giants_article


class ArticleEntityTeamMismatchTests(unittest.TestCase):
    def _assert_single_detection(self, detected, *, team_prefix, name, owning_team, position):
        self.assertEqual(len(detected), 1)
        self.assertEqual(
            detected[0],
            {
                "team_prefix": team_prefix,
                "name": name,
                "owning_team": owning_team,
                "position": position,
            },
        )

    def test_detects_other_team_player_after_giants_prefix(self):
        body_text = "巨人:則本昂大が登板"

        detected = detect_other_team_player_in_giants_article("", body_text)

        self._assert_single_detection(
            detected,
            team_prefix="巨人",
            name="則本昂大",
            owning_team="楽天",
            position=0,
        )

    def test_detects_other_team_player_after_giants_name_prefix(self):
        body_text = "ジャイアンツ:山本由伸"

        detected = detect_other_team_player_in_giants_article("", body_text)

        self._assert_single_detection(
            detected,
            team_prefix="ジャイアンツ",
            name="山本由伸",
            owning_team="ドジャース",
            position=0,
        )

    def test_detects_other_team_player_after_yomiuri_prefix(self):
        body_text = "読売:佐々木朗希"

        detected = detect_other_team_player_in_giants_article("", body_text)

        self._assert_single_detection(
            detected,
            team_prefix="読売",
            name="佐々木朗希",
            owning_team="ドジャース",
            position=0,
        )

    def test_ignores_names_outside_seed_roster(self):
        detected = detect_other_team_player_in_giants_article("", "巨人:岡本和真")

        self.assertEqual(detected, [])

    def test_suppresses_detection_for_opponent_context_markers(self):
        body_text = "巨人:則本昂大が先発し、巨人 vs 楽天で巨人打線がどう対応するかが焦点になる。"

        detected = detect_other_team_player_in_giants_article("", body_text)

        self.assertEqual(detected, [])

    def test_ignores_non_giants_team_prefix(self):
        detected = detect_other_team_player_in_giants_article("", "楽天・則本昂大が巨人を抑え")

        self.assertEqual(detected, [])

    def test_suppresses_detection_for_opponent_title_scope(self):
        detected = detect_other_team_player_in_giants_article("対楽天戦展望", "巨人:則本昂大との対戦が注目される。")

        self.assertEqual(detected, [])

    def test_ignores_name_without_giants_prefix(self):
        detected = detect_other_team_player_in_giants_article("", "則本氏が調整を続けた。")

        self.assertEqual(detected, [])
