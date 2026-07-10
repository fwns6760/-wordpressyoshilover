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
        self.assertEqual(rows[0]["keyword"], "アシナガバチ")
        self.assertEqual(rows[0]["traffic"], "200+")
        self.assertEqual(rows[1]["keyword"], "岡本和真")
        self.assertEqual(rows[3]["keyword"], "有吉の壁")
        self.assertEqual(rows[3]["traffic"], "")

    def test_parse_empty(self):
        self.assertEqual(stn.parse_trend_rss(""), [])


class NoteAndBoostTests(unittest.TestCase):
    def _run(self, candidates, roster=None):
        with patch.object(stn, "fetch_jp_trends", return_value=stn.parse_trend_rss(_RSS)), \
             patch.object(stn, "_giants_name_tokens", return_value=roster or set()):
            return stn.build_trend_note_and_boost(candidates)

    def test_note_lists_baseball_first_and_top10_reference(self):
        note = self._run([], roster={"岡本和真", "岡本"})
        fire_line, ref_line = note.split("\n", 1)
        self.assertIn("岡本和真(2万+)", fire_line)
        self.assertIn("パドレス 対 dバックス(500+)", fire_line)
        # 野球関連行には一般語を入れない (参考TOP10 行には入る)
        self.assertNotIn("アシナガバチ", fire_line)
        self.assertIn("📈 参考・総合急上昇TOP10", ref_line)
        self.assertIn("アシナガバチ", ref_line)
        self.assertIn("有吉の壁", ref_line)

    def test_matching_candidate_gets_fire_tag(self):
        c = _Cand(title="本塁打", post_text="岡本和真が决めた")
        note = self._run([c], roster={"岡本和真"})
        self.assertTrue(c.title.startswith("🔥[急上昇: 岡本和真]"))
        self.assertTrue(note)

    def test_non_matching_candidate_untouched(self):
        c = _Cand(title="登録公示", post_text="浅野翔吾")
        self._run([c], roster={"岡本和真"})
        self.assertEqual(c.title, "登録公示")

    def test_no_relevant_trend_returns_top10_reference_only(self):
        with patch.object(
            stn, "fetch_jp_trends",
            return_value=[{"keyword": "有吉の壁", "traffic": ""}],
        ), patch.object(stn, "_giants_name_tokens", return_value=set()):
            note = stn.build_trend_note_and_boost([])
        self.assertIn("📈 参考・総合急上昇TOP10", note)
        self.assertIn("有吉の壁", note)
        self.assertNotIn("🔥", note)

    def test_fetch_failure_returns_empty(self):
        with patch.object(stn, "fetch_jp_trends", return_value=[]):
            self.assertEqual(stn.build_trend_note_and_boost([]), "")

    def test_compound_keyword_token_match(self):
        c = _Cand(title="MLB", post_text="パドレスがdバックスに勝利")
        self._run([c])
        self.assertTrue(c.title.startswith("🔥"))


class WeaveGateTests(unittest.TestCase):
    def test_ok(self):
        with patch.object(stn, "_giants_name_tokens", return_value={"岡本和真"}):
            self.assertTrue(stn._weave_gate_ok(
                "岡本和真が決めた。", "オールスターの岡本和真が決めた。", "オールスター"
            ))

    def test_keyword_missing_rejected(self):
        self.assertFalse(stn._weave_gate_ok("本文。", "本文のまま。", "オールスター"))

    def test_new_number_rejected(self):
        with patch.object(stn, "_giants_name_tokens", return_value=set()):
            self.assertFalse(stn._weave_gate_ok(
                "岡本和真が決めた。", "オールスターで打率.999の岡本和真が決めた。", "オールスター"
            ))

    def test_new_roster_name_rejected(self):
        with patch.object(stn, "_giants_name_tokens", return_value={"戸郷翔征"}):
            self.assertFalse(stn._weave_gate_ok(
                "岡本和真が決めた。", "オールスターは戸郷翔征と岡本和真。", "オールスター"
            ))

    def test_too_long_rejected(self):
        with patch.object(stn, "_giants_name_tokens", return_value=set()):
            self.assertFalse(stn._weave_gate_ok(
                "短い。", "オールスター" + "あ" * 200, "オールスター"
            ))


class WeaveApplyTests(unittest.TestCase):
    def test_weave_updates_post_and_title(self):
        c = _Cand(title="候補A", post_text="岡本和真が決めた。")
        with patch.object(
            stn, "_weave_llm",
            return_value=("オールスターの岡本和真が決めた。", "オールスター"),
        ), patch.object(stn, "_giants_name_tokens", return_value=set()):
            n = stn.weave_trends_into_candidates(
                [c], [{"keyword": "オールスター", "traffic": ""}], gemini_api_key="k"
            )
        self.assertEqual(n, 1)
        self.assertIn("オールスター", c.post_text)
        self.assertTrue(c.title.startswith("🔥[急上昇入り: オールスター]"))

    def test_candidate_already_containing_kw_skipped(self):
        c = _Cand(title="候補A", post_text="オールスターだ。")
        with patch.object(stn, "_weave_llm") as m:
            n = stn.weave_trends_into_candidates(
                [c], [{"keyword": "オールスター", "traffic": ""}], gemini_api_key="k"
            )
        self.assertEqual(n, 0)
        m.assert_not_called()


class TrendReactionTests(unittest.TestCase):
    _REL = [{
        "keyword": "岡本和真",
        "traffic": "2万+",
        "news_title": "岡本和真がサヨナラ打",
        "news_url": "https://news.example/1",
        "news_source": "報知",
    }]

    def test_builds_candidate_with_keyword(self):
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真、これは効くわ。",
        ):
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNotNone(cand)
        self.assertEqual(cand.metric, "TREND_REACTION")
        self.assertIn("岡本和真", cand.post_text)
        self.assertTrue(cand.signature.startswith("trendreact|"))

    def test_dedup_skips_same_headline(self):
        import hashlib

        sig = "trendreact|" + hashlib.sha1(
            "20260710|岡本和真|岡本和真がサヨナラ打".encode("utf-8")
        ).hexdigest()[:16]
        cand = stn.build_trend_reaction_candidate(
            self._REL, gemini_api_key="k", dedup_set={sig}, now_date="20260710"
        )
        self.assertIsNone(cand)

    def test_new_headline_fires_again(self):
        import hashlib

        old_sig = "trendreact|" + hashlib.sha1(
            "20260710|岡本和真|昨夜の見出し".encode("utf-8")
        ).hexdigest()[:16]
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真、続報も見逃せないな。",
        ):
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set={old_sig},
                now_date="20260710",
            )
        self.assertIsNotNone(cand)

    def test_voice_without_keyword_rejected(self):
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="キーワードが入っていない文。",
        ):
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNone(cand)

    def test_no_news_title_skipped(self):
        rel = [{"keyword": "巨人", "traffic": "", "news_title": ""}]
        cand = stn.build_trend_reaction_candidate(
            rel, gemini_api_key="k", dedup_set=set(), now_date="20260710"
        )
        self.assertIsNone(cand)


if __name__ == "__main__":
    unittest.main()
