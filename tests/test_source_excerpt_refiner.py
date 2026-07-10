"""source_excerpt_refiner の原文一致 gate (捏造ゼロ構造) のテスト。

LLM 呼び出し自体は mock/対象外 — parse_passages / verify_and_join の
pure 関数と、refine_excerpt の入力ガードだけを検証する。
"""

import unittest

from src.source_excerpt_refiner import (
    parse_passages,
    refine_excerpt,
    verify_and_join,
)

_SRC = (
    "阿部慎之助監督は試合後、報道陣に対して静かに語り始めた。"
    "「あの場面で代えたのは私の責任。選手は最後までよくやってくれた」"
    "と敗戦の弁を述べた。ベンチ裏では若手に直接声をかける場面もあった。\n"
    "一方でファンからは采配への疑問の声も上がっている。"
    "次戦は甲子園での首位攻防戦となる。"
)


class ParsePassagesTest(unittest.TestCase):
    def test_two_labels(self):
        raw = "PASSAGE1: 一節その1です。\nPASSAGE2: 一節その2です。"
        self.assertEqual(parse_passages(raw), ["一節その1です。", "一節その2です。"])

    def test_single_label(self):
        self.assertEqual(parse_passages("PASSAGE1: 本文だけ。"), ["本文だけ。"])

    def test_no_label_returns_empty(self):
        self.assertEqual(parse_passages("それっぽい文章だけ"), [])
        self.assertEqual(parse_passages(""), [])


class VerifyAndJoinTest(unittest.TestCase):
    def test_literal_passage_accepted(self):
        p = (
            "「あの場面で代えたのは私の責任。選手は最後までよくやってくれた」"
            "と敗戦の弁を述べた。"
        )
        self.assertEqual(verify_and_join([p], _SRC, max_chars=1200), p)

    def test_rewritten_passage_rejected(self):
        p = (
            "阿部慎之助監督は「あの場面で交代させたのは自分の責任だ」と"
            "堂々と敗戦の弁を語った。これは書き換えなので原文に無い。"
        )
        self.assertEqual(verify_and_join([p], _SRC, max_chars=1200), "")

    def test_whitespace_difference_still_literal(self):
        p = (
            "「あの場面で代えたのは私の責任。\n選手は最後までよくやってくれた」"
            "と敗戦の弁を述べた。ベンチ裏では若手に直接声をかける場面もあった。"
        )
        self.assertTrue(verify_and_join([p], _SRC, max_chars=1200))

    def test_too_short_rejected(self):
        self.assertEqual(verify_and_join(["短い。"], _SRC, max_chars=1200), "")

    def test_max_chars_drops_tail_passage(self):
        p1 = "阿部慎之助監督は試合後、報道陣に対して静かに語り始めた。「あの場面で代えたのは私の責任。選手は最後までよくやってくれた」と敗戦の弁を述べた。"
        p2 = "一方でファンからは采配への疑問の声も上がっている。次戦は甲子園での首位攻防戦となる。"
        joined = verify_and_join([p1, p2], _SRC, max_chars=len(p1))
        self.assertEqual(joined, p1)


class RefineExcerptGuardTest(unittest.TestCase):
    def test_no_key_returns_empty(self):
        self.assertEqual(
            refine_excerpt(_SRC, title="t", max_chars=1200, gemini_api_key=""),
            "",
        )

    def test_short_text_returns_empty(self):
        self.assertEqual(
            refine_excerpt("短い", title="t", max_chars=1200, gemini_api_key="k"),
            "",
        )


if __name__ == "__main__":
    unittest.main()
