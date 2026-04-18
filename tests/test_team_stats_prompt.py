import json
import unittest
from unittest.mock import patch

from src import rss_fetcher


class _FakeGeminiResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


class TeamStatsPromptTests(unittest.TestCase):
    def test_format_team_batting_stats_block_limits_to_top_five_sorted_by_avg_then_rbi(self):
        team_stats = {
            "sakamoto": {"name": "坂本勇人", "avg": ".312", "hr": "5", "rbi": "23"},
            "okamoto": {"name": "岡本和真", "avg": ".298", "hr": "8", "rbi": "25"},
            "maru": {"name": "丸佳浩", "avg": ".320", "hr": "3", "rbi": "10"},
            "wakabayashi": {"name": "若林楽人", "avg": ".320", "hr": "1", "rbi": "12"},
            "izumiguchi": {"name": "泉口友汰", "avg": ".301", "hr": "2", "rbi": "18"},
            "kadotani": {"name": "門脇誠", "avg": ".281", "hr": "0", "rbi": "9"},
        }

        block = rss_fetcher._format_team_batting_stats_block(team_stats)
        lines = block.splitlines()

        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], "・若林楽人 .320 / 1本 / 12打点")
        self.assertEqual(lines[1], "・丸佳浩 .320 / 3本 / 10打点")
        self.assertEqual(lines[2], "・坂本勇人 .312 / 5本 / 23打点")
        self.assertEqual(lines[4], "・岡本和真 .298 / 8本 / 25打点")
        self.assertNotIn("門脇誠", block)

    def test_format_team_batting_stats_block_returns_empty_for_empty_or_none(self):
        self.assertEqual(rss_fetcher._format_team_batting_stats_block({}), "")
        self.assertEqual(rss_fetcher._format_team_batting_stats_block(None), "")

    def test_format_team_batting_stats_block_handles_non_numeric_avg_without_crash(self):
        team_stats = {
            "a": {"name": "吉川尚輝", "avg": ".301", "hr": "1", "rbi": "10"},
            "b": {"name": "浅野翔吾", "avg": "-", "hr": "4", "rbi": "15"},
            "c": {"name": "増田陸", "avg": "abc", "hr": "-", "rbi": "7"},
        }

        block = rss_fetcher._format_team_batting_stats_block(team_stats)
        lines = block.splitlines()

        self.assertEqual(lines[0], "・吉川尚輝 .301 / 1本 / 10打点")
        self.assertEqual(lines[1], "・浅野翔吾 - / 4本 / 15打点")
        self.assertEqual(lines[2], "・増田陸 - / -本 / 7打点")

    def test_build_gemini_strict_prompt_is_identical_when_team_stats_block_is_empty(self):
        kwargs = dict(
            title="【巨人】阪神に3-2で勝利　岡田が決勝打",
            summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。田中将大投手は7回2失点だった。",
            category="試合速報",
            source_fact_block="・巨人が阪神に3-2で勝利\n・岡田悠希の決勝打\n・田中将大投手は7回2失点",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
        )

        prompt_without_param = rss_fetcher._build_gemini_strict_prompt(**kwargs)
        prompt_with_empty_block = rss_fetcher._build_gemini_strict_prompt(**kwargs, team_stats_block="")

        self.assertEqual(prompt_without_param, prompt_with_empty_block)

    def test_build_gemini_strict_prompt_injects_team_stats_for_game(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【巨人】阪神に3-2で勝利　岡田が決勝打",
            summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。田中将大投手は7回2失点だった。",
            category="試合速報",
            source_fact_block="・巨人が阪神に3-2で勝利\n・岡田悠希の決勝打\n・田中将大投手は7回2失点",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
            team_stats_block="・坂本勇人 .312 / 5本 / 23打点",
        )

        self.assertIn("【参考：巨人打者の今季主要指標", prompt)
        self.assertIn("・坂本勇人 .312 / 5本 / 23打点", prompt)

    def test_build_gemini_strict_prompt_injects_team_stats_for_manager(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="阿部監督「結果残せば使います」「競争は続けます」",
            summary="阿部監督が起用方針について語った。",
            category="首脳陣",
            source_fact_block="・阿部監督が起用方針を説明した\n・元記事中の表現: 「結果残せば使います」",
            win_loss_hint="",
            has_game=False,
            real_reactions=[],
            team_stats_block="・坂本勇人 .312 / 5本 / 23打点",
        )

        self.assertIn("【参考：巨人打者の今季主要指標", prompt)
        self.assertIn("・坂本勇人 .312 / 5本 / 23打点", prompt)

    def test_build_gemini_strict_prompt_does_not_inject_team_stats_for_farm(self):
        prompt = rss_fetcher._build_gemini_strict_prompt(
            title="【二軍】巨人 4-1 ロッテ　ティマが2安打3打点、山城京平は3回1失点",
            summary="巨人二軍がロッテとの二軍戦に4-1で勝利した。ティマが2安打3打点を記録し、山城京平投手は3回1失点だった。",
            category="ドラフト・育成",
            source_fact_block="・巨人二軍がロッテとの二軍戦に4-1で勝利\n・ティマが2安打3打点\n・山城京平投手は3回1失点",
            win_loss_hint="",
            has_game=True,
            real_reactions=[],
            team_stats_block="・坂本勇人 .312 / 5本 / 23打点",
        )

        self.assertNotIn("【参考：巨人打者の今季主要指標", prompt)
        self.assertNotIn("・坂本勇人 .312 / 5本 / 23打点", prompt)

    def test_generate_article_with_gemini_does_not_fetch_team_stats_when_flag_off(self):
        fake_payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "これはテスト用の十分に長い本文です。"}
                        ]
                    }
                }
            ]
        }

        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "dummy-key",
                "STRICT_FACT_MODE": "1",
                "ARTICLE_INJECT_TEAM_STATS": "0",
            },
            clear=False,
        ):
            with patch.object(rss_fetcher, "strict_fact_mode_enabled", return_value=True):
                with patch.object(rss_fetcher, "fetch_giants_batting_stats_from_yahoo", side_effect=AssertionError("should not be called")):
                    with patch.object(rss_fetcher, "_get_gemini_strict_min_chars", return_value=1):
                        with patch("urllib.request.urlopen", return_value=_FakeGeminiResponse(fake_payload)):
                            article = rss_fetcher.generate_article_with_gemini(
                                title="【巨人】阪神に3-2で勝利　岡田が決勝打",
                                summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。田中将大投手は7回2失点だった。",
                                category="試合速報",
                                real_reactions=[],
                                has_game=True,
                            )

        self.assertEqual(article, "これはテスト用の十分に長い本文です。")


if __name__ == "__main__":
    unittest.main()
