"""data_site_template_foreign (歴代外国人選手 hub /data/foreign-players/) のテスト。"""
from __future__ import annotations

import unittest

from src.data_site_template_foreign import (
    load_foreign_players_data,
    render_foreign_players_excerpt,
    render_foreign_players_html,
    render_foreign_players_title,
)


def _sample_data() -> dict:
    return {
        "season": 2026,
        "pending": ["金伏ウーゴ (2016、日系ブラジル人、一軍登板なし) — 外国人選手としての扱い整備中"],
        "ob": [
            {"name": "V.スタルヒン(須田博)", "display_name": "V.スタルヒン(須田 博)", "slug": "starffin",
             "type": "pitcher", "years": "1934-1944", "roman": "VICTOR STARFFIN",
             "npb": {"games": 586, "w": 303, "era": "2.09", "k": 1960}},
            {"name": "与那嶺要", "display_name": "与那嶺要", "slug": "yonamine-kaname",
             "type": "batter", "years": "1951-1960", "roman": "",
             "npb": {"games": 1219, "avg": ".311", "hits": 1337, "hr": 82, "rbi": 482},
             "note": "ハワイ・ホノルル出身の日系二世 (米国籍)。首位打者3回、1994年野球殿堂入り"},
            {"name": "W.クロマティ", "display_name": "W.クロマティ", "slug": "cromartie",
             "type": "batter", "years": "1984-1990", "roman": "WARREN CROMARTIE",
             "npb": {"games": 1886, "avg": ".298", "hits": 2055, "hr": 232, "rbi": 949}},
        ],
        "active": [
            {"name": "バルドナード", "group": "投手", "status": "支配下", "slug": "baldonado"},
            {"name": "ティマ", "group": "外野手", "status": "支配下", "slug": "tima"},
            {"name": "グズマン", "group": "投手", "status": "育成", "slug": ""},
        ],
    }


class RenderForeignPlayersTests(unittest.TestCase):
    def test_title_and_excerpt(self) -> None:
        self.assertIn("歴代外国人選手", render_foreign_players_title())
        ex = render_foreign_players_excerpt(_sample_data())
        self.assertIn("6名", ex)  # OB 3 + 現役 3

    def test_sections_present(self) -> None:
        html = render_foreign_players_html(_sample_data())
        self.assertIn("ys-foreign-search", html)
        self.assertIn("ys-foreign-active", html)
        self.assertIn("ys-foreign-decades", html)
        self.assertIn("ys-foreign-years", html)
        self.assertIn("BreadcrumbList", html)
        # 編成データ nav に自ページが selected で入る
        self.assertIn("🌍 歴代外国人", html)

    def test_player_links_and_badges(self) -> None:
        html = render_foreign_players_html(_sample_data())
        self.assertIn('href="/data/cromartie"', html)
        self.assertIn('href="/data/baldonado"', html)
        # slug 無し (グズマン) はリンクを作らない
        self.assertNotIn('href="/data//"', html)
        self.assertIn("育成", html)
        self.assertIn("VICTOR STARFFIN", html)
        # 日系注記
        self.assertIn("ハワイ・ホノルル出身", html)

    def test_year_matrix_expands_ranges_and_collapses_gaps(self) -> None:
        html = render_foreign_players_html(_sample_data())
        # クロマティ在籍 1984-1990 が各年に展開される (1987 行にも出る)
        self.assertIn(">1987<", html)
        # 空白年 (1961-1983) は圧縮表示
        self.assertIn("1961-1983", html)
        self.assertIn("掲載選手なし", html)

    def test_npb_summary_formats(self) -> None:
        html = render_foreign_players_html(_sample_data())
        self.assertIn("303勝", html)
        self.assertIn("打率.298", html)
        self.assertIn("232本", html)

    def test_real_config_loads_and_renders(self) -> None:
        """repo の正本 config が壊れていない & render が例外なく通る。"""
        data = load_foreign_players_data()
        self.assertGreaterEqual(len(data.get("ob") or []), 130)
        self.assertGreaterEqual(len(data.get("active") or []), 1)
        html = render_foreign_players_html(data)
        self.assertIn("クロマティ", html)
        self.assertIn("スタルヒン", html)
        # リチャード (日本人) は収録しない
        self.assertNotIn(">リチャード<", html)


if __name__ == "__main__":
    unittest.main()
