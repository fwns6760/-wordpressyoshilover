"""Tests for data_site_publisher (ticket 444 Phase 1.0).

WP REST 呼び出しは mock、 template render の組み合わせと dry-run path のみ。
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from src.data_site_publisher import (
    _build_notable_data,
    _build_pillar_info,
    _find_page_id_by_slug,
    _remove_notable_data_section,
    _replace_legacy_notable_data_links,
    publish_notable_data_only,
    publish_phase1,
    retire_legacy_notable_page,
)
from src.data_site_query import RosterPlayer
from src.data_site_template_cluster import ClusterPlayerEntry


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


class NotableDataOnlyTests(unittest.TestCase):
    @mock.patch.dict(
        os.environ,
        {"WP_URL": "https://example.test", "WP_USER": "user", "WP_APP_PASSWORD": "pass"},
        clear=False,
    )
    @mock.patch("src.data_site_publisher.requests.get")
    def test_find_page_id_by_slug_checks_any_status_to_avoid_slug_2(self, m_get):
        response = mock.Mock(ok=True)
        response.json.return_value = [
            {"id": 86549, "slug": "notable", "parent": 73526, "status": "draft"}
        ]
        m_get.return_value = response

        page_id = _find_page_id_by_slug("notable", parent=73526)

        self.assertEqual(page_id, 86549)
        params = m_get.call_args.kwargs["params"]
        self.assertEqual(params["slug"], "notable")
        self.assertEqual(params["status"], "any")
        self.assertEqual(params["context"], "edit")

    def test_remove_legacy_notable_data_section_from_player_hub(self):
        original = (
            '<section class="ys-cluster-intro">intro</section>'
            '<section id="ys-notable-data"><p>old</p></section>'
            '<section class="ys-cluster-search">search</section>'
        )
        updated = _remove_notable_data_section(original)
        self.assertNotIn("<p>old</p>", updated)
        self.assertNotIn('id="ys-notable-data"', updated)
        self.assertIn('class="ys-cluster-intro"', updated)
        self.assertIn('class="ys-cluster-search"', updated)

    def test_replace_legacy_notable_data_links(self):
        original = (
            '<a href="/data/notable" style="color:#e25400;">📈 驚き・注目選手</a>'
            '<a href="/data#ys-notable-data">注目データ</a>'
            '<a href="#ys-notable-data">注目データ</a>'
        )
        updated = _replace_legacy_notable_data_links(original)
        self.assertNotIn("#ys-notable-data", updated)
        self.assertNotIn("驚き・注目選手", updated)
        self.assertEqual(updated.count('/data/notable'), 3)
        self.assertIn("注目データ", updated)

    @mock.patch("src.data_site_publisher.fetch_npb_cl_standings", return_value=[])
    @mock.patch("src.data_site_publisher.fetch_team_leaders", return_value={})
    @mock.patch("src.data_site_publisher.fetch_surprise_stats", return_value=[])
    @mock.patch("src.data_site_publisher.fetch_contribution_streak")
    @mock.patch("src.data_site_publisher.fetch_hit_streak")
    @mock.patch("src.data_site_publisher.fetch_player_latest_game_date")
    @mock.patch("src.data_site_publisher.fetch_latest_giants_game_date", return_value="2026-06-07")
    def test_build_notable_data_uses_latest_game_date(
        self, m_latest, m_player_latest, m_hit, m_contrib, m_surprise, m_leaders, m_standings
    ):
        m_player_latest.side_effect = lambda name, table="batting_logs": {
            "吉川尚輝": "2026-06-07",
            "平山功太": "2026-05-30",
        }.get(name, "")
        m_hit.side_effect = [
            mock.Mock(active=6, season_max=6),
        ]
        m_contrib.side_effect = [
            mock.Mock(active=2, season_max=3),
        ]
        entries = [
            ClusterPlayerEntry(
                name="吉川尚輝", slug="yoshikawa-naoki", position="内野手",
                jersey_number="2", position_group="内野手",
            ),
            ClusterPlayerEntry(
                name="平山功太", slug="hirayama-kota", position="外野手",
                jersey_number="002", position_group="外野手",
            ),
        ]
        data = _build_notable_data(entries)
        self.assertEqual(data["as_of"], "2026-06-07")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["player"], "吉川尚輝")
        self.assertEqual(data["items"][0]["note"], "今季最長6試合")
        self.assertEqual(data["items"][0]["category"], "streak")
        self.assertNotIn("平山功太", str(data))

    @mock.patch("src.data_site_publisher._update_page_content")
    @mock.patch("src.data_site_publisher._get_page_for_edit_by_slug")
    @mock.patch("src.data_site_publisher._build_notable_data_from_targets")
    @mock.patch("src.data_site_publisher._upsert_page")
    def test_publish_notable_data_only_upserts_notable_page_only(
        self, m_upsert, m_data, m_page, m_update
    ):
        m_data.return_value = {"as_of": "2026-06-07", "items": []}
        m_page.return_value = {
            "id": 73526,
            "content": {
                "raw": (
                    '<a href="/data#ys-notable-data">驚き・注目選手</a>'
                    '<section id="ys-notable-data"><p>old</p></section><p>keep</p>'
                )
            },
        }
        m_upsert.return_value = mock.Mock(action="updated", page_id=81234)
        m_update.return_value = mock.Mock(action="updated", page_id=73526)
        summary = publish_notable_data_only()
        self.assertEqual(summary["mode"], "notable_data_only")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["notable_page_id"], 81234)
        m_upsert.assert_called_once()
        self.assertEqual(m_upsert.call_args.kwargs["slug"], "notable")
        self.assertEqual(m_upsert.call_args.kwargs["parent"], 73526)
        m_update.assert_called_once()
        sent_content = m_update.call_args.args[1]
        self.assertIn("/data/notable", sent_content)
        self.assertNotIn("#ys-notable-data", sent_content)
        self.assertNotIn('id="ys-notable-data"', sent_content)
        self.assertNotIn("驚き・注目選手", sent_content)

    @mock.patch("src.data_site_publisher._get_page_for_edit_by_slug")
    @mock.patch("src.data_site_publisher._build_notable_data_from_targets")
    def test_publish_notable_data_only_aborts_without_game_date(self, m_data, m_page):
        m_data.return_value = {"as_of": "", "items": []}
        summary = publish_notable_data_only()
        self.assertEqual(summary["status"], "abort")
        self.assertEqual(summary["reason"], "latest_game_date_unavailable")
        m_page.assert_not_called()

    @mock.patch("src.data_site_publisher._update_page_status")
    @mock.patch("src.data_site_publisher._get_page_for_edit_by_slug")
    @mock.patch("src.data_site_publisher._find_page_id_by_slug", return_value=73526)
    def test_retire_legacy_notable_page_is_noop_now_that_page_is_canonical(self, m_find, m_page, m_update):
        summary = retire_legacy_notable_page()
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["mode"], "retire_legacy_notable")
        self.assertEqual(summary["action"], "canonical_page_kept")
        m_find.assert_not_called()
        m_page.assert_not_called()
        m_update.assert_not_called()

    @mock.patch("src.data_site_publisher._update_page_status")
    @mock.patch("src.data_site_publisher._get_page_for_edit_by_slug")
    @mock.patch("src.data_site_publisher._find_page_id_by_slug", return_value=73526)
    def test_retire_legacy_notable_page_never_drafts_page(self, m_find, m_page, m_update):
        summary = retire_legacy_notable_page()
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["action"], "canonical_page_kept")
        m_find.assert_not_called()
        m_page.assert_not_called()
        m_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class ThinPillarNoindexTests(unittest.TestCase):
    """2026-07-02 SEO: 成績ゼロ OB のみ thin=noindex、データが 1 つでもあれば index。"""

    def _info(self, **kw):
        from src.data_site_template_pillar import PillarPlayerInfo
        base = dict(name="テスト選手", slug="test-player", position="", jersey_number="")
        base.update(kw)
        return PillarPlayerInfo(**base)

    def test_ob_without_any_stats_is_thin(self):
        from src.data_site_publisher import is_thin_pillar
        info = self._info(role="ob", ob_profile={"display_name": "テスト選手"})
        self.assertTrue(is_thin_pillar(info))

    def test_ob_with_yearly_career_not_thin(self):
        from src.data_site_publisher import is_thin_pillar
        info = self._info(role="ob", ob_profile={}, npb_career={"batting": {"rows": [1]}})
        self.assertFalse(is_thin_pillar(info))

    def test_ob_with_career_totals_not_thin(self):
        from src.data_site_publisher import is_thin_pillar
        info = self._info(role="ob", ob_profile={"npb": {"games": 1000}})
        self.assertFalse(is_thin_pillar(info))

    def test_active_player_never_thin(self):
        from src.data_site_publisher import is_thin_pillar
        info = self._info(role="player")
        self.assertFalse(is_thin_pillar(info))


class IndexNowTests(unittest.TestCase):
    def test_payload_dedupes_and_filters(self):
        from src.data_site_publisher import _indexnow_payload, _INDEXNOW_KEY
        p = _indexnow_payload([
            "https://yoshilover.com/data/a",
            "https://yoshilover.com/data/a",
            "/data/relative-skip",
            "https://yoshilover.com/data/b",
        ])
        self.assertEqual(p["urlList"], ["https://yoshilover.com/data/a", "https://yoshilover.com/data/b"])
        self.assertEqual(p["host"], "yoshilover.com")
        self.assertEqual(p["keyLocation"], f"https://yoshilover.com/{_INDEXNOW_KEY}.txt")

    def test_payload_empty_returns_none(self):
        from src.data_site_publisher import _indexnow_payload
        self.assertIsNone(_indexnow_payload([]))

    def test_plugin_serves_same_key(self):
        # publisher と 063 plugin の key 不一致は IndexNow 全滅になるため静的同期 check
        from pathlib import Path
        from src.data_site_publisher import _INDEXNOW_KEY
        php = (Path(__file__).resolve().parents[1] / "src" / "yoshilover-063-frontend.php").read_text(encoding="utf-8")
        assert f"define( 'YOSHILOVER_063_INDEXNOW_KEY', '{_INDEXNOW_KEY}' );" in php
        assert "yoshi_noindex" in php
