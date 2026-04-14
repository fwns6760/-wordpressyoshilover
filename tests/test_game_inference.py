import unittest

from src import rss_fetcher


class GameInferenceTests(unittest.TestCase):
    def test_game_category_is_treated_as_game_article(self):
        self.assertTrue(rss_fetcher.infer_article_has_game("阿部監督コメント", "起用について語った", "試合速報", False))

    def test_score_in_title_marks_game_article(self):
        self.assertTrue(rss_fetcher.infer_article_has_game("巨人3-2阪神", "逆転勝ち", "選手情報", False))

    def test_non_game_comment_article_stays_non_game_when_daily_flag_false(self):
        self.assertFalse(rss_fetcher.infer_article_has_game("阿部監督がコメント", "起用方針について語った", "首脳陣", False))

    def test_daily_flag_only_promotes_explicit_matchup_markers(self):
        self.assertTrue(rss_fetcher.infer_article_has_game("巨人 vs 阪神 先発予想", "試合前情報", "コラム", True))
        self.assertFalse(rss_fetcher.infer_article_has_game("阿部監督が会見", "今後の方針を説明", "首脳陣", True))


if __name__ == "__main__":
    unittest.main()
