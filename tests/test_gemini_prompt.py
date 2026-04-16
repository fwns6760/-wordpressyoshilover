import unittest

from src import rss_fetcher


class GeminiPromptTests(unittest.TestCase):
    def test_detect_player_article_mode_classifies_three_modes(self):
        self.assertEqual(
            rss_fetcher._detect_player_article_mode(
                "【巨人】田中将大「打線を線にしない」移籍後初の阪神戦へ",
                "田中将大が甲子園での登板へ向けて「打線を線にしない」と話した。",
            ),
            "player_quote",
        )
        self.assertEqual(
            rss_fetcher._detect_player_article_mode(
                "【巨人】戸郷翔征がフォーム修正",
                "久保コーチの助言を受けながらフォームの修正に取り組んでいる。",
            ),
            "player_mechanics",
        )
        self.assertEqual(
            rss_fetcher._detect_player_article_mode(
                "【巨人】グリフィンが一軍合流",
                "先発ローテ候補として一軍に合流した。次回登板へ向けた調整段階にある。",
            ),
            "player_status",
        )

    def test_player_quote_prompt_uses_compact_two_heading_template(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】田中将大「打線を線にしない」移籍後初の阪神戦へ",
            summary="田中将大が甲子園での登板へ向けて「打線を線にしない」と話した。試合前コメントの記事である。",
            category="選手情報",
            source_fact_block="",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
        )

        self.assertIn("田中将大投手は読売ジャイアンツ所属である。", prompt)
        self.assertIn("300〜400文字", prompt)
        self.assertIn("見出しは【ニュースの整理】と【次の注目】の2つのみです。", prompt)
        self.assertIn("事実にない単語を1つでも足さないでください。", prompt)
        self.assertNotIn("フォーム・投げ方の変化", prompt)

    def test_player_mechanics_prompt_uses_repair_template(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】戸郷翔征がフォーム修正",
            summary="戸郷翔征投手がフォーム修正に取り組んでいる。久保康生巡回投手コーチの助言を受けながら、フォームの修正を進めている。次回登板へ向けた調整段階にある。",
            category="選手情報",
            source_fact_block="",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
        )

        self.assertIn("戸郷翔征投手は読売ジャイアンツ所属である。", prompt)
        self.assertIn("400〜550文字", prompt)
        self.assertIn("【ここに注目】では、事実2と事実3に書かれている修正内容を", prompt)
        self.assertIn("同じ事実を繰り返さないでください。", prompt)
        self.assertIn("文末は「〜に注目です」「〜がポイントです」「〜を見たいところです」", prompt)

    def test_player_status_prompt_uses_state_template(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】佐々木俊輔が登録抹消",
            summary="2025年9月1日、佐々木俊輔外野手が出場選手登録を抹消された。9月11日以後でなければ再登録はできない。",
            category="選手情報",
            source_fact_block="",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
            source_day_label="9月1日",
        )

        self.assertIn("佐々木俊輔外野手は読売ジャイアンツ所属である。", prompt)
        self.assertIn("200〜350文字", prompt)
        self.assertIn("本文の最初は必ず「（9月1日時点）」で始めてください。", prompt)
        self.assertIn("見出しは【ニュースの整理】と【次の注目】の2つのみです。", prompt)
        self.assertIn("投手は次回登板、野手は次の実戦出場、捕手は次の登録発表", prompt)
        self.assertIn("同じ事実を繰り返さないでください。", prompt)

    def test_manager_prompt_uses_manager_specific_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="阿部監督「結果残せば使います」「競争は続けます」",
            summary="阿部監督が起用方針について語った。",
            category="首脳陣",
            source_fact_block="・阿部監督が起用方針を説明した\n・元記事中の表現: 「結果残せば使います」",
            win_loss_hint="",
            has_game=False,
            real_reactions=["起用の変化があるか見たい。"],
            source_day_label="4月16日",
        )

        self.assertIn("発言者は必ず", prompt)
        self.assertIn("400〜800文字", prompt)
        self.assertIn("【発言の要旨】", prompt)
        self.assertIn("【発言内容】", prompt)
        self.assertIn("【文脈と背景】", prompt)
        self.assertIn("【次の注目】", prompt)
        self.assertIn("【発言の要旨】の1文目には「4月16日時点」を自然に入れてください。", prompt)
        self.assertIn("引用が2つ以上ある場合は、【発言内容】で2つまで並べて整理してください。", prompt)
        self.assertIn("元記事にない数字、過去比較、一般論、精神論、推測は足さない", prompt)


if __name__ == "__main__":
    unittest.main()
