"""Tests for src/source_npb_standings_extractor.py.

Pure offline parser — every test feeds a synthetic HTML payload that
matches NPB.jp's standings shape.
"""
from __future__ import annotations

import unittest

from src.source_npb_standings_extractor import (
    find_giants_standings_row,
    parse_npb_standings_html,
)


def _build_table(rows, with_class=True):
    """Legacy layout: cells[0]=rank, cells[1]=team."""
    head = (
        "<thead><tr>"
        "<th>順位</th><th>チーム</th><th>試合</th><th>勝</th><th>負</th>"
        "<th>分</th><th>勝率</th><th>ゲーム差</th>"
        "</tr></thead>"
    )
    body = "<tbody>"
    for r in rows:
        body += (
            f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td>"
            f"<td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td>"
            f"<td>{r[6]}</td><td>{r[7]}</td></tr>"
        )
    body += "</tbody>"
    cls = ' class="tablefix2"' if with_class else ""
    return f"<table{cls}>{head}{body}</table>"


def _build_table_new_layout(rows, with_class=True):
    """New layout (2026 NPB.jp std_c.html): cells[0]=team, 順位 column 削除、
    rank は行順から推定。

    rows = [(team, games, wins, losses, draws, win_pct, gb), ...]
    """
    head = (
        "<thead><tr>"
        "<th>チーム</th><th>試合</th><th>勝利</th><th>敗北</th>"
        "<th>引分</th><th>勝率</th><th>差</th>"
        "</tr></thead>"
    )
    body = "<tbody>"
    for r in rows:
        body += (
            f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td>"
            f"<td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td>"
            f"<td>{r[6]}</td></tr>"
        )
    body += "</tbody>"
    cls = ' class="tablefix2"' if with_class else ""
    # 順位 keyword を _table_is_standings heuristic 用に追加 (live HTML には
    # 「順位」が page 内に必ず存在する想定)
    return f"<p>順位</p><table{cls}>{head}{body}</table>"


class StandardParseTests(unittest.TestCase):
    def test_central_league_full_standings(self):
        rows = [
            ("1", "阪神", "30", "20", "8", "2", ".714", "-"),
            ("2", "巨人", "30", "18", "10", "2", ".643", "2.0"),
            ("3", "DeNA", "29", "15", "12", "2", ".556", "4.5"),
            ("4", "広島", "30", "13", "15", "2", ".464", "7.0"),
            ("5", "中日", "30", "10", "18", "2", ".357", "10.0"),
            ("6", "ヤクルト", "31", "8", "21", "2", ".276", "12.5"),
        ]
        html = _build_table(rows)
        out = parse_npb_standings_html(html)
        self.assertEqual(len(out), 6)
        self.assertEqual(out[0]["team"], "阪神")
        self.assertEqual(out[1]["team"], "巨人")
        self.assertEqual(out[1]["wins"], "18")
        self.assertEqual(out[1]["losses"], "10")
        self.assertEqual(out[1]["win_pct"], ".643")
        self.assertEqual(out[1]["gb"], "2.0")

    def test_returns_empty_when_no_standings_table(self):
        html = "<html><body><p>not a standings page</p></body></html>"
        self.assertEqual(parse_npb_standings_html(html), [])

    def test_returns_empty_on_empty_input(self):
        self.assertEqual(parse_npb_standings_html(""), [])
        self.assertEqual(parse_npb_standings_html(None), [])


class FallbackPathTests(unittest.TestCase):
    def test_fallback_when_class_missing(self):
        rows = [
            ("1", "巨人", "30", "20", "8", "2", ".714", "-"),
        ]
        html = _build_table(rows, with_class=False)
        out = parse_npb_standings_html(html)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["team"], "巨人")

    def test_skips_non_digit_rank_rows(self):
        # Header / footer rows commonly have non-digit cell-0
        rows_html = (
            '<table class="tablefix2"><thead>'
            "<tr><th>順位</th><th>チーム</th><th>試合</th><th>勝率</th></tr>"
            "</thead><tbody>"
            "<tr><td>--</td><td>合計</td><td>30</td><td>.500</td></tr>"
            "<tr><td>1</td><td>巨人</td><td>30</td><td>.643</td></tr>"
            "</tbody></table>"
        )
        out = parse_npb_standings_html(rows_html)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["team"], "巨人")


class GiantsRowFinderTests(unittest.TestCase):
    def test_find_giants_row(self):
        rows = [
            {"rank": "1", "team": "阪神"},
            {"rank": "2", "team": "巨人"},
        ]
        match = find_giants_standings_row(rows)
        self.assertIsNotNone(match)
        self.assertEqual(match["rank"], "2")

    def test_giants_row_match_via_alias(self):
        rows = [{"rank": "1", "team": "読売ジャイアンツ"}]
        match = find_giants_standings_row(rows)
        self.assertIsNotNone(match)

    def test_giants_row_returns_none_when_absent(self):
        rows = [{"rank": "1", "team": "阪神"}, {"rank": "2", "team": "DeNA"}]
        self.assertIsNone(find_giants_standings_row(rows))


class HallucinationGuardTests(unittest.TestCase):
    def test_team_names_are_substrings_of_input(self):
        rows = [("1", "巨人", "30", "20", "8", "2", ".714", "-")]
        html = _build_table(rows)
        out = parse_npb_standings_html(html)
        for r in out:
            self.assertIn(r["team"], html)
            self.assertIn(r["wins"], html)
            self.assertIn(r["losses"], html)


class NewLayoutParseTests(unittest.TestCase):
    """2026-05-08 NPB.jp std_c.html structure 変化対応 (順位 column 削除)。"""

    def test_new_layout_central_league_full(self):
        # 5/8 live data に近い形
        rows = [
            ("阪神タイガース", "33", "20", "12", "1", ".625", "--"),
            ("東京ヤクルトスワローズ", "34", "21", "13", "0", ".618", "0.0"),
            ("読売ジャイアンツ", "33", "17", "16", "0", ".515", "3.5"),
            ("横浜DeNAベイスターズ", "32", "15", "16", "1", ".484", "4.5"),
            ("広島東洋カープ", "30", "11", "17", "2", ".393", "7.0"),
            ("中日ドラゴンズ", "33", "12", "21", "0", ".364", "8.5"),
        ]
        html = _build_table_new_layout(rows)
        out = parse_npb_standings_html(html)
        self.assertEqual(len(out), 6)
        self.assertEqual(out[0]["team"], "阪神タイガース")
        self.assertEqual(out[0]["rank"], "1")
        self.assertEqual(out[2]["team"], "読売ジャイアンツ")
        self.assertEqual(out[2]["rank"], "3")
        self.assertEqual(out[2]["wins"], "17")
        self.assertEqual(out[2]["losses"], "16")
        self.assertEqual(out[2]["win_pct"], ".515")
        self.assertEqual(out[2]["gb"], "3.5")

    def test_new_layout_giants_lookup(self):
        rows = [
            ("阪神", "33", "20", "12", "1", ".625", "--"),
            ("読売ジャイアンツ", "33", "17", "16", "0", ".515", "3.5"),
        ]
        html = _build_table_new_layout(rows)
        out = parse_npb_standings_html(html)
        giants = find_giants_standings_row(out)
        self.assertIsNotNone(giants)
        self.assertEqual(giants["rank"], "2")
        self.assertEqual(giants["team"], "読売ジャイアンツ")

    def test_new_layout_skips_header_row(self):
        # Header と data 両方含む生 HTML
        html = (
            "<p>順位</p>"
            '<table class="tablefix2">'
            "<tr><th>チーム</th><th>試合</th><th>勝利</th><th>敗北</th>"
            "<th>引分</th><th>勝率</th><th>差</th></tr>"
            "<tr><td>阪神</td><td>33</td><td>20</td><td>12</td>"
            "<td>1</td><td>.625</td><td>--</td></tr>"
            "</table>"
        )
        out = parse_npb_standings_html(html)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["team"], "阪神")
        self.assertEqual(out[0]["rank"], "1")


if __name__ == "__main__":
    unittest.main()
