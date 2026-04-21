"""046 parity first-wave promotion tests for ``src.tools.run_notice_fixed_lane``."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
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
            "首脳陣": 665,
            "読売ジャイアンツ": 999,
        }
        return mapping.get(name, 0)


class FixedLaneParityFirstWave046Tests(unittest.TestCase):
    def _make_candidate(self, family: str, **overrides):
        defaults = {
            "lineup_notice": {
                "game_id": "20260421-g-t",
                "lineup_kind": "starting",
                "title": "【スタメン】4月21日 巨人-阪神",
                "body_html": "<p>lineup</p>",
                "category": "試合速報",
                "tags": ["スタメン"],
                "source_url": "https://x.com/tokyogiants/status/2026042101",
                "trust_tier": lane.TRUST_TIER_T2,
                "source_kind": lane.SOURCE_KIND_TEAM_X,
            },
            "comment_notice": {
                "notice_date": "20260421",
                "speaker": "阿部慎之助監督",
                "context_slug": "postgame-qa",
                "title": "阿部監督コメント",
                "body_html": "<p>comment</p>",
                "category": "首脳陣",
                "tags": ["コメント"],
                "source_url": "https://hochi.news/articles/20260421-OHT1T51000.html",
                "trust_tier": lane.TRUST_TIER_T2,
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
                "source_url": "https://www.giants.jp/news/20260421_1234/",
                "trust_tier": lane.TRUST_TIER_T1,
                "source_kind": lane.SOURCE_KIND_COMMENT_QUOTE,
            },
            "postgame_result": {
                "game_id": "20260421-g-t",
                "result_token": "win",
                "title": "巨人 3-2 阪神",
                "body_html": "<p>postgame</p>",
                "category": "試合速報",
                "tags": ["試合結果"],
                "source_url": "https://npb.jp/games/20260421/g-t/scoreboard.html",
                "trust_tier": lane.TRUST_TIER_T1,
                "source_kind": lane.SOURCE_KIND_NPB,
            },
        }
        payload = {"family": family}
        payload.update(defaults[family])
        payload.update(overrides)
        candidate, outcome = lane._normalize_intake_item(payload)
        self.assertIsNone(outcome)
        self.assertIsNotNone(candidate)
        return candidate

    def test_first_wave_boundary_sources_promote_to_fixed_primary(self):
        cases = [
            ("lineup_notice", lane.SOURCE_KIND_TEAM_X, lane.TRUST_TIER_T2),
            ("comment_notice", lane.SOURCE_KIND_COMMENT_QUOTE, lane.TRUST_TIER_T2),
            ("injury_notice", lane.SOURCE_KIND_COMMENT_QUOTE, lane.TRUST_TIER_T1),
            ("postgame_result", lane.SOURCE_KIND_NPB, lane.TRUST_TIER_T1),
        ]
        for family, expected_source_kind, expected_trust_tier in cases:
            with self.subTest(family=family):
                candidate = self._make_candidate(family)
                stdout = io.StringIO()
                with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
                    lane,
                    "_resolve_category_ids",
                    return_value=[candidate.metadata["category"] == "試合速報" and 663 or 664, 999],
                ), patch.object(lane, "_resolve_tag_ids", return_value=[777]), patch.object(
                    lane,
                    "_create_notice_draft",
                    wraps=lane._create_notice_draft,
                ) as create_mock, patch.object(
                    lane,
                    "maybe_generate_structured_eyecatch_media",
                    return_value=None,
                ), patch.object(
                    lane.requests,
                    "post",
                    return_value=_FakeResponse(201, {"id": 63175}),
                ):
                    with redirect_stdout(stdout):
                        result = lane._process_candidates(_FakeWP(), [candidate])

                self.assertEqual(result.created_post_id, 63175)
                self.assertIn(lane.ROUTE_FIXED_PRIMARY, result.route_outcomes)
                create_mock.assert_called_once()
                output = stdout.getvalue()
                self.assertIn('"event": "canary_post_created"', output)
                self.assertIn('"route": "fixed_primary"', output)
                self.assertIn(f'"subtype": "{family}"', output)
                self.assertIn(f'"source_kind": "{expected_source_kind}"', output)
                self.assertIn(f'"trust_tier": "{expected_trust_tier}"', output)

    def test_first_wave_outside_boundary_stays_deferred_pickup(self):
        cases = [
            ("lineup_notice", {"source_url": "https://hochi.news/articles/20260421-OHT1T50000.html", "trust_tier": lane.TRUST_TIER_T2, "source_kind": lane.SOURCE_KIND_MAJOR_RSS}, lane.SOURCE_KIND_MAJOR_RSS, lane.TRUST_TIER_T2),
            ("comment_notice", {"source_url": "https://x.com/hochi_giants/status/2026042102", "trust_tier": lane.TRUST_TIER_T3, "source_kind": lane.SOURCE_KIND_REPORTER_X}, lane.SOURCE_KIND_REPORTER_X, lane.TRUST_TIER_T3),
            ("injury_notice", {"source_url": "https://hochi.news/articles/20260421-OHT1T50001.html", "trust_tier": lane.TRUST_TIER_T2, "source_kind": lane.SOURCE_KIND_MAJOR_RSS}, lane.SOURCE_KIND_MAJOR_RSS, lane.TRUST_TIER_T2),
            ("postgame_result", {"source_url": "https://hochi.news/articles/20260421-OHT1T50002.html", "trust_tier": lane.TRUST_TIER_T2, "source_kind": lane.SOURCE_KIND_MAJOR_RSS}, lane.SOURCE_KIND_MAJOR_RSS, lane.TRUST_TIER_T2),
        ]
        for family, overrides, expected_source_kind, expected_trust_tier in cases:
            with self.subTest(family=family):
                candidate = self._make_candidate(family, **overrides)
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    routed, outcomes = lane._route_candidates([candidate])

                self.assertEqual(routed, [])
                self.assertEqual(outcomes, [lane.ROUTE_DEFERRED_PICKUP])
                output = stdout.getvalue()
                self.assertIn('"event": "deferred_pickup"', output)
                self.assertIn('"route": "deferred_pickup"', output)
                self.assertIn(f'"subtype": "{family}"', output)
                self.assertIn(f'"source_kind": "{expected_source_kind}"', output)
                self.assertIn(f'"trust_tier": "{expected_trust_tier}"', output)

    def test_first_wave_promoted_candidates_still_dedupe_by_candidate_key(self):
        families = (
            "lineup_notice",
            "comment_notice",
            "injury_notice",
            "postgame_result",
        )
        for family in families:
            with self.subTest(family=family):
                candidate = self._make_candidate(family)
                with patch.object(
                    lane,
                    "_find_duplicate_posts",
                    return_value=[{"id": 63175, "status": "draft", "meta": {"candidate_key": candidate.metadata["candidate_key"]}}],
                ), patch.object(lane, "_create_notice_draft") as create_mock:
                    result = lane._process_candidates(_FakeWP(), [candidate])

                self.assertIsNone(result.created_post_id)
                self.assertTrue(result.duplicate_skip)
                self.assertIn(lane.ROUTE_DUPLICATE_ABSORBED, result.route_outcomes)
                self.assertIn(lane.ROUTE_DEFERRED_PICKUP, result.route_outcomes)
                create_mock.assert_not_called()


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, int]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, int]:
        return self._payload


if __name__ == "__main__":
    unittest.main()
