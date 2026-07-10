"""starter_matchup_post — 予告先発予習 + スタメン発表 (2026-07-10 user GO A+C)。"""

import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src import starter_matchup_post as smp

JST = timezone(timedelta(hours=9))
_NOW = datetime(2026, 7, 10, 8, 30, tzinfo=JST)

_HTML = (
    "<h1>予告先発</h1><table><tr><td>DeNA</td></tr>"
    "<tr><th>背番号</th><th>投</th><th>選手名</th></tr>"
    "<tr><td>36</td><td>右投</td><td>尾形 崇斗</td></tr>"
    "<tr><th>防御率</th><th>登板</th><th>勝利</th><th>敗戦</th></tr>"
    "<tr><td>今季</td><td>2.81</td><td>5</td><td>1</td><td>2</td></tr>"
    "<tr><td>対戦</td><td>-</td><td>0</td><td>0</td><td>0</td></tr>"
    "<tr><td>巨人</td></tr>"
    "<tr><td>45</td><td>右投</td><td>ウィットリー</td></tr>"
    "<tr><td>今季</td><td>2.51</td><td>11</td><td>3</td><td>4</td></tr>"
    "</table>"
)

_MATCHUP = {
    "opp": "DeNA",
    "venue": "横浜",
    "giants": {"name": "ウィットリー", "era": "2.51", "games": "11", "wins": "3", "losses": "4"},
    "opponent": {"name": "尾形崇斗", "era": "2.81", "games": "5", "wins": "1", "losses": "2"},
}

_LINEUP = [
    {"order": str(i), "position": pos, "name": nm}
    for i, (pos, nm) in enumerate([
        ("遊", "泉口"), ("中", "丸"), ("左", "キャベッジ"), ("三", "岡本"),
        ("一", "岸田"), ("右", "浅野"), ("二", "門脇"), ("捕", "甲斐"),
        ("投", "ウィットリー"),
    ], 1)
]


class ParseStartersTests(unittest.TestCase):
    def test_parse_both_teams(self):
        rows = smp.parse_probable_starters(_HTML)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "尾形崇斗")
        self.assertEqual(rows[0]["era"], "2.81")
        self.assertEqual(rows[1]["name"], "ウィットリー")
        self.assertEqual(rows[1]["wins"], "3")

    def test_no_section_returns_empty(self):
        self.assertEqual(smp.parse_probable_starters("<html>試合中</html>"), [])


class MatchupCandidateTests(unittest.TestCase):
    def _build(self, **kw):
        kw.setdefault("now", _NOW)
        kw.setdefault("matchup", dict(_MATCHUP))
        kw.setdefault("dedup_set", set())
        return smp.build_starter_matchup_candidate(**kw)

    def test_builds_polite_matchup_post(self):
        c = self._build()
        self.assertIsNotNone(c)
        self.assertIn("巨人の先発: ウィットリー（今季 防御率2.51・11登板・3勝4敗）", c.post_text)
        self.assertIn("相手の先発: 尾形崇斗（DeNA・今季 防御率2.81・5登板・1勝2敗）", c.post_text)
        self.assertIn("7/10(金) DeNA戦（横浜）", c.post_text)
        self.assertEqual(c.focus_player, "ウィットリー")

    def test_bucket_dedup(self):
        sig = "startermatch|" + hashlib.sha1(
            "20260710|am|ウィットリー".encode("utf-8")
        ).hexdigest()[:16]
        self.assertIsNone(self._build(dedup_set={sig}))
        # 別バケット (試合前) は再度出る
        pre = self._build(
            now=_NOW.replace(hour=16), dedup_set={sig}
        )
        self.assertIsNotNone(pre)

    def test_no_matchup_returns_none(self):
        self.assertIsNone(self._build(matchup={}))


class LineupAnnounceTests(unittest.TestCase):
    def _build(self, **kw):
        kw.setdefault("now", _NOW.replace(hour=17))
        kw.setdefault("lineup_rows", [dict(r) for r in _LINEUP])
        kw.setdefault("opp", "DeNA")
        kw.setdefault("dedup_set", set())
        with patch.object(
            smp, "_canonical_names",
            side_effect=lambda names: [n + "太" for n in names],
        ):
            return smp.build_lineup_announce_candidate(**kw)

    def test_lists_nine_fullnames_in_order(self):
        c = self._build()
        self.assertIsNotNone(c)
        self.assertIn("1(遊) 泉口太", c.post_text)
        self.assertIn("9(投) ウィットリー太", c.post_text)
        self.assertIn("本日は岡本太が4番に入っています。", c.post_text)
        self.assertIn("（DeNA戦）", c.post_text)

    def test_fewer_than_nine_skips(self):
        self.assertIsNone(self._build(lineup_rows=_LINEUP[:5]))

    def test_same_lineup_dedup_and_changed_lineup_refires(self):
        c1 = self._build()
        c2 = self._build(dedup_set={c1.signature})
        self.assertIsNone(c2)
        changed = [dict(r) for r in _LINEUP]
        changed[0]["name"] = "中山"
        c3 = self._build(lineup_rows=changed, dedup_set={c1.signature})
        self.assertIsNotNone(c3)


if __name__ == "__main__":
    unittest.main()
