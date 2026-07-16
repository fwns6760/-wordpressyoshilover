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

    def test_note_categorized_lines_and_top10_reference(self):
        note = self._run([], roster={"岡本和真", "岡本"})
        lines = note.split("\n")
        giants = next(l for l in lines if l.startswith("🔥 急上昇/巨人"))
        mlb = next(l for l in lines if l.startswith("🌍 急上昇/メジャー"))
        ref = next(l for l in lines if l.startswith("📈 参考・総合急上昇TOP10"))
        self.assertIn("岡本和真(2万+)", giants)
        self.assertIn("パドレス 対 dバックス(500+)", mlb)
        # 野球関連行には一般語を入れない (参考TOP10 行には入る)
        self.assertNotIn("アシナガバチ", giants)
        self.assertIn("アシナガバチ", ref)
        self.assertIn("有吉の壁", ref)

    def test_categorize_trend_keyword(self):
        self.assertEqual(stn.categorize_trend_keyword("巨人 スタメン", set()), "giants")
        self.assertEqual(stn.categorize_trend_keyword("泉口友汰", {"泉口友汰"}), "giants")
        self.assertEqual(stn.categorize_trend_keyword("大谷翔平", set()), "mlb")
        self.assertEqual(stn.categorize_trend_keyword("阪神 先発", set()), "npb")
        self.assertEqual(stn.categorize_trend_keyword("有吉の壁", set()), "")

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
        "category": "giants",
        "news_title": "岡本和真がサヨナラ打",
        "news_url": "https://news.example/1",
        "news_source": "報知",
    }]
    _EXCERPT = "岡本和真が9回2死から左翼席へサヨナラ打を放ち、チームは連敗を止めた。"

    def _excerpt_patch(self, value=None):
        return patch.object(
            stn, "_fetch_article_excerpt",
            return_value=(self._EXCERPT if value is None else value),
        )

    def test_builds_candidate_with_keyword(self):
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真、これは効くわ。",
        ), self._excerpt_patch():
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNotNone(cand)
        self.assertEqual(cand.metric, "TREND_REACTION")
        self.assertIn("岡本和真", cand.post_text)
        # 記事 lead が mail の事実源 (draft) に載り、user が照合できる
        self.assertIn("記事より", cand.draft_text)
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
        ), self._excerpt_patch():
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set={old_sig},
                now_date="20260710",
            )
        self.assertIsNotNone(cand)

    def test_voice_without_keyword_rejected(self):
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="キーワードが入っていない文。",
        ), self._excerpt_patch():
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNone(cand)

    def test_article_unreachable_skipped(self):
        # 記事が読めない候補は長文反応を作らない (2026-07-10 捏造対策)
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真、これは効くわ。",
        ), self._excerpt_patch(value=""):
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNone(cand)

    def test_ungrounded_mlb_claim_rejected(self):
        # 実事故 (2026-07-10): 事実源に無い「メジャー行き」を LLM が補完 → 全破棄
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真がメジャーでも通用する打棒を見せました。",
        ), self._excerpt_patch():
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNone(cand)

    def test_ungrounded_player_name_rejected(self):
        # 事実源に無い実名 (roster) が生成文に混入 → 全破棄
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真に続いて坂本勇人にも期待ですね。",
        ), self._excerpt_patch(), patch.object(
            stn, "_giants_name_tokens", return_value={"坂本勇人", "坂本"}
        ):
            cand = stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNone(cand)

    def test_dated_headline_requires_time_context(self):
        # 実運用 2026-07-10: 「11日の巨人戦で今季初先発」記事への反応が
        # 今夜の話に読める文になった → 日付/時制の明示を gate で強制
        rel = [{**self._REL[0], "news_title": "岡本和真 11日の中日戦で復帰へ"}]
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真の復帰、待ちに待った瞬間ですね。",
        ), self._excerpt_patch(value="岡本和真が11日の中日戦で戦列復帰する見込みだ。"):
            cand = stn.build_trend_reaction_candidate(
                rel, gemini_api_key="k", dedup_set=set(), now_date="20260710-19"
            )
        self.assertIsNone(cand)  # 本文に「11日」も「あす」も無い → 破棄

    def test_dated_headline_with_tomorrow_word_allowed(self):
        rel = [{**self._REL[0], "news_title": "岡本和真 11日の中日戦で復帰へ"}]
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真があす復帰とのこと、待ちに待った瞬間ですね。",
        ), self._excerpt_patch(value="岡本和真が11日の中日戦で戦列復帰する見込みだ。"):
            cand = stn.build_trend_reaction_candidate(
                rel, gemini_api_key="k", dedup_set=set(), now_date="20260710-19"
            )
        self.assertIsNotNone(cand)  # 10日基準で 11日=あす の言い換えは整合

    def test_compound_keyword_natural_notation_ok(self):
        # 2026-07-10 19:30便実測: kw「dena 対 巨人」を LLM が「DeNA対巨人」と
        # 自然表記 → 逐語一致で毎回落ちた。token + case 非依存で通す。
        rel = [{
            "keyword": "dena 対 巨人", "traffic": "5万+", "category": "giants",
            "news_title": "巨人がDeNAと今夜対戦", "news_url": "https://news.example/9",
            "news_source": "報知",
        }]
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="今夜のDeNA対巨人、序盤から目が離せない展開ですね。",
        ), self._excerpt_patch(value="巨人は今夜、横浜スタジアムでDeNAと対戦する。"):
            cand = stn.build_trend_reaction_candidate(
                rel, gemini_api_key="k", dedup_set=set(), now_date="20260710-19"
            )
        self.assertIsNotNone(cand)

    def test_grounded_claim_word_allowed(self):
        # 事実源に claim 語がある場合は通る (over-blocking しない)
        rel = [{**self._REL[0], "news_title": "岡本和真 メジャー挑戦を表明"}]
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真のメジャー挑戦、ついに来ましたね。",
        ), self._excerpt_patch(value="岡本和真が会見でメジャー挑戦の意向を明らかにした。"):
            cand = stn.build_trend_reaction_candidate(
                rel, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNotNone(cand)

    def test_no_news_title_skipped(self):
        rel = [{
            "keyword": "巨人", "traffic": "", "category": "giants",
            "news_title": "",
        }]
        cand = stn.build_trend_reaction_candidate(
            rel, gemini_api_key="k", dedup_set=set(), now_date="20260710"
        )
        self.assertIsNone(cand)

    def test_npb_other_team_skipped_mlb_ok(self):
        # 2026-07-10 user「巨人やメジャーならいいけど。他球団なら意味ない」
        rel = [
            {
                "keyword": "阪神", "traffic": "5万+", "category": "npb",
                "news_title": "阪神が首位攻防戦を制す",
                "news_url": "https://news.example/2", "news_source": "報知",
            },
            {
                "keyword": "大谷翔平", "traffic": "10万+", "category": "mlb",
                "news_title": "大谷翔平が30号ホームラン",
                "news_url": "https://news.example/3", "news_source": "報知",
            },
        ]
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="大谷翔平、この打球速度は別格ですね。",
        ), patch.object(
            stn, "_fetch_article_excerpt",
            return_value="大谷翔平が第1打席で今季30号となる先制ソロを放った。",
        ):
            cand = stn.build_trend_reaction_candidate(
                rel, gemini_api_key="k", dedup_set=set(), now_date="20260710"
            )
        self.assertIsNotNone(cand)
        self.assertIn("大谷翔平", cand.title)
        self.assertNotIn("阪神", cand.title)


if __name__ == "__main__":
    unittest.main()


class YahooTopicsMergeTests(unittest.TestCase):
    """2026-07-10 user「メジャーとプロ野球のトレンドがとんでない」対応。"""

    _TOPICS = [
        "DeNA デュプランティエが退団へ",
        "大谷翔平 3試合連発の36号",
        "巨人 岡本和真が復帰",
        "一発退場の処分 FIFA判断分かれる",  # 野球外 → 除外
        "高校野球 金足農まさかの初戦敗退",
    ]

    def test_topics_fill_empty_categories(self):
        relevant = []
        stn.merge_yahoo_topics_into_relevant(
            relevant, set(), topics=list(self._TOPICS)
        )
        cats = {t["keyword"]: t["category"] for t in relevant}
        self.assertEqual(cats["DeNA デュプランティエが退団へ"], "npb")
        self.assertEqual(cats["大谷翔平 3試合連発の36号"], "mlb")
        self.assertEqual(cats["巨人 岡本和真が復帰"], "giants")
        self.assertNotIn("一発退場の処分 FIFA判断分かれる", cats)
        # トピックスは反応候補の素材にもなる (news_title 付き)
        self.assertTrue(all(t["news_title"] for t in relevant))

    def test_note_includes_topics_when_google_has_no_baseball(self):
        with patch.object(
            stn, "fetch_jp_trends",
            return_value=[{"keyword": "皇室典範", "traffic": "", "news_title": "",
                          "news_url": "", "news_source": ""}],
        ), patch.object(stn, "_giants_name_tokens", return_value=set()), \
             patch.object(stn, "fetch_yahoo_sports_topics",
                          return_value=list(self._TOPICS)):
            note = stn.build_trend_note_and_boost([])
        self.assertIn("⚾ 急上昇/プロ野球", note)
        self.assertIn("DeNA デュプランティエが退団へ", note)
        self.assertIn("🌍 急上昇/メジャー", note)
        self.assertIn("大谷翔平 3試合連発の36号", note)

    def test_per_category_cap(self):
        relevant = [
            {"keyword": f"巨人ネタ{i}", "traffic": "", "category": "giants"}
            for i in range(5)
        ]
        stn.merge_yahoo_topics_into_relevant(
            relevant, set(), topics=["巨人 追加ネタ"]
        )
        self.assertEqual(
            len([t for t in relevant if t["category"] == "giants"]), 5
        )


class MlbMentionFillTests(unittest.TestCase):
    """2026-07-10 user「検索トレンドにメジャーはないの？」: MLB 空白の fallback。"""

    def test_fills_when_mlb_empty(self):
        relevant = [{"keyword": "巨人 スタメン", "traffic": "", "category": "giants"}]
        stn.fill_mlb_from_mentions(relevant, keywords=["大谷翔平", "マイコラス"])
        mlb = [t for t in relevant if t["category"] == "mlb"]
        self.assertEqual([t["keyword"] for t in mlb], ["大谷翔平", "マイコラス"])
        # news_title 無し = トレンド反応候補の素材にはしない
        self.assertTrue(all(not t["news_title"] for t in mlb))

    def test_skips_when_mlb_already_present(self):
        relevant = [{"keyword": "大谷翔平", "traffic": "", "category": "mlb"}]
        stn.fill_mlb_from_mentions(relevant, keywords=["山本由伸"])
        self.assertEqual(len(relevant), 1)


class TrendReactionShortDefaultTests(unittest.TestCase):
    """2026-07-16 user「長文は伸びなかったから短文に」: fav実測 (260字以上=中央値1、
    100-180字=中央値10) で mail便トレンド反応の既定を短文 (force_long=False) へ。"""

    _REL = [{
        "keyword": "岡本和真", "category": "giants",
        "news_title": "岡本和真がサヨナラ打", "news_url": "https://ex.com/a",
        "news_source": "報知",
    }]

    def test_default_is_short_form(self):
        with patch(
            "src.x_post_branding_gen.build_quote_rt_comment",
            return_value="岡本和真、これは効くわ。",
        ) as m, patch.object(
            stn, "_fetch_article_excerpt", return_value="記事本文の抜粋テキスト。",
        ):
            stn.build_trend_reaction_candidate(
                self._REL, gemini_api_key="k", dedup_set=set(), now_date="20260716"
            )
        self.assertFalse(m.call_args.kwargs.get("force_long"))
        # 短文モードは 135字 cap 指示が extra_voice_note に入る
        self.assertIn("135字以内", m.call_args.kwargs.get("extra_voice_note", ""))
