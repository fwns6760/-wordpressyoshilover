import unittest

from src import rss_fetcher


class PostGenValidateTests(unittest.TestCase):
    def test_post_gen_validate_rejects_missing_close_marker(self):
        text = "\n".join(
            [
                "【ニュースの整理】",
                "巨人がスタメンを発表した。",
                "【次の注目】",
                "上位打線がどうつながるかを整理したい。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text)
        self.assertFalse(result["ok"])
        self.assertIn("close_marker", result["fail_axes"])

    def test_post_gen_validate_rejects_intro_echo(self):
        text = "\n".join(
            [
                "あなたは読売ジャイアンツ専門ブログの編集者です。",
                "【話題の要旨】",
                "阿部監督が選手起用について語った。",
                "【ファンの関心ポイント】",
                "ベンチの次の動きが気になります。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text)
        self.assertFalse(result["ok"])
        self.assertIn("intro_echo", result["fail_axes"])

    def test_post_gen_validate_accepts_clean_final_section_marker(self):
        text = "\n".join(
            [
                "【試合結果】",
                "巨人が3-2で競り勝った。",
                "【ハイライト】",
                "中軸の長打で流れを引き寄せた。",
                "【選手成績】",
                "先発が7回2失点だった。",
                "【試合展開】",
                "終盤の継投が次戦にもつながるか気になります。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text)
        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])
        self.assertEqual(result["final_section_heading"], "【試合展開】")

    def test_post_gen_validate_allows_lineup_without_close_marker(self):
        text = "\n".join(
            [
                "【試合概要】",
                "巨人が阪神戦のスタメンを発表した。",
                "【スタメン一覧】",
                "1番丸、4番岡本和。",
                "【先発投手】",
                "先発は戸郷翔征。",
                "【注目ポイント】",
                "スタメン発表の時点では、並びの意味をどう読むかが一番のポイントです。試合が始まって最初にどこを見るかまで、コメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="lineup")
        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])
        self.assertEqual(result["final_section_heading"], "【注目ポイント】")

    def test_post_gen_validate_keeps_close_marker_requirement_for_non_lineup_game_subtypes(self):
        text = "\n".join(
            [
                "【二軍試合概要】",
                "巨人二軍がDeNA戦のスタメンを発表した。",
                "【二軍スタメン一覧】",
                "1番浅野、4番ティマ。",
                "【注目選手】",
                "試合が始まったら、並びの意図がどこに出るかを見ていきたい。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="farm_lineup")
        self.assertFalse(result["ok"])
        self.assertIn("close_marker", result["fail_axes"])


if __name__ == "__main__":
    unittest.main()
