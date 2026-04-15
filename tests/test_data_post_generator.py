import unittest

from src import data_post_generator


SAMPLE_HTML = """
<table class="tablefix2">
  <tr class="ststats">
    <td>1</td>
    <td>古賀　優大(ヤ)</td>
    <td>.667</td>
  </tr>
  <tr class="ststats">
    <td>2</td>
    <td>岸田　行倫(巨)</td>
    <td>.286</td>
  </tr>
  <tr class="ststats">
    <td>3</td>
    <td>坂本　誠志郎(神)</td>
    <td>.273</td>
  </tr>
</table>
"""

SAMPLE_BATTING_HTML = """
<h3 class="bis-heading bis-heading--g-2026"><span>2026年度 読売ジャイアンツ</span></h3>
<p class="right">2026年4月13日 現在</p>
<table class="tablefix2">
  <tbody>
    <tr>
      <td class="left-hand"><sup>*</sup>泉口　友汰</td>
      <td>14</td>
      <td>57</td>
      <td>51</td>
      <td>8</td>
      <td>15</td>
      <td>3</td>
      <td>0</td>
      <td>3</td>
      <td>27</td>
      <td>7</td>
      <td>1</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>6</td>
      <td>0</td>
      <td>0</td>
      <td>9</td>
      <td>1</td>
      <td>.294</td>
      <td>.529</td>
      <td>.368</td>
    </tr>
    <tr>
      <td>ダルベック</td>
      <td>13</td>
      <td>52</td>
      <td>44</td>
      <td>3</td>
      <td>9</td>
      <td>4</td>
      <td>0</td>
      <td>2</td>
      <td>19</td>
      <td>7</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>7</td>
      <td>0</td>
      <td>1</td>
      <td>18</td>
      <td>1</td>
      <td>.205</td>
      <td>.432</td>
      <td>.327</td>
    </tr>
    <tr>
      <td>赤星　優志</td>
      <td>5</td>
      <td>1</td>
      <td>1</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
      <td>.000</td>
      <td>.000</td>
      <td>.000</td>
    </tr>
  </tbody>
</table>
"""


class DataPostGeneratorTests(unittest.TestCase):
    def test_parse_caught_stealing_leaders(self):
        entries = data_post_generator.parse_caught_stealing_leaders(SAMPLE_HTML, 2026, "c")

        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[1].player, "岸田　行倫")
        self.assertEqual(entries[1].team, "巨")
        self.assertEqual(entries[1].rate, ".286")
        self.assertEqual(entries[1].rank, 2)

    def test_build_title_uses_giants_primary_entry(self):
        report = {
            "giants_primary": data_post_generator.CaughtStealingEntry(
                rank=2,
                player="岸田　行倫",
                team="巨",
                rate=".286",
                year=2026,
                league="c",
            )
        }

        title = data_post_generator.build_caught_stealing_title(report)

        self.assertIn("岸田", title)
        self.assertIn("セ2位", title)

    def test_build_content_contains_expected_sections(self):
        current_entries = data_post_generator.parse_caught_stealing_leaders(SAMPLE_HTML, 2026, "c")
        report = {
            "year": 2026,
            "current_entries": current_entries,
            "giants_entries": [current_entries[1]],
            "giants_primary": current_entries[1],
            "history_entries": [current_entries[1]],
        }

        content = data_post_generator.build_caught_stealing_content(report)

        self.assertIn("【ニュースの整理】", content)
        self.assertIn("📊 セ・リーグ盗塁阻止率ランキング", content)
        self.assertIn("🧭 他球団と比べた巨人の位置", content)
        self.assertIn("📈 巨人捕手の最近の推移", content)
        self.assertIn("💬 この数字、どう見る？", content)

    def test_parse_team_batting_stats(self):
        updated_label, entries = data_post_generator.parse_team_batting_stats(SAMPLE_BATTING_HTML)

        self.assertEqual(updated_label, "2026年4月13日 現在")
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].name, "泉口 友汰")
        self.assertEqual(entries[0].obp, ".368")
        self.assertEqual(entries[1].ops, ".759")

    def test_build_on_base_title_and_content(self):
        _, entries = data_post_generator.parse_team_batting_stats(SAMPLE_BATTING_HTML)
        report = {
            "year": 2026,
            "updated_label": "2026年4月13日 現在",
            "entries": entries,
            "qualifying_entries": entries[:2],
            "top_entries": entries[:2],
            "gap_entries": [entries[1], entries[0]],
            "source_url": "https://npb.jp/bis/2026/stats/idb1_g.html",
            "min_pa": 10,
        }

        title = data_post_generator.build_on_base_title(report)
        content = data_post_generator.build_on_base_content(report)

        self.assertIn("出塁率", title)
        self.assertIn("泉口", title)
        self.assertIn("📊 巨人打線の出塁率一覧（10打席以上）", content)
        self.assertIn("📚 引用元", content)
        self.assertIn("https://npb.jp/bis/2026/stats/idb1_g.html", content)
        self.assertIn("ダルベックは打率.205", content)


if __name__ == "__main__":
    unittest.main()
