import unittest

from src import rss_fetcher


class LineupCreatePriorityTests(unittest.TestCase):
    def test_prioritize_prepared_entries_moves_lineup_and_farm_lineup_first(self):
        general_entry = {
            "source_type": "news",
            "category": "選手情報",
            "title": "【巨人】戸郷翔征がブルペン調整",
            "summary": "戸郷翔征がブルペンで調整した。",
            "entry_has_game": False,
            "entry_index": 0,
        }
        farm_entry = {
            "source_type": "news",
            "category": "ドラフト・育成",
            "title": "【二軍】浅野翔吾が適時打",
            "summary": "巨人二軍で浅野翔吾が適時打を放った。",
            "entry_has_game": True,
            "entry_index": 1,
        }
        lineup_entry = {
            "source_type": "news",
            "category": "試合速報",
            "title": "【巨人】今日のスタメン発表 1番丸、4番岡本和",
            "summary": "巨人が阪神戦のスタメンを発表した。",
            "entry_has_game": True,
            "entry_index": 2,
        }
        farm_lineup_entry = {
            "source_type": "news",
            "category": "ドラフト・育成",
            "title": "【二軍】巨人対DeNA 4番ショートでスタメン",
            "summary": "巨人二軍のスタメンが発表された。",
            "entry_has_game": True,
            "entry_index": 3,
        }

        prioritized = rss_fetcher._prioritize_prepared_entries_for_creation(
            [general_entry, farm_entry, lineup_entry, farm_lineup_entry]
        )

        self.assertEqual(
            [item["title"] for item in prioritized],
            [
                lineup_entry["title"],
                farm_lineup_entry["title"],
                general_entry["title"],
                farm_entry["title"],
            ],
        )

    def test_prioritize_prepared_entries_keeps_lineup_inside_limit_window(self):
        general_entries = [
            {
                "source_type": "news",
                "category": "選手情報",
                "title": f"【巨人】一般記事{i}",
                "summary": f"一般記事{i}の概要。",
                "entry_has_game": False,
                "entry_index": i,
            }
            for i in range(10)
        ]
        lineup_entry = {
            "source_type": "news",
            "category": "試合速報",
            "title": "【巨人】今日のスタメン発表 1番丸、4番岡本和",
            "summary": "巨人が阪神戦のスタメンを発表した。",
            "entry_has_game": True,
            "entry_index": 10,
        }

        prioritized = rss_fetcher._prioritize_prepared_entries_for_creation(general_entries + [lineup_entry])
        limited_titles = [item["title"] for item in prioritized[:10]]

        self.assertIn(lineup_entry["title"], limited_titles)
        self.assertNotIn(general_entries[-1]["title"], limited_titles)


if __name__ == "__main__":
    unittest.main()
