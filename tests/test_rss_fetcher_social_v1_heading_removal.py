import json
import logging
import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


SOCIAL_BODY = "\n".join(
    [
        "【話題の要旨】",
        "スポーツ報知巨人班Xが阿部監督のコメントを伝えた。",
        "【発信内容の要約】",
        "原文のニュアンスを残しながら内容を整理する。",
        "【文脈と背景】",
        "試合後コメントとして出た投稿だった。",
        "【ファンの関心ポイント】",
        "次の起用にどうつながるかが焦点になる。",
    ]
)

POSTGAME_BODY = "\n".join(
    [
        "【試合結果】",
        "巨人が阪神に3-2で勝利した。",
        "【ハイライト】",
        "岡本和真の決勝打で終盤に抜け出した。",
        "【選手成績】",
        "先発投手が7回2失点で試合を作った。",
        "【試合展開】",
        "終盤の一打が流れを決めた。",
    ]
)


class SocialV1HeadingRemovalTests(unittest.TestCase):
    def _build_social_blocks(self, flag_value: str, media_quotes: list[dict] | None = None):
        with patch.dict(
            os.environ,
            {"ENABLE_SOCIAL_V1_HEADING_REMOVAL": flag_value},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=SOCIAL_BODY):
                    return rss_fetcher.build_news_block(
                        title="阿部監督が起用意図を説明",
                        summary="スポーツ報知巨人班Xが阿部監督のコメントを伝えた。",
                        url="https://twitter.com/hochi_giants/status/1",
                        source_name="スポーツ報知巨人班X",
                        category="首脳陣",
                        has_game=False,
                        source_type="social_news",
                        media_quotes=media_quotes or [],
                    )

    def test_flag_off_keeps_existing_visible_heading(self):
        blocks, _ = self._build_social_blocks("0")

        self.assertIn("<h3>【発信内容の要約】</h3>", blocks)
        self.assertIn("<h3>【文脈と背景】</h3>", blocks)

    def test_flag_on_removes_summary_and_context_headings(self):
        blocks, _ = self._build_social_blocks("1")

        self.assertNotIn("<h3>【発信内容の要約】</h3>", blocks)
        self.assertNotIn("<h3>【文脈と背景】</h3>", blocks)
        self.assertIn("<h2>【話題の要旨】</h2>", blocks)
        self.assertIn("<h3>【ファンの関心ポイント】</h3>", blocks)

    def test_flag_on_preserves_source_block(self):
        media_quotes = [
            {
                "url": "https://twitter.com/hochi_giants/status/1",
                "handle": "@hochi_giants",
                "source_name": "スポーツ報知巨人班X",
                "section_label": "📌 関連ポスト",
            }
        ]

        blocks, _ = self._build_social_blocks("1", media_quotes=media_quotes)

        self.assertIn("📌 関連ポスト", blocks)
        self.assertIn("https://twitter.com/hochi_giants/status/1", blocks)
        self.assertIn("📰 参照元:", blocks)
        self.assertIn("スポーツ報知巨人班X", blocks)

    def test_flag_on_preserves_score_block(self):
        with patch.dict(
            os.environ,
            {"ENABLE_SOCIAL_V1_HEADING_REMOVAL": "1"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=POSTGAME_BODY):
                    blocks, _ = rss_fetcher.build_news_block(
                        title="【巨人】阪神に3-2で勝利　岡本和真が決勝打",
                        summary="巨人が阪神に3-2で勝利した。岡本和真が決勝打を放った。",
                        url="https://example.com/postgame",
                        source_name="スポーツ報知 巨人",
                        category="試合速報",
                        has_game=True,
                    )

        self.assertIn("📊 今日の試合結果", blocks)
        self.assertIn("3-2", blocks)
        self.assertIn("👀 勝負の分岐点", blocks)

    def test_flag_on_with_empty_result_falls_back_to_off(self):
        render_lines = [
            "【発信内容の要約】",
            "原文のニュアンスを残しながら内容を整理する。",
            "【文脈と背景】",
            "試合後コメントとして出た投稿だった。",
        ]

        with patch.dict(
            os.environ,
            {"ENABLE_SOCIAL_V1_HEADING_REMOVAL": "1"},
            clear=False,
        ):
            with self.assertLogs("rss_fetcher", level="INFO") as cm:
                filtered = rss_fetcher._maybe_remove_social_v1_visible_heading_lines(
                    render_lines,
                    body_category="選手情報",
                    has_game=False,
                    body_subtype="player_notice",
                    logger=logging.getLogger("rss_fetcher"),
                )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(filtered, render_lines)
        self.assertEqual(payload["event"], "social_v1_visible_heading_removed")
        self.assertEqual(payload["body_length_before"], payload["body_length_after"])

    def test_flag_on_emits_structured_log_with_metrics(self):
        render_lines = [
            "【話題の要旨】",
            "スポーツ報知巨人班Xが復帰状況を伝えた。",
            "【発信内容の要約】",
            "復帰までの見立てをまとめていた。",
            "【文脈と背景】",
            "二軍調整の進み具合にも触れていた。",
            "【ファンの関心ポイント】",
            "次の実戦復帰時期が焦点になる。",
        ]

        with patch.dict(
            os.environ,
            {"ENABLE_SOCIAL_V1_HEADING_REMOVAL": "1"},
            clear=False,
        ):
            with self.assertLogs("rss_fetcher", level="INFO") as cm:
                filtered = rss_fetcher._maybe_remove_social_v1_visible_heading_lines(
                    render_lines,
                    body_category="選手情報",
                    has_game=False,
                    body_subtype="player_recovery",
                    logger=logging.getLogger("rss_fetcher"),
                )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "social_v1_visible_heading_removed")
        self.assertEqual(payload["subtype"], "player_recovery")
        self.assertEqual(payload["removed_headings"], ["発信内容の要約", "文脈と背景"])
        self.assertLess(payload["body_length_after"], payload["body_length_before"])
        self.assertEqual(payload["severity"], "INFO")
        self.assertEqual(
            filtered,
            [
                "【話題の要旨】",
                "スポーツ報知巨人班Xが復帰状況を伝えた。",
                "【ファンの関心ポイント】",
                "次の実戦復帰時期が焦点になる。",
            ],
        )


if __name__ == "__main__":
    unittest.main()
