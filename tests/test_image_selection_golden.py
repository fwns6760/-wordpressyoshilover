import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src import rss_fetcher
from src.wp_client import WPClient


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "image_selection_golden.json"


class ImageSelectionGoldenTests(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    def test_image_selection_fixture(self):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                case_type = case["type"]
                if case_type == "candidate_filter":
                    self._assert_candidate_filter_case(case)
                elif case_type == "upload_mime":
                    self._assert_upload_mime_case(case)
                elif case_type == "mime_allow":
                    self._assert_mime_allow_case(case)
                else:
                    self.fail(f"unexpected case type: {case_type}")

    def _assert_candidate_filter_case(self, case: dict):
        if "expected_log" in case:
            with self.assertLogs("rss_fetcher", level="INFO") as cm:
                actual = rss_fetcher._filter_image_candidates(
                    case["candidate_urls"],
                    case["source_url"],
                )
            self.assertEqual(len(cm.records), 1)
            payload = json.loads(cm.records[0].getMessage())
            self.assertEqual(payload, case["expected_log"])
        else:
            actual = rss_fetcher._filter_image_candidates(
                case["candidate_urls"],
                case["source_url"],
            )
        self.assertEqual(actual, case["expected_urls"])

    @patch("src.wp_client.requests.post")
    @patch("src.wp_client.requests.get")
    def _assert_upload_mime_case(self, case: dict, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            headers={"Content-Type": case["content_type"]},
            content=b"svg",
        )
        mock_get.return_value.raise_for_status = Mock()

        with patch("builtins.print") as mock_print:
            media_id = self.wp.upload_image_from_url(
                case["image_url"],
                source_url=case["source_url"],
            )

        self.assertEqual(media_id, 0)
        mock_post.assert_not_called()

        payloads = []
        for call in mock_print.call_args_list:
            if not call.args:
                continue
            message = call.args[0]
            if isinstance(message, str) and message.startswith("{"):
                payloads.append(json.loads(message))
        self.assertIn(case["expected_log"], payloads)

    def _assert_mime_allow_case(self, case: dict):
        for content_type in case["content_types"]:
            with self.subTest(content_type=content_type):
                self.assertEqual(self.wp._get_image_mime_exclusion_reason(content_type), "")


if __name__ == "__main__":
    unittest.main()
