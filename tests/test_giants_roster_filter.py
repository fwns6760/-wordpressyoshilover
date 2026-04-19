import unittest

from src import rss_fetcher


class GiantsRosterFilterTests(unittest.TestCase):
    def test_roster_file_has_minimum_entries(self):
        roster = rss_fetcher._load_giants_roster()
        self.assertGreaterEqual(len(roster), 30)

    def test_is_giants_related_accepts_roster_name_without_team_keyword(self):
        text = "戸郷翔征がブルペン入りし、次回登板へ向けて調整した。"
        self.assertTrue(rss_fetcher.is_giants_related(text))

    def test_is_giants_related_rejects_other_team_transfer_story(self):
        text = "阪神が戸郷翔征の獲得を検討、FA戦線の目玉として調査を進める。"
        self.assertFalse(rss_fetcher.is_giants_related(text))

    def test_matching_giants_roster_names_returns_expected_hit(self):
        hits = rss_fetcher._matching_giants_roster_names("阿部監督が打順の狙いを明かした。")
        self.assertIn("阿部慎之助", hits)


if __name__ == "__main__":
    unittest.main()
