"""Tests for data_site_template_pillar (ticket 443/444 Phase 1.0)."""

from __future__ import annotations

import json
import re
import unittest

from src.data_site_template_pillar import (
    PillarPlayerInfo,
    render_pillar_html,
    render_pillar_title,
)


class RenderPillarHtmlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = PillarPlayerInfo(
            name="坂本勇人",
            slug="sakamoto-hayato",
            position="内野手",
            jersey_number="6",
            role="player",
            featured_image_url="https://yoshilover.com/wp-content/sample.jpg",
            short_review="今月の調子は上向き。 直近 5 試合で 3 度の長打、 7 番起用が機能している。",
            related_topic_links=[
                ("https://yoshilover.com/73041/", "坂本勇人「最後まで集中して振り切れた」"),
                ("https://yoshilover.com/73037/", "坂本勇人 ベテランの存在感"),
            ],
        )

    def test_html_contains_player_name(self) -> None:
        html = render_pillar_html(self.player)
        self.assertIn("坂本勇人", html)

    def test_breadcrumb_links_to_cluster(self) -> None:
        html = render_pillar_html(self.player)
        self.assertIn('https://yoshilover.com/data/', html)
        self.assertIn("巨人選手データ", html)

    def test_featured_image_included(self) -> None:
        html = render_pillar_html(self.player)
        self.assertIn("https://yoshilover.com/wp-content/sample.jpg", html)
        self.assertIn('alt="坂本勇人選手"', html)

    def test_short_review_section(self) -> None:
        html = render_pillar_html(self.player)
        self.assertIn("今月の調子は上向き", html)

    def test_related_topic_links_present(self) -> None:
        html = render_pillar_html(self.player)
        self.assertIn("https://yoshilover.com/73041/", html)
        self.assertIn("最後まで集中", html)

    def test_jsonld_sports_player_valid(self) -> None:
        html = render_pillar_html(self.player)
        matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        self.assertGreaterEqual(len(matches), 2)
        sports_data = next(json.loads(m) for m in matches if "SportsPlayer" in m)
        self.assertEqual(sports_data["@type"], "SportsPlayer")
        self.assertEqual(sports_data["name"], "坂本勇人")
        self.assertEqual(sports_data["url"], "https://yoshilover.com/data/sakamoto-hayato/")
        self.assertEqual(sports_data["memberOf"]["name"], "読売ジャイアンツ")

    def test_jsonld_breadcrumb_3_items(self) -> None:
        html = render_pillar_html(self.player)
        matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        breadcrumb = next(json.loads(m) for m in matches if "BreadcrumbList" in m)
        self.assertEqual(len(breadcrumb["itemListElement"]), 3)
        self.assertEqual(breadcrumb["itemListElement"][2]["name"], "坂本勇人")

    def test_back_link_to_cluster(self) -> None:
        html = render_pillar_html(self.player)
        self.assertIn("一覧に戻る", html)

    def test_missing_review_skipped(self) -> None:
        p = PillarPlayerInfo(name="丸佳浩", slug="maru-yoshihiro", position="外野手", jersey_number="8")
        html = render_pillar_html(p)
        # short_review が空なら section 自体出さない
        self.assertNotIn("短評", html)
        # 構造は維持
        self.assertIn("丸佳浩", html)

    def test_no_topic_links_placeholder(self) -> None:
        p = PillarPlayerInfo(name="吉川尚輝", slug="yoshikawa-naoki", position="内野手", jersey_number="2")
        html = render_pillar_html(p)
        self.assertIn("関連記事準備中", html)

    def test_name_or_slug_required(self) -> None:
        with self.assertRaises(ValueError):
            render_pillar_html(PillarPlayerInfo(name="", slug="x", position="", jersey_number=""))
        with self.assertRaises(ValueError):
            render_pillar_html(PillarPlayerInfo(name="x", slug="", position="", jersey_number=""))

    def test_venue_split_section_rendered(self) -> None:
        p = PillarPlayerInfo(name="吉川尚輝", slug="yoshikawa-naoki", position="内野手", jersey_number="2")
        p.venue_split_stats = [
            ("本拠地", 14, 53, 8, 5, 8 / 53),
            ("ビジター", 7, 27, 9, 3, 9 / 27),
        ]
        html = render_pillar_html(p)
        self.assertIn("ys-pillar-venue-split", html)
        self.assertIn("本拠地", html)
        self.assertIn("ビジター", html)
        self.assertIn("大手未掲載", html)

    def test_venue_split_section_skipped_when_empty(self) -> None:
        # data 無し player では venue section を出さない (placeholder 乱立防止)
        p = PillarPlayerInfo(name="丸佳浩", slug="maru-yoshihiro", position="外野手", jersey_number="8")
        html = render_pillar_html(p)
        self.assertNotIn("ys-pillar-venue-split", html)

    def test_manager_renders_staff_profile_no_stats(self) -> None:
        p = PillarPlayerInfo(name="阿部慎之助", slug="abe-shinnosuke", position="監督",
                             jersey_number="83", role="manager")
        html = render_pillar_html(p)
        self.assertIn("ys-pillar-staff-profile", html)
        self.assertIn("監督", html)
        # stats section は一切出さない
        self.assertNotIn("ys-pillar-venue-split", html)
        self.assertNotIn("今シーズン 通算", html)
        self.assertNotIn("打順別 成績", html)

    def test_staff_career_stats_batter(self) -> None:
        p = PillarPlayerInfo(name="阿部慎之助", slug="abe-shinnosuke", position="監督",
                             jersey_number="83", role="manager")
        p.career_stats = {"type": "batter", "games": 2282, "avg": ".284", "hits": 2132,
                          "hr": 406, "rbi": 1285, "years": "2001-2019"}
        html = render_pillar_html(p)
        self.assertIn("ys-pillar-career-stats", html)
        self.assertIn("現役時代 通算成績", html)
        self.assertIn("2132", html)
        self.assertIn("406", html)

    def test_staff_career_stats_pitcher(self) -> None:
        p = PillarPlayerInfo(name="内海哲也", slug="utsumi-tetsuya", position="投手コーチ",
                             jersey_number="77", role="coach")
        p.career_stats = {"type": "pitcher", "games": 335, "w": 135, "l": 104,
                          "era": "3.24", "k": 1519, "years": "2004-2022"}
        html = render_pillar_html(p)
        self.assertIn("ys-pillar-career-stats", html)
        self.assertIn("奪三振", html)
        self.assertIn("135", html)

    def test_staff_career_stats_absent_when_none(self) -> None:
        p = PillarPlayerInfo(name="某コーチ", slug="x-coach", position="コーチ",
                             jersey_number="80", role="coach")
        html = render_pillar_html(p)
        self.assertNotIn("ys-pillar-career-stats", html)

    def test_ob_legend_profile_with_mlb(self) -> None:
        p = PillarPlayerInfo(name="松井秀喜", slug="matsui-hideki", position="", jersey_number="", role="ob")
        p.ob_profile = {
            "type": "batter", "years": "NPB 1993-2002 / MLB 2003-2012",
            "teams": "読売ジャイアンツ→ヤンキース 他",
            "npb": {"games": 1268, "avg": ".304", "hr": 332},
            "mlb": {"avg": ".282", "hr": 175, "rbi": 760},
            "honors": ["巨人で本塁打王3回・通算332本塁打", "2009 ワールドシリーズMVP (日本人初)"],
        }
        html = render_pillar_html(p)
        self.assertIn("ys-pillar-ob-profile", html)
        self.assertIn("NPB通算", html)
        self.assertIn("MLB", html)
        self.assertIn("本塁打175", html)
        self.assertIn("2009 ワールドシリーズMVP (日本人初)", html)
        # OB は live stats section を出さない
        self.assertNotIn("ys-pillar-venue-split", html)

    def test_ob_pitcher_omits_zero_fields(self) -> None:
        # games/l/k が 0/欠損の投手 OB は勝利・防御率のみ表示 (0 を出さない)
        p = PillarPlayerInfo(name="桑田真澄", slug="kuwata-masumi", position="", jersey_number="", role="ob")
        p.ob_profile = {"type": "pitcher", "years": "1986-2006", "teams": "巨人",
                        "npb": {"games": 0, "w": 173, "l": 0, "era": "3.55", "k": 0},
                        "honors": ["通算173勝"]}
        html = render_pillar_html(p)
        self.assertIn("173勝", html)
        self.assertIn("防御率3.55", html)
        self.assertNotIn("登板0", html)
        self.assertNotIn("0敗", html)

    def test_sportsplayer_jsonld_has_position_and_jersey(self) -> None:
        p = PillarPlayerInfo(name="戸郷翔征", slug="togo-shosei", position="投手", jersey_number="20")
        html = render_pillar_html(p)
        matches = re.findall(r'<script type="application/ld\+json">(.+?)</script>', html, flags=re.DOTALL)
        sp = next(json.loads(m) for m in matches if '"SportsPlayer"' in m)
        props = {pv["name"]: pv["value"] for pv in sp.get("additionalProperty", [])}
        self.assertEqual(props.get("ポジション"), "投手")
        self.assertEqual(props.get("背番号"), "20")

    def test_related_players_internal_links(self) -> None:
        p = PillarPlayerInfo(name="戸郷翔征", slug="togo-shosei", position="投手", jersey_number="20")
        p.related_players = [("yamazaki-iori", "山﨑伊織"), ("akahoshi-yushi", "赤星優志")]
        html = render_pillar_html(p)
        self.assertIn("ys-pillar-related-players", html)
        self.assertIn("同じ投手の選手", html)
        self.assertIn('href="/data/yamazaki-iori/"', html)
        self.assertIn('href="/data/akahoshi-yushi/"', html)

    def test_related_players_absent_when_empty(self) -> None:
        p = PillarPlayerInfo(name="丸佳浩", slug="maru-yoshihiro", position="外野手", jersey_number="8")
        html = render_pillar_html(p)
        self.assertNotIn("ys-pillar-related-players", html)

    def test_coach_renders_staff_profile(self) -> None:
        p = PillarPlayerInfo(name="内海哲也", slug="utsumi-tetsuya", position="投手コーチ",
                             jersey_number="77", role="coach")
        html = render_pillar_html(p)
        self.assertIn("ys-pillar-staff-profile", html)
        self.assertIn("投手コーチ", html)
        self.assertNotIn("今シーズン 通算", html)


class RenderPillarTitleTests(unittest.TestCase):
    def test_title_format(self) -> None:
        p = PillarPlayerInfo(name="坂本勇人", slug="sakamoto-hayato", position="内野手", jersey_number="6")
        title = render_pillar_title(p)
        self.assertIn("坂本勇人", title)
        self.assertIn("内野手", title)
        self.assertIn("6", title)
        self.assertIn("巨人選手データ", title)


if __name__ == "__main__":
    unittest.main()
