"""Regression tests for the 2026-05-12 eyecatch player priority + dedupe.

Two paths are added to rss_fetcher.py:

* ``_resolve_high_confidence_player_media_id(title, wp, logger)`` —
  returns the WP media id for the single 巨人 player named in the title
  (delegates to ``resolve_eyecatch_from_title`` with
  ``allow_existing_person_media=True`` so cache + remote /media lookup
  fires). Returns 0 when ``detect_person`` is None, when the cache /
  lookup returns no usable id, or when the
  ``EYECATCH_PLAYER_PRIORITY_DISABLED`` env kill switch is set.

* ``_recently_used_featured_media_ids(wp, window_seconds)`` — returns
  the set of ``featured_media`` ids that were attached to WP posts in
  the trailing ``window_seconds`` window. Network failure returns an
  empty set so the dedupe quietly falls through to the legacy path.

* ``_upload_featured_media_with_fallback`` gains a new ``recent_used``
  kwarg. When a candidate resolves to an existing WP media id that is
  in ``recent_used``, the helper logs ``featured_media_recent_dedupe``
  and continues with the next candidate. When every candidate is
  skipped this way the helper returns 0, deferring to the team
  fallback (Tokyo Dome).
"""
from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import MagicMock, patch

from src import rss_fetcher


class HighConfidencePlayerPathTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("EYECATCH_PLAYER_PRIORITY_DISABLED", None)

    @patch("src.rss_fetcher.resolve_eyecatch_from_title", create=True)
    @patch("src.rss_fetcher._detect_person_for_eyecatch_priority")
    def test_single_player_title_returns_player_media_id(
        self, mock_detect, mock_resolve
    ):
        mock_detect.return_value = "戸郷翔征"
        mock_resolve.return_value = 66521
        wp = MagicMock()
        wp.base_url = "https://example.com"
        wp.auth = ("u", "p")
        logger = logging.getLogger("rss_fetcher.test.priority")

        media_id = rss_fetcher._resolve_high_confidence_player_media_id(
            "【巨人】戸郷翔征、無失点投球",
            wp,
            logger,
        )
        self.assertEqual(media_id, 66521)

    @patch("src.rss_fetcher.resolve_eyecatch_from_title", create=True)
    @patch("src.rss_fetcher._detect_person_for_eyecatch_priority")
    def test_no_player_in_title_returns_zero(self, mock_detect, mock_resolve):
        mock_detect.return_value = None
        wp = MagicMock()
        logger = logging.getLogger("rss_fetcher.test.priority")

        media_id = rss_fetcher._resolve_high_confidence_player_media_id(
            "巨人 vs 広島 試合速報",
            wp,
            logger,
        )
        self.assertEqual(media_id, 0)
        mock_resolve.assert_not_called()

    @patch("src.rss_fetcher.resolve_eyecatch_from_title", create=True)
    @patch("src.rss_fetcher._detect_person_for_eyecatch_priority")
    def test_player_without_photo_returns_zero(self, mock_detect, mock_resolve):
        """detect_person returns a player but cache / WP /media find nothing."""
        mock_detect.return_value = "平山功太"
        mock_resolve.return_value = None
        wp = MagicMock()
        wp.base_url = "https://example.com"
        wp.auth = ("u", "p")
        logger = logging.getLogger("rss_fetcher.test.priority")

        media_id = rss_fetcher._resolve_high_confidence_player_media_id(
            "【巨人】平山功太、ダイビングキャッチ",
            wp,
            logger,
        )
        self.assertEqual(media_id, 0)

    @patch.dict(
        os.environ,
        {"EYECATCH_PLAYER_PRIORITY_DISABLED": "1"},
        clear=False,
    )
    @patch("src.rss_fetcher.resolve_eyecatch_from_title", create=True)
    @patch("src.rss_fetcher._detect_person_for_eyecatch_priority")
    def test_kill_switch_disables_player_priority(
        self, mock_detect, mock_resolve
    ):
        mock_detect.return_value = "戸郷翔征"
        mock_resolve.return_value = 66521
        wp = MagicMock()
        logger = logging.getLogger("rss_fetcher.test.priority")

        media_id = rss_fetcher._resolve_high_confidence_player_media_id(
            "【巨人】戸郷翔征、無失点投球",
            wp,
            logger,
        )
        self.assertEqual(media_id, 0)
        mock_resolve.assert_not_called()


class RecentMediaDedupeTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("EYECATCH_DEDUPE_RECENT_DISABLED", None)

    def test_helper_returns_recent_ids_set(self):
        wp = MagicMock()
        wp.base_url = "https://example.com"
        wp.list_recent_featured_media_ids = MagicMock(
            return_value=[66577, 66491, 65953, 0, 66577]
        )
        logger = logging.getLogger("rss_fetcher.test.dedupe")

        ids = rss_fetcher._recently_used_featured_media_ids(
            wp, window_seconds=3600, logger=logger
        )
        self.assertIn(66577, ids)
        self.assertIn(66491, ids)
        self.assertIn(65953, ids)
        self.assertNotIn(0, ids)

    def test_helper_returns_empty_on_failure(self):
        wp = MagicMock()
        wp.base_url = "https://example.com"
        wp.list_recent_featured_media_ids = MagicMock(
            side_effect=RuntimeError("network")
        )
        logger = logging.getLogger("rss_fetcher.test.dedupe")
        ids = rss_fetcher._recently_used_featured_media_ids(
            wp, window_seconds=3600, logger=logger
        )
        self.assertEqual(ids, set())

    @patch.dict(
        os.environ,
        {"EYECATCH_DEDUPE_RECENT_DISABLED": "1"},
        clear=False,
    )
    def test_helper_kill_switch_returns_empty(self):
        wp = MagicMock()
        wp.base_url = "https://example.com"
        wp.list_recent_featured_media_ids = MagicMock(
            return_value=[66577]
        )
        logger = logging.getLogger("rss_fetcher.test.dedupe")
        ids = rss_fetcher._recently_used_featured_media_ids(
            wp, window_seconds=3600, logger=logger
        )
        self.assertEqual(ids, set())
        wp.list_recent_featured_media_ids.assert_not_called()


class UploadFeaturedMediaWithFallbackDedupeTests(unittest.TestCase):
    def test_dedupe_skips_recent_media_and_returns_next(self):
        wp = MagicMock()
        wp.find_uploaded_media_id_for_url = MagicMock(
            side_effect=lambda url: {
                "https://hochi.news/img/a.jpg": 66577,
                "https://hochi.news/img/b.jpg": 66491,
            }.get(url, 0)
        )
        logger = logging.getLogger("rss_fetcher.test.dedupe2")

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            [
                "https://hochi.news/img/a.jpg",
                "https://hochi.news/img/b.jpg",
            ],
            "https://hochi.news/articles/test.html",
            logger,
            recent_used={66577},
        )
        self.assertEqual(media_id, 66491)

    def test_dedupe_returns_zero_when_all_candidates_recent(self):
        wp = MagicMock()
        wp.find_uploaded_media_id_for_url = MagicMock(
            side_effect=lambda url: {
                "https://hochi.news/img/a.jpg": 66577,
                "https://hochi.news/img/b.jpg": 66491,
            }.get(url, 0)
        )
        logger = logging.getLogger("rss_fetcher.test.dedupe3")

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            [
                "https://hochi.news/img/a.jpg",
                "https://hochi.news/img/b.jpg",
            ],
            "https://hochi.news/articles/test.html",
            logger,
            recent_used={66577, 66491},
        )
        self.assertEqual(media_id, 0)
        wp.upload_image_from_url.assert_not_called()

    def test_dedupe_empty_recent_set_is_no_op(self):
        wp = MagicMock()
        wp.find_uploaded_media_id_for_url = MagicMock(return_value=66577)
        logger = logging.getLogger("rss_fetcher.test.dedupe4")

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            ["https://hochi.news/img/a.jpg"],
            "https://hochi.news/articles/test.html",
            logger,
            recent_used=set(),
        )
        self.assertEqual(media_id, 66577)

    def test_dedupe_default_arg_unchanged_when_omitted(self):
        wp = MagicMock()
        wp.find_uploaded_media_id_for_url = MagicMock(return_value=66577)
        logger = logging.getLogger("rss_fetcher.test.dedupe5")

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            ["https://hochi.news/img/a.jpg"],
            "https://hochi.news/articles/test.html",
            logger,
        )
        self.assertEqual(media_id, 66577)


if __name__ == "__main__":
    unittest.main()
