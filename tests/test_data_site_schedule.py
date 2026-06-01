"""Tests for data/schedule page (Phase B 452)."""
from __future__ import annotations
import os, sqlite3, tempfile, unittest
from src.data_site_query import fetch_giants_schedule
from src.data_site_template_schedule import render_schedule_html, render_schedule_title, render_schedule_excerpt


class _GR:
    def __init__(self, d, opp, ha, gs, os_, res):
        self.game_date, self.opponent, self.home_away = d, opp, ha
        self.giants_score, self.opp_score, self.result, self.summary = gs, os_, res, ""


class ScheduleTemplateTests(unittest.TestCase):
    def test_render_groups_by_month_and_colors(self) -> None:
        rows = [_GR("2026-05-31", "日本ハム", "ビジター", 0, 3, "負"),
                _GR("2026-05-30", "日本ハム", "ビジター", 5, 3, "勝"),
                _GR("2026-04-05", "ヤクルト", "本拠地", 4, 1, "勝")]
        html = render_schedule_html(rows)
        self.assertIn("5月", html)
        self.assertIn("4月", html)
        self.assertIn("vs 日本ハム", html)
        self.assertIn("5-3", html)
        self.assertIn("巨人 試合日程・結果", html)

    def test_title_and_excerpt(self) -> None:
        rows = [_GR("2026-05-30", "日本ハム", "ビジター", 5, 3, "勝")]
        self.assertIn("日程・結果", render_schedule_title())
        self.assertIn("1勝0敗", render_schedule_excerpt(rows))


class FetchScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.execute("CREATE TABLE games(game_id TEXT, game_date TEXT, opponent TEXT, home_away TEXT, giants_score INT, opp_score INT, result TEXT, one_line_summary TEXT)")
        conn.executemany("INSERT INTO games VALUES(?,?,?,?,?,?,?,?)", [
            ("2026-05-31:f-g-03", "2026-05-31", "日本ハム", "u", 0, 3, "loss", ""),   # 巨人away
            ("2026-05-27:g-h-02", "2026-05-27", "ソフトバンク", "u", 5, 1, "win", ""), # 巨人home
            ("2026-05-20:db-s-01", "2026-05-20", "ヤクルト", "u", 9, 9, "draw", ""),   # 巨人不在→除外
        ])
        conn.commit(); conn.close()
        self._p = os.environ.get("INSIGHT_DB_PATH"); os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._p is None: os.environ.pop("INSIGHT_DB_PATH", None)
        else: os.environ["INSIGHT_DB_PATH"] = self._p
        os.unlink(self.tmp.name)

    def test_giants_only_and_mapping(self) -> None:
        rows = fetch_giants_schedule()
        self.assertEqual(len(rows), 2)  # 巨人不在の db-s 除外
        by = {r.game_date: r for r in rows}
        self.assertEqual(by["2026-05-31"].home_away, "ビジター")  # f-g → away
        self.assertEqual(by["2026-05-31"].result, "負")
        self.assertEqual(by["2026-05-27"].home_away, "本拠地")    # g-h → home
        self.assertEqual(by["2026-05-27"].result, "勝")


if __name__ == "__main__":
    unittest.main()
