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
        long_quote = "今日は最後まで集中して投げ切ることができた。" + "バッテリーともしっかり話して" * 7
        text = f"巨人の戸郷が「{long_quote}」と試合後コメント"
        out = extract_long_quote(text)
        self.assertGreaterEqual(len(out), 100)
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
        # 14 字 + 「よかった」 ×25 (100 字) = 114 字 > 100 min
        html = '<p>巨人の坂本勇人が<span>「最後まで集中して振り切れた' + 'よかった' * 25 + '」</span>と話した</p>'
        out = extract_long_quote(html)
        self.assertIn("最後まで集中して振り切れた", out)
        self.assertGreaterEqual(len(out), 100)

    def test_multiple_quotes_pick_longest_above_min(self) -> None:
        text = "「短いやつ」「" + "長い発言" * 30 + "」"  # 短/長 2 quote
        out = extract_long_quote(text)
        self.assertIn("長い発言", out)

    def test_nested_quote_excluded(self) -> None:
        """ネスト『』 は対象外。 外側「」 のみ抽出。"""
        text = "「コメントの中で『内側』を使った長い発言" + "が続く" * 30 + "」"
        out = extract_long_quote(text)
        # 外側「」 の content (内側『』 含む) が取れる
        self.assertIn("『内側』", out)


class SpeakerProximityTests(unittest.TestCase):
    def test_speaker_present_returns_quote(self) -> None:
        text = "巨人の戸郷翔征が「" + "今日は" * 40 + "」と話した"
        out = extract_long_quote(text, speaker_aliases=("戸郷翔征", "戸郷"))
        self.assertIn("今日は", out)

    def test_speaker_absent_returns_empty(self) -> None:
        # speaker は 戸郷 として渡すが、 実際の文は 菅野 が話している
        text = "ロッキーズの菅野智之が「" + "シーズン中だから" * 15 + "」とコメント"
        out = extract_long_quote(text, speaker_aliases=("戸郷翔征", "戸郷"))
        self.assertEqual(out, "")

    def test_speaker_too_far_returns_empty(self) -> None:
        # speaker と quote の距離が 40 文字超 → proximity 外
        far_text = "戸郷翔征" + ("x" * 100) + "「" + ("長い発言" * 20) + "」"
        out = extract_long_quote(far_text, speaker_aliases=("戸郷翔征",))
        self.assertEqual(out, "")

    def test_partial_alias_surname_only(self) -> None:
        text = "戸郷が「" + "今日も投げきった" * 14 + "」と話した"
        out = extract_long_quote(text, speaker_aliases=("戸郷",))
        self.assertGreater(len(out), 0)

    def test_no_aliases_skips_proximity_check(self) -> None:
        """speaker_aliases 空なら proximity check スキップ (backward compat)。"""
        text = "誰かが「" + "発言" * 55 + "」と言った"
        out = extract_long_quote(text, speaker_aliases=())
        self.assertGreater(len(out), 0)

    def test_competing_speaker_between_alias_and_quote_rejected(self) -> None:
        """2026-07-03: alias と 「 の間に別人の発言者表現 → 誤帰属として不採用.

        実事故: 記事内にキャベッジの名前が出ただけで、 坂口智隆氏の発言を
        キャベッジのコメント速報として mail に出した。
        """
        quote = "よくもなく悪くもなくといったところだと思います。" + "非常に球種が多い投手です。" * 5
        text = f"５回にはキャベッジを空振り三振。解説の坂口智隆氏は「{quote}」と称賛した"
        out = extract_long_quote(text, speaker_aliases=("キャベッジ",))
        self.assertEqual(out, "")

    def test_alias_own_title_suffix_not_competing(self) -> None:
        """alias 直後の bare 役職 (橋上秀樹監督代行「...) は競合扱いしない。"""
        quote = "今週も５試合なので最低でも２勝１敗で勝ち越したいですし" * 4
        text = f"試合後、橋上秀樹監督代行は「{quote}」と語った"
        out = extract_long_quote(text, speaker_aliases=("橋上秀樹", "橋上"))
        self.assertGreater(len(out), 0)

    def test_competing_speaker_with_role_word_rejected(self) -> None:
        """名前+監督 形の別発言者 (阿部監督) が間に挟まる場合も不採用。"""
        quote = "彼はよくやってくれているので信頼して送り出しました" * 3
        text = f"この日２安打の浦田俊輔。試合後に阿部監督は「{quote}」と話した"
        out = extract_long_quote(text, speaker_aliases=("浦田俊輔", "浦田"))
        self.assertEqual(out, "")


class ThresholdRelaxationTests(unittest.TestCase):
    """2026-05-28 PM3 lock: min_chars 100 (40→60→80→100 と段階引き上げ) /
    speaker_proximity 100 (維持)。"""

    def test_quote_below_60_rejected(self) -> None:
        quote_30 = "今日は良い結果になった本当に良かった" + "!" * 12
        self.assertEqual(len(quote_30), 30)
        text = f"戸郷が「{quote_30}」と話した"
        self.assertEqual(extract_long_quote(text), "")

    def test_quote_80_to_99_chars_rejected(self) -> None:
        # 80 字 fixture → 100 字閾値では reject
        quote_80 = "集中して投げ切る" * 10
        self.assertEqual(len(quote_80), 80)
        text = f"巨人の戸郷が「{quote_80}」と試合後コメント"
        self.assertEqual(extract_long_quote(text), "")

    def test_quote_100_chars_accepted(self) -> None:
        # 「集中して投げ切る」 8 字 × 13 回 = 104 字 ≥ 100 閾値
        quote_104 = "集中して投げ切る" * 13
        self.assertEqual(len(quote_104), 104)
        text = f"巨人の戸郷が「{quote_104}」と試合後コメント"
        out = extract_long_quote(text)
        self.assertGreaterEqual(len(out), 100)
        self.assertIn("集中して投げ切る", out)

    def test_speaker_within_100_chars_now_accepted(self) -> None:
        # speaker と quote 間が 60 字 → 旧 40 字 window 外、 新 100 字 window 内
        gap = "x" * 60
        text = f"戸郷翔征{gap}「" + "今日は集中して投げきった" * 11 + "」"
        out = extract_long_quote(text, speaker_aliases=("戸郷翔征",))
        self.assertGreater(len(out), 0)
        self.assertIn("今日は集中して投げきった", out)

    def test_speaker_beyond_100_chars_still_rejected(self) -> None:
        # speaker と quote 間が 200 字 → 100 字 window 外、 reject 維持
        gap = "x" * 200
        text = f"戸郷翔征{gap}「" + "今日は集中して投げきった" * 5 + "」"
        out = extract_long_quote(text, speaker_aliases=("戸郷翔征",))
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
