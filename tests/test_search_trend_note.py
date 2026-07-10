"""search_trend_note — Google 急上昇ワードの候補メール反映 (2026-07-10)。"""

import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from src import search_trend_note as stn

_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>アシナガバチ</title><ht:approx_traffic>200+</ht:approx_traffic></item>
<item><title>岡本和真</title><ht:approx_traffic>2万+</ht:approx_traffic></item>
<item><title>パドレス 対 dバックス</title><ht:approx_traffic>500+</ht:approx_traffic></item>
<item><title>有吉の壁</title></item>
</channel></rss>"""


@dataclass
class _Cand:
    title: str = "t"
    post_text: str = ""
    draft_text: str = ""
    focus_player: str = ""


class ParseTests(unittest.TestCase):
    def test_parse_keywords_and_traffic(self):
        rows = stn.parse_trend_rss(_RSS)
        self.assertEqual(rows[0], {"keyword": "アシナガバチ", "traffic": "200+"})
        self.assertEqual(rows[1]["keyword"], "岡本和真")
        self.assertEqual(rows[3], {"keyword": "有吉の壁", "traffic": ""})

    def test_parse_empty(self):
        self.assertEqual(stn.parse_trend_rss(""), [])


class NoteAndBoostTests(unittest.TestCase):
    def _run(self, candidates, roster=None):
        with patch.object(stn, "fetch_jp_trends", return_value=stn.parse_trend_rss(_RSS)), \
             patch.object(stn, "_giants_name_tokens", return_value=roster or set()):
            return stn.build_trend_note_and_boost(candidates)

    def test_note_lists_only_baseball_related(self):
        note = self._run([], roster={"岡本和真", "岡本"})
        self.assertIn("岡本和真(2万+)", note)
        self.assertIn("パドレス 対 dバックス(500+)", note)
        self.assertNotIn("アシナガバチ", note)
        self.assertNotIn("有吉の壁", note)

    def test_matching_candidate_gets_fire_tag(self):
        c = _Cand(title="本塁打", post_text="岡本和真が决めた")
        note = self._run([c], roster={"岡本和真"})
        self.assertTrue(c.title.startswith("🔥[急上昇: 岡本和真]"))
        self.assertTrue(note)

    def test_non_matching_candidate_untouched(self):
        c = _Cand(title="登録公示", post_text="浅野翔吾")
        self._run([c], roster={"岡本和真"})
        self.assertEqual(c.title, "登録公示")

    def test_no_relevant_trend_returns_empty(self):
        with patch.object(
            stn, "fetch_jp_trends",
            return_value=[{"keyword": "有吉の壁", "traffic": ""}],
        ), patch.object(stn, "_giants_name_tokens", return_value=set()):
            self.assertEqual(stn.build_trend_note_and_boost([]), "")

    def test_fetch_failure_returns_empty(self):
        with patch.object(stn, "fetch_jp_trends", return_value=[]):
            self.assertEqual(stn.build_trend_note_and_boost([]), "")

    def test_compound_keyword_token_match(self):
        c = _Cand(title="MLB", post_text="パドレスがdバックスに勝利")
        self._run([c])
        self.assertTrue(c.title.startswith("🔥"))


if __name__ == "__main__":
    unittest.main()
