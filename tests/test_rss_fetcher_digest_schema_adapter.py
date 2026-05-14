"""Tests for _adapt_candidate_for_digest (#22 / 341-FIX)."""

from __future__ import annotations

import unittest

from src import rss_fetcher


class AdaptCandidateForDigestTests(unittest.TestCase):
    def test_source_family_derived_from_hochi_url(self):
        cand = {"post_url": "https://hochi.news/articles/20260514-OHT1T51000.html", "title": "巨人記事"}
        result = rss_fetcher._adapt_candidate_for_digest(cand)
        self.assertEqual(result["source_family"], "hochi")

    def test_source_family_derived_from_sponichi_url(self):
        cand = {"post_url": "https://www.sponichi.co.jp/baseball/news/2026/05/14/x.html", "title": "巨人"}
        result = rss_fetcher._adapt_candidate_for_digest(cand)
        self.assertEqual(result["source_family"], "sponichi")

    def test_player_name_extracted_from_title(self):
        cand = {
            "post_url": "https://hochi.news/x.html",
            "title": "坂本勇人が逆転サヨナラ３ラン",
            "summary": "",
        }
        result = rss_fetcher._adapt_candidate_for_digest(cand)
        self.assertTrue(result.get("player_name"))

    def test_game_id_falls_back_to_published_day(self):
        cand = {
            "post_url": "https://hochi.news/x.html",
            "title": "巨人",
            "published_day": "2026-05-14",
        }
        result = rss_fetcher._adapt_candidate_for_digest(cand)
        self.assertEqual(result["game_id"], "2026-05-14")

    def test_existing_fields_not_overwritten(self):
        cand = {
            "post_url": "https://hochi.news/x.html",
            "title": "坂本",
            "summary": "",
            "published_day": "2026-05-14",
            "source_family": "custom_pre_set",
            "player_name": "事前設定選手",
            "game_id": "custom_id",
        }
        result = rss_fetcher._adapt_candidate_for_digest(cand)
        self.assertEqual(result["source_family"], "custom_pre_set")
        self.assertEqual(result["player_name"], "事前設定選手")
        self.assertEqual(result["game_id"], "custom_id")

    def test_idempotent_two_passes_equal(self):
        cand = {
            "post_url": "https://hochi.news/x.html",
            "title": "坂本勇人がサヨナラ",
            "summary": "",
            "published_day": "2026-05-14",
        }
        once = rss_fetcher._adapt_candidate_for_digest(cand)
        twice = rss_fetcher._adapt_candidate_for_digest(once)
        self.assertEqual(once, twice)

    def test_no_post_url_safe(self):
        cand = {"title": "巨人", "published_day": "2026-05-14"}
        result = rss_fetcher._adapt_candidate_for_digest(cand)
        self.assertIn("source_family", result)

    def test_original_candidate_not_mutated(self):
        cand = {
            "post_url": "https://hochi.news/x.html",
            "title": "坂本勇人がサヨナラ",
            "summary": "",
            "published_day": "2026-05-14",
        }
        original_keys = set(cand.keys())
        rss_fetcher._adapt_candidate_for_digest(cand)
        self.assertEqual(set(cand.keys()), original_keys)


if __name__ == "__main__":
    unittest.main()
