"""Tests for ``src.tools.run_notice_fixed_lane``."""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from src.tools import run_notice_fixed_lane as lane


class _FakeWP:
    def __init__(self) -> None:
        self.api = "https://example.com/wp-json/wp/v2"
        self.auth = ("user", "pass")
        self.headers = {"Content-Type": "application/json"}

    def _raise_for_status(self, resp, action: str) -> None:
        if resp.status_code >= 400:
            raise RuntimeError(f"{action}:{resp.status_code}")

    def resolve_category_id(self, name: str) -> int:
        self.last_category_name = name
        return 664


class NoticeFixedLaneTests(unittest.TestCase):
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
        self.assertEqual(candidate.notice_date, "20260420")
        self.assertEqual(
            candidate.metadata["candidate_id"],
            "https://npb.jp/announcement/roster:transaction_notice:20260420",
        )
        self.assertEqual(candidate.metadata["subtype"], "fact_notice")
        self.assertEqual(candidate.metadata["category"], "選手情報")
        self.assertEqual(candidate.metadata["tags"], ["公示"])
        self.assertEqual(candidate.metadata["article_type"], "transaction_notice")
        self.assertIn("山瀬慎之助", candidate.title)
        self.assertIn("丸佳浩", candidate.title)
        self.assertIn("再登録", candidate.body_html)

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
    def test_duplicate_detection_handles_exists_and_not_exists(self, mock_get):
        cases = [
            ([{"id": 10}], True),
            ([], False),
        ]
        for rows, expected_exists in cases:
            with self.subTest(rows=rows):
                mock_get.return_value = Mock(status_code=200, json=lambda rows=rows: rows)
                found = lane._find_duplicate_posts(_FakeWP(), "candidate-1")
                self.assertEqual(bool(found), expected_exists)

    def test_build_candidate_id_matches_expected_format(self):
        candidate_id = lane._build_candidate_id("https://npb.jp/announcement/roster/", "20260420")

        self.assertEqual(candidate_id, "https://npb.jp/announcement/roster:transaction_notice:20260420")

    def test_max_canary_posts_caps_to_one_even_when_two_candidates_exist(self):
        candidate1 = lane.NoticeCandidate(
            source_url="https://npb.jp/announcement/roster/",
            source_id="https://npb.jp/announcement/roster",
            notice_date="20260420",
            title="first",
            body_html="<p>first</p>",
            metadata={"candidate_id": "candidate-1"},
        )
        candidate2 = lane.NoticeCandidate(
            source_url="https://npb.jp/announcement/roster/",
            source_id="https://npb.jp/announcement/roster",
            notice_date="20260421",
            title="second",
            body_html="<p>second</p>",
            metadata={"candidate_id": "candidate-2"},
        )

        with patch.object(lane, "_find_duplicate_posts", return_value=[]), patch.object(
            lane,
            "_create_notice_draft",
            side_effect=[900, 901],
        ) as create_mock:
            post_id, duplicate_skip = lane._process_candidates(
                _FakeWP(),
                [candidate1, candidate2],
                category_id=664,
            )

        self.assertEqual(post_id, 900)
        self.assertFalse(duplicate_skip)
        self.assertEqual(create_mock.call_count, 1)
        self.assertEqual(create_mock.call_args.args[1].metadata["candidate_id"], "candidate-1")


if __name__ == "__main__":
    unittest.main()
