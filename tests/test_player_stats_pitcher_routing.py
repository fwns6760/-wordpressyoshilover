"""2026-05-14 67239 incident regression guard.

A pitcher who also has a batting record (e.g. 戸郷翔征 with a single
plate appearance) must not show batting stats — the rendered block has
to route to the pitching bucket whenever roster ``position`` is 投手.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from src.tools import manual_intake as mi


SAMPLE_ROSTER = [
    {
        "name": "戸郷翔征",
        "aliases": ["戸郷翔征", "戸郷 翔征"],
        "role": "player",
        "position": "投手",
        "jersey_number": "20",
        "active": True,
    },
    {
        "name": "岡本和真",
        "aliases": ["岡本和真", "岡本 和真"],
        "role": "player",
        "position": "一塁",
        "jersey_number": "25",
        "active": True,
    },
    {
        "name": "阿部慎之助",
        "aliases": ["阿部慎之助", "阿部監督"],
        "role": "manager",
        "position": "監督",
        "jersey_number": "83",
        "active": True,
    },
]


class PitcherNameSetTests(unittest.TestCase):
    def test_pitcher_set_captures_full_name_and_alias_variants(self):
        with patch(
            "src.nomotoke_card_renderer._load_giants_roster",
            return_value=SAMPLE_ROSTER,
        ):
            pitchers = mi._build_pitcher_name_set()
        self.assertIn("戸郷翔征", pitchers)
        self.assertNotIn("岡本和真", pitchers)
        self.assertNotIn("阿部慎之助", pitchers)

    def test_stats_key_is_pitcher_strips_marker(self):
        pitchers = {"戸郷翔征"}
        self.assertTrue(mi._stats_key_is_pitcher("戸郷翔征", pitchers))
        self.assertTrue(mi._stats_key_is_pitcher("*戸郷翔征", pitchers))
        self.assertTrue(mi._stats_key_is_pitcher("戸郷 翔征", pitchers))
        self.assertFalse(mi._stats_key_is_pitcher("岡本和真", pitchers))


class StatsLookupRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        # Freeze cache so refresh doesn't hit the network during tests.
        self._cache_backup = mi._PLAYER_STATS_CACHE.copy()
        mi._PLAYER_STATS_CACHE.clear()
        mi._PLAYER_STATS_CACHE.update({
            "batting": {
                "戸郷翔征": {
                    "__rendered_name__": "戸郷 翔征",
                    "打率": ".333",
                    "本塁打": "0",
                    "打点": "0",
                    "盗塁": "0",
                },
                "岡本和真": {
                    "__rendered_name__": "岡本 和真",
                    "打率": ".298",
                    "本塁打": "12",
                    "打点": "35",
                    "盗塁": "2",
                },
            },
            "pitching": {
                "戸郷翔征": {
                    "__rendered_name__": "戸郷 翔征",
                    "登板": "5",
                    "勝": "1",
                    "敗": "1",
                    "防御率": "2.50",
                    "奪三振": "25",
                },
            },
            "fetched_at": time.time(),
        })

    def tearDown(self) -> None:
        mi._PLAYER_STATS_CACHE.clear()
        mi._PLAYER_STATS_CACHE.update(self._cache_backup)

    def test_pitcher_collision_routes_to_pitching_record(self):
        with patch(
            "src.nomotoke_card_renderer._load_giants_roster",
            return_value=SAMPLE_ROSTER,
        ):
            stats = mi._get_player_stats_lookup()
        self.assertEqual(stats["戸郷翔征"]["kind"], "pitching")
        self.assertIn("防御率", stats["戸郷翔征"]["record"])
        self.assertNotIn("打率", stats["戸郷翔征"]["record"])

    def test_batter_uses_batting_record(self):
        with patch(
            "src.nomotoke_card_renderer._load_giants_roster",
            return_value=SAMPLE_ROSTER,
        ):
            stats = mi._get_player_stats_lookup()
        self.assertEqual(stats["岡本和真"]["kind"], "batting")
        self.assertEqual(stats["岡本和真"]["record"]["打率"], ".298")

    def test_unknown_role_falls_back_to_batting_when_only_batting_exists(self):
        mi._PLAYER_STATS_CACHE["batting"]["未掲載選手"] = {
            "__rendered_name__": "未掲載 選手",
            "打率": ".250",
            "本塁打": "1",
            "打点": "2",
            "盗塁": "0",
        }
        with patch(
            "src.nomotoke_card_renderer._load_giants_roster",
            return_value=SAMPLE_ROSTER,
        ):
            stats = mi._get_player_stats_lookup()
        # not on roster → falls back to whichever bucket has the name
        self.assertEqual(stats["未掲載選手"]["kind"], "batting")


class PlayerStatsBlockEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self._cache_backup = mi._PLAYER_STATS_CACHE.copy()
        mi._PLAYER_STATS_CACHE.clear()
        mi._PLAYER_STATS_CACHE.update({
            "batting": {
                "戸郷翔征": {
                    "__rendered_name__": "戸郷 翔征",
                    "打率": ".333",
                    "本塁打": "0",
                    "打点": "0",
                    "盗塁": "0",
                },
            },
            "pitching": {
                "戸郷翔征": {
                    "__rendered_name__": "戸郷 翔征",
                    "登板": "5",
                    "勝": "1",
                    "敗": "1",
                    "防御率": "2.50",
                    "奪三振": "25",
                },
            },
            "fetched_at": time.time(),
        })

    def tearDown(self) -> None:
        mi._PLAYER_STATS_CACHE.clear()
        mi._PLAYER_STATS_CACHE.update(self._cache_backup)

    def test_block_for_pitcher_renders_pitching_columns(self):
        with patch(
            "src.nomotoke_card_renderer._load_giants_roster",
            return_value=SAMPLE_ROSTER,
        ):
            block = mi._build_player_stats_block("戸郷翔征が好投。")
        self.assertIn("戸郷", block)
        self.assertIn("防御率", block)
        self.assertIn("2.50", block)
        # Pitcher row must NOT carry batting columns.
        self.assertNotIn(".333", block)


if __name__ == "__main__":
    unittest.main()
