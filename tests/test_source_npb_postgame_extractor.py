"""Unit tests for ``src/source_npb_postgame_extractor.py``.

NOMOTOKE-LINEUP-FROM-POSTGAME-001 Phase 2F regression coverage. Parses
NPB公式 ``/scores/<YYYY>/<MMDD>/<away>-<home>-<N>/box.html`` static HTML
pages into per-batter / per-pitcher row dicts.

Uses the saved 2026-05-10 中日 vs 巨人 fixture committed alongside
Phase 2E (``npb_score_2026_0510_d-g-08_box.html``).
"""

from __future__ import annotations

import unittest
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
BOX_FIXTURE = FIXTURE_DIR / "npb_score_2026_0510_d-g-08_box.html"


class ParseNPBBoxHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BOX_FIXTURE.exists():
            raise unittest.SkipTest(f"missing fixture: {BOX_FIXTURE}")
        cls.html = BOX_FIXTURE.read_text(encoding="utf-8")

    def test_returns_giants_facts_dict(self):
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        self.assertIsNotNone(facts)
        self.assertIn("giants_batters", facts)
        self.assertIn("giants_pitchers", facts)
        self.assertIn("opponent_batters", facts)
        self.assertIn("opponent_pitchers", facts)
        self.assertIn("opponent_team_name", facts)

    def test_giants_batters_extracted(self):
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        batters = facts["giants_batters"]
        self.assertGreater(len(batters), 8, "巨人 batter rows < 9")
        # First row 1番二吉川 (per fixture)
        first = batters[0]
        self.assertEqual(first["順"], "1")
        self.assertEqual(first["守備"], "二")
        self.assertEqual(first["選手"], "吉川")
        # Counts
        self.assertEqual(first["打数"], "5")

    def test_giants_pitcher_森田_with_invest(self):
        """森田 投手 row が 巨人 投手 table に入る(本日 5/10 fixture では先発)。"""
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        pitchers = facts["giants_pitchers"]
        names = [p.get("選手", "") for p in pitchers]
        self.assertIn("森田", names)

    def test_opponent_team_name(self):
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        # 5/10 fixture: 巨人 vs 中日 → opponent = 中日
        self.assertEqual(facts["opponent_team_name"], "中日")

    def test_atbats_column_present(self):
        """打席結果列(1-9)が各 batter row に list として入る。"""
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        batters = facts["giants_batters"]
        first = batters[0]
        self.assertIn("atbats", first)
        self.assertEqual(len(first["atbats"]), 9, "9 inning slots expected")
        # First atbat for 吉川 in fixture is "二ゴロ"
        self.assertIn("二ゴロ", first["atbats"][0])

    def test_inning_score_extracted(self):
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        self.assertIn("inning_score", facts)
        inning = facts["inning_score"]
        self.assertEqual(len(inning), 2, "2 team rows expected")
        # 巨人 (away) total = 9, 中日 (home) total = 4 per fixture
        giants_row = next((r for r in inning if "巨人" in (r.get("name") or "")), None)
        self.assertIsNotNone(giants_row)
        self.assertEqual(int(giants_row["total"]), 9)

    def test_pitcher_result_mark_captured(self):
        """Phase 2H: row[0] (○/●/S/H) を result_mark に保持。"""
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        g_p = facts["giants_pitchers"]
        funami = next((p for p in g_p if p.get("選手") == "船迫"), None)
        self.assertIsNotNone(funami)
        self.assertEqual(funami.get("result_mark"), "○")
        # 森田(先発、勝敗なし)は空
        morita = next((p for p in g_p if p.get("選手") == "森田"), None)
        self.assertIsNotNone(morita)
        self.assertEqual(morita.get("result_mark"), "")

    def test_wls_summary_derived(self):
        """Phase 2H: winning_pitcher / losing_pitcher を NPB facts から
        derive 可能(Yahoo 不要)。"""
        from src.source_npb_postgame_extractor import parse_npb_box_html
        facts = parse_npb_box_html(self.html)
        self.assertIn("winning_pitcher", facts)
        self.assertIn("losing_pitcher", facts)
        self.assertIn("save_pitcher", facts)
        # 5/10 fixture: 巨人 9-4 中日 → 勝利 = 巨人 投手、敗戦 = 中日 投手
        winner = facts["winning_pitcher"]
        self.assertEqual(winner.get("team"), "巨人")
        self.assertEqual(winner.get("name"), "船迫")
        loser = facts["losing_pitcher"]
        self.assertEqual(loser.get("team"), "中日")
        self.assertEqual(loser.get("name"), "メヒア")


if __name__ == "__main__":
    unittest.main()
