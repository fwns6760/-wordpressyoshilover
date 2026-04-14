import unittest
from unittest.mock import patch

from src import rss_fetcher


class BuildNewsBlockTests(unittest.TestCase):
    def test_empty_ai_body_uses_safe_fallback_instead_of_repeating_summary(self):
        title = "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み"
        summary = (
            "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加し、心境を明かした。"
            "前日12日の2軍DeNA戦に先発して7回4安打1失点と好投した。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "選手情報", "ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    blocks, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/post",
                        source_name="日刊スポーツ 巨人",
                        category="選手情報",
                        has_game=False,
                    )

        self.assertIn("【ニュースの整理】", ai_body)
        self.assertIn("<h3>【ニュースの整理】</h3>", blocks)
        self.assertIn("戸郷翔征投手の現状を整理します。", ai_body)
        self.assertIn("<p>ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加し、心境を明かした。前日12日の2軍DeNA戦に先発して7回4安打1失点と好投した。</p>", blocks)
        self.assertIn("外からの助言を受け入れて投げ方を組み替えている", ai_body)
        self.assertNotIn("……", blocks)

    def test_safe_fallback_uses_fan_reaction_temperature_when_available(self):
        title = "【巨人】則本昂大、甲子園で12年ぶり先発「極力聞かないように」"
        summary = (
            "巨人則本昂大投手が甲子園での先発を前に調整した。"
            "登板予定だった前回は雨で流れたが、今回は改めて先発が見込まれている。"
            "野球少年時代から阪神ファンだったことも明かしている。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報", "ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(
                rss_fetcher,
                "fetch_fan_reactions_from_yahoo",
                return_value=[
                    {"handle": "@gfan01", "text": "甲子園での先発はかなり楽しみ。どう入るか注目したい。", "url": "https://x.com/gfan01/status/1"},
                    {"handle": "@gfan02", "text": "独特の空気でも自分の投球ができるか見たい。", "url": "https://x.com/gfan02/status/2"},
                ],
            ):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    _, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/post",
                        source_name="日刊スポーツ 巨人",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertIn("【次の注目】", ai_body)
        self.assertIn("反応を見ると", ai_body)
        self.assertIn("登板前ならではの緊張感", ai_body)
        self.assertIn("試合前の記事だからこそ", ai_body)
        self.assertGreater(len(ai_body), 320)

    def test_lineup_article_fallback_uses_lineup_specific_structure(self):
        title = "【巨人】今日のスタメン発表　1番丸、4番岡田"
        summary = (
            "巨人が阪神戦のスタメンを発表した。"
            "1番に丸佳浩、4番に岡田悠希が入った。"
        )

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                _, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="試合速報",
                    has_game=True,
                )

        self.assertIn("まずは今日のスタメンでどこが動いたかを整理します。", ai_body)
        self.assertIn("今日のスタメン記事で大事なのは、誰が入ったかだけでなく、打順や守備位置のどこが動いたかです。", ai_body)
        self.assertIn("試合前にまず見たいのは、この並びが初回からどう機能するか", ai_body)

    def test_manager_article_fallback_focuses_on_bench_intent(self):
        title = "【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待"
        summary = "阿部監督が「レギュラーは決まってません。結果残せば使います」と話した。若手積極起用で競争を促す考えを示した。"

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                _, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="報知 巨人",
                    category="首脳陣",
                    has_game=False,
                )

        self.assertIn("整理すると、今回のニュースは3点です。", ai_body)
        self.assertIn("まず、阿部監督が「レギュラーは決まってません。結果残せば使います」と話し、若手も含めて結果重視で競争を促す考えを出したことです。", ai_body)
        self.assertIn("次に「レギュラーは決まってません。結果残せば使います」という言葉が出たことで、起用を固定しない姿勢がはっきりしました。", ai_body)
        self.assertIn("そして、若手起用とセットで序列を動かす前提まで見えてきたのが今回の整理ポイントです。", ai_body)
        self.assertIn("レギュラー固定でいかないという意思表示にも見えます。", ai_body)
        self.assertIn("名前より結果で並びを動かす前提に見えてきます。", ai_body)
        self.assertIn("既存の序列も安泰ではないという空気が出ています。", ai_body)
        self.assertIn("次に見たいのは、この発言が実際のスタメンやベンチワークにどう出るかという点です。", ai_body)
        self.assertNotIn("結果残せば使います」と話した。", ai_body)

    def test_manager_article_reaction_line_is_summarized_not_raw_quotes(self):
        title = "【巨人】阿部監督が起用の狙いを説明"
        summary = "阿部監督がスタメン起用の意図について説明した。今後の起用方針にも触れた。"

        with patch.object(
            rss_fetcher,
            "fetch_fan_reactions_from_yahoo",
            return_value=[
                {"handle": "@gfan01", "text": "このコメントより次のスタメンがどう動くか気になる。", "url": "https://x.com/gfan01/status/1"},
            ],
        ):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                _, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="報知 巨人",
                    category="首脳陣",
                    has_game=False,
                )

        self.assertIn("次のスタメンや起用がどう動くかを見たい空気が強いです。", ai_body)

    def test_postgame_article_fallback_focuses_on_flow_and_next_game(self):
        title = "【巨人】阪神に3-2で勝利　岡田が決勝打"
        summary = "巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。"

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                _, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="報知 巨人",
                    category="試合速報",
                    has_game=True,
                )

        self.assertIn("結果だけを並べるより、どこで流れが動いたかを見ておきたい試合です。", ai_body)
        self.assertIn("次に見たいのは、この試合で出た手応えや課題が次戦にも続くのかという点です。", ai_body)

    def test_roster_article_fallback_focuses_on_fit_and_competition(self):
        title = "【巨人】新外国人右腕を獲得へ"
        summary = "巨人が新外国人右腕の獲得に動いている。先発陣の層を厚くする狙いがある。"

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                _, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="補強・移籍",
                    has_game=False,
                )

        self.assertIn("補強の話は名前より先に、チームのどこを埋める話なのかを整理します。", ai_body)
        self.assertIn("補強の話は名前のインパクトだけでは足りません。どこの穴を埋める話なのか、既存戦力とどうかみ合うかまで見ておきたいです。", ai_body)
        self.assertIn("次に見たいのは、この動きで一軍の競争や編成全体がどう変わるかという点です。", ai_body)

    def test_fan_reactions_with_urls_render_as_compact_x_embeds(self):
        with patch.object(
            rss_fetcher,
            "fetch_fan_reactions_from_yahoo",
            return_value=[
                {"handle": "@gfan01", "text": "かなり楽しみ。", "url": "https://x.com/gfan01/status/1"},
                {"handle": "@gfan02", "text": "内容に注目したい。", "url": "https://x.com/gfan02/status/2"},
            ],
        ):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】則本昂大が先発へ",
                    summary="巨人則本昂大投手が先発に向けて調整した。",
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="試合速報",
                    has_game=True,
                )

        self.assertIn("yoshilover-x-embed", blocks)
        self.assertIn("https://twitter.com/gfan01/status/1", blocks)
        self.assertIn("yoshilover-x-embed-compact", blocks)
        self.assertIn('data-conversation="none"', blocks)
        self.assertIn('data-cards="hidden"', blocks)
        self.assertIn('style="margin:0 auto 0 !important;max-width:550px;"', blocks)
        self.assertEqual(blocks.count("https://platform.twitter.com/widgets.js"), 1)
        self.assertNotIn("wp-embed-aspect-16-9", blocks)

    def test_news_section_renders_before_fan_reactions(self):
        with patch.object(
            rss_fetcher,
            "fetch_fan_reactions_from_yahoo",
            return_value=[
                {"handle": "@gfan01", "text": "かなり楽しみ。", "url": "https://x.com/gfan01/status/1"},
            ],
        ):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】則本昂大が先発へ",
                    summary="巨人則本昂大投手が先発に向けて調整した。",
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="試合速報",
                    has_game=True,
                )

        self.assertLess(blocks.index("【ニュースの整理】"), blocks.index("💬 ファンの声（Xより）"))

    def test_comment_cta_is_always_rendered_three_times_without_stats(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【ニュースの整理】\n"
                    "巨人の則本昂大投手が先発に向けて調整しました。\n"
                    "【試合のポイント】\n"
                    "甲子園での登板が焦点です。\n"
                    "【次の注目】\n"
                    "入り方がポイントになります。"
                ),
            ):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】則本昂大が先発へ",
                    summary="巨人則本昂大投手が先発に向けて調整した。",
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="試合速報",
                    has_game=True,
                )

        self.assertEqual(blocks.count('href="#respond"'), 3)
        self.assertIn("このニュース、どう見る？", blocks)
        self.assertIn("先に予想を書く？", blocks)
        self.assertIn("みんなの本音は？", blocks)
        self.assertLess(blocks.index("このニュース、どう見る？"), blocks.index("先に予想を書く？"))

    def test_comment_cta_stays_at_three_with_stats_block(self):
        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "選手情報", "ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(
                    rss_fetcher,
                    "generate_article_with_grok",
                    return_value=(
                        "【ニュースの整理】\n戸郷翔征投手が調整を続けています。\n【ここに注目】\n次回登板へ向けた状態です。\n【次の注目】\n実戦での内容が焦点です。",
                        [],
                        "",
                        "・投球回: 7回\n・失点: 1",
                        "",
                    ),
                ):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】戸郷翔征が調整",
                        summary="巨人の戸郷翔征投手が次回登板へ向けて調整を続けている。",
                        url="https://example.com/post",
                        source_name="日刊スポーツ 巨人",
                        category="選手情報",
                        has_game=False,
                        article_ai_mode_override="grok",
                    )

        self.assertEqual(blocks.count('href="#respond"'), 3)

    def test_comment_cta_positions_follow_news_next_and_fans_sections(self):
        with patch.object(
            rss_fetcher,
            "fetch_fan_reactions_from_yahoo",
            return_value=[
                {"handle": "@gfan01", "text": "かなり楽しみ。", "url": "https://x.com/gfan01/status/1"},
            ],
        ):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【ニュースの整理】\n"
                    "則本昂大投手が先発に向けて調整しました。\n"
                    "【試合のポイント】\n"
                    "甲子園の空気への入り方が焦点です。\n"
                    "【次の注目】\n"
                    "初回の立ち上がりに注目が集まります。"
                ),
            ):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】則本昂大が先発へ",
                    summary="巨人則本昂大投手が先発に向けて調整した。",
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="試合速報",
                    has_game=True,
                )

        self.assertLess(blocks.index("【ニュースの整理】"), blocks.index("このニュース、どう見る？"))
        self.assertLess(blocks.index("【次の注目】"), blocks.index("先に予想を書く？"))
        self.assertLess(blocks.index("💬 ファンの声（Xより）"), blocks.index("みんなの本音は？"))

    def test_editor_voice_rewrites_generic_phrases(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【ニュースの整理】\n"
                    "この試合で何が焦点だったのか、元記事の事実に沿って整理します。\n"
                    "【試合のポイント】\n"
                    "多くのファンが注目を集めていました。\n"
                    "【次の注目】\n"
                    "特別な意味を持つ一戦でした。"
                ),
            ):
                _, ai_body = rss_fetcher.build_news_block(
                    title="【巨人】則本昂大が先発へ",
                    summary="巨人則本昂大投手が先発に向けて調整した。",
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="試合速報",
                    has_game=True,
                )

        self.assertIn("巨人ファンが試合前から気にしていた論点", ai_body)
        self.assertIn("G党の視線が集まっていました", ai_body)
        self.assertIn("見え方が少し変わる一戦でした", ai_body)

    def test_editor_voice_softens_generic_player_language(self):
        raw = (
            "【ニュースの整理】\n"
            "戸郷のフォーム改造が注目されています。\n"
            "【ここに注目】\n"
            "外部からの視点や専門的なアドバイスを積極的に取り入れる姿勢が伺えます。\n"
            "【次の注目】\n"
            "重要なポイントとなります。"
        )

        rewritten = rss_fetcher._apply_editor_voice(raw, "選手情報", "戸郷翔征投手")

        self.assertIn("戸郷のフォーム改造に目が向きます。", rewritten)
        self.assertIn("姿勢が見えてきます。", rewritten)
        self.assertIn("見どころです。", rewritten)

    def test_generic_player_ai_text_falls_back_to_direct_safe_version(self):
        title = "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み"
        summary = (
            "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加し、心境を明かした。"
            "前日12日の2軍DeNA戦に先発して7回4安打1失点と好投した。"
        )

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【ニュースの整理】\n"
                    "戸郷翔征投手がフォーム変更に取り組んでいます。\n"
                    "【ここに注目】\n"
                    "期待の声が上がっています。重要な焦点となるでしょう。\n"
                    "【次の注目】\n"
                    "今後も継続してその効果を見極める必要があります。"
                ),
            ):
                _, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="選手情報",
                    has_game=False,
                )

        self.assertIn("戸郷翔征投手の現状を整理します。", ai_body)
        self.assertIn("外からの助言を受け入れて投げ方を組み替えている", ai_body)
        self.assertNotIn("今後も継続してその効果を見極める必要があります。", ai_body)

    def test_article_ai_mode_override_forces_grok_even_on_offday(self):
        title = "【巨人】戸郷翔征がフォーム改造に手応え"
        summary = "巨人の戸郷翔征投手がフォーム改造の現状について語った。次回登板へ向けて調整を続けている。"
        grok_body = (
            "■選手情報の整理\n"
            "戸郷翔征投手がフォーム改造の現状を語りました。\n"
            "【ニュースの整理】\n"
            "次回登板へ向けた調整が続いています。\n"
            "【ファン目線の注目点】\n"
            "実戦でどこまで戻せるか注目です。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "選手情報", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "none"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "generate_article_with_grok", return_value=(grok_body, [], "", "", "")) as grok_mock:
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value="Gemini本文") as gemini_mock:
                    with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                        blocks, ai_body = rss_fetcher.build_news_block(
                            title=title,
                            summary=summary,
                            url="https://example.com/post",
                            source_name="日刊スポーツ 巨人",
                            category="選手情報",
                            has_game=False,
                            article_ai_mode_override="grok",
                        )

        grok_mock.assert_called_once()
        gemini_mock.assert_not_called()
        self.assertIn("戸郷翔征投手がフォーム改造の現状を語りました。", ai_body)
        self.assertIn("<h3>【ニュースの整理】</h3>", blocks)
        self.assertIn("<h3>【次の注目】</h3>", blocks)


if __name__ == "__main__":
    unittest.main()
