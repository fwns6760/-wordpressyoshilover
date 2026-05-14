import unittest
from unittest.mock import patch

from src import giants_roster_loader as loader


NPB_HTML_SAMPLE = """
<html><body>
<h2>読売ジャイアンツ</h2>
<h3>2026年度 選手一覧</h3>
<h3>■ 支配下選手</h3>
<table>
<tr class="rosterPlayer"><td>83</td><td class="rosterRegister"><a href="/bis/players/x.html">阿部　慎之助</a></td><td>1979.03.20</td></tr>
<tr class="rosterPlayer"><td>11</td><td class="rosterRegister"><a href="/bis/players/y.html">田中　将大</a></td><td>1988.11.01</td></tr>
<tr class="rosterPlayer"><td>2</td><td class="rosterRegister"><a href="/bis/players/z.html">坂本　達也</a></td><td>2000.01.01</td></tr>
</table>
<h3>■ 育成選手</h3>
<table>
<tr class="rosterPlayer"><td>014</td><td class="rosterRegister"><a href="/bis/players/w.html">堀江　正太郎</a></td><td>2006.10.08</td></tr>
</table>
</body></html>
"""


class GiantsRosterLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        loader.reset_cache()

    def tearDown(self) -> None:
        loader.reset_cache()

    def test_parses_shihaikako_and_ikusei_sections(self):
        entries = loader._parse_npb_html(NPB_HTML_SAMPLE)
        names = [e["name"] for e in entries]
        self.assertIn("阿部 慎之助", names)
        self.assertIn("坂本 達也", names)
        self.assertIn("堀江 正太郎", names)
        roles = {e["name"]: e["role"] for e in entries}
        self.assertEqual(roles["阿部 慎之助"], "shihaikako")
        self.assertEqual(roles["堀江 正太郎"], "ikusei")

    def test_alias_contains_full_name_variants_only(self):
        # Surname-only aliases are NOT generated; the lineup parsers
        # already do surname-prefix matching at runtime via
        # ``is_giants_player`` length 1-4 fallback.
        entries = loader._parse_npb_html(NPB_HTML_SAMPLE)
        sakamoto = next(e for e in entries if e["name"] == "坂本 達也")
        self.assertIn("坂本 達也", sakamoto["aliases"])
        self.assertIn("坂本達也", sakamoto["aliases"])
        self.assertNotIn("坂本", sakamoto["aliases"])
        self.assertNotIn("坂本達", sakamoto["aliases"])

    def test_fetch_failure_falls_back_to_json(self):
        with patch.object(loader, "_fetch_npb_roster", return_value=[]):
            entries = loader.load_active_roster(force_refresh=True)
        self.assertIsInstance(entries, list)
        self.assertEqual(loader.cache_source(), "fallback")

    def test_fetch_success_merges_with_fallback(self):
        npb_only = loader._parse_npb_html(NPB_HTML_SAMPLE)
        with patch.object(loader, "_fetch_npb_roster", return_value=npb_only):
            entries = loader.load_active_roster(force_refresh=True)
        names = {e["name"].replace(" ", "") for e in entries}
        self.assertIn("阿部慎之助", names)
        self.assertEqual(loader.cache_source(), "npb+fallback")

    def test_cache_returns_same_object_within_ttl(self):
        with patch.object(loader, "_fetch_npb_roster", return_value=[]):
            first = loader.load_active_roster(force_refresh=True)
            second = loader.load_active_roster()
        self.assertIs(first, second)

    def test_disable_env_skips_fetch(self):
        with patch.dict("os.environ", {"DISABLE_NPB_ROSTER_FETCH": "1"}, clear=False):
            with patch.object(loader, "_http_get") as mocked_get:
                loader.load_active_roster(force_refresh=True)
            mocked_get.assert_not_called()
        self.assertEqual(loader.cache_source(), "fallback")

    def test_merge_dedupes_by_normalized_name(self):
        json_entries = [
            {"name": "阿部慎之助", "aliases": ["阿部"], "active": True, "role": "manager"},
        ]
        npb_entries = loader._parse_npb_html(NPB_HTML_SAMPLE)
        merged = loader._merge_with_fallback(npb_entries, json_entries)
        abe_entries = [e for e in merged if e["name"].replace(" ", "") == "阿部慎之助"]
        self.assertEqual(len(abe_entries), 1)


if __name__ == "__main__":
    unittest.main()
