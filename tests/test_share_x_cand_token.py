"""tests for src/share_x_cand_token.py (437 Phase 8 / 2026-05-26).

x-post-mail-lane の候補ごと share-x button 用 HMAC token の test。
"""

from __future__ import annotations

import unittest

from src.share_x_cand_token import (
    generate_share_x_cand_token,
    verify_share_x_cand_token,
)


_NOW = 1_700_000_000
_KEY = "share_x_cand/20260526-120000/cand-01.png"


class ShareXCandTokenTests(unittest.TestCase):
    def test_generate_and_verify_roundtrip(self):
        token = generate_share_x_cand_token(_KEY, ttl_seconds=3600, now=_NOW)
        self.assertTrue(token)
        self.assertIn(".", token)
        self.assertTrue(
            verify_share_x_cand_token(_KEY, token, now=_NOW + 100)
        )

    def test_verify_wrong_blob_key_fails(self):
        token = generate_share_x_cand_token(_KEY, ttl_seconds=3600, now=_NOW)
        self.assertFalse(
            verify_share_x_cand_token(
                "share_x_cand/20260526-120000/cand-02.png", token, now=_NOW + 100
            )
        )

    def test_verify_expired_token_fails(self):
        token = generate_share_x_cand_token(_KEY, ttl_seconds=60, now=_NOW)
        self.assertFalse(
            verify_share_x_cand_token(_KEY, token, now=_NOW + 999_999)
        )

    def test_verify_tampered_hmac_fails(self):
        token = generate_share_x_cand_token(_KEY, ttl_seconds=3600, now=_NOW)
        expiry, _, _hmac = token.partition(".")
        bad = f"{expiry}.0000000000000000000000aa"
        self.assertFalse(verify_share_x_cand_token(_KEY, bad, now=_NOW + 100))

    def test_empty_blob_key_returns_empty_token(self):
        self.assertEqual(
            generate_share_x_cand_token("", ttl_seconds=3600, now=_NOW), ""
        )

    def test_zero_ttl_returns_empty_token(self):
        self.assertEqual(
            generate_share_x_cand_token(_KEY, ttl_seconds=0, now=_NOW), ""
        )

    def test_malformed_token_fails_verify(self):
        self.assertFalse(verify_share_x_cand_token(_KEY, "no-dot-here", now=_NOW))
        self.assertFalse(verify_share_x_cand_token(_KEY, ".only-after-dot", now=_NOW))
        self.assertFalse(verify_share_x_cand_token(_KEY, "abc.def", now=_NOW))


if __name__ == "__main__":
    unittest.main()
