"""Tests for src/title_template_assembler.py — 330-QA のもとけ pattern."""

from __future__ import annotations

import os
import unittest

from src.title_template_assembler import (
    assemble_nomotoke_title,
    nomotoke_title_template_enabled,
)


class EnablementTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("ENABLE_NOMOTOKE_TITLE_TEMPLATE", None)

    def tearDown(self):
        os.environ.pop("ENABLE_NOMOTOKE_TITLE_TEMPLATE", None)

    def test_default_enabled(self):
        self.assertTrue(nomotoke_title_template_enabled())

    def test_disabled_returns_none(self):
        os.environ["ENABLE_NOMOTOKE_TITLE_TEMPLATE"] = "0"
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="dummy",
            source_body="戸郷翔征「自分らしく投げるだけ」",
            player_name="戸郷翔征",
            role="投手",
        )
        self.assertIsNone(result)


class PatternAPlayerCommentTests(unittest.TestCase):
    def test_basic_quote_assembly(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="戸郷翔征 試合後コメント",
            source_body="戸郷翔征選手「自分らしく投げるだけ」と前向きに語った。",
            player_name="戸郷翔征",
            role="投手",
        )
        self.assertEqual(result, "戸郷翔征「自分らしく投げるだけ」")

    def test_long_quote_trimmed(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body="戸郷「" + "あ" * 50 + "」",
            player_name="戸郷",
            role="投手",
        )
        self.assertIsNotNone(result)
        self.assertIn("戸郷「", result)
        self.assertIn("…」", result)

    def test_no_quote_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="戸郷翔征 試合後コメント",
            source_body="戸郷翔征が無失点で投球を続けた。",
            player_name="戸郷翔征",
            role="投手",
        )
        self.assertIsNone(result)

    def test_no_name_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body="「自分らしく」",
            player_name="",
            role="",
        )
        self.assertIsNone(result)


class PatternAManagerTests(unittest.TestCase):
    def test_manager_subtype_appends_manager_suffix(self):
        result = assemble_nomotoke_title(
            article_subtype="manager",
            existing_title="阿部 試合後",
            source_body="阿部監督「勝負をかけた」と語った。",
            player_name="阿部",
            role="監督",
        )
        self.assertEqual(result, "阿部監督「勝負をかけた」")

    def test_manager_name_already_with_suffix(self):
        result = assemble_nomotoke_title(
            article_subtype="manager",
            existing_title="d",
            source_body="阿部監督「勝負をかけた」",
            player_name="阿部監督",
            role="監督",
        )
        # already ends with 監督 → no duplication
        self.assertEqual(result, "阿部監督「勝負をかけた」")


class PatternACoachTests(unittest.TestCase):
    def test_coach_suffix(self):
        result = assemble_nomotoke_title(
            article_subtype="coach_comment",
            existing_title="d",
            source_body="杉内投手チーフコーチ「なんとか勝たせてあげたい」",
            player_name="杉内",
            role="コーチ",
        )
        self.assertIn("杉内", result)
        self.assertIn("「なんとか勝たせてあげたい」", result)


class PatternBPostgameTests(unittest.TestCase):
    def test_sayonara_modifier(self):
        result = assemble_nomotoke_title(
            article_subtype="postgame",
            existing_title="d",
            source_body="佐々木俊輔が劇的サヨナラ2ランで勝利を呼び込んだ。",
            player_name="佐々木俊輔",
            role="選手",
        )
        self.assertIsNotNone(result)
        self.assertIn("サヨナラ", result)
        self.assertIn("巨人・佐々木俊輔", result)

    def test_no_modifier_no_result_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="postgame",
            existing_title="d",
            source_body="特になし",
            player_name="佐々木俊輔",
            role="選手",
        )
        self.assertIsNone(result)


class PatternEBroadcastTests(unittest.TestCase):
    def test_broadcast_with_date_and_opponent(self):
        result = assemble_nomotoke_title(
            article_subtype="broadcast",
            existing_title="d",
            metadata={
                "event_date_label": "5月13日(水)",
                "opponent": "広島",
            },
        )
        self.assertEqual(
            result, "5月13日(水)「巨人vs.広島」【テレビ・ネット中継】"
        )

    def test_broadcast_missing_facts_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="broadcast",
            existing_title="d",
            metadata={"opponent": "広島"},
        )
        self.assertIsNone(result)


class UnsupportedSubtypeTests(unittest.TestCase):
    def test_unknown_subtype_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="general",
            existing_title="d",
            source_body="戸郷「a」",
            player_name="戸郷",
        )
        self.assertIsNone(result)

    def test_lineup_not_yet_supported(self):
        result = assemble_nomotoke_title(
            article_subtype="lineup",
            existing_title="d",
            source_body="戸郷",
            player_name="戸郷",
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
