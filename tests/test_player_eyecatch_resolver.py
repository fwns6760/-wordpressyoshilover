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


if __name__ == "__main__":
    unittest.main()
