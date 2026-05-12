"""Unit tests for ``src/source_npb_playbyplay_extractor.py``.

NOMOTOKE-LINEUP-FROM-POSTGAME-001 Phase 2I regression coverage. Parses
NPB公式 ``/scores/<YYYY>/<MMDD>/<away>-<home>-<N>/playbyplay.html``
static HTML pages into a flat list of plate-appearance events, and
filters to the highlight-reel scoring plays.

Uses the saved 2026-05-10 中日 vs 巨人 fixture committed alongside
Phase 2F (``npb_score_2026_0510_d-g-08_playbyplay.html``).
"""

from __future__ import annotations

import unittest
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
PBP_FIXTURE = FIXTURE_DIR / "npb_score_2026_0510_d-g-08_playbyplay.html"


class ParseNPBPlaybyplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PBP_FIXTURE.exists():
            raise unittest.SkipTest(f"missing fixture: {PBP_FIXTURE}")
        cls.html = PBP_FIXTURE.read_text(encoding="utf-8")

    def test_returns_event_list(self):
        from src.source_npb_playbyplay_extractor import parse_npb_playbyplay_html
        events = parse_npb_playbyplay_html(self.html)
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 30, "9 innings × ~3-4 batters = 30+ events expected")

    def test_event_dict_shape(self):
        from src.source_npb_playbyplay_extractor import parse_npb_playbyplay_html
        events = parse_npb_playbyplay_html(self.html)
        first = events[0]
        for key in ("inning_no", "half", "team", "outs", "batter", "count", "result"):
            self.assertIn(key, first, f"missing key: {key}")
        # First event in 5/10 fixture: 1回表 巨人 吉川 (打順 1 番)
        self.assertEqual(first["inning_no"], 1)
        self.assertEqual(first["half"], "表")
        self.assertEqual(first["team"], "巨人")
        self.assertEqual(first["batter"], "吉川")

    def test_extract_scoring_plays(self):
        """得点プレー = 本塁打 / 適時 / 犠飛 / 押し出し / 打点 含む結果。"""
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_html,
            extract_scoring_plays,
        )
        events = parse_npb_playbyplay_html(self.html)
        scoring = extract_scoring_plays(events)
        self.assertGreater(len(scoring), 4, "9-4 試合なら少なくとも 5 件以上の scoring play")
        # 5/10 fixture: ダルベックの 4回表 2ランホームランが含まれる
        names = [s["batter"] for s in scoring]
        self.assertIn("ダルベック", names)

    def test_extract_giants_scoring_plays(self):
        """巨人 攻撃の得点プレーのみ filter。"""
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_html,
            extract_giants_scoring_plays,
        )
        events = parse_npb_playbyplay_html(self.html)
        g_scoring = extract_giants_scoring_plays(events)
        self.assertGreater(len(g_scoring), 3, "巨人 5 得点なら scoring play 5 件想定")
        teams = {s["team"] for s in g_scoring}
        # 中日 の半回 は除外されている
        self.assertEqual(teams, {"巨人"})

    def test_none_for_empty_input(self):
        from src.source_npb_playbyplay_extractor import parse_npb_playbyplay_html
        self.assertIsNone(parse_npb_playbyplay_html(""))
        self.assertIsNone(parse_npb_playbyplay_html(None))


if __name__ == "__main__":
    unittest.main()
