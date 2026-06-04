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
        # 刷新: 50音×通算成績テーブル名鑑 (featured カード / 名球会見出しは廃止)。
        html = render_legends_html(self._entries())
        self.assertIn("長嶋茂雄", html)
        self.assertIn("/data/nagashima-shigeo/", html)  # 名前→個別ページ
        self.assertIn("50音で探す", html)                # 五十音ジャンプナビ
        self.assertIn("歴代在籍選手", html)               # 新見出し
        self.assertNotIn("名球会", html)                  # 名球会の特別枠は廃止
        self.assertIn("OPS", html)                        # 打者テーブルの deep 列

    def test_title_excerpt(self) -> None:
        self.assertIn("OB", render_legends_title())
        self.assertIn("2名", render_legends_excerpt(self._entries()))

    def test_empty_safe(self) -> None:
        self.assertIn("歴代在籍選手", render_legends_html([]))


if __name__ == "__main__":
    unittest.main()
