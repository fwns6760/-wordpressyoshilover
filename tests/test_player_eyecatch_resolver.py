"""Tests for src/player_eyecatch_resolver.py."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src import player_eyecatch_resolver as per


class DetectPersonTests(unittest.TestCase):
    def test_full_name_match(self):
        self.assertEqual(per.detect_person("巨人・吉川尚輝、前例なき復帰！"), "吉川尚輝")
        self.assertEqual(per.detect_person("田中将大、歴代2位タイの203勝"), "田中将大")

    def test_alias_match(self):
        self.assertEqual(per.detect_person("巨人・阿部監督、集中して臨むだけ"), "阿部慎之助")
        self.assertEqual(per.detect_person("巨人・大勢、真っ直ぐで押し切れた"), "翁田大勢")

    def test_full_width_space_normalized(self):
        # 全角スペース入りの hochi-style title
        self.assertEqual(per.detect_person("巨人・石塚 裕惺、今季打撃成績"), "石塚裕惺")

    def test_returns_none_for_non_player_titles(self):
        for t in (
            "2026年5月7日の予告先発が発表される！！！",
            "セ・リーグ 試合結果",
            "【公示】2026年5月7日のプロ野球公示",
            "",
        ):
            with self.subTest(t=t):
                self.assertIsNone(per.detect_person(t))


class CacheRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.cache_path = Path(self.tmpdir.name) / "map.json"
        os.environ[per._CACHE_PATH_ENV] = str(self.cache_path)
        self.addCleanup(self.tmpdir.cleanup)
        self.addCleanup(lambda: os.environ.pop(per._CACHE_PATH_ENV, None))

    def test_resolve_uses_cache_hit_without_remote(self):
        self.cache_path.write_text(
            json.dumps({"吉川尚輝": {"id": 50815, "title": "x"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        with patch.object(per, "_media_search") as mock_search:
            media_id = per.resolve_eyecatch_from_title(
                "巨人・吉川尚輝、3安打",
                wp_url="https://example.com",
                auth=("u", "p"),
            )
        self.assertEqual(media_id, 50815)
        mock_search.assert_not_called()

    def test_resolve_caches_negative_result_then_falls_back(self):
        with patch.object(per, "_media_search", return_value=None) as mock_search:
            first = per.resolve_eyecatch_from_title(
                "巨人・小濱佑斗、最高のヒット",
                wp_url="https://example.com",
                auth=("u", "p"),
            )
            second = per.resolve_eyecatch_from_title(
                "巨人・小濱佑斗、別記事",
                wp_url="https://example.com",
                auth=("u", "p"),
            )
        # Person detected but no per-person image → team fallback fires.
        self.assertEqual(first, per._TEAM_FALLBACK_MEDIA_ID_DEFAULT)
        self.assertEqual(second, per._TEAM_FALLBACK_MEDIA_ID_DEFAULT)
        # Negative cache → media_search only called once
        self.assertEqual(mock_search.call_count, 1)
        cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertIn("小濱佑斗", cached)
        self.assertIsNone(cached["小濱佑斗"])

    def test_resolve_persists_positive_lookup(self):
        with patch.object(
            per, "_media_search",
            return_value={"id": 99999, "title": "新規 player"}
        ):
            media_id = per.resolve_eyecatch_from_title(
                "巨人・松本剛、3番中堅",
                wp_url="https://example.com",
                auth=("u", "p"),
            )
        self.assertEqual(media_id, 99999)
        cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(cached["松本剛"]["id"], 99999)

    def test_remote_disabled_falls_back_to_team_default(self):
        # Empty cache, allow_remote_lookup=False → no network call,
        # but team fallback still applies.
        with patch.object(per, "_media_search") as mock_search:
            media_id = per.resolve_eyecatch_from_title(
                "巨人・松本剛、3番中堅",
                allow_remote_lookup=False,
            )
        self.assertEqual(media_id, per._TEAM_FALLBACK_MEDIA_ID_DEFAULT)
        mock_search.assert_not_called()

    def test_no_person_detected_falls_back_to_team_default(self):
        media_id = per.resolve_eyecatch_from_title(
            "2026年5月7日の予告先発が発表される",
            wp_url="https://example.com",
            auth=("u", "p"),
        )
        self.assertEqual(media_id, per._TEAM_FALLBACK_MEDIA_ID_DEFAULT)

    def test_team_fallback_disabled_returns_none(self):
        # Caller explicitly opts out of the generic fallback.
        media_id = per.resolve_eyecatch_from_title(
            "2026年5月7日の予告先発が発表される",
            wp_url="https://example.com",
            auth=("u", "p"),
            use_team_fallback=False,
        )
        self.assertIsNone(media_id)

    def test_team_fallback_env_override(self):
        os.environ[per._TEAM_FALLBACK_MEDIA_ID_ENV] = "12345"
        self.addCleanup(lambda: os.environ.pop(per._TEAM_FALLBACK_MEDIA_ID_ENV, None))
        media_id = per.resolve_eyecatch_from_title(
            "2026年5月7日の予告先発が発表される",
            allow_remote_lookup=False,
        )
        self.assertEqual(media_id, 12345)

    def test_team_fallback_disabled_via_env_zero(self):
        os.environ[per._TEAM_FALLBACK_MEDIA_ID_ENV] = "0"
        self.addCleanup(lambda: os.environ.pop(per._TEAM_FALLBACK_MEDIA_ID_ENV, None))
        media_id = per.resolve_eyecatch_from_title(
            "2026年5月7日の予告先発が発表される",
            allow_remote_lookup=False,
        )
        self.assertIsNone(media_id)

    def test_allow_existing_person_media_false_uses_team_fallback_even_on_cache_hit(self):
        self.cache_path.write_text(
            json.dumps({"吉川尚輝": {"id": 50815, "title": "x"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        media_id = per.resolve_eyecatch_from_title(
            "巨人・吉川尚輝、3安打",
            allow_remote_lookup=False,
            allow_existing_person_media=False,
            allow_diversified_pool=False,
        )
        self.assertEqual(media_id, per._TEAM_FALLBACK_MEDIA_ID_DEFAULT)


class DiversifiedPoolFallbackTests(unittest.TestCase):
    """Tests for the title-hash-keyed player pool fallback (RELIABILITY-
    2026-05-08-H continuation: when per-person resolution misses, pick
    another known player's image instead of returning fm=0)."""

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.cache_path = Path(self.tmpdir.name) / "map.json"
        os.environ[per._CACHE_PATH_ENV] = str(self.cache_path)
        self.addCleanup(self.tmpdir.cleanup)
        self.addCleanup(lambda: os.environ.pop(per._CACHE_PATH_ENV, None))
        self.addCleanup(lambda: os.environ.pop(per._POOL_FALLBACK_DISABLED_ENV, None))
        self.cache_path.write_text(
            json.dumps(
                {
                    "吉川尚輝":   {"id": 50815, "title": "x"},
                    "大城卓三":   {"id": 44424, "title": "x"},
                    "田中将大":   {"id": 33574, "title": "x"},
                    "翁田大勢":   {"id": 31157, "title": "x"},
                    "阿部慎之助": {"id": 36062, "title": "x"},
                    "三塚琉生":   None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_no_person_detected_uses_diversified_pool(self):
        # Title has no detectable player → diversified fallback fires
        # and picks one of the 5 cached hits (negative entries skipped).
        media_id = per.resolve_eyecatch_from_title(
            "バンテリンドーム 本日の審判団",
            allow_remote_lookup=False,
        )
        self.assertIn(media_id, {50815, 44424, 33574, 31157, 36062})

    def test_diversified_pool_is_deterministic_per_title(self):
        title = "あす5/9の予告先発 中日 大野雄大 巨人田中将大"
        # detect_person hits 田中将大 → per-person path returns 33574.
        # Use a title that has no detectable player to exercise the pool.
        no_person_title = "バンテリンドーム 本日の審判団 球審 山口"
        first = per.resolve_eyecatch_from_title(
            no_person_title, allow_remote_lookup=False,
        )
        second = per.resolve_eyecatch_from_title(
            no_person_title, allow_remote_lookup=False,
        )
        self.assertEqual(first, second)
        self.assertIn(first, {50815, 44424, 33574, 31157, 36062})

    def test_different_titles_can_get_different_images(self):
        # 50 distinct titles → distribution should hit at least 2 different
        # players from the 5-entry pool. (Exact distribution depends on
        # md5(title) but with 50 inputs collisions are statistically
        # vanishing.)
        results = set()
        for i in range(50):
            mid = per.resolve_eyecatch_from_title(
                f"審判団 第{i}試合 ベンチ入り 控え選手",
                allow_remote_lookup=False,
            )
            results.add(mid)
        self.assertGreater(len(results), 1)

    def test_pool_fallback_disabled_falls_through_to_team_default(self):
        os.environ[per._POOL_FALLBACK_DISABLED_ENV] = "1"
        media_id = per.resolve_eyecatch_from_title(
            "バンテリンドーム 本日の審判団",
            allow_remote_lookup=False,
        )
        self.assertEqual(media_id, per._TEAM_FALLBACK_MEDIA_ID_DEFAULT)

    def test_pool_fallback_disabled_team_env_still_honored(self):
        os.environ[per._POOL_FALLBACK_DISABLED_ENV] = "1"
        os.environ[per._TEAM_FALLBACK_MEDIA_ID_ENV] = "999"
        self.addCleanup(lambda: os.environ.pop(per._TEAM_FALLBACK_MEDIA_ID_ENV, None))
        media_id = per.resolve_eyecatch_from_title(
            "バンテリンドーム 本日の審判団",
            allow_remote_lookup=False,
        )
        self.assertEqual(media_id, 999)

    def test_use_team_fallback_false_skips_diversified_pool(self):
        # Caller explicitly opts out — diversified pool must also be
        # skipped (manual-intake path: user picks the eyecatch).
        media_id = per.resolve_eyecatch_from_title(
            "バンテリンドーム 本日の審判団",
            allow_remote_lookup=False,
            use_team_fallback=False,
        )
        self.assertIsNone(media_id)

    def test_per_person_hit_takes_priority_over_diversified_pool(self):
        # Title contains 吉川尚輝 → per-person path returns 50815 directly,
        # diversified pool never runs.
        media_id = per.resolve_eyecatch_from_title(
            "巨人・吉川尚輝、3安打",
            allow_remote_lookup=False,
        )
        self.assertEqual(media_id, 50815)

    def test_negative_cache_entry_falls_through_to_diversified_pool(self):
        # 三塚琉生 is detected but cached as None (no per-person image).
        # With diversified pool enabled, returns one of the 5 hits
        # rather than None.
        media_id = per.resolve_eyecatch_from_title(
            "巨人・三塚琉生、ファームで好投",
            allow_remote_lookup=False,
        )
        self.assertIn(media_id, {50815, 44424, 33574, 31157, 36062})

    def test_empty_cache_diversified_pool_returns_none(self):
        # Override cache with no positive hits.
        self.cache_path.write_text("{}", encoding="utf-8")
        media_id = per.resolve_eyecatch_from_title(
            "バンテリンドーム 本日の審判団",
            allow_remote_lookup=False,
        )
        self.assertEqual(media_id, per._TEAM_FALLBACK_MEDIA_ID_DEFAULT)


if __name__ == "__main__":
    unittest.main()
