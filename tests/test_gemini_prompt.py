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

    def test_lineup_prompt_uses_game_specific_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】今日のスタメン発表　1番丸、4番岡田",
            summary="巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。予告先発は田中将大投手。18:00開始予定。",
            category="試合速報",
            source_fact_block="・巨人が阪神戦のスタメンを発表\n・1番に丸佳浩、4番に岡田悠希\n・予告先発は田中将大投手\n・18:00開始予定",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
        )

        self.assertIn("【試合概要】", prompt)
        self.assertIn("【スタメン一覧】", prompt)
        self.assertIn("【先発投手】", prompt)
        self.assertIn("【注目ポイント】", prompt)
        self.assertIn("選手名、球場名、開始時刻、打順、成績数字は source にある表記をそのまま残す", prompt)

    def test_postgame_prompt_uses_game_specific_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】阪神に3-2で勝利　岡田が決勝打",
            summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。田中将大投手は7回2失点だった。",
            category="試合速報",
            source_fact_block="・巨人が阪神に3-2で勝利\n・岡田悠希の決勝打\n・田中将大投手は7回2失点",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
        )

        self.assertIn("【試合結果】", prompt)
        self.assertIn("【ハイライト】", prompt)
        self.assertIn("【選手成績】", prompt)
        self.assertIn("【試合展開】", prompt)
        self.assertIn("source にあるスコア 3-2 を必ず残してください。", prompt)

    def test_pregame_prompt_uses_game_specific_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】雨天中止で先発予定だった田中将大は16日にスライド登板",
            summary="巨人田中将大投手が雨天中止にともなってスライド登板することになった。16日の同戦にスライドすることになった。",
            category="試合速報",
            source_fact_block="・雨天中止にともなってスライド登板\n・16日の同戦にスライド",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
            source_day_label="4月16日",
        )

        self.assertIn("【変更情報の要旨】", prompt)
        self.assertIn("【具体的な変更内容】", prompt)
        self.assertIn("【この変更が意味すること】", prompt)
        self.assertIn("ですます調、350〜650文字", prompt)
        self.assertIn("4月16日時点の情報であることが伝わるように書く", prompt)


if __name__ == "__main__":
    unittest.main()
