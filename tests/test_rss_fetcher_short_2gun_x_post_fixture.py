import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src import article_quality_guards, body_validator, rss_fetcher


KEYWORDS = json.loads(
    (Path(__file__).resolve().parent.parent / "config" / "keywords.json").read_text(encoding="utf-8")
)
FIXTURE = {
    "title": "【巨人】小浜佑斗が意表を突くホームスチール！２軍合流で再出発打→ヘッスラ生還",
    "summary": "【巨人】小浜佑斗が意表を突くホームスチール！２軍合流で再出発打→ヘッスラ生還",
    "source_url": "https://x.com/hochi_giants/status/2051533159368388916?s=20",
    "source_name": "スポーツ報知巨人取材班X",
    "source_type": "social_news",
    "has_game": False,
    "source_handle": "hochi_giants",
}
RELATED_POSTS = [
    {
        "title": "巨人二軍 小浜佑斗の直近出場を整理",
        "link": "https://yoshilover.com/archives/205100",
    }
]
BASE_FLAGS = {
    "ENABLE_DUPLICATE_SENTENCE_GUARD": "1",
    "ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "0",
    "ENABLE_FARM_SHORT_POST_TEMPLATE": "0",
}


class RSSFetcherShort2GunXPostFixtureTests(unittest.TestCase):
    def _routing_context(self) -> tuple[str, dict[str, object]]:
        category = rss_fetcher.classify_category(FIXTURE["title"], KEYWORDS)
        context = rss_fetcher._resolve_rss_story_type_context(
            title=FIXTURE["title"],
            summary=FIXTURE["summary"],
            category=category,
            daily_has_game=FIXTURE["has_game"],
            source_type=FIXTURE["source_type"],
            source_url=FIXTURE["source_url"],
            source_name=FIXTURE["source_name"],
        )
        return category, context

    def _rescue_meta(self) -> tuple[bool, dict | None]:
        return rss_fetcher._evaluate_authoritative_social_entry(
            FIXTURE["title"],
            FIXTURE["summary"],
            "ドラフト・育成",
            "farm",
            source_name=FIXTURE["source_name"],
            source_handle=FIXTURE["source_handle"],
            source_url=FIXTURE["source_url"],
        )

    def _render_case(
        self,
        *,
        flag_overrides: dict[str, str] | None = None,
        capture_logs: bool = False,
    ) -> tuple[str, str, dict[str, object], dict[str, object], list[dict[str, object]]]:
        env = {**BASE_FLAGS, **(flag_overrides or {})}
        logs: list[dict[str, object]] = []

        def _build_body() -> str:
            return rss_fetcher._maybe_build_short_source_narrow_body(
                title=FIXTURE["title"],
                summary=FIXTURE["summary"],
                category="ドラフト・育成",
                body_subtype="farm",
                source_url=FIXTURE["source_url"],
                source_name=FIXTURE["source_name"],
                source_day_label="",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )

        with patch.dict(os.environ, env, clear=False):
            if capture_logs:
                with self.assertLogs("rss_fetcher", level="INFO") as cm:
                    ai_body = _build_body()
                for record in cm.records:
                    message = record.getMessage()
                    if message.startswith("{"):
                        logs.append(json.loads(message))
            else:
                ai_body = _build_body()

        content = ""
        if ai_body:
            with patch.dict(os.environ, env, clear=False):
                with patch.object(rss_fetcher, "fetch_fan_reactions_from_yahoo", return_value=[]):
                    with patch.object(rss_fetcher, "_find_related_posts_for_article", return_value=RELATED_POSTS):
                        with patch.object(rss_fetcher, "generate_article_with_gemini", return_value=""):
                            with patch.object(rss_fetcher, "_apply_article_guardrails", side_effect=lambda *args: args[3]):
                                content, _ = rss_fetcher.build_news_block(
                                    title=FIXTURE["title"],
                                    summary=FIXTURE["summary"],
                                    url=FIXTURE["source_url"],
                                    source_name=FIXTURE["source_name"],
                                    category="ドラフト・育成",
                                    has_game=FIXTURE["has_game"],
                                    source_type=FIXTURE["source_type"],
                                    article_ai_mode_override="gemini",
                                )

        with patch.dict(os.environ, env, clear=False):
            body_validation = body_validator.validate_body_candidate(
                ai_body,
                "farm",
                rendered_html=content,
                source_context={"title": FIXTURE["title"]},
            )
            post_validation = rss_fetcher._evaluate_post_gen_validate(
                ai_body,
                article_subtype="farm",
                title=FIXTURE["title"],
                rendered_html=rss_fetcher._render_preview_body_html(ai_body),
            )
        return content, ai_body, body_validation, post_validation, logs

    @staticmethod
    def _first_body_line(ai_body: str) -> str:
        for line in ai_body.splitlines():
            stripped = line.strip()
            if stripped and not (stripped.startswith("【") and "】" in stripped):
                return stripped
        return ""

    def test_flag_off_keeps_existing_skip_behavior_for_2gun_short_post(self):
        worthy, rescue_meta = self._rescue_meta()
        self.assertTrue(worthy)
        self.assertEqual(rescue_meta["rescue_reason"], "zenkaku_2gun")
        category, context = self._routing_context()
        self.assertEqual(category, "ドラフト・育成")
        self.assertEqual(context["title_subtype"], "farm")
        self.assertEqual(context["body_subtype"], "farm")
        self.assertEqual(context["validator_subtype"], "farm")

        _, ai_body, body_validation, post_validation, _ = self._render_case(
            flag_overrides={"ENABLE_SHORT_SOURCE_NARROW_TEMPLATE": "1"}
        )

        self.assertTrue(body_validation["ok"])
        self.assertFalse(post_validation["ok"])
        self.assertIn("duplicate_sentence:near_duplicate_sentence", post_validation["fail_axes"])
        self.assertIn("【二軍個別選手成績】", ai_body)

    def test_flag_on_creates_draft_for_2gun_short_post_without_near_duplicate(self):
        worthy, rescue_meta = self._rescue_meta()
        self.assertTrue(worthy)
        self.assertEqual(rescue_meta["rescue_reason"], "zenkaku_2gun")

        _, ai_body, body_validation, post_validation, logs = self._render_case(
            flag_overrides={"ENABLE_FARM_SHORT_POST_TEMPLATE": "1"},
            capture_logs=True,
        )

        self.assertTrue(body_validation["ok"])
        self.assertTrue(post_validation["ok"])
        self.assertFalse(any(axis.startswith("duplicate_sentence:") for axis in post_validation["fail_axes"]))
        template_logs = [payload for payload in logs if payload.get("event") == "farm_short_post_template_used"]
        self.assertEqual(len(template_logs), 1)
        self.assertEqual(template_logs[0]["source_url"], FIXTURE["source_url"])
        self.assertEqual(template_logs[0]["subtype"], "farm")
        self.assertEqual(template_logs[0]["body_length"], len(ai_body))

    def test_flag_on_body_under_300_chars(self):
        _, ai_body, _body_validation, post_validation, _ = self._render_case(
            flag_overrides={"ENABLE_FARM_SHORT_POST_TEMPLATE": "1"}
        )

        self.assertTrue(post_validation["ok"])
        self.assertLess(len(ai_body), 300)

    def test_flag_on_no_paraphrase_of_title_in_body_lead(self):
        _, ai_body, _body_validation, post_validation, _ = self._render_case(
            flag_overrides={"ENABLE_FARM_SHORT_POST_TEMPLATE": "1"}
        )

        lead_line = self._first_body_line(ai_body)
        title_fact = rss_fetcher._strip_title_prefix(FIXTURE["title"])
        overlap = rss_fetcher._body_dup_reduction_ngram_overlap(FIXTURE["title"], lead_line)

        self.assertTrue(post_validation["ok"])
        self.assertNotEqual(lead_line, title_fact)
        self.assertLess(overlap, 0.55)

    def test_flag_on_preserves_source_link_and_related_post(self):
        content, ai_body, body_validation, post_validation, _ = self._render_case(
            flag_overrides={"ENABLE_FARM_SHORT_POST_TEMPLATE": "1"}
        )

        self.assertTrue(body_validation["ok"])
        self.assertTrue(post_validation["ok"])
        self.assertIn(f"出典: {FIXTURE['source_url']}", ai_body)
        self.assertIn("yoshilover-related-posts", content)
        self.assertIn(RELATED_POSTS[0]["title"], content)
        self.assertIn(RELATED_POSTS[0]["link"], content)
        self.assertIn(FIXTURE["source_url"].replace("&", "&amp;"), content)

    def test_flag_on_does_not_relax_validator_threshold(self):
        self.assertEqual(article_quality_guards.find_duplicate_sentence.__defaults__, (0.9,))

        issue = article_quality_guards.find_duplicate_sentence(
            "\n".join(
                [
                    "【試合結果】",
                    "巨人が阪神に3-2で勝利した。",
                    "【ハイライト】",
                    "巨人が阪神に3-2で勝利した。",
                ]
            )
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["reason"], "near_duplicate_sentence")


if __name__ == "__main__":
    unittest.main()
