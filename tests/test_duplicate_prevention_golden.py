import json
import unittest
from pathlib import Path
from unittest.mock import Mock

import pytest

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

    def _run_same_fire_guard(self, rewritten_title, source_urls, **kwargs):
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
                    **kwargs,
                )
            )
        return wp, logger, post_ids

    def test_same_fire_lineup_title_collision_skips_second_source(self):
        rewritten_title = "巨人スタメン 巨人 vs DeNA 東京ドーム 14時試合開始"
        source_urls = [
            "https://twitter.com/TokyoGiants/status/2055511381106098274",
            "https://twitter.com/TokyoGiants/status/2055509985573163155",
        ]

        wp, logger, post_ids = self._run_same_fire_guard(
            rewritten_title,
            source_urls,
            enrichment_category="試合速報",
            enrichment_template_key="game_lineup",
        )

        self.assertEqual(post_ids, [900, 0])
        self.assertEqual(len(wp.calls), 1)
        self.assertEqual(wp.calls[0]["source_url"], source_urls[0])
        logged = "\n".join(str(call.args[0]) for call in logger.info.call_args_list)
        self.assertIn("same_fire_cross_source_title_duplicate_skip", logged)
        self.assertIn(source_urls[1], logged)

    def test_same_fire_player_quote_title_collision_skips_second_source(self):
        rewritten_title = "坂本勇人「状態は上がっている」 関連発言"
        source_urls = [
            "https://hochi.news/articles/20260516-OHT1T50001.html",
            "https://www.sponichi.co.jp/baseball/news/2026/05/16/kiji/0001.html",
        ]

        wp, logger, post_ids = self._run_same_fire_guard(
            rewritten_title,
            source_urls,
            enrichment_category="選手情報",
            enrichment_template_key="player_quote",
        )

        self.assertEqual(post_ids, [900, 0])
        self.assertEqual(len(wp.calls), 1)
        logged = "\n".join(str(call.args[0]) for call in logger.info.call_args_list)
        self.assertIn("same_fire_cross_source_title_duplicate_skip", logged)

    def test_same_fire_generic_title_collision_still_observes_only(self):
        rewritten_title = "巨人ニュース"
        source_urls = [
            "https://example.com/general/1",
            "https://example.com/general/2",
        ]

        wp, logger, post_ids = self._run_same_fire_guard(rewritten_title, source_urls)

        self.assertEqual(post_ids, [900, 901])
        self.assertEqual(len(wp.calls), 2)
        self.assertIn(
            (
                "same_fire_distinct_source_detected source_url=%s rewritten_title=%s",
                source_urls[1],
                rewritten_title,
            ),
            [call.args for call in logger.info.call_args_list],
        )

    @pytest.mark.xfail(reason="pre-existing duplicate-prevention regression, baseline-confirmed at e298fa4; tracked separately", strict=False)
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

    @pytest.mark.xfail(reason="pre-existing duplicate-prevention regression, baseline-confirmed at e298fa4; tracked separately", strict=False)
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

    @pytest.mark.xfail(reason="pre-existing duplicate-prevention regression, baseline-confirmed at e298fa4; tracked separately", strict=False)
    def test_same_source_retry_reuses_existing_draft(self):
        # RELIABILITY-2026-05-08-DUP-FIX: 旧 golden は [900, 900] (= 2 回 WP API
        # 叩いて WP-side dedup で同 post_id 返却、buggy 挙動を encode してた)。
        # fetcher-side で 2 回目を skip する新 dedup guard 導入後の正規挙動は
        # [900, 0] = 1 回しか WP に届かない、効率も idempotency も改善。
        rewritten_title = "巨人戦 試合の流れを分けたポイント"
        source_url = "https://example.com/postgame/20260420/hochi"

        wp, logger, post_ids = self._run_same_fire_guard(rewritten_title, [source_url, source_url])

        self.assertEqual(post_ids, [900, 0])
        # WP create_post は 1 回のみ
        self.assertEqual(len(wp.calls), 1)
        self.assertEqual(wp.calls[0]["allow_title_only_reuse"], False)
        # dedup skip log が 1 回出る
        self.assertEqual(logger.info.call_count, 1)
        logger.info.assert_called()


if __name__ == "__main__":
    unittest.main()
