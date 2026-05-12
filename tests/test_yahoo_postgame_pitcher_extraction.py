"""Unit tests for the Phase 2E extension of
``src/source_yahoo_boxscore_extractor.py`` — 勝利投手 / 敗戦投手 / セーブ
row extraction from Yahoo Sportsnavi `/index` HTML.

Uses a saved 2026-05-10 阪神 vs DeNA fixture (selected because it has
the gameTable block with all three pitcher rows; the team isn't 巨人
on purpose so the test exercises the structural parse separately from
the ``giants_facts()`` filter).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from src.source_yahoo_boxscore_extractor import parse_yahoo_game_html


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "yahoo_postgame_2021038841_完了試合.html"


class YahooPostgamePitcherExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE_PATH.exists():
            raise unittest.SkipTest(f"fixture missing: {FIXTURE_PATH}")
        cls.html = FIXTURE_PATH.read_text(encoding="utf-8")

    def test_winning_pitcher_extracted(self):
        facts = parse_yahoo_game_html(self.html)
        self.assertIsNotNone(facts)
        self.assertEqual(facts.winning_pitcher, {"team": "阪神", "name": "才木", "record": "4勝1敗0S"})

    def test_losing_pitcher_extracted(self):
        facts = parse_yahoo_game_html(self.html)
        self.assertIsNotNone(facts)
        self.assertEqual(facts.losing_pitcher, {"team": "DeNA", "name": "石田裕", "record": "2勝4敗0S"})

    def test_save_pitcher_extracted(self):
        facts = parse_yahoo_game_html(self.html)
        self.assertIsNotNone(facts)
        self.assertEqual(facts.save_pitcher, {"team": "阪神", "name": "ドリス", "record": "0勝1敗5S"})

    def test_giants_facts_carries_pitcher_dicts(self):
        """Even when 巨人 is absent, ``giants_facts()`` returns ``{}``;
        this asserts the pitcher fields exist on the dataclass so the
        renderer can introspect them unconditionally."""
        facts = parse_yahoo_game_html(self.html)
        self.assertIsNotNone(facts)
        # Pitcher fields are set on the dataclass (giants_facts() may
        # be empty since 阪神 vs DeNA has no 巨人 — that's fine).
        self.assertIsInstance(facts.winning_pitcher, dict)
        self.assertIsInstance(facts.losing_pitcher, dict)
        self.assertIsInstance(facts.save_pitcher, dict)


if __name__ == "__main__":
    unittest.main()
