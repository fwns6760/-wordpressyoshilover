"""② 節目カウントダウン(現役通算記録の接近)generator のテスト。"""
import unittest

from src.analysis import career_milestone as cm


def _cache() -> dict:
    """npb_career cache 形 (ids: name->id, players: id->career)。"""
    return {
        "ids": {
            "丸佳浩": "p_maru",
            "坂本勇人": "p_sakamoto",
            "戸郷翔征": "p_togo",
        },
        "players": {
            # 本塁打 291 -> 300 (あと9, window内) / 盗塁 188 -> 200 (あと12, window内)
            "p_maru": {
                "is_pitcher": False,
                "batting": {
                    "total": {"安打": "1800", "本塁打": "291", "打点": "950", "盗塁": "188"},
                    "years": [
                        {"年度": "2024", "本塁打": "14", "盗塁": "8"},
                        {"年度": "2025", "本塁打": "6", "盗塁": "5"},
                        {"年度": "2026", "本塁打": "2", "盗塁": "0"},
                    ],
                },
            },
            # 安打 2457 -> 次2500 はあと43 (window外) / 本塁打 300 は到達済 -> 次400 遠い
            "p_sakamoto": {
                "is_pitcher": False,
                "batting": {
                    "total": {"安打": "2457", "本塁打": "300", "打点": "1065", "盗塁": "163"},
                    "years": [{"年度": "2026", "本塁打": "5"}],
                },
            },
            # 投手: 勝利 95 -> 100 (あと5, 投手window 10内)
            "p_togo": {
                "is_pitcher": True,
                "pitching": {
                    "total": {"勝利": "95", "セーブ": "0", "三振": "816"},
                    "years": [
                        {"年度": "2024", "勝利": "12"},
                        {"年度": "2025", "勝利": "11"},
                        {"年度": "2026", "勝利": "3"},
                    ],
                },
            },
        },
    }


class CareerMilestoneTests(unittest.TestCase):
    def test_find_approaching_window(self):
        cands = cm.find_approaching(_cache())
        keys = {(c["name"], c["unit"], c["remaining"]) for c in cands}
        # 丸 本塁打あと9 / 丸 盗塁あと12 / 戸郷 勝あと5 が window 内
        self.assertIn(("丸佳浩", "本塁打", 9), keys)
        self.assertIn(("丸佳浩", "盗塁", 12), keys)
        self.assertIn(("戸郷翔征", "勝", 5), keys)

    def test_out_of_window_excluded(self):
        cands = cm.find_approaching(_cache())
        # 坂本 安打あと43 は打者window 30 外 → 出ない
        self.assertFalse(any(c["name"] == "坂本勇人" for c in cands))

    def test_sorted_by_remaining(self):
        cands = cm.find_approaching(_cache())
        rems = [c["remaining"] for c in cands]
        self.assertEqual(rems, sorted(rems))
        # 最も近いのは戸郷の勝あと5
        self.assertEqual((cands[0]["name"], cands[0]["remaining"]), ("戸郷翔征", 5))

    def test_title_format_case_c(self):
        arts = cm.generate_articles(_cache(), max_articles=5)
        titles = [a["title"] for a in arts]
        self.assertIn("【巨人データ】戸郷翔征 通算95勝、100勝まであと5", titles)
        self.assertIn("【巨人データ】丸佳浩 通算291本塁打、300本塁打まであと9", titles)

    def test_body_has_link_and_milestone(self):
        arts = cm.generate_articles(_cache(), max_articles=5)
        maru_hr = next(a for a in arts if "本塁打" in a["title"] and "丸佳浩" in a["title"])
        body = maru_hr["body_md"]
        self.assertIn("/data/maru-yoshihiro/", body)
        self.assertIn("あと9", body)
        self.assertIn("300本塁打", body)

    def test_max_articles_cap(self):
        arts = cm.generate_articles(_cache(), max_articles=1)
        self.assertEqual(len(arts), 1)
        # 残り最小(戸郷あと5)が優先採用される
        self.assertIn("戸郷翔征", arts[0]["title"])

    def test_empty_cache_returns_empty(self):
        self.assertEqual(cm.find_approaching({}), [])
        self.assertEqual(cm.generate_articles({}, max_articles=3), [])

    def test_enabled_env_gate_default_off(self):
        import os

        old = os.environ.pop("DATA_INSIGHT_CAREER_MILESTONE", None)
        try:
            self.assertFalse(cm.enabled())
            os.environ["DATA_INSIGHT_CAREER_MILESTONE"] = "1"
            self.assertTrue(cm.enabled())
        finally:
            os.environ.pop("DATA_INSIGHT_CAREER_MILESTONE", None)
            if old is not None:
                os.environ["DATA_INSIGHT_CAREER_MILESTONE"] = old


if __name__ == "__main__":
    unittest.main()
