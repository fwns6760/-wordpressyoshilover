"""037 parity pickup expansion tests for ``src.tools.run_notice_fixed_lane``."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.tools import run_notice_fixed_lane as lane


class _FakeWP:
    def __init__(self) -> None:
        self.api = "https://example.com/wp-json/wp/v2"
        self.auth = ("user", "pass")
        self.headers = {"Content-Type": "application/json"}

    def _raise_for_status(self, resp, action: str) -> None:  # pragma: no cover - not used in patched paths
        if resp.status_code >= 400:
            raise RuntimeError(f"{action}:{resp.status_code}")

    def resolve_category_id(self, name: str) -> int:
        mapping = {
            "試合速報": 663,
            "選手情報": 664,
            "読売ジャイアンツ": 999,
        }
        return mapping.get(name, 0)


class FixedLaneParity037Tests(unittest.TestCase):
    def _make_candidate(self, family: str, **overrides):
        defaults = {
            "lineup_notice": {
                "game_id": "20260421-g-t",
                "lineup_kind": "starting",
                "title": "【スタメン】4月21日 巨人-阪神",
                "body_html": "<p>lineup</p>",
                "category": "試合速報",
                "tags": ["スタメン"],
                "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
            },
            "comment_notice": {
                "notice_date": "20260421",
                "speaker": "阿部慎之助監督",
                "context_slug": "postgame-qa",
                "title": "阿部監督コメント",
                "body_html": "<p>comment</p>",
                "category": "首脳陣",
                "tags": ["コメント"],
                "source_kind": lane.SOURCE_KIND_COMMENT_QUOTE,
            },
            "injury_notice": {
                "notice_date": "20260421",
                "subject": "浅野翔吾",
                "injury_status": "upper_body",
                "title": "浅野翔吾の故障状況",
                "body_html": "<p>injury</p>",
                "category": "選手情報",
                "tags": ["故障"],
                "source_kind": lane.SOURCE_KIND_COMMENT_QUOTE,
            },
            "postgame_result": {
                "game_id": "20260421-g-t",
                "result_token": "win",
                "title": "巨人 3-2 阪神",
                "body_html": "<p>postgame</p>",
                "category": "試合速報",
                "tags": ["試合結果"],
                "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
            },
            "player_stat_update": {
                "stat_date": "20260421",
                "subject": "岡本和真",
                "metric_slug": "home_run_100",
                "title": "岡本和真が節目到達",
                "body_html": "<p>stats</p>",
                "category": "選手情報",
                "tags": ["野球データ"],
                "source_kind": lane.SOURCE_KIND_PLAYER_STATS_FEED,
            },
            "program_notice": {
                "air_date": "20260421",
                "program_slug": "giants-tv",
                "title": "[04/21] ジャイアンツTV 放送予定",
                "body_html": "<p>program</p>",
                "category": "球団情報",
                "tags": ["番組"],
                "source_kind": lane.SOURCE_KIND_PROGRAM_TABLE,
            },
        }
        payload = {
            "family": family,
            "source_url": "https://example.com/source",
            "trust_tier": lane.TRUST_TIER_T1,
        }
        payload.update(defaults[family])
        payload.update(overrides)
        candidate, outcome = lane._normalize_intake_item(payload)
        self.assertIsNone(outcome)
        self.assertIsNotNone(candidate)
        return candidate

    def test_supported_pickup_families_include_parity_expansion(self):
        self.assertEqual(
            lane.supported_pickup_families(),
            (
                "program_notice",
                "transaction_notice",
                "probable_pitcher",
                "farm_result",
                "lineup_notice",
                "comment_notice",
                "injury_notice",
                "postgame_result",
                "player_stat_update",
            ),
        )

    def test_supported_pickup_source_kinds_are_fixed(self):
        self.assertEqual(
            lane.supported_pickup_source_kinds(),
            (
                "official_web",
                "npb",
                "major_rss",
                "team_x",
                "reporter_x",
                "program_table",
                "farm_info",
                "tv_radio_comment",
                "comment_quote",
                "player_stats_feed",
            ),
        )

    def test_candidate_key_builders_cover_all_parity_families(self):
        cases = [
            ("lineup_notice", {"game_id": "20260421-g-t", "lineup_kind": "starting"}, "lineup_notice:20260421-g-t:starting"),
            ("comment_notice", {"notice_date": "20260421", "speaker": "阿部慎之助監督", "context_slug": "postgame-qa"}, "comment_notice:20260421:阿部慎之助監督:postgame-qa"),
            ("injury_notice", {"notice_date": "20260421", "subject": "浅野翔吾", "injury_status": "upper_body"}, "injury_notice:20260421:浅野翔吾:upper_body"),
            ("postgame_result", {"game_id": "20260421-g-t", "result_token": "win"}, "postgame_result:20260421-g-t:win"),
            ("player_stat_update", {"stat_date": "20260421", "subject": "岡本和真", "metric_slug": "home_run_100"}, "player_stat_update:20260421:岡本和真:home_run_100"),
        ]
        for family, fields, expected in cases:
            with self.subTest(family=family):
                candidate = self._make_candidate(family, **fields)
                self.assertEqual(candidate.metadata["candidate_key"], expected)

    def test_parity_family_keeps_parent_category_and_ai_lane_target(self):
        candidate = self._make_candidate("postgame_result")

        self.assertEqual(candidate.metadata["parent_category"], "読売ジャイアンツ")
        self.assertEqual(candidate.metadata["lane_target"], lane.TARGET_LANE_AI)

    def test_duplicate_flood_is_absorbed_into_bundle_by_candidate_key(self):
        official = self._make_candidate(
            "comment_notice",
            source_url="https://www.giants.jp/news/123.html",
            trust_tier=lane.TRUST_TIER_T1,
            source_kind=lane.SOURCE_KIND_OFFICIAL_WEB,
        )
        rss = self._make_candidate(
            "comment_notice",
            source_url="https://hochi.news/articles/20260421-OHT1T51000.html",
            trust_tier=lane.TRUST_TIER_T2,
            source_kind=lane.SOURCE_KIND_MAJOR_RSS,
        )

        merged = lane._merge_candidates(official, rss)
        routed, outcomes = lane._route_candidates([official, rss])

        self.assertEqual(routed, [])
        self.assertIn(lane.ROUTE_DUPLICATE_ABSORBED, outcomes)
        self.assertIn(lane.ROUTE_DEFERRED_PICKUP, outcomes)
        self.assertEqual(
            [entry["source_kind"] for entry in merged.metadata["source_bundle"]],
            [lane.SOURCE_KIND_OFFICIAL_WEB, lane.SOURCE_KIND_MAJOR_RSS],
        )

    def test_t3_pickup_stays_trigger_only_and_is_deferred(self):
        candidate = self._make_candidate(
            "player_stat_update",
            source_url="https://x.com/hochi_giants/status/1234567890",
            trust_tier=lane.TRUST_TIER_T3,
            source_kind=lane.SOURCE_KIND_REPORTER_X,
        )

        routed, outcomes = lane._route_candidates([candidate])

        self.assertEqual(routed, [])
        self.assertEqual(candidate.metadata["source_bundle"], [])
        self.assertEqual(candidate.metadata["trigger_only_sources"][0]["source_kind"], lane.SOURCE_KIND_REPORTER_X)
        self.assertIn(lane.ROUTE_DEFERRED_PICKUP, outcomes)

    def test_fixed_lane_duplicate_skip_also_labels_deferred_pickup(self):
        candidate = self._make_candidate(
            "program_notice",
            source_url="https://www.ntv.co.jp/giants-tv/schedule",
            trust_tier=lane.TRUST_TIER_T1,
            source_kind=lane.SOURCE_KIND_PROGRAM_TABLE,
        )

        with patch.object(
            lane,
            "_find_duplicate_posts",
            return_value=[{"id": 63175, "status": "draft", "meta": {"candidate_key": candidate.metadata["candidate_key"]}}],
        ), patch.object(lane, "_create_notice_draft") as create_mock:
            result = lane._process_candidates(_FakeWP(), [candidate])

        self.assertTrue(result.duplicate_skip)
        self.assertIn(lane.ROUTE_DUPLICATE_ABSORBED, result.route_outcomes)
        self.assertIn(lane.ROUTE_DEFERRED_PICKUP, result.route_outcomes)
        create_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
