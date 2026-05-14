"""Tests for src/youtube_caption_fetcher.py (344-INGEST Phase 1a)."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from src import youtube_caption_fetcher


class _FakeSegment:
    def __init__(self, text: str):
        self.text = text


def _make_segments(texts: list[str]):
    return [_FakeSegment(t) for t in texts]


class JoinCaptionSegmentsTests(unittest.TestCase):
    def test_joins_with_space(self):
        result = youtube_caption_fetcher._join_caption_segments(
            _make_segments(["こんにちは", "巨人の話", "今日の試合"])
        )
        self.assertEqual(result, "こんにちは 巨人の話 今日の試合")

    def test_normalizes_whitespace(self):
        result = youtube_caption_fetcher._join_caption_segments(
            _make_segments(["a\nb", "c\td", "  e  "])
        )
        self.assertEqual(result, "a b c d e")

    def test_empty_segments_skipped(self):
        result = youtube_caption_fetcher._join_caption_segments(
            _make_segments(["", "巨人", "", " "])
        )
        self.assertEqual(result, "巨人")

    def test_dict_segments_supported(self):
        result = youtube_caption_fetcher._join_caption_segments(
            [{"text": "巨人"}, {"text": "勝利"}]
        )
        self.assertEqual(result, "巨人 勝利")


class TrimToMaxCharsTests(unittest.TestCase):
    def test_under_limit_unchanged(self):
        self.assertEqual(
            youtube_caption_fetcher._trim_to_max_chars("巨人勝利", 600), "巨人勝利"
        )

    def test_trims_at_sentence_boundary(self):
        text = "巨人が勝った。坂本がHR。" * 60
        result = youtube_caption_fetcher._trim_to_max_chars(text, 100)
        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.endswith("。"))

    def test_hard_trim_when_no_sentence_boundary(self):
        text = "あ" * 800
        result = youtube_caption_fetcher._trim_to_max_chars(text, 600)
        self.assertEqual(len(result), 600)


class FetchYoutubeCaptionTests(unittest.TestCase):
    def test_empty_video_id_returns_empty(self):
        self.assertEqual(youtube_caption_fetcher.fetch_youtube_caption(""), "")

    def test_successful_fetch_returns_joined_text(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls:
            mock_api = MagicMock()
            mock_api.fetch.return_value = _make_segments(
                ["巨人・坂本勇人が逆転サヨナラ３ラン。", "「一生忘れない」と語った。"]
            )
            mock_api_cls.return_value = mock_api
            result = youtube_caption_fetcher.fetch_youtube_caption("dummy_id")
            self.assertIn("巨人・坂本勇人", result)
            self.assertIn("一生忘れない", result)

    def test_api_exception_returns_empty(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls:
            mock_api = MagicMock()
            mock_api.fetch.side_effect = Exception("NoTranscriptFound")
            mock_api_cls.return_value = mock_api
            result = youtube_caption_fetcher.fetch_youtube_caption("dummy_id")
            self.assertEqual(result, "")

    def test_too_short_caption_returns_empty(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls:
            mock_api = MagicMock()
            mock_api.fetch.return_value = _make_segments(["短い"])
            mock_api_cls.return_value = mock_api
            result = youtube_caption_fetcher.fetch_youtube_caption("dummy_id")
            self.assertEqual(result, "")

    def test_max_chars_applied(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls:
            mock_api = MagicMock()
            mock_api.fetch.return_value = _make_segments(["巨人勝利。" * 200])
            mock_api_cls.return_value = mock_api
            result = youtube_caption_fetcher.fetch_youtube_caption(
                "dummy_id", max_chars=300
            )
            self.assertLessEqual(len(result), 300)

    def test_languages_passed_through(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_cls:
            mock_api = MagicMock()
            mock_api.fetch.return_value = _make_segments(["巨人本日勝利、戸郷が完封勝利を達成しました。"])
            mock_api_cls.return_value = mock_api
            youtube_caption_fetcher.fetch_youtube_caption(
                "dummy_id", languages=("ja",)
            )
            mock_api.fetch.assert_called_once_with("dummy_id", languages=("ja",))


if __name__ == "__main__":
    unittest.main()
