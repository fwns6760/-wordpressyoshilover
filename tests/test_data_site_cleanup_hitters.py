"""Tests for /data/cleanup-hitters history page."""

from __future__ import annotations

import unittest

from src.data_site_template_cleanup_hitters import (
    load_cleanup_hitters_data,
    render_cleanup_hitters_excerpt,
    render_cleanup_hitters_html,
    render_cleanup_hitters_title,
)


class CleanupHittersTemplateTests(unittest.TestCase):
    def test_data_has_full_history_shape(self) -> None:
        data = load_cleanup_hitters_data()
        self.assertEqual(data["as_of"], "2025年終了時点")
        self.assertGreaterEqual(len(data["alltime"]), 90)
        self.assertEqual(data["alltime"][0]["generation"], 96)
        self.assertEqual(data["alltime"][-1]["generation"], 1)
        self.assertEqual(data["consecutive_starter_record"]["name"], "A.ラミレス")

    def test_title_and_excerpt(self) -> None:
        data = load_cleanup_hitters_data()
        self.assertIn("歴代4番打者", render_cleanup_hitters_title())
        ex = render_cleanup_hitters_excerpt(data)
        self.assertIn("2025年終了時点", ex)
        self.assertIn("連続4番先発記録", ex)

    def test_render_has_tables_and_topic_cluster_links(self) -> None:
        html = render_cleanup_hitters_html(load_cleanup_hitters_data())
        self.assertIn("巨人 歴代4番打者 成績一覧", html)
        self.assertIn("2025年シーズンの4番起用", html)
        self.assertIn("歴代4番打者 全一覧", html)
        self.assertIn("川上哲治", html)
        self.assertIn("長嶋茂雄", html)
        self.assertIn("王貞治", html)
        self.assertIn("/data/record", html)
        self.assertIn("/data/legends", html)
        self.assertIn("/data/oh-sadaharu", html)
        self.assertIn("成績は4番先発時の集計", html)


if __name__ == "__main__":
    unittest.main()
