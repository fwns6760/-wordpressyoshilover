import unittest

from src import rss_fetcher


class GenericTitleRepairActionLossTests(unittest.TestCase):
    """Issue #17 / 338-QA: 「無失点」を「失点」と誤判定しないこと。"""

    def test_muiten_does_not_match_loss_label(self):
        result = rss_fetcher._generic_title_repair_action(
            "則本昂大が好投",
            "則本昂大が7回無失点で勝利投手の権利を得た",
        )
        self.assertNotEqual(result, "失点")

    def test_quantified_loss_matches_loss_label(self):
        result = rss_fetcher._generic_title_repair_action(
            "巨人、則本昂大",
            "則本昂大が7回1失点でQS達成",
        )
        self.assertEqual(result, "失点")

    def test_zero_loss_alone_does_not_match(self):
        result = rss_fetcher._generic_title_repair_action(
            "巨人勝利",
            "救援陣が無失点リレーで逃げ切った",
        )
        self.assertNotEqual(result, "失点")

    def test_quantified_loss_in_title_matches(self):
        result = rss_fetcher._generic_title_repair_action(
            "則本昂大、5回3失点",
            "巨人の則本昂大は5回3失点で降板",
        )
        self.assertEqual(result, "失点")

    def test_homerun_label_still_works(self):
        result = rss_fetcher._generic_title_repair_action(
            "岡本和真が一発",
            "岡本和真がレフトスタンドへ本塁打を放った",
        )
        self.assertEqual(result, "本塁打")

    def test_muiten_falls_through_to_win_label(self):
        result = rss_fetcher._generic_title_repair_action(
            "巨人、則本昂大",
            "則本昂大が7回無失点で白星を挙げた",
        )
        self.assertEqual(result, "勝利")


if __name__ == "__main__":
    unittest.main()
