"""ticket 467 — NPB career page parser tests (実 NPB HTML fixture で検証)。

fixture は 2026-06-02 に npb.jp から実取得:
  - npb_career_pitcher_togo_41045138.html (戸郷翔征 / 投手)
  - npb_career_batter_sakamoto_51955114.html (坂本勇人 / 打者)
  - npb_roster_rst_g_ids.html (巨人ロスター、 name->id リンク)
"""

from __future__ import annotations

import os
import unittest

from src.npb_career_scraper import (
    BATTING_COLUMNS,
    PITCHING_COLUMNS,
    compute_career_milestones,
    parse_giants_roster_ids,
    parse_player_career,
    parse_player_profile,
)

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> str:
    with open(os.path.join(_FIX, name), encoding="utf-8", errors="replace") as fh:
        return fh.read()


class RosterIdParseTests(unittest.TestCase):
    def test_name_to_id(self) -> None:
        ids = parse_giants_roster_ids(_load("npb_roster_rst_g_ids.html"))
        self.assertGreater(len(ids), 50)  # 支配下+育成で 100 名規模
        self.assertEqual(ids.get("戸郷翔征"), "41045138")
        self.assertEqual(ids.get("坂本勇人"), "51955114")
        self.assertEqual(ids.get("田中将大"), "11215114")
        # 全角空白が除去され姓名連結キーになっていること
        self.assertNotIn("戸郷　翔征", ids)


class ProfileParseTests(unittest.TestCase):
    def test_pitcher_profile(self) -> None:
        p = parse_player_profile(_load("npb_career_pitcher_togo_41045138.html"))
        self.assertEqual(p["position"], "投手")
        self.assertEqual(p["bats_throws"], "右投右打")
        self.assertIn("187cm", p["height_weight"])
        self.assertIn("2000年4月4日", p["birthdate"])
        self.assertIn("聖心ウルスラ", p["school"])
        self.assertIn("2018年", p["draft"])

    def test_batter_profile(self) -> None:
        p = parse_player_profile(_load("npb_career_batter_sakamoto_51955114.html"))
        self.assertEqual(p["position"], "内野手")
        self.assertIn("1988年12月14日", p["birthdate"])
        self.assertIn("光星学院", p["school"])


class CareerParseTests(unittest.TestCase):
    def test_pitcher_career(self) -> None:
        c = parse_player_career(_load("npb_career_pitcher_togo_41045138.html"))
        self.assertTrue(c["is_pitcher"])
        pit = c["pitching"]
        self.assertIsNotNone(pit)
        self.assertEqual(pit["columns"], PITCHING_COLUMNS)
        # 2019-2026 の 8 年分
        self.assertEqual(len(pit["years"]), 8)
        y0 = pit["years"][0]
        self.assertEqual(y0["年度"], "2019")
        self.assertEqual(y0["所属球団"], "読売")
        self.assertEqual(y0["投球回"], "8.2")  # nested inning table flatten
        self.assertEqual(y0["防御率"], "2.08")
        # 通算行
        tot = pit["total"]
        self.assertIsNotNone(tot)
        self.assertEqual(tot["登板"], "147")
        self.assertEqual(tot["投球回"], "924.2")
        self.assertEqual(tot["防御率"], "2.93")
        # 全 year 行が 24 列フルで埋まる (網羅 = 取りこぼし無し)
        for row in pit["years"]:
            self.assertEqual(len(row), len(PITCHING_COLUMNS))

    def test_batter_career(self) -> None:
        c = parse_player_career(_load("npb_career_batter_sakamoto_51955114.html"))
        self.assertFalse(c["is_pitcher"])
        bat = c["batting"]
        self.assertIsNotNone(bat)
        self.assertEqual(bat["columns"], BATTING_COLUMNS)
        self.assertGreaterEqual(len(bat["years"]), 19)  # 2007- 長期キャリア
        y0 = bat["years"][0]
        self.assertEqual(y0["年度"], "2007")
        tot = bat["total"]
        self.assertEqual(tot["安打"], "2457")
        self.assertEqual(tot["本塁打"], "300")
        self.assertEqual(tot["打率"], ".286")
        # 移籍履歴の網羅: 所属球団が全 year 行で取れる
        for row in bat["years"]:
            self.assertTrue(row["所属球団"])

    def test_empty_html(self) -> None:
        c = parse_player_career("")
        self.assertEqual(c["profile"], {})
        self.assertIsNone(c["batting"])
        self.assertIsNone(c["pitching"])


class CareerMilestoneTests(unittest.TestCase):
    """468-2: compute_career_milestones の決定的計算 + 検算ガード。"""

    def _bat(self, years, total):
        return {"is_pitcher": False,
                "batting": {"years": years, "total": total},
                "pitching": None}

    def test_batter_cumulative_crossings(self) -> None:
        years = [
            {"年度": "2008", "試合": "100", "安打": "800", "本塁打": "40"},
            {"年度": "2009", "試合": "100", "安打": "800", "本塁打": "40"},
            {"年度": "2010", "試合": "100", "安打": "500", "本塁打": "30"},
        ]
        total = {"安打": "2100", "本塁打": "110", "試合": "300"}
        ms = compute_career_milestones(self._bat(years, total))
        hits = {(m["milestone"], m["year"], m["cum_games"]) for m in ms if m["stat"] == "安打"}
        # 1000安打=2009年(cum1600,試合200)、1500安打=2009年、2000安打=2010年(cum2100,試合300)
        self.assertIn((1000, "2009", 200), hits)
        self.assertIn((1500, "2009", 200), hits)
        self.assertIn((2000, "2010", 300), hits)
        self.assertNotIn(2500, {m["milestone"] for m in ms if m["stat"] == "安打"})
        # 100本塁打=2010年(cum110)
        self.assertIn((100, "2010"), {(m["milestone"], m["year"]) for m in ms if m["stat"] == "本塁打"})
        # 投手節目は出ない
        self.assertEqual([m for m in ms if m["games_unit"] == "登板"], [])

    def test_total_mismatch_skips_stat(self) -> None:
        """年度別累計が total と食い違う stat は出さない (出典不一致を黙って出さない)。"""
        years = [
            {"年度": "2008", "試合": "100", "安打": "800"},
            {"年度": "2009", "試合": "100", "安打": "800"},
            {"年度": "2010", "試合": "100", "安打": "500"},
        ]
        total = {"安打": "9999", "試合": "300"}  # 累計2100と不一致
        ms = compute_career_milestones(self._bat(years, total))
        self.assertEqual([m for m in ms if m["stat"] == "安打"], [])

    def test_real_sakamoto_fixture(self) -> None:
        """実 NPB fixture (坂本勇人) で 通算2000安打=2020年、累計==total を確認。"""
        car = parse_player_career(_load("npb_career_batter_sakamoto_51955114.html"))
        ms = compute_career_milestones(car)
        hit2000 = [m for m in ms if m["stat"] == "安打" and m["milestone"] == 2000]
        self.assertEqual(len(hit2000), 1)
        self.assertEqual(hit2000[0]["year"], "2020")  # 記憶でなく出典計算: 2020年到達
        self.assertEqual(hit2000[0]["games_unit"], "試合")
        # 安打節目が出ている = 累計と total が一致した (検算通過) ことの担保
        self.assertTrue(any(m["stat"] == "安打" for m in ms))

    def test_empty_career_no_milestones(self) -> None:
        self.assertEqual(compute_career_milestones({}), [])
        self.assertEqual(compute_career_milestones({"is_pitcher": False, "batting": None}), [])


if __name__ == "__main__":
    unittest.main()
