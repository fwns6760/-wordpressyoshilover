"""Tests for 417: build_x_post_from_article_info / _find_first_giants_player_in_text.

Gemini API call は patch、 silent skip path を中心に verify。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src import x_post_branding_gen as xbg
from src import x_post_candidate_queue as q


def _make_article(title="", summary="", **kw):
    return q.CandidateArticleInfo(
        source_url=kw.get("source_url", "https://hochi.news/giants/1"),
        title=title,
        summary=summary,
        source_name=kw.get("source_name", "スポーツ報知"),
        source_type=kw.get("source_type", "rss"),
        article_subtype=kw.get("article_subtype", "player_voice"),  # 既存 default、 個別 player 系
        player_canonical=kw.get("player_canonical", []),
    )


class FindFirstGiantsPlayerTests(unittest.TestCase):
    def test_finds_canonical_player_in_title(self):
        result = xbg._find_first_giants_player_in_text("巨人の戸郷翔征が好投、ヤクルト戦完封勝利")
        self.assertEqual(result, "戸郷翔征")

    def test_alias_maps_to_canonical(self):
        # "戸郷" alias → "戸郷翔征" canonical
        result = xbg._find_first_giants_player_in_text("巨人戸郷が完封")
        self.assertEqual(result, "戸郷翔征")

    def test_no_player_returns_empty(self):
        result = xbg._find_first_giants_player_in_text("巨人、ヤクルト戦で逆転勝利")
        self.assertEqual(result, "")

    def test_non_string_returns_empty(self):
        self.assertEqual(xbg._find_first_giants_player_in_text(None), "")
        self.assertEqual(xbg._find_first_giants_player_in_text(123), "")
        self.assertEqual(xbg._find_first_giants_player_in_text(""), "")

    def test_picks_earliest_in_text(self):
        # 田中将大 (3-4 文字目) より 戸郷 (6-7) のほうが後 → 田中将大が選ばれる
        # (両方 roster にあるかは alias 次第)
        result = xbg._find_first_giants_player_in_text("田中将大、戸郷と並んで連勝中")
        # "田中将大" alias が roster にあれば優先選択される (alias map では確認済)
        self.assertEqual(result, "田中将大")


class BuildXPostFromArticleInfoSkipPathTests(unittest.TestCase):
    def test_invalid_input_skipped(self):
        # None article_info
        self.assertIsNone(
            xbg.build_x_post_from_article_info(None, gemini_api_key="key")
        )
        # empty title
        article = _make_article(title="")
        self.assertIsNone(
            xbg.build_x_post_from_article_info(article, gemini_api_key="key")
        )

    def test_missing_gemini_key_skipped(self):
        article = _make_article(title="巨人の戸郷翔征が完封")
        self.assertIsNone(
            xbg.build_x_post_from_article_info(article, gemini_api_key="")
        )

    def test_no_giants_player_in_title_skipped(self):
        # title / summary 両方に Giants roster player が無い
        article = _make_article(title="巨人、ヤクルト戦で逆転勝利", summary="序盤からリードを奪い")
        self.assertIsNone(
            xbg.build_x_post_from_article_info(article, gemini_api_key="key")
        )

    @patch("src.x_post_branding_gen._gemini_branding_safety_check", return_value=False)
    @patch("google.genai.Client")
    def test_safety_check_failure_drops_candidate(self, mock_client_cls, _safety):
        # Gemini Flash Lite が「絶対に勝てる」 等の forbidden pattern を吐いた場合
        mock_response = type("R", (), {"text": "絶対に勝てる、 100% 確実だ"})()
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        article = _make_article(title="戸郷翔征が完封勝利")
        result = xbg.build_x_post_from_article_info(article, gemini_api_key="key")
        self.assertIsNone(result)

    @patch("src.x_post_branding_gen._gemini_branding_safety_check", return_value=True)
    @patch("src.x_post_branding_gen._extract_unverified_numbers", return_value=["999"])
    @patch("google.genai.Client")
    def test_unverified_numbers_drops_candidate(self, mock_client_cls, _unverified, _safety):
        # Gemini Flash Lite が verified_text に存在しない数字 (例: "999連勝") を出力した case
        mock_response = type("R", (), {"text": "戸郷翔征の好投で999連勝、 これは凄い"})()
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        article = _make_article(title="戸郷翔征が好投")
        result = xbg.build_x_post_from_article_info(article, gemini_api_key="key")
        self.assertIsNone(result)


class PostgameTeamWideTests(unittest.TestCase):
    """417 user 修正 (2026-05-21): postgame は team-wide / fuuga 強制、 個別 player 不要."""

    @patch("src.x_post_branding_gen._gemini_branding_safety_check", return_value=True)
    @patch("src.x_post_branding_gen._extract_unverified_numbers", return_value=[])
    @patch("src.x_post_branding_gen.is_giants_game_day", return_value=True)
    @patch("google.genai.Client")
    def test_postgame_subtype_uses_team_wide_player(self, mock_client_cls, _gd, _unv, _safety):
        # postgame subtype → focus_player は 「巨人」 (team-wide)、 個別 player でない
        # 2026-06-04: voice 門番 (_voice_quality_ok) 追加に伴い、 作りポエム調 (！連発)
        # ではなく、 読みの入った fuuga voice に差し替え (team-wide ロジック検証が本旨)。
        # 2026-06-04 B: voice 門番が数字 1 個必須になったため、 数字入りの fuuga voice に更新。
        mock_response = type("R", (), {"text": "今日は投打が噛み合って7連勝だな。先発が6回をしっかり投げ切って、中盤の効果的な追加点で相手に流れを渡さなかったのが効いた。この勝ち方を続けられれば上位争いは十分見えてくる。"})()
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        article = _make_article(
            title="巨人完勝で 7 連勝、 投打噛み合う充実の展開",
            summary="9 回 3-0 でヤクルトに勝利、 投打が噛み合った内容",
            article_subtype="postgame",
        )
        cand = xbg.build_x_post_from_article_info(article, gemini_api_key="key", persona="fuuga")
        self.assertIsNotNone(cand)
        self.assertEqual(cand.focus_player, "巨人")
        self.assertIn("巨人", cand.title)

    @patch("src.x_post_branding_gen._gemini_branding_safety_check", return_value=True)
    @patch("src.x_post_branding_gen._extract_unverified_numbers", return_value=[])
    @patch("src.x_post_branding_gen.is_giants_game_day", return_value=True)
    @patch("google.genai.Client")
    def test_postgame_skips_player_extraction_even_if_player_in_title(
        self, mock_client_cls, _gd, _unv, _safety
    ):
        # title に「戸郷翔征」 が居ても postgame は team-wide (= 巨人) で書く
        # 2026-06-04: voice 門番追加に伴い、 ！連発のポエムから読みの入った fuuga voice へ差し替え。
        # 2026-06-04 B: voice 門番が数字 1 個必須になったため、 数字入りの fuuga voice に更新。
        mock_response = type("R", (), {"text": "戸郷翔征が7回を制球良く試合を作って、 打線も序盤から先手を取れた完勝だな。先発が長いイニングを投げ切ると中継ぎを温存できるのが大きい。この形を続けたいところ。"})()
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        article = _make_article(
            title="戸郷翔征 7 回無失点で完勝、 巨人 7 連勝",
            summary="戸郷が制球冴え、 打線も序盤から得点",
            article_subtype="postgame",
        )
        cand = xbg.build_x_post_from_article_info(article, gemini_api_key="key", persona="fuuga")
        self.assertIsNotNone(cand)
        # 個別 player でなく 巨人 が focus_player
        self.assertEqual(cand.focus_player, "巨人")

    @patch("src.x_post_branding_gen._gemini_branding_safety_check", return_value=True)
    @patch("src.x_post_branding_gen._extract_unverified_numbers", return_value=[])
    @patch("src.x_post_branding_gen.is_giants_game_day", return_value=True)
    @patch("google.genai.Client")
    def test_non_postgame_uses_player_extraction(self, mock_client_cls, _gd, _unv, _safety):
        # 非 postgame (player_voice 等) → 個別 player を抽出して focus
        mock_response = type("R", (), {"text": "4 回終わって 2-2、 戸郷ようやくリズム掴んできた、 次の回頭からクリーンアップ" * 2})()
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        article = _make_article(
            title="戸郷翔征 4 回終わって 2-2",
            summary="戸郷投手が4回まで投げて 2 失点",
            article_subtype="player_voice",
        )
        cand = xbg.build_x_post_from_article_info(article, gemini_api_key="key", persona="kandume")
        self.assertIsNotNone(cand)
        # 個別 player (戸郷) が focus
        self.assertEqual(cand.focus_player, "戸郷翔征")


if __name__ == "__main__":
    unittest.main()


class BuildXPostFromArticleInfoPlayerDedupTests(unittest.TestCase):
    """2026-06-03: 同一選手の重複生成を Gemini 呼び出し前に抑止 (LLM 費用節約)。"""

    def test_skip_player_keys_blocks_before_gemini(self):
        # cooldown / window-cap 既出 player は生成側 (gemini_api_key 有) でも skip。
        article = _make_article(title="巨人の戸郷翔征が完封勝利")
        key = xbg._normalize_player_name("戸郷翔征")
        with patch.object(
            xbg, "_build_system_prompt", side_effect=AssertionError("must skip before Gemini")
        ):
            out = xbg.build_x_post_from_article_info(
                article, gemini_api_key="key", skip_player_keys={key}
            )
        self.assertIsNone(out)

    def test_succeeded_player_blocks_within_run_repeat(self):
        # 同 run で既に投稿成立済みの player は再生成しない (1 選手 1 投稿)。
        article = _make_article(title="巨人の戸郷翔征が完封勝利")
        key = xbg._normalize_player_name("戸郷翔征")
        with patch.object(
            xbg, "_build_system_prompt", side_effect=AssertionError("must skip before Gemini")
        ):
            out = xbg.build_x_post_from_article_info(
                article, gemini_api_key="key", succeeded_player_keys={key}
            )
        self.assertIsNone(out)

    def test_attempt_cap_blocks_after_max_attempts(self):
        # 試行上限到達 player は生成しない (全部品質ゲート落ちの暴走防止)。
        article = _make_article(title="巨人の戸郷翔征が完封勝利")
        key = xbg._normalize_player_name("戸郷翔征")
        with patch.object(
            xbg, "_build_system_prompt", side_effect=AssertionError("must skip before Gemini")
        ):
            out = xbg.build_x_post_from_article_info(
                article, gemini_api_key="key",
                attempt_counts={key: 3}, max_attempts_per_player=3,
            )
        self.assertIsNone(out)

    def test_attempt_count_increments_below_cap(self):
        # 上限未満なら試行カウントを増やして生成へ進む (Gemini 手前で stop)。
        article = _make_article(title="巨人の戸郷翔征が完封勝利")
        key = xbg._normalize_player_name("戸郷翔征")
        counts: dict = {}
        with patch.object(xbg, "_build_system_prompt", side_effect=RuntimeError("stop")):
            try:
                xbg.build_x_post_from_article_info(
                    article, gemini_api_key="key",
                    attempt_counts=counts, max_attempts_per_player=3,
                )
            except RuntimeError:
                pass
        self.assertEqual(counts.get(key), 1)

    def test_team_wide_postgame_not_capped_by_skip_keys(self):
        # postgame team-wide ("巨人") は試合ごと 1 回なので cross-run cap 対象外。
        # skip_player_keys に "巨人" key が居ても skip しない (within-run seen は別)。
        article = _make_article(
            title="巨人が逆転勝ちで連勝", article_subtype="postgame"
        )
        team_key = xbg._normalize_player_name("巨人")
        # _build_system_prompt 到達 = cap で止まらなかった = 期待挙動。
        # Gemini 自体は呼ばせず prompt 構築段階で確認。
        reached = {"v": False}

        def _stop(*a, **k):
            reached["v"] = True
            raise RuntimeError("stop after cap check")

        with patch.object(xbg, "_build_system_prompt", side_effect=_stop):
            try:
                xbg.build_x_post_from_article_info(
                    article, gemini_api_key="key", skip_player_keys={team_key}
                )
            except RuntimeError:
                pass
        self.assertTrue(reached["v"], "team-wide postgame must not be skipped by cap")


class LLMBudgetTests(unittest.TestCase):
    """2026-06-03: per-fire LLM 生成上限 (コスト削減)。"""

    def test_budget_blocks_after_max(self):
        xbg.set_llm_budget(2)
        xbg._llm_budget_guard("t")   # used 1
        xbg._llm_budget_guard("t")   # used 2
        with self.assertRaises(RuntimeError):
            xbg._llm_budget_guard("t")  # exceeds
        xbg.set_llm_budget(None)  # reset to unlimited for other tests

    def test_budget_zero_or_none_unlimited(self):
        xbg.set_llm_budget(0)
        for _ in range(50):
            xbg._llm_budget_guard("t")  # never raises
        xbg.set_llm_budget(None)
        for _ in range(50):
            xbg._llm_budget_guard("t")
