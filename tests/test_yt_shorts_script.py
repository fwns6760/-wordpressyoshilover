import unittest

from src.yt_shorts_script import (
    allowed_numbers_for_topic,
    build_script,
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

        self.assertIn("泉口友汰", script.narration)
        self.assertIn("連続試合安打7試合", script.narration)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)

    def test_allowed_numbers_include_value_note_and_date(self):
        allowed = allowed_numbers_for_topic(_topic())

        self.assertIn("7", allowed)
        self.assertIn("2026", allowed)
        self.assertIn("6", allowed)
        self.assertIn("12", allowed)

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

    def test_extract_number_tokens_normalizes_leading_zero_and_decimal(self):
        self.assertEqual(extract_number_tokens("07試合 .450 0.320"), ("7", ".450", ".320"))


if __name__ == "__main__":
    unittest.main()
