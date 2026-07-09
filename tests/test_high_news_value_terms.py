"""_is_high_news_value_topic: 報知が取り上げる見どころプレーを高価値扱いにする
(2026-07-09 user「報知が投稿した=話題。NPB データに無い好守も報知にはある」)。
高価値 = news_opinion の player history filter を override して埋もれさせない。"""
from __future__ import annotations

import unittest

from src.tools.run_x_post_mail import _is_high_news_value_topic


class HighNewsValueFinePlayTests(unittest.TestCase):
    def test_fine_play_topics_are_high_value(self):
        for title in (
            "坂本勇人が値千金の好守！ダイビングキャッチ",
            "岡本和真が猛打賞の活躍",
            "戸郷翔征が完封勝利",
            "キャベッジのサヨナラ打で決着",
            "門脇のスーパープレー",
        ):
            self.assertTrue(_is_high_news_value_topic(title, ""), title)

    def test_transfer_topics_still_high_value(self):
        self.assertTrue(_is_high_news_value_topic("菅野智之がMLB移籍", ""))

    def test_ordinary_topic_not_high_value(self):
        self.assertFalse(_is_high_news_value_topic("練習後に取材に応じた", ""))


if __name__ == "__main__":
    unittest.main()
