"""Tests for /data/injured (離脱選手) と /data/players (選手索引) — 2026-07-06 user GO。"""

from __future__ import annotations

import unittest
from datetime import date

from src.data_site_template_injured import (
    InjuryRow,
    _split_annotation,
    compute_injury_board,
    render_injured_html,
)
from src.data_site_template_player_index import (
    build_index_entries,
    render_player_index_html,
)


def _moves_data():
    return {"years": [{
        "year": 2026,
        "roster": [],
        "moves": [
            {"date": "6/8", "reg": [], "out": ["西舘 勇陽"]},
            {"date": "5/10", "reg": ["泉口 友汰"], "out": []},
            {"date": "4/21", "reg": [], "out": ["泉口 友汰（脳振盪※）"]},
            {"date": "4/05", "reg": [], "out": ["S.ハワード（右アキレス腱炎）"]},
        ],
    }]}


class InjuredBoardTests(unittest.TestCase):
    def test_annotation_split(self):
        self.assertEqual(_split_annotation("泉口 友汰（脳振盪※）"), ("泉口 友汰", "脳振盪※"))
        self.assertEqual(_split_annotation("西舘 勇陽"), ("西舘 勇陽", ""))

    def test_annotated_out_pairs_with_clean_reg(self):
        """注記付き抹消 + 注記なし再登録がペアリングされ、復帰済みが離脱中に残らない
        (2026-07-06 実データで泉口が離脱中に誤表示された bug の回帰)。"""
        board = compute_injury_board(_moves_data(), date(2026, 7, 6))
        current_names = [r.name for r in board["current"]]
        self.assertNotIn("泉口 友汰", current_names)
        self.assertIn("西舘 勇陽", current_names)
        self.assertIn("S.ハワード", current_names)
        history = {r.name: r for r in board["history"]}
        self.assertEqual(history["泉口 友汰"].note, "脳振盪※")
        self.assertEqual(history["泉口 友汰"].days_out, 19)

    def test_earliest_return_is_out_plus_10(self):
        row = InjuryRow(name="x", out_date=date(2026, 6, 8))
        self.assertEqual(row.earliest_return(), date(2026, 6, 18))

    def test_render_contains_note_column(self):
        board = compute_injury_board(_moves_data(), date(2026, 7, 6))
        html = render_injured_html(board, date(2026, 7, 6))
        self.assertIn("右アキレス腱炎", html)
        self.assertIn("最短復帰", html)
        self.assertIn("/data/roster-moves", html)

    def test_empty_data_safe(self):
        board = compute_injury_board({}, date(2026, 7, 6))
        self.assertIsNone(board["year"])


class PlayerIndexTests(unittest.TestCase):
    class _Info:
        def __init__(self, name, slug, role):
            self.name = name
            self.slug = slug
            self.role = role

    def test_groups_and_rows(self):
        infos = [
            self._Info("坂本勇人", "sakamoto-hayato", "player"),
            self._Info("長嶋茂雄", "nagashima-shigeo", "ob"),
            self._Info("ティマ", "tima", "player"),
            self._Info("阿部慎之助", "abe-shinnosuke", "manager"),
        ]
        entries = build_index_entries(infos)
        by = {e["name"]: e for e in entries}
        self.assertEqual(by["坂本勇人"]["row"], "さ行")
        self.assertEqual(by["長嶋茂雄"]["group"], "OB・歴代選手")
        self.assertEqual(by["ティマ"]["row"], "た行")  # カタカナ→ひらがな変換
        self.assertEqual(by["阿部慎之助"]["group"], "首脳陣")
        html = render_player_index_html(entries)
        self.assertIn('href="/data/sakamoto-hayato"', html)
        self.assertIn("さ行", html)

    def test_dedupe_by_slug(self):
        infos = [
            self._Info("坂本勇人", "sakamoto-hayato", "player"),
            self._Info("坂本勇人", "sakamoto-hayato", "player"),
        ]
        self.assertEqual(len(build_index_entries(infos)), 1)


if __name__ == "__main__":
    unittest.main()
