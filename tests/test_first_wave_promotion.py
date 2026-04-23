"""046-A1 fixture tests for first-wave pickup promotion."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.first_wave_promotion import (
    FIRST_WAVE_FAMILIES,
    ROUTE_DEFERRED_PICKUP,
    ROUTE_DUPLICATE_ABSORBED,
    ROUTE_FIXED_PRIMARY,
    judge_first_wave_batch,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "first_wave"
EXPECTED_ROUTES = {
    ROUTE_FIXED_PRIMARY,
    ROUTE_DEFERRED_PICKUP,
    ROUTE_DUPLICATE_ABSORBED,
}


class FirstWavePromotionFixtureTests(unittest.TestCase):
    def test_first_wave_4_family_3_branch_fixtures_are_fixed(self) -> None:
        fixtures = _load_fixtures()
        self.assertEqual(len(fixtures), 12)

        observed = set()
        for path, fixture in fixtures:
            with self.subTest(fixture=path.name):
                decisions = judge_first_wave_batch(
                    fixture["candidates"],
                    existing_candidate_keys=fixture.get("existing_candidate_keys", ()),
                )
                self.assertEqual(len(decisions), 1)
                decision = decisions[0]
                self.assertEqual(decision.route, fixture["expected_route"])
                self.assertIn(decision.route, EXPECTED_ROUTES)
                self.assertIn(decision.subtype, FIRST_WAVE_FAMILIES)
                self.assertTrue(decision.candidate_key)
                self.assertTrue(decision.source_kind)
                self.assertTrue(decision.trust_tier)
                observed.add((decision.subtype, decision.route))

        expected = {
            (family, route)
            for family in FIRST_WAVE_FAMILIES
            for route in EXPECTED_ROUTES
        }
        self.assertEqual(observed, expected)

    def test_trust_outside_boundary_never_promotes(self) -> None:
        for path, fixture in _load_fixtures("*_deferred_pickup.json"):
            with self.subTest(fixture=path.name):
                decision = judge_first_wave_batch(fixture["candidates"])[0]
                self.assertEqual(decision.route, ROUTE_DEFERRED_PICKUP)

    def test_duplicate_candidate_key_absorbs_before_promotion(self) -> None:
        for path, fixture in _load_fixtures("*_duplicate_absorbed.json"):
            with self.subTest(fixture=path.name):
                decision = judge_first_wave_batch(
                    fixture["candidates"],
                    existing_candidate_keys=fixture["existing_candidate_keys"],
                )[0]
                self.assertEqual(decision.route, ROUTE_DUPLICATE_ABSORBED)


def _load_fixtures(pattern: str = "*.json") -> list[tuple[Path, dict]]:
    fixtures = []
    for path in sorted(FIXTURE_DIR.glob(pattern)):
        with path.open(encoding="utf-8") as handle:
            fixtures.append((path, json.load(handle)))
    return fixtures


if __name__ == "__main__":
    unittest.main()
