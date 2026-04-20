import unittest

from src import rss_fetcher


class ClassifierFallbackTests(unittest.TestCase):
    def test_core_subtypes_constant_contains_e4_templates(self):
        self.assertEqual(
            rss_fetcher.CORE_SUBTYPES,
            ("pregame", "live_anchor", "postgame", "fact_notice", "farm"),
        )

    def test_explicit_fact_notice_marker_routes_to_fact_notice(self):
        subtype = rss_fetcher._detect_article_subtype(
            "【訂正】記事内容の更新",
            "誤報だったため当該内容を取り下げます。",
            "コラム",
            False,
        )

        self.assertEqual(subtype, "fact_notice")

    def test_score_and_opponent_fallback_routes_to_postgame(self):
        subtype = rss_fetcher._detect_article_subtype(
            "巨人が阪神に3-1で勝利",
            "阪神戦で白星をつかんだ。",
            "コラム",
            False,
        )

        self.assertEqual(subtype, "postgame")

    def test_existing_lineup_signal_is_unchanged(self):
        subtype = rss_fetcher._detect_article_subtype(
            "【巨人】阪神戦スタメン発表 1番丸、4番岡本",
            "東京ドームで18時開始。先発は戸郷翔征。",
            "試合速報",
            True,
        )

        self.assertEqual(subtype, "lineup")

    def test_unmatched_input_keeps_existing_default(self):
        subtype = rss_fetcher._detect_article_subtype(
            "巨人関連の雑感",
            "今日の話題を簡潔にまとめる。",
            "コラム",
            False,
        )

        self.assertEqual(subtype, "general")


if __name__ == "__main__":
    unittest.main()
