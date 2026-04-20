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


    def test_post_gen_validate_rejects_live_update_lineup_structure(self):
        text = "\n".join(
            [
                "【いま起きていること】",
                "7回表は巨人が3-2でリードしています。",
                "【流れが動いた場面】",
                "1番丸 2番泉口 3番吉川 4番岡本 5番甲斐と並べた打順表のまま試合が進んでいます。",
                "【次にどこを見るか】",
                "次の継投で流れが変わるか、みなさんの意見はコメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="live_update")
        self.assertFalse(result["ok"])
        self.assertIn("live_update_lineup_structure", result["fail_axes"])
        self.assertEqual(result["stop_reason"], "live_update_lineup_guard")

    def test_post_gen_validate_accepts_normal_live_update(self):
        text = "\n".join(
            [
                "【いま起きていること】",
                "7回表は巨人が3-2でリードし、4番手がマウンドに上がりました。",
                "【流れが動いた場面】",
                "6回に同点を許した直後、7回表に勝ち越し打が出て流れを引き戻しました。",
                "【次にどこを見るか】",
                "8回の継投でこの1点差をどう守るかが気になります。みなさんの意見はコメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="live_update")
        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])

    def test_post_gen_validate_rejects_live_update_title_prefix(self):
        text = "\n".join(
            [
                "【いま起きていること】",
                "7回表は巨人が3-2でリードしています。",
                "【流れが動いた場面】",
                "6回に同点を許したあと、7回に勝ち越しました。",
                "【次にどこを見るか】",
                "次の継投で流れがどう動くか、みなさんの意見はコメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(
            text,
            article_subtype="live_update",
            title="巨人スタメン 7回表 3-2 途中経過",
        )
        self.assertFalse(result["ok"])
        self.assertIn("live_update_title_prefix", result["fail_axes"])

    def test_post_gen_validate_rejects_live_update_h2_heading_prefix(self):
        text = "\n".join(
            [
                "<h2>巨人スタメン 7回表 3-2</h2>",
                "7回表は巨人が3-2でリードしています。",
                "<h2>流れが動いた場面</h2>",
                "6回に同点を許したあと、7回に勝ち越しました。",
                "<h2>次にどこを見るか</h2>",
                "次の継投で流れがどう動くか、みなさんの意見はコメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="live_update")
        self.assertFalse(result["ok"])
        self.assertIn("live_update_heading_prefix", result["fail_axes"])

if __name__ == "__main__":
    unittest.main()
