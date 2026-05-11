import unittest

from src import rss_fetcher


class GeneralSubtypeRoutingTests(unittest.TestCase):
    def assert_general_source_routes_to(self, title: str, summary: str, category: str, expected: str) -> None:
        subtype = rss_fetcher._detect_article_subtype(title, summary, category, False)
        gate_subtype = rss_fetcher.resolve_publish_gate_subtype(title, summary, category, subtype, "news")

        self.assertEqual(subtype, expected)
        self.assertEqual(gate_subtype, expected)

    def test_farm_result_from_column_routes_to_farm_subtype(self):
        self.assert_general_source_routes_to(
            "【巨人】二軍で浅野翔吾が猛打賞",
            "巨人二軍の試合で浅野翔吾が3安打を放った。",
            "コラム",
            "farm",
        )

    def test_player_notice_from_column_routes_to_notice_subtype(self):
        self.assert_general_source_routes_to(
            "【巨人】浅野翔吾が出場選手登録",
            "公示で浅野翔吾外野手が出場選手登録された。",
            "コラム",
            "notice",
        )

    def test_player_recovery_from_column_routes_to_recovery_subtype(self):
        self.assert_general_source_routes_to(
            "【巨人】大城卓三がヘルメットにバット直撃",
            "大城卓三捕手は試合中にバットがヘルメットへ当たり、負傷の状態を確認している。",
            "コラム",
            "recovery",
        )

    def test_player_record_from_team_info_routes_to_player_subtype(self):
        self.assert_general_source_routes_to(
            "【巨人】坂本勇人が通算1664単打",
            "坂本勇人内野手が通算1664単打を記録した。",
            "球団情報",
            "player",
        )


if __name__ == "__main__":
    unittest.main()
