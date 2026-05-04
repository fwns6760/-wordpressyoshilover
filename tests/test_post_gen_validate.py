import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


class PostGenValidateTests(unittest.TestCase):
    def test_post_gen_validate_rejects_missing_close_marker(self):
        text = "\n".join(
            [
                "【ニュースの整理】",
                "巨人がスタメンを発表した。",
                "【次の注目】",
                "上位打線がどうつながるかを整理したい。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text)
        self.assertFalse(result["ok"])
        self.assertIn("close_marker", result["fail_axes"])

    def test_post_gen_validate_rejects_intro_echo(self):
        text = "\n".join(
            [
                "あなたは読売ジャイアンツ専門ブログの編集者です。",
                "【話題の要旨】",
                "阿部監督が選手起用について語った。",
                "【ファンの関心ポイント】",
                "ベンチの次の動きが気になります。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text)
        self.assertFalse(result["ok"])
        self.assertIn("intro_echo", result["fail_axes"])

    def test_post_gen_validate_accepts_clean_final_section_marker(self):
        text = "\n".join(
            [
                "【試合結果】",
                "巨人が3-2で競り勝った。",
                "【ハイライト】",
                "中軸の長打で流れを引き寄せた。",
                "【選手成績】",
                "先発が7回2失点だった。",
                "【試合展開】",
                "終盤の継投が次戦にもつながるか気になります。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text)
        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])
        self.assertEqual(result["final_section_heading"], "【試合展開】")

    def test_post_gen_validate_allows_lineup_without_close_marker(self):
        text = "\n".join(
            [
                "【試合概要】",
                "巨人が阪神戦のスタメンを発表した。",
                "【スタメン一覧】",
                "1番丸、4番岡本和。",
                "【先発投手】",
                "先発は戸郷翔征。",
                "【注目ポイント】",
                "スタメン発表の時点では、並びの意味をどう読むかが一番のポイントです。試合が始まって最初にどこを見るかまで、コメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="lineup")
        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])
        self.assertEqual(result["final_section_heading"], "【注目ポイント】")

    def test_post_gen_validate_keeps_close_marker_requirement_for_non_lineup_game_subtypes(self):
        text = "\n".join(
            [
                "【二軍試合概要】",
                "巨人二軍がDeNA戦のスタメンを発表した。",
                "【二軍スタメン一覧】",
                "1番浅野、4番ティマ。",
                "【注目選手】",
                "試合が始まったら、並びの意図がどこに出るかを見ていきたい。",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="farm_lineup")
        self.assertFalse(result["ok"])
        self.assertIn("close_marker", result["fail_axes"])

    def test_post_gen_validate_rejects_live_update_lineup_structure(self):
        text = "\n".join(
            [
                "【いま起きていること】",
                "7回表は巨人が3-2でリードしています。",
                "【流れが動いた場面】",
                "1番丸 2番泉口 3番吉川 4番岡本 5番甲斐と並べた打順表のまま試合が進んでいます。",
                "【次にどこを見るか】",
                "次の継投で流れが変わるか、みなさんの意見はコメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="live_update")
        self.assertFalse(result["ok"])
        self.assertIn("live_update_lineup_structure", result["fail_axes"])
        self.assertEqual(result["stop_reason"], "live_update_lineup_guard")

    def test_post_gen_validate_accepts_normal_live_update(self):
        text = "\n".join(
            [
                "【いま起きていること】",
                "7回表は巨人が3-2でリードし、4番手がマウンドに上がりました。",
                "【流れが動いた場面】",
                "6回に同点を許した直後、7回表に勝ち越し打が出て流れを引き戻しました。",
                "【次にどこを見るか】",
                "8回の継投でこの1点差をどう守るかが気になります。みなさんの意見はコメントで教えてください！",
            ]
        )
        result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="live_update")
        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])

    def test_post_gen_validate_rejects_starmen_title_prefix_for_non_lineup_subtypes(self):
        cases = [
            (
                "pregame",
                "巨人スタメン 雨天中止で先発変更をどう見るか",
                "\n".join(
                    [
                        "【変更情報の要旨】",
                        "雨天中止で先発変更になった。",
                        "【具体的な変更内容】",
                        "先発が翌日にスライドした。",
                        "【この変更が意味すること】",
                        "入り方がどう変わるか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
            (
                "postgame",
                "【巨人スタメン】阪神に3-2で勝利",
                "\n".join(
                    [
                        "【試合結果】",
                        "巨人が3-2で勝った。",
                        "【ハイライト】",
                        "終盤の決勝打が出た。",
                        "【選手成績】",
                        "先発が7回2失点だった。",
                        "【試合展開】",
                        "継投の切り替えがどう響いたか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
            (
                "farm",
                "巨人スタメン 二軍4-1勝利をどう見るか",
                "\n".join(
                    [
                        "【二軍結果・活躍の要旨】",
                        "巨人二軍が4-1で勝った。",
                        "【ファームのハイライト】",
                        "ティマが2安打3打点だった。",
                        "【二軍個別選手成績】",
                        "先発は3回1失点だった。",
                        "【一軍への示唆】",
                        "次の昇格争いがどう動くか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
            (
                "live_update",
                "巨人スタメン 7回表 3-2 途中経過",
                "\n".join(
                    [
                        "【いま起きていること】",
                        "7回表は巨人が3-2でリードしています。",
                        "【流れが動いた場面】",
                        "6回に同点を許したあと、7回に勝ち越しました。",
                        "【次にどこを見るか】",
                        "次の継投で流れがどう動くか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
        ]

        for article_subtype, title, text in cases:
            with self.subTest(article_subtype=article_subtype):
                result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype=article_subtype, title=title)
                self.assertFalse(result["ok"])
                self.assertIn("starmen_title_prefix", result["fail_axes"])
                self.assertEqual(result["stop_reason"], "starmen_prefix_guard")

    def test_post_gen_validate_rejects_starmen_h2_heading_prefix_for_non_lineup_subtypes(self):
        cases = [
            (
                "pregame",
                "\n".join(
                    [
                        "<h2>巨人スタメン 雨天中止で先発変更</h2>",
                        "変更点を整理する。",
                        "<h2>具体的な変更内容</h2>",
                        "先発が翌日にスライドした。",
                        "<h2>この変更が意味すること</h2>",
                        "入り方がどう変わるか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
            (
                "postgame",
                "\n".join(
                    [
                        "<h2>巨人スタメン 阪神に3-2で勝利</h2>",
                        "勝敗とスコアを整理する。",
                        "<h2>ハイライト</h2>",
                        "終盤の決勝打が出た。",
                        "<h2>選手成績</h2>",
                        "先発が7回2失点だった。",
                        "<h2>試合展開</h2>",
                        "継投の切り替えがどう響いたか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
            (
                "farm",
                "\n".join(
                    [
                        "<h2>巨人スタメン 二軍4-1勝利</h2>",
                        "結果を整理する。",
                        "<h2>ファームのハイライト</h2>",
                        "ティマが2安打3打点だった。",
                        "<h2>二軍個別選手成績</h2>",
                        "先発は3回1失点だった。",
                        "<h2>一軍への示唆</h2>",
                        "次の昇格争いがどう動くか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
            (
                "live_update",
                "\n".join(
                    [
                        "<h2>巨人スタメン 7回表 3-2</h2>",
                        "7回表は巨人が3-2でリードしています。",
                        "<h2>流れが動いた場面</h2>",
                        "6回に同点を許したあと、7回に勝ち越しました。",
                        "<h2>次にどこを見るか</h2>",
                        "次の継投で流れがどう動くか、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
        ]

        for article_subtype, text in cases:
            with self.subTest(article_subtype=article_subtype):
                result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype=article_subtype)
                self.assertFalse(result["ok"])
                self.assertIn("starmen_heading_prefix", result["fail_axes"])
                self.assertEqual(result["stop_reason"], "starmen_prefix_guard")

    def test_post_gen_validate_forbidden_phrase_guard_is_flagged_when_enabled(self):
        text = "\n".join(
            [
                "【話題の要旨】",
                "巨人の話題を整理する。",
                "【投稿で出ていた内容】",
                "投稿の主語と事実を押さえる。",
                "【この話が出た流れ】",
                "この表現は目を引きます。",
                "【ファンの関心ポイント】",
                "次の起用にどうつながるか気になります。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_FORBIDDEN_PHRASE_FILTER": "1"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="postgame")

        self.assertFalse(result["ok"])
        self.assertTrue(any(axis.startswith("forbidden_phrase:") for axis in result["fail_axes"]))

    def test_post_gen_validate_forbidden_phrase_guard_is_inactive_when_disabled(self):
        text = "\n".join(
            [
                "【話題の要旨】",
                "巨人の話題を整理する。",
                "【投稿で出ていた内容】",
                "投稿の主語と事実を押さえる。",
                "【この話が出た流れ】",
                "この表現は目を引きます。",
                "【ファンの関心ポイント】",
                "次の起用にどうつながるか気になります。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_FORBIDDEN_PHRASE_FILTER": "0"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="postgame")

        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])

    def test_post_gen_validate_placeholder_body_is_flagged_when_enabled(self):
        text = "\n".join(
            [
                "【話題の要旨】",
                "巨人の話題を整理する。",
                "【投稿で出ていた内容】",
                "",
                "【この話が出た流れ】",
                "元記事の内容を確認中です。",
                "【ファンの関心ポイント】",
                "次の起用にどうつながるか気になります。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_FORBIDDEN_PHRASE_FILTER": "1"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="postgame")

        self.assertFalse(result["ok"])
        self.assertTrue(any(axis.startswith("placeholder_body:") for axis in result["fail_axes"]))

    def test_post_gen_validate_quote_integrity_guard_rejects_unbalanced_quote(self):
        text = "\n".join(
            [
                "【発言の要旨】",
                "阿部監督が起用意図を説明した。",
                "【発言内容】",
                "阿部監督は「次も同じ形でいきたいと話した。",
                "【この話が出た流れ】",
                "直前の継投判断が焦点だった。",
                "【次の注目】",
                "次の継投で何を優先するか気になります。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_QUOTE_INTEGRITY_GUARD": "1"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="manager")

        self.assertFalse(result["ok"])
        self.assertTrue(any(axis.startswith("quote_integrity:") for axis in result["fail_axes"]))

    def test_post_gen_validate_duplicate_sentence_guard_rejects_near_duplicate(self):
        text = "\n".join(
            [
                "【試合結果】",
                "巨人が阪神に3-2で勝利した。",
                "【ハイライト】",
                "巨人が阪神に3-2で勝利した。",
                "【選手成績】",
                "戸郷翔征が7回1失点で試合を作った。",
                "【試合展開】",
                "終盤の継投がどう次戦につながるか気になります。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_DUPLICATE_SENTENCE_GUARD": "1"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype="postgame")

        self.assertFalse(result["ok"])
        self.assertTrue(any(axis.startswith("duplicate_sentence:") for axis in result["fail_axes"]))

    def test_post_gen_validate_active_team_mismatch_guard_rejects_non_giants_status_story(self):
        text = "\n".join(
            [
                "【故障・復帰の要旨】",
                "岡本和真の実戦復帰プランを整理する。",
                "【故障の詳細】",
                "状態の推移を確認する。",
                "【リハビリ状況・復帰見通し】",
                "復帰までの工程を追う。",
                "【チームへの影響と今後の注目点】",
                "どこで復帰するか気になります。",
            ]
        )
        source_refs = {
            "source_title": "ブルージェイズ・岡本和真が実戦復帰へ前進",
            "source_summary": "ブルージェイズでの実戦復帰プランが進んでいる。",
        }
        with patch.dict(os.environ, {"ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "1"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(
                text,
                article_subtype="player_recovery",
                source_refs=source_refs,
            )

        self.assertFalse(result["ok"])
        self.assertIn("entity_mismatch:non_giants_team_prefix", result["fail_axes"])

    def test_post_gen_validate_active_team_mismatch_guard_rejects_alumni_non_baseball_story(self):
        text = "\n".join(
            [
                "【ニュースの整理】",
                "上原浩治氏のコメントを整理する。",
                "【ここに注目】",
                "発言の要点を追う。",
                "【次の注目】",
                "この反応がどう広がるか気になります。",
            ]
        )
        source_refs = {
            "source_title": "元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ",
            "source_summary": "ラウンド中に息をするのも忘れるくらいだったとボクシング世界戦を語った。",
        }
        with patch.dict(os.environ, {"ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "1"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(
                text,
                article_subtype="general",
                source_refs=source_refs,
            )

        self.assertFalse(result["ok"])
        self.assertIn("entity_mismatch:alumni_non_baseball_context", result["fail_axes"])

    def test_post_gen_validate_quality_guards_allow_clean_example(self):
        text = "\n".join(
            [
                "【試合結果】",
                "巨人が阪神に3-2で競り勝った。",
                "【ハイライト】",
                "松浦慶斗が緊急リリーフで流れを切った。",
                "【選手成績】",
                "戸郷翔征が7回1失点、打線は11安打だった。",
                "【試合展開】",
                "終盤の継投が次戦でもどう使われるか気になります。",
            ]
        )
        source_refs = {
            "source_title": "巨人・松浦慶斗が緊急リリーフで流れを切る",
            "source_summary": "戸郷翔征が7回1失点、打線は11安打で3-2勝利。",
        }
        with patch.dict(
            os.environ,
            {
                "ENABLE_FORBIDDEN_PHRASE_FILTER": "1",
                "ENABLE_QUOTE_INTEGRITY_GUARD": "1",
                "ENABLE_DUPLICATE_SENTENCE_GUARD": "1",
                "ENABLE_ACTIVE_TEAM_MISMATCH_GUARD": "1",
            },
            clear=False,
        ):
            result = rss_fetcher._evaluate_post_gen_validate(
                text,
                article_subtype="postgame",
                source_refs=source_refs,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])

    def test_post_gen_validate_allows_starmen_prefix_for_lineup_and_farm_lineup(self):
        cases = [
            (
                "lineup",
                "巨人スタメン 1番丸 4番岡本",
                "\n".join(
                    [
                        "<h2>巨人スタメン 1番丸 4番岡本</h2>",
                        "並びの確認です。",
                        "【注目ポイント】",
                        "試合が始まって最初にどこを見るかまで、みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
            (
                "farm_lineup",
                "巨人スタメン 二軍 1番浅野 4番ティマ",
                "\n".join(
                    [
                        "<h2>巨人スタメン 二軍 1番浅野 4番ティマ</h2>",
                        "二軍の並びを整理します。",
                        "【注目選手】",
                        "若手がどう見せるかは見たいところです。みなさんの意見はコメントで教えてください！",
                    ]
                ),
            ),
        ]

        for article_subtype, title, text in cases:
            with self.subTest(article_subtype=article_subtype):
                result = rss_fetcher._evaluate_post_gen_validate(text, article_subtype=article_subtype, title=title)
                self.assertTrue(result["ok"])
                self.assertEqual(result["fail_axes"], [])


if __name__ == "__main__":
    unittest.main()
