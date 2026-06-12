"""Tests for data_site_template_cluster (ticket 443/444 Phase 1.0)."""

from __future__ import annotations

import json
import re
import unittest

from src.data_site_template_cluster import (
    ClusterPlayerEntry,
    render_cluster_html,
    render_notable_data_page_html,
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
        self.assertIn("/data/yoshikawa-naoki", html)
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
            self.assertIn(f"/data/{p.slug}", html)

    def test_intro_links_to_farm_cluster(self) -> None:
        html = render_cluster_html(self.players)
        self.assertIn("/data/farm", html)
        self.assertIn("2軍ファーム", html)

    def test_intro_links_to_jersey_number_cluster(self) -> None:
        html = render_cluster_html(self.players)
        self.assertIn("/data/jersey-numbers", html)
        self.assertIn("歴代背番号", html)

    def test_intro_links_to_record_room_and_notable_page(self) -> None:
        html = render_cluster_html(self.players)
        self.assertIn("/data/notable", html)
        self.assertIn("注目データ", html)
        self.assertIn("/data/batting-ranking", html)
        self.assertIn("打撃ランキング", html)
        self.assertIn("/data/pitching-ranking", html)
        self.assertIn("投手ランキング", html)
        self.assertNotIn("/data/ranking", html)
        self.assertIn("/data/record", html)
        self.assertIn("記録室", html)
        self.assertNotIn("href=\"#ys-notable-data\"", html)
        self.assertNotIn("驚き・注目選手", html)

    def test_cluster_does_not_render_notable_data_content(self) -> None:
        notable = {
            "as_of": "2026-06-07",
            "items": [
                {
                    "player": "吉川尚輝",
                    "slug": "yoshikawa-naoki",
                    "label": "連続試合安打",
                    "value": "6試合",
                    "note": "現在進行中。",
                }
            ]
        }
        html = render_cluster_html(self.players, notable_data=notable)
        self.assertIn("/data/notable", html)
        self.assertNotIn('id="ys-notable-data"', html)
        self.assertNotIn("注目データ一覧を見る", html)
        self.assertNotIn("基準日: 2026-06-07 試合終了時点", html)
        self.assertNotIn("現在 1 件を掲載中", html)
        self.assertNotIn("連続試合安打", html)
        self.assertNotIn("6試合", html)

    def test_notable_data_page_shows_whose_record_it_is(self) -> None:
        notable = {
            "as_of": "2026-06-07",
            "items": [
                {
                    "player": "吉川尚輝",
                    "slug": "yoshikawa-naoki",
                    "label": "連続試合安打",
                    "value": "6試合",
                    "note": "現在進行中。",
                }
            ],
            "standings": [
                {"rank": 1, "team": "巨人", "g": "60", "w": "35", "l": "23",
                 "t": "2", "pct": ".603", "gb": "-", "is_giants": True},
            ],
            "leaders": {
                "本塁打": [
                    {"player": "岡本和真", "display": "15本", "slug": "okamoto-kazuma"},
                    {"player": "吉川尚輝", "display": "8本", "slug": "yoshikawa-naoki"},
                ],
            },
        }
        html = render_notable_data_page_html(notable)
        self.assertIn("巨人 注目データ", html)
        self.assertIn("連続試合安打", html)
        self.assertIn("吉川尚輝", html)
        self.assertIn("6試合", html)
        self.assertIn("継続中の連続記録", html)
        self.assertIn("/data/yoshikawa-naoki", html)
        self.assertIn("基準日 2026-06-07", html)
        self.assertIn("他の選手の記録はこちら", html)
        self.assertIn("/data/batting-ranking", html)
        self.assertIn("/data/pitching-ranking", html)
        self.assertIn("セ・リーグ順位表", html)
        self.assertIn("/data/team", html)
        self.assertIn("チーム内リーダー", html)
        self.assertIn("岡本和真", html)
        self.assertIn("/data/leaders", html)
        self.assertIn("dataset-notable-data", html)
        self.assertIn('"@type": "Dataset"', html)
        forbidden = [
            "投手 一覧",
            "捕手 一覧",
            "内野手 一覧",
            "外野手 一覧",
            "育成選手 一覧",
            "監督・コーチ 一覧",
            "ys-cluster-pitcher-table",
            "ys-cluster-catcher-table",
            "ys-cluster-infielder-table",
            "ys-cluster-outfielder-table",
            "ys-cluster-ikusei-table",
            "ys-cluster-staff-table",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, html)
        matches = re.findall(r'<script[^>]*type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        dataset = next(json.loads(m) for m in matches if "Dataset" in m)
        self.assertEqual(dataset["url"], "https://yoshilover.com/data/notable")
        item_list = next(json.loads(m) for m in matches if "ItemList" in m)
        self.assertEqual(item_list["itemListElement"][0]["name"], "吉川尚輝 連続試合安打 6試合")

    def test_cluster_does_not_render_recent_hot_card(self) -> None:
        hot = {"batter": [("吉川尚輝", "OPS .950", 3, 144)], "pitcher": []}
        html = render_cluster_html(self.players, hot=hot)
        self.assertNotIn("直近5試合の注目選手", html)
        self.assertNotIn("OPS .950", html)

    def test_player_count_displayed(self) -> None:
        html = render_cluster_html(self.players)
        self.assertIn("3 名", html)

    def test_jsonld_collection_page(self) -> None:
        html = render_cluster_html(self.players)
        matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        self.assertGreaterEqual(len(matches), 2)
        cp = next(json.loads(m) for m in matches if "CollectionPage" in m)
        self.assertEqual(cp["@type"], "CollectionPage")
        self.assertEqual(cp["url"], "https://yoshilover.com/data")
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
            self.assertEqual(item["item"]["url"], f"https://yoshilover.com/data/{self.players[i].slug}")

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
                season_games=20, season_ab=76, season_hits=17, season_rbi=3,
                season_hr=4, season_avg=0.224, has_stats=True,
            ),
        ]
        html = render_cluster_html(players)
        self.assertIn(">20<", html)  # 試合
        self.assertIn(">76<", html)  # 打数
        self.assertIn(">17<", html)  # 安打
        self.assertIn(".224", html)  # 打率
        self.assertIn(">4<", html)  # 本塁打

    def test_batter_table_has_ab_and_hr_columns(self) -> None:
        """捕手/内野手/外野手 表に 打数・本塁打 列がある (本塁打追加 2026-06-10)。"""
        html = render_cluster_html(self.players)
        self.assertIn(">打数</th>", html)
        self.assertIn(">本塁打</th>", html)


class RenderClusterTitleTests(unittest.TestCase):
    def test_title_format(self) -> None:
        title = render_cluster_title()
        self.assertIn("巨人選手データ", title)
        self.assertIn("ヨシラバー", title)


class ClusterSearchBoxTests(unittest.TestCase):
    """460: 選手名インクリメンタル検索 box (client-side、 progressive enhancement)。"""

    def setUp(self) -> None:
        self.players = [
            ClusterPlayerEntry(name="戸郷翔征", slug="togo-shosei", position="投手", jersey_number="20"),
            ClusterPlayerEntry(name="坂本勇人", slug="sakamoto-hayato", position="内野手", jersey_number="6"),
        ]

    def test_search_box_present(self) -> None:
        html = render_cluster_html(self.players)
        self.assertIn('id="ys-player-search"', html)
        self.assertIn('type="search"', html)
        self.assertIn("選手名で検索", html)

    def test_search_script_scoped_to_player_tables(self) -> None:
        html = render_cluster_html(self.players)
        # JS が table section 内の /data/ リンクのみ対象にする (intro ナビ除外)
        self.assertIn('section[class*="ys-cluster"][class*="-table"] a[href^="/data"]', html)
        self.assertIn("closest(\"tr\")", html)
        self.assertIn('id="ys-search-empty"', html)

    def test_search_box_before_tables(self) -> None:
        html = render_cluster_html(self.players)
        # 検索 box は選手テーブルより前 (画面上部) に出る
        self.assertLess(html.index("ys-player-search"), html.index("/data/togo-shosei"))

    def test_full_list_intact_without_js(self) -> None:
        # progressive enhancement: 検索を入れても全選手リンクはそのまま残る
        html = render_cluster_html(self.players)
        for p in self.players:
            self.assertIn(f"/data/{p.slug}", html)


if __name__ == "__main__":
    unittest.main()
