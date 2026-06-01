"""451/SNS: tests for src.sns_card (データ差し込み HTML 生成)。"""
from __future__ import annotations

import unittest

from src import sns_card as sc


class PlayerCardTests(unittest.TestCase):
    def test_player_card_has_brand_data_rank(self):
        h = sc.render_player_card_html(
            name="大城卓三", position="捕手", jersey="24",
            season_avg=33 / 95, hits=33, rbi=14, games=40, late_avg=12 / 27,
            rank=3, rank_total=160, point_line="終盤に強い。",
        )
        self.assertIn("大城卓三", h)
        self.assertIn("@yoshilover_giants", h)   # ブランド
        self.assertIn(".347", h)                  # 打率 hero
        self.assertIn("3位", h)
        self.assertIn("160人中", h)
        self.assertIn("33", h)  # 安打
        self.assertTrue(h.strip().startswith("<!doctype html>"))

    def test_player_card_no_rank_pill_when_missing(self):
        h = sc.render_player_card_html(name="新人", season_avg=0.25, hits=5, rbi=2, games=10)
        self.assertNotIn("NPB", h)  # rank 無しなら pill 出さない
        self.assertIn("新人", h)


class LateInningCardTests(unittest.TestCase):
    def test_late_inning_card_marks_top_phase(self):
        h = sc.render_late_inning_card_html(
            name="岸田行倫", position="捕手",
            soban=0.207, chuban=0.267, shuban=0.423, shuban_h=11, shuban_ab=26,
        )
        self.assertIn("終盤に強い男", h)
        self.assertIn("岸田行倫", h)
        self.assertIn(".423", h)
        self.assertIn("11安打/26打数", h)
        # 終盤(最高)が top クラスで強調される
        self.assertIn('class="bar top"', h)

    def test_avg_format(self):
        self.assertEqual(sc._fmt_avg(0.347), ".347")
        self.assertEqual(sc._fmt_avg(None), "-")


if __name__ == "__main__":
    unittest.main()
