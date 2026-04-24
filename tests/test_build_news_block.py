import unittest
from unittest.mock import patch

from src import rss_fetcher
from src.media_xpost_selector import select_media_quotes


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
        self.assertIn("戸郷翔征投手が何を変えているのか整理します。", ai_body)
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

        self.assertIn("【この変更が意味すること】", ai_body)
        self.assertIn("反応を見ると", ai_body)
        self.assertIn("次の試合前の入り方をどう整えるか", ai_body)
        self.assertIn("阪神戦 / 甲子園の試合前情報として整理します。", ai_body)
        self.assertGreater(len(ai_body), 200)

    def test_social_quote_player_fallback_stays_on_quote_and_makes_source_clear(self):
        title = "【巨人】田中将大「打線を線にしない」甲子園の“申し子”が移籍後初の阪神戦で好投誓う"
        summary = (
            "スポーツ報知巨人班Xが、田中将大が「打線を線にしない」と話し、"
            "移籍後初の阪神戦へ向けて好投を誓ったと伝えた。"
        )

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            blocks, ai_body = rss_fetcher.build_news_block(
                title=title,
                summary=summary,
                url="https://twitter.com/hochi_giants/status/1",
                source_name="スポーツ報知巨人班X",
                category="選手情報",
                has_game=False,
            )

        self.assertIn("田中将大のコメントと試合前の論点を整理します。", ai_body)
        self.assertIn("「打線を線にしない」", ai_body)
        self.assertNotIn("フォームそのものより", ai_body)
        self.assertNotIn("投げ方を組み替えている", ai_body)
        self.assertIn("報知新聞 / スポーツ報知巨人班X", blocks)

    def test_lineup_article_fallback_uses_lineup_specific_structure(self):
        title = "【巨人】今日のスタメン発表　1番丸、4番岡田"
        summary = (
            "巨人が阪神戦のスタメンを発表した。"
            "1番に丸佳浩、4番に岡田悠希が入った。"
        )

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    _, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/post",
                        source_name="日刊スポーツ 巨人",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertIn("【試合概要】", ai_body)
        self.assertIn("【スタメン一覧】", ai_body)
        self.assertIn("【先発投手】", ai_body)
        self.assertIn("【注目ポイント】", ai_body)
        self.assertIn("巨人は阪神戦に臨みます。", ai_body)
        self.assertIn("まず見たいのは、この並びが初回の攻め方にどう出るかという点です。", ai_body)

    def test_farm_lineup_article_fallback_uses_separate_structure(self):
        title = "【二軍】巨人対DeNA 4番ショートでスタメン"
        summary = (
            "巨人の二軍スタメンが発表された。"
            "若手内野手が4番ショートに入った。"
        )

        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                _, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="ドラフト・育成",
                    has_game=True,
                )

        self.assertIn("【二軍試合概要】", ai_body)
        self.assertIn("【二軍スタメン一覧】", ai_body)
        self.assertIn("【注目選手】", ai_body)
        self.assertIn("巨人二軍はDeNA戦に臨みます。", ai_body)
        self.assertIn("若手内野手が4番ショートに入った。", ai_body)

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

        self.assertIn("【発言の要旨】", ai_body)
        self.assertIn("【発言内容】", ai_body)
        self.assertIn("【文脈と背景】", ai_body)
        self.assertIn("【次の注目】", ai_body)
        self.assertIn("阿部監督が「レギュラーは決まってません。結果残せば使います」と話した。", ai_body)
        self.assertIn("今回の発言の軸は「レギュラーは決まってません。結果残せば使います」という言葉です。", ai_body)
        self.assertIn("この話題は序列や競争をどう動かすか、という文脈で読む必要があります。", ai_body)
        self.assertIn("次に見たいのは、この発言が実際の序列や競争にどう出るかという点です。", ai_body)
        self.assertNotIn("整理すると、今回のニュースは3点です。", ai_body)

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
                blocks, ai_body = rss_fetcher.build_news_block(
                    title=title,
                    summary=summary,
                    url="https://example.com/post",
                    source_name="報知 巨人",
                    category="首脳陣",
                    has_game=False,
                )

        self.assertIn("反応を見ると、この発言の強さよりも、スタメンや起用が実際にどう動くかを見たい空気が強いです。", ai_body)
        self.assertIn('<h2>【発言の要旨】</h2>', blocks)
        self.assertIn('<h3>【発言内容】</h3>', blocks)
        self.assertIn('<h3>【文脈と背景】</h3>', blocks)
        self.assertIn('<h3>【次の注目】</h3>', blocks)

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

        self.assertIn("【試合結果】", ai_body)
        self.assertIn("【ハイライト】", ai_body)
        self.assertIn("【選手成績】", ai_body)
        self.assertIn("【試合展開】", ai_body)
        self.assertIn("巨人が阪神に3-2で勝利した。", ai_body)
        self.assertIn("次戦にどの流れを持ち込めるかまで見ていきたいです。", ai_body)

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

        self.assertLess(blocks.index("【変更情報の要旨】"), blocks.index("💬 ファンの声（Xより）"))

    def test_social_news_inserts_media_quote_after_summary_and_before_ai_body(self):
        media_quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/hochi_giants/status/1",
                "source_name": "スポーツ報知巨人班X",
            }
        )
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【話題の要旨】\n"
                    "スポーツ報知巨人班Xが阿部監督のコメントを伝えた。\n"
                    "【発信内容の要約】\n"
                    "原文のニュアンスを残しながら内容を整理する。\n"
                    "【文脈と背景】\n"
                    "試合後コメントとして出た投稿だった。\n"
                    "【ファンの関心ポイント】\n"
                    "次の起用にどうつながるかが焦点になる。"
                ),
            ):
                blocks, _ = rss_fetcher.build_news_block(
                    title="阿部監督が起用意図を説明",
                    summary="スポーツ報知巨人班Xが阿部監督のコメントを伝えた。",
                    url="https://twitter.com/hochi_giants/status/1",
                    source_name="スポーツ報知巨人班X",
                    category="首脳陣",
                    has_game=False,
                    source_type="social_news",
                    media_quotes=media_quotes,
                )

        self.assertIn("📌 関連ポスト", blocks)
        self.assertIn("https://twitter.com/hochi_giants/status/1", blocks)
        self.assertLess(blocks.index("📌 関連ポスト"), blocks.index("【話題の要旨】"))
        self.assertEqual(blocks.count("https://platform.twitter.com/widgets.js"), 1)

    def test_notice_article_renders_notice_media_quote_section(self):
        media_quotes = [
            {
                "url": "https://twitter.com/npb/status/1",
                "handle": "@npb",
                "section_label": "📌 公示ポスト",
                "match_reason": "composite",
                "match_score": 157,
            }
        ]
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, _ = rss_fetcher.build_news_block(
                    title="皆川岳飛、一軍登録 関連情報",
                    summary="巨人・皆川岳飛外野手が出場選手登録された。",
                    url="https://example.com/post",
                    source_name="スポニチ",
                    category="選手情報",
                    has_game=False,
                    source_type="news",
                    media_quotes=media_quotes,
                )

        self.assertIn("📌 公示ポスト", blocks)
        self.assertIn("https://twitter.com/npb/status/1", blocks)

    def test_notice_article_renders_two_media_quotes_in_order(self):
        media_quotes = [
            {
                "url": "https://twitter.com/npb/status/1",
                "handle": "@npb",
                "quote_account": "@npb",
                "source_name": "NPB公式X",
                "section_label": "📌 公示ポスト",
                "match_reason": "composite",
                "match_score": 157,
            },
            {
                "url": "https://twitter.com/TokyoGiants/status/2",
                "handle": "@TokyoGiants",
                "quote_account": "@TokyoGiants",
                "source_name": "巨人公式X",
                "section_label": "📌 公示ポスト",
                "match_reason": "composite",
                "match_score": 140,
            },
        ]
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, _ = rss_fetcher.build_news_block(
                    title="皆川岳飛、一軍登録 関連情報",
                    summary="巨人・皆川岳飛外野手が出場選手登録された。",
                    url="https://example.com/post",
                    source_name="スポニチ",
                    category="選手情報",
                    has_game=False,
                    source_type="news",
                    media_quotes=media_quotes,
                )

        self.assertIn("1. NPB公式X", blocks)
        self.assertIn("2. 巨人公式X", blocks)
        self.assertLess(blocks.index("https://twitter.com/npb/status/1"), blocks.index("https://twitter.com/TokyoGiants/status/2"))

    def test_manager_article_renders_manager_media_quote_section(self):
        media_quotes = [
            {
                "url": "https://twitter.com/hochi_giants/status/1",
                "handle": "@hochi_giants",
                "section_label": "📢 報道ポスト",
                "match_reason": "composite",
                "match_score": 145,
            }
        ]
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, _ = rss_fetcher.build_news_block(
                    title="阿部監督「彼が打ったらもっと打線が機能する」",
                    summary="スポーツ報知巨人班Xが阿部監督のコメントを伝えた。",
                    url="https://example.com/post",
                    source_name="スポーツ報知 巨人",
                    category="首脳陣",
                    has_game=False,
                    source_type="news",
                    media_quotes=media_quotes,
                )

        self.assertIn("📢 報道ポスト", blocks)
        self.assertIn("https://twitter.com/hochi_giants/status/1", blocks)

    def test_news_article_does_not_render_media_quote_section(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】則本昂大が先発へ",
                    summary="巨人則本昂大投手が先発に向けて調整した。",
                    url="https://example.com/post",
                    source_name="日刊スポーツ 巨人",
                    category="試合速報",
                    has_game=True,
                    source_type="news",
                    media_quotes=[],
                )

        self.assertNotIn("📌 関連ポスト", blocks)

    def test_social_media_quote_keeps_fan_reactions_at_tail(self):
        media_quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/TokyoGiants/status/1",
                "source_name": "巨人公式X",
            }
        )
        with patch.object(
            rss_fetcher,
            "fetch_fan_reactions_from_yahoo",
            return_value=[
                {"handle": "@gfan01", "text": "かなり楽しみ。", "url": "https://x.com/gfan01/status/1"},
            ],
        ):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, _ = rss_fetcher.build_news_block(
                    title="巨人4-3 試合の流れを分けたポイント",
                    summary="巨人公式Xが勝利を伝えた。",
                    url="https://twitter.com/TokyoGiants/status/1",
                    source_name="巨人公式X",
                    category="試合速報",
                    has_game=True,
                    source_type="social_news",
                    media_quotes=media_quotes,
                )

        self.assertLess(blocks.index("📌 関連ポスト"), blocks.index("【試合結果】"))
        self.assertLess(blocks.index("【試合展開】"), blocks.index("💬 ファンの声（Xより）"))
        self.assertIn("https://twitter.com/gfan01/status/1", blocks)

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

        self.assertLess(blocks.index("【変更情報の要旨】"), blocks.index("このニュース、どう見る？"))
        self.assertLess(blocks.index("【この変更が意味すること】"), blocks.index("先に予想を書く？"))
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

        self.assertIn("【変更情報の要旨】", ai_body)
        self.assertIn("【具体的な変更内容】", ai_body)
        self.assertIn("【この変更が意味すること】", ai_body)
        self.assertIn("元記事にある日程や先発情報を、そのまま押さえておきたい変更です。", ai_body)
        self.assertIn("結果予想より先に、この変更で次の試合前をどう迎えるかがポイントです。", ai_body)

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

        self.assertIn("戸郷翔征投手が何を変えているのか整理します。", ai_body)
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

    def test_offday_player_quote_routes_to_gemini(self):
        title = "【巨人】田中将大「打線を線にしない」移籍後初の阪神戦へ"
        summary = "田中将大が甲子園での登板へ向けて「打線を線にしない」と話した。"
        gemini_body = (
            "【ニュースの整理】\n"
            "田中将大投手が移籍後初の阪神戦に向けて「打線を線にしない」と話した。\n"
            "【次の注目】\n"
            "試合の入り方にこの意識がどう出るかに注目です。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "選手情報", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=gemini_body) as gemini_mock:
                    _, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/post",
                        source_name="スポーツ報知 巨人",
                        category="選手情報",
                        has_game=False,
                    )

        gemini_mock.assert_called_once()
        self.assertIn("田中将大投手", ai_body)

    def test_offday_player_status_routes_to_gemini(self):
        title = "【巨人】佐々木俊輔が登録抹消"
        summary = "2025年9月1日、佐々木俊輔外野手が出場選手登録を抹消された。9月11日以後でなければ再登録はできない。"
        gemini_body = (
            "【ニュースの整理】\n"
            "（9月1日時点）佐々木俊輔外野手が出場選手登録を抹消された。\n"
            "【次の注目】\n"
            "佐々木俊輔外野手の次の登録発表に注目です。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "選手情報", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=gemini_body) as gemini_mock:
                    _, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/post",
                        source_name="スポーツ報知 巨人",
                        category="選手情報",
                        has_game=False,
                        source_day_label="9月1日",
                    )

        gemini_mock.assert_called_once()
        self.assertIn("佐々木俊輔外野手", ai_body)

    def test_notice_like_column_routes_to_notice_template(self):
        title = "【巨人】皆川岳飛が初１軍合流「やってやろうという気持ち」"
        summary = "皆川岳飛が初１軍合流となり、試合前に抱負を語った。"
        gemini_body = (
            "【ニュースの整理】\n"
            "皆川岳飛が初１軍合流となった。\n"
            "【次の注目】\n"
            "次の出場機会でどこを見たいかに注目です。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=gemini_body) as gemini_mock:
                    _, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/minagawa",
                        source_name="スポーツ報知巨人班X",
                        category="コラム",
                        has_game=False,
                    )

        gemini_mock.assert_called_once()
        self.assertEqual(gemini_mock.call_args.args[2], "選手情報")
        self.assertIn("【公示の要旨】", ai_body)
        self.assertIn("【対象選手の基本情報】", ai_body)
        self.assertIn("【公示の背景】", ai_body)
        self.assertIn("【今後の注目点】", ai_body)
        self.assertIn("皆川岳飛が初１軍合流となり、試合前に抱負を語った。", ai_body)

    def test_recovery_like_column_routes_to_recovery_template(self):
        title = "【巨人】西舘勇陽がコンディション不良からの復帰へ向けてブルペン投球再開"
        summary = "西舘勇陽投手がコンディション不良からの復帰へ向けてブルペンで投球練習を再開した。"
        gemini_body = (
            "【ニュースの整理】\n"
            "西舘勇陽が復帰へ向けて調整している。\n"
            "【次の注目】\n"
            "今後の状態に注目です。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=gemini_body) as gemini_mock:
                    _, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/nishidate",
                        source_name="スポーツ報知巨人班X",
                        category="コラム",
                        has_game=False,
                    )

        gemini_mock.assert_called_once()
        self.assertEqual(gemini_mock.call_args.args[2], "選手情報")
        self.assertIn("【故障・復帰の要旨】", ai_body)
        self.assertIn("【故障の詳細】", ai_body)
        self.assertIn("【リハビリ状況・復帰見通し】", ai_body)
        self.assertIn("【チームへの影響と今後の注目点】", ai_body)
        self.assertIn("西舘勇陽投手がコンディション不良からの復帰へ向けてブルペンで投球練習を再開した。", ai_body)

    def test_farm_articles_route_to_gemini_even_in_low_cost_subset(self):
        title = "【二軍】巨人 3-1 ハヤテ（5回降雨コールド）"
        summary = "巨人が3-1で勝利し、若手が本塁打を放った。"
        gemini_body = (
            "【ニュースの整理】\n"
            "巨人二軍が3-1で勝利した。\n"
            "【次の注目】\n"
            "若手の打席内容を次も見たいところです。"
        )

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "gemini"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=gemini_body) as gemini_mock:
                    _, ai_body = rss_fetcher.build_news_block(
                        title=title,
                        summary=summary,
                        url="https://example.com/farm",
                        source_name="巨人公式X",
                        category="ドラフト・育成",
                        has_game=False,
                    )

        gemini_mock.assert_called_once()
        self.assertEqual(gemini_mock.call_args.args[2], "ドラフト・育成")
        self.assertIn("【二軍結果・活躍の要旨】", ai_body)
        self.assertIn("【ファームのハイライト】", ai_body)
        self.assertIn("【二軍個別選手成績】", ai_body)
        self.assertIn("【一軍への示唆】", ai_body)
        self.assertIn("巨人二軍の試合は3-1という結果でした。", ai_body)

    def test_source_links_render_multiple_references(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】今日のスタメン発表　1番丸、4番岡田",
                        summary="巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。",
                        url="https://example.com/post",
                        source_name="スポーツ報知 / 日刊スポーツ",
                        category="試合速報",
                        has_game=True,
                        source_links=[
                            {"name": "スポーツ報知", "url": "https://example.com/hochi"},
                            {"name": "日刊スポーツ", "url": "https://example.com/nikkan"},
                        ],
                    )

        self.assertIn("📰 参照元:", blocks)
        self.assertIn("https://example.com/hochi", blocks)
        self.assertIn("https://example.com/nikkan", blocks)

    def test_lineup_stats_table_renders_when_verified_rows_exist(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[
                {"order": "1", "position": "中", "name": "丸 佳浩", "avg": ".281", "hr": "3", "rbi": "12", "sb": "2"},
                {"order": "4", "position": "左", "name": "岡田 悠希", "avg": ".298", "hr": "5", "rbi": "18", "sb": "1"},
            ]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】今日のスタメン発表　1番丸、4番岡田",
                        summary="巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。",
                        url="https://example.com/post",
                        source_name="スポーツ報知",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertIn("📊 今日のスタメンデータ", blocks)
        self.assertIn("丸 佳浩", blocks)
        self.assertIn("12", blocks)

    def test_lineup_stats_and_watch_points_render_after_news_section(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[
                {"order": "1", "position": "中", "name": "丸 佳浩", "avg": ".281", "hr": "3", "rbi": "12", "sb": "2"},
                {"order": "2", "position": "右", "name": "佐々木 俊輔", "avg": ".265", "hr": "1", "rbi": "6", "sb": "3"},
                {"order": "4", "position": "左", "name": "岡田 悠希", "avg": ".298", "hr": "5", "rbi": "18", "sb": "1"},
                {"order": "8", "position": "捕", "name": "甲斐 拓也", "avg": ".240", "hr": "2", "rbi": "8", "sb": "0"},
                {"order": "9", "position": "投", "name": "井上 温大", "avg": ".000", "hr": "0", "rbi": "0", "sb": "0"},
            ]):
                with patch.object(
                    rss_fetcher,
                    "generate_article_with_gemini",
                    return_value=(
                        "【ニュースの整理】\n"
                        "巨人が阪神戦のスタメンを発表した。\n"
                        "【次の注目】\n"
                        "序盤の流れがポイントになる。"
                    ),
                ):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】今日のスタメン発表　1番丸、4番岡田",
                        summary="巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。",
                        url="https://example.com/post",
                        source_name="スポーツ報知",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertLess(blocks.index("【試合概要】"), blocks.index("📊 今日のスタメンデータ"))
        self.assertLess(blocks.index("📊 今日のスタメンデータ"), blocks.index("👀 スタメンの見どころ"))
        self.assertLess(blocks.index("👀 スタメンの見どころ"), blocks.index("このニュース、どう見る？"))
        self.assertIn("<li>1番丸 佳浩から4番岡田 悠希までの流れ。</li>", blocks)
        self.assertIn("<li>2番佐々木 俊輔がつなぎ、4番岡田 悠希で返せるか。</li>", blocks)
        self.assertIn("<li>捕手甲斐 拓也を含めた下位打線の入り。</li>", blocks)

    def test_postgame_result_summary_and_watch_points_render_after_news_section(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【ニュースの整理】\n"
                    "巨人が阪神に3-2で勝利した。\n"
                    "【試合のポイント】\n"
                    "終盤に岡田悠希の決勝打が飛び出した。\n"
                    "【次の注目】\n"
                    "この流れを次戦にもつなげたい。"
                ),
            ):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】阪神に3-2で勝利　岡田が決勝打",
                    summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
                    url="https://example.com/post",
                    source_name="スポーツ報知",
                    category="試合速報",
                    has_game=True,
                )

        self.assertLess(blocks.index("【試合結果】"), blocks.index("📊 今日の試合結果"))
        self.assertLess(blocks.index("📊 今日の試合結果"), blocks.index("👀 勝負の分岐点"))
        self.assertLess(blocks.index("👀 勝負の分岐点"), blocks.index("この試合、どう見る？"))
        self.assertIn("巨人勝利", blocks)
        self.assertIn("3-2", blocks)
        self.assertIn("阪神", blocks)
        self.assertIn("岡田悠希の決勝打が飛び出した", blocks)

    def test_postgame_cta_labels_are_contextual(self):
        with patch.object(
            rss_fetcher,
            "fetch_fan_reactions_from_yahoo",
            return_value=[
                {"handle": "@gfan01", "text": "今日は岡田が決めた。", "url": "https://x.com/gfan01/status/1"},
            ],
        ):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【ニュースの整理】\n"
                    "巨人が阪神に3-2で勝利した。\n"
                    "【試合のポイント】\n"
                    "終盤に岡田悠希の決勝打が飛び出した。\n"
                    "【次の注目】\n"
                    "この流れを次戦にもつなげたい。"
                ),
            ):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】阪神に3-2で勝利　岡田が決勝打",
                    summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
                    url="https://example.com/post",
                    source_name="スポーツ報知",
                    category="試合速報",
                    has_game=True,
                )

        self.assertIn("この試合、どう見る？", blocks)
        self.assertIn("勝負の分岐点は？", blocks)
        self.assertIn("今日のMVPは？", blocks)

    def test_featured_image_is_not_duplicated_inside_body(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(
                rss_fetcher,
                "generate_article_with_gemini",
                return_value=(
                    "【ニュースの整理】\n"
                    "巨人が阪神に3-2で勝利した。\n"
                    "【試合のポイント】\n"
                    "終盤に岡田悠希の決勝打が飛び出した。\n"
                    "【次の注目】\n"
                    "この流れを次戦にもつなげたい。"
                ),
            ):
                blocks, _ = rss_fetcher.build_news_block(
                    title="【巨人】阪神に3-2で勝利　岡田が決勝打",
                    summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
                    url="https://example.com/post",
                    source_name="スポーツ報知",
                    category="試合速報",
                    og_image_url="https://example.com/hero.jpg",
                    media_id=123,
                    extra_images=["https://example.com/extra.jpg"],
                    has_game=True,
                )

        self.assertNotIn("hero.jpg", blocks)
        self.assertNotIn("extra.jpg", blocks)
        self.assertNotIn("wp-block-image", blocks)


    def test_live_anchor_safe_fallback_uses_anchor_structure(self):
        body = rss_fetcher._build_game_safe_fallback(
            "【巨人】阪神戦 3回表終了時点 2-1",
            "3回表終了時点で巨人が阪神に2-1。岡本和真の適時打で先制し、山崎伊織が3回まで無失点で抑えている。",
            "live_anchor",
        )

        self.assertIn("【時点】", body)
        self.assertIn("節目", body)
        self.assertIn("【現在スコア】", body)
        self.assertIn("現在スコア", body)
        self.assertIn("【ファン視点】", body)
        self.assertIn("気になります", body)

    def test_fact_notice_safe_fallback_is_cautious_and_omits_cta(self):
        body = rss_fetcher._build_safe_article_fallback(
            title="【訂正】巨人戦の開始時刻を修正",
            summary="スポーツ報知が4月21日配信記事を訂正した。訂正元URLを追記した。",
            category="球団情報",
            has_game=False,
            source_name="スポーツ報知",
            tweet_url="https://example.com/correction",
            source_day_label="4月21日",
        )

        self.assertIn("【訂正の対象】", body)
        self.assertIn("【訂正内容】", body)
        self.assertIn("【訂正元】", body)
        self.assertIn("【お詫び / ファン視点】", body)
        self.assertIn("訂正", body)
        self.assertRegex(body, "確認中|確認できた範囲|現時点")
        self.assertNotIn("みなさんの意見はコメントで教えてください！", body)

    def test_live_anchor_cta_slots_render_inline(self):
        ai_body = """
【時点】
3回表終了時点という節目で、試合の流れを整理します。
【現在スコア】
現在スコアは阪神戦で2-1です。
【直近のプレー】
岡本和真の適時打で先制した。
【ファン視点】
この節目のあとに次の流れがどう動くかは気になります。
""".strip()

        with patch.object(rss_fetcher, "_detect_article_subtype", return_value="live_anchor"):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=ai_body):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】阪神戦 3回表終了時点 2-1",
                        summary="3回表終了時点で巨人が阪神に2-1。岡本和真の適時打で先制し、山崎伊織が3回まで無失点で抑えている。",
                        url="https://example.com/live-anchor",
                        source_name="スポーツ報知",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertEqual(blocks.count('href="#respond"'), 3)
        self.assertLess(blocks.index("【時点】"), blocks.index("このニュース、どう見る？"))
        self.assertLess(blocks.index("このニュース、どう見る？"), blocks.index("【現在スコア】"))
        self.assertLess(blocks.index("【ファン視点】"), blocks.index("先に予想を書く？"))

    def test_fact_notice_blocks_omit_comment_cta(self):
        with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
            with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                blocks, ai_body = rss_fetcher.build_news_block(
                    title="【訂正】巨人戦の開始時刻を修正",
                    summary="スポーツ報知が4月21日配信記事を訂正した。訂正元URLを追記した。",
                    url="https://example.com/correction",
                    source_name="スポーツ報知",
                    category="球団情報",
                    has_game=False,
                )

        self.assertIn("【訂正の対象】", ai_body)
        self.assertEqual(blocks.count('href="#respond"'), 0)
        self.assertNotIn("みなさんの意見はコメントで教えてください！", ai_body)

    def test_existing_safe_fallback_outputs_remain_unchanged(self):
        self.assertEqual(
            rss_fetcher._build_game_safe_fallback(
                "【巨人】雨天中止で先発予定だった田中将大は16日にスライド登板 村田善則コーチ明かす",
                "巨人田中将大投手が雨天中止にともなってスライド登板することになった。先発予定だった15日の阪神戦（甲子園）が雨天中止となり、16日の同戦にスライドすることになった。村田善則バッテリーチーフコーチは「明日はスライドでいってもらいます」と話した。",
                "pregame",
            ),
            """
【変更情報の要旨】
巨人田中将大投手が雨天中止にともなってスライド登板することになった。
阪神戦 / 甲子園の試合前情報として整理します。
【具体的な変更内容】
先発予定だった15日の阪神戦（甲子園）が雨天中止となり、16日の同戦にスライドすることになった。
村田善則バッテリーチーフコーチは「明日はスライドでいってもらいます」と話した。
【この変更が意味すること】
結果予想より先に、この変更で次の試合前をどう迎えるかがポイントです。
変更の意味は実際の入り方にどう出るかで見えてきます。みなさんの意見はコメントで教えてください！
""".strip(),
        )
        self.assertEqual(
            rss_fetcher._build_game_safe_fallback(
                "【巨人】阪神に3-2で勝利　岡田が決勝打",
                "巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。田中将大投手は7回2失点だった。",
                "postgame",
            ),
            """
【試合結果】
巨人が阪神に3-2で勝利した。
阪神戦の勝敗とスコアを最初に押さえると、試合全体の見え方が揃います。
【ハイライト】
終盤に岡田悠希の決勝打が飛び出した。
決勝打や好投など、勝敗を動かした場面を先に追うと試合の芯が見えやすくなります。
【選手成績】
田中将大投手は7回2失点だった。
【試合展開】
田中将大投手は7回2失点だった。
次戦にどの流れを持ち込めるかまで見ていきたいです。みなさんの意見はコメントで教えてください！
""".strip(),
        )
        self.assertEqual(
            rss_fetcher._build_farm_safe_fallback(
                "【巨人2軍】日本ハムに4-2で勝利　浅野が2安打1打点",
                "巨人2軍が日本ハムに4-2で勝利した。浅野翔吾が2安打1打点を記録した。先発の京本眞投手は5回1失点だった。",
            ),
            """
【二軍結果・活躍の要旨】
巨人二軍の試合は4-2という結果でした。
巨人2軍が日本ハムに4-2で勝利した。
浅野翔吾が2安打1打点を記録した。
【ファームのハイライト】
先発の京本眞投手は5回1失点だった。
ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。
【二軍個別選手成績】
巨人2軍が日本ハムに4-2で勝利した。
浅野翔吾が2安打1打点を記録した。
【一軍への示唆】
二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。
次にどんな数字を積み上げるかまで追っていきたいです。みなさんの意見はコメントで教えてください！
""".strip(),
        )
        self.assertEqual(
            rss_fetcher._build_safe_article_fallback(
                "【巨人】3回表終了時点で阪神に2-1　岡本和真が先制打",
                "3回表終了時点で巨人が阪神に2-1。岡本和真の適時打で先制し、山崎伊織が3回まで無失点で抑えている。",
                "試合速報",
                True,
            ),
            """
【ニュースの整理】
まずは今のスコアと流れが動いた場面を整理します。
3回表終了時点で巨人が阪神に2-1。
岡本和真の適時打で先制し、山崎伊織が3回まで無失点で抑えている。
【試合のポイント】
途中経過では、いまのスコアより先に流れがどこで動いたかを見るのが大事です。
岡本和真の適時打で先制し、山崎伊織が3回まで無失点で抑えている。この場面が、いまの試合の空気を左右しています。
【次の注目】
ここから同点・勝ち越し・継投のどこが次に動くかが見どころです。
途中経過の記事で大事なのは、スコアそのものより流れがどこで変わったかです。ここから次にどこを見るか、コメントで教えてください！
""".strip(),
        )


if __name__ == "__main__":
    unittest.main()
