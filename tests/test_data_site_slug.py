"""Tests for data_site_slug (ticket 443/444 Phase 1.0)."""

from __future__ import annotations

import unittest

from src.data_site_slug import player_slug, known_player_names


class PlayerSlugTests(unittest.TestCase):
    def test_phase1_3_players(self) -> None:
        """Phase 1.0 対象 3 名の slug がぶれない。"""
        self.assertEqual(player_slug("吉川尚輝"), "yoshikawa-naoki")
        self.assertEqual(player_slug("坂本勇人"), "sakamoto-hayato")
        self.assertEqual(player_slug("丸佳浩"), "maru-yoshihiro")

    def test_full_width_space_normalized(self) -> None:
        """roster の姓名間 全角空白を吸収。"""
        self.assertEqual(player_slug("坂本　勇人"), "sakamoto-hayato")
        self.assertEqual(player_slug("丸 佳浩"), "maru-yoshihiro")

    def test_katakana_foreign_player(self) -> None:
        self.assertEqual(player_slug("マルティネス"), "martinez")
        self.assertEqual(player_slug("キャベッジ"), "cabbage")

    def test_manager_coach(self) -> None:
        self.assertEqual(player_slug("阿部慎之助"), "abe-shinnosuke")
        self.assertEqual(player_slug("橋上秀樹"), "hashigami-hideki")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(player_slug(""), "")
        self.assertEqual(player_slug(None), "")  # type: ignore[arg-type]

    def test_unknown_player_fallback(self) -> None:
        """未知 player は normalized 内容で fallback (例外投げない)。"""
        out = player_slug("田中ABC")
        self.assertIsInstance(out, str)
        self.assertTrue(len(out) > 0)

    def test_known_player_names_includes_phase1(self) -> None:
        names = known_player_names()
        self.assertIn("吉川尚輝", names)
        self.assertIn("坂本勇人", names)
        self.assertIn("丸佳浩", names)
        self.assertGreaterEqual(len(names), 3)


if __name__ == "__main__":
    unittest.main()
