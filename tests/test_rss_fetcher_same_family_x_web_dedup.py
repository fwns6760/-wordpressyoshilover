"""Tests for _aggregate_same_family_x_web_candidates (#18 / 339-INGEST)."""

from __future__ import annotations

import os
import unittest

from src import rss_fetcher


class SameFamilyXWebDedupFlagTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop(rss_fetcher._SAME_FAMILY_X_WEB_DEDUP_ENV_FLAG, None)

    def tearDown(self):
        os.environ.pop(rss_fetcher._SAME_FAMILY_X_WEB_DEDUP_ENV_FLAG, None)

    def test_flag_off_default_returns_input_unchanged(self):
        candidates = [
            {
                "post_url": "https://hochi.news/x.html",
                "title": "坂本サヨナラ",
                "summary": "",
                "source_type": "news",
            },
            {
                "post_url": "https://x.com/hochi_giants/status/123",
                "title": "坂本サヨナラ",
                "summary": "",
                "source_type": "social_news",
            },
        ]
        result = rss_fetcher._aggregate_same_family_x_web_candidates(candidates)
        self.assertEqual(len(result), 2)

    def test_empty_candidates_safe(self):
        os.environ[rss_fetcher._SAME_FAMILY_X_WEB_DEDUP_ENV_FLAG] = "1"
        self.assertEqual(rss_fetcher._aggregate_same_family_x_web_candidates([]), [])


class SameFamilyXWebDedupBehaviorTests(unittest.TestCase):
    def setUp(self):
        os.environ[rss_fetcher._SAME_FAMILY_X_WEB_DEDUP_ENV_FLAG] = "1"

    def tearDown(self):
        os.environ.pop(rss_fetcher._SAME_FAMILY_X_WEB_DEDUP_ENV_FLAG, None)

    def test_hochi_x_consumed_when_paired_with_hochi_web(self):
        candidates = [
            {
                "post_url": "https://hochi.news/articles/20260514.html",
                "title": "坂本勇人がサヨナラホームラン",
                "summary": "巨人・坂本勇人が逆転サヨナラホームラン。「一生忘れない」",
                "source_type": "news",
            },
            {
                "post_url": "https://x.com/hochi_giants/status/123",
                "title": "坂本勇人サヨナラホームラン速報",
                "summary": "坂本勇人がサヨナラホームラン",
                "source_type": "social_news",
            },
        ]
        result = rss_fetcher._aggregate_same_family_x_web_candidates(candidates)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["post_url"], "https://hochi.news/articles/20260514.html")
        self.assertIn("same_family_x_consumed", result[0])
        self.assertEqual(len(result[0]["same_family_x_consumed"]), 1)
        self.assertIn("x.com/hochi_giants", result[0]["same_family_x_consumed"][0]["url"])

    def test_different_family_pair_not_deduped(self):
        candidates = [
            {
                "post_url": "https://hochi.news/articles/20260514.html",
                "title": "坂本勇人サヨナラホームラン",
                "summary": "巨人・坂本勇人が逆転サヨナラホームラン",
                "source_type": "news",
            },
            {
                "post_url": "https://x.com/sanspo_giants/status/456",
                "title": "坂本勇人サヨナラホームラン速報",
                "summary": "坂本勇人がサヨナラホームラン",
                "source_type": "social_news",
            },
        ]
        result = rss_fetcher._aggregate_same_family_x_web_candidates(candidates)
        self.assertEqual(len(result), 2)

    def test_x_only_no_web_pair_unchanged(self):
        candidates = [
            {
                "post_url": "https://x.com/hochi_giants/status/123",
                "title": "坂本サヨナラホームラン",
                "summary": "",
                "source_type": "social_news",
            },
        ]
        result = rss_fetcher._aggregate_same_family_x_web_candidates(candidates)
        self.assertEqual(len(result), 1)

    def test_different_event_token_not_deduped(self):
        candidates = [
            {
                "post_url": "https://hochi.news/articles/20260514.html",
                "title": "坂本勇人サヨナラホームラン",
                "summary": "巨人・坂本勇人が逆転サヨナラホームラン",
                "source_type": "news",
            },
            {
                "post_url": "https://x.com/hochi_giants/status/123",
                "title": "戸郷翔征完封勝利",
                "summary": "戸郷翔征が完封勝利",
                "source_type": "social_news",
            },
        ]
        result = rss_fetcher._aggregate_same_family_x_web_candidates(candidates)
        self.assertEqual(len(result), 2)

    def test_two_web_no_x_unchanged(self):
        candidates = [
            {
                "post_url": "https://hochi.news/x.html",
                "title": "坂本勇人サヨナラホームラン",
                "summary": "巨人・坂本勇人が逆転サヨナラホームラン",
                "source_type": "news",
            },
            {
                "post_url": "https://hochi.news/y.html",
                "title": "坂本勇人サヨナラホームラン続報",
                "summary": "坂本勇人がサヨナラホームラン続報",
                "source_type": "news",
            },
        ]
        result = rss_fetcher._aggregate_same_family_x_web_candidates(candidates)
        self.assertEqual(len(result), 2)


class DetectEventTokenForDedupTests(unittest.TestCase):
    def test_sayonara_homerun(self):
        self.assertIn("サヨナラホームラン", rss_fetcher._detect_event_token_for_dedup("巨人・坂本がサヨナラホームラン"))

    def test_kanshu_shori(self):
        self.assertIn("完封", rss_fetcher._detect_event_token_for_dedup("戸郷が完封勝利"))

    def test_no_event_returns_empty(self):
        self.assertEqual(rss_fetcher._detect_event_token_for_dedup("通常記事"), "")


if __name__ == "__main__":
    unittest.main()
