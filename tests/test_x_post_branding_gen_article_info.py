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
        article_subtype=kw.get("article_subtype", "postgame"),
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

    @patch("src.x_post_branding_gen._gemma_branding_safety_check", return_value=False)
    @patch("google.genai.Client")
    def test_safety_check_failure_drops_candidate(self, mock_client_cls, _safety):
        # Gemma が「絶対に勝てる」 等の forbidden pattern を吐いた場合
        mock_response = type("R", (), {"text": "絶対に勝てる、 100% 確実だ"})()
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        article = _make_article(title="戸郷翔征が完封勝利")
        result = xbg.build_x_post_from_article_info(article, gemini_api_key="key")
        self.assertIsNone(result)

    @patch("src.x_post_branding_gen._gemma_branding_safety_check", return_value=True)
    @patch("src.x_post_branding_gen._extract_unverified_numbers", return_value=["999"])
    @patch("google.genai.Client")
    def test_unverified_numbers_drops_candidate(self, mock_client_cls, _unverified, _safety):
        # Gemma が verified_text に存在しない数字 (例: "999連勝") を出力した case
        mock_response = type("R", (), {"text": "戸郷翔征の好投で999連勝、 これは凄い"})()
        mock_client_cls.return_value.models.generate_content.return_value = mock_response
        article = _make_article(title="戸郷翔征が好投")
        result = xbg.build_x_post_from_article_info(article, gemini_api_key="key")
        self.assertIsNone(result)


class SelectBrandingModelByTimeTests(unittest.TestCase):
    """417 follow-up: 試合中 (18:00-21:30 JST) Gemini 3.5 Flash 切替 boundary test."""

    def _at(self, h, m=0):
        from datetime import datetime, timezone, timedelta
        return datetime(2026, 5, 21, h, m, tzinfo=timezone(timedelta(hours=9)))

    def test_morning_uses_gemma(self):
        self.assertEqual(xbg.select_branding_model_by_time(self._at(7, 0)), "gemma-4-31b-it")

    def test_lunch_uses_gemma(self):
        self.assertEqual(xbg.select_branding_model_by_time(self._at(12, 0)), "gemma-4-31b-it")

    def test_pre_game_1759_uses_gemma(self):
        # 17:59 → まだ試合中ではない、 Gemma
        self.assertEqual(xbg.select_branding_model_by_time(self._at(17, 59)), "gemma-4-31b-it")

    def test_game_start_1800_uses_flash(self):
        # 18:00 ちょうど → 試合中、 Gemini 3.5 Flash
        self.assertEqual(xbg.select_branding_model_by_time(self._at(18, 0)), "gemini-3.5-flash")

    def test_mid_game_uses_flash(self):
        for h, m in [(18, 30), (19, 15), (20, 0), (20, 59), (21, 0), (21, 29)]:
            with self.subTest(time=f"{h:02d}:{m:02d}"):
                self.assertEqual(xbg.select_branding_model_by_time(self._at(h, m)), "gemini-3.5-flash")

    def test_game_end_2130_uses_gemma(self):
        # 21:30 ちょうど → 試合終了扱い、 Gemma に戻る
        self.assertEqual(xbg.select_branding_model_by_time(self._at(21, 30)), "gemma-4-31b-it")

    def test_postgame_2200_uses_gemma(self):
        self.assertEqual(xbg.select_branding_model_by_time(self._at(22, 0)), "gemma-4-31b-it")

    def test_none_input_returns_gemma(self):
        self.assertEqual(xbg.select_branding_model_by_time(None), "gemma-4-31b-it")


if __name__ == "__main__":
    unittest.main()
