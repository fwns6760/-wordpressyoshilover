"""028 routing tests for ``src.tools.run_notice_fixed_lane``."""

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
            "ドラフト・育成": 666,
            "球団情報": 669,
            "選手情報": 664,
            "読売ジャイアンツ": 999,
        }
        return mapping.get(name, 0)


class FixedLaneRouting028Tests(unittest.TestCase):
    def _make_candidate(self, family: str, **overrides):
        defaults = {
            "program_notice": {
                "air_date": "20260421",
                "program_slug": "giants-tv",
                "title": "[04/21] ジャイアンツTV 放送予定",
                "body_html": "<p>program</p>",
                "category": "球団情報",
                "tags": ["番組"],
            },
            "transaction_notice": {
                "notice_date": "20260420",
                "subject": "山瀬慎之助+丸佳浩",
                "notice_kind": "register_deregister",
                "title": "【公示】4月20日 巨人は山瀬慎之助を登録、丸佳浩を抹消",
                "body_html": "<p>notice</p>",
                "category": "選手情報",
                "tags": ["公示"],
            },
            "probable_pitcher": {
                "game_id": "20260421-g-t",
                "title": "【4/21予告先発】 巨人 vs 阪神",
                "body_html": "<p>pregame</p>",
                "category": "試合速報",
                "tags": ["予告先発"],
            },
            "farm_result": {
                "game_id": "farm-20260421-g-db",
                "title": "巨人二軍 4-1 結果のポイント",
                "body_html": "<p>farm</p>",
                "category": "ドラフト・育成",
                "tags": ["ファーム"],
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

    def test_supported_mvp_families_are_fixed(self):
        self.assertEqual(
            lane.supported_mvp_families(),
            ("program_notice", "transaction_notice", "probable_pitcher", "farm_result"),
        )

    def test_candidate_key_builders_cover_all_mvp_families(self):
        cases = [
            (
                "program_notice",
                {"air_date": "20260421", "program_slug": "giants-tv"},
                "program_notice:20260421:giants-tv",
            ),
            (
                "transaction_notice",
                {"notice_date": "20260420", "subject": "山瀬慎之助+丸佳浩", "notice_kind": "register_deregister"},
                "transaction_notice:20260420:山瀬慎之助+丸佳浩:register_deregister",
            ),
            (
                "probable_pitcher",
                {"game_id": "20260421-g-t"},
                "probable_pitcher:20260421-g-t",
            ),
            (
                "farm_result",
                {"game_id": "farm-20260421-g-db"},
                "farm_result:farm-20260421-g-db",
            ),
        ]
        for family, fields, expected in cases:
            with self.subTest(family=family):
                candidate = self._make_candidate(family, **fields)
                self.assertEqual(candidate.metadata["candidate_key"], expected)

    def test_t2_source_is_absorbed_into_bundle_when_t1_exists(self):
        t1 = self._make_candidate(
            "program_notice",
            source_url="https://www.ntv.co.jp/giants-tv/schedule",
            trust_tier=lane.TRUST_TIER_T1,
            air_date="20260421",
            program_slug="giants-tv",
        )
        t2 = self._make_candidate(
            "program_notice",
            source_url="https://hochi.news/articles/20260421-OHT1T50000.html",
            trust_tier=lane.TRUST_TIER_T2,
            air_date="20260421",
            program_slug="giants-tv",
        )

        routed, outcomes = lane._route_candidates([t1, t2])

        self.assertEqual(len(routed), 1)
        self.assertEqual(outcomes, [lane.ROUTE_DUPLICATE_ABSORBED])
        bundle_tiers = [entry["trust_tier"] for entry in routed[0].metadata["source_bundle"]]
        self.assertEqual(bundle_tiers, [lane.TRUST_TIER_T1, lane.TRUST_TIER_T2])

    def test_t3_source_stays_trigger_only_and_awaits_primary(self):
        candidate = self._make_candidate(
            "probable_pitcher",
            source_url="https://x.com/reporter/status/1234567890",
            trust_tier=lane.TRUST_TIER_T3,
            game_id="20260421-g-t",
        )

        routed, outcomes = lane._route_candidates([candidate])

        self.assertEqual(routed, [])
        self.assertEqual(outcomes, [lane.ROUTE_AWAIT_PRIMARY, lane.ROUTE_DEFERRED_PICKUP])
        self.assertEqual(candidate.metadata["source_bundle"], [])
        self.assertEqual(candidate.metadata["trigger_only_sources"][0]["trust_tier"], lane.TRUST_TIER_T3)

    def test_normalize_intake_items_emits_ambiguous_and_out_of_family_labels(self):
        items = [
            {
                "family": "postgame",
                "source_url": "https://example.com/postgame",
                "title": "試合結果",
                "body_html": "<p>postgame</p>",
            },
            {
                "family": "transaction_notice",
                "source_url": "https://npb.jp/announcement/roster/",
                "trust_tier": lane.TRUST_TIER_T1,
                "notice_date": "20260420",
                "title": "【公示】4月20日 巨人は公示対象を確認中",
                "body_html": "<p>ambiguous</p>",
            },
        ]

        candidates, outcomes = lane._normalize_intake_items(items)

        self.assertEqual(candidates, [])
        self.assertEqual(outcomes, [lane.ROUTE_OUT_OF_MVP_FAMILY, lane.ROUTE_AMBIGUOUS_SUBJECT])

    def test_process_candidates_marks_fixed_primary_for_t1_candidate(self):
        candidate = self._make_candidate(
            "farm_result",
            source_url="https://www.giants.jp/farm/game/20260421/",
            trust_tier=lane.TRUST_TIER_T1,
            game_id="farm-20260421-g-db",
        )

        with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
            lane,
            "_resolve_category_ids",
            return_value=[666, 999],
        ), patch.object(lane, "_resolve_tag_ids", return_value=[888]), patch.object(
            lane,
            "_create_notice_draft",
            return_value=63175,
        ):
            result = lane._process_candidates(_FakeWP(), [candidate])

        self.assertEqual(result.created_post_id, 63175)
        self.assertFalse(result.duplicate_skip)
        self.assertIn(lane.ROUTE_FIXED_PRIMARY, result.route_outcomes)

    def test_process_candidates_marks_duplicate_absorbed_when_existing_draft_matches(self):
        candidate = self._make_candidate(
            "probable_pitcher",
            source_url="https://npb.jp/games/20260421/g-t/probable",
            trust_tier=lane.TRUST_TIER_T1,
            game_id="20260421-g-t",
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
