import unittest

from src import rss_fetcher
from src.title_style_validator import validate_title_style


class RssFetcherTitleStyleAlignmentTests(unittest.TestCase):
    def test_speculative_refactor_templates_return_fact_first_titles(self):
        cases = (
            {
                "name": "game_pregame_first_at_bat_with_opponent",
                "title": "【巨人】阪神戦で皆川岳飛がプロ初打席へ",
                "summary": "巨人のルーキー皆川岳飛が阪神戦でプロ初打席に向かう。",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人阪神戦 初打席の注目選手",
                "expected_key": "game_pregame_first_at_bat",
                "validator_subtype": "pregame",
            },
            {
                "name": "game_pregame_first_at_bat_without_opponent",
                "title": "【巨人】ドラ４ルーキーがプロ初打席へ",
                "summary": "巨人のルーキーがプロ初打席に向かう。",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人戦 初打席の注目選手情報",
                "expected_key": "game_pregame_first_at_bat",
                "validator_subtype": "pregame",
            },
            {
                "name": "game_pregame_subject_with_opponent",
                "title": "阪神・佐藤輝明、衝撃の一発！辻発彦氏「強振している感じがしない」",
                "summary": "",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人阪神戦 佐藤輝明に関する試合前情報",
                "expected_key": "game_pregame_subject",
                "validator_subtype": "pregame",
            },
            {
                "name": "game_pregame_subject_without_opponent",
                "title": "坂本勇人の調整状況",
                "summary": "巨人の坂本勇人が試合前練習で汗を流した。",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人戦 坂本勇人に関する試合前情報",
                "expected_key": "game_pregame_subject",
                "validator_subtype": "pregame",
            },
            {
                "name": "game_pregame_venue_with_opponent",
                "title": "【一軍】巨人 vs 阪神 4/16(木)18:00試合開始予定⚾ 阪神甲子園球場",
                "summary": "",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人阪神戦 甲子園に関する試合前情報",
                "expected_key": "game_pregame_venue",
                "validator_subtype": "pregame",
            },
            {
                "name": "game_pregame_venue_without_opponent",
                "title": "【一軍】巨人 4/16(木)18:00試合開始予定⚾ 東京ドーム",
                "summary": "",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人戦 東京ドームに関する試合前情報",
                "expected_key": "game_pregame_venue",
                "validator_subtype": "pregame",
            },
            {
                "name": "game_pregame_opponent",
                "title": "【巨人】阪神戦の試合前情報",
                "summary": "",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人阪神戦 当日カードの試合前情報",
                "expected_key": "game_pregame_opponent",
                "validator_subtype": "pregame",
            },
            {
                "name": "game_pregame_generic",
                "title": "【巨人】試合開始前の最新情報",
                "summary": "",
                "category": "試合速報",
                "has_game": True,
                "expected_title": "巨人戦 当日カードの試合前情報",
                "expected_key": "game_pregame_generic",
                "validator_subtype": "pregame",
            },
            {
                "name": "reinforcement_foreign",
                "title": "巨人の新外国人補強に注目",
                "summary": "",
                "category": "補強・移籍",
                "has_game": False,
                "expected_title": "巨人の新外国人補強 関連情報",
                "expected_key": "reinforcement_foreign",
                "validator_subtype": "notice",
            },
            {
                "name": "reinforcement_trade",
                "title": "巨人の補強・移籍とトレード動向",
                "summary": "",
                "category": "補強・移籍",
                "has_game": False,
                "expected_title": "巨人の補強・移籍 最新関連情報",
                "expected_key": "reinforcement_trade",
                "validator_subtype": "notice",
            },
            {
                "name": "reinforcement_generic",
                "title": "巨人補強の整理",
                "summary": "",
                "category": "補強・移籍",
                "has_game": False,
                "expected_title": "巨人補強の整理 関連トピック",
                "expected_key": "reinforcement_generic",
                "validator_subtype": "notice",
            },
            {
                "name": "farm_lineup",
                "title": "【二軍】巨人対DeNA 4番ショートでスタメン",
                "summary": "巨人の二軍スタメンが発表された。",
                "category": "ドラフト・育成",
                "has_game": True,
                "expected_title": "巨人二軍スタメン 当日カード試合前情報",
                "expected_key": "farm_lineup",
                "validator_subtype": "farm",
            },
        )

        for case in cases:
            with self.subTest(case=case["name"]):
                rewritten, template_key = rss_fetcher._rewrite_display_title_with_template(
                    case["title"],
                    case["summary"],
                    case["category"],
                    case["has_game"],
                )
                self.assertEqual(rewritten, case["expected_title"])
                self.assertEqual(template_key, case["expected_key"])
                result = validate_title_style(rewritten, case["validator_subtype"])
                self.assertTrue(result.ok, msg=f"{case['name']}: {result}")


if __name__ == "__main__":
    unittest.main()
