"""NPB 公式 一軍 個人打撃成績 source + fetch_batting_stats_season 統合のテスト。

宇都宮葵星 (一軍 6試合2打数) が insight.db に無くても公式合計から拾えること、
公式が空/flag OFF のとき insight.db に fallback することを検証する。
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import src.data_site_ichigun_stats as ichi
import src.data_site_query as q


_HEADER = ["選手", "試合", "打席", "打数", "得点", "安打", "本塁打", "打点", "盗塁", "打率"]
_ROWS = [
    ["*宇都宮 葵星", "6", "2", "2", "2", "1", "0", "0", "0", ".500"],
    ["*キャベッジ", "65", "245", "236", "25", "58", "12", "26", "4", ".246"],
    ["山城 京平", "1", "0", "0", "0", "0", "0", "0", "0", ".000"],  # 0試合扱い→除外しない(1試合)
    ["大勢", "27", "0", "0", "0", "0", "0", "0", "0", ".000"],
]


def _reset():
    ichi._CACHE = None
    ichi._CACHE_YEAR = None


class IchigunBattingMapTests(unittest.TestCase):
    def test_parses_official_table(self):
        _reset()
        with mock.patch.object(ichi, "_fetch_table", return_value=(_HEADER, _ROWS)):
            m = ichi.giants_ichigun_batting_map(2026)
        self.assertEqual(m["宇都宮葵星"],
                         {"games": 6, "ab": 2, "hits": 1, "rbi": 0, "runs": 2, "sb": 0, "hr": 0})
        self.assertEqual(m["キャベッジ"]["hr"], 12)
        self.assertEqual(m["キャベッジ"]["ab"], 236)
        # 名前の先頭 * は除去される
        self.assertNotIn("*宇都宮 葵星", m)

    def test_empty_on_fetch_failure(self):
        _reset()
        with mock.patch.object(ichi, "_fetch_table", return_value=([], [])):
            self.assertEqual(ichi.giants_ichigun_batting_map(2026), {})


class FetchBattingSeasonSourceTests(unittest.TestCase):
    def test_prefers_official_over_insight(self):
        # 宇都宮: 公式に居る → insight.db を読まずに公式値を返す
        with mock.patch.dict(os.environ, {"DATA_SITE_ICHIGUN_OFFICIAL": "1"}), \
             mock.patch("src.data_site_ichigun_stats.giants_ichigun_batting_map",
                        return_value={"宇都宮葵星": {"games": 6, "ab": 2, "hits": 1,
                                                      "rbi": 0, "runs": 2, "sb": 0, "hr": 0}}), \
             mock.patch.object(q, "_ensure_insight_db_local") as ins:
            s = q.fetch_batting_stats_season("宇都宮葵星")
            ins.assert_not_called()
        self.assertEqual((s.games, s.ab, s.hits, s.runs), (6, 2, 1, 2))

    def test_falls_back_to_insight_when_official_absent(self):
        # 公式に居ない選手 → insight.db path へ進む (None=DB未設定で None)
        with mock.patch.dict(os.environ, {"DATA_SITE_ICHIGUN_OFFICIAL": "1"}), \
             mock.patch("src.data_site_ichigun_stats.giants_ichigun_batting_map",
                        return_value={}), \
             mock.patch.object(q, "_ensure_insight_db_local", return_value=None) as ins:
            s = q.fetch_batting_stats_season("誰か")
            ins.assert_called_once()
        self.assertIsNone(s)

    def test_flag_off_skips_official(self):
        with mock.patch.dict(os.environ, {"DATA_SITE_ICHIGUN_OFFICIAL": "0"}), \
             mock.patch("src.data_site_ichigun_stats.giants_ichigun_batting_map") as off, \
             mock.patch.object(q, "_ensure_insight_db_local", return_value=None):
            q.fetch_batting_stats_season("宇都宮葵星")
            off.assert_not_called()


if __name__ == "__main__":
    unittest.main()
