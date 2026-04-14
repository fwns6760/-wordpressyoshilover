import unittest

from src import rss_fetcher


class DisplayTitleRewriteTests(unittest.TestCase):
    def test_manager_title_prefers_angle_over_source_headline(self):
        title = "【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待"
        summary = "阿部監督が「レギュラーは決まってません。結果残せば使います」と話した。若手積極起用で競争を促す考えを示した。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "首脳陣", False)

        self.assertEqual(rewritten, "阿部監督「レギュラーは決まってません。結果残せば使います」 若手起用で序列はどう…")

    def test_player_title_becomes_reader_angle(self):
        title = "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み"
        summary = "ファームでフォーム改造中の巨人戸郷翔征投手が調整した。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "選手情報", False)

        self.assertEqual(rewritten, "戸郷翔征、フォーム変更のポイントはどこか")

    def test_lineup_title_drops_source_like_duplication(self):
        title = "【巨人】今日のスタメン発表　1番丸、4番岡田"
        summary = "巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "試合速報", True)

        self.assertEqual(rewritten, "巨人スタメン 1番丸、4番岡田でどこを動かしたか")


if __name__ == "__main__":
    unittest.main()
