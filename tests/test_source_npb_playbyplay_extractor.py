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


class ParseNPBPlaybyplayFullDetailTests(unittest.TestCase):
    """405 / 415 (b) Phase 1: 拡張 parser regression。"""

    @classmethod
    def setUpClass(cls):
        if not PBP_FIXTURE.exists():
            raise unittest.SkipTest(f"missing fixture: {PBP_FIXTURE}")
        cls.html = PBP_FIXTURE.read_text(encoding="utf-8")

    def test_returns_extended_event_list(self):
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 30, "30+ PA events expected for 9 innings")

    def test_extended_dict_shape(self):
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        first = events[0]
        for key in (
            "inning_no", "half", "team", "outs", "runner_state",
            "batter", "count", "count_balls", "count_strikes",
            "result", "current_pitcher",
        ):
            self.assertIn(key, first, f"missing key: {key}")

    def test_count_parsing(self):
        """count "3-2より" → balls=3, strikes=2 に分解できる。"""
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        # count field を持つ event がほぼ全 PA にある (空 count は除く)
        parseable = [
            ev for ev in events
            if ev.get("count_balls") is not None
            and ev.get("count_strikes") is not None
        ]
        self.assertGreater(len(parseable), 20, "30+ events のうち多くが count parse 可能")
        for ev in parseable:
            self.assertIsInstance(ev["count_balls"], int)
            self.assertIsInstance(ev["count_strikes"], int)
            self.assertGreaterEqual(ev["count_balls"], 0)
            self.assertLessEqual(ev["count_balls"], 3)
            self.assertGreaterEqual(ev["count_strikes"], 0)
            self.assertLessEqual(ev["count_strikes"], 2)

    def test_pitcher_tracking(self):
        """current_pitcher が 5/10 fixture の先発投手 (櫻井) を 1 回表 PA で track。"""
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        # 1 回表 巨人攻撃の 1 PA 目 → vs 中日先発 (櫻井 expect)
        first_giants_top = next(
            ev for ev in events
            if ev["inning_no"] == 1 and ev["half"] == "表" and ev["team"] == "巨人"
        )
        self.assertEqual(first_giants_top["current_pitcher"], "櫻井",
            "5/10 fixture の 1 回表先発は櫻井")

    def test_runner_state_normalize(self):
        """runner_state が 「無走者 = 空文字」 / 走者 case で適切に分類される。"""
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        runner_states = [ev.get("runner_state", "") for ev in events]
        # 一般的試合では 無走者 PA が最多 (1 番打者の先頭 PA 等)
        no_runner_count = sum(1 for s in runner_states if s == "")
        self.assertGreater(no_runner_count, 5, "9 イニング x 多 PA の中で無走者 PA 多数想定")

    def test_full_detail_none_for_empty(self):
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
        )
        self.assertIsNone(parse_npb_playbyplay_full_detail(""))
        self.assertIsNone(parse_npb_playbyplay_full_detail(None))


class RunnerStateHelpersTests(unittest.TestCase):
    """405 走者状況別 helper の挙動。"""

    @classmethod
    def setUpClass(cls):
        if not PBP_FIXTURE.exists():
            raise unittest.SkipTest(f"missing fixture: {PBP_FIXTURE}")
        cls.html = PBP_FIXTURE.read_text(encoding="utf-8")

    def test_extract_pa_with_runners_state_no_runners(self):
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
            extract_pa_with_runners_state,
            RUNNER_STATE_NO_RUNNERS,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        no_runners = extract_pa_with_runners_state(events, RUNNER_STATE_NO_RUNNERS)
        self.assertGreater(len(no_runners), 0)
        for ev in no_runners:
            self.assertEqual(ev["runner_state"], "")

    def test_extract_pa_first_pitch_decision(self):
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
            extract_pa_first_pitch_decision,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        first_pitch = extract_pa_first_pitch_decision(events)
        for ev in first_pitch:
            self.assertEqual(ev["count_balls"], 0)
            self.assertEqual(ev["count_strikes"], 0)

    def test_extract_pa_two_strike(self):
        from src.source_npb_playbyplay_extractor import (
            parse_npb_playbyplay_full_detail,
            extract_pa_two_strike,
        )
        events = parse_npb_playbyplay_full_detail(self.html)
        two_strike = extract_pa_two_strike(events)
        for ev in two_strike:
            self.assertEqual(ev["count_strikes"], 2)


if __name__ == "__main__":
    unittest.main()


class PitcherChangeIncomingTests(unittest.TestCase):
    """投手交代「A → B」で登板側 B を current_pitcher にする (交代前 A ではない)。"""

    def test_incoming_pitcher_after_change(self):
        from src.source_npb_playbyplay_extractor import parse_npb_playbyplay_full_detail
        html = (
            '<h5 name="com1-1" id="com1-1">1回表（巨人の攻撃）</h5><table>'
            '<tr><td colspan="5">（先発投手） <a href="/bis/players/1.html">櫻井</a></td></tr>'
            '<tr><td>0アウト</td><td>&nbsp;</td><td><a href="/bis/players/2.html">吉川</a></td>'
            '<td>0-0より</td><td>セカンドゴロ</td></tr>'
            '</table><table>'
            '<tr><td colspan="5">（投手交代） <a href="/bis/players/1.html">櫻井</a> → '
            '<a href="/bis/players/3.html">メヒア</a></td></tr>'
            '<tr><td>1アウト</td><td>&nbsp;</td><td><a href="/bis/players/4.html">岡本</a></td>'
            '<td>1-1より</td><td>見逃し三振</td></tr>'
            '</table>'
        )
        evs = parse_npb_playbyplay_full_detail(html)
        by_batter = {e["batter"]: e["current_pitcher"] for e in evs}
        self.assertEqual(by_batter["吉川"], "櫻井")   # 先発
        self.assertEqual(by_batter["岡本"], "メヒア")  # 交代後=登板側
        self.assertNotEqual(by_batter["岡本"], "櫻井")
