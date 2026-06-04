"""全史ランキング共有部品 + ④ ランキング変動検知のテスト。"""
import unittest

from src.analysis import alltime_ranking as ar
from src.analysis import career_rank_change as rc


def _ob() -> dict:
    # batter: hr。pitcher: w。
    return {
        "王貞治": {"type": "batter", "slug": "oh", "npb": {"hr": 868, "hits": 2786, "rbi": 2170}},
        "長嶋茂雄": {"type": "batter", "slug": "nagashima", "npb": {"hr": 444, "hits": 2471, "rbi": 1522}},
        "原辰徳": {"type": "batter", "slug": "hara", "npb": {"hr": 382, "hits": 1675, "rbi": 1093}},
        "中畑清": {"type": "batter", "slug": "nakahata", "npb": {"hr": 171, "hits": 1294, "rbi": 705}},
        "金田正一": {"type": "pitcher", "slug": "kaneda", "npb": {"w": 400, "k": 4490}},
    }


def _cache(maru_hr: int = 291) -> dict:
    return {
        "ids": {"丸佳浩": "p_maru", "岡本和真": "p_okamoto"},
        "players": {
            "p_maru": {"is_pitcher": False, "batting": {"total": {"本塁打": str(maru_hr), "安打": "1800", "打点": "950"}}},
            "p_okamoto": {"is_pitcher": False, "batting": {"total": {"本塁打": "248", "安打": "1100", "打点": "760"}}},
        },
    }


class AlltimeRankingTests(unittest.TestCase):
    def test_ranking_merges_ob_and_current(self):
        rk = ar.build_rankings(_ob(), _cache())
        hr = rk["hr"]
        names = [r["name"] for r in hr]
        # 王 868 > 長嶋 444 > 原 382 > 岡本 248 > 中畑 171 ...
        self.assertEqual(names[0], "王貞治")
        okamoto = next(r for r in hr if r["name"] == "岡本和真")
        nakahata = next(r for r in hr if r["name"] == "中畑清")
        self.assertTrue(okamoto["rank"] < nakahata["rank"])  # 248 > 171
        self.assertTrue(okamoto["is_current"])

    def test_current_player_ranks_below_name(self):
        rk = ar.build_rankings(_ob(), _cache())
        cpr = ar.current_player_ranks(rk)
        # 岡本 248 の 1 つ下は 中畑清 171
        self.assertEqual(cpr["hr"]["岡本和真"]["below_name"], "中畑清")

    def test_pitcher_ranking_separate(self):
        rk = ar.build_rankings(_ob(), _cache())
        win_names = [r["name"] for r in rk["win"]]
        self.assertEqual(win_names[0], "金田正一")
        # batter は win に出ない
        self.assertNotIn("王貞治", win_names)


class RankChangeTests(unittest.TestCase):
    def _snapshot(self, cache):
        rk = ar.build_rankings(_ob(), cache)
        return {"ranks": ar.current_player_ranks(rk)}

    def test_no_prev_snapshot_no_change(self):
        today = ar.current_player_ranks(ar.build_rankings(_ob(), _cache()))
        self.assertEqual(rc.detect_rank_changes(today, None), [])

    def test_rank_up_passes_named_player(self):
        # 岡本 248(中畑171の上=ある順位)→ 原辰徳382 を超える 390 に増加して順位上昇
        prev = self._snapshot(_cache())  # 岡本 248
        cache_up = _cache()
        cache_up["players"]["p_okamoto"]["batting"]["total"]["本塁打"] = "390"  # 原(382)超え
        today = ar.current_player_ranks(ar.build_rankings(_ob(), cache_up))
        changes = rc.detect_rank_changes(today, prev)
        okamoto = [c for c in changes if c["name"] == "岡本和真"]
        self.assertTrue(okamoto)
        c = okamoto[0]
        self.assertLess(c["today_rank"], c["prev_rank"])  # 上昇
        self.assertEqual(c["passed"], "原辰徳")  # 1つ下=抜いた相手

    def test_article_title_and_body(self):
        prev = self._snapshot(_cache())
        cache_up = _cache()
        cache_up["players"]["p_okamoto"]["batting"]["total"]["本塁打"] = "390"
        today = ar.current_player_ranks(ar.build_rankings(_ob(), cache_up))
        changes = rc.detect_rank_changes(today, prev)
        art = rc.build_article(next(c for c in changes if c["name"] == "岡本和真"))
        self.assertIn("岡本和真", art["title"])
        self.assertIn("浮上", art["title"])
        self.assertIn("原辰徳を抜く", art["title"])
        self.assertIn("/data/", art["body_md"])
        self.assertIn("NPB通算", art["body_md"])

    def test_no_change_when_rank_same(self):
        prev = self._snapshot(_cache())
        today = ar.current_player_ranks(ar.build_rankings(_ob(), _cache()))  # 変化なし
        self.assertEqual(rc.detect_rank_changes(today, prev), [])

    def test_enabled_gate_default_off(self):
        import os
        old = os.environ.pop("DATA_INSIGHT_RANK_CHANGE", None)
        try:
            self.assertFalse(rc.enabled())
            os.environ["DATA_INSIGHT_RANK_CHANGE"] = "1"
            self.assertTrue(rc.enabled())
        finally:
            os.environ.pop("DATA_INSIGHT_RANK_CHANGE", None)
            if old is not None:
                os.environ["DATA_INSIGHT_RANK_CHANGE"] = old


if __name__ == "__main__":
    unittest.main()
