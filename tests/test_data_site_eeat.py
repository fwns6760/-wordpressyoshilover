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
