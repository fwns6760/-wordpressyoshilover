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


if __name__ == "__main__":
    unittest.main()
