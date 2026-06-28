import unittest

from src.yt_shorts_topic import (
    list_topics_from_notable_data,
    select_topic_from_notable_data,
    topic_from_notable_item,
)


class YtShortsTopicTests(unittest.TestCase):
    def test_list_topics_returns_all_sorted_best_first(self):
        data = {
            "as_of": "2026-06-12",
            "items": [
                {
                    "player": "吉川尚輝",
                    "slug": "yoshikawa-naoki",
                    "label": "OPS",
                    "value": ".910",
                    "note": "",
                    "category": "form",
                },
                {
                    "player": "泉口友汰",
                    "slug": "izuguchi-yuta",
                    "label": "連続試合安打",
                    "value": "7試合",
                    "note": "今季最長7試合",
                    "category": "streak",
                },
            ],
        }

        topics = list_topics_from_notable_data(data)

        self.assertEqual([t.player for t in topics], ["泉口友汰", "吉川尚輝"])
        self.assertEqual(list_topics_from_notable_data(None), [])

    def test_selects_streak_before_form_metric(self):
        data = {
            "as_of": "2026-06-12",
            "items": [
                {
                    "player": "吉川尚輝",
                    "slug": "yoshikawa-naoki",
                    "label": "OPS",
                    "value": ".910",
                    "note": "今季・リーグ3位",
                    "category": "form",
                },
                {
                    "player": "泉口友汰",
                    "slug": "izuguchi-yuta",
                    "label": "連続試合安打",
                    "value": "7試合",
                    "note": "今季最長7試合",
                    "category": "streak",
                },
            ],
        }

        topic = select_topic_from_notable_data(data)

        self.assertIsNotNone(topic)
        self.assertEqual(topic.player, "泉口友汰")
        self.assertEqual(topic.topic_key, "yt_shorts|2026-06-12|泉口友汰|連続試合安打|7試合")

    def test_empty_payload_returns_none(self):
        self.assertIsNone(select_topic_from_notable_data({"as_of": "2026-06-12", "items": []}))

    def test_missing_required_item_field_is_rejected(self):
        self.assertIsNone(topic_from_notable_item({"player": "泉口友汰", "label": "連続試合安打"}))

    def test_ascii_metric_decimal_value_is_separated_for_number_guard(self):
        topic = topic_from_notable_item(
            {
                "player": "吉川尚輝",
                "label": "OPS",
                "value": ".981",
                "note": "直近10試合 OPS .981",
            }
        )

        self.assertIsNotNone(topic)
        self.assertEqual(topic.title, "吉川尚輝 OPS .981をデータで見る")
        self.assertEqual(topic.hook, "吉川尚輝、OPS .981")


if __name__ == "__main__":
    unittest.main()
