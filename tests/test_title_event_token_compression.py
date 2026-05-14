"""Tests for compress_event_token_repetition (335-QA Phase 3 / Issue #8)."""

from __future__ import annotations

import unittest

from src.title_template_assembler import compress_event_token_repetition


class CompressEventTokenRepetitionTests(unittest.TestCase):
    def test_67169_actual_title_compresses_sayonara_axis(self):
        original = "「一生忘れない」巨人・坂本が逆転サヨナラ３ラン！通算３００号のメモリアル弾で２試合連続のサヨナラ勝…"
        result = compress_event_token_repetition(original)
        self.assertIn("逆転サヨナラ３ラン", result)
        self.assertNotIn("２試合連続のサヨナラ勝", result)
        self.assertIn("通算３００号", result)
        self.assertIn("メモリアル弾", result)

    def test_single_sayonara_unchanged(self):
        original = "巨人・坂本が逆転サヨナラ３ラン！通算３００号のメモリアル弾"
        result = compress_event_token_repetition(original)
        self.assertEqual(result, original)

    def test_two_kanshu_compresses_to_first(self):
        original = "戸郷翔征が完封勝利！4回完封の好投も含む快投"
        result = compress_event_token_repetition(original)
        self.assertIn("完封勝利", result)
        self.assertEqual(result.count("完封"), 1)

    def test_numeric_fact_preserved_alongside_sayonara(self):
        original = "坂本が通算300号のサヨナラホームラン！"
        result = compress_event_token_repetition(original)
        self.assertEqual(result, original)
        self.assertIn("通算300号", result)
        self.assertIn("サヨナラホームラン", result)

    def test_empty_and_none_safe(self):
        self.assertEqual(compress_event_token_repetition(""), "")
        self.assertEqual(compress_event_token_repetition("通常タイトル"), "通常タイトル")

    def test_idempotent_after_one_pass(self):
        original = "巨人・坂本が逆転サヨナラ３ラン！通算３００号のメモリアル弾で２試合連続のサヨナラ勝…"
        once = compress_event_token_repetition(original)
        twice = compress_event_token_repetition(once)
        self.assertEqual(once, twice)

    def test_three_sayonara_drops_second_and_third(self):
        original = "サヨナラ安打！逆転サヨナラ３ランで２試合連続のサヨナラ勝"
        result = compress_event_token_repetition(original)
        self.assertEqual(result.count("サヨナラ"), 1)
        self.assertIn("サヨナラ安打", result)


if __name__ == "__main__":
    unittest.main()
