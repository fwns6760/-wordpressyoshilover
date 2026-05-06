import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


class ShortSourceBodyShrinkRepairTests(unittest.TestCase):
    def test_flag_off_keeps_existing_long_social_body(self):
        body = "\n".join(
            [
                "【話題の要旨】",
                "球団投稿の概要を長めに整理する。",
                "【発信内容の要約】",
                "投稿内容を丁寧に言い換えながら、背景説明も重ねていく。",
                "さらに同じ論点を補足し、長文化した前提も整理していく。",
                "【文脈と背景】",
                "周辺事情を長く説明し、ここでも言い換えを重ねていく。",
                "まだ別の説明を続け、短い source から大きく膨らませていく。",
                "さらに別の観点からも補足し、元の投稿にない長いまとめ方を重ねていく。",
                "【ファンの関心ポイント】",
                "次にどうつながるかまで長く整理していきたい。",
            ]
        )

        repaired = rss_fetcher._maybe_apply_short_source_body_shrink_repair(
            body_text=body,
            title="球団投稿が話題",
            summary="スポーツ報知巨人班Xが新フォトブースを紹介した。",
            category="コラム",
            body_subtype="social_news",
            source_url="https://twitter.com/hochi_giants/status/1",
            source_name="スポーツ報知巨人班X",
            source_day_label="",
        )

        self.assertEqual(repaired, body)

    def test_flag_on_shrinks_long_social_body_to_short_template(self):
        body = "\n".join(
            [
                "【話題の要旨】",
                "球団投稿の概要を長めに整理する。",
                "【発信内容の要約】",
                "投稿内容を丁寧に言い換えながら、背景説明も重ねていく。",
                "さらに同じ論点を補足し、長文化した前提も整理していく。",
                "【文脈と背景】",
                "周辺事情を長く説明し、ここでも言い換えを重ねていく。",
                "まだ別の説明を続け、短い source から大きく膨らませていく。",
                "さらに別の観点からも補足し、元の投稿にない長いまとめ方を重ねていく。",
                "【ファンの関心ポイント】",
                "次にどうつながるかまで長く整理していきたい。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR": "1"}, clear=False):
            repaired = rss_fetcher._maybe_apply_short_source_body_shrink_repair(
                body_text=body,
                title="球団投稿が話題",
                summary="スポーツ報知巨人班Xが新フォトブースを紹介した。",
                category="コラム",
                body_subtype="social_news",
                source_url="https://twitter.com/hochi_giants/status/1",
                source_name="スポーツ報知巨人班X",
                source_day_label="",
            )

        self.assertIn("【話題の要旨】", repaired)
        self.assertIn("出典: https://twitter.com/hochi_giants/status/1", repaired)
        self.assertLess(len(repaired), len(body))

    def test_flag_on_prefers_link_only_template_for_short_manager_news(self):
        body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督のコメントを長めに整理する。",
                "若手起用の意図や周辺事情まで重ねて説明していく。",
                "【今回のポイント】",
                "ここでも同じ論点をもう一度整理していく。",
                "さらに別の表現で言い換え、短い source を膨らませる。",
                "補足説明を重ねて、短い原文以上の論点を積み増していく。",
                "同じ発言の余韻やベンチの空気まで話を広げ、説明を長く続けていく。",
                "【次の注目】",
                "次にどこを見るかまで長く語っていきたい。",
                "別の角度からも見どころを重ね、ここでも長文化を続けていく。",
            ]
        )
        with patch.dict(os.environ, {"ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR": "1"}, clear=False):
            repaired = rss_fetcher._maybe_apply_short_source_body_shrink_repair(
                body_text=body,
                title="阿部監督が起用意図を説明",
                summary="若手起用の意図を語った。",
                category="首脳陣",
                body_subtype="manager",
                source_url="https://example.com/manager-short",
                source_name="スポーツ報知",
                source_day_label="",
            )

        self.assertIn("【発言の要旨】", repaired)
        self.assertIn("【次の注目】", repaired)
        self.assertIn("出典: https://example.com/manager-short", repaired)
        self.assertLess(len(repaired), len(body))

    def test_flag_on_keeps_existing_body_when_source_is_not_short(self):
        body = "\n".join(
            [
                "【ニュースの整理】",
                "球団投稿の概要を長めに整理する。",
                "【発信内容の要約】",
                "投稿内容を丁寧に言い換えながら、背景説明も重ねていく。",
                "さらに同じ論点を補足し、長文化した前提も整理していく。",
                "【文脈と背景】",
                "周辺事情を長く説明し、ここでも言い換えを重ねていく。",
                "まだ別の説明を続け、短い source から大きく膨らませていく。",
                "さらに別の観点からも補足し、元の投稿にない長いまとめ方を重ねていく。",
                "【ファンの関心ポイント】",
                "次にどうつながるかまで長く整理していきたい。",
            ]
        )
        long_summary = " ".join(["スポーツ報知巨人班Xが新フォトブースを紹介した。"] * 12)
        with patch.dict(os.environ, {"ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR": "1"}, clear=False):
            repaired = rss_fetcher._maybe_apply_short_source_body_shrink_repair(
                body_text=body,
                title="球団投稿が話題",
                summary=long_summary,
                category="コラム",
                body_subtype="social_news",
                source_url="https://twitter.com/hochi_giants/status/1",
                source_name="スポーツ報知巨人班X",
                source_day_label="",
            )

        self.assertEqual(repaired, body)


if __name__ == "__main__":
    unittest.main()
