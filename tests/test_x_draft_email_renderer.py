import unittest

from src.x_draft_email_renderer import FIELD_ORDER, render_x_draft_email_candidate
from src.x_draft_email_validator import validate_candidate


class XDraftEmailRendererTests(unittest.TestCase):
    def _fact_article(self):
        return {
            "news_family": "試合結果",
            "entity_primary": "巨人",
            "event_nucleus": "巨人 3-2 阪神",
            "source_tier": "fact",
            "safe_fact": "巨人が阪神に3-2で勝利しました。",
            "title": "巨人、阪神に3-2で勝利",
            "published_url": "https://yoshilover.com/archives/065-postgame/",
            "source_ref": "https://www.giants.jp/game/20260423/result/",
        }

    def test_renders_fixed_eight_fields_in_order(self):
        candidate = render_x_draft_email_candidate(self._fact_article())
        payload = candidate.to_dict()

        self.assertEqual(tuple(payload.keys()), FIELD_ORDER)
        self.assertEqual(payload["recommended_account"], "official")
        self.assertEqual(payload["source_tier"], "fact")
        self.assertIn("巨人が阪神に3-2で勝利しました。", payload["safe_fact"])
        self.assertIn("巨人、阪神に3-2で勝利", payload["official_draft"])
        self.assertIn("https://yoshilover.com/archives/065-postgame/", payload["official_draft"])

    def test_official_and_inner_fields_are_separated(self):
        candidate = render_x_draft_email_candidate(self._fact_article())
        payload = candidate.to_dict()

        self.assertNotIn("中の人", payload["official_draft"])
        self.assertNotIn("個人的", payload["official_draft"])
        self.assertIn("ファン目線", payload["inner_angle"])
        self.assertNotEqual(payload["official_draft"], payload["inner_angle"])

    def test_topic_candidate_uses_inner_account_and_risk_note(self):
        candidate = render_x_draft_email_candidate(
            {
                "news_family": "コメント",
                "entity_primary": "阿部監督",
                "event_nucleus": "試合後コメント",
                "source_tier": "topic",
                "topic": "阿部監督の試合後コメント",
                "title": "阿部監督の試合後コメントが話題に",
                "published_url": "https://yoshilover.com/archives/065-comment/",
                "source_ref": "https://x.com/hochi_giants/status/1",
            }
        )
        payload = candidate.to_dict()

        self.assertEqual(payload["recommended_account"], "inner")
        self.assertIn("一次確認待ち", payload["official_draft"])
        self.assertIn("primary trust", payload["risk_note"])
        self.assertTrue(validate_candidate(candidate).ok)

    def test_draft_url_is_not_allowed_by_safety_validator(self):
        article = self._fact_article()
        article["published_url"] = "https://yoshilover.com/?p=123&preview=true"
        article["source_ref"] = "https://yoshilover.com/?p=123&preview=true"

        result = validate_candidate(render_x_draft_email_candidate(article))

        self.assertIn("DRAFT_URL_LEAK", result.hard_fail_tags)

    def test_published_public_url_is_allowed(self):
        result = validate_candidate(render_x_draft_email_candidate(self._fact_article()))

        self.assertTrue(result.ok)
        self.assertNotIn("DRAFT_URL_LEAK", result.hard_fail_tags)


if __name__ == "__main__":
    unittest.main()
