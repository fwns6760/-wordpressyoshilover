"""Tests for src/giants_ob_roster.py (344-INGEST Phase 1a)."""

from __future__ import annotations

import unittest

from src import giants_ob_roster


class LoadGiantsObRosterTests(unittest.TestCase):
    def test_load_returns_non_empty_list(self):
        roster = giants_ob_roster.load_giants_ob_roster()
        self.assertIsInstance(roster, list)
        self.assertGreaterEqual(len(roster), 25)

    def test_each_entry_has_name_and_aliases(self):
        roster = giants_ob_roster.load_giants_ob_roster()
        for entry in roster:
            self.assertIn("name", entry, msg=f"entry missing name: {entry}")
            self.assertIn("aliases", entry, msg=f"entry missing aliases: {entry}")
            self.assertIsInstance(entry["aliases"], list)
            self.assertGreater(len(entry["aliases"]), 0)

    def test_canonical_names_are_unique(self):
        roster = giants_ob_roster.load_giants_ob_roster()
        names = [str(e.get("name") or "") for e in roster]
        self.assertEqual(len(names), len(set(names)), "duplicate canonical name in OB roster")


class MatchingObNamesTests(unittest.TestCase):
    def test_full_name_hit(self):
        result = giants_ob_roster.matching_ob_names("上原浩治がメジャー初登板で好投")
        self.assertIn("上原浩治", result)

    def test_alias_hit(self):
        result = giants_ob_roster.matching_ob_names("デーブ大久保が雑談 YT で語る")
        self.assertIn("大久保博元", result)

    def test_legend_hit(self):
        result = giants_ob_roster.matching_ob_names("王貞治と長嶋茂雄のONコンビ")
        self.assertIn("王貞治", result)
        self.assertIn("長嶋茂雄", result)

    def test_recent_ob_hit(self):
        # 元巨人 MLB 移籍 OB
        result = giants_ob_roster.matching_ob_names("菅野智之、ヤンキースで初先発")
        self.assertIn("菅野智之", result)

    def test_no_match_returns_empty(self):
        result = giants_ob_roster.matching_ob_names("通常記事タイトル")
        self.assertEqual(result, [])

    def test_empty_input_safe(self):
        self.assertEqual(giants_ob_roster.matching_ob_names(""), [])
        self.assertEqual(giants_ob_roster.matching_ob_names(None), [])

    def test_is_giants_ob_true(self):
        self.assertTrue(giants_ob_roster.is_giants_ob("元木大介チャンネル更新"))

    def test_is_giants_ob_false(self):
        self.assertFalse(giants_ob_roster.is_giants_ob("通常記事タイトル"))

    def test_dedup_when_alias_overlaps(self):
        # 「上原浩治」と「上原」 (現状 alias に短姓含めず、full name のみ hit)
        result = giants_ob_roster.matching_ob_names(
            "上原浩治『球宴前に見せた直球』"
        )
        # canonical name は 1 件 (重複除去)
        self.assertEqual(result.count("上原浩治"), 1)

    def test_short_aliases_under_2_chars_excluded(self):
        # 「王」「原」のような単漢字 alias は false positive 防止のため
        # 2 文字未満は match させない (原則 alias で 2 文字以上を要求)
        # この test は roster JSON 設計の anchor として残す
        roster = giants_ob_roster.load_giants_ob_roster()
        for entry in roster:
            for alias in entry["aliases"]:
                # 1 文字 alias を含む entry があってもよいが、matching では skip される
                # ここは最低限「2 文字以上の alias が必ず 1 つ以上ある」ことだけ verify
                pass
            self.assertTrue(
                any(len(str(a)) >= 2 for a in entry["aliases"]),
                msg=f"entry {entry['name']} has no alias >= 2 chars",
            )


if __name__ == "__main__":
    unittest.main()
