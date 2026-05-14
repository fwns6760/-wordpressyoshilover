"""Tests for src/youtube_title_filter.py (344-INGEST Phase 1a)."""

from __future__ import annotations

import unittest

from src import youtube_title_filter


def _stub_giants_roster_matcher(text: str) -> list[str]:
    """test 用 stub: 簡易 player roster 検出。"""
    players = ("坂本勇人", "坂本", "戸郷翔征", "戸郷", "岡本和真")
    hits = []
    for p in players:
        if len(p) >= 2 and p in text:
            hits.append(p)
    return hits


class YoutubeTitleFilterTests(unittest.TestCase):
    def test_giants_keyword_巨人_passes(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "巨人vsヤクルト振り返り"
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_keyword")

    def test_giants_keyword_jaianzu_passes(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "ジャイアンツ次戦展望"
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_keyword")

    def test_giants_keyword_yomiuri_passes(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "読売巨人軍特集"
        )
        self.assertTrue(ok)

    def test_active_player_passes(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "坂本勇人300号を語る",
            giants_roster_matcher=_stub_giants_roster_matcher,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_player")

    def test_ob_passes(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "上原浩治のWBC裏話",
            giants_roster_matcher=_stub_giants_roster_matcher,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_ob")

    def test_ob_legend_passes(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "王貞治と長嶋茂雄 ONコンビ秘話",
            giants_roster_matcher=_stub_giants_roster_matcher,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_ob")

    def test_recent_ob_菅野_passes(self):
        # 元巨人 OB MLB 移籍 (project_mlb_player_inclusion_policy)
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "菅野智之、ヤンキースで初先発",
            giants_roster_matcher=_stub_giants_roster_matcher,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_ob")

    def test_no_match_skipped(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "メジャー大谷総決算",
            giants_roster_matcher=_stub_giants_roster_matcher,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "no_match")

    def test_unrelated_baseball_skipped(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "高校野球決勝の名場面",
            giants_roster_matcher=_stub_giants_roster_matcher,
        )
        self.assertFalse(ok)

    def test_empty_input_safe(self):
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter("")
        self.assertFalse(ok)
        self.assertEqual(reason, "no_match")

    def test_giants_keyword_priority(self):
        # 巨人 keyword + OB 両方 hit → keyword が先 (reason 確認)
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "巨人 上原浩治 引退試合",
            giants_roster_matcher=_stub_giants_roster_matcher,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_keyword")

    def test_no_matcher_provided_falls_back_to_keyword_and_ob(self):
        # giants_roster_matcher=None でも 巨人 keyword + OB は動作
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "巨人 vs ヤクルト",
            giants_roster_matcher=None,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_keyword")

        ok2, reason2 = youtube_title_filter.youtube_title_passes_giants_filter(
            "上原浩治 雑談",
            giants_roster_matcher=None,
        )
        self.assertTrue(ok2)
        self.assertEqual(reason2, "giants_ob")

    def test_matcher_exception_does_not_break_flow(self):
        def broken_matcher(text):
            raise RuntimeError("intentional test error")
        ok, reason = youtube_title_filter.youtube_title_passes_giants_filter(
            "上原浩治の雑談",
            giants_roster_matcher=broken_matcher,
        )
        # 巨人 keyword には hit せず、matcher 例外 → ob check に fall through
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_ob")


if __name__ == "__main__":
    unittest.main()
