from __future__ import annotations

import unittest

from src.instagram_source_registry import (
    SOURCE_ROLES,
    SOURCE_STATUSES,
    find_instagram_source,
    is_review_candidate,
    load_instagram_sources,
    normalize_instagram_handle,
)


class InstagramSourceRegistryTests(unittest.TestCase):
    def test_source_registry_loads_broad_giants_source_shelves(self):
        sources = load_instagram_sources()
        roles = {source.role for source in sources}
        statuses = {source.status for source in sources}

        self.assertGreaterEqual(len(sources), 45)
        self.assertTrue({"official", "media", "player", "development_player", "coach", "ob"}.issubset(roles))
        self.assertTrue({"confirmed", "candidate", "hold", "excluded"}.issubset(statuses))

    def test_role_and_status_constants_keep_reviewable_shelves_explicit(self):
        self.assertIn("candidate_player", SOURCE_ROLES)
        self.assertIn("former_player", SOURCE_ROLES)
        self.assertEqual(SOURCE_STATUSES, frozenset({"confirmed", "candidate", "hold", "excluded"}))

    def test_handle_normalization_accepts_profile_url_and_at_prefix(self):
        self.assertEqual(normalize_instagram_handle("https://www.instagram.com/sportshochi_giants/"), "sportshochi_giants")
        self.assertEqual(normalize_instagram_handle("@Hayato.Sakamoto6"), "hayato.sakamoto6")

    def test_lookup_finds_official_media_current_player_development_coach_and_ob(self):
        expected = {
            "yomiuri.giants": ("official", "confirmed"),
            "sportshochi_giants": ("media", "confirmed"),
            "hayato.sakamoto6": ("player", "confirmed"),
            "makoto5528": ("development_player", "candidate"),
            "sugi_toshi18": ("coach", "candidate"),
            "makihara17": ("ob", "candidate"),
        }

        for handle, (role, status) in expected.items():
            with self.subTest(handle=handle):
                source = find_instagram_source(handle)
                self.assertIsNotNone(source)
                self.assertEqual(source.role, role)
                self.assertEqual(source.status, status)

    def test_hold_and_excluded_sources_are_not_review_candidates(self):
        hold_source = find_instagram_source("kazuma.okamoto25")
        excluded_source = find_instagram_source("sample_non_giants_fan")

        self.assertIsNotNone(hold_source)
        self.assertIsNotNone(excluded_source)
        self.assertEqual(hold_source.status, "hold")
        self.assertEqual(excluded_source.status, "excluded")
        self.assertFalse(is_review_candidate(hold_source))
        self.assertFalse(is_review_candidate(excluded_source))

    def test_candidate_and_confirmed_sources_are_review_candidates(self):
        self.assertTrue(is_review_candidate(find_instagram_source("sportshochi_giants")))
        self.assertTrue(is_review_candidate(find_instagram_source("makoto5528")))

    def test_unknown_source_returns_none_instead_of_silent_confirming(self):
        self.assertIsNone(find_instagram_source("unknown_giants_like_account"))


if __name__ == "__main__":
    unittest.main()
