"""Tests for src/h3_normalizer.py."""

from __future__ import annotations

import unittest

from src.h3_normalizer import normalize_h3_in_html


class TestExactMatchNormalization(unittest.TestCase):
    """完全一致 mapping の検証。"""

    def test_old_relpost_to_fan_voice(self):
        body = "<h3>📣 関連投稿</h3><p>...</p>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>💬 ファンの声</h3>", result)
        self.assertNotIn("📣 関連投稿", result)

    def test_gemini_highlight_to_fact_card(self):
        body = "<h3>【ハイライト】</h3><p>...</p>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>📋 事実カード</h3>", result)

    def test_gemini_fan_interest_to_next_focus(self):
        body = "<h3>【ファンの関心ポイント】</h3><p>...</p>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>📅 次の注目</h3>", result)

    def test_naked_chuukei_to_emoji_form(self):
        body = "<h3>中継予定</h3>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>🎬 中継予定</h3>", result)

    def test_score_to_fact_card(self):
        body = "<h3>試合スコア</h3>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>📋 事実カード</h3>", result)

    def test_injury_detail_to_injury_status(self):
        body = "<h3>【故障の詳細】</h3>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>💉 怪我状況</h3>", result)


class TestPrefixMatchWithSuffix(unittest.TestCase):
    """attribution suffix 付き H3 の正規化。"""

    def test_relpost_with_source_in_parens_japanese(self):
        body = "<h3>📣 関連投稿(巨人公式X)</h3>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>💬 ファンの声</h3>", result)
        self.assertNotIn("📣", result)

    def test_relpost_with_source_in_parens_ascii(self):
        body = "<h3>📣 関連投稿(スポーツ報知巨人班X)</h3>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>💬 ファンの声</h3>", result)


class TestIdempotent(unittest.TestCase):
    def test_already_unified_passes_through(self):
        body = (
            "<h3>📋 事実カード</h3><p>...</p>"
            "<h3>💬 ファンの声</h3><p>...</p>"
            "<h3>🔗 出典記事</h3>"
        )
        result = normalize_h3_in_html(body)
        self.assertEqual(result, body)

    def test_double_normalize_unchanged(self):
        body = "<h3>【ハイライト】</h3>"
        once = normalize_h3_in_html(body)
        twice = normalize_h3_in_html(once)
        self.assertEqual(once, twice)


class TestUnknownH3Preserved(unittest.TestCase):
    def test_unknown_h3_kept_as_is(self):
        body = "<h3>カスタム見出し テスト</h3>"
        result = normalize_h3_in_html(body)
        self.assertEqual(result, body)

    def test_no_h3_in_body(self):
        body = "<p>本文だけ</p>"
        result = normalize_h3_in_html(body)
        self.assertEqual(result, body)

    def test_empty_input(self):
        self.assertEqual(normalize_h3_in_html(""), "")


class TestMultipleH3InOneBody(unittest.TestCase):
    def test_multiple_replacements(self):
        body = (
            "<h3>【ハイライト】</h3><p>...</p>"
            "<h3>📣 関連投稿(巨人公式X)</h3><p>...</p>"
            "<h3>【ファンの関心ポイント】</h3>"
        )
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>📋 事実カード</h3>", result)
        self.assertIn("<h3>💬 ファンの声</h3>", result)
        self.assertIn("<h3>📅 次の注目</h3>", result)
        # 旧形式が残ってないか確認
        self.assertNotIn("【ハイライト】", result)
        self.assertNotIn("📣", result)
        self.assertNotIn("【ファンの関心ポイント】", result)


class TestH3WithInnerHtml(unittest.TestCase):
    def test_h3_with_span_inside(self):
        body = "<h3><span>📣 関連投稿</span></h3>"
        result = normalize_h3_in_html(body)
        self.assertIn("💬 ファンの声", result)


class TestFanVoiceH3Dedup(unittest.TestCase):
    """ENABLE_FAN_VOICE_H3_DEDUP (default ON) で重複 💬 ファンの声 h3 を集約する。"""

    def test_two_fan_voice_h3_collapses_to_one_keeping_twitter(self):
        # 空 fan voice h3 + filler → 後段に X embed の fan voice h3 = 重複
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>投稿要点を短く整理します。</p>"
            "<h3>📅 次の注目</h3>"
            "<p>出典: example.com</p>"
            "<h3>💬 ファンの声（Xより）</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        # 残るのは twitter-tweet を含む方
        self.assertIn("twitter-tweet", result)
        self.assertIn("💬 ファンの声（Xより）", result)
        # 重複は除去
        self.assertEqual(result.count("💬 ファンの声"), 1)
        # filler の「整理します」 paragraph も同 section ごと除去
        self.assertNotIn("整理します", result)

    def test_single_fan_voice_h3_unchanged(self):
        body = (
            "<h3>💬 ファンの声</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        self.assertEqual(result, body)

    def test_dedup_is_idempotent(self):
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>filler</p>"
            "<h3>💬 ファンの声（Xより）</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        once = normalize_h3_in_html(body)
        twice = normalize_h3_in_html(once)
        self.assertEqual(once, twice)

    def test_dedup_keeps_longer_when_no_twitter_in_either(self):
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>short</p>"
            "<h3>💬 ファンの声</h3>"
            "<p>longer body content paragraph here with details</p>"
        )
        result = normalize_h3_in_html(body)
        self.assertEqual(result.count("💬 ファンの声"), 1)
        self.assertIn("longer body content", result)

    def test_dedup_disabled_when_flag_off_keeps_both(self):
        import os
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>filler</p>"
            "<h3>💬 ファンの声（Xより）</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        os.environ["ENABLE_FAN_VOICE_H3_DEDUP"] = "0"
        try:
            result = normalize_h3_in_html(body)
            self.assertEqual(result.count("💬 ファンの声"), 2)
        finally:
            os.environ.pop("ENABLE_FAN_VOICE_H3_DEDUP", None)


if __name__ == "__main__":
    unittest.main()
