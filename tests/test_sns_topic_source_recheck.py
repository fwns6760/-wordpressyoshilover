import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.sns_topic_source_recheck import (
    ROUTE_CANDIDATE_ONLY,
    ROUTE_DRAFT_READY,
    ROUTE_DUPLICATE_NEWS,
    ROUTE_HOLD_SENSITIVE,
    ROUTE_REJECT,
    build_draft_proposals,
    dump_sns_topic_source_recheck_report,
    evaluate_sns_topic_source_recheck_batch,
)
from src.tools import run_sns_topic_source_recheck as dry_run


class SNSTopicSourceRecheckTests(unittest.TestCase):
    def _candidate(self, **overrides):
        payload = {
            "topic_key": "player:sakamoto:state",
            "category": "player",
            "entities": ["坂本勇人"],
            "trend_terms": ["状態"],
            "signal_count": 6,
            "fact_recheck_required": True,
            "unsafe_flags": [],
        }
        payload.update(overrides)
        return payload

    def test_route_draft_ready_when_official_source_present(self):
        candidate = self._candidate()
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://www.giants.jp/news/example"],
            },
        )

        self.assertEqual(decisions[0].route, ROUTE_DRAFT_READY)
        self.assertTrue(decisions[0].source_recheck_passed)
        self.assertEqual(
            build_draft_proposals(decisions)[0].source_urls,
            ("https://www.giants.jp/news/example",),
        )

    def test_route_candidate_only_when_source_missing(self):
        candidate = self._candidate()
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {"official": False, "rss_match": False, "rumor_risk": False},
        )

        self.assertEqual(decisions[0].route, ROUTE_CANDIDATE_ONLY)
        self.assertEqual(decisions[0].reasons, ("missing_confirmed_non_sns_source",))

    def test_route_hold_sensitive_for_injury_keyword(self):
        candidate = self._candidate(
            topic_key="injury:togo:return",
            category="injury_return",
            entities=["戸郷翔征"],
            trend_terms=["復帰時期"],
        )
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://www.giants.jp/news/example"],
            },
        )

        self.assertEqual(decisions[0].route, ROUTE_HOLD_SENSITIVE)
        self.assertIn("sensitive_topic_category", decisions[0].reasons)

    def test_route_hold_sensitive_for_family_keyword(self):
        candidate = self._candidate(
            topic_key="player:sakamoto:family",
            trend_terms=["家族"],
        )
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {"official": False, "rss_match": False, "rumor_risk": False},
        )

        self.assertEqual(decisions[0].route, ROUTE_HOLD_SENSITIVE)
        self.assertIn("sensitive_keyword", decisions[0].reasons)

    def test_route_duplicate_news_when_rss_overlap(self):
        candidate = self._candidate()
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {"official": True, "rss_match": True, "rumor_risk": False},
        )

        self.assertEqual(decisions[0].route, ROUTE_DUPLICATE_NEWS)
        self.assertTrue(decisions[0].recent_news_overlap)

    def test_route_reject_when_unsafe_flag(self):
        candidate = self._candidate(unsafe=True)
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {"official": True, "rss_match": False, "rumor_risk": False},
        )

        self.assertEqual(decisions[0].route, ROUTE_REJECT)
        self.assertIn("unsafe_flag", decisions[0].reasons)

    def test_draft_proposal_has_no_raw_sns_text(self):
        candidate = self._candidate(
            post_text="生SNS本文そのまま",
            username="fan-user",
            handle="@fan123",
            source_urls=["https://x.com/fan123/status/1"],
        )
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": [
                    "https://www.giants.jp/news/example",
                    "https://x.com/fan123/status/1",
                ],
            },
        )

        proposals = build_draft_proposals(decisions)
        json_report = dump_sns_topic_source_recheck_report(decisions, fmt="json")
        human_report = dump_sns_topic_source_recheck_report(decisions, fmt="human")

        self.assertEqual(
            proposals[0].source_urls,
            ("https://www.giants.jp/news/example",),
        )
        self.assertNotIn("生SNS本文そのまま", json_report)
        self.assertNotIn("生SNS本文そのまま", human_report)
        self.assertNotIn("@fan123", json_report)
        self.assertNotIn("@fan123", human_report)
        self.assertNotIn("https://x.com/fan123/status/1", json_report)
        self.assertNotIn("https://x.com/fan123/status/1", human_report)
        self.assertNotIn("fan-user", json_report)
        self.assertNotIn("fan-user", human_report)

    def test_draft_proposal_includes_required_fields(self):
        candidate = self._candidate()
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://hochi.news/example"],
            },
        )
        proposal = build_draft_proposals(decisions)[0].as_dict()

        self.assertTrue(proposal["source_recheck_passed"])
        self.assertTrue(proposal["sns_topic_seed"])
        self.assertTrue(proposal["publish_gate_required"])
        self.assertEqual(proposal["topic_category"], "player")
        self.assertEqual(proposal["source_urls"], ["https://hochi.news/example"])

    def test_draft_proposal_includes_mock_draft_id(self):
        candidate = self._candidate()
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://hochi.news/example"],
            },
        )

        proposal = build_draft_proposals(decisions)[0]

        self.assertIn("mock_draft_id", proposal.as_dict())
        self.assertTrue(proposal.mock_draft_id)

    def test_top_level_draft_ids_array_matches_proposals(self):
        candidate = self._candidate()
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://hochi.news/example"],
            },
        )

        payload = json.loads(dump_sns_topic_source_recheck_report(decisions, fmt="json"))

        self.assertEqual(payload["draft_ids"], [payload["draft_proposals"][0]["mock_draft_id"]])

    def test_mock_draft_id_is_deterministic_from_topic_key(self):
        candidate = self._candidate()
        decisions_first = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://hochi.news/example"],
            },
        )
        decisions_second = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://hochi.news/example"],
            },
        )

        proposal_first = build_draft_proposals(decisions_first)[0]
        proposal_second = build_draft_proposals(decisions_second)[0]

        self.assertEqual(proposal_first.mock_draft_id, proposal_second.mock_draft_id)

    def test_mock_draft_id_starts_with_mock_prefix(self):
        candidate = self._candidate()
        decisions = evaluate_sns_topic_source_recheck_batch(
            [candidate],
            lambda _: {
                "official": True,
                "rss_match": False,
                "rumor_risk": False,
                "source_urls": ["https://hochi.news/example"],
            },
        )

        proposal = build_draft_proposals(decisions)[0]

        self.assertTrue(proposal.mock_draft_id.startswith("mock_draft_"))
        self.assertEqual(len(proposal.mock_draft_id), len("mock_draft_") + 16)


class RunSNSTopicSourceRecheckTests(unittest.TestCase):
    def _fixture_payload(self):
        candidate = {
            "topic_key": "player:sakamoto:state",
            "category": "player",
            "entities": ["坂本勇人"],
            "trend_terms": ["状態"],
            "signal_count": 5,
            "fact_recheck_required": True,
            "unsafe_flags": [],
        }
        return {
            "results": [candidate],
            "resolver_results": {
                "player:sakamoto:state": {
                    "official": True,
                    "rss_match": False,
                    "rumor_risk": False,
                    "source_urls": ["https://www.giants.jp/news/example"],
                }
            },
        }

    def test_cli_json_format_returns_routed_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "fixture.json"
            fixture_path.write_text(json.dumps(self._fixture_payload(), ensure_ascii=False), encoding="utf-8")

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture_path), "--format", "json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("routed_candidates", payload)
        self.assertEqual(payload["routed_candidates"]["draft_ready"]["count"], 1)
        self.assertEqual(payload["draft_proposals"][0]["topic_category"], "player")

    def test_cli_human_format_renders_route_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "fixture.json"
            fixture_path.write_text(json.dumps(self._fixture_payload(), ensure_ascii=False), encoding="utf-8")

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture_path), "--format", "human"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("SNS Topic Source Recheck Dry Run", output)
        self.assertIn("draft_ready: 1", output)
        self.assertIn("title_hint:", output)

    def test_human_format_includes_draft_ids_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "fixture.json"
            fixture_path.write_text(json.dumps(self._fixture_payload(), ensure_ascii=False), encoding="utf-8")

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = dry_run.main(["--fixture", str(fixture_path), "--format", "human"])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("draft_ids_count: 1", output)
        self.assertIn("mock_draft_id:", output)


if __name__ == "__main__":
    unittest.main()
