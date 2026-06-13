import unittest
from urllib.parse import parse_qs, urlparse

from scripts.setup_yt_shorts_youtube_oauth import (
    YOUTUBE_SCOPE,
    build_authorization_url,
    parse_args,
)


class SetupYtShortsYoutubeOauthTests(unittest.TestCase):
    def test_build_authorization_url_requests_offline_youtube_scope(self):
        url = build_authorization_url(
            "client-id",
            "http://127.0.0.1:8765/callback",
            "state-token",
        )

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "accounts.google.com")
        self.assertEqual(qs["client_id"], ["client-id"])
        self.assertEqual(qs["redirect_uri"], ["http://127.0.0.1:8765/callback"])
        self.assertEqual(qs["scope"], [YOUTUBE_SCOPE])
        self.assertEqual(qs["access_type"], ["offline"])
        self.assertEqual(qs["prompt"], ["consent"])
        self.assertEqual(qs["state"], ["state-token"])

    def test_parse_args_defaults_to_baseballsite(self):
        args = parse_args([])

        self.assertEqual(args.project, "baseballsite")
        self.assertEqual(args.client_id_secret_name, "yt-shorts-youtube-client-id")
        self.assertEqual(args.client_secret_secret_name, "yt-shorts-youtube-client-secret")
        self.assertEqual(args.refresh_token_secret_name, "yt-shorts-youtube-refresh-token")
        self.assertEqual(args.approval_token_secret_name, "yt-shorts-approval-token-secret")


if __name__ == "__main__":
    unittest.main()
