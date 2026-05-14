"""Tests for Pattern R2 extension (post 67262 fix): 、 separator + optional descriptor."""

from __future__ import annotations

import unittest

from src.title_template_assembler import _assemble_pattern_R_reaction


class PatternR2_67262Tests(unittest.TestCase):
    """Pattern R2: subject、(任意descriptor)target の fact (任意を) verb「q1」「q2」"""

    def test_67262_actual_source_with_descriptor_and_no_wo(self):
        # post 67262 actual source: descriptor "幼なじみ" + を 欠落
        source = '【巨人】田中将大、"幼なじみ"坂本勇人の通算300号祝福 「漫画の世界」「キセキやん」の声'
        result = _assemble_pattern_R_reaction(
            source_title=source,
            source_body="",
            summary="",
        )
        self.assertEqual(
            result,
            "田中将大が坂本勇人の通算300号を祝福「漫画の世界」「キセキやん」",
        )

    def test_67262_curly_quote_descriptor_variant(self):
        # U+201C/U+201D curly double quote の descriptor も match
        source = "【巨人】田中将大、“幼なじみ”坂本勇人の通算300号祝福「漫画の世界」「キセキやん」"
        result = _assemble_pattern_R_reaction(
            source_title=source,
            source_body="",
            summary="",
        )
        self.assertIn("田中将大が坂本勇人", result)
        self.assertIn("祝福", result)
        self.assertIn("漫画の世界", result)
        self.assertIn("キセキやん", result)

    def test_r2_no_descriptor(self):
        # descriptor 無しでも `、` separator + を 任意 で match
        source = "田中将大、坂本勇人の300号を祝福「漫画の世界」「キセキやん」"
        result = _assemble_pattern_R_reaction(
            source_title=source,
            source_body="",
            summary="",
        )
        self.assertEqual(
            result,
            "田中将大が坂本勇人の300号を祝福「漫画の世界」「キセキやん」",
        )

    def test_r1_existing_case_still_works(self):
        # 既存 R: が separator + を 必須
        source = "岡本和真が坂本勇人の劇的通算300号を祝福「さすが」「エンターテイナー」"
        result = _assemble_pattern_R_reaction(
            source_title=source,
            source_body="",
            summary="",
        )
        self.assertEqual(
            result,
            "岡本和真が坂本勇人の劇的通算300号を祝福「さすが」「エンターテイナー」",
        )

    def test_r2_with_japanese_bracket_descriptor(self):
        # 『友人』のような 『』 descriptor も match
        source = "戸郷翔征、『友人』菅野智之の300勝祝福「すごい」「あこがれ」"
        result = _assemble_pattern_R_reaction(
            source_title=source,
            source_body="",
            summary="",
        )
        self.assertIn("戸郷翔征が菅野智之", result)
        self.assertIn("祝福", result)

    def test_r2_extracted_from_body_when_title_lacks(self):
        result = _assemble_pattern_R_reaction(
            source_title="巨人、坂本300号関連",
            source_body='田中将大、"幼なじみ"坂本勇人の通算300号祝福「漫画の世界」「キセキやん」',
            summary="",
        )
        self.assertIn("田中将大が坂本勇人", result)

    def test_no_match_returns_empty(self):
        source = "通常の記事タイトル"
        self.assertEqual(
            _assemble_pattern_R_reaction(
                source_title=source, source_body="", summary=""
            ),
            "",
        )

    def test_r2_other_verbs(self):
        # verb は祝福 だけでなく他の reaction verbs も match
        for verb in ("称賛", "絶賛", "感心", "歓喜"):
            source = f"田中将大、坂本勇人の300号{verb}「漫画の世界」「キセキやん」"
            result = _assemble_pattern_R_reaction(
                source_title=source, source_body="", summary=""
            )
            self.assertIn(verb, result, msg=f"verb={verb} not matched")
            self.assertIn("田中将大が坂本勇人", result, msg=f"verb={verb}")


if __name__ == "__main__":
    unittest.main()
