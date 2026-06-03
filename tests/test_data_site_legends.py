"""Tests for data/legends OB hub (Phase B 452)."""
from __future__ import annotations
import unittest
from src.data_site_template_legends import render_legends_html, render_legends_title, render_legends_excerpt


class LegendsTemplateTests(unittest.TestCase):
    def _entries(self):
        return [
            {"display_name": "長嶋茂雄", "slug": "nagashima-shigeo", "type": "batter",
             "years": "1958-1974", "npb": {"avg": ".305", "hr": 444},
             "honors": ["永久欠番「3」・ミスタージャイアンツ"]},
            {"display_name": "上原浩治", "slug": "uehara-koji", "type": "pitcher",
             "years": "1999-2008", "npb": {"w": 112, "era": "3.01"}, "honors": ["通算112勝"]},
        ]

    def test_render(self) -> None:
        html = render_legends_html(self._entries())
        self.assertIn("長嶋茂雄", html)
        self.assertIn("444本", html)
        self.assertIn("/data/nagashima-shigeo/", html)
        self.assertIn("永久欠番", html)
        self.assertIn("112勝", html)  # 投手は勝/防御率
        self.assertIn("OB・レジェンド", html)

    def test_title_excerpt(self) -> None:
        self.assertIn("OB", render_legends_title())
        self.assertIn("2名", render_legends_excerpt(self._entries()))

    def test_empty_safe(self) -> None:
        self.assertIn("OB・レジェンド", render_legends_html([]))


if __name__ == "__main__":
    unittest.main()
