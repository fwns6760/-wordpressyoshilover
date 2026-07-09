"""試合日 gate (2026-07-02「野球はない日をうまくやりたい」) のテスト。"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src import game_day_gate as gate

JST = timezone(timedelta(hours=9))

# 2026-07-04 (土) デーゲーム 14:00 / 07-05 (日) 巨人戦なし / 07-06 (月) 終了済表示
_FIX_DAY_GAME = (
    '<div>7/4（土）<span class="team1">巨人</span><span class="team2">中日</span>'
    '<span class="score1"></span><span class="time">14:00</span><span class="place">東京ドーム</span></div>'
)
_FIX_NO_GIANTS = (
    '<div>7/5（日）<span class="team1">阪神</span><span class="team2">広島</span>'
    '<span class="score1"></span><span class="time">18:00</span><span class="place">甲子園</span></div>'
)
_FIX_FINISHED = (
    '<div>7/6（月）<span class="team1">巨人</span><span class="team2">中日</span>'
    '<span class="score1">3</span><span class="place">東京ドーム</span></div>'
)
_FIX_NIGHT = (
    '<div>7/4（土）<span class="team1">巨人</span><span class="team2">ヤクルト</span>'
    '<span class="score1"></span><span class="time">18:00</span><span class="place">神宮</span></div>'
)


def _dt(day: int, h: int, m: int = 0) -> datetime:
    return datetime(2026, 7, day, h, m, tzinfo=JST)


class FindTodayGameTests(unittest.TestCase):
    def test_day_game_start_parsed(self):
        g = gate.find_today_game(_FIX_DAY_GAME, _dt(4, 10))
        self.assertIsNotNone(g)
        self.assertEqual(g["start"].hour, 14)

    def test_no_giants_game_returns_none(self):
        self.assertIsNone(gate.find_today_game(_FIX_NO_GIANTS, _dt(5, 10)))

    def test_finished_game_listed_without_start(self):
        g = gate.find_today_game(_FIX_FINISHED, _dt(6, 22))
        self.assertIsNotNone(g)
        self.assertIsNone(g["start"])


class ShouldProceedTests(unittest.TestCase):
    def test_no_game_day_skips_both_windows(self):
        for w in ("lineup", "game"):
            ok, reason = gate.should_proceed(w, _dt(5, 17, 20), fetch_fn=lambda now: _FIX_NO_GIANTS)
            self.assertFalse(ok, reason)

    def test_day_game_lineup_window_shifts_to_noon(self):
        fetch = lambda now: _FIX_DAY_GAME  # noqa: E731
        ok, _ = gate.should_proceed("lineup", _dt(4, 12, 20), fetch_fn=fetch)
        self.assertTrue(ok)   # 14時開始 → 12:20 は窓内
        ok, _ = gate.should_proceed("lineup", _dt(4, 17, 20), fetch_fn=fetch)
        self.assertFalse(ok)  # 従来の 17:20 は試合中 → スタメン便不要

    def test_day_game_game_window(self):
        fetch = lambda now: _FIX_DAY_GAME  # noqa: E731
        self.assertTrue(gate.should_proceed("game", _dt(4, 14, 30), fetch_fn=fetch)[0])
        self.assertTrue(gate.should_proceed("game", _dt(4, 13, 45), fetch_fn=fetch)[0])
        self.assertFalse(gate.should_proceed("game", _dt(4, 19, 0), fetch_fn=fetch)[0])   # start+4h 超
        self.assertFalse(gate.should_proceed("game", _dt(4, 13, 30), fetch_fn=fetch)[0])  # start-15m 前

    def test_night_game_matches_legacy_behavior(self):
        fetch = lambda now: _FIX_NIGHT  # noqa: E731
        self.assertTrue(gate.should_proceed("lineup", _dt(4, 17, 20), fetch_fn=fetch)[0])
        self.assertTrue(gate.should_proceed("game", _dt(4, 21, 45), fetch_fn=fetch)[0])
        self.assertFalse(gate.should_proceed("game", _dt(4, 22, 15), fetch_fn=fetch)[0])

    def test_night_game_lineup_window_opens_4h_before(self):
        # 18:00 開始 → lineup 窓 [14:00, 18:00)。14 時便も通す (user 2026-07-09)。
        fetch = lambda now: _FIX_NIGHT  # noqa: E731
        self.assertTrue(gate.should_proceed("lineup", _dt(4, 14, 0), fetch_fn=fetch)[0])
        self.assertTrue(gate.should_proceed("lineup", _dt(4, 16, 0), fetch_fn=fetch)[0])
        self.assertFalse(gate.should_proceed("lineup", _dt(4, 13, 59), fetch_fn=fetch)[0])
        self.assertFalse(gate.should_proceed("lineup", _dt(4, 18, 0), fetch_fn=fetch)[0])

    def test_finished_game_fails_open_to_legacy_window(self):
        fetch = lambda now: _FIX_FINISHED  # noqa: E731
        self.assertTrue(gate.should_proceed("game", _dt(6, 21, 0), fetch_fn=fetch)[0])
        self.assertFalse(gate.should_proceed("game", _dt(6, 13, 0), fetch_fn=fetch)[0])

    def test_fetch_error_fails_open_to_legacy_window(self):
        def boom(now):
            raise RuntimeError("npb down")
        self.assertTrue(gate.should_proceed("lineup", _dt(4, 17, 20), fetch_fn=boom)[0])
        self.assertFalse(gate.should_proceed("lineup", _dt(4, 12, 20), fetch_fn=boom)[0])

    def test_unknown_window_passes(self):
        self.assertTrue(gate.should_proceed("", _dt(5, 12, 0), fetch_fn=lambda now: "")[0])


class EvaluateStartTimeTests(unittest.TestCase):
    """477: evaluate() は開始時刻も返す (デイゲーム モード自動注入用)。"""

    def test_evaluate_returns_start_for_day_game(self):
        ok, _, start = gate.evaluate("game", _dt(4, 14, 30), fetch_fn=lambda now: _FIX_DAY_GAME)
        self.assertTrue(ok)
        self.assertEqual((start.hour, start.minute), (14, 0))

    def test_evaluate_start_none_when_no_game_or_unknown(self):
        _, _, start = gate.evaluate("game", _dt(5, 14, 30), fetch_fn=lambda now: _FIX_NO_GIANTS)
        self.assertIsNone(start)
        _, _, start2 = gate.evaluate("game", _dt(6, 18, 0), fetch_fn=lambda now: _FIX_FINISHED)
        self.assertIsNone(start2)


class DayGameModeInjectionTests(unittest.TestCase):
    """477 narrow: NPB 開始時刻 → EXTRA_GAME env の in-process 自動注入。"""

    def setUp(self):
        import os
        from src.tools import run_x_post_mail as r
        from src import x_post_mail_lane as lane
        self.r = r
        self.lane = lane
        self.os = os
        self._saved = {
            k: os.environ.get(k)
            for k in (lane.EXTRA_GAME_DATE_ENV, lane.EXTRA_GAME_START_ENV, lane.EXTRA_GAME_END_ENV)
        }
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                self.os.environ.pop(k, None)
            else:
                self.os.environ[k] = v

    def test_day_game_injects_window(self):
        # 日曜 13:30 開始 → 13:15-17:30 が試合中扱い
        injected = self.r._maybe_inject_day_game_mode(_dt(5, 13, 30), _dt(5, 13, 20))
        self.assertTrue(injected)
        self.assertEqual(self.os.environ[self.lane.EXTRA_GAME_DATE_ENV], "2026-07-05")
        self.assertEqual(self.os.environ[self.lane.EXTRA_GAME_START_ENV], "13:15")
        self.assertEqual(self.os.environ[self.lane.EXTRA_GAME_END_ENV], "17:30")
        self.assertTrue(self.lane.is_extra_game_window(_dt(5, 14, 0)))
        self.assertFalse(self.lane.is_extra_game_window(_dt(5, 18, 0)))

    def test_night_game_does_not_inject(self):
        # ナイター (18:00) は壁時計バンドが既にカバー → 挙動不変
        self.assertFalse(self.r._maybe_inject_day_game_mode(_dt(4, 18, 0), _dt(4, 18, 30)))
        self.assertNotIn(self.lane.EXTRA_GAME_DATE_ENV, self.os.environ)

    def test_manual_env_for_today_wins(self):
        self.os.environ[self.lane.EXTRA_GAME_DATE_ENV] = "2026-07-04"
        self.os.environ[self.lane.EXTRA_GAME_START_ENV] = "13:45"
        self.os.environ[self.lane.EXTRA_GAME_END_ENV] = "18:00"
        self.assertFalse(self.r._maybe_inject_day_game_mode(_dt(4, 14, 0), _dt(4, 14, 0)))
        self.assertEqual(self.os.environ[self.lane.EXTRA_GAME_START_ENV], "13:45")

    def test_stale_env_date_is_overridden(self):
        self.os.environ[self.lane.EXTRA_GAME_DATE_ENV] = "2026-06-07"
        self.assertTrue(self.r._maybe_inject_day_game_mode(_dt(5, 13, 30), _dt(5, 13, 20)))
        self.assertEqual(self.os.environ[self.lane.EXTRA_GAME_DATE_ENV], "2026-07-05")

    def test_none_start_does_not_inject(self):
        self.assertFalse(self.r._maybe_inject_day_game_mode(None, _dt(5, 13, 20)))


if __name__ == "__main__":
    unittest.main()
