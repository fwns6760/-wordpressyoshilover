"""Tests for src/source_yahoo_schedule_extractor.py — NOMOTOKE-POSTGAME-
AUTO-001."""

from __future__ import annotations

import unittest

from src.source_yahoo_schedule_extractor import (
    GIANTS_TEAM_TOKENS,
    find_giants_completed_games,
    find_giants_games,
    find_giants_pregame_games,
)


def _game_block(*, gid, home, away, completed=True):
    """Build a synthetic schedule game block matching Yahoo's HTML."""
    final_marker = "試合終了" if completed else ""
    return (
        f'<a class="bb-score__content" href="/npb/game/{gid}/index" data-ylk="">'
        f'  <p class="bb-score__description">'
        f'    <span class="bb-score__venue">東京ドーム</span>'
        f'  </p>'
        f'  <div class="bb-score__team">'
        f'    <p class="bb-score__homeLogo bb-score__homeLogo--npbTeam1">{home}</p>'
        f'    <p class="bb-score__awayLogo bb-score__awayLogo--npbTeam2">{away}</p>'
        f'  </div>'
        f'  <div class="bb-score__info">{final_marker}</div>'
        f"</a>"
    )


class GiantsCompletedGameDetectionTests(unittest.TestCase):
    def test_giants_home_completed_detected(self):
        html = _game_block(gid="1234", home="巨人", away="ヤクルト", completed=True)
        games = find_giants_completed_games(html)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["game_id"], "1234")
        self.assertEqual(games[0]["home"], "巨人")
        self.assertEqual(games[0]["away"], "ヤクルト")
        self.assertTrue(games[0]["is_completed"])
        self.assertTrue(games[0]["url"].endswith("/npb/game/1234/index"))

    def test_giants_away_completed_detected(self):
        html = _game_block(gid="5678", home="阪神", away="巨人", completed=True)
        games = find_giants_completed_games(html)
        self.assertEqual(len(games), 1)

    def test_non_giants_game_filtered_out(self):
        html = (
            _game_block(gid="111", home="阪神", away="広島", completed=True)
            + _game_block(gid="222", home="中日", away="DeNA", completed=True)
        )
        self.assertEqual(find_giants_completed_games(html), [])

    def test_pregame_giants_game_excluded_from_completed(self):
        # find_giants_completed_games is now strict — pregame games are
        # not returned (use find_giants_games for the unfiltered list).
        html = _game_block(gid="999", home="巨人", away="中日", completed=False)
        self.assertEqual(find_giants_completed_games(html), [])
        all_games = find_giants_games(html)
        self.assertEqual(len(all_games), 1)
        self.assertFalse(all_games[0]["is_completed"])
        self.assertFalse(all_games[0]["is_cancelled"])

    def test_pregame_helper_returns_only_pregame(self):
        html = (
            _game_block(gid="888", home="巨人", away="ヤクルト", completed=True)
            + _game_block(gid="999", home="巨人", away="中日", completed=False)
        )
        pregame = find_giants_pregame_games(html)
        self.assertEqual(len(pregame), 1)
        self.assertEqual(pregame[0]["game_id"], "999")
        self.assertFalse(pregame[0]["is_completed"])

    def test_multiple_giants_games_all_returned(self):
        html = (
            _game_block(gid="11", home="巨人", away="ヤクルト", completed=True)
            + _game_block(gid="22", home="阪神", away="広島", completed=True)
            + _game_block(gid="33", home="中日", away="巨人", completed=True)
        )
        games = find_giants_completed_games(html)
        self.assertEqual(len(games), 2)
        self.assertEqual({g["game_id"] for g in games}, {"11", "33"})

    def test_empty_or_invalid_html(self):
        self.assertEqual(find_giants_completed_games(""), [])
        self.assertEqual(find_giants_completed_games(None), [])  # type: ignore
        self.assertEqual(find_giants_completed_games("<html>no games</html>"), [])

    def test_cancelled_game_not_completed(self):
        # 中止 + 試合終了 stamp shouldn't count as completed.
        block = (
            '<a class="bb-score__content" href="/npb/game/77/index">'
            '<p class="bb-score__homeLogo">巨人</p>'
            '<p class="bb-score__awayLogo">阪神</p>'
            '中止 試合終了'
            '</a>'
        )
        completed = find_giants_completed_games(block)
        self.assertEqual(completed, [])
        all_games = find_giants_games(block)
        self.assertEqual(len(all_games), 1)
        self.assertTrue(all_games[0]["is_cancelled"])
        self.assertFalse(all_games[0]["is_completed"])
        self.assertEqual(find_giants_pregame_games(block), [])  # cancelled = not pregame

    def test_substring_終了_alone_does_not_mark_completed(self):
        # bare 終了 (e.g. 受付終了 in news widget) must not trigger the
        # completed marker — required full 試合終了.
        block = (
            '<a class="bb-score__content" href="/npb/game/88/index">'
            '<p class="bb-score__homeLogo">巨人</p>'
            '<p class="bb-score__awayLogo">中日</p>'
            'チケット販売は受付終了'
            '</a>'
        )
        self.assertEqual(find_giants_completed_games(block), [])

    def test_giants_team_tokens_constant(self):
        self.assertIn("巨人", GIANTS_TEAM_TOKENS)
        self.assertIn("読売", GIANTS_TEAM_TOKENS)


if __name__ == "__main__":
    unittest.main()
