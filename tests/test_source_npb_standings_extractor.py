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


if __name__ == "__main__":
    unittest.main()
