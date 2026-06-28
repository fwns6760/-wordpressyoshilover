import unittest

from src.yt_shorts_ranking import (
    RANKING_OPENING,
    build_ranking_script,
    list_ranking_topics,
    ranking_topic_from_stat,
)
from src.yt_shorts_script import verify_number_guard


def _leaders() -> dict:
    return {
        "本塁打": [
            {"player": "岡本和真", "display": "15本", "slug": "okamoto-kazuma"},
            {"player": "坂本勇人", "display": "9本", "slug": "sakamoto-hayato"},
            {"player": "丸佳浩", "display": "7本", "slug": "maru-yoshihiro"},
        ],
        "打率": [
            {"player": "泉口友汰", "display": ".318", "slug": "izuguchi-yuta"},
            {"player": "吉川尚輝", "display": ".299", "slug": "yoshikawa-naoki"},
        ],
    }


class YtShortsRankingTests(unittest.TestCase):
    def test_topic_needs_two_entries(self):
        single = {"本塁打": [{"player": "岡本和真", "display": "15本"}]}
        self.assertIsNone(ranking_topic_from_stat("本塁打", single["本塁打"]))

    def test_list_orders_count_stats_first(self):
        topics = list_ranking_topics(_leaders(), as_of="2026-06-28")
        self.assertEqual(topics[0].stat, "本塁打")
        stats = [t.stat for t in topics]
        self.assertIn("打率", stats)

    def test_script_opening_and_number_guard(self):
        topic = ranking_topic_from_stat("本塁打", _leaders()["本塁打"], as_of="2026-06-28")
        script = build_ranking_script(topic)
        self.assertTrue(script.narration.startswith(RANKING_OPENING))
        self.assertIn("本塁打", script.title)
        self.assertIn("ランキング", script.title)
        self.assertIn("岡本和真", script.description)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)
        ok_cap, leaked_cap = verify_number_guard(
            "\n".join(c.text for c in script.captions), script.allowed_numbers
        )
        self.assertTrue(ok_cap, leaked_cap)
        self.assertIn("15", script.allowed_numbers)

    def test_ratio_stat_is_read_as_waribunrin(self):
        topic = ranking_topic_from_stat("打率", _leaders()["打率"], as_of="2026-06-28")
        script = build_ranking_script(topic)
        # 打率 .318 が割分厘で読み下されている
        self.assertIn("三割一分八厘", script.narration)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)

    def test_topic_key_uses_stat_and_date(self):
        topic = ranking_topic_from_stat("本塁打", _leaders()["本塁打"], as_of="2026-06-28")
        self.assertEqual(topic.topic_key, "yt_shorts_ranking|2026-06-28|本塁打")


if __name__ == "__main__":
    unittest.main()
