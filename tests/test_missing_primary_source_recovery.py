import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import missing_primary_source_recovery as audit
from src.tools import run_missing_primary_source_audit as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T09:00:00+09:00")


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    modified: str = "2026-04-26T08:00:00",
    date: str = "2026-04-26T07:00:00",
    excerpt: str = "",
    meta: dict | None = None,
) -> dict:
    payload = {
        "id": post_id,
        "title": {"raw": title, "rendered": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": excerpt, "rendered": excerpt},
        "status": "draft",
        "date": date,
        "modified": modified,
        "link": f"https://yoshilover.com/{post_id}",
        "featured_media": 10,
        "categories": [],
        "tags": [],
    }
    if meta is not None:
        payload["meta"] = meta
    return payload


class StrictReadOnlyWPClient:
    def __init__(self, pages: dict[int, list[dict]]):
        self.pages = pages
        self.list_posts_calls: list[dict] = []
        self.get_post_calls: list[int] = []
        self.write_attempted = False

    def list_posts(self, **kwargs):
        self.list_posts_calls.append(dict(kwargs))
        page = int(kwargs.get("page", 1))
        return json.loads(json.dumps(self.pages.get(page, []), ensure_ascii=False))

    def get_post(self, post_id: int):
        self.get_post_calls.append(int(post_id))
        raise AssertionError("get_post should not be needed for this audit")

    def update_post_fields(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")

    def update_post_status(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")


class MissingPrimarySourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.no_source_anywhere = _post(
            901,
            "巨人が室内調整",
            "<p>巨人が室内練習で調整した。試合前の動きと打撃練習の様子を整理した。</p>",
        )
        self.source_name_only = _post(
            902,
            "巨人が打線を確認",
            "<p>スポーツ報知によると、阿部監督が打線の並びを確認した。</p>",
        )
        self.footer_only_no_url = _post(
            903,
            "巨人が阪神戦へ調整",
            (
                "<p>巨人が阪神戦へ向けて調整した。</p>"
                "<p>参照元:<br>スポーツ報知<br>https://hochi.news/articles/20260426-OHT1T50003.html</p>"
            ),
        )
        self.meta_only_no_body = _post(
            904,
            "巨人が試合前に最終確認",
            "<p>巨人が試合前に守備位置と継投の順番を最終確認した。</p>",
            meta={"_yoshilover_source_url": "https://hochi.news/articles/20260426-OHT1T50004.html"},
        )
        self.twitter_only = _post(
            905,
            "巨人が球場入り",
            (
                "<p>巨人が球場入りした。</p>"
                "<p>参照元: https://x.com/yoshilover6760/status/1911111111111111111</p>"
            ),
        )
        self.social_news_subtype = _post(
            906,
            "巨人公式Xの投稿まとめ",
            (
                "<p>巨人公式Xの投稿をもとに球場の雰囲気を整理した。</p>"
                "<p>https://x.com/TokyoGiants/status/1912222222222222222</p>"
            ),
            meta={"source_type": "social_news", "article_subtype": "social"},
        )
        self.clean = _post(
            907,
            "巨人が広島に勝利",
            (
                "<p>スポーツ報知によると、巨人が広島に勝利した。</p>"
                '<p>参照元: <a href="https://hochi.news/articles/20260426-OHT1T50007.html">スポーツ報知</a></p>'
            ),
        )
        self.old = _post(
            908,
            "古い下書き",
            "<p>スポーツ報知によると、古い下書きの確認メモ。</p>",
            modified="2026-04-20T08:00:00",
            date="2026-04-20T07:00:00",
        )

    def test_audit_raw_posts_classifies_all_six_cause_tags(self):
        report = audit.audit_raw_posts(
            [
                self.no_source_anywhere,
                self.source_name_only,
                self.footer_only_no_url,
                self.meta_only_no_body,
                self.twitter_only,
                self.social_news_subtype,
                self.clean,
                self.old,
            ],
            window_hours=96,
            max_pool=20,
            now=FIXED_NOW,
        )

        self.assertEqual(report["scan_meta"]["scanned"], 7)
        self.assertEqual(report["summary"]["total_drafts_in_pool"], 7)
        self.assertEqual(report["missing_primary_source_count"], 6)
        self.assertEqual(report["summary"]["no_primary_source_count"], 6)
        self.assertEqual(report["summary"]["rescue_pct"], 66.7)

        by_cause = report["by_cause_tag"]
        self.assertEqual(by_cause["no_source_anywhere"]["count"], 1)
        self.assertEqual(by_cause["source_name_only"]["count"], 1)
        self.assertEqual(by_cause["footer_only_no_url"]["count"], 1)
        self.assertEqual(by_cause["meta_only_no_body"]["count"], 1)
        self.assertEqual(by_cause["twitter_only"]["count"], 1)
        self.assertEqual(by_cause["social_news_subtype"]["count"], 1)

        self.assertEqual(by_cause["no_source_anywhere"]["samples"][0]["post_id"], 901)
        self.assertEqual(by_cause["source_name_only"]["samples"][0]["post_id"], 902)
        self.assertEqual(by_cause["footer_only_no_url"]["samples"][0]["post_id"], 903)
        self.assertEqual(by_cause["meta_only_no_body"]["samples"][0]["post_id"], 904)
        self.assertEqual(by_cause["twitter_only"]["samples"][0]["post_id"], 905)
        self.assertEqual(by_cause["social_news_subtype"]["samples"][0]["post_id"], 906)

        rescue_tags = [item["cause_tag"] for item in report["rescue_candidates"]]
        self.assertEqual(
            rescue_tags,
            [
                "footer_only_no_url",
                "meta_only_no_body",
                "source_name_only",
                "social_news_subtype",
            ],
        )

    def test_scan_wp_drafts_paginates_and_uses_get_only(self):
        page_one = [
            _post(
                1000 + index,
                f"下書き {index}",
                "<p>一次情報の記載がない下書き。</p>",
            )
            for index in range(100)
        ]
        page_two = [_post(2001, "追加の下書き", "<p>一次情報の記載がない下書き。</p>")]
        wp = StrictReadOnlyWPClient({1: page_one, 2: page_two})

        report = audit.scan_wp_drafts(
            wp,
            window_hours=96,
            max_pool=101,
            now=FIXED_NOW,
        )

        self.assertEqual(report["scan_meta"]["fetched"], 101)
        self.assertEqual(report["scan_meta"]["scanned"], 101)
        self.assertEqual(report["missing_primary_source_count"], 101)
        self.assertEqual([call["page"] for call in wp.list_posts_calls], [1, 2])
        self.assertEqual([call["per_page"] for call in wp.list_posts_calls], [100, 1])
        self.assertTrue(all(call["status"] == "draft" for call in wp.list_posts_calls))
        self.assertEqual(wp.get_post_calls, [])
        self.assertFalse(wp.write_attempted)

    def test_render_human_report_shows_summary_cause_tags_and_rescue_lines(self):
        report = audit.audit_raw_posts(
            [
                self.no_source_anywhere,
                self.source_name_only,
                self.footer_only_no_url,
                self.meta_only_no_body,
                self.twitter_only,
                self.social_news_subtype,
            ],
            now=FIXED_NOW,
        )

        rendered = audit.render_human_report(report)

        self.assertIn("Missing Primary Source Audit", rendered)
        self.assertIn("Cause Tags", rendered)
        self.assertIn("footer_only_no_url", rendered)
        self.assertIn("Rescue Candidates", rendered)
        self.assertIn("meta source_url を body の参照元ブロックへ反映", rendered)

    def test_cli_main_writes_json_output_without_wp_write(self):
        report = audit.audit_raw_posts([self.footer_only_no_url], now=FIXED_NOW)
        fake_wp = StrictReadOnlyWPClient({})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "audit.json"
            with patch.object(cli, "_make_wp_client", return_value=fake_wp), patch.object(
                cli, "scan_wp_drafts", return_value=report
            ):
                exit_code = cli.main(
                    [
                        "--window-hours",
                        "96",
                        "--max-pool",
                        "200",
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    ]
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["missing_primary_source_count"], 1)
        self.assertFalse(fake_wp.write_attempted)

    def test_cli_main_prints_human_output_to_stdout(self):
        report = audit.audit_raw_posts([self.source_name_only], now=FIXED_NOW)
        stdout = io.StringIO()

        with patch.object(cli, "_make_wp_client"), patch.object(cli, "scan_wp_drafts", return_value=report), patch(
            "sys.stdout", stdout
        ):
            exit_code = cli.main(["--format", "human"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Missing Primary Source Audit", stdout.getvalue())

    def test_new_files_do_not_import_llm_or_write_clients(self):
        targets = [
            Path(audit.__file__),
            Path(cli.__file__),
        ]
        forbidden_tokens = (
            "openai",
            "anthropic",
            "google.generativeai",
            "grok",
            "xai",
            "x_api_client",
        )

        for path in targets:
            source = path.read_text(encoding="utf-8").lower()
            for token in forbidden_tokens:
                self.assertNotIn(token, source, msg=f"{path.name} must not import/use {token}")


if __name__ == "__main__":
    unittest.main()
