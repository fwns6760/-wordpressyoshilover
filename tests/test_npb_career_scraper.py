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


if __name__ == "__main__":
    unittest.main()
