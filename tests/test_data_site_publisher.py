"""Tests for data_site_publisher (ticket 444 Phase 1.0).

WP REST 呼び出しは mock、 template render の組み合わせと dry-run path のみ。
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from src.data_site_publisher import _build_pillar_info, publish_phase1
from src.data_site_query import RosterPlayer


class BuildPillarInfoTests(unittest.TestCase):
    @mock.patch("src.data_site_publisher.fetch_player_npb_ranks", return_value=[])
    @mock.patch("src.data_site_publisher.find_player_featured_media_id", return_value=44424)
    @mock.patch("src.data_site_publisher.find_player_featured_image_url", return_value="https://yoshilover.com/img/sample.jpg")
    @mock.patch("src.data_site_publisher.fetch_related_topic_links", return_value=[("https://yoshilover.com/73041/", "title1")])
    @mock.patch("src.data_site_publisher.load_roster_player")
    def test_build_pillar_info_basic(self, m_roster, m_topic, m_img, m_media, m_ranks):
        m_roster.return_value = RosterPlayer(
            name="坂本勇人", position="内野手", jersey_number="6", role="player", aliases=["坂本勇人"]
        )
        info = _build_pillar_info("坂本勇人")
        self.assertIsNotNone(info)
        self.assertEqual(info.name, "坂本勇人")
        self.assertEqual(info.slug, "sakamoto-hayato")
        self.assertEqual(info.position, "内野手")
        self.assertEqual(info.jersey_number, "6")
        self.assertEqual(info.featured_image_url, "https://yoshilover.com/img/sample.jpg")
        # SNS 共有 og:image 用に featured_media_id が info に乗ること
        self.assertEqual(info.featured_media_id, 44424)
        self.assertEqual(len(info.related_topic_links), 1)

    @mock.patch("src.data_site_publisher.load_roster_player", return_value=None)
    def test_build_pillar_info_no_roster(self, m_roster):
        self.assertIsNone(_build_pillar_info("存在しない選手"))


class PublishPhase1DryRunTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {"DATA_SITE_DRY_RUN": "1"}, clear=False)
    @mock.patch("src.data_site_publisher.fetch_player_npb_ranks", return_value=[])
    @mock.patch("src.data_site_publisher.find_player_featured_media_id", return_value=None)
    @mock.patch("src.data_site_publisher.find_player_featured_image_url", return_value="")
    @mock.patch("src.data_site_publisher.fetch_related_topic_links", return_value=[])
    @mock.patch("src.data_site_publisher.load_ob_names", return_value=[])
    @mock.patch("src.data_site_publisher.load_roster_player")
    @mock.patch("src.data_site_publisher.load_data_site_target_names", return_value=["吉川尚輝", "坂本勇人", "丸佳浩"])
    def test_dry_run_returns_ok(self, m_names, m_roster, m_ob, m_topic, m_img, m_media, m_ranks):
        def roster_side(name):
            return RosterPlayer(
                name=name,
                position="内野手" if name in {"吉川尚輝", "坂本勇人"} else "外野手",
                jersey_number={"吉川尚輝": "2", "坂本勇人": "6", "丸佳浩": "8"}[name],
                role="player",
                aliases=[name],
            )
        m_roster.side_effect = roster_side

        summary = publish_phase1()
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["pillar_count"], 3)
        self.assertEqual(summary["cluster"]["action"], "skipped")
        slugs = [p["slug"] for p in summary["pillars"]]
        self.assertEqual(slugs, ["yoshikawa-naoki", "sakamoto-hayato", "maru-yoshihiro"])

    @mock.patch.dict(os.environ, {"DATA_SITE_DRY_RUN": "1"}, clear=False)
    @mock.patch("src.data_site_publisher.load_data_site_target_names", return_value=[])
    def test_no_target_players_aborts(self, m_names):
        summary = publish_phase1()
        self.assertEqual(summary["status"], "abort")
        self.assertEqual(summary["reason"], "no_target_players")


if __name__ == "__main__":
    unittest.main()
