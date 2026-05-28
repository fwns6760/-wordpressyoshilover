"""Tests for data_site_template_cluster (ticket 443/444 Phase 1.0)."""

from __future__ import annotations

import json
import re
import unittest

from src.data_site_template_cluster import (
    ClusterPlayerEntry,
    render_cluster_html,
    render_cluster_title,
)


class RenderClusterHtmlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.players = [
            ClusterPlayerEntry(name="吉川尚輝", slug="yoshikawa-naoki", position="内野手", jersey_number="2"),
            ClusterPlayerEntry(name="坂本勇人", slug="sakamoto-hayato", position="内野手", jersey_number="6"),
            ClusterPlayerEntry(name="丸佳浩", slug="maru-yoshihiro", position="外野手", jersey_number="8"),
        ]

    def test_html_contains_all_player_names(self) -> None:
        html = render_cluster_html(self.players)
        for p in self.players:
            self.assertIn(p.name, html)

    def test_html_links_to_each_pillar(self) -> None:
        html = render_cluster_html(self.players)
        for p in self.players:
            self.assertIn(f"/data/{p.slug}/", html)

    def test_player_count_displayed(self) -> None:
        html = render_cluster_html(self.players)
        self.assertIn("3 名", html)

    def test_jsonld_collection_page(self) -> None:
        html = render_cluster_html(self.players)
        matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        self.assertGreaterEqual(len(matches), 2)
        cp = next(json.loads(m) for m in matches if "CollectionPage" in m)
        self.assertEqual(cp["@type"], "CollectionPage")
        self.assertEqual(cp["url"], "https://yoshilover.com/data/")
        self.assertEqual(cp["mainEntity"]["@type"], "ItemList")
        self.assertEqual(cp["mainEntity"]["numberOfItems"], 3)

    def test_jsonld_item_list_has_3_sports_players(self) -> None:
        html = render_cluster_html(self.players)
        matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        cp = next(json.loads(m) for m in matches if "CollectionPage" in m)
        items = cp["mainEntity"]["itemListElement"]
        self.assertEqual(len(items), 3)
        for i, item in enumerate(items):
            self.assertEqual(item["position"], i + 1)
            self.assertEqual(item["item"]["@type"], "SportsPlayer")
            self.assertEqual(item["item"]["url"], f"https://yoshilover.com/data/{self.players[i].slug}/")

    def test_jsonld_breadcrumb_2_items(self) -> None:
        html = render_cluster_html(self.players)
        matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        breadcrumb = next(json.loads(m) for m in matches if "BreadcrumbList" in m)
        self.assertEqual(len(breadcrumb["itemListElement"]), 2)

    def test_empty_players_safe(self) -> None:
        html = render_cluster_html([])
        self.assertIn("準備中", html)

    def test_position_and_jersey_displayed(self) -> None:
        html = render_cluster_html(self.players)
        self.assertIn("内野手", html)
        self.assertIn("外野手", html)
        # jersey column shows raw number (背番号 col)
        self.assertIn(">2<", html)
        self.assertIn(">6<", html)
        self.assertIn(">8<", html)

    def test_table_sorted_by_jersey_number(self) -> None:
        """背番号順 sort: 2 → 6 → 8 (user 指示 2026-05-28 PM3)。"""
        # input は適当順、 output で 2/6/8 順を期待
        unsorted = [
            ClusterPlayerEntry(name="丸佳浩", slug="maru-yoshihiro", position="外野手", jersey_number="8"),
            ClusterPlayerEntry(name="吉川尚輝", slug="yoshikawa-naoki", position="内野手", jersey_number="2"),
            ClusterPlayerEntry(name="坂本勇人", slug="sakamoto-hayato", position="内野手", jersey_number="6"),
        ]
        html = render_cluster_html(unsorted)
        # 吉川 (2) は 坂本 (6) より前に出る
        pos_yoshikawa = html.find("吉川尚輝")
        pos_sakamoto = html.find("坂本勇人")
        pos_maru = html.find("丸佳浩")
        self.assertLess(pos_yoshikawa, pos_sakamoto)
        self.assertLess(pos_sakamoto, pos_maru)

    def test_stats_column_shows_dash_when_no_data(self) -> None:
        """has_stats=False の player は '-' 表示。"""
        html = render_cluster_html(self.players)  # all defaults has_stats=False
        # 試合 column に「-」 が含まれる
        self.assertIn(">-<", html)

    def test_stats_column_shows_values_when_data(self) -> None:
        """has_stats=True の player は数値表示。"""
        players = [
            ClusterPlayerEntry(
                name="吉川尚輝", slug="yoshikawa-naoki", position="内野手", jersey_number="2",
                season_games=20, season_hits=17, season_rbi=3, season_avg=0.224, has_stats=True,
            ),
        ]
        html = render_cluster_html(players)
        self.assertIn(">20<", html)  # 試合
        self.assertIn(">17<", html)  # 安打
        self.assertIn(".224", html)  # 打率


class RenderClusterTitleTests(unittest.TestCase):
    def test_title_format(self) -> None:
        title = render_cluster_title()
        self.assertIn("巨人選手データ", title)
        self.assertIn("ヨシラバー", title)


if __name__ == "__main__":
    unittest.main()
