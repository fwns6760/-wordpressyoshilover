import unittest
from unittest.mock import patch

from src import rss_fetcher


class GeminiPromptTests(unittest.TestCase):
    def assert_common_strict_intro(self, prompt: str):
        self.assertIn("以下の『使ってよい事実』に書かれた情報を材料に、巨人ファン向けに本文を書いてください。", prompt)
        self.assertIn("『使ってよい事実』の範囲にある事実は自由に書いてよい", prompt)
        self.assertIn("そこに無い数字、選手名、比較、結果予想、推測、創作、誇張は書かないでください。", prompt)
        self.assertIn("source にある事実に基づく解釈と、巨人ファンとしての短い感想は、後述の「事実 → 解釈 → 感想」の流れで必ず書いてください。", prompt)
        self.assertIn("文章は「事実 → 解釈 → 感想」の順で流し、感想だけを先に書かない。", prompt)
        self.assertIn("事実 → 解釈 → 感想", prompt)
        self.assertTrue(
            any(marker in prompt for marker in ("気になります", "注目です", "見たいところです", "と思います"))
        )
        self.assertIn("自由に書いてよい", prompt)
        self.assertTrue("結果予想" in prompt or "一般論" in prompt)
        self.assertNotIn("感想を足さない", prompt[:300])

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
            title="【巨人】グリフィンが先発見込み",
            summary="グリフィン投手が次回登板へ向けた調整段階にある。先発見込みとしてブルペンで投球練習を行った。",
            category="選手情報",
            source_fact_block="",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
            source_day_label="9月1日",
        )

        self.assertIn("グリフィン投手は読売ジャイアンツ所属である。", prompt)
        self.assertIn("200〜350文字", prompt)
        self.assertIn("本文の最初は必ず「（9月1日時点）」で始めてください。", prompt)
        self.assertIn("見出しは【ニュースの整理】と【次の注目】の2つのみです。", prompt)
        self.assertIn("投手は次回登板、野手は次の実戦出場、捕手は次の登録発表", prompt)
        self.assertIn("同じ事実を繰り返さないでください。", prompt)

    def test_notice_prompt_uses_public_notice_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】皆川岳飛が出場選手登録",
            summary="皆川岳飛外野手が4月16日に出場選手登録された。今季二軍で打率.261、2本塁打を記録している。",
            category="選手情報",
            source_fact_block="",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
            source_day_label="4月16日",
        )

        self.assertIn("皆川岳飛", prompt)
        self.assertIn("読売ジャイアンツ所属である。", prompt)
        self.assertIn("見出しは【公示の要旨】【対象選手の基本情報】【公示の背景】【今後の注目点】", prompt)
        self.assertIn("本文の最初は必ず「（4月16日時点）」で始めてください。", prompt)
        self.assertIn("選手名は見出し以外の本文にも必ず明記してください。", prompt)
        self.assertIn("公示の日付・区分", prompt)

    def test_recovery_prompt_uses_injury_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】坂本勇人が左ふくらはぎ肉離れで離脱",
            summary="坂本勇人内野手が左ふくらはぎ肉離れと診断された。復帰時期は未定で、リハビリを開始した。代役は泉口友汰が務める見通しだ。",
            category="選手情報",
            source_fact_block="",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
            source_day_label="4月16日",
        )

        self.assertIn("坂本勇人", prompt)
        self.assertIn("見出しは【故障・復帰の要旨】【故障の詳細】【リハビリ状況・復帰見通し】【チームへの影響と今後の注目点】", prompt)
        self.assertIn("部位・期間・診断名など医療関連情報は source にある表現を正確に引用してください。", prompt)
        self.assertIn("復帰時期の推測を足さない", prompt)
        self.assertIn("本文の最初は必ず「（4月16日時点）」で始めてください。", prompt)

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
        self.assert_common_strict_intro(prompt)
        self.assertIn("【発言の要旨】の1文目には「4月16日時点」を自然に入れてください。", prompt)
        self.assertIn("引用が2つ以上ある場合は、【発言内容】で2つまで並べて整理してください。", prompt)
        self.assertIn("【次の注目】は必ず「事実 → 解釈 → 感想」の順で流れを作る", prompt)
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
        self.assert_common_strict_intro(prompt)
        self.assertIn("【注目ポイント】は必ず「事実 → 解釈 → 感想」の順で流れを作る", prompt)
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
        self.assert_common_strict_intro(prompt)
        self.assertIn("【試合展開】は必ず「事実 → 解釈 → 感想」の順で流れを作る", prompt)
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
        self.assert_common_strict_intro(prompt)
        self.assertIn("【この変更が意味すること】は必ず「事実 → 解釈 → 感想」の順で流れを作る", prompt)
        self.assertIn("ですます調、350〜650文字", prompt)
        self.assertIn("4月16日時点の情報であることが伝わるように書く", prompt)

    def test_farm_prompt_uses_second_team_specific_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【二軍】巨人 4-1 ロッテ　ティマが2安打3打点、山城京平は3回1失点",
            summary="巨人二軍がロッテとの二軍戦に4-1で勝利した。ティマが2安打3打点を記録し、山城京平投手は3回1失点だった。",
            category="ドラフト・育成",
            source_fact_block="・巨人二軍がロッテとの二軍戦に4-1で勝利\n・ティマが2安打3打点\n・山城京平投手は3回1失点",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
        )

        self.assertIn("【二軍結果・活躍の要旨】", prompt)
        self.assertIn("【ファームのハイライト】", prompt)
        self.assertIn("【二軍個別選手成績】", prompt)
        self.assertIn("【一軍への示唆】", prompt)
        self.assert_common_strict_intro(prompt)
        self.assertIn("【一軍への示唆】は必ず「事実 → 解釈 → 感想」の順で流れを作る", prompt)
        self.assertIn("source にあるスコア 4-1 を必ず残してください。", prompt)
        self.assertIn("一軍記事と混同しないよう、「二軍」「ファーム」の文脈を明確にする", prompt)

    def test_farm_lineup_prompt_uses_second_team_lineup_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【二軍】巨人 vs DeNA 18:00試合開始　1番浅野、4番ティマでスタメン",
            summary="巨人二軍がDeNA戦のスタメンを発表した。1番浅野翔吾、4番ティマ、先発は西舘勇陽投手。",
            category="ドラフト・育成",
            source_fact_block="・巨人二軍がDeNA戦のスタメンを発表\n・1番浅野翔吾、4番ティマ\n・先発は西舘勇陽投手\n・18:00試合開始",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
        )

        self.assertIn("【二軍試合概要】", prompt)
        self.assertIn("【二軍スタメン一覧】", prompt)
        self.assertIn("【注目選手】", prompt)
        self.assert_common_strict_intro(prompt)
        self.assertIn("【注目選手】は必ず「事実 → 解釈 → 感想」の順で流れを作る", prompt)
        self.assertIn("一軍記事のような書き方をしない。二軍戦の並びであることを明確に書く", prompt)
        self.assertIn("数字、打順、選手名、球場名は source にある表記をそのまま残す", prompt)

    def test_social_news_prompt_uses_social_specific_structure(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="「彼が打ったらもっと打線が機能する」巨人・阿部監督、身ぶり手ぶりでダルベックを熱血指導",
            summary="スポーツ報知巨人班Xが、阿部監督が「彼が打ったらもっと打線が機能する」と話し、ダルベックを熱血指導したと伝えた。",
            category="首脳陣",
            source_fact_block="・阿部監督がダルベックを熱血指導した\n・元記事中の表現: 「彼が打ったらもっと打線が機能する」",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
            source_name="スポーツ報知巨人班X",
            source_type="social_news",
            tweet_url="https://twitter.com/hochi_giants/status/1",
            source_day_label="4月16日",
        )

        self.assertIn("【話題の要旨】", prompt)
        self.assertIn("【発信内容の要約】", prompt)
        self.assertIn("【文脈と背景】", prompt)
        self.assertIn("【ファンの関心ポイント】", prompt)
        self.assertIn("報知新聞 / スポーツ報知巨人班XのX投稿", prompt)
        self.assertIn("『』で1〜2か所だけ残しながら整理する", prompt)
        self.assertIn("発信元がマスコミ記者・報道アカウントなのか、本文冒頭で明確にする", prompt)
        self.assertIn("4月16日時点", prompt)
        self.assert_common_strict_intro(prompt)
        self.assertIn("【ファンの関心ポイント】は必ず「事実 → 解釈 → 感想」の順で流れを作る", prompt)

    def test_enhanced_player_quote_prompt_adds_anti_paraphrase_rules(self):
        with patch.dict("os.environ", {"ENABLE_ENHANCED_PROMPTS": "1"}, clear=False):
            prompt = rss_fetcher._build_gemini_strict_prompt(
                title="【巨人】田中将大「打線を線にしない」移籍後初の阪神戦へ",
                summary="田中将大が甲子園での登板へ向けて「打線を線にしない」と話した。試合前コメントの記事である。",
                category="選手情報",
                source_fact_block="",
                win_loss_hint="",
                has_game=False,
                real_reactions=[],
            )

        self.assertIn("どの場面に向けた言葉かを先に固定してください。", prompt)
        self.assertIn("巨人ファンが次に1つだけ確認したい具体点を必ず書いてください。", prompt)

    def test_enhanced_recovery_prompt_requires_precise_medical_scope(self):
        with patch.dict("os.environ", {"ENABLE_ENHANCED_PROMPTS": "1"}, clear=False):
            prompt = rss_fetcher._build_gemini_strict_prompt(
                title="【巨人】坂本勇人が左ふくらはぎ肉離れで離脱",
                summary="坂本勇人内野手が左ふくらはぎ肉離れと診断された。復帰時期は未定で、リハビリを開始した。代役は泉口友汰が務める見通しだ。",
                category="選手情報",
                source_fact_block="",
                win_loss_hint="",
                has_game=False,
                real_reactions=[],
            )

        self.assertIn("部位が空なら空のまま扱い", prompt)
        self.assertIn("『順調』『万全』などの断定を避け", prompt)

    def test_enhanced_notice_prompt_requires_timing_and_numbers(self):
        with patch.dict("os.environ", {"ENABLE_ENHANCED_PROMPTS": "1"}, clear=False):
            prompt = rss_fetcher._build_gemini_strict_prompt(
                title="【巨人】皆川岳飛が出場選手登録",
                summary="皆川岳飛外野手が4月16日に出場選手登録された。今季二軍で打率.261、2本塁打を記録している。",
                category="選手情報",
                source_fact_block="",
                win_loss_hint="",
                has_game=False,
                real_reactions=[],
            )

        self.assertIn("年齢・成績・試合数のどれかを必ず1つ残してください。", prompt)
        self.assertIn("日付や区分を優先してください。", prompt)

    def test_enhanced_manager_prompt_makes_next_focus_concrete(self):
        with patch.dict("os.environ", {"ENABLE_ENHANCED_PROMPTS": "1"}, clear=False):
            prompt = rss_fetcher._build_gemini_strict_prompt(
                title="阿部監督「結果残せば使います」「競争は続けます」",
                summary="阿部監督が起用方針について語った。",
                category="首脳陣",
                source_fact_block="・阿部監督が起用方針を説明した\n・元記事中の表現: 「結果残せば使います」",
                win_loss_hint="",
                has_game=False,
                real_reactions=[],
            )

        self.assertIn("巨人のスタメン・序列・継投・競争のどれを動かす話かを先に固定してください。", prompt)
        self.assertIn("見たい場面・数字・起用・登録・打席・登板のどれかを1つに絞ってください。", prompt)

    def test_enhanced_game_prompt_preserves_numbers_and_splits_sections(self):
        with patch.dict("os.environ", {"ENABLE_ENHANCED_PROMPTS": "1"}, clear=False):
            prompt = rss_fetcher._build_gemini_strict_prompt(
                title="【巨人】阪神に3-2で勝利　岡田が決勝打",
                summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。田中将大投手は7回2失点だった。",
                category="試合速報",
                source_fact_block="・巨人が阪神に3-2で勝利\n・岡田悠希の決勝打\n・田中将大投手は7回2失点",
                win_loss_hint="",
                has_game=True,
                real_reactions=[],
            )

        self.assertIn("固有情報を、抽象語に言い換えず残してください。", prompt)
        self.assertIn("片方は流れ、片方は数字に寄せてください。", prompt)

    def test_enhanced_farm_prompt_prevents_first_team_mixup(self):
        with patch.dict("os.environ", {"ENABLE_ENHANCED_PROMPTS": "1"}, clear=False):
            prompt = rss_fetcher._build_gemini_strict_prompt(
                title="【二軍】巨人 4-1 ロッテ　ティマが2安打3打点、山城京平は3回1失点",
                summary="巨人二軍がロッテとの二軍戦に4-1で勝利した。ティマが2安打3打点を記録し、山城京平投手は3回1失点だった。",
                category="ドラフト・育成",
                source_fact_block="・巨人二軍がロッテとの二軍戦に4-1で勝利\n・ティマが2安打3打点\n・山城京平投手は3回1失点",
                win_loss_hint="",
                has_game=True,
                real_reactions=[],
            )

        self.assertIn("安打数・打点・投球回・失点のどれかを必ず残してください。", prompt)
        self.assertIn("昇格断定を避けつつ", prompt)

    def test_enhanced_social_prompt_removes_sns_pollution_and_demands_context(self):
        with patch.dict("os.environ", {"ENABLE_ENHANCED_PROMPTS": "1"}, clear=False):
            prompt = rss_fetcher._build_gemini_strict_prompt(
                title="「彼が打ったらもっと打線が機能する」巨人・阿部監督、身ぶり手ぶりでダルベックを熱血指導",
                summary="スポーツ報知巨人班Xが、阿部監督が「彼が打ったらもっと打線が機能する」と話し、ダルベックを熱血指導したと伝えた。",
                category="首脳陣",
                source_fact_block="・阿部監督がダルベックを熱血指導した\n・元記事中の表現: 「彼が打ったらもっと打線が機能する」",
                win_loss_hint="",
                has_game=False,
                real_reactions=[],
                source_name="スポーツ報知巨人班X",
                source_type="social_news",
                tweet_url="https://twitter.com/hochi_giants/status/1",
            )

        self.assertIn("ハッシュタグ、URL、媒体名の繰り返し、宣伝文句、SNSの定型句は本文に残さないでください。", prompt)
        self.assertIn("ファンの温度感の言い換えだけで終えず", prompt)


if __name__ == "__main__":
    unittest.main()
