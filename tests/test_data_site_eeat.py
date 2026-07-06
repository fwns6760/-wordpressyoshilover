"""Tests for /data 全ページ共通の E-E-A-T ブロック (2026-07-06 user GO)。

- 信頼フッター: 出典 + データ基準日 (render時刻ではなく最終試合日 = 差分更新を壊さない)
- JSON-LD: BreadcrumbList + Dataset (+pillar は Person)
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src import data_site_publisher as pub


class _Info:
    name = "坂本勇人"
    slug = "sakamoto-hayato"
    role = "player"
    featured_image_url = "https://yoshilover.com/img/sakamoto.jpg"


def _parse_jsonld(script_html: str) -> dict:
    body = script_html.replace('<script type="application/ld+json">', "").replace(
        "</script>", ""
    )
    return json.loads(body)


class EeatFooterTests(unittest.TestCase):
    def setUp(self):
        pub._EEAT_AS_OF_CACHE = "2026-07-05"
        self.addCleanup(lambda: setattr(pub, "_EEAT_AS_OF_CACHE", ""))

    def test_footer_has_source_date_and_about_link(self):
        html = pub._eeat_footer_html()
        self.assertIn("NPB公式発表", html)
        self.assertIn("2026年7月5日", html)
        self.assertIn('href="/data/about"', html)

    def test_footer_without_as_of_still_renders(self):
        pub._EEAT_AS_OF_CACHE = ""
        with patch.object(pub, "fetch_latest_giants_game_date", side_effect=RuntimeError):
            html = pub._eeat_footer_html()
        self.assertIn("NPB公式発表", html)
        self.assertNotIn("データ基準日", html)

    def test_date_format_jp(self):
        self.assertEqual(pub._format_date_jp("2026-07-05"), "2026年7月5日")
        self.assertEqual(pub._format_date_jp(""), "")


class JsonLdTests(unittest.TestCase):
    def setUp(self):
        pub._EEAT_AS_OF_CACHE = "2026-07-05"
        self.addCleanup(lambda: setattr(pub, "_EEAT_AS_OF_CACHE", ""))

    def test_breadcrumb_and_dataset(self):
        data = _parse_jsonld(pub._jsonld_script_html("sakamoto-hayato", "坂本勇人 2026 成績"))
        types = [g["@type"] for g in data["@graph"]]
        self.assertEqual(types, ["BreadcrumbList", "Dataset"])
        ds = data["@graph"][1]
        self.assertEqual(ds["dateModified"], "2026-07-05")
        self.assertEqual(ds["url"], "https://yoshilover.com/data/sakamoto-hayato")
        self.assertIn("https://x.com/yoshilover6760", ds["creator"]["sameAs"])

    def test_person_extra_appended(self):
        person = pub._pillar_person_jsonld(_Info())
        data = _parse_jsonld(
            pub._jsonld_script_html("sakamoto-hayato", "坂本勇人", jsonld_extra=[person])
        )
        self.assertEqual(data["@graph"][2]["@type"], "Person")
        self.assertEqual(data["@graph"][2]["name"], "坂本勇人")
        self.assertEqual(data["@graph"][2]["jobTitle"], "プロ野球選手")

    def test_manager_job_title(self):
        class Mgr(_Info):
            name = "阿部慎之助"
            role = "manager"

        self.assertEqual(pub._pillar_person_jsonld(Mgr())["jobTitle"], "プロ野球監督")


if __name__ == "__main__":
    unittest.main()


class RecentDigestTests(unittest.TestCase):
    """冒頭ダイジェスト (2026-07-06 差別化UX)。"""

    def _batter(self, games):
        from src.data_site_template_pillar import PillarPlayerInfo

        b = PillarPlayerInfo(name="泉口友汰", slug="izuguchi-yuta",
                             position="内野手", jersey_number="35")
        b.recent_games = games
        return b

    def test_hot_batter_digest(self):
        from src.data_site_template_pillar import _build_recent_digest_html

        html = _build_recent_digest_html(self._batter(
            [("07/05", "中日", 4, 2, 1, 3, 0), ("07/04", "中日", 4, 2, 0, 0, 0)]
        ))
        self.assertIn("🔥", html)
        self.assertIn("直近2試合", html)
        self.assertIn(".500", html)

    def test_pitcher_thirds_ip_sum(self):
        from src.data_site_template_pillar import PillarPlayerInfo, _build_recent_digest_html

        p = PillarPlayerInfo(name="戸郷翔征", slug="togo", position="投手", jersey_number="20")
        p.recent_pitching_games = [
            ("07/05", "中日", "○", 6.1, 5, 8, 1, 1),
            ("06/28", "広島", "-", 5.2, 4, 6, 2, 2),
        ]
        html = _build_recent_digest_html(p)
        self.assertIn("12回", html)  # 6回1/3 + 5回2/3 = 12回
        self.assertIn("防御率 2.25", html)

    def test_ob_and_no_data_omitted(self):
        from src.data_site_template_pillar import PillarPlayerInfo, _build_recent_digest_html

        ob = PillarPlayerInfo(name="松井秀喜", slug="matsui", position="",
                              jersey_number="", role="ob")
        self.assertEqual(_build_recent_digest_html(ob), "")
        self.assertEqual(_build_recent_digest_html(self._batter([])), "")

    def test_pillar_jsonld_dataset_only_skips_breadcrumb(self):
        pub._EEAT_AS_OF_CACHE = "2026-07-05"
        try:
            data = _parse_jsonld(
                pub._jsonld_script_html("sakamoto-hayato", "坂本勇人", dataset_only=True)
            )
        finally:
            pub._EEAT_AS_OF_CACHE = ""
        self.assertEqual([g["@type"] for g in data["@graph"]], ["Dataset"])


class ForumCtaTests(unittest.TestCase):
    def test_pillar_has_forum_cta(self):
        from src.data_site_template_pillar import PillarPlayerInfo, _build_forum_cta_html

        info = PillarPlayerInfo(name="泉口友汰", slug="izuguchi-yuta",
                                position="内野手", jersey_number="35")
        html = _build_forum_cta_html(info)
        self.assertIn("泉口友汰について", html)
        self.assertIn("/forums/forum/", html)
        self.assertIn("匿名OK", html)
