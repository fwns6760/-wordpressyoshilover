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


if __name__ == "__main__":
    unittest.main()
