import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import published_site_component_audit as audit
from src.tools import run_published_site_component_audit as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T09:00:00+09:00")
LONG_EXTRA = (
    "試合全体の流れと継投の意味まで追える内容で、打線のつながりや守備面の整理もしやすかった。"
    "ファンが試合の核をつかみやすい情報量を保ち、終盤の判断材料も十分に残っていた。"
)


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    status: str = "publish",
    date: str = "2026-04-24T10:00:00",
    modified: str = "2026-04-24T11:00:00",
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
        "featured_media": 10,
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


class PublishedSiteComponentAuditTests(unittest.TestCase):
    def setUp(self):
        self.clean_post = _post(
            101,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合をつくり、岡本和真が終盤に決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.heading_post = _post(
            102,
            "巨人が中日に5-1で勝利",
            (
                "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で流れをつくり、打線も序盤から先手を取った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.dev_log_post = _post(
            103,
            "巨人が広島に3-1で勝利",
            (
                "<p>巨人が広島に3-1で勝利した。先発が試合を作り、打線も追加点を重ねた。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "tokens used: 10\n"
                "</pre>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.weird_heading_post = _post(
            104,
            "巨人がDeNAに4-1で勝利",
            (
                "<p>巨人がDeNAに4-1で勝利した。先発が試合をつくり、打線も中盤に追加点を挙げた。</p>"
                "<h3>スタメン</h3>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>阿部監督が試合後に継投の意図を詳しく語り、終盤の勝ち筋を説明した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.site_middle_post = _post(
            105,
            "巨人がヤクルトに2-1で勝利",
            (
                "<p>巨人がヤクルトに2-1で勝利した。序盤から丁寧に試合を運び、先発もリズムよく投げ込んだ。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>【関連記事】</p>"
                "<p>終盤は継投で逃げ切り、守備でも要所を締めた。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.site_tail_post = _post(
            106,
            "巨人が西武に6-2で勝利",
            (
                "<p>巨人が西武に6-2で勝利した。打線が中盤に突き放し、救援陣もリードを守った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
                "<p>💬 ファンの声</p>"
            ),
        )

    def test_audit_published_posts_collects_proposals_and_summary_counts(self):
        report = audit.audit_published_posts(
            [
                self.clean_post,
                self.heading_post,
                self.dev_log_post,
                self.weird_heading_post,
                self.site_middle_post,
                self.site_tail_post,
            ],
            limit=10,
            now=FIXED_NOW,
        )

        self.assertEqual(report["summary"]["total"], 6)
        self.assertEqual(report["summary"]["with_proposals"], 5)
        self.assertEqual(report["clean_posts"], [101])
        self.assertEqual(
            report["summary"]["by_type"],
            {
                "heading_sentence_as_h3": 1,
                "dev_log_contamination": 1,
                "weird_heading_label": 1,
                "site_component_middle": 1,
                "site_component_tail": 1,
            },
        )

        by_post_id = {entry["post_id"]: entry for entry in report["cleanup_proposals"]}
        self.assertEqual(by_post_id[102]["detected_types"], ["heading_sentence_as_h3"])
        self.assertEqual(
            by_post_id[102]["proposed_diff_preview"]["heading_sentence_as_h3"][0]["would_become"],
            "<p>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</p>",
        )
        self.assertEqual(by_post_id[103]["detected_types"], ["dev_log_contamination"])
        self.assertTrue(by_post_id[103]["proposed_diff_preview"]["dev_log_contamination"][0]["would_delete"])
        self.assertEqual(by_post_id[104]["detected_types"], ["weird_heading_label"])
        self.assertTrue(
            by_post_id[104]["proposed_diff_preview"]["weird_heading_label"][0]["would_require_manual_review"]
        )
        self.assertEqual(by_post_id[105]["detected_types"], ["site_component_mixed_into_body_middle"])
        self.assertEqual(
            by_post_id[105]["proposed_diff_preview"]["site_component_mixed_into_body"][0]["verdict"],
            "middle/Red",
        )
        self.assertEqual(by_post_id[106]["detected_types"], ["site_component_mixed_into_body_tail"])
        self.assertEqual(
            by_post_id[106]["proposed_diff_preview"]["site_component_mixed_into_body"][0]["verdict"],
            "tail/Yellow",
        )

    def test_scan_wp_published_posts_excludes_today_by_default_and_uses_get_only(self):
        today_post = _post(
            201,
            "巨人が今日も勝利",
            self.clean_post["content"]["raw"],
            date="2026-04-26T07:30:00",
            modified="2026-04-26T08:00:00",
        )
        older_post_a = _post(202, "巨人が阪神に勝利", self.clean_post["content"]["raw"])
        older_post_b = _post(203, "巨人が中日に勝利", self.clean_post["content"]["raw"])
        wp = StrictReadOnlyWPClient({1: [today_post, older_post_a], 2: [older_post_b]})

        report = audit.scan_wp_published_posts(
            wp,
            limit=2,
            orderby="modified",
            order="desc",
            include_todays_publishes=False,
            now=FIXED_NOW,
        )

        self.assertEqual(report["scan_meta"]["scanned"], 2)
        self.assertEqual(report["scan_meta"]["skipped_today"], 1)
        self.assertEqual(report["clean_posts"], [202, 203])
        self.assertEqual([call["page"] for call in wp.list_posts_calls], [1, 2])
        self.assertTrue(all(call["status"] == "publish" for call in wp.list_posts_calls))
        self.assertFalse(wp.write_attempted)

    def test_scan_wp_published_posts_can_include_todays_publishes(self):
        today_post = _post(
            301,
            "巨人が今日も勝利",
            self.heading_post["content"]["raw"],
            date="2026-04-26T06:30:00",
            modified="2026-04-26T07:00:00",
        )
        older_post = _post(302, "巨人が昨日勝利", self.clean_post["content"]["raw"])
        wp = StrictReadOnlyWPClient({1: [today_post, older_post]})

        report = audit.scan_wp_published_posts(
            wp,
            limit=2,
            include_todays_publishes=True,
            now=FIXED_NOW,
        )

        self.assertEqual(report["scan_meta"]["scanned"], 2)
        self.assertEqual(report["scan_meta"]["skipped_today"], 0)
        self.assertEqual(report["cleanup_proposals"][0]["post_id"], 301)
        self.assertIn("heading_sentence_as_h3", report["cleanup_proposals"][0]["detected_types"])

    def test_render_human_report_shows_summary_and_top_proposals(self):
        report = audit.audit_published_posts(
            [self.clean_post, self.heading_post, self.dev_log_post],
            limit=3,
            now=FIXED_NOW,
        )

        rendered = audit.render_human_report(report)

        self.assertIn("Published Site Component Cleanup Audit", rendered)
        self.assertIn("with_proposals", rendered)
        self.assertIn("heading_sentence_as_h3", rendered)
        self.assertIn("Cleanup Proposals (top 10)", rendered)
        self.assertIn("102 | 巨人が中日に5-1で勝利 | heading_sentence_as_h3", rendered)

    def test_cli_main_writes_json_output_without_wp_write(self):
        report = audit.audit_published_posts([self.heading_post], limit=1, now=FIXED_NOW)
        fake_wp = StrictReadOnlyWPClient({})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "audit.json"
            with patch.object(cli, "_make_wp_client", return_value=fake_wp), patch.object(
                cli, "scan_wp_published_posts", return_value=report
            ):
                exit_code = cli.main(
                    [
                        "--limit",
                        "1",
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    ]
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["with_proposals"], 1)
        self.assertFalse(fake_wp.write_attempted)

    def test_cli_main_prints_human_output_to_stdout(self):
        report = audit.audit_published_posts([self.dev_log_post], limit=1, now=FIXED_NOW)
        stdout = io.StringIO()

        with patch.object(cli, "_make_wp_client"), patch.object(
            cli, "scan_wp_published_posts", return_value=report
        ), patch("sys.stdout", stdout):
            exit_code = cli.main(["--limit", "1", "--format", "human"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Published Site Component Cleanup Audit", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
