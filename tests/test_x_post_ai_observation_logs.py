import json
import logging
import unittest
from unittest.mock import patch

from src import rss_fetcher


class XPostAiObservationLogTests(unittest.TestCase):
    def test_x_post_ai_generated_log_payload(self):
        logger = logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_x_post_ai_generated(
                logger,
                post_id=62580,
                category="試合速報",
                article_subtype="pregame",
                ai_mode="gemini",
                generated_length=132,
                fallback_used=False,
                preview_text="Gemini generated preview",
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(
            payload,
            {
                "event": "x_post_ai_generated",
                "post_id": 62580,
                "category": "試合速報",
                "article_subtype": "pregame",
                "ai_mode": "gemini",
                "generated_length": 132,
                "fallback_used": False,
                "preview_text": "Gemini generated preview",
            },
        )

    def test_x_post_ai_failed_log_payload(self):
        logger = logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_x_post_ai_failed(
                logger,
                post_id=62581,
                category="選手情報",
                error_type="timeout",
                fallback_used=True,
                article_subtype="notice",
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(
            payload,
            {
                "event": "x_post_ai_failed",
                "post_id": 62581,
                "category": "選手情報",
                "article_subtype": "notice",
                "error_type": "timeout",
                "fallback_used": True,
            },
        )

    def test_preview_helper_logs_and_increments_daily_ai_generation_count(self):
        logger = logging.getLogger("rss_fetcher")
        history = {}

        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "gemini", "X_POST_AI_CATEGORIES": "試合速報,選手情報,首脳陣"}, clear=False):
            with patch.object(rss_fetcher, "build_x_post_text_with_meta") as build_mock:
                build_mock.return_value = (
                    "Gemini preview text",
                    {
                        "article_subtype": "pregame",
                        "effective_ai_mode": "gemini",
                        "ai_attempted": True,
                        "generated_length": 118,
                        "fallback_used": False,
                        "failure_reason": "",
                    },
                )
                with self.assertLogs("rss_fetcher", level="INFO") as cm:
                    preview_text, meta = rss_fetcher._build_x_post_preview_for_observation(
                        logger=logger,
                        history=history,
                        today_str="2026-04-17",
                        x_post_daily_limit=10,
                        post_id=62582,
                        title="巨人ヤクルト戦 神宮18時開始",
                        article_url="https://yoshilover.com/62582",
                        category="試合速報",
                        summary="戸郷翔征が先発予定。",
                        content_html="<p>戸郷翔征が先発予定。</p>",
                        article_subtype="pregame",
                        source_type="news",
                        source_name="スポーツ報知",
                    )

        self.assertEqual(preview_text, "Gemini preview text")
        self.assertEqual(meta["effective_ai_mode"], "gemini")
        self.assertEqual(history["x_ai_generation_count_2026-04-17"], 1)
        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(payload["event"], "x_post_ai_generated")
        self.assertFalse(payload["fallback_used"])

    def test_preview_helper_uses_deterministic_fallback_when_daily_limit_reached(self):
        logger = logging.getLogger("rss_fetcher")
        history = {"x_ai_generation_count_2026-04-17": 10}

        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "gemini", "X_POST_AI_CATEGORIES": "試合速報,選手情報,首脳陣"}, clear=False):
            with patch.object(rss_fetcher, "build_x_post_text_with_meta") as build_mock:
                build_mock.return_value = (
                    "Deterministic preview text",
                    {
                        "article_subtype": "notice",
                        "effective_ai_mode": "none",
                        "ai_attempted": False,
                        "generated_length": 114,
                        "fallback_used": False,
                        "failure_reason": "",
                    },
                )
                with self.assertLogs("rss_fetcher", level="INFO") as cm:
                    preview_text, meta = rss_fetcher._build_x_post_preview_for_observation(
                        logger=logger,
                        history=history,
                        today_str="2026-04-17",
                        x_post_daily_limit=10,
                        post_id=62583,
                        title="浅野翔吾が一軍登録へ",
                        article_url="https://yoshilover.com/62583",
                        category="選手情報",
                        summary="浅野翔吾外野手が一軍登録される見込み。",
                        content_html="<p>浅野翔吾外野手が一軍登録される見込み。</p>",
                        article_subtype="notice",
                        source_type="news",
                        source_name="NPB",
                    )

        self.assertEqual(preview_text, "Deterministic preview text")
        self.assertEqual(meta["failure_reason"], "daily_limit_reached")
        self.assertEqual(history["x_ai_generation_count_2026-04-17"], 10)
        failed_payload = json.loads(cm.output[0].split(":", 2)[2])
        generated_payload = json.loads(cm.output[1].split(":", 2)[2])
        self.assertEqual(failed_payload["event"], "x_post_ai_failed")
        self.assertEqual(failed_payload["error_type"], "daily_limit_reached")
        self.assertEqual(generated_payload["event"], "x_post_ai_generated")
        self.assertTrue(generated_payload["fallback_used"])

    def test_preview_helper_does_not_increment_generation_count_when_ai_key_is_missing(self):
        logger = logging.getLogger("rss_fetcher")
        history = {}

        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "gemini", "X_POST_AI_CATEGORIES": "試合速報,選手情報,首脳陣"},
            clear=False,
        ):
            with patch.object(rss_fetcher, "build_x_post_text_with_meta") as build_mock:
                build_mock.return_value = (
                    "Deterministic preview text",
                    {
                        "article_subtype": "manager",
                        "effective_ai_mode": "gemini",
                        "ai_attempted": False,
                        "generated_length": 121,
                        "fallback_used": True,
                        "failure_reason": "missing_api_key",
                    },
                )
                with self.assertLogs("rss_fetcher", level="INFO") as cm:
                    preview_text, meta = rss_fetcher._build_x_post_preview_for_observation(
                        logger=logger,
                        history=history,
                        today_str="2026-04-17",
                        x_post_daily_limit=10,
                        post_id=62584,
                        title="阿部監督が起用意図を説明",
                        article_url="https://yoshilover.com/62584",
                        category="首脳陣",
                        summary="阿部監督が起用意図を説明した。",
                        content_html="<p>阿部監督が起用意図を説明した。</p>",
                        article_subtype="manager",
                        source_type="news",
                        source_name="報知",
                    )

        self.assertEqual(preview_text, "Deterministic preview text")
        self.assertEqual(meta["failure_reason"], "missing_api_key")
        self.assertNotIn("x_ai_generation_count_2026-04-17", history)
        failed_payload = json.loads(cm.output[0].split(":", 2)[2])
        generated_payload = json.loads(cm.output[1].split(":", 2)[2])
        self.assertEqual(failed_payload["error_type"], "missing_api_key")
        self.assertTrue(generated_payload["fallback_used"])


if __name__ == "__main__":
    unittest.main()
