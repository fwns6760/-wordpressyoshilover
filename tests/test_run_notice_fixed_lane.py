"""Tests for ``src.tools.run_notice_fixed_lane``."""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from src.tools import run_notice_fixed_lane as lane


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SPLIT_ROWS_FIXTURE = FIXTURES_DIR / "npb_roster_notice_20260420_split_rows.html"


class _FakeWP:
    def __init__(self, mapping: dict[str, int] | None = None) -> None:
        self.api = "https://example.com/wp-json/wp/v2"
        self.auth = ("user", "pass")
        self.headers = {"Content-Type": "application/json"}
        self.mapping = {
            "選手情報": 664,
            "試合速報": 663,
            "ドラフト・育成": 666,
            "球団情報": 669,
            "読売ジャイアンツ": 999,
        }
        if mapping:
            self.mapping.update(mapping)

    def _raise_for_status(self, resp, action: str) -> None:
        if resp.status_code >= 400:
            raise RuntimeError(f"{action}:{resp.status_code}")

    def resolve_category_id(self, name: str) -> int:
        return self.mapping.get(name, 0)


class NoticeFixedLaneTests(unittest.TestCase):
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

    def test_parse_notice_row_accepts_split_rows_for_target_team(self):
        lines = lane._html_to_lines(SPLIT_ROWS_FIXTURE.read_text(encoding="utf-8"))
        start_index = lines.index("読売ジャイアンツ 捕手")

        entry, consumed = lane._parse_notice_row(lines[start_index:], "deregister")

        self.assertEqual(consumed, 3)
        self.assertEqual(
            entry,
            lane.NoticeEntry(
                action="deregister",
                position="捕手",
                number="67",
                player_name="山瀬慎之助",
            ),
        )

    def test_parse_latest_notice_from_html_extracts_giants_candidate(self):
        html_text = """
        <html><body>
          <h1>2026年4月20日の出場選手登録、登録抹消</h1>
          <h2>セントラル・リーグ</h2>
          <h3>出場選手登録</h3>
          <table><tr><td>読売ジャイアンツ</td><td>捕手</td><td>67</td><td>山瀬 慎之助</td></tr></table>
          <h3>出場選手登録抹消</h3>
          <table><tr><td>読売ジャイアンツ</td><td>外野手</td><td>8</td><td>丸 佳浩</td></tr></table>
          <p>※4月30日以後でなければ出場選手の再登録はできません。</p>
          <h2>パシフィック・リーグ</h2>
        </body></html>
        """

        candidate = lane._parse_latest_notice_from_html(html_text)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        expected_key = "transaction_notice:20260420:山瀬慎之助+丸佳浩:register_deregister"
        self.assertEqual(candidate.notice_date, "20260420")
        self.assertEqual(
            candidate.metadata["candidate_id"],
            "https://npb.jp/announcement/roster:transaction_notice:20260420",
        )
        self.assertEqual(candidate.metadata["candidate_key"], expected_key)
        self.assertEqual(candidate.candidate_slug, lane._build_candidate_slug(expected_key))
        self.assertEqual(candidate.metadata["subtype"], "fact_notice")
        self.assertEqual(candidate.metadata["category"], "選手情報")
        self.assertEqual(candidate.metadata["parent_category"], "読売ジャイアンツ")
        self.assertEqual(candidate.metadata["tags"], ["公示"])
        self.assertEqual(candidate.metadata["article_type"], "transaction_notice")
        self.assertEqual(candidate.metadata["primary_trust_tier"], lane.TRUST_TIER_T1)
        self.assertEqual(candidate.metadata["source_bundle"][0]["trust_tier"], lane.TRUST_TIER_T1)
        self.assertIn("山瀬慎之助", candidate.title)
        self.assertIn("丸佳浩", candidate.title)
        self.assertIn("再登録", candidate.body_html)

    def test_parse_latest_notice_from_split_row_fixture_extracts_candidate_key_and_slug(self):
        candidate = lane._parse_latest_notice_from_html(
            SPLIT_ROWS_FIXTURE.read_text(encoding="utf-8"),
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        expected_key = "transaction_notice:20260420:山瀬慎之助+丸佳浩:deregister"
        self.assertEqual(candidate.notice_date, "20260420")
        self.assertEqual(candidate.metadata["candidate_key"], expected_key)
        self.assertEqual(candidate.candidate_slug, lane._build_candidate_slug(expected_key))
        self.assertIn("山瀬慎之助", candidate.title)
        self.assertIn("丸佳浩", candidate.title)
        self.assertIn("yoshilover_notice_meta", candidate.body_html)

    @patch("src.tools.run_notice_fixed_lane.requests.delete")
    @patch("src.tools.run_notice_fixed_lane.requests.post")
    def test_wp_post_dry_run_success_creates_and_deletes_probe(self, mock_post, mock_delete):
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 321})
        mock_delete.return_value = Mock(status_code=200, json=lambda: {"deleted": True})

        result = lane._run_wp_post_dry_run(_FakeWP(), now=datetime(2026, 4, 21, 7, 30, 45))

        self.assertEqual(result, "pass")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_delete.call_count, 1)
        self.assertIn("canary-probe-20260421-073045", mock_post.call_args.kwargs["json"]["title"])
        self.assertEqual(mock_delete.call_args.kwargs["params"], {"force": "true"})

    @patch("src.tools.run_notice_fixed_lane.requests.get")
    def test_fetch_latest_notice_candidate_prefers_apparent_utf8_when_requests_defaults_to_latin1(self, mock_get):
        response = requests.Response()
        response.status_code = 200
        response._content = SPLIT_ROWS_FIXTURE.read_bytes()
        response.encoding = "ISO-8859-1"

        mock_get.return_value = response

        candidate = lane._fetch_latest_notice_candidate()

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.notice_date, "20260420")
        self.assertIn("山瀬慎之助", candidate.title)

    @patch("src.tools.run_notice_fixed_lane.requests.post")
    def test_wp_post_dry_run_failure_covers_401_and_403(self, mock_post):
        cases = [
            (401, "fail:application_password_unauthorized"),
            (403, "fail:wp_permission_forbidden"),
        ]
        for status_code, expected in cases:
            with self.subTest(status_code=status_code):
                mock_post.return_value = Mock(status_code=status_code, text="{}")
                result = lane._run_wp_post_dry_run(_FakeWP(), now=datetime(2026, 4, 21, 7, 30, 45))
                self.assertEqual(result, expected)

    @patch("src.tools.run_notice_fixed_lane.requests.get")
    def test_duplicate_detection_filters_candidate_key_from_draft_list(self, mock_get):
        candidate = self._make_candidate(
            "transaction_notice",
            source_url="https://npb.jp/announcement/roster/",
        )
        mock_get.side_effect = [
            Mock(
                status_code=200,
                json=lambda: [
                    {
                        "id": 63056,
                        "status": "draft",
                        "meta": {"candidate_key": candidate.metadata["candidate_key"]},
                    },
                    {"id": 61000, "status": "draft", "meta": {"candidate_key": "candidate-x"}},
                    {
                        "id": 63082,
                        "status": "draft",
                        "meta": {"candidate_key": candidate.metadata["candidate_key"]},
                    },
                    {
                        "id": 62000,
                        "status": "publish",
                        "meta": {"candidate_key": candidate.metadata["candidate_key"]},
                    },
                ],
            ),
        ]

        found = lane._find_duplicate_posts(_FakeWP(), candidate)

        self.assertEqual([row["id"] for row in found], [63056, 63082])
        first_call = mock_get.call_args_list[0]
        self.assertEqual(first_call.kwargs["params"]["status"], "any")
        self.assertEqual(first_call.kwargs["params"]["search"], candidate.title[:40])
        self.assertEqual(first_call.kwargs["params"]["context"], "edit")
        self.assertEqual(
            first_call.kwargs["params"]["_fields"],
            "id,status,slug,generated_slug,title,meta,date",
        )

    @patch("src.tools.run_notice_fixed_lane.requests.get")
    def test_duplicate_detection_falls_back_to_slug_or_title_when_meta_is_missing(self, mock_get):
        candidate = self._make_candidate(
            "transaction_notice",
            source_url="https://npb.jp/announcement/roster/",
        )
        mock_get.return_value = Mock(
            status_code=200,
            headers={"X-WP-TotalPages": "1"},
            json=lambda: [
                {
                    "id": 63161,
                    "status": "draft",
                    "slug": candidate.candidate_slug,
                    "title": {"raw": candidate.title},
                    "meta": {},
                }
            ],
        )

        found = lane._find_duplicate_posts(_FakeWP(), candidate)

        self.assertEqual([row["id"] for row in found], [63161])

    @patch("src.tools.run_notice_fixed_lane.requests.post")
    @patch("src.tools.run_notice_fixed_lane.requests.get")
    def test_resolve_tag_ids_creates_missing_tag(self, mock_get, mock_post):
        mock_get.return_value = Mock(status_code=200, json=lambda: [])
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 777})

        tag_ids = lane._resolve_tag_ids(_FakeWP(), ["公示"])

        self.assertEqual(tag_ids, [777])
        self.assertEqual(mock_post.call_args.kwargs["json"], {"name": "公示"})

    def test_process_candidates_respects_max_canary_cap(self):
        candidate1 = self._make_candidate("transaction_notice")
        candidate2 = self._make_candidate("program_notice")

        with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
            lane,
            "_resolve_category_ids",
            side_effect=[[664, 999], [669, 999]],
        ), patch.object(lane, "_resolve_tag_ids", return_value=[777]), patch.object(
            lane,
            "_create_notice_draft",
            side_effect=[900, 901],
        ) as create_mock:
            result = lane._process_candidates(_FakeWP(), [candidate1, candidate2])

        self.assertEqual(result.created_post_id, 900)
        self.assertFalse(result.duplicate_skip)
        self.assertIn(lane.ROUTE_FIXED_PRIMARY, result.route_outcomes)
        self.assertEqual(create_mock.call_count, 1)
        self.assertEqual(create_mock.call_args.args[1].metadata["candidate_id"], candidate1.metadata["candidate_id"])

    def test_process_candidates_skips_create_when_duplicate_draft_exists(self):
        candidate = self._make_candidate("transaction_notice")

        with patch.object(
            lane,
            "_find_duplicate_posts",
            return_value=[
                {"id": 63056, "status": "draft", "meta": {"candidate_key": candidate.metadata["candidate_key"]}},
                {"id": 63082, "status": "draft", "meta": {"candidate_key": candidate.metadata["candidate_key"]}},
            ],
        ), patch.object(lane, "_create_notice_draft") as create_mock:
            result = lane._process_candidates(_FakeWP(), [candidate])

        self.assertIsNone(result.created_post_id)
        self.assertTrue(result.duplicate_skip)
        self.assertIn(lane.ROUTE_DUPLICATE_ABSORBED, result.route_outcomes)
        create_mock.assert_not_called()

    @patch("src.tools.run_notice_fixed_lane.requests.post")
    def test_create_notice_draft_includes_child_and_parent_categories(self, mock_post):
        candidate = self._make_candidate("transaction_notice")
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 63175})

        post_id = lane._create_notice_draft(_FakeWP(), candidate, [664, 999], [777])

        self.assertEqual(post_id, 63175)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["categories"], [664, 999])
        self.assertEqual(payload["meta"]["parent_category"], "読売ジャイアンツ")
        self.assertEqual(payload["meta"]["candidate_key"], candidate.metadata["candidate_key"])


if __name__ == "__main__":
    unittest.main()
