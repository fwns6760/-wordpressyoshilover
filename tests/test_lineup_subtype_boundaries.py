import unittest

from src import rss_fetcher


REJECT_CASES = (
    {
        "post_id": "62965",
        "title": "【巨人】阪神戦スタメン発表 1番丸、4番岡本",
        "summary": "6回表 巨人3-1阪神。3番手の投手が3者凡退で流れをつないだ。",
        "expected_subtype": "live_update",
        "expected_title": "巨人6回表 3-1 途中経過のポイント",
    },
    {
        "post_id": "62962",
        "title": "【巨人】阪神戦スタメン発表 1番丸、4番岡本",
        "summary": "7回表 巨人3-2阪神。4番手の投手が継投に入った。",
        "expected_subtype": "live_update",
        "expected_title": "巨人7回表 3-2 途中経過のポイント",
    },
    {
        "post_id": "62955",
        "title": "【巨人】阪神戦スタメン発表 1番丸、4番岡本",
        "summary": "8回表 巨人4-2阪神。3番手の投手が継投に入った。",
        "expected_subtype": "live_update",
        "expected_title": "巨人8回表 4-2 途中経過のポイント",
    },
    {
        "post_id": "62948",
        "title": "【巨人】阪神戦スタメン発表 1番丸、4番岡本",
        "summary": "6回裏 巨人2-2阪神。2番手の投手が満塁のピンチをしのいだ。",
        "expected_subtype": "live_update",
        "expected_title": "巨人6回裏 2-2 途中経過のポイント",
    },
    {
        "post_id": "62609",
        "title": "【巨人】DeNA戦スタメン発表 1番丸、4番岡本",
        "summary": "5回 巨人4-1DeNA。打者がサイクル安打王手になった。",
        "expected_subtype": "live_update",
        "expected_title": "巨人5回 4-1 途中経過のポイント",
    },
    {
        "post_id": "62621",
        "title": "【巨人】阪神戦スタメン発表 1番丸、4番岡本",
        "summary": "9回裏 巨人2-4阪神。6番手の投手が2点を失いサヨナラ負けを喫した。",
        "expected_subtype": "postgame",
        "expected_title": "巨人阪神戦 終盤の一打で何が動いたか",
    },
)


class LineupSubtypeBoundaryTests(unittest.TestCase):
    def test_live_update_and_postgame_fragments_do_not_stay_lineup(self):
        for case in REJECT_CASES:
            with self.subTest(post_id=case["post_id"]):
                subtype = rss_fetcher._detect_article_subtype(
                    case["title"],
                    case["summary"],
                    "試合速報",
                    True,
                )

                self.assertEqual(subtype, case["expected_subtype"])

    def test_non_lineup_game_subtypes_do_not_get_lineup_prefix(self):
        for case in REJECT_CASES:
            with self.subTest(post_id=case["post_id"]):
                rewritten = rss_fetcher.rewrite_display_title(
                    case["title"],
                    case["summary"],
                    "試合速報",
                    True,
                )

                self.assertEqual(rewritten, case["expected_title"])
                self.assertFalse(rewritten.startswith("巨人スタメン"))


if __name__ == "__main__":
    unittest.main()
