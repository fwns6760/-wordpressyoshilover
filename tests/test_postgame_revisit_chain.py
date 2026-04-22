"""047 postgame revisit chain tests."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from unittest.mock import patch

from src import postgame_revisit_chain as chain
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


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, int]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, int]:
        return self._payload


class PostgameRevisitChain047Tests(unittest.TestCase):
    def _base_context(self, **overrides):
        context = {
            "title": "巨人 3-2 阪神",
            "body_html": "<p>postgame</p>",
            "game_id": "20260421-g-t",
            "result_token": "win",
            "candidate_key": "postgame_result:20260421-g-t:win",
            "source_url": "https://npb.jp/games/20260421/g-t/scoreboard.html",
            "source_kind": lane.SOURCE_KIND_NPB,
            "trust_tier": lane.TRUST_TIER_T1,
            "metadata": {
                "accepted_at": "2026-04-22T09:00:00",
                "primary_trust_tier": lane.TRUST_TIER_T1,
                "pickup_source_kind": lane.SOURCE_KIND_NPB,
                "article_subtype": "postgame",
                "game_id": "20260421-g-t",
                "result_token": "win",
                "candidate_key": "postgame_result:20260421-g-t:win",
            },
        }
        for key, value in overrides.items():
            if key == "metadata":
                context["metadata"].update(value)
            else:
                context[key] = value
        return context

    def _make_postgame_candidate(self, **metadata_overrides):
        payload = {
            "family": "postgame_result",
            "game_id": "20260421-g-t",
            "result_token": "win",
            "title": "巨人 3-2 阪神",
            "body_html": "<p>postgame</p>",
            "category": "試合速報",
            "tags": ["試合結果"],
            "source_url": "https://npb.jp/games/20260421/g-t/scoreboard.html",
            "trust_tier": lane.TRUST_TIER_T1,
            "source_kind": lane.SOURCE_KIND_NPB,
            "metadata": {
                "accepted_at": "2026-04-22T09:00:00",
                "primary_trust_tier": lane.TRUST_TIER_T1,
                "pickup_source_kind": lane.SOURCE_KIND_NPB,
                "article_subtype": "postgame",
            },
        }
        payload["metadata"].update(metadata_overrides)
        candidate, outcome = lane._normalize_intake_item(payload)
        self.assertIsNone(outcome)
        self.assertIsNotNone(candidate)
        return candidate

    def test_player_primary_emits_fixed_primary_derivative(self):
        context = self._base_context(
            metadata={
                "player_weights": [
                    {
                        "player": "岡本和真",
                        "weight": 0.78,
                        "impact": "game_deciding",
                        "achievement": "決勝本塁打",
                        "trust_tier": lane.TRUST_TIER_T1,
                        "source_kind": lane.SOURCE_KIND_NPB,
                    },
                    {"player": "吉川尚輝", "weight": 0.31},
                ]
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(len(derivatives), 1)
        self.assertEqual(derivatives[0].family, "player")
        self.assertEqual(derivatives[0].route, chain.ROUTE_FIXED_PRIMARY_DERIVATIVE)

    def test_manager_primary_emits_fixed_primary_derivative(self):
        quote = "阿部監督" + "次戦への布石を語る。" * 40
        context = self._base_context(
            metadata={
                "manager_comment": {
                    "speaker": "阿部慎之助監督",
                    "quote": quote,
                    "topics": ["tactics", "next_game_plan"],
                    "trust_tier": lane.TRUST_TIER_T1,
                    "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
                    "source_url": "https://www.giants.jp/news/postgame-comment/",
                }
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual([d.family for d in derivatives], ["manager"])
        self.assertEqual(derivatives[0].route, chain.ROUTE_FIXED_PRIMARY_DERIVATIVE)

    def test_transaction_primary_emits_fixed_primary_derivative(self):
        context = self._base_context(
            metadata={
                "transaction_events": [
                    {
                        "subject": "浅野翔吾",
                        "notice_kind": "injury",
                        "summary": "右肩の状態を確認するため登録抹消。",
                        "observed_at": "2026-04-22T10:00:00",
                        "trust_tier": lane.TRUST_TIER_T1,
                        "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
                        "source_url": "https://www.giants.jp/news/roster/",
                    }
                ]
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual([d.family for d in derivatives], ["transaction"])
        self.assertEqual(derivatives[0].route, chain.ROUTE_FIXED_PRIMARY_DERIVATIVE)

    def test_data_primary_emits_fixed_primary_derivative(self):
        context = self._base_context(
            metadata={
                "data_points": [
                    {
                        "subject": "岡本和真",
                        "metric_slug": "100_home_run",
                        "milestone_kind": "personal_milestone",
                        "tags": ["野球データ", "岡本和真"],
                        "summary": "通算100本塁打に到達。",
                        "trust_tier": lane.TRUST_TIER_T1,
                        "source_kind": lane.SOURCE_KIND_NPB,
                    }
                ]
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual([d.family for d in derivatives], ["data"])
        self.assertEqual(derivatives[0].route, chain.ROUTE_FIXED_PRIMARY_DERIVATIVE)

    def test_player_secondary_stays_deferred_pickup_derivative(self):
        context = self._base_context(
            metadata={
                "player_weights": [
                    {
                        "player": "岡本和真",
                        "weight": 0.78,
                        "impact": "game_deciding",
                        "achievement": "決勝本塁打",
                        "trust_tier": lane.TRUST_TIER_T2,
                        "source_kind": lane.SOURCE_KIND_MAJOR_RSS,
                    }
                ]
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(derivatives[0].route, chain.ROUTE_DEFERRED_PICKUP_DERIVATIVE)

    def test_manager_secondary_stays_deferred_pickup_derivative(self):
        quote = "阿部監督" + "投手起用の狙いを整理する。" * 40
        context = self._base_context(
            metadata={
                "manager_comment": {
                    "speaker": "阿部慎之助監督",
                    "quote": quote,
                    "topics": ["strategy"],
                    "trust_tier": lane.TRUST_TIER_T2,
                    "source_kind": lane.SOURCE_KIND_MAJOR_RSS,
                    "source_url": "https://hochi.news/articles/postgame-comment.html",
                }
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(derivatives[0].route, chain.ROUTE_DEFERRED_PICKUP_DERIVATIVE)

    def test_transaction_rumor_stays_deferred_pickup_derivative(self):
        context = self._base_context(
            metadata={
                "transaction_events": [
                    {
                        "subject": "浅野翔吾",
                        "notice_kind": "injury",
                        "summary": "状態について記者が言及。",
                        "observed_at": "2026-04-22T10:00:00",
                        "trust_tier": lane.TRUST_TIER_T3,
                        "source_kind": lane.SOURCE_KIND_REPORTER_X,
                        "source_url": "https://x.com/reporter/status/12345",
                    }
                ]
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(derivatives[0].route, chain.ROUTE_DEFERRED_PICKUP_DERIVATIVE)

    def test_data_secondary_stays_deferred_pickup_derivative(self):
        context = self._base_context(
            metadata={
                "data_points": [
                    {
                        "subject": "岡本和真",
                        "metric_slug": "league_top_hr",
                        "milestone_kind": "league_rank",
                        "tags": ["野球データ", "岡本和真"],
                        "summary": "本塁打数でリーグ首位に並んだ。",
                        "trust_tier": lane.TRUST_TIER_T2,
                        "source_kind": lane.SOURCE_KIND_MAJOR_RSS,
                    }
                ]
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(derivatives[0].route, chain.ROUTE_DEFERRED_PICKUP_DERIVATIVE)

    def test_max_four_derivatives_cap_drops_fifth_candidate(self):
        context = self._base_context(
            metadata={
                "player_weights": [
                    {
                        "player": "岡本和真",
                        "weight": 0.80,
                        "impact": "game_deciding",
                        "achievement": "決勝本塁打",
                        "trust_tier": lane.TRUST_TIER_T1,
                        "source_kind": lane.SOURCE_KIND_NPB,
                    }
                ],
                "manager_comment": {
                    "speaker": "阿部慎之助監督",
                    "quote": "采配の狙いを説明する。" * 30,
                    "topics": ["tactics"],
                    "trust_tier": lane.TRUST_TIER_T1,
                    "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
                },
                "transaction_events": [
                    {
                        "subject": "浅野翔吾",
                        "notice_kind": "injury",
                        "observed_at": "2026-04-22T10:00:00",
                        "trust_tier": lane.TRUST_TIER_T1,
                        "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
                    },
                    {
                        "subject": "門脇誠",
                        "notice_kind": "register",
                        "observed_at": "2026-04-22T11:00:00",
                        "trust_tier": lane.TRUST_TIER_T1,
                        "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
                    },
                ],
                "data_points": [
                    {
                        "subject": "岡本和真",
                        "metric_slug": "100_home_run",
                        "milestone_kind": "personal_milestone",
                        "tags": ["野球データ", "岡本和真"],
                        "trust_tier": lane.TRUST_TIER_T1,
                        "source_kind": lane.SOURCE_KIND_NPB,
                    }
                ],
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(len(derivatives), 4)
        self.assertEqual([d.family for d in derivatives], ["player", "manager", "transaction", "transaction"])

    def test_live_anchor_state_emits_no_derivative(self):
        context = self._base_context(metadata={"article_subtype": "live_anchor", "post_state": "live"})
        context["metadata"]["player_weights"] = [
            {
                "player": "岡本和真",
                "weight": 0.80,
                "impact": "game_deciding",
                "achievement": "決勝本塁打",
                "trust_tier": lane.TRUST_TIER_T1,
                "source_kind": lane.SOURCE_KIND_NPB,
            }
        ]

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(derivatives, [])

    def test_outside_24h_window_emits_no_derivative(self):
        context = self._base_context(metadata={"accepted_at": "2026-04-20T08:00:00"})
        context["metadata"]["player_weights"] = [
            {
                "player": "岡本和真",
                "weight": 0.80,
                "impact": "game_deciding",
                "achievement": "決勝本塁打",
                "trust_tier": lane.TRUST_TIER_T1,
                "source_kind": lane.SOURCE_KIND_NPB,
            }
        ]

        derivatives = chain.aggregate_postgame_derivatives(
            context,
            now=lane.datetime(2026, 4, 22, 12, 0, 0),
        )

        self.assertEqual(derivatives, [])

    def test_thin_manager_comment_is_not_promoted(self):
        context = self._base_context(
            metadata={
                "manager_comment": {
                    "speaker": "阿部慎之助監督",
                    "quote": "良かったです。" * 10,
                    "topics": ["tactics"],
                    "trust_tier": lane.TRUST_TIER_T1,
                    "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
                }
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(derivatives, [])

    def test_dispersed_player_weights_do_not_emit_player_derivative(self):
        context = self._base_context(
            metadata={
                "player_weights": [
                    {
                        "player": "岡本和真",
                        "weight": 0.51,
                        "impact": "game_deciding",
                        "achievement": "決勝打",
                        "trust_tier": lane.TRUST_TIER_T1,
                    },
                    {
                        "player": "吉川尚輝",
                        "weight": 0.44,
                        "impact": "special_performance",
                        "achievement": "猛打賞",
                        "trust_tier": lane.TRUST_TIER_T1,
                    },
                ]
            }
        )

        derivatives = chain.aggregate_postgame_derivatives(context)

        self.assertEqual(derivatives, [])

    def test_hook_emits_fixed_and_deferred_routes_to_stdout(self):
        candidate = self._make_postgame_candidate(
            player_weights=[
                {
                    "player": "岡本和真",
                    "weight": 0.78,
                    "impact": "game_deciding",
                    "achievement": "決勝本塁打",
                    "trust_tier": lane.TRUST_TIER_T1,
                    "source_kind": lane.SOURCE_KIND_NPB,
                }
            ],
            manager_comment={
                "speaker": "阿部慎之助監督",
                "quote": "采配の狙いを説明する。" * 30,
                "topics": ["tactics"],
                "trust_tier": lane.TRUST_TIER_T2,
                "source_kind": lane.SOURCE_KIND_MAJOR_RSS,
                "source_url": "https://hochi.news/articles/postgame-comment.html",
            },
        )
        stdout = io.StringIO()
        with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
            lane,
            "_resolve_category_ids",
            return_value=[664, 999],
        ), patch.object(lane, "_resolve_tag_ids", return_value=[777]), patch.object(
            lane,
            "maybe_generate_structured_eyecatch_media",
            return_value=None,
        ), patch.object(
            lane.requests,
            "post",
            return_value=_FakeResponse(201, {"id": 64100}),
        ) as post_mock:
            with redirect_stdout(stdout):
                outcomes = lane._process_postgame_revisit_chain(_FakeWP(), candidate)

        self.assertEqual(post_mock.call_count, 1)
        self.assertIn(chain.ROUTE_FIXED_PRIMARY_DERIVATIVE, outcomes)
        self.assertIn(chain.ROUTE_DEFERRED_PICKUP_DERIVATIVE, outcomes)
        output = stdout.getvalue()
        self.assertIn('"route": "fixed_primary_derivative"', output)
        self.assertIn('"route": "deferred_pickup_derivative"', output)

    def test_derivative_candidate_key_stays_disjoint_and_duplicate_is_absorbed(self):
        candidate = self._make_postgame_candidate(
            player_weights=[
                {
                    "player": "岡本和真",
                    "weight": 0.78,
                    "impact": "game_deciding",
                    "achievement": "決勝本塁打",
                    "trust_tier": lane.TRUST_TIER_T1,
                    "source_kind": lane.SOURCE_KIND_NPB,
                }
            ]
        )
        context = lane._build_postgame_revisit_context(candidate)
        derivatives = chain.aggregate_postgame_derivatives(context)
        self.assertEqual(len(derivatives), 1)
        self.assertNotEqual(derivatives[0].candidate_key, candidate.metadata["candidate_key"])
        self.assertTrue(derivatives[0].candidate_key.startswith("postgame_player:"))

        stdout = io.StringIO()
        with patch.object(
            lane,
            "_find_duplicate_posts",
            return_value=[{"id": 65001, "status": "draft", "meta": {"candidate_key": derivatives[0].candidate_key}}],
        ), patch.object(lane, "_create_notice_draft") as create_mock:
            with redirect_stdout(stdout):
                outcomes = lane._process_postgame_revisit_chain(_FakeWP(), candidate)

        self.assertIn(lane.ROUTE_DUPLICATE_ABSORBED, outcomes)
        create_mock.assert_not_called()
        self.assertIn('"route": "duplicate_absorbed"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
