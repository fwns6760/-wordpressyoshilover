"""Tests for mail unpublish link integration in publish_notice_email_sender."""

from __future__ import annotations

import os
import unittest

from src.publish_notice_email_sender import _build_unpublish_link
from src.unpublish_token import generate_unpublish_token


class BuildUnpublishLinkTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("UNPUBLISH_BASE_URL", None)
        os.environ.pop("UNPUBLISH_TOKEN_SECRET", None)

    def tearDown(self):
        os.environ.pop("UNPUBLISH_BASE_URL", None)
        os.environ.pop("UNPUBLISH_TOKEN_SECRET", None)

    def test_link_contains_post_id_and_token(self):
        link = _build_unpublish_link(67372)
        expected_token = generate_unpublish_token(67372)
        self.assertIn("post_id=67372", link)
        self.assertIn(f"token={expected_token}", link)

    def test_default_base_url_used(self):
        link = _build_unpublish_link(67372)
        self.assertIn("yoshilover-fetcher", link)
        self.assertIn("/unpublish", link)

    def test_env_base_url_override(self):
        os.environ["UNPUBLISH_BASE_URL"] = "https://example.com/u"
        link = _build_unpublish_link(67372)
        self.assertTrue(link.startswith("https://example.com/u?"))

    def test_invalid_post_id_returns_empty(self):
        self.assertEqual(_build_unpublish_link(None), "")
        self.assertEqual(_build_unpublish_link(""), "")
        self.assertEqual(_build_unpublish_link("abc"), "")

    def test_string_int_post_id_works(self):
        self.assertIn("post_id=67372", _build_unpublish_link("67372"))


if __name__ == "__main__":
    unittest.main()
