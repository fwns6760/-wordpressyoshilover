"""Tests for data_site_template_pillar (ticket 443/444 Phase 1.0)."""

from __future__ import annotations

import json
import re
import unittest

from src.data_site_template_pillar import (
    PillarPlayerInfo,
    render_pillar_html,
    render_pillar_title,
    render_pillar_excerpt,
    _build_ob_milestones_html,
    _build_career_milestones_html,
)


class RenderPillarExcerptTests(unittest.TestCase):
    """SNS 共有 / meta description 用 excerpt (崩れたパンくず+数字を防ぐ)。"""

    def _clean(self, text: str) -> None:
        # パンくず / 生 stats 羅列 が混ざらず、 句点で終わる 1 文であること
        self.assertNotIn("Home ›", text)
        self.assertNotIn("›", text)
        self.assertTrue(text.endswith("。"))
        self.assertLessEqual(len(text), 120)

    def test_batter_excerpt(self):
        p = PillarPlayerInfo(
            name="吉川尚輝", slug="yoshikawa-naoki", position="内野手", jersey_number="2",
            role="player", has_stats=True, season_avg=0.227, season_hits=20, season_rbi=8,
        )
        ex = render_pillar_excerpt(p)
        self._clean(ex)
        self.assertIn("吉川尚輝", ex)
        self.assertIn("打率.227", ex)
        self.assertIn("序盤/中盤/終盤", ex)

    def test_pitcher_excerpt(self):
        p = PillarPlayerInfo(
            name="戸郷翔征", slug="togo-shosei", position="投手", jersey_number="20",
            role="player", has_pitching_stats=True, pitch_wins=5, pitch_losses=3,
            pitch_era=2.45, pitch_k=80,
        )
        ex = render_pillar_excerpt(p)
        self._clean(ex)
        self.assertIn("戸郷翔征", ex)
        self.assertIn("5勝3敗", ex)
        self.assertIn("防御率2.45", ex)

    def test_manager_excerpt(self):
        p = PillarPlayerInfo(
            name="阿部慎之助", slug="abe-shinnosuke", position="監督", jersey_number="",
            role="manager",
        )
        ex = render_pillar_excerpt(p)
        self._clean(ex)
        self.assertIn("阿部慎之助", ex)
        self.assertIn("通算成績", ex)

    def test_no_stats_placeholder_excerpt(self):
        p = PillarPlayerInfo(
            name="新人選手", slug="rookie", position="内野手", jersey_number="99",
            role="player", has_stats=False,
        )
        ex = render_pillar_excerpt(p)
        self._clean(ex)
        self.assertIn("新人選手", ex)


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
        self.assertIn('https://yoshilover.com/data', html)
        self.assertIn("巨人選手データ", html)

    def test_lead_paragraph_precedes_breadcrumb(self) -> None:
        # SSP の auto description が breadcrumb ではなく lead 文で始まるよう、
        # lead <p> が breadcrumb より前に出ること
        html = render_pillar_html(self.player)
        self.assertIn('class="ys-lead"', html)
        # 要素の出現順 (style block の CSS セレクタでなく実マークアップ) で比較
        self.assertLess(html.index('class="ys-lead"'), html.index('class="ys-bc"'))

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
        self.assertEqual(sports_data["url"], "https://yoshilover.com/data/sakamoto-hayato")
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
        self.assertIn("ys-bar", html)  # 横棒バー可視化
        self.assertIn("本拠地", html)
        self.assertIn("ビジター", html)
        self.assertIn("大手未掲載", html)

    def test_venue_split_section_skipped_when_empty(self) -> None:
        # data 無し player では venue section を出さない (placeholder 乱立防止)
        p = PillarPlayerInfo(name="丸佳浩", slug="maru-yoshihiro", position="外野手", jersey_number="8")
        html = render_pillar_html(p)
        self.assertNotIn("ys-pillar-venue-split", html)

    def test_inning_split_section_rendered(self) -> None:
        p = PillarPlayerInfo(name="吉川尚輝", slug="yoshikawa-naoki", position="内野手", jersey_number="2")
        p.inning_split_stats = [
            ("序盤", 38, 7, 7 / 38),
            ("中盤", 25, 5, 5 / 25),
            ("終盤", 28, 8, 8 / 28),
        ]
        html = render_pillar_html(p)
        self.assertIn("ys-bar", html)  # 横棒バー可視化
        self.assertIn("序盤", html)
        self.assertIn("中盤", html)
        self.assertIn("終盤", html)
        self.assertIn("大手未掲載", html)
        self.assertIn(".286", html)  # 8/28 終盤 avg

    def test_inning_split_section_skipped_when_empty(self) -> None:
        p = PillarPlayerInfo(name="丸佳浩", slug="maru-yoshihiro", position="外野手", jersey_number="8")
        html = render_pillar_html(p)
        self.assertNotIn("ys-pillar-inning-split", html)

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
        self.assertIn('href="/data/yamazaki-iori"', html)
        self.assertIn('href="/data/akahoshi-yushi"', html)

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


class CareerHistoryRenderTests(unittest.TestCase):
    """467: 実 NPB fixture を parse → pillar に profile + 年度別/通算が網羅描画されること。"""

    @classmethod
    def setUpClass(cls) -> None:
        import os

        from src.npb_career_scraper import parse_player_career

        fix = os.path.join(os.path.dirname(__file__), "fixtures")
        with open(os.path.join(fix, "npb_career_batter_sakamoto_51955114.html"),
                  encoding="utf-8", errors="replace") as fh:
            cls.bat_career = parse_player_career(fh.read())
        with open(os.path.join(fix, "npb_career_pitcher_togo_41045138.html"),
                  encoding="utf-8", errors="replace") as fh:
            cls.pit_career = parse_player_career(fh.read())

    def test_batter_profile_and_career(self) -> None:
        p = PillarPlayerInfo(
            name="坂本勇人", slug="sakamoto-hayato", position="内野手",
            jersey_number="6", role="player", npb_career=self.bat_career,
        )
        html = render_pillar_html(p)
        # profile section
        self.assertIn("プロフィール", html)
        self.assertIn("1988年12月14日", html)
        self.assertIn("光星学院", html)
        # 年度別/通算 section (全列網羅 + 通算)
        self.assertIn("年度別成績・通算", html)
        self.assertIn("打撃成績", html)
        self.assertIn("2007", html)   # 入団年
        self.assertIn("通", html)      # 通算行
        self.assertIn("出塁率", html)  # 打撃フル列の末尾
        self.assertIn("併殺打", html)
        # 投手成績表は出ない (野手)
        self.assertNotIn("投手成績", html)

    def test_pitcher_career_columns(self) -> None:
        p = PillarPlayerInfo(
            name="戸郷翔征", slug="togo-shosei", position="投手",
            jersey_number="20", role="player", npb_career=self.pit_career,
        )
        html = render_pillar_html(p)
        self.assertIn("投手成績", html)
        self.assertIn("防御率", html)
        self.assertIn("投球回", html)
        self.assertIn("8.2", html)    # nested inning table flatten が描画まで通る
        self.assertIn("自責点", html)
        # 投手は打撃成績表を出さない (冗長回避)。 lead 文の「打撃成績」は別物なので表見出しで判定。
        self.assertNotIn(">打撃成績</h3>", html)

    def test_no_career_no_section(self) -> None:
        p = PillarPlayerInfo(
            name="無記録選手", slug="none", position="内野手",
            jersey_number="99", role="player", npb_career=None,
        )
        html = render_pillar_html(p)
        self.assertNotIn("年度別成績・通算", html)
        self.assertNotIn("プロフィール</h2>", html)


class CareerMilestoneRenderTests(unittest.TestCase):
    """468-2: 通算節目の到達ブロック (現役 = live 計算 / OB = precomputed)。"""

    def test_active_player_milestone_block(self) -> None:
        # 年度別から 1000安打 を跨ぐ最小 career
        career = {
            "is_pitcher": False,
            "batting": {
                "years": [
                    {"年度": "2010", "試合": "140", "安打": "600", "本塁打": "20", "打点": "60", "盗塁": "5"},
                    {"年度": "2011", "試合": "140", "安打": "600", "本塁打": "20", "打点": "60", "盗塁": "5"},
                ],
                "total": {"安打": "1200", "本塁打": "40", "打点": "120", "試合": "280"},
            },
            "pitching": None,
        }
        p = PillarPlayerInfo(name="テスト選手", slug="test", position="内野手",
                             jersey_number="00", npb_career=career)
        html = _build_career_milestones_html(p)
        self.assertIn("通算節目の到達", html)
        self.assertIn("通算1000安打", html)
        self.assertIn("2011年に到達", html)

    def test_ob_legend_milestone_block_oh(self) -> None:
        # 王貞治: precomputed JSON 由来。868本→800本塁打、2786安打→2500安打 が出る
        p = PillarPlayerInfo(name="王貞治", slug="oh-sadaharu", position="", jersey_number="")
        html = _build_ob_milestones_html(p)
        self.assertIn("通算節目の到達", html)
        self.assertIn("通算800本塁打", html)
        self.assertIn("通算2500安打", html)
        # 868本に届かない 900本塁打 は出さない
        self.assertNotIn("通算900本塁打", html)

    def test_ob_unknown_player_empty(self) -> None:
        p = PillarPlayerInfo(name="存在しない人", slug="nobody", position="", jersey_number="")
        self.assertEqual(_build_ob_milestones_html(p), "")


if __name__ == "__main__":
    unittest.main()
