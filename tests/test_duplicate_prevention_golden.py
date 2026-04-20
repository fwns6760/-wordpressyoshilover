import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from src import rss_fetcher


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "duplicate_prevention_golden.json"


class FakeWPClient:
    def __init__(self):
        self.calls = []
        self.posts = []
        self.next_id = 900

    def create_post(
        self,
        title,
        content,
        categories=None,
        status="draft",
        featured_media=None,
        source_url=None,
        allow_title_only_reuse=False,
    ):
        self.calls.append(
            {
                "title": title,
                "status": status,
                "categories": categories or [],
                "featured_media": featured_media,
                "source_url": source_url,
                "allow_title_only_reuse": allow_title_only_reuse,
            }
        )
        for post in self.posts:
            if post["title"] != title:
                continue
            if source_url and post["source_url"] == source_url:
                return post["id"]
            if allow_title_only_reuse:
                return post["id"]
        post_id = self.next_id
        self.next_id += 1
        self.posts.append({"id": post_id, "title": title, "source_url": source_url})
        return post_id


class DuplicatePreventionGoldenTests(unittest.TestCase):
    def test_duplicate_prevention_fixture(self):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                actual = rss_fetcher._is_history_duplicate(
                    case["post_url"],
                    case["entry_title_norm"],
                    case["history"],
                )
                self.assertEqual(actual, case["expected_duplicate"])

    def _run_same_fire_guard(self, rewritten_title, source_urls):
        wp = FakeWPClient()
        logger = Mock()
        same_fire_source_urls = set()
        same_fire_title_sources = {}
        post_ids = []
        for source_url in source_urls:
            post_ids.append(
                rss_fetcher._create_draft_with_same_fire_guard(
                    wp,
                    logger,
                    same_fire_source_urls,
                    same_fire_title_sources,
                    rewritten_title,
                    "<p>body</p>",
                    [673],
                    source_url,
                )
            )
        return wp, logger, post_ids

    def test_same_fire_distinct_farm_sources_split_post_ids(self):
        rewritten_title = "巨人二軍 結果のポイント"
        source_urls = [
            "https://example.com/farm/20260420/game-1",
            "https://example.com/farm/20260420/game-2",
        ]

        wp, logger, post_ids = self._run_same_fire_guard(rewritten_title, source_urls)

        self.assertEqual(post_ids, [900, 901])
        self.assertEqual(
            [call["allow_title_only_reuse"] for call in wp.calls],
            [False, False],
        )
        logger.info.assert_called_once_with(
            "same_fire_distinct_source_detected source_url=%s rewritten_title=%s",
            source_urls[1],
            rewritten_title,
        )

    def test_same_fire_distinct_pregame_sources_split_post_ids(self):
        rewritten_title = "巨人戦 試合前にどこを見たいか"
        source_urls = [
            "https://example.com/pregame/20260420/hochi",
            "https://example.com/pregame/20260420/nikkan",
        ]

        wp, logger, post_ids = self._run_same_fire_guard(rewritten_title, source_urls)

        self.assertEqual(post_ids, [900, 901])
        self.assertEqual(
            [call["source_url"] for call in wp.calls],
            source_urls,
        )
        logger.info.assert_called_once_with(
            "same_fire_distinct_source_detected source_url=%s rewritten_title=%s",
            source_urls[1],
            rewritten_title,
        )

    def test_same_source_retry_reuses_existing_draft(self):
        rewritten_title = "巨人戦 試合の流れを分けたポイント"
        source_url = "https://example.com/postgame/20260420/hochi"

        wp, logger, post_ids = self._run_same_fire_guard(rewritten_title, [source_url, source_url])

        self.assertEqual(post_ids, [900, 900])
        self.assertEqual(
            [call["allow_title_only_reuse"] for call in wp.calls],
            [False, False],
        )
        logger.info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
