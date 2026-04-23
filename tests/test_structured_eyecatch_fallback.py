from __future__ import annotations

import os
import time
import unittest
from unittest.mock import Mock, patch

from src import eyecatch_fallback
from src.tools import run_notice_fixed_lane as lane
from src.wp_client import WPClient


class _UploadingWP:
    def __init__(self, media_id: int = 731) -> None:
        self.api = "https://example.com/wp-json/wp/v2"
        self.auth = ("user", "pass")
        self.headers = {"Content-Type": "application/json"}
        self.media_id = media_id
        self.generated_calls: list[tuple[bytes, str, str]] = []

    def upload_generated_image(self, image_data: bytes, filename: str, content_type: str) -> int:
        self.generated_calls.append((image_data, filename, content_type))
        return self.media_id


class StructuredEyecatchFallbackTests(unittest.TestCase):
    def _make_candidate(self, family: str, **overrides):
        defaults = {
            "program_notice": {
                "air_date": "20260421",
                "program_slug": "giants-tv",
                "title": "[04/21] ジャイアンツTV 18:00 放送予定",
                "body_html": "<p>ジャイアンツTV 4/21 18:00 放送予定</p>",
                "category": "球団情報",
                "tags": ["番組"],
            },
            "transaction_notice": {
                "notice_date": "20260420",
                "subject": "山瀬慎之助+丸佳浩",
                "notice_kind": "register_deregister",
                "title": "【公示】4月20日 巨人は山瀬慎之助を登録、丸佳浩を抹消",
                "body_html": "<p>公示本文</p>",
                "category": "選手情報",
                "tags": ["公示"],
            },
            "probable_pitcher": {
                "game_id": "20260421-g-t",
                "title": "【4/21予告先発】 巨人 vs 阪神 #田中将大 #才木浩人",
                "body_html": "<p>予告先発 田中将大投手 才木浩人投手</p>",
                "category": "試合速報",
                "tags": ["予告先発"],
            },
            "comment_notice": {
                "notice_date": "20260421",
                "speaker": "阿部慎之助監督",
                "context_slug": "postgame-qa",
                "title": "阿部慎之助監督「守備から入れた」",
                "body_html": "<p>comment</p>",
                "category": "首脳陣",
                "tags": ["コメント"],
                "source_kind": lane.SOURCE_KIND_COMMENT_QUOTE,
            },
            "injury_notice": {
                "notice_date": "20260421",
                "subject": "浅野翔吾",
                "injury_status": "upper_body",
                "title": "浅野翔吾の故障状況",
                "body_html": "<p>injury</p>",
                "category": "選手情報",
                "tags": ["故障"],
                "source_kind": lane.SOURCE_KIND_COMMENT_QUOTE,
            },
            "postgame_result": {
                "game_id": "20260421-g-t",
                "result_token": "win",
                "title": "巨人 3-2 阪神",
                "body_html": "<p>postgame</p>",
                "category": "試合速報",
                "tags": ["試合結果"],
                "source_kind": lane.SOURCE_KIND_OFFICIAL_WEB,
            },
        }
        payload = {
            "family": family,
            "source_url": "https://example.com/source",
            "trust_tier": lane.TRUST_TIER_T1,
        }
        payload.update(defaults[family])
        payload.update(overrides)
        candidate, outcome = lane._normalize_intake_item(payload)
        self.assertIsNone(outcome)
        self.assertIsNotNone(candidate)
        return candidate

    def test_supported_layouts_render_expected_source_facts(self):
        cases = [
            ("program_notice", "fact_notice_program", "番組情報", ["ジャイアンツTV", "2026.04.21", "18:00"]),
            ("transaction_notice", "fact_notice_transaction", "公示", ["山瀬慎之助", "丸佳浩", "登録 / 抹消"]),
            ("probable_pitcher", "probable_starter", "予告先発", ["巨人 vs 阪神", "田中将大", "才木浩人"]),
            ("comment_notice", "comment_notice", "コメント", ["阿部慎之助監督", "守備から入れた"]),
            ("injury_notice", "injury_notice", "怪我状況", ["浅野翔吾", "上半身の状態"]),
            ("postgame_result", "postgame_result", "試合結果", ["巨人 vs 阪神", "3 - 2"]),
        ]
        for family, layout_key, label, expected_texts in cases:
            with self.subTest(family=family):
                candidate = self._make_candidate(family)
                structured = eyecatch_fallback.build_structured_eyecatch(candidate)
                self.assertIsNotNone(structured)
                assert structured is not None
                self.assertEqual(structured.layout_key, layout_key)
                self.assertEqual(structured.label, label)
                rendered = structured.image_bytes.decode("utf-8")
                for expected in expected_texts:
                    self.assertIn(expected, rendered)

    def test_generated_svg_replaces_common_noimage_for_supported_candidate(self):
        candidate = self._make_candidate("transaction_notice")
        structured = eyecatch_fallback.build_structured_eyecatch(candidate)

        self.assertIsNotNone(structured)
        assert structured is not None
        rendered = structured.image_bytes.decode("utf-8")
        self.assertTrue(rendered.startswith("<svg"))
        self.assertNotIn("example.com", rendered)
        self.assertNotIn("noimage", rendered.lower())
        self.assertNotIn("no_image", rendered.lower())

    def test_assertability_does_not_leak_context_slug(self):
        candidate = self._make_candidate("comment_notice", context_slug="postgame-qa")
        structured = eyecatch_fallback.build_structured_eyecatch(candidate)

        self.assertIsNotNone(structured)
        assert structured is not None
        rendered = structured.image_bytes.decode("utf-8")
        self.assertNotIn("postgame-qa", rendered)
        self.assertIn("守備から入れた", rendered)

    def test_existing_image_metadata_skips_fallback_generation(self):
        candidate = self._make_candidate("postgame_result")
        candidate.metadata["og_image_url"] = "https://example.com/hero.jpg"

        structured = eyecatch_fallback.build_structured_eyecatch(candidate)

        self.assertIsNone(structured)

    @patch("src.tools.run_notice_fixed_lane.requests.post")
    def test_create_notice_draft_attaches_generated_featured_media(self, mock_post):
        candidate = self._make_candidate("transaction_notice")
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 63175})
        wp = _UploadingWP(media_id=731)

        post_id = lane._create_notice_draft(wp, candidate, [664, 999], [777])

        self.assertEqual(post_id, 63175)
        self.assertEqual(len(wp.generated_calls), 1)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["featured_media"], 731)
        self.assertEqual(payload["meta"]["candidate_key"], candidate.metadata["candidate_key"])

    @patch("src.tools.run_notice_fixed_lane.requests.post")
    def test_create_notice_draft_skips_fallback_when_existing_image_present(self, mock_post):
        candidate = self._make_candidate("transaction_notice")
        candidate.metadata["featured_image_url"] = "https://example.com/hero.jpg"
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 63175})
        wp = _UploadingWP(media_id=731)

        post_id = lane._create_notice_draft(wp, candidate, [664, 999], [777])

        self.assertEqual(post_id, 63175)
        self.assertEqual(wp.generated_calls, [])
        payload = mock_post.call_args.kwargs["json"]
        self.assertNotIn("featured_media", payload)

    def test_build_structured_eyecatch_is_lightweight(self):
        candidate = self._make_candidate("postgame_result")

        start = time.perf_counter()
        for _ in range(200):
            structured = eyecatch_fallback.build_structured_eyecatch(candidate)
            self.assertIsNotNone(structured)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 1.0)


class WPClientGeneratedImageUploadTests(unittest.TestCase):
    def setUp(self):
        os.environ["WP_URL"] = "https://example.com"
        os.environ["WP_USER"] = "user"
        os.environ["WP_APP_PASSWORD"] = "pass"
        self.wp = WPClient()

    @patch("src.wp_client.requests.get", side_effect=AssertionError("external fetch should not run"))
    @patch("src.wp_client.requests.post")
    def test_upload_generated_image_posts_bytes_without_external_fetch(self, mock_post, _mock_get):
        mock_post.return_value = Mock(status_code=201, json=lambda: {"id": 90210})

        media_id = self.wp.upload_generated_image(
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            filename="structured-eyecatch.svg",
            content_type="image/svg+xml",
        )

        self.assertEqual(media_id, 90210)
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Content-Type"], "image/svg+xml")
        self.assertIn('structured-eyecatch.svg', kwargs["headers"]["Content-Disposition"])
        self.assertIn(b"<svg", kwargs["data"])


if __name__ == "__main__":
    unittest.main()
