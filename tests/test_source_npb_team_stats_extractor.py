"""Tests for src/source_npb_team_stats_extractor.py — NOMOTOKE-PLAYER-
STATS-FROM-NPB-001."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.source_npb_team_stats_extractor import (
    find_player_row,
    parse_npb_team_stats_html,
    stats_card_payload,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "npb_stats"
BATTING = FIXTURE_DIR / "2026_giants_batting.html"
PITCHING = FIXTURE_DIR / "2026_giants_pitching.html"


class NpbTeamStatsParserTests(unittest.TestCase):
    def test_batting_parses_to_player_dict(self):
        parsed = parse_npb_team_stats_html(BATTING.read_text(encoding="utf-8"))
        self.assertIsNotNone(parsed)
        # 47 players observed in the 2026 5/7 fixture.
        self.assertGreater(len(parsed), 30)

    def test_batting_columns_include_打率_本塁打(self):
        parsed = parse_npb_team_stats_html(BATTING.read_text(encoding="utf-8"))
        any_record = next(iter(parsed.values()))
        for key in ("打率", "本塁打", "打点", "試合"):
            self.assertIn(key, any_record)

    def test_pitching_parses_to_player_dict(self):
        parsed = parse_npb_team_stats_html(PITCHING.read_text(encoding="utf-8"))
        self.assertIsNotNone(parsed)
        self.assertGreater(len(parsed), 5)

    def test_find_player_row_kanji_no_space(self):
        parsed = parse_npb_team_stats_html(BATTING.read_text(encoding="utf-8"))
        hit = find_player_row(parsed, "石塚裕惺")
        self.assertIsNotNone(hit)
        normalized, record = hit
        self.assertEqual(normalized, "石塚裕惺")
        # Rendered name preserves NPB's space.
        self.assertIn(" ", record["__rendered_name__"])

    def test_find_player_row_with_space(self):
        parsed = parse_npb_team_stats_html(BATTING.read_text(encoding="utf-8"))
        hit = find_player_row(parsed, "石塚 裕惺")
        self.assertIsNotNone(hit)

    def test_find_player_row_unknown_returns_none(self):
        parsed = parse_npb_team_stats_html(BATTING.read_text(encoding="utf-8"))
        self.assertIsNone(find_player_row(parsed, "存在しない選手"))

    def test_invalid_html_returns_none(self):
        self.assertIsNone(parse_npb_team_stats_html(""))
        self.assertIsNone(parse_npb_team_stats_html("<html>no table</html>"))
        self.assertIsNone(parse_npb_team_stats_html(None))  # type: ignore[arg-type]

    def test_stats_card_payload_shape(self):
        parsed = parse_npb_team_stats_html(BATTING.read_text(encoding="utf-8"))
        _, rec = find_player_row(parsed, "石塚裕惺")
        payload = stats_card_payload(
            rendered_name=rec["__rendered_name__"],
            record=rec,
            stat_kind="batting",
            date_label="2026年5月7日",
            source_url="https://npb.jp/bis/2026/stats/idb1_g.html",
        )
        self.assertEqual(payload["team_name"], "巨人")
        self.assertEqual(payload["stat_kind"], "batting")
        self.assertIn("選手", payload["stats_columns"])
        self.assertIn("打率", payload["stats_columns"])
        self.assertEqual(len(payload["stats_rows"]), 1)
        self.assertNotIn("__rendered_name__", payload["stats_rows"][0])

    def test_stats_card_payload_renders_via_player_stats_card(self):
        # End-to-end: parser → payload → renderer produces a clean card.
        import os
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import render_player_stats_card

        parsed = parse_npb_team_stats_html(BATTING.read_text(encoding="utf-8"))
        _, rec = find_player_row(parsed, "石塚裕惺")
        payload = stats_card_payload(
            rendered_name=rec["__rendered_name__"],
            record=rec,
            stat_kind="batting",
            date_label="2026年5月7日",
            source_url="https://npb.jp/bis/2026/stats/idb1_g.html",
        )
        result = render_player_stats_card(payload)
        self.assertTrue(result["validation_ok"])
        body = result["content_html"]
        self.assertIn("打率", body)
        self.assertIn("本塁打", body)
        self.assertIn("石塚", body)


if __name__ == "__main__":
    unittest.main()
