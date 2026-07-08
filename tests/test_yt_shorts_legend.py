import unittest

from src.yt_shorts_legend import (
    LEGEND_CLOSING,
    LEGEND_OPENING,
    build_legend_script,
    legend_topic_from_entry,
    list_legend_topics,
    select_legend_topic,
)
from src.yt_shorts_script import extract_number_tokens, verify_number_guard


def _oh() -> dict:
    return {
        "display_name": "王貞治",
        "slug": "oh-sadaharu",
        "type": "batter",
        "years": "1959-1980",
        "teams": "読売ジャイアンツ",
        "npb": {"games": 2831, "avg": ".301", "hits": 2786, "hr": 868, "rbi": 2170},
        "honors": ["永久欠番「1」・世界の王", "通算868本塁打 (世界記録)"],
        "kana": "おう さだはる",
    }


def _kaneda() -> dict:
    return {
        "display_name": "金田正一",
        "slug": "kaneda-masaichi",
        "type": "pitcher",
        "years": "1950-1969",
        "teams": "国鉄スワローズ→読売ジャイアンツ",
        "npb": {"games": 944, "w": 400, "l": 298, "era": "2.34", "k": 4490},
        "honors": ["史上唯一の通算400勝"],
        "kana": "かねだ まさいち",
    }


def _weak() -> dict:
    return {
        "display_name": "記録薄太郎",
        "slug": "weak",
        "type": "batter",
        "years": "2010-2012",
        "teams": "読売ジャイアンツ",
        "npb": {"games": 30, "avg": ".210", "hits": 12, "hr": 1, "rbi": 5},
    }


class YtShortsLegendTests(unittest.TestCase):
    def test_weak_record_player_is_excluded_from_lead(self):
        self.assertIsNone(legend_topic_from_entry(_weak()))

    def test_list_ranks_record_strength_and_honors_first(self):
        topics = list_legend_topics([_weak(), _oh(), _kaneda()])
        names = [t.player for t in topics]
        self.assertIn("王貞治", names)
        self.assertIn("金田正一", names)
        self.assertNotIn("記録薄太郎", names)

    def test_select_returns_a_legend(self):
        topic = select_legend_topic([_oh(), _kaneda()])
        self.assertIsNotNone(topic)

    def test_batter_script_has_brand_opening_and_close_and_passes_guard(self):
        topic = legend_topic_from_entry(_oh())
        script = build_legend_script(topic)
        self.assertTrue(script.narration.startswith(LEGEND_OPENING))
        self.assertIn(LEGEND_CLOSING, script.narration)
        # 2026-07-08 QC 落ち再発防止: 締めヨシラバー表記 (yt_shorts_qc の必須 gate)
        self.assertIn("ヨシラバー", script.narration)
        self.assertIn("王貞治", script.title)
        # 数字はすべて出典由来 (allowed) — guard を通る
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)
        ok_cap, leaked_cap = verify_number_guard(
            "\n".join(c.text for c in script.captions), script.allowed_numbers
        )
        self.assertTrue(ok_cap, leaked_cap)
        # 本塁打数が allowed に含まれる (記録が narration に乗っている)
        self.assertIn("868", script.allowed_numbers)
        self.assertIn("868", script.narration)

    def test_pitcher_script_uses_kana_reading_and_era(self):
        topic = legend_topic_from_entry(_kaneda())
        script = build_legend_script(topic)
        # kana 読みが narration に入っている (VOICEVOX 誤読対策)
        self.assertIn("かねだ まさいち", script.narration)
        # 防御率の小数が読み下されている
        self.assertIn("二点三四", script.narration)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)

    def test_topic_key_is_date_independent(self):
        topic = legend_topic_from_entry(_oh())
        self.assertEqual(topic.topic_key, "yt_shorts_legend|oh-sadaharu")


if __name__ == "__main__":
    unittest.main()
