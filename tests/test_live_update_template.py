import unittest
from unittest.mock import patch

from src import rss_fetcher


LIVE_UPDATE_HEADINGS = (
    "【いま起きていること】",
    "【流れが動いた場面】",
    "【次にどこを見るか】",
)

PREGAME_LEAK_HEADINGS = (
    "【変更情報の要旨】",
    "【具体的な変更内容】",
    "【この変更が意味すること】",
)


class LiveUpdateTemplateTests(unittest.TestCase):
    def test_live_update_is_game_template_subtype(self):
        self.assertTrue(rss_fetcher._is_game_template_subtype("live_update"))

    def test_live_update_required_headings(self):
        self.assertEqual(
            rss_fetcher._game_required_headings("live_update"),
            LIVE_UPDATE_HEADINGS,
        )

    def test_live_update_strict_prompt_contains_new_headings(self):
        prompt = rss_fetcher._build_game_strict_prompt(
            "【巨人】阪神戦 途中経過",
            "7回表 巨人3-2阪神。4番手の投手が継投に入った。",
            "live_update",
            "・7回表 巨人3-2阪神\n・4番手の投手が継投に入った",
        )
        for heading in LIVE_UPDATE_HEADINGS:
            self.assertIn(heading, prompt)

    def test_live_update_strict_prompt_does_not_leak_pregame_headings(self):
        prompt = rss_fetcher._build_game_strict_prompt(
            "【巨人】阪神戦 途中経過",
            "7回表 巨人3-2阪神。4番手の投手が継投に入った。",
            "live_update",
            "・7回表 巨人3-2阪神\n・4番手の投手が継投に入った",
        )
        for heading in PREGAME_LEAK_HEADINGS:
            self.assertNotIn(heading, prompt)

    def test_live_update_strict_prompt_forbids_lineup_structure(self):
        prompt = rss_fetcher._build_game_strict_prompt(
            "【巨人】阪神戦 途中経過",
            "7回表 巨人3-2阪神。4番手の投手が継投に入った。",
            "live_update",
            "・7回表 巨人3-2阪神\n・4番手の投手が継投に入った",
        )
        self.assertIn("1番〜9番を並べた一覧", prompt)
        self.assertIn("タイトル先頭や見出しで「巨人スタメン」を使わない。", prompt)
        self.assertIn("「打順」「スタメン」「先発メンバー」を section heading にしない", prompt)

    def test_pregame_strict_prompt_still_uses_pregame_headings(self):
        prompt = rss_fetcher._build_game_strict_prompt(
            "【巨人】先発変更のお知らせ",
            "先発投手がスライド登板となりました。",
            "pregame",
            "・先発がスライド登板に変更",
        )
        for heading in PREGAME_LEAK_HEADINGS:
            self.assertIn(heading, prompt)
        for heading in LIVE_UPDATE_HEADINGS:
            self.assertNotIn(heading, prompt)
        self.assertIn("タイトル先頭や見出しで「巨人スタメン」を使わない。", prompt)

    def test_live_update_template_v2_keeps_h3_within_guard_limit(self):
        with patch.dict("os.environ", {"ENABLE_BODY_TEMPLATE_V2": "1"}, clear=False):
            blocks = rss_fetcher._render_preview_body_html(
                "\n".join(
                    [
                        "【いま起きていること】",
                        "7回表で巨人が3-2とリードしています。",
                        "【流れが動いた場面】",
                        "岡本和真の適時打で勝ち越しました。",
                        "【次にどこを見るか】",
                        "次の継投を見たいところです。",
                    ]
                )
            )

        self.assertEqual(blocks.count("<h3>"), 2)
        self.assertNotIn("<h4>", blocks)


if __name__ == "__main__":
    unittest.main()
