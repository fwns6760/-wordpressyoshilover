import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from src import x_post_generator


class XPostGeneratorTests(unittest.TestCase):
    @staticmethod
    def _weighted_length(text: str, url: str) -> int:
        return len(text.replace(url, "x" * 23))

    def test_pregame_post_uses_explicit_article_subtype(self):
        url = "https://yoshilover.com/62030"
        text = x_post_generator.build_post(
            title="巨人ヤクルト戦 プレビュー",
            url=url,
            category="試合速報",
            summary="神宮18:00試合開始。先発は戸郷翔征で、序盤の入りが注目される。",
            article_subtype="pregame",
        )

        self.assertIn("巨人ヤクルト戦 神宮18:00開始。", text)
        self.assertIn("先発は戸郷翔征。立ち上がりから注目です。", text)
        self.assertIn("今日はどこを見る?", text)

    def test_pregame_post_falls_back_from_title_and_summary(self):
        url = "https://yoshilover.com/62031"
        text = x_post_generator.build_post(
            title="巨人ヤクルト戦 神宮18時開始",
            url=url,
            category="試合速報",
            summary="予告先発は戸郷翔征。試合前の材料がそろってきた。",
        )

        self.assertIn("巨人ヤクルト戦 神宮18時開始。", text)
        self.assertIn("先発は戸郷翔征。立ち上がりから注目です。", text)
        self.assertIn("今日はどこを見る?", text)

    def test_notice_post_uses_explicit_article_subtype(self):
        url = "https://yoshilover.com/62032"
        text = x_post_generator.build_post(
            title="浅野翔吾が一軍登録へ",
            url=url,
            category="選手情報",
            summary="浅野翔吾外野手が一軍登録され、出番増も期待される。",
            article_subtype="notice",
        )

        self.assertIn("浅野翔吾が一軍登録。", text)
        self.assertIn("ここから出番が増えるかも気になります。", text)
        self.assertIn("この動き、どう見ますか？", text)
        self.assertIn("#巨人 #ジャイアンツ #浅野翔吾", text)

    def test_notice_post_falls_back_from_notice_keywords(self):
        url = "https://yoshilover.com/62033"
        text = x_post_generator.build_post(
            title="【巨人】浅野翔吾が出場選手登録",
            url=url,
            category="選手情報",
            summary="公示で浅野翔吾外野手の出場選手登録が発表された。",
        )

        self.assertIn("浅野翔吾が一軍登録。", text)
        self.assertIn("ここから出番が増えるかも気になります。", text)

    def test_recovery_post_uses_explicit_article_subtype(self):
        url = "https://yoshilover.com/62034"
        text = x_post_generator.build_post(
            title="西舘勇陽が復帰へ前進",
            url=url,
            category="選手情報",
            summary="西舘勇陽投手がブルペン再開。実戦復帰へ向けて段階を上げている。",
            article_subtype="recovery",
        )

        self.assertIn("西舘勇陽が復帰へ前進。", text)
        self.assertIn("ブルペン段階まで戻ってきたのは前進です。", text)
        self.assertIn("一軍復帰、いつがいいと思いますか？", text)

    def test_recovery_post_falls_back_from_recovery_keywords(self):
        url = "https://yoshilover.com/62035"
        text = x_post_generator.build_post(
            title="【巨人】西舘勇陽が実戦復帰へ",
            url=url,
            category="選手情報",
            summary="コンディション不良からの復帰へ向けて二軍での状態確認が続く。",
        )

        self.assertIn("西舘勇陽が復帰へ前進。", text)
        self.assertIn("実戦復帰まで段階が進んできました。", text)

    def test_social_news_post_uses_explicit_source_type_and_subtype(self):
        url = "https://yoshilover.com/62036"
        text = x_post_generator.build_post(
            title="阿部監督が若手起用を説明",
            url=url,
            category="首脳陣",
            summary="スポーツ報知巨人班Xが阿部監督について報じている。",
            article_subtype="social",
            source_type="social_news",
            source_name="スポーツ報知巨人班X",
        )

        self.assertIn("報知が阿部慎之助について報じています。", text)
        self.assertIn("ベンチの狙いがどう見えるか、気になる話題です。", text)
        self.assertIn("巨人ファン的にはどう見る?", text)
        self.assertIn("#巨人 #ジャイアンツ #阿部慎之助", text)

    def test_social_news_post_falls_back_from_source_type(self):
        url = "https://yoshilover.com/62037"
        text = x_post_generator.build_post(
            title="巨人ヤクルト戦のスタメン発表",
            url=url,
            category="試合速報",
            summary="巨人公式Xがスタメンを伝えた。",
            source_type="social_news",
            source_name="巨人公式X",
        )

        self.assertIn("巨人公式が巨人ヤクルト戦のスタメン発表。", text)
        self.assertIn("試合前の空気が変わるポイントかもしれません。", text)
        self.assertIn("巨人ファン的にはどう見る?", text)

    def test_social_news_embed_html_does_not_change_output(self):
        params = dict(
            title="阿部監督が若手起用を説明",
            url="https://yoshilover.com/62037-social",
            category="首脳陣",
            summary="スポーツ報知巨人班Xが阿部監督について報じている。",
            article_subtype="social",
            source_type="social_news",
            source_name="スポーツ報知巨人班X",
        )
        without_embed = x_post_generator.build_post(**params, content_html="<p>阿部監督の発言要旨。</p>")
        with_embed = x_post_generator.build_post(
            **params,
            content_html=(
                "<p>阿部監督の発言要旨。</p>"
                "<div>📌関連ポスト</div>"
                "<blockquote class=\"twitter-tweet\">...</blockquote>"
            ),
        )

        self.assertEqual(without_embed, with_embed)

    def test_notice_embed_html_does_not_change_output(self):
        params = dict(
            title="【巨人】浅野翔吾が出場選手登録",
            url="https://yoshilover.com/62037-notice",
            category="選手情報",
            summary="公示で浅野翔吾外野手の出場選手登録が発表された。",
            article_subtype="notice",
        )
        without_embed = x_post_generator.build_post(**params, content_html="<p>公示内容の整理。</p>")
        with_embed = x_post_generator.build_post(
            **params,
            content_html=(
                "<p>公示内容の整理。</p>"
                "<div>📌公示ポスト</div>"
                "<blockquote class=\"twitter-tweet\">...</blockquote>"
            ),
        )

        self.assertEqual(without_embed, with_embed)

    def test_manager_embed_html_does_not_change_output(self):
        params = dict(
            title="【巨人】阿部監督が継投の意図を説明",
            url="https://yoshilover.com/62037-manager",
            category="首脳陣",
            summary="阿部監督が継投と代打の判断について説明した。次の采配にも視線が集まる。",
        )
        without_embed = x_post_generator.build_post(**params, content_html="<p>ベンチワークの要点。</p>")
        with_embed = x_post_generator.build_post(
            **params,
            content_html=(
                "<p>ベンチワークの要点。</p>"
                "<div>📢報道ポスト</div>"
                "<blockquote class=\"twitter-tweet\">...</blockquote>"
            ),
        )

        self.assertEqual(without_embed, with_embed)

    def test_explicit_lineup_subtype_keeps_existing_branch(self):
        text = x_post_generator.build_post(
            title="巨人ヤクルト戦 先発メンバー",
            url="https://yoshilover.com/62038",
            category="試合速報",
            summary="1番 丸佳浩 打率.281 3本 12打点 2盗塁 4番 岡田悠希 打率.298 5本 18打点 1盗塁",
            article_subtype="lineup",
        )

        self.assertIn("1番丸佳浩 .281 3本 12打点 2盗塁", text)
        self.assertIn("この並び、どう見ますか？", text)

    def test_generated_post_text_stays_within_280_chars(self):
        url = "https://yoshilover.com/62039"
        text = x_post_generator.build_post(
            title="巨人ヤクルト戦 神宮18時開始 予告先発は戸郷翔征で若手の起用も含めて気になる点が多いプレビュー",
            url=url,
            category="試合速報",
            summary="神宮18時開始。予告先発は戸郷翔征。若手の起用、スタメン、終盤のベンチワークまで見どころが多い。",
            article_subtype="pregame",
        )

        self.assertLessEqual(len(text.replace(url, "x" * 23)), 280)

    def test_specialized_posts_stay_within_280_chars_across_categories(self):
        cases = [
            (
                "pregame",
                dict(
                    title="巨人ヤクルト戦 神宮18時開始 予告先発と打順の注目点を全部盛り込んだかなり長い試合前プレビューで若手起用や終盤の継投まで気になるポイントを整理した版",
                    url="https://yoshilover.com/limit-pregame",
                    category="試合速報",
                    summary="神宮18時開始。予告先発は戸郷翔征。スタメンの並び、若手の起用、終盤のベンチワーク、守備位置の変化まで含めて見どころが多く、巨人ファンが試合前に確認しておきたい材料を長めに整理したプレビュー。",
                    article_subtype="pregame",
                ),
            ),
            (
                "postgame",
                dict(
                    title="【巨人】阪神に3-2で勝利した試合をかなり長めに振り返りながら決勝打や継投判断や序盤の攻防まで一気に整理した長文タイトル版",
                    url="https://yoshilover.com/limit-postgame",
                    category="試合速報",
                    summary="巨人が阪神に3-2で勝利。岡田悠希の決勝打、井上温大の粘投、終盤の継投判断、守備固めのタイミング、ベンチワークの狙いまで触れた長めの試合後要約で、それぞれの局面が勝敗にどう影響したかを丁寧にたどる。",
                    article_subtype="postgame",
                ),
            ),
            (
                "lineup",
                dict(
                    title="【巨人】今日のスタメン発表 1番丸 4番岡田 5番浅野と話題が多い打順を長めに整理したタイトル版",
                    url="https://yoshilover.com/limit-lineup",
                    category="試合速報",
                    summary="スタメンの並びだけでなく、前日からの変更点、左右のバランス、上位打線の組み方、下位打線の役割まで含めた長めの説明文。",
                    article_subtype="lineup",
                    content_html=(
                        "<table>"
                        "<tr><th>打順</th><th>位置</th><th>選手名</th><th>打率</th><th>本塁打</th><th>打点</th><th>盗塁</th></tr>"
                        "<tr><td>1</td><td>中</td><td>丸 佳浩</td><td>.281</td><td>3</td><td>12</td><td>2</td></tr>"
                        "<tr><td>4</td><td>左</td><td>岡田 悠希</td><td>.298</td><td>5</td><td>18</td><td>1</td></tr>"
                        "</table>"
                    ),
                ),
            ),
            (
                "manager",
                dict(
                    title="【巨人】阿部監督が継投と打順変更の意図をかなり詳しく説明し次の采配まで気になる長めタイトル版",
                    url="https://yoshilover.com/limit-manager",
                    category="首脳陣",
                    summary="阿部監督が継投の狙い、打順の組み替え、若手起用の意図、終盤の代打判断までをかなり詳しく説明した長めの要約で、次戦のベンチワークにもつながる論点が多い。",
                ),
            ),
            (
                "notice",
                dict(
                    title="【巨人】浅野翔吾が出場選手登録 公示の意味と今後の起用まで見たくなる長めタイトル版",
                    url="https://yoshilover.com/limit-notice",
                    category="選手情報",
                    summary="公示で浅野翔吾外野手の出場選手登録が発表され、打線の入れ替えや守備位置の選択肢、代打起用の幅まで考えたくなる長めの背景説明。",
                    article_subtype="notice",
                ),
            ),
            (
                "recovery",
                dict(
                    title="【巨人】西舘勇陽が復帰へ前進 実戦復帰までの過程と一軍復帰時期まで気になる長めタイトル版",
                    url="https://yoshilover.com/limit-recovery",
                    category="選手情報",
                    summary="西舘勇陽投手が実戦復帰へ向けて段階を上げており、二軍での状態確認、球数の増やし方、一軍ローテにどう戻すかまで考えたくなる長めの進捗整理。",
                    article_subtype="recovery",
                ),
            ),
            (
                "farm",
                dict(
                    title="【巨人2軍】浅野翔吾が昇格へ向けてマルチ安打 打席内容や一軍再合流のタイミングまで見たくなる長めタイトル版",
                    url="https://yoshilover.com/limit-farm",
                    category="ドラフト・育成",
                    summary="巨人2軍の浅野翔吾外野手がマルチ安打を記録し、打席内容や対応力、守備位置、ここから一軍にどう戻していくかまで含めて見たくなる長めの要約。",
                ),
            ),
            (
                "social",
                dict(
                    title="阿部監督が若手起用を説明し今後のベンチワークまで考えたくなる長めタイトル版",
                    url="https://yoshilover.com/limit-social",
                    category="首脳陣",
                    summary="スポーツ報知巨人班Xが阿部監督の若手起用について詳しく報じており、ベンチの意図や今後の序列、次戦へのつながりまで考えたくなる長めの説明。",
                    article_subtype="social",
                    source_type="social_news",
                    source_name="スポーツ報知巨人班X",
                ),
            ),
        ]

        for name, kwargs in cases:
            with self.subTest(name=name):
                text = x_post_generator.build_post(**kwargs)
                self.assertLessEqual(self._weighted_length(text, kwargs["url"]), 280)

    def test_finalize_post_text_reduces_optional_hashtags_but_keeps_required_tags(self):
        url = "https://yoshilover.com/limit-tags"
        hashtags = ["#巨人", "#ジャイアンツ", "#戸郷翔征", "#プロ野球"]
        text = "あ" * 420 + f"\n\n{url}\n{' '.join(hashtags)}"

        finalized = x_post_generator._finalize_post_text(text, url, hashtags)

        self.assertLessEqual(self._weighted_length(finalized, url), 280)
        self.assertIn("#巨人 #ジャイアンツ", finalized)
        self.assertNotIn("#戸郷翔征", finalized)
        self.assertNotIn("#プロ野球", finalized)

    def test_ai_grok_mode_calls_grok_generator(self):
        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "grok", "X_POST_AI_CATEGORIES": "試合速報"},
            clear=False,
        ):
            with patch.object(x_post_generator, "generate_with_grok", return_value="Grok generated") as grok_mock:
                with patch.object(x_post_generator, "generate_with_gemini", return_value="Gemini generated") as gemini_mock:
                    text = x_post_generator.build_post(
                        title="巨人3-2阪神 テスト",
                        url="https://yoshilover.com/ai-grok",
                        category="試合速報",
                        summary="終盤の勝負どころを整理した。",
                    )

        grok_mock.assert_called_once()
        gemini_mock.assert_not_called()
        self.assertIn("Grok generated", text)

    def test_ai_gemini_mode_calls_gemini_generator(self):
        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "gemini", "X_POST_AI_CATEGORIES": "試合速報"},
            clear=False,
        ):
            with patch.object(x_post_generator, "generate_with_grok", return_value="Grok generated") as grok_mock:
                with patch.object(x_post_generator, "generate_with_gemini", return_value="Gemini generated") as gemini_mock:
                    text = x_post_generator.build_post(
                        title="巨人3-2阪神 テスト",
                        url="https://yoshilover.com/ai-gemini",
                        category="試合速報",
                        summary="終盤の勝負どころを整理した。",
                    )

        grok_mock.assert_not_called()
        gemini_mock.assert_called_once()
        self.assertIn("Gemini generated", text)

    def test_ai_auto_mode_falls_back_to_gemini_when_grok_returns_empty(self):
        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "auto", "X_POST_AI_CATEGORIES": "試合速報"},
            clear=False,
        ):
            with patch.object(x_post_generator, "generate_with_grok", return_value="") as grok_mock:
                with patch.object(x_post_generator, "generate_with_gemini", return_value="Gemini fallback generated") as gemini_mock:
                    text = x_post_generator.build_post(
                        title="巨人3-2阪神 テスト",
                        url="https://yoshilover.com/ai-auto",
                        category="試合速報",
                        summary="終盤の勝負どころを整理した。",
                    )

        grok_mock.assert_called_once()
        gemini_mock.assert_called_once()
        self.assertIn("Gemini fallback generated", text)

    def test_ai_generated_output_over_280_chars_is_trimmed(self):
        long_ai_text = "巨人の話題です。" * 80
        url = "https://yoshilover.com/ai-long"
        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "grok", "X_POST_AI_CATEGORIES": "試合速報"},
            clear=False,
        ):
            with patch.object(x_post_generator, "generate_with_grok", return_value=long_ai_text):
                text = x_post_generator.build_post(
                    title="巨人戦 長文AIテスト",
                    url=url,
                    category="試合速報",
                    summary="試合全体の流れを長文で説明するAI生成テスト。",
                )

        self.assertLessEqual(self._weighted_length(text, url), 280)
        self.assertIn("#巨人 #ジャイアンツ", text)
        self.assertNotIn("#プロ野球", text)
        self.assertNotIn("#セリーグ", text)

    def test_explicit_live_update_subtype_uses_live_update_builder(self):
        with patch.object(x_post_generator, "_build_live_update_post", return_value="live-update-route") as live_mock:
            text = x_post_generator.build_post(
                title="通常の試合メモ",
                url="https://yoshilover.com/live-route",
                category="試合速報",
                summary="通常文面だが synthetic live update 扱いで分岐させたい。",
                article_subtype="live_update",
            )

        live_mock.assert_called_once()
        self.assertEqual(text, "live-update-route")

    def test_cli_post_id_resolves_category_and_passes_context_to_build_post(self):
        fake_post = {
            "title": {"rendered": "【巨人】今日のスタメン発表"},
            "link": "https://yoshilover.com/post-id-lineup",
            "content": {"rendered": "<p>巨人がスタメンを発表した。</p>"},
            "categories": [5],
        }
        fake_categories = [
            {"id": 5, "name": "試合速報"},
        ]

        with patch.object(x_post_generator, "WPClient") as wp_mock:
            wp_mock.return_value.get_post.return_value = fake_post
            wp_mock.return_value.get_categories.return_value = fake_categories
            with patch.object(x_post_generator, "build_post", return_value="tweet-text") as build_mock:
                with patch("sys.argv", ["x_post_generator.py", "--post-id", "123"]):
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        x_post_generator.main()

        args, kwargs = build_mock.call_args
        self.assertEqual(args[:3], ("【巨人】今日のスタメン発表", "https://yoshilover.com/post-id-lineup", "試合速報"))
        self.assertEqual(kwargs["summary"], "巨人がスタメンを発表した。")
        self.assertEqual(kwargs["content_html"], "<p>巨人がスタメンを発表した。</p>")
        self.assertEqual(kwargs["article_subtype"], "")
        self.assertEqual(kwargs["source_type"], "news")

    def test_cli_post_id_uses_fallback_notice_detection_when_subtype_is_missing(self):
        fake_post = {
            "title": {"rendered": "【巨人】浅野翔吾が出場選手登録"},
            "link": "https://yoshilover.com/post-id-notice",
            "content": {"rendered": "<p>公示で浅野翔吾外野手の出場選手登録が発表された。</p>"},
            "categories": [8],
        }
        fake_categories = [
            {"id": 8, "name": "選手情報"},
        ]

        with patch.object(x_post_generator, "WPClient") as wp_mock:
            wp_mock.return_value.get_post.return_value = fake_post
            wp_mock.return_value.get_categories.return_value = fake_categories
            with patch("sys.argv", ["x_post_generator.py", "--post-id", "456"]):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    x_post_generator.main()

        output = stdout.getvalue()
        self.assertIn("浅野翔吾が一軍登録。", output)
        self.assertIn("ここから出番が増えるかも気になります。", output)
        self.assertIn("この動き、どう見ますか？", output)

    def test_player_post_uses_quote_angle_question_and_three_tags(self):
        text = x_post_generator.build_post(
            title="【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み",
            url="https://yoshilover.com/61897",
            category="選手情報",
            summary=(
                "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加し、心境を明かした。"
                "前日12日の2軍DeNA戦に先発して7回4安打1失点と好投した。"
            ),
        )

        self.assertIn("戸郷翔征「人の助言を取り入れることも重要」", text)
        self.assertIn("今回は結果より、フォーム変更の中身が気になる記事です。", text)
        self.assertIn("この変化、どう見ますか？", text)
        self.assertIn("https://yoshilover.com/61897", text)
        self.assertIn("#巨人 #ジャイアンツ #戸郷翔征", text)
        self.assertNotIn("#プロ野球", text)

    def test_player_post_without_quote_falls_back_to_player_led_copy(self):
        text = x_post_generator.build_post(
            title="【巨人】浅野翔吾が1軍昇格へ",
            url="https://yoshilover.com/62000",
            category="選手情報",
            summary="巨人の浅野翔吾外野手が1軍昇格に向けて準備を進めている。",
        )

        self.assertIn("浅野翔吾の今回の動き、気になります。", text)
        self.assertIn("今回の動き、今後の起用にも関わってきそうです。", text)
        self.assertIn("この流れ、どう見ますか？", text)
        self.assertIn("#巨人 #ジャイアンツ #浅野翔吾", text)

    def test_manager_post_uses_quote_angle_question_and_three_tags(self):
        text = x_post_generator.build_post(
            title="【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待",
            url="https://yoshilover.com/61903",
            category="首脳陣",
            summary="阿部監督が「レギュラーは決まってません。結果残せば使います」と話した。若手積極起用で競争を促す考えを示した。",
        )

        self.assertIn("阿部慎之助「レギュラーは決まってません。結果残せば使います」", text)
        self.assertIn("このコメント、次の序列にも関わってきそうです。", text)
        self.assertIn("この競争、どう見ますか？", text)
        self.assertIn("https://yoshilover.com/61903", text)
        self.assertIn("#巨人 #ジャイアンツ #阿部慎之助", text)
        self.assertNotIn("#プロ野球", text)

    def test_manager_post_lineup_variant_changes_question(self):
        text = x_post_generator.build_post(
            title="【巨人】阿部監督がスタメン起用の狙いを説明",
            url="https://yoshilover.com/62010",
            category="首脳陣",
            summary="阿部監督がスタメンと打順の組み方について説明した。次の起用にも注目が集まる。",
        )

        self.assertIn("この発言、次のスタメンをどう動かすか気になります。", text)
        self.assertIn("次のスタメン、どう変わると思いますか？", text)

    def test_manager_post_strategy_variant_changes_question(self):
        text = x_post_generator.build_post(
            title="【巨人】阿部監督が継投の意図を説明",
            url="https://yoshilover.com/62011",
            category="首脳陣",
            summary="阿部監督が継投と代打の判断について説明した。次の采配にも視線が集まる。",
        )

        self.assertIn("この発言、次のベンチワークをどう読むか気になります。", text)
        self.assertIn("この采配、どう見ますか？", text)

    def test_lineup_post_uses_verified_stat_rows_when_present(self):
        text = x_post_generator.build_post(
            title="【巨人】今日のスタメン発表 1番丸、4番岡田",
            url="https://yoshilover.com/62012",
            category="試合速報",
            summary=(
                "【今日のスタメンデータ】 "
                "1番 丸佳浩 打率.281 3本 12打点 2盗塁 "
                "4番 岡田悠希 打率.298 5本 18打点 1盗塁"
            ),
        )

        self.assertIn("1番丸佳浩 .281 3本 12打点 2盗塁", text)
        self.assertIn("4番岡田悠希 .298 5本 18打点 1盗塁", text)
        self.assertIn("この並び、どう見ますか？", text)
        self.assertIn("#巨人 #ジャイアンツ", text)

    def test_lineup_post_falls_back_when_stats_missing(self):
        text = x_post_generator.build_post(
            title="【巨人】今日のスタメン発表 1番丸、4番岡田",
            url="https://yoshilover.com/62013",
            category="試合速報",
            summary="巨人が阪神戦のスタメンを発表した。",
        )

        self.assertIn("今日の並び、どこが気になりますか？", text)

    def test_lineup_post_can_read_stats_from_article_html(self):
        text = x_post_generator.build_post(
            title="【巨人】今日のスタメン発表 1番丸、4番岡田",
            url="https://yoshilover.com/62014",
            category="試合速報",
            summary="巨人が阪神戦のスタメンを発表した。",
            content_html=(
                "<table>"
                "<tr><th>打順</th><th>位置</th><th>選手名</th><th>打率</th><th>本塁打</th><th>打点</th><th>盗塁</th></tr>"
                "<tr><td>1</td><td>中</td><td>丸 佳浩</td><td>.281</td><td>3</td><td>12</td><td>2</td></tr>"
                "<tr><td>4</td><td>左</td><td>岡田 悠希</td><td>.298</td><td>5</td><td>18</td><td>1</td></tr>"
                "</table>"
            ),
        )

        self.assertIn("1番丸 佳浩 .281 3本 12打点 2盗塁", text)
        self.assertIn("4番岡田 悠希 .298 5本 18打点 1盗塁", text)

    def test_postgame_post_uses_result_flow_and_question(self):
        text = x_post_generator.build_post(
            title="【巨人】今季２度目の０封負けで連敗　井上温大は６回２失点も打線が沈黙",
            url="https://yoshilover.com/61924",
            category="試合速報",
            summary=(
                "巨人はヤクルト投手陣を攻略できず、今季2度目の0封負けを喫した。"
                "先発井上温大投手は6回6安打2失点と粘投したが、打線の援護なく今季2敗目を喫した。"
            ),
        )

        self.assertIn("巨人、打線が沈黙して連敗。", text)
        self.assertIn("井上温大は試合を壊さず、勝敗を分けたのは攻撃でした。", text)
        self.assertIn("この試合の分岐点、どこでしたか？", text)
        self.assertIn("#巨人 #ジャイアンツ #井上温大", text)

    def test_postgame_post_win_variant_uses_endgame_angle(self):
        text = x_post_generator.build_post(
            title="【巨人】阪神に3-2で勝利　岡田が決勝打",
            url="https://yoshilover.com/62015",
            category="試合速報",
            summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
        )

        self.assertIn("巨人、競り勝って白星。", text)
        self.assertIn("岡田悠希の一打で流れが動き、終盤の勝負どころがはっきり出た試合でした。", text)
        self.assertIn("この試合の分岐点、どこでしたか？", text)
        self.assertIn("#巨人 #ジャイアンツ #岡田悠希", text)

    def test_live_update_post_uses_non_bot_like_flow_copy(self):
        text = x_post_generator.build_post(
            title="【巨人途中経過】6回表 巨人2-2阪神と同点",
            url="https://yoshilover.com/62020",
            category="試合速報",
            summary="巨人が6回表に2-2の同点に持ち込んだ。ここから次の1点が重い。",
        )

        self.assertIn("巨人、6回表に2-2の同点。", text)
        self.assertIn("次の1点をどちらが取るかです。", text)
        self.assertIn("この流れ、どう見ますか？", text)
        self.assertIn("#巨人 #ジャイアンツ", text)

    def test_farm_post_uses_player_and_promotion_angle(self):
        text = x_post_generator.build_post(
            title="【巨人2軍】浅野翔吾が昇格へ向けてマルチ安打",
            url="https://yoshilover.com/62021",
            category="ドラフト・育成",
            summary="巨人2軍の浅野翔吾外野手がマルチ安打を記録。昇格候補として注目が集まる。",
        )

        self.assertIn("浅野翔吾の2軍での動き、気になります。", text)
        self.assertIn("この動き、一軍の入れ替えにも関わってきそうです。", text)
        self.assertIn("次に上がるなら誰を見たいですか？", text)
        self.assertIn("#巨人 #ジャイアンツ #浅野翔吾", text)

    def test_data_obp_post_uses_top_five_tags_and_source_name(self):
        text = x_post_generator.build_post(
            title="巨人打線は打率だけで見ていいのか 出塁率で見ると泉口友汰が先頭に立つ",
            url="https://yoshilover.com/61939",
            category="コラム",
            summary="巨人の出塁率記事。",
            content_html=(
                "<table>"
                "<tr><th>順</th><th>選手</th><th>試合</th><th>打席</th><th>打率</th><th>出塁率</th><th>OPS</th></tr>"
                "<tr><td>1</td><td>泉口 友汰</td><td>14</td><td>57</td><td>.294</td><td>.368</td><td>.897</td></tr>"
                "<tr><td>2</td><td>ダルベック</td><td>13</td><td>52</td><td>.205</td><td>.327</td><td>.759</td></tr>"
                "<tr><td>3</td><td>キャベッジ</td><td>14</td><td>55</td><td>.309</td><td>.309</td><td>.836</td></tr>"
                "<tr><td>4</td><td>佐々木 俊輔</td><td>11</td><td>27</td><td>.296</td><td>.296</td><td>.777</td></tr>"
                "<tr><td>5</td><td>浦田 俊輔</td><td>11</td><td>38</td><td>.229</td><td>.289</td><td>.603</td></tr>"
                "<tr><td>10</td><td>坂本 勇人</td><td>10</td><td>29</td><td>.077</td><td>.172</td><td>.364</td></tr>"
                "</table>"
            ),
        )

        self.assertIn("阿部監督は打線をどう組むのか。", text)
        self.assertIn("出塁率上位5人", text)
        self.assertIn("泉口 友汰 .368", text)
        self.assertIn("浦田 俊輔 .289", text)
        self.assertIn("坂本勇人 10位 .172", text)
        self.assertIn("NPB調べ", text)
        self.assertIn("#巨人 #ジャイアンツ #泉口友汰 #ダルベック #キャベッジ #佐々木俊輔 #浦田俊輔", text)


if __name__ == "__main__":
    unittest.main()
