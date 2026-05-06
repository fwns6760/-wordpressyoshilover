import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


class SourceGroundingDriftRepairTests(unittest.TestCase):
    def test_flag_off_keeps_existing_post_gen_validate_behavior(self):
        text = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督のコメントを整理する。",
                "5-3で逃げ切った流れも振り返りたい。",
                "【次の注目】",
                "次の起用に注目です。",
            ]
        )
        source_refs = {
            "category": "首脳陣",
            "source_title": "阿部監督が若手起用の意図を説明",
            "source_summary": "若手起用の意図を語った。",
        }

        with patch.dict(os.environ, {"ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR": "0"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(
                text,
                article_subtype="general",
                source_refs=source_refs,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["fail_axes"], [])

    def test_flag_on_repair_removes_ungrounded_score_sentence_when_section_has_other_fact(self):
        body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が若手起用の意図を説明した。",
                "5-3で逃げ切った流れも振り返りたい。",
                "【次の注目】",
                "次の起用で何を続けるかを見たい。",
            ]
        )
        source_refs = {
            "category": "首脳陣",
            "source_title": "阿部監督が若手起用の意図を説明",
            "source_summary": "若手起用の意図を語った。",
        }
        with patch.dict(os.environ, {"ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR": "1"}, clear=False):
            repaired = rss_fetcher._maybe_apply_source_grounding_drift_repair(
                body_text=body,
                source_title=source_refs["source_title"],
                source_summary=source_refs["source_summary"],
                article_subtype="general",
                source_refs=source_refs,
            )

        self.assertIn("阿部監督が若手起用の意図を説明した。", repaired)
        self.assertNotIn("5-3で逃げ切った流れも振り返りたい。", repaired)

    def test_flag_on_repair_removes_ungrounded_team_and_actor_sentence(self):
        body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が若手起用の意図を説明した。",
                "戸郷翔征はブルージェイズ戦の流れにも触れた。",
                "【次の注目】",
                "次の起用で何を続けるかを見たい。",
            ]
        )
        source_refs = {
            "category": "首脳陣",
            "source_title": "阿部監督が若手起用の意図を説明",
            "source_summary": "若手起用の意図を語った。",
        }
        with patch.dict(os.environ, {"ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR": "1"}, clear=False):
            repaired = rss_fetcher._maybe_apply_source_grounding_drift_repair(
                body_text=body,
                source_title=source_refs["source_title"],
                source_summary=source_refs["source_summary"],
                article_subtype="general",
                source_refs=source_refs,
            )

        self.assertIn("阿部監督が若手起用の意図を説明した。", repaired)
        self.assertNotIn("戸郷翔征はブルージェイズ戦の流れにも触れた。", repaired)

    def test_flag_on_routes_single_sentence_ungrounded_quote_to_review(self):
        text = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が「必ず完投する」と断言した。",
                "【次の注目】",
                "次の起用に注目です。",
            ]
        )
        source_refs = {
            "category": "首脳陣",
            "source_title": "阿部監督が若手起用の意図を説明",
            "source_summary": "若手起用の意図を語った。",
        }
        with patch.dict(os.environ, {"ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR": "1"}, clear=False):
            result = rss_fetcher._evaluate_post_gen_validate(
                text,
                article_subtype="general",
                source_refs=source_refs,
            )

        self.assertFalse(result["ok"])
        self.assertIn("source_grounding_drift:quote", result["fail_axes"])


if __name__ == "__main__":
    unittest.main()
