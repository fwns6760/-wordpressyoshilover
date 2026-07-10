"""source_excerpt_refiner の原文一致 gate (捏造ゼロ構造) のテスト。

LLM 呼び出し自体は mock/対象外 — parse_passages / verify_and_join の
pure 関数と、refine_excerpt の入力ガードだけを検証する。
2026-07-10 user「引用の文字が足りない」: 合計 400 字未満の選択は不採用
(caller が従来の冒頭抜粋 1200 字を使う)。
"""

import unittest

from src.source_excerpt_refiner import (
    _MIN_TOTAL_CHARS,
    parse_passages,
    refine_excerpt,
    verify_and_join,
)

_P1 = (
    "阿部慎之助監督は試合後、報道陣に対して静かに語り始めた。"
    "「あの場面で代えたのは私の責任。選手は最後までよくやってくれた。"
    "明日はまた別の戦い方を見せたい」と敗戦の弁を述べた。"
    "ベンチ裏では若手に直接声をかける場面もあり、報道陣の問いかけには"
    "一つひとつ丁寧に言葉を選びながら答えていた。"
    "「結果は全部私が背負う。選手には思い切ってやってほしいと伝えている」"
    "と続け、質問が采配の意図に及ぶと、しばらく間を置いてから"
    "「あそこはああするしかなかった。もう一度同じ場面が来ても同じ決断をする」"
    "と言い切った。その表情には悔しさと同時に、明日へ切り替える指揮官の顔があった。"
)
_P2 = (
    "一方でファンからは采配への疑問の声も上がっている。"
    "スタンドからは厳しい声援も飛んだが、選手たちは整列後も"
    "ファンへの挨拶を欠かさなかった。次戦は甲子園での首位攻防戦となり、"
    "先発は今季防御率リーグ2位の右腕が予告されている。"
    "打線の組み替えを含め、首脳陣の決断が注目される一戦になる。"
    "遠征に帯同する若手の登録も検討されており、ベンチ入りメンバーの発表は"
    "試合当日の午後になる見込みだ。首位攻防の3連戦は今季の行方を占う"
    "天王山として、球場は3日間すべてチケット完売となっている。"
)
_SRC = _P1 + "\n" + _P2 + "\n記事後半には別メニュー調整の詳細も記されている。"


class ParsePassagesTest(unittest.TestCase):
    def test_four_labels(self):
        raw = (
            "PASSAGE1: 一節その1。\nPASSAGE2: 一節その2。\n"
            "PASSAGE3: 一節その3。\nPASSAGE4: 一節その4。"
        )
        self.assertEqual(
            parse_passages(raw),
            ["一節その1。", "一節その2。", "一節その3。", "一節その4。"],
        )

    def test_single_label(self):
        self.assertEqual(parse_passages("PASSAGE1: 本文だけ。"), ["本文だけ。"])

    def test_no_label_returns_empty(self):
        self.assertEqual(parse_passages("それっぽい文章だけ"), [])
        self.assertEqual(parse_passages(""), [])


class VerifyAndJoinTest(unittest.TestCase):
    def test_literal_passages_accepted_when_long_enough(self):
        joined = verify_and_join([_P1, _P2], _SRC, max_chars=1200)
        self.assertEqual(joined, f"{_P1}\n{_P2}")
        self.assertGreaterEqual(len(joined), _MIN_TOTAL_CHARS)

    def test_rewritten_passage_rejected(self):
        fake = (
            "阿部慎之助監督は「あの場面で交代させたのは自分の責任だ」と堂々と語り、"
            "これは原文に無い書き換え文なので literal 一致しないはずである。"
        )
        self.assertEqual(verify_and_join([fake, _P2 + "だが原文に無い一文を足す。"], _SRC, max_chars=1200), "")

    def test_whitespace_difference_still_literal(self):
        p1_with_breaks = _P1.replace("。", "。\n")
        joined = verify_and_join([p1_with_breaks, _P2], _SRC, max_chars=1200)
        self.assertTrue(joined)

    def test_short_total_rejected(self):
        short = "「あの場面で代えたのは私の責任。選手は最後までよくやってくれた。"
        self.assertEqual(verify_and_join([short], _SRC, max_chars=1200), "")

    def test_max_chars_drops_tail_passage_but_keeps_min(self):
        joined = verify_and_join([_P1, _P2], _SRC, max_chars=len(_P1) + 10)
        # P2 を落とすと P1 のみ = _MIN_TOTAL_CHARS 未満なら "" になる
        if len(_P1) >= _MIN_TOTAL_CHARS:
            self.assertEqual(joined, _P1)
        else:
            self.assertEqual(joined, "")


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
