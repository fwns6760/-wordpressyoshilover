import unittest

from src.yt_shorts_script import (
    allowed_numbers_for_topic,
    build_script,
    display_as_of_date,
    extract_number_tokens,
    verify_number_guard,
)
from src.yt_shorts_topic import ShortsTopic


def _topic() -> ShortsTopic:
    return ShortsTopic(
        player="泉口友汰",
        slug="izuguchi-yuta",
        label="連続試合安打",
        value="7試合",
        note="今季最長7試合",
        category="streak",
        as_of="2026-06-12",
        title="泉口友汰 連続試合安打7試合をデータで見る",
        hook="泉口友汰、連続試合安打7試合",
        priority=507,
        raw_item={"player": "泉口友汰", "label": "連続試合安打", "value": "7試合", "note": "今季最長7試合"},
    )


class YtShortsScriptTests(unittest.TestCase):
    def test_build_script_keeps_numbers_from_topic_only(self):
        topic = _topic()
        script = build_script(topic)

        # narration は TTS 誤読対策で選手名を かな 読みに補正 (泉口=いずぐち)
        self.assertIn("いずぐちゆうた", script.narration)
        self.assertNotIn("泉口友汰", script.narration)
        # title は漢字表記を維持
        self.assertIn("泉口友汰", script.title)
        self.assertIn("連続試合安打7試合", script.narration)
        self.assertIn("2026年6月12日", script.narration)
        self.assertIn("2026年6月12日", script.title)
        self.assertIn("記録日: 2026年6月12日", script.description)
        self.assertIn("2026年6月12日", script.captions[0].text)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)

    def test_caption_timeline_matches_current_short_pacing(self):
        script = build_script(_topic())

        self.assertEqual(script.captions[0].start, 0.0)
        self.assertEqual(script.captions[-1].end, 27.0)
        self.assertEqual(tuple(round(c.end - c.start, 1) for c in script.captions), (2.2, 6.2, 6.4, 6.2, 6.0))

    def test_allowed_numbers_include_value_note_and_date(self):
        allowed = allowed_numbers_for_topic(_topic())

        self.assertIn("7", allowed)
        self.assertIn("2026", allowed)
        self.assertIn("6", allowed)
        self.assertIn("12", allowed)

    def test_display_as_of_date_formats_iso_date(self):
        self.assertEqual(display_as_of_date("2026-06-12"), "2026年6月12日")
        self.assertEqual(display_as_of_date(""), "")

    def test_number_guard_detects_unverified_number(self):
        ok, leaked = verify_number_guard("未確認で10本塁打ペースです", ("7",))

        self.assertFalse(ok)
        self.assertEqual(leaked, ("10",))

    def test_metric_label_number_is_allowed_for_k_per_9(self):
        topic = ShortsTopic(
            player="戸郷翔征",
            slug="togo-shosei",
            label="K/9",
            value="8.7",
            note="今季・リーグ3位",
            category="form",
            as_of="2026-06-12",
            title="戸郷翔征 K/9 8.7をデータで見る",
            hook="戸郷翔征、K/9 8.7",
            priority=208.7,
            raw_item={"player": "戸郷翔征", "label": "K/9", "value": "8.7", "note": "今季・リーグ3位"},
        )

        script = build_script(topic)

        ok, leaked = verify_number_guard(
            script.title + "\n" + script.narration + "\n" + script.description,
            script.allowed_numbers,
        )
        self.assertTrue(ok, leaked)

    def test_batting_average_uses_baseball_speech_reading_only_in_narration(self):
        topic = ShortsTopic(
            player="浦田俊輔",
            slug="urata-shunsuke",
            label="対DeNA打率",
            value=".464",
            note="対DeNAは13安打/28打数・3打点。シーズン打率.265から+.199の対戦別split。",
            category="form",
            as_of="2026-06-15",
            title="浦田俊輔 対DeNA打率.464をデータで見る",
            hook="浦田俊輔、対DeNA打率.464",
            priority=246.4,
            raw_item={
                "player": "浦田俊輔",
                "label": "対DeNA打率",
                "value": ".464",
                "note": "対DeNAは13安打/28打数・3打点。シーズン打率.265から+.199の対戦別split。",
            },
        )

        script = build_script(topic)

        self.assertIn("対DeNA打率四割六分四厘", script.narration)
        self.assertIn("シーズン打率二割六分五厘からプラス一割九分九厘", script.narration)
        self.assertNotIn(".464", script.narration)
        self.assertIn(".464", script.title)
        self.assertIn(".464", script.captions[1].text)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)

    def test_ops_uses_digit_run_not_wariburin_in_narration(self):
        topic = ShortsTopic(
            player="松本剛",
            slug="matsumoto-go",
            label="OPS",
            value=".909",
            note="直近データでOPS.909",
            category="form",
            as_of="2026-06-14",
            title="松本剛 OPS .909をデータで見る",
            hook="松本剛、OPS .909",
            priority=290.9,
            raw_item={"player": "松本剛", "label": "OPS", "value": ".909", "note": "直近データでOPS.909"},
        )

        script = build_script(topic)

        self.assertIn("オーピーエス きゅうまるきゅう", script.narration)
        self.assertIn("オーピーエスきゅうまるきゅう", script.narration)
        self.assertNotIn("割", script.narration)
        self.assertIn(".909", script.title)

    def test_era_and_k_per_9_use_decimal_point_speech_reading(self):
        era_topic = ShortsTopic(
            player="戸郷翔征",
            slug="togo-shosei",
            label="防御率",
            value="2.35",
            note="今季防御率2.35",
            category="form",
            as_of="2026-06-15",
            title="戸郷翔征 防御率2.35をデータで見る",
            hook="戸郷翔征、防御率2.35",
            priority=235.0,
            raw_item={"player": "戸郷翔征", "label": "防御率", "value": "2.35", "note": "今季防御率2.35"},
        )
        k9_topic = ShortsTopic(
            player="戸郷翔征",
            slug="togo-shosei",
            label="K/9",
            value="8.7",
            note="今季K/9 8.7",
            category="form",
            as_of="2026-06-15",
            title="戸郷翔征 K/9 8.7をデータで見る",
            hook="戸郷翔征、K/9 8.7",
            priority=208.7,
            raw_item={"player": "戸郷翔征", "label": "K/9", "value": "8.7", "note": "今季K/9 8.7"},
        )

        era_script = build_script(era_topic)
        k9_script = build_script(k9_topic)

        self.assertIn("防御率二点三五", era_script.narration)
        self.assertIn("ケーナイン 八点七", k9_script.narration)

    def test_extract_number_tokens_normalizes_leading_zero_and_decimal(self):
        self.assertEqual(extract_number_tokens("07試合 .450 0.320"), ("7", ".450", ".320"))


if __name__ == "__main__":
    unittest.main()
