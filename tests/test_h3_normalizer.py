"""Tests for src/h3_normalizer.py."""

from __future__ import annotations

import unittest

from src.h3_normalizer import normalize_h3_in_html


class TestExactMatchNormalization(unittest.TestCase):
    """完全一致 mapping の検証。"""

    def test_old_relpost_to_fan_voice(self):
        # Body carries a twitter-tweet so the section survives the new
        # `_drop_empty_fan_voice_sections` step (canonical fan voice is
        # X-embed-bearing).
        body = (
            "<h3>📣 関連投稿</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>💬 ファンの声（Xより）</h3>", result)
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
        body = (
            "<h3>📣 関連投稿(巨人公式X)</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>💬 ファンの声（Xより）</h3>", result)
        self.assertNotIn("📣", result)

    def test_relpost_with_source_in_parens_ascii(self):
        body = (
            "<h3>📣 関連投稿(スポーツ報知巨人班X)</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>💬 ファンの声（Xより）</h3>", result)


class TestIdempotent(unittest.TestCase):
    def test_already_unified_passes_through(self):
        body = (
            "<h3>📋 事実カード</h3><p>...</p>"
            "<h3>💬 ファンの声（Xより）</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
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
            "<h3>📣 関連投稿(巨人公式X)</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
            "<h3>【ファンの関心ポイント】</h3>"
        )
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>📋 事実カード</h3>", result)
        self.assertIn("<h3>💬 ファンの声（Xより）</h3>", result)
        self.assertIn("<h3>📅 次の注目</h3>", result)
        # 旧形式が残ってないか確認
        self.assertNotIn("【ハイライト】", result)
        self.assertNotIn("📣", result)
        self.assertNotIn("【ファンの関心ポイント】", result)


class TestH3WithInnerHtml(unittest.TestCase):
    def test_h3_with_span_inside(self):
        body = (
            "<h3><span>📣 関連投稿</span></h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        self.assertIn("💬 ファンの声（Xより）", result)


class TestH3CleanupMappingsAdded(unittest.TestCase):
    """333-QA Layer C 拡張: 2 mapping rule 追加。"""

    def test_nigun_lineup_to_fact_card(self):
        body = "<h3>【二軍スタメン一覧】</h3><p>...</p>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>📋 事実カード</h3>", result)
        self.assertNotIn("【二軍スタメン一覧】", result)

    def test_chumoku_player_to_notable_player(self):
        body = "<h3>【注目選手】</h3><p>...</p>"
        result = normalize_h3_in_html(body)
        self.assertIn("<h3>🏆 注目選手</h3>", result)
        self.assertNotIn("【注目選手】", result)


class TestH3TitleDuplicateRemoval(unittest.TestCase):
    """333-QA TITLE_AS_H3: 記事タイトル風 h3 を body 冒頭から削除。"""

    def setUp(self):
        import os
        os.environ.pop("ENABLE_H3_TITLE_DUP_REMOVAL", None)

    def tearDown(self):
        import os
        os.environ.pop("ENABLE_H3_TITLE_DUP_REMOVAL", None)

    def test_title_like_h3_at_body_start_removed(self):
        body = (
            "<h3>【巨人】前回登板で完封の育成３年目・園田純規が先発 "
            "ＤｅＮＡ先発は藤浪…２軍・ＤｅＮＡ戦。</h3>"
            "<h3>📋 事実カード</h3><p>...</p>"
        )
        result = normalize_h3_in_html(body)
        self.assertNotIn("園田純規", result)
        self.assertIn("📋 事実カード", result)

    def test_university_baseball_title_removed(self):
        body = (
            "<h3>【大学野球】近大・宮原廉、関大・米沢友翔のドラフト候補対決"
            "にスカウト集結 巨人は超異例の１１人態勢。</h3>"
            "<h3>📅 次の注目</h3><p>...</p>"
        )
        result = normalize_h3_in_html(body)
        self.assertNotIn("大学野球", result)
        self.assertIn("📅 次の注目", result)

    def test_short_unified_h3_NOT_removed(self):
        # 12 unified set の短い h3 は対象外
        body = "<h3>📋 事実カード</h3><p>...</p>"
        result = normalize_h3_in_html(body)
        self.assertIn("📋 事実カード", result)

    def test_h3_starts_with_bracket_but_short_NOT_removed(self):
        # 【ハイライト】 など旧 H3 (短い) は別 normalize path で扱う
        body = "<h3>【ハイライト】</h3><p>...</p>"
        result = normalize_h3_in_html(body)
        # mapping で 📋 事実カード に変換、削除はされない
        self.assertIn("📋 事実カード", result)

    def test_title_like_h3_NOT_at_body_start_kept(self):
        # 200 chars 以降の h3 は body 中盤の正当な見出し
        prefix = "<p>" + "あ" * 250 + "</p>"
        body = (
            prefix
            + "<h3>【巨人】長い見出しっぽい引用が body 中盤に。</h3>"
            "<p>...</p>"
        )
        result = normalize_h3_in_html(body)
        # 200 chars 以降は保護される
        self.assertIn("【巨人】長い見出しっぽい引用が body 中盤に。", result)

    def test_h3_without_trailing_period_kept(self):
        body = (
            "<h3>【巨人】前回登板で完封の育成３年目・園田純規が先発</h3>"
            "<p>...</p>"
        )
        result = normalize_h3_in_html(body)
        # 。 で終わらないので削除されない (誤削除予防)
        self.assertIn("園田純規", result)

    def test_flag_off_keeps_title_h3(self):
        import os
        os.environ["ENABLE_H3_TITLE_DUP_REMOVAL"] = "0"
        body = (
            "<h3>【巨人】前回登板で完封の育成３年目・園田純規が先発 "
            "ＤｅＮＡ先発は藤浪…２軍・ＤｅＮＡ戦。</h3>"
        )
        result = normalize_h3_in_html(body)
        self.assertIn("園田純規", result)


class TestFanVoiceDedupSuffixVariants(unittest.TestCase):
    """333-QA: suffix 違い (Xより) を含む fan voice h3 dedup の明示テスト。
    327-QA で既に suffix 違いも startswith 比較で dedup される実装だが、
    explicit な regression test として追加。"""

    def test_dedup_handles_xyori_suffix(self):
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>filler 「整理します」</p>"
            "<h3>💬 ファンの声（Xより）</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        # 💬 ファンの声 が 1 つだけ残る (twitter-tweet を含む方)
        self.assertEqual(result.count("💬 ファンの声"), 1)
        self.assertIn("（Xより）", result)
        self.assertIn("twitter-tweet", result)
        self.assertNotIn("整理します", result)


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
        # The longer surviving section must have a twitter-tweet so it
        # isn't subsequently removed by _drop_empty_fan_voice_sections
        # (which targets fan voice sections without X embeds).
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>short</p>"
            "<h3>💬 ファンの声</h3>"
            "<p>longer body content paragraph here with details</p>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        self.assertEqual(result.count("💬 ファンの声"), 1)
        self.assertIn("longer body content", result)

    def test_dedup_disabled_when_flag_off_keeps_both(self):
        import os
        # Both sections carry twitter-tweet so neither is removed by the
        # empty-drop step (we are testing dedup-flag behavior in isolation).
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>filler</p>"
            '<blockquote class="twitter-tweet"><a>tweetA</a></blockquote>'
            "<h3>💬 ファンの声（Xより）</h3>"
            '<blockquote class="twitter-tweet"><a>tweetB</a></blockquote>'
        )
        os.environ["ENABLE_FAN_VOICE_H3_DEDUP"] = "0"
        try:
            result = normalize_h3_in_html(body)
            self.assertEqual(result.count("💬 ファンの声"), 2)
        finally:
            os.environ.pop("ENABLE_FAN_VOICE_H3_DEDUP", None)


class TestFanVoiceEmptyDrop(unittest.TestCase):
    """2026-05-14: filler `💬 ファンの声(Xより)` section without X embed
    must be removed from the published body. Sections that DO contain
    a `twitter-tweet` blockquote (= legitimate community section) survive."""

    def setUp(self):
        import os
        os.environ.pop("ENABLE_FAN_VOICE_EMPTY_DROP", None)

    def tearDown(self):
        import os
        os.environ.pop("ENABLE_FAN_VOICE_EMPTY_DROP", None)

    def test_section_with_twitter_tweet_kept(self):
        body = (
            "<h3>💬 ファンの声（Xより）</h3>"
            '<blockquote class="twitter-tweet"><a>tweet</a></blockquote>'
        )
        result = normalize_h3_in_html(body)
        self.assertIn("💬 ファンの声（Xより）", result)
        self.assertIn("twitter-tweet", result)

    def test_empty_section_dropped(self):
        # Gemini paraphrase only, no twitter-tweet → section removed.
        body = (
            "<h3>💬 ファンの声（Xより）</h3>"
            "<p>投稿要点を短く整理します。</p>"
            "<h3>🔗 出典記事</h3><p>...</p>"
        )
        result = normalize_h3_in_html(body)
        self.assertNotIn("💬 ファンの声", result)
        self.assertNotIn("投稿要点を短く整理します", result)
        # 後段の出典 h3 は残る
        self.assertIn("🔗 出典記事", result)

    def test_legacy_plain_label_filler_also_dropped(self):
        # Backward-compat: a stray plain `💬 ファンの声` (no suffix) with
        # no twitter is also treated as filler and dropped.
        body = (
            "<h3>💬 ファンの声</h3>"
            "<p>整理します。</p>"
        )
        result = normalize_h3_in_html(body)
        self.assertNotIn("💬 ファンの声", result)
        self.assertNotIn("整理します", result)

    def test_long_text_section_kept_even_without_twitter(self):
        # Section body >= threshold chars survives (real fan reaction text).
        long_body = "ファンの本物の感想文がここに" * 20  # >> 200 chars
        body = (
            "<h3>💬 ファンの声（Xより）</h3>"
            f"<p>{long_body}</p>"
        )
        result = normalize_h3_in_html(body)
        self.assertIn("💬 ファンの声（Xより）", result)

    def test_empty_drop_disabled_when_flag_off(self):
        import os
        body = (
            "<h3>💬 ファンの声（Xより）</h3>"
            "<p>filler</p>"
        )
        os.environ["ENABLE_FAN_VOICE_EMPTY_DROP"] = "0"
        result = normalize_h3_in_html(body)
        self.assertIn("💬 ファンの声（Xより）", result)
        self.assertIn("filler", result)

    def test_empty_drop_idempotent(self):
        body = (
            "<h3>💬 ファンの声（Xより）</h3>"
            "<p>整理します。</p>"
            "<h3>🔗 出典記事</h3>"
        )
        once = normalize_h3_in_html(body)
        twice = normalize_h3_in_html(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
