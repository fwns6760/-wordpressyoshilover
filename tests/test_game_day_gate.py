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


if __name__ == "__main__":
    unittest.main()
