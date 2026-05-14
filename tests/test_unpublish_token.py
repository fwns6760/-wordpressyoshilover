"""Tests for src/unpublish_token.py (mail unpublish 1-click 機能)."""

from __future__ import annotations

import os
import unittest

from src import unpublish_token


class UnpublishTokenTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("UNPUBLISH_TOKEN_SECRET", None)

    def tearDown(self):
        os.environ.pop("UNPUBLISH_TOKEN_SECRET", None)

    def test_generate_returns_24_char_hex(self):
        token = unpublish_token.generate_unpublish_token(67372)
        self.assertEqual(len(token), 24)
        self.assertTrue(all(c in "0123456789abcdef" for c in token))

    def test_same_post_id_same_token(self):
        t1 = unpublish_token.generate_unpublish_token(67372)
        t2 = unpublish_token.generate_unpublish_token(67372)
        self.assertEqual(t1, t2)

    def test_different_post_id_different_token(self):
        t1 = unpublish_token.generate_unpublish_token(67372)
        t2 = unpublish_token.generate_unpublish_token(67375)
        self.assertNotEqual(t1, t2)

    def test_string_int_post_id_same_token(self):
        t1 = unpublish_token.generate_unpublish_token(67372)
        t2 = unpublish_token.generate_unpublish_token("67372")
        self.assertEqual(t1, t2)

    def test_empty_post_id_returns_empty(self):
        self.assertEqual(unpublish_token.generate_unpublish_token(""), "")

    def test_verify_correct_token(self):
        t = unpublish_token.generate_unpublish_token(67372)
        self.assertTrue(unpublish_token.verify_unpublish_token(67372, t))

    def test_verify_wrong_token(self):
        wrong = "x" * 24
        self.assertFalse(unpublish_token.verify_unpublish_token(67372, wrong))

    def test_verify_token_for_different_post_id(self):
        t = unpublish_token.generate_unpublish_token(67372)
        self.assertFalse(unpublish_token.verify_unpublish_token(67375, t))

    def test_verify_empty_token(self):
        self.assertFalse(unpublish_token.verify_unpublish_token(67372, ""))

    def test_verify_empty_post_id(self):
        t = unpublish_token.generate_unpublish_token(67372)
        self.assertFalse(unpublish_token.verify_unpublish_token("", t))

    def test_env_secret_override(self):
        t1 = unpublish_token.generate_unpublish_token(67372)
        os.environ["UNPUBLISH_TOKEN_SECRET"] = "custom_secret_xxx"
        t2 = unpublish_token.generate_unpublish_token(67372)
        self.assertNotEqual(t1, t2)


if __name__ == "__main__":
    unittest.main()
