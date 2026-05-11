from __future__ import annotations

import unittest

from src.youtube_ob_source_registry import (
    SOURCE_ROLES,
    SOURCE_STATUSES,
    find_youtube_ob_source,
    is_review_candidate,
    load_youtube_ob_sources,
    normalize_youtube_channel_id,
    normalize_youtube_video_url,
)


class YouTubeOBSourceRegistryTests(unittest.TestCase):
    def test_source_registry_loads_giants_ob_shelf_for_review(self):
        sources = load_youtube_ob_sources()
        names = {source.display_name for source in sources}
        roles = {source.role for source in sources}
        statuses = {source.status for source in sources}

        self.assertGreaterEqual(len(sources), 8)
        self.assertTrue({"official", "ob", "media"}.issubset(roles))
        self.assertTrue({"confirmed", "candidate", "excluded"}.issubset(statuses))
        self.assertIn("デーブ大久保チャンネル", names)
        self.assertIn("アスリートアカデミア 岡崎郁 official", names)
        self.assertIn("DAZNベースボール", names)

    def test_role_and_status_constants_keep_reviewable_shelves_explicit(self):
        self.assertIn("ob", SOURCE_ROLES)
        self.assertIn("broadcast", SOURCE_ROLES)
        self.assertEqual(SOURCE_STATUSES, frozenset({"confirmed", "candidate", "hold", "excluded"}))

    def test_channel_id_normalization_accepts_feed_and_channel_urls(self):
        channel_id = "UCKa1VlSq1WwdSQWv4JFdgxg"

        self.assertEqual(normalize_youtube_channel_id(channel_id), channel_id)
        self.assertEqual(normalize_youtube_channel_id(f"https://www.youtube.com/channel/{channel_id}/videos"), channel_id)
        self.assertEqual(
            normalize_youtube_channel_id(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"),
            channel_id,
        )

    def test_video_url_normalization_accepts_youtu_be_and_shorts(self):
        self.assertEqual(
            normalize_youtube_video_url("https://youtu.be/abc12345DEF?si=tracking"),
            "https://www.youtube.com/watch?v=abc12345DEF",
        )
        self.assertEqual(
            normalize_youtube_video_url("https://www.youtube.com/shorts/abc12345DEF"),
            "https://www.youtube.com/watch?v=abc12345DEF",
        )

    def test_lookup_finds_official_existing_and_new_ob_channels(self):
        expected = {
            "UCXxg0igSYUp0tqdd6luPEnQ": ("official", "confirmed"),
            "UCyeDNNizMGbVsn_8Ttc3FIw": ("media", "confirmed"),
            "UCKa1VlSq1WwdSQWv4JFdgxg": ("ob", "candidate"),
            "UCB-FcvdGhY5a69C7Csv4unA": ("ob", "candidate"),
            "UCU77bY7q28jGPYlDn089gfg": ("ob", "candidate"),
        }

        for channel_id, (role, status) in expected.items():
            with self.subTest(channel_id=channel_id):
                source = find_youtube_ob_source(channel_id)
                self.assertIsNotNone(source)
                self.assertEqual(source.role, role)
                self.assertEqual(source.status, status)

    def test_excluded_sources_are_not_review_candidates(self):
        excluded_source = find_youtube_ob_source("UC0000000000000000000000")

        self.assertIsNotNone(excluded_source)
        self.assertEqual(excluded_source.status, "excluded")
        self.assertFalse(is_review_candidate(excluded_source))

    def test_candidate_and_confirmed_sources_are_review_candidates(self):
        self.assertTrue(is_review_candidate(find_youtube_ob_source("UCXxg0igSYUp0tqdd6luPEnQ")))
        self.assertTrue(is_review_candidate(find_youtube_ob_source("UCKa1VlSq1WwdSQWv4JFdgxg")))

    def test_unknown_source_returns_none_instead_of_silent_confirming(self):
        self.assertIsNone(find_youtube_ob_source("UCunknownUnknownUnknown00"))


if __name__ == "__main__":
    unittest.main()
