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
