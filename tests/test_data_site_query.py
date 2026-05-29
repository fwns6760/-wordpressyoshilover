"""Tests for data_site_query venue split (ticket 447 Phase 1.0c venue)."""

from __future__ import annotations

import unittest

from src.data_site_query import giants_venue_from_game_id


class GiantsVenueFromGameIdTests(unittest.TestCase):
    """game_id (NPB.jp box score code `{home}-{away}-{no}`) → 巨人視点 home/away。"""

    def test_giants_home_left_code(self) -> None:
        # 巨人 code 'g' が左 (home) = 本拠地
        self.assertEqual(giants_venue_from_game_id("2026-03-27:g-t-01"), "home")
        self.assertEqual(giants_venue_from_game_id("2026-04-03:g-db-01"), "home")

    def test_giants_away_right_code(self) -> None:
        # 巨人 code 'g' が右 (away) = ビジター
        self.assertEqual(giants_venue_from_game_id("2026-03-31:d-g-01"), "away")
        self.assertEqual(giants_venue_from_game_id("2026-04-07:c-g-01"), "away")

    def test_non_giants_game_returns_none(self) -> None:
        # 巨人が含まれない試合 (リーグ全体 ingest 分) は None
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:db-s-01"))
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:c-d-01"))

    def test_malformed_returns_none(self) -> None:
        self.assertIsNone(giants_venue_from_game_id(""))
        self.assertIsNone(giants_venue_from_game_id("no-colon-here"))
        self.assertIsNone(giants_venue_from_game_id("2026-03-27:g"))


if __name__ == "__main__":
    unittest.main()
