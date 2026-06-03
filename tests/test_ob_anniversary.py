"""③ 今日は何の日(OB)誕生日記事 generator のテスト。"""
import datetime as dt
import unittest

from src.analysis import ob_anniversary as oa


def _sample() -> dict:
    return {
        "王貞治": {
            "slug": "oh-sadaharu", "type": "batter", "years": "1959-1980",
            "birth": "1940-05-20",
            "npb": {"games": 2831, "avg": ".301", "hits": 2786, "hr": 868, "rbi": 2170},
            "honors": ["世界の本塁打王"],
        },
        "桑田真澄": {
            "slug": "kuwata-masumi", "type": "pitcher", "years": "1986-2006",
            "birth": "1968-04-01",
            "npb": {"games": 442, "w": 173, "era": "3.55", "k": 1980},
            "honors": ["巨人の大エース"],
        },
        "無名太郎": {  # notable gate で除外される短期選手
            "slug": "mumei", "type": "batter", "years": "1975-1976",
            "birth": "1950-05-20", "npb": {"games": 12, "hr": 0}, "honors": [],
        },
    }


class ObAnniversaryTests(unittest.TestCase):
    def test_birthday_match_generates_article(self):
        arts = oa.generate_today_articles(_sample(), today=dt.date(2026, 5, 20))
        self.assertEqual(len(arts), 1)  # 王のみ(無名は gate 除外)
        self.assertIn("王貞治", arts[0]["title"])
        self.assertIn("5月20日", arts[0]["title"])
        self.assertIn("868本塁打", arts[0]["title"])

    def test_age_and_body(self):
        arts = oa.generate_today_articles(_sample(), today=dt.date(2026, 5, 20))
        body = arts[0]["body_md"]
        self.assertIn("満86歳", body)  # 1940 -> 2026
        self.assertIn("/data/oh-sadaharu/", body)
        self.assertIn("世界の本塁打王", body)

    def test_pitcher_career_line(self):
        arts = oa.generate_today_articles(_sample(), today=dt.date(2026, 4, 1))
        self.assertEqual(len(arts), 1)
        self.assertIn("桑田真澄", arts[0]["title"])
        self.assertIn("173勝", arts[0]["body_md"])

    def test_no_match_returns_empty(self):
        arts = oa.generate_today_articles(_sample(), today=dt.date(2026, 12, 25))
        self.assertEqual(arts, [])

    def test_notable_gate_excludes_minor(self):
        arts = oa.generate_today_articles(_sample(), today=dt.date(2026, 5, 20))
        names = " ".join(a["title"] for a in arts)
        self.assertNotIn("無名太郎", names)

    def test_max_articles_cap(self):
        big = {f"選手{i}": {"slug": f"p{i}", "type": "batter", "years": "2000-2010",
                            "birth": "1980-06-03",
                            "npb": {"games": 1000, "hr": 200}, "honors": ["賞"]}
               for i in range(5)}
        arts = oa.generate_today_articles(big, today=dt.date(2026, 6, 3), max_articles=3)
        self.assertEqual(len(arts), 3)


if __name__ == "__main__":
    unittest.main()
