"""324-QA fan voice whitelist RSS source registration scaffolding tests.

Covers the additive scaffolding only (env flag helper + cache helpers). The
main fetch loop branch is exercised indirectly via the cache helper. Picker
integration (325-QA) lives behind ENABLE_FAN_VOICE_WHITELIST and is not yet
wired into any caller; tests here verify the helpers are reachable and that
the flag defaults OFF.
"""

import os
import unittest
from unittest import mock

from src import rss_fetcher


class FanVoiceWhitelistFlagTests(unittest.TestCase):
    def test_disabled_by_default_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_FAN_VOICE_WHITELIST", None)
            self.assertFalse(rss_fetcher.get_fan_voice_whitelist_enabled())

    def test_disabled_when_env_zero(self):
        with mock.patch.dict(os.environ, {"ENABLE_FAN_VOICE_WHITELIST": "0"}):
            self.assertFalse(rss_fetcher.get_fan_voice_whitelist_enabled())

    def test_enabled_when_env_one(self):
        with mock.patch.dict(os.environ, {"ENABLE_FAN_VOICE_WHITELIST": "1"}):
            self.assertTrue(rss_fetcher.get_fan_voice_whitelist_enabled())

    def test_enabled_when_env_true(self):
        with mock.patch.dict(os.environ, {"ENABLE_FAN_VOICE_WHITELIST": "true"}):
            self.assertTrue(rss_fetcher.get_fan_voice_whitelist_enabled())


class FanVoicePoolCacheTests(unittest.TestCase):
    def setUp(self):
        rss_fetcher._reset_fan_voice_pool_cache()

    def tearDown(self):
        rss_fetcher._reset_fan_voice_pool_cache()

    def test_empty_cache_returns_empty_list(self):
        self.assertEqual(rss_fetcher.get_fan_voice_pool_entries(), [])

    def test_reset_clears_cache(self):
        rss_fetcher._record_fan_voice_pool_entries(
            "test_source",
            [{"link": "https://x.com/u/status/1", "summary": "hi"}],
        )
        self.assertEqual(len(rss_fetcher.get_fan_voice_pool_entries()), 1)
        rss_fetcher._reset_fan_voice_pool_cache()
        self.assertEqual(rss_fetcher.get_fan_voice_pool_entries(), [])

    def test_record_normalizes_entry_fields(self):
        added = rss_fetcher._record_fan_voice_pool_entries(
            "巨人ファンA",
            [
                {
                    "link": "https://x.com/giants_fan_a/status/123",
                    "summary": "今日の打席良かった",
                    "published_parsed": None,
                }
            ],
        )
        self.assertEqual(added, 1)
        entries = rss_fetcher.get_fan_voice_pool_entries()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["source_name"], "巨人ファンA")
        self.assertEqual(entry["url"], "https://x.com/giants_fan_a/status/123")
        self.assertEqual(entry["text"], "今日の打席良かった")
        self.assertEqual(entry["handle"], "@giants_fan_a")

    def test_record_falls_back_to_description_or_title(self):
        added = rss_fetcher._record_fan_voice_pool_entries(
            "src",
            [
                {"link": "https://x.com/u/status/1", "description": "本文desc"},
                {"link": "https://x.com/u/status/2", "title": "本文title"},
            ],
        )
        self.assertEqual(added, 2)
        texts = [e["text"] for e in rss_fetcher.get_fan_voice_pool_entries()]
        self.assertIn("本文desc", texts)
        self.assertIn("本文title", texts)

    def test_record_dedupes_by_url(self):
        rss_fetcher._record_fan_voice_pool_entries(
            "src",
            [{"link": "https://x.com/u/status/1", "summary": "first"}],
        )
        added2 = rss_fetcher._record_fan_voice_pool_entries(
            "src",
            [{"link": "https://x.com/u/status/1", "summary": "duplicate"}],
        )
        self.assertEqual(added2, 0)
        self.assertEqual(len(rss_fetcher.get_fan_voice_pool_entries()), 1)

    def test_record_skips_empty_text(self):
        added = rss_fetcher._record_fan_voice_pool_entries(
            "src",
            [
                {"link": "https://x.com/u/status/1", "summary": ""},
                {"link": "https://x.com/u/status/2", "summary": "   "},
                {"link": "https://x.com/u/status/3", "summary": "ok"},
            ],
        )
        self.assertEqual(added, 1)

    def test_record_caps_at_limit(self):
        original_limit = rss_fetcher._FAN_VOICE_POOL_CACHE_LIMIT
        try:
            rss_fetcher._FAN_VOICE_POOL_CACHE_LIMIT = 3
            added = rss_fetcher._record_fan_voice_pool_entries(
                "src",
                [
                    {"link": f"https://x.com/u/status/{i}", "summary": f"t{i}"}
                    for i in range(10)
                ],
            )
            self.assertEqual(added, 3)
            self.assertEqual(len(rss_fetcher.get_fan_voice_pool_entries()), 3)
        finally:
            rss_fetcher._FAN_VOICE_POOL_CACHE_LIMIT = original_limit

    def test_get_returns_defensive_copy(self):
        rss_fetcher._record_fan_voice_pool_entries(
            "src",
            [{"link": "https://x.com/u/status/1", "summary": "ok"}],
        )
        view = rss_fetcher.get_fan_voice_pool_entries()
        view.clear()
        # cache itself untouched
        self.assertEqual(len(rss_fetcher.get_fan_voice_pool_entries()), 1)

    def test_record_empty_input_returns_zero(self):
        self.assertEqual(rss_fetcher._record_fan_voice_pool_entries("src", []), 0)
        self.assertEqual(rss_fetcher._record_fan_voice_pool_entries("src", None), 0)


if __name__ == "__main__":
    unittest.main()
