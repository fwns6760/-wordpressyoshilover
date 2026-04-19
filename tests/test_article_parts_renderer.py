import unittest

from src import rss_fetcher
from src.article_parts_renderer import ArticleParts, render_postgame


class ArticlePartsRendererTests(unittest.TestCase):
    def build_parts(self) -> ArticleParts:
        return {
            "title": "巨人が阪神に3-2で勝利 岡田悠希が決勝打",
            "fact_lead": "巨人が阪神に3-2で勝利し、終盤に岡田悠希の決勝打が出た。",
            "body_core": [
                "先発の田中将大投手は7回2失点で試合をつくった。",
                "打線は終盤まで同点のまま進み、終盤に勝ち越した。",
            ],
            "game_context": "終盤まで拮抗した展開が続き、最後は勝ち越し点を守り切った。",
            "fan_view": "この勝ち方は次戦にもつながりそうです。",
            "source_attribution": {
                "source_name": "日刊スポーツ",
                "source_url": "https://example.com/postgame",
            },
        }

    def test_render_postgame_includes_source_block_headings_and_close(self):
        html = render_postgame(self.build_parts())

        self.assertIn("📰 日刊スポーツ", html)
        self.assertIn("記事元を読む", html)
        self.assertIn("<h2>試合概要</h2>", html)
        self.assertIn("<h2>試合展開</h2>", html)
        self.assertIn("この勝ち方は次戦にもつながりそうです。", html)

    def test_render_postgame_omits_close_when_fan_view_missing(self):
        parts = self.build_parts()
        del parts["fan_view"]

        html = render_postgame(parts)

        self.assertNotIn("次戦にもつながりそうです", html)
        self.assertEqual(html.count("<!-- wp:paragraph -->"), 4)

    def test_render_postgame_allows_empty_body_core(self):
        parts = self.build_parts()
        parts["body_core"] = []

        html = render_postgame(parts)

        self.assertIn("<h2>試合概要</h2>", html)
        self.assertIn("<h2>試合展開</h2>", html)
        self.assertIn("終盤まで拮抗した展開が続き", html)

    def test_render_postgame_escapes_embedded_html(self):
        parts = self.build_parts()
        parts["fact_lead"] = "<script>alert('x')</script>勝利"
        parts["body_core"] = ["<b>岡田悠希</b>が決勝打を放った。"]
        parts["fan_view"] = "<img src=x onerror=alert(1)>注目です。"

        html = render_postgame(parts)

        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>岡田悠希</b>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert('x')&lt;/script&gt;勝利", html)
        self.assertIn("&lt;b&gt;岡田悠希&lt;/b&gt;が決勝打を放った。", html)


class ArticlePartsPromptTests(unittest.TestCase):
    def test_postgame_parts_prompt_declares_schema_and_json_only_output(self):
        prompt = rss_fetcher._build_game_parts_prompt_postgame(
            title="【巨人】阪神に3-2で勝利 岡田悠希が決勝打",
            summary="巨人が阪神に3-2で勝利した。岡田悠希が決勝打を放った。",
            source_fact_block="・巨人が阪神に3-2で勝利\n・岡田悠希が決勝打\n・田中将大投手は7回2失点",
            score="3-2",
            win_loss_hint="勝利",
            team_stats_reference="チーム打率 .245 / 12本塁打",
        )

        for field_name in (
            "title",
            "fact_lead",
            "body_core",
            "game_context",
            "fan_view",
            "source_attribution",
        ):
            self.assertIn(field_name, prompt)
        self.assertIn("全文の HTML や template 構造は書かない", prompt)
        self.assertIn("JSON object で返してください", prompt)
        self.assertIn("source / 材料 にない事実・数字・比較・推測は禁止", prompt)

    def test_postgame_parts_prompt_does_not_reuse_chain_of_reasoning_or_opinion_marker_language(self):
        prompt = rss_fetcher._build_game_parts_prompt_postgame(
            title="【巨人】阪神に3-2で勝利 岡田悠希が決勝打",
            summary="巨人が阪神に3-2で勝利した。岡田悠希が決勝打を放った。",
            source_fact_block="・巨人が阪神に3-2で勝利\n・岡田悠希が決勝打\n・田中将大投手は7回2失点",
            score="3-2",
            win_loss_hint="勝利",
            team_stats_reference="",
        )

        self.assertNotIn("事実 → 解釈 → 感想", prompt)
        self.assertNotIn("気になります", prompt)
        self.assertNotIn("【注目ポイント】", prompt)


if __name__ == "__main__":
    unittest.main()
