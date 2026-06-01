"""Tests for data_site_template_cluster (ticket 443/444 Phase 1.0)."""

from __future__ import annotations

import json
import re
import unittest

from src.data_site_template_cluster import (
    ClusterPlayerEntry,
    render_cluster_html,
    render_cluster_title,
    _build_hot_html,
)


class HotCardTests(unittest.TestCase):
    """460: 今日の注目カード (直近5HOT、 server-rendered)。"""

    def test_render_with_pillar_link(self) -> None:
        hot = {"batter": [("吉川尚輝", "OPS .950", 3, 144)],
               "pitcher": [("戸郷翔征", "防御率 1.20", 2, 60)]}
        html = _build_hot_html(hot)
        self.assertIn("直近5試合の注目選手", html)
        self.assertIn("吉川尚輝", html)
        self.assertIn("OPS .950", html)
        self.assertIn("/data/yoshikawa-naoki/", html)
        self.assertIn("防御率 1.20", html)

    def test_empty_safe(self) -> None:
        self.assertEqual(_build_hot_html({"batter": [], "pitcher": []}), "")
        self.assertEqual(_build_hot_html(None), "")


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

    def test_staff_table_separate_from_player_tables(self) -> None:
        """監督・コーチ は専用 staff 表に入り、 野手・投手 表には混入しない。"""
        players = self.players + [
            ClusterPlayerEntry(name="阿部慎之助", slug="abe-shinnosuke", position="監督",
                               jersey_number="83", role="manager"),
            ClusterPlayerEntry(name="内海哲也", slug="utsumi-tetsuya", position="投手コーチ",
                               jersey_number="77", role="coach"),
        ]
        html = render_cluster_html(players)
        self.assertIn("ys-cluster-staff-table", html)
        self.assertIn("監督・コーチ 一覧 (2 名)", html)
        # 軍別小見出し (内海=投手コーチ は position に二軍/三軍/巡回 無し → 一軍)
        self.assertIn("一軍 (2 名)", html)
        # staff は野手表 (内野手/外野手) に入らない: sample 3 名は内野2+外野1 のまま
        self.assertIn("内野手 一覧 (2 名", html)
        self.assertIn("外野手 一覧 (1 名", html)
        # 監督が先頭 (コーチより前)
        self.assertLess(html.find("阿部慎之助"), html.find("内海哲也"))

    def test_position_split_four_tables(self) -> None:
        """支配下が 投手/捕手/内野手/外野手 の登録区分別に分割される。"""
        players = [
            ClusterPlayerEntry(name="戸郷翔征", slug="togo-shosei", position="投手",
                               jersey_number="20", position_group="投手"),
            ClusterPlayerEntry(name="岸田行倫", slug="kishida-yukinori", position="捕手",
                               jersey_number="27", position_group="捕手"),
            ClusterPlayerEntry(name="吉川尚輝", slug="yoshikawa-naoki", position="内野手",
                               jersey_number="2", position_group="内野手"),
            ClusterPlayerEntry(name="丸佳浩", slug="maru-yoshihiro", position="外野手",
                               jersey_number="8", position_group="外野手"),
        ]
        html = render_cluster_html(players)
        self.assertIn("投手 一覧 (1 名", html)
        self.assertIn("捕手 一覧 (1 名", html)
        self.assertIn("内野手 一覧 (1 名", html)
        self.assertIn("外野手 一覧 (1 名", html)

    def test_ikusei_frame_listed_without_links(self) -> None:
        """育成枠は氏名+ポジションの一覧、 個別ページ link なし。"""
        html = render_cluster_html(self.players, [("中田歩夢", "内野手"), ("鈴木大和", "外野手")])
        self.assertIn("ys-cluster-ikusei-table", html)
        self.assertIn("育成選手 一覧 (2 名)", html)
        self.assertIn("中田歩夢", html)
        # 育成は個別ページ無し → /data/{slug}/ への link を作らない
        self.assertNotIn("中田歩夢</a>", html)

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
