"""Tests for src/source_yahoo_lineup_extractor.py.

The parser is offline only — every test constructs a synthetic
HTML payload that mimics Yahoo's lineup-table shape.
"""
from __future__ import annotations

import unittest

from src.source_yahoo_lineup_extractor import parse_yahoo_lineup_html


def _build_table(rows):
    head = (
        "<thead><tr>"
        "<th>打順</th><th>守</th><th>選手</th><th>打/投</th>"
        "</tr></thead>"
    )
    body = "<tbody>"
    for r in rows:
        body += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>右/右</td></tr>"
    body += "</tbody>"
    return f'<table class="bb-startMembersBatter">{head}{body}</table>'


class StandardParseTests(unittest.TestCase):
    def test_two_team_lineup_parsed(self):
        home_rows = [
            ("1", "中", "丸佳浩"),
            ("2", "遊", "吉川尚輝"),
            ("3", "右", "岡本和真"),
            ("4", "三", "坂本勇人"),
            ("5", "一", "中田翔"),
            ("6", "左", "オコエ"),
            ("7", "捕", "大城卓三"),
            ("8", "二", "増田大輝"),
            ("9", "投", "戸郷翔征"),
        ]
        away_rows = [
            ("1", "中", "近本光司"),
            ("2", "二", "中野拓夢"),
            ("3", "右", "森下翔太"),
            ("4", "DH", "大山悠輔"),
        ]
        html = (
            "<html><body>"
            + _build_table(home_rows)
            + _build_table(away_rows)
            + "</body></html>"
        )
        home, away = parse_yahoo_lineup_html(html)
        self.assertEqual(len(home), 9)
        self.assertEqual(home[0], {"order": "1", "position": "中", "name": "丸佳浩"})
        self.assertEqual(home[2]["name"], "岡本和真")
        self.assertEqual(home[8], {"order": "9", "position": "投", "name": "戸郷翔征"})
        self.assertEqual(len(away), 4)
        self.assertEqual(away[3]["name"], "大山悠輔")

    def test_returns_empty_when_no_lineup_table(self):
        html = "<html><body><p>no lineup here</p></body></html>"
        home, away = parse_yahoo_lineup_html(html)
        self.assertEqual(home, [])
        self.assertEqual(away, [])

    def test_returns_empty_on_empty_html(self):
        self.assertEqual(parse_yahoo_lineup_html(""), ([], []))
        self.assertEqual(parse_yahoo_lineup_html(None), ([], []))


class ConservativeFilterTests(unittest.TestCase):
    def test_table_without_打順_marker_skipped(self):
        # A table with only "選手" but no "打順" is not a lineup table.
        html = """
        <table>
          <tr><th>選手</th></tr>
          <tr><td>丸佳浩</td></tr>
        </table>
        """
        home, away = parse_yahoo_lineup_html(html)
        self.assertEqual(home, [])

    def test_non_digit_first_cell_skips_row(self):
        # Bench player tables sometimes share the same structure but
        # use names in the first column.
        html = """
        <table>
          <tr><th>打順</th><th>守</th><th>選手</th></tr>
          <tr><td>控え</td><td>捕</td><td>岸田行倫</td></tr>
          <tr><td>1</td><td>中</td><td>丸佳浩</td></tr>
        </table>
        """
        home, away = parse_yahoo_lineup_html(html)
        self.assertEqual(len(home), 1)
        self.assertEqual(home[0]["name"], "丸佳浩")

    def test_fullwidth_order_normalised(self):
        html = """
        <table>
          <tr><th>打順</th><th>守</th><th>選手</th></tr>
          <tr><td>１</td><td>中</td><td>丸佳浩</td></tr>
          <tr><td>２</td><td>遊</td><td>吉川尚輝</td></tr>
        </table>
        """
        home, _ = parse_yahoo_lineup_html(html)
        self.assertEqual(len(home), 2)
        self.assertEqual(home[0]["order"], "1")
        self.assertEqual(home[1]["order"], "2")


class HallucinationGuardTests(unittest.TestCase):
    def test_names_are_substrings_of_input(self):
        rows = [
            ("1", "中", "丸佳浩"),
            ("2", "遊", "吉川尚輝"),
        ]
        html = _build_table(rows)
        home, _ = parse_yahoo_lineup_html(html)
        for entry in home:
            self.assertIn(entry["name"], html)
            self.assertIn(entry["position"], html)


if __name__ == "__main__":
    unittest.main()
