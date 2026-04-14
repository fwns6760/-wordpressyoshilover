import unittest

from src import rss_fetcher


class GeminiPromptTests(unittest.TestCase):
    def test_strict_prompt_includes_structure_and_fan_temperature(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】戸郷翔征がフォーム改造に手応え",
            summary="戸郷翔征投手がフォーム改造について語った。次回登板へ向けて調整中。",
            category="選手情報",
            source_fact_block="・戸郷翔征投手がフォーム改造について語った\n・次回登板へ向けて調整中",
            win_loss_hint="",
            has_game=False,
            real_reactions=[
                "戸郷の調整が順調ならローテがかなり助かる。",
                "焦らず戻してほしい。内容は悪くなさそう。",
            ],
        )

        self.assertIn("【使ってよい事実】", prompt)
        self.assertIn("【参考にしてよいファンの反応の温度感】", prompt)
        self.assertIn("【ニュースの整理】", prompt)
        self.assertIn("【ここに注目】", prompt)
        self.assertIn("【次の注目】", prompt)
        self.assertIn("最初の1文で", prompt)
        self.assertIn("明確に書く", prompt)
        self.assertIn("事実を2文に分けて丁寧に言い換えて厚みを出してよい", prompt)
        self.assertIn("何を変えているのか", prompt)
        self.assertIn("次の実戦でどこを見るか", prompt)
        self.assertIn("のような無難語はできるだけ避け", prompt)
        self.assertIn("追加材料待ちで文を埋めない", prompt)

    def test_source_fact_block_expands_safe_materials_from_same_source(self):
        fact_block = rss_fetcher._build_source_fact_block(
            title="【巨人】則本昂大「極力、聞かないように」甲子園先発へ",
            summary=(
                "巨人の則本昂大投手が14日の阪神戦で移籍後初勝利を狙う。"
                "2年ぶりとなる甲子園での登板を前に調整した。"
                "昨季王者を破らなければ上位進出はないと強い決意を示した。"
                "野球少年時代から阪神ファンだったことも明かした。"
                "甲子園特有の応援について「極力、聞かないように頑張ります」と話した。"
                "雨で流れた前回登板から仕切り直しのマウンドになる。"
            ),
        )

        self.assertGreaterEqual(fact_block.count("・"), 7)
        self.assertIn("極力、聞かないように", fact_block)

    def test_strict_prompt_omits_fan_section_when_no_reactions(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="阿部監督が起用方針を説明",
            summary="阿部監督が起用方針について語った。",
            category="首脳陣",
            source_fact_block="・阿部監督が起用方針を説明した",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
        )

        self.assertNotIn("【参考にしてよいファンの反応の温度感】", prompt)

    def test_player_prompt_discourages_generic_phrases(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】戸郷翔征がフォーム改造に手応え",
            summary="戸郷翔征投手がフォーム改造について語った。",
            category="選手情報",
            source_fact_block="・戸郷翔征投手がフォーム改造について語った",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
        )

        self.assertIn("『可能性があります』『期待が高まります』『注目されます』『重要な意味を持ちます』", prompt)
        self.assertIn("『どこが気になるか』『どこが分かれ目か』", prompt)

    def test_lineup_prompt_adds_lineup_specific_rules(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】今日のスタメン発表　1番丸、4番岡田",
            summary="巨人が今日のスタメンを発表した。打順と守備位置が明らかになった。",
            category="試合速報",
            source_fact_block="・巨人が今日のスタメンを発表した\n・打順と守備位置が明らかになった",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
        )

        self.assertIn("今日のスタメンのどこが動いたか", prompt)
        self.assertIn("誰が入ったかだけでなく、打順や守備位置のどこが動いたか", prompt)


if __name__ == "__main__":
    unittest.main()
