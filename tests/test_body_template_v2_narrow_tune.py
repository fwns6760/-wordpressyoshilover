import unittest
from unittest.mock import patch

from src import rss_fetcher


FORBIDDEN_PHRASES = (
    "発信内容の要約",
    "文脈と背景",
    "source にある範囲だけで",
    "目を引きます",
    "注目が集まります",
    "ファン必見です",
    "今後の動向から目が離せません",
    "と言えるでしょう",
    "ではないでしょうか",
)

V1_LEAK_HEADINGS = (
    "【発言の要旨】",
    "【発言内容】",
    "【発信内容の要約】",
    "【文脈と背景】",
)

PREVIEW_CASES = (
    {
        "name": "sample_64532_game_v2_izumiguchi",
        "title": "【巨人】4-2で勝利 泉口が復帰戦で1安打",
        "summary": "スポニチ巨人Xが巨人の4-2勝利と泉口友汰の復帰戦1安打を伝えた。終盤は救援陣が逃げ切った。",
        "url": "https://twitter.com/sponichi_giants/status/64532",
        "source_name": "スポニチ巨人X",
        "category": "試合速報",
        "has_game": True,
        "source_type": "social_news",
    },
    {
        "name": "sample_64534_social_v2_player_comment",
        "title": "【巨人】岸田行倫が試合後コメント「自分の役割をやるだけ」",
        "summary": "サンスポ巨人Xが岸田行倫の試合後コメントを伝えた。次戦の起用や役割への意識にも触れていた。",
        "url": "https://twitter.com/sanspo_giants/status/64534",
        "source_name": "サンスポ巨人X",
        "category": "選手情報",
        "has_game": False,
        "source_type": "social_news",
    },
    {
        "name": "sample_64539_game_v2_coach_comment",
        "title": "【巨人】3-1で勝利 打撃コーチが終盤の得点場面を振り返る",
        "summary": "スポーツ報知巨人班Xが巨人の3-1勝利と打撃コーチのコメントを伝えた。七回の得点場面が勝敗を分けた。",
        "url": "https://twitter.com/hochi_giants/status/64539",
        "source_name": "スポーツ報知巨人班X",
        "category": "試合速報",
        "has_game": True,
        "source_type": "social_news",
    },
)


def _media_quotes(url: str, label: str = "📌 関連ポスト", source_name: str = "関連X") -> list[dict]:
    return [
        {
            "url": url,
            "handle": "@related_source",
            "quote_account": "@related_source",
            "source_name": source_name,
            "section_label": label,
            "match_reason": "test",
            "match_score": 100,
        }
    ]


class BodyTemplateV2NarrowTuneTests(unittest.TestCase):
    def _render_case(self, case: dict, *, enable_v2: bool) -> tuple[str, str]:
        env_value = "1" if enable_v2 else "0"
        with patch.dict("os.environ", {"ENABLE_BODY_TEMPLATE_V2": env_value}, clear=False):
            with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=[]):
                        with patch.object(rss_fetcher, "article_parts_renderer_postgame_enabled", return_value=False):
                            with patch.object(rss_fetcher, "_postgame_strict_enabled", return_value=False):
                                return rss_fetcher.build_news_block(
                                    title=case["title"],
                                    summary=case["summary"],
                                    url=case["url"],
                                    source_name=case["source_name"],
                                    category=case["category"],
                                    has_game=case["has_game"],
                                    source_type=case["source_type"],
                                    media_quotes=_media_quotes(case["url"], source_name=case["source_name"]),
                                    article_ai_mode_override="gemini",
                                )

    def test_preview_samples_cap_h3_and_remove_forbidden_phrases(self):
        for case in PREVIEW_CASES:
            with self.subTest(case=case["name"]):
                blocks, ai_body = self._render_case(case, enable_v2=True)
                combined = "\n".join((blocks, ai_body))

                self.assertIn("<h4>📌 関連ポスト</h4>", blocks)
                self.assertLessEqual(blocks.count("<h3>"), 2)
                for phrase in FORBIDDEN_PHRASES:
                    self.assertNotIn(phrase, combined)
                for heading in V1_LEAK_HEADINGS:
                    self.assertNotIn(heading, combined)

        _, social_ai_body = self._render_case(PREVIEW_CASES[1], enable_v2=True)
        self.assertIn("【投稿で出ていた内容】", social_ai_body)
        self.assertIn("【この話が出た流れ】", social_ai_body)

    def test_v2_disable_keeps_v1_social_path(self):
        blocks, ai_body = self._render_case(PREVIEW_CASES[1], enable_v2=False)
        combined = "\n".join((blocks, ai_body))

        self.assertIn("<h3>📌 関連ポスト</h3>", blocks)
        self.assertIn("【発信内容の要約】", combined)
        self.assertIn("【文脈と背景】", combined)
        self.assertNotIn("【投稿で出ていた内容】", combined)
        self.assertNotIn("【この話が出た流れ】", combined)

    def test_media_quote_heading_is_demoted_for_manager_farm_and_notice_v2(self):
        cases = (
            {
                "name": "manager_v2",
                "title": "【巨人】阿部監督が起用意図を説明",
                "summary": "スポーツ報知巨人班Xが阿部監督の起用意図を伝えた。次戦の並びにも触れていた。",
                "url": "https://twitter.com/hochi_giants/status/70001",
                "source_name": "スポーツ報知巨人班X",
                "category": "首脳陣",
                "has_game": False,
                "source_type": "news",
            },
            {
                "name": "farm_v2",
                "title": "【巨人2軍】ティマが適時打 泉口も1安打",
                "summary": "巨人2軍が試合を行い、ティマが適時打を放った。泉口も1安打で状態を上げている。",
                "url": "https://twitter.com/giants_farm/status/70002",
                "source_name": "巨人ファーム情報",
                "category": "ドラフト・育成",
                "has_game": True,
                "source_type": "news",
            },
            {
                "name": "notice_v2",
                "title": "皆川岳飛、一軍登録 関連情報",
                "summary": "巨人・皆川岳飛外野手が出場選手登録された。",
                "url": "https://twitter.com/npb/status/70003",
                "source_name": "NPB公式X",
                "category": "選手情報",
                "has_game": False,
                "source_type": "news",
            },
        )

        for case in cases:
            with self.subTest(case=case["name"]):
                blocks, _ = self._render_case(case, enable_v2=True)
                self.assertIn("<h4>📌 関連ポスト</h4>", blocks)
                self.assertLessEqual(blocks.count("<h3>"), 2)


if __name__ == "__main__":
    unittest.main()
