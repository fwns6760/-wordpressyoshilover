"""tests for src/publish_button_token.py (379-OPS / GH #53)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.publish_button_token import (
    generate_publish_button_token,
    verify_publish_button_token,
)


class GenerateTests(unittest.TestCase):
    def test_returns_token_with_expiry_and_hmac(self):
        token = generate_publish_button_token(123, ttl_seconds=3600, now=1_000_000)
        expiry, _, hmac_part = token.partition(".")
        assert expiry == str(1_000_000 + 3600)
        assert len(hmac_part) == 24
        assert hmac_part.isalnum()

    def test_str_post_id_accepted(self):
        token_int = generate_publish_button_token(456, ttl_seconds=60, now=1)
        token_str = generate_publish_button_token("456", ttl_seconds=60, now=1)
        assert token_int == token_str

    def test_empty_post_id_returns_empty_string(self):
        assert generate_publish_button_token("", ttl_seconds=60) == ""
        assert generate_publish_button_token(None, ttl_seconds=60) == ""  # type: ignore[arg-type]

    def test_zero_ttl_returns_empty(self):
        assert generate_publish_button_token(1, ttl_seconds=0) == ""

    def test_negative_ttl_returns_empty(self):
        assert generate_publish_button_token(1, ttl_seconds=-1) == ""

    def test_different_post_ids_produce_different_tokens(self):
        t1 = generate_publish_button_token(1, ttl_seconds=60, now=1)
        t2 = generate_publish_button_token(2, ttl_seconds=60, now=1)
        assert t1 != t2

    def test_different_expiry_produces_different_token(self):
        t1 = generate_publish_button_token(1, ttl_seconds=60, now=1)
        t2 = generate_publish_button_token(1, ttl_seconds=120, now=1)
        assert t1 != t2

    def test_different_secret_produces_different_token(self):
        t1 = generate_publish_button_token(1, ttl_seconds=60, now=1)
        with patch.dict(os.environ, {"PUBLISH_BUTTON_TOKEN_SECRET": "alt"}, clear=False):
            t2 = generate_publish_button_token(1, ttl_seconds=60, now=1)
        assert t1 != t2


class VerifyTests(unittest.TestCase):
    def test_valid_token_passes(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token(100, token, now=1010) is True

    def test_str_post_id_matches_int(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token("100", token, now=1010) is True

    def test_expired_token_fails(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token(100, token, now=2000) is False

    def test_expiry_at_exact_boundary_fails(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token(100, token, now=1060) is False

    def test_wrong_post_id_fails(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token(101, token, now=1010) is False

    def test_tampered_hmac_fails(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        expiry, _, hmac_part = token.partition(".")
        tampered_hmac = "0" * len(hmac_part)
        assert verify_publish_button_token(100, f"{expiry}.{tampered_hmac}", now=1010) is False

    def test_tampered_expiry_fails(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        _, _, hmac_part = token.partition(".")
        future_expiry = 9_999_999_999
        # 改ざんした expiry に対する HMAC は元と違うので fail
        assert verify_publish_button_token(100, f"{future_expiry}.{hmac_part}", now=1010) is False

    def test_missing_dot_separator_fails(self):
        assert verify_publish_button_token(100, "no_separator_token") is False

    def test_empty_token_fails(self):
        assert verify_publish_button_token(100, "") is False

    def test_empty_post_id_fails(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token("", token, now=1010) is False

    def test_non_numeric_expiry_fails(self):
        assert verify_publish_button_token(100, "abc.0123456789abcdef01234567") is False

    def test_secret_change_invalidates_existing_token(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        with patch.dict(os.environ, {"PUBLISH_BUTTON_TOKEN_SECRET": "alt"}, clear=False):
            assert verify_publish_button_token(100, token, now=1010) is False

    def test_idempotent_verify(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token(100, token, now=1010) is True
        assert verify_publish_button_token(100, token, now=1020) is True
        assert verify_publish_button_token(100, token, now=1030) is True

    def test_whitespace_stripped_from_token(self):
        token = generate_publish_button_token(100, ttl_seconds=60, now=1000)
        assert verify_publish_button_token(100, f"  {token}  ", now=1010) is True


class BuildPublishButtonUrlTests(unittest.TestCase):
    def test_builds_url_with_post_id_and_token(self):
        from src.publish_button_token import build_publish_button_url
        url = build_publish_button_url(
            123,
            "https://yoshilover-fetcher-487178857517.asia-northeast1.run.app",
            ttl_seconds=3600,
            now=1_000_000,
        )
        assert url is not None
        assert url.startswith(
            "https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/publish-and-tweet"
        )
        assert "post_id=123" in url
        assert "token=" in url

    def test_returns_none_for_none_post_id(self):
        from src.publish_button_token import build_publish_button_url
        assert build_publish_button_url(None, "https://foo.example.com") is None

    def test_returns_none_for_invalid_post_id(self):
        from src.publish_button_token import build_publish_button_url
        assert build_publish_button_url("abc", "https://foo.example.com") is None
        assert build_publish_button_url(0, "https://foo.example.com") is None
        assert build_publish_button_url(-1, "https://foo.example.com") is None

    def test_returns_none_for_missing_base_url(self):
        from src.publish_button_token import build_publish_button_url
        assert build_publish_button_url(123, None) is None
        assert build_publish_button_url(123, "") is None
        assert build_publish_button_url(123, "   ") is None

    def test_strips_trailing_slash(self):
        from src.publish_button_token import build_publish_button_url
        url = build_publish_button_url(
            123, "https://foo.example.com/", ttl_seconds=60, now=1
        )
        assert url is not None
        assert url.startswith("https://foo.example.com/publish-and-tweet")
        assert "https://foo.example.com//publish-and-tweet" not in url

    def test_generated_url_token_round_trip_verify(self):
        from src.publish_button_token import (
            build_publish_button_url,
            verify_publish_button_token,
        )
        url = build_publish_button_url(
            123, "https://foo.example.com", ttl_seconds=3600, now=1_000_000
        )
        assert url is not None
        # URL の token 部分を取り出して verify pass
        token = url.split("token=")[-1]
        assert verify_publish_button_token(123, token, now=1_000_500) is True


if __name__ == "__main__":
    unittest.main()
