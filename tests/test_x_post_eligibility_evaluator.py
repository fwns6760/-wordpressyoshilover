import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import x_post_eligibility_evaluator as evaluator
from src.tools import run_x_post_eligibility_evaluator as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T09:00:00+09:00")


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    status: str = "publish",
    date: str = "2026-04-25T10:00:00",
    modified: str = "2026-04-25T11:00:00",
    featured_media: int = 10,
) -> dict:
    return {
        "id": post_id,
        "title": {"raw": title, "rendered": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": "", "rendered": ""},
        "status": status,
        "date": date,
        "modified": modified,
        "link": f"https://yoshilover.com/{post_id}",
        "featured_media": featured_media,
        "meta": {"article_subtype": "postgame"},
        "categories": [],
        "tags": [],
    }


class StrictReadOnlyWPClient:
    def __init__(self, pages: dict[int, list[dict]]):
        self.pages = pages
        self.list_posts_calls: list[dict] = []
        self.write_attempted = False

    def list_posts(self, **kwargs):
        self.list_posts_calls.append(dict(kwargs))
        return json.loads(json.dumps(self.pages.get(int(kwargs["page"]), []), ensure_ascii=False))

    def update_post_fields(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")

    def update_post_status(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")


class XPostEligibilityEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.green_post = _post(
            501,
            "巨人が阪神に3-2で勝利 戸郷が7回2失点",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合をつくり、岡本和真が終盤に決勝打を放った。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T51111.html</p>"
            ),
        )
        self.yellow_post = _post(
            502,
            "巨人が中日に4-1で勝利",
            (
                "<p>巨人が中日に4-1で勝利した。先発が7回1失点で流れをつくり、打線が中盤に突き放した。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T52222.html</p>"
            ),
            featured_media=0,
        )
        self.red_post = _post(
            503,
            "巨人のポイントはどこ 阿部監督の試合前コメント",
            (
                "<p>巨人の試合前コメントを整理した。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T53333.html</p>"
            ),
        )
        self.cleanup_post = _post(
            504,
            "巨人が広島に5-2で勝利",
            (
                "<p>巨人が広島に5-2で勝利した。先発が試合をつくり、打線も中盤に追加点を重ねた。</p>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "tokens used: 10\n"
                "</pre>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T54444.html</p>"
            ),
        )
        self.draft_post = _post(
            505,
            "巨人がヤクルトに勝利",
            self.green_post["content"]["raw"],
            status="draft",
        )

    def test_evaluate_published_posts_returns_green_article_as_eligible(self):
        report = evaluator.evaluate_published_posts([self.green_post], limit=10, now=FIXED_NOW)

        self.assertEqual(report["summary"]["total"], 1)
        self.assertEqual(report["summary"]["eligible_count"], 1)
        self.assertEqual(report["summary"]["refused_count"], 0)
        self.assertEqual(report["x_eligible"][0]["post_id"], 501)
        self.assertEqual(report["x_eligible"][0]["why_eligible"], evaluator.WHY_ELIGIBLE_ALL_GREEN)

    def test_wp_gate_yellow_and_red_posts_are_refused_with_reasons(self):
        report = evaluator.evaluate_published_posts(
            [self.green_post, self.yellow_post, self.red_post],
            limit=10,
            now=FIXED_NOW,
        )

        refused_by_post = {entry["post_id"]: entry for entry in report["x_refused"]}
        self.assertEqual(report["summary"]["eligible_count"], 1)
        self.assertIn("wp_gate_yellow_missing_featured_media", refused_by_post[502]["refuse_reasons"])
        self.assertIn("wp_gate_red_speculative_title", refused_by_post[503]["refuse_reasons"])

    def test_cleanup_pending_green_article_is_refused_for_x(self):
        report = evaluator.evaluate_published_posts([self.cleanup_post], limit=10, now=FIXED_NOW)

        self.assertEqual(report["summary"]["eligible_count"], 0)
        self.assertEqual(report["summary"]["refused_count"], 1)
        self.assertEqual(report["x_refused"][0]["post_id"], 504)
        self.assertIn("x_side_red_cleanup_dev_log_contamination", report["x_refused"][0]["refuse_reasons"])

    def test_recent_history_duplicate_like_article_is_refused(self):
        history = [
            {
                "post_id": 9001,
                "title": "既に投稿した阪神戦まとめ",
                "game_key": "postgame/阪神/2026-04-25",
                "posted_at": "2026-04-26T07:30:00+09:00",
            }
        ]

        report = evaluator.evaluate_published_posts(
            [self.green_post],
            limit=10,
            now=FIXED_NOW,
            recent_x_history=history,
        )

        self.assertEqual(report["summary"]["eligible_count"], 0)
        self.assertEqual(report["summary"]["refused_count"], 1)
        self.assertIn("x_side_red_recent_x_duplicate_24h", report["x_refused"][0]["refuse_reasons"])

    def test_scan_wp_published_posts_uses_get_only_and_publish_status(self):
        wp = StrictReadOnlyWPClient({1: [self.green_post, self.draft_post, self.cleanup_post]})

        report = evaluator.scan_wp_published_posts(
            wp,
            limit=3,
            orderby="modified",
            order="desc",
            now=FIXED_NOW,
        )

        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual([call["page"] for call in wp.list_posts_calls], [1])
        self.assertTrue(all(call["status"] == "publish" for call in wp.list_posts_calls))
        self.assertFalse(wp.write_attempted)

    def test_render_human_report_shows_summary_and_preview(self):
        report = evaluator.evaluate_published_posts(
            [self.green_post, self.cleanup_post],
            limit=10,
            now=FIXED_NOW,
        )

        rendered = evaluator.render_human_report(report)

        self.assertIn("X Post Eligibility Evaluator", rendered)
        self.assertIn("Eligible Preview (top 5)", rendered)
        self.assertIn("501 | 巨人が阪神に3-2で勝利 戸郷が7回2失点", rendered)
        self.assertIn("Refused Top Reasons", rendered)

    def test_cli_fixture_mode_avoids_wp_client_and_secret_leak(self):
        fixture = {
            "now": FIXED_NOW.isoformat(),
            "posts": [self.green_post],
            "recent_x_history": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.dict(os.environ, {"X_API_KEY": "super-secret-key"}, clear=False), patch.object(
                cli, "_make_wp_client", side_effect=AssertionError("fixture mode must not build WP client")
            ):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.main(["--fixture", str(fixture_path), "--format", "json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("super-secret-key", stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["summary"]["eligible_count"], 1)

    def test_new_files_do_not_import_forbidden_x_api_or_llm_clients(self):
        targets = [
            Path(evaluator.__file__),
            Path(cli.__file__),
        ]
        forbidden_tokens = (
            "x_api_client",
            "openai",
            "anthropic",
            "google.generativeai",
            "grok",
            "xai",
        )

        for path in targets:
            source = path.read_text(encoding="utf-8").lower()
            for token in forbidden_tokens:
                self.assertNotIn(token, source, msg=f"{path.name} must not import/use {token}")


if __name__ == "__main__":
    unittest.main()
