"""Tests for long_quote_extractor (ticket 438 Phase 2)."""

from __future__ import annotations

import unittest

from src.long_quote_extractor import extract_long_quote, _strip_html_to_plain, _truncate_at_sentence_boundary


class StripHtmlTests(unittest.TestCase):
    def test_strip_script(self) -> None:
        html = "<p>before</p><script>alert(1)</script><p>after</p>"
        out = _strip_html_to_plain(html)
        self.assertNotIn("alert", out)
        self.assertIn("before", out)
        self.assertIn("after", out)

    def test_strip_style(self) -> None:
        html = "<style>body{color:red}</style><p>hello</p>"
        out = _strip_html_to_plain(html)
        self.assertNotIn("color", out)
        self.assertIn("hello", out)

    def test_decode_html_entity(self) -> None:
        out = _strip_html_to_plain("<p>&amp;quot;test&quot;</p>")
        self.assertIn('"test"', out)

    def test_no_tags_pass_through(self) -> None:
        self.assertEqual(_strip_html_to_plain("plain text"), "plain text")


class TruncateTests(unittest.TestCase):
    def test_within_max_returns_as_is(self) -> None:
        text = "短い文。"
        self.assertEqual(_truncate_at_sentence_boundary(text, 100, 60), text)

    def test_cut_at_period(self) -> None:
        # 60 文字以上、 100 字前後で「。」 がある想定
        text = "あ" * 90 + "。" + "い" * 50
        out = _truncate_at_sentence_boundary(text, 100, 60)
        self.assertTrue(out.endswith("。"))
        self.assertLessEqual(len(out), 100)
        self.assertEqual(len(out), 91)

    def test_cut_at_comma_when_no_period(self) -> None:
        text = "あ" * 90 + "、" + "い" * 50
        out = _truncate_at_sentence_boundary(text, 100, 60)
        self.assertTrue(out.endswith("、"))


class ExtractLongQuoteTests(unittest.TestCase):
    def test_simple_extract(self) -> None:
        long_quote = "今日は最後まで集中して投げ切ることができた。" + "バッテリーともしっかり話して" * 3
        text = f"巨人の戸郷が「{long_quote}」と試合後コメント"
        out = extract_long_quote(text)
        self.assertGreaterEqual(len(out), 60)
        self.assertNotIn("「", out)
        self.assertNotIn("」", out)

    def test_short_quote_rejected(self) -> None:
        text = "戸郷が「短い」と話した"
        self.assertEqual(extract_long_quote(text), "")

    def test_no_quote_returns_empty(self) -> None:
        self.assertEqual(extract_long_quote("文章中に quote マークが無い場合"), "")

    def test_empty_input(self) -> None:
        self.assertEqual(extract_long_quote(""), "")
        self.assertEqual(extract_long_quote(None), "")  # type: ignore[arg-type]

    def test_truncate_when_exceeds_max(self) -> None:
        # 200 字超の quote
        long = "あ" * 100 + "。" + "い" * 100 + "。"
        text = f"「{long}」"
        out = extract_long_quote(text, min_chars=60, max_chars=180)
        # max_chars 以下
        self.assertLessEqual(len(out), 180)
        # min_chars 以上
        self.assertGreaterEqual(len(out), 60)
        # 「」 含まず
        self.assertNotIn("「", out)
        self.assertNotIn("」", out)

    def test_html_input(self) -> None:
        # 「最後まで集中して振り切れた」 (14 字) + 「よかった」 ×15 (60 字) = 74 字 > 60 min
        html = '<p>巨人の坂本勇人が<span>「最後まで集中して振り切れた' + 'よかった' * 15 + '」</span>と話した</p>'
        out = extract_long_quote(html)
        self.assertIn("最後まで集中して振り切れた", out)
        self.assertGreaterEqual(len(out), 60)

    def test_multiple_quotes_pick_longest_above_min(self) -> None:
        text = "「短いやつ」「" + "長い発言" * 30 + "」"  # 短/長 2 quote
        out = extract_long_quote(text)
        self.assertIn("長い発言", out)

    def test_nested_quote_excluded(self) -> None:
        """ネスト『』 は対象外。 外側「」 のみ抽出。"""
        text = "「コメントの中で『内側』を使った長い発言" + "が続く" * 20 + "」"
        out = extract_long_quote(text)
        # 外側「」 の content (内側『』 含む) が取れる
        self.assertIn("『内側』", out)


if __name__ == "__main__":
    unittest.main()
