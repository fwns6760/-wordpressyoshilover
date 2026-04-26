import io
import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import published_cleanup_proposals as proposals
from src.tools import run_published_cleanup_proposals as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T13:00:00+09:00")
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
    date: str = "2026-04-26T10:00:00+09:00",
    modified: str = "2026-04-26T10:30:00+09:00",
    featured_media: int = 10,
    meta: dict | None = None,
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
        "meta": meta or {"article_subtype": "postgame"},
        "categories": [],
        "tags": [],
    }


class StrictReadOnlyWPClient:
    def __init__(self, posts: dict[int, dict]):
        self.posts = {int(post_id): json.loads(json.dumps(post, ensure_ascii=False)) for post_id, post in posts.items()}
        self.get_post_calls: list[int] = []
        self.write_attempted = False

    def get_post(self, post_id: int):
        self.get_post_calls.append(int(post_id))
        return json.loads(json.dumps(self.posts[int(post_id)], ensure_ascii=False))

    def create_post(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")

    def update_post_fields(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")

    def update_post_status(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")

    def delete_post(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")


class PublishedCleanupProposalTests(unittest.TestCase):
    def setUp(self):
        self.clean_post = _post(
            701,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合をつくり、岡本和真が終盤に決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.heading_post = _post(
            702,
            "巨人が中日に5-1で勝利",
            (
                "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で流れをつくり、打線も序盤から先手を取った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.site_component_post = _post(
            703,
            "巨人がヤクルトに2-1で勝利",
            (
                "<p>巨人がヤクルトに2-1で勝利した。序盤から丁寧に試合を運び、先発もリズムよく投げ込んだ。</p>"
                f"<p>{LONG_EXTRA}</p>"
                '<div class="yoshilover-related-posts"><p>関連記事</p></div>'
                "<p>終盤は継投で逃げ切り、守備でも要所を締めた。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )

    def test_proposals_for_site_component_post(self):
        wp = StrictReadOnlyWPClient({703: self.site_component_post})

        report = proposals.generate_cleanup_proposals(wp, post_ids=[703], now=FIXED_NOW)

        self.assertEqual(report["summary"]["with_proposals"], 1)
        entry = report["cleanup_proposals"][0]
        self.assertEqual(entry["post_id"], 703)
        self.assertEqual(entry["priority"], "high")
        self.assertIn("site_component_mixed_into_body", entry["repairable_flags"])
        self.assertEqual(entry["proposed_cleanups"][0]["action"], "remove_site_component_block")
        self.assertIn("(deleted)", entry["proposed_cleanups"][0]["after_excerpt"])
        self.assertFalse(wp.write_attempted)

    def test_proposals_for_heading_sentence_h3(self):
        wp = StrictReadOnlyWPClient({702: self.heading_post})

        report = proposals.generate_cleanup_proposals(wp, post_ids=[702], now=FIXED_NOW)

        self.assertEqual(report["summary"]["with_proposals"], 1)
        entry = report["cleanup_proposals"][0]
        self.assertIn("heading_sentence_as_h3", entry["repairable_flags"])
        self.assertEqual(entry["proposed_cleanups"][0]["action"], "h3_to_p_demotion")
        self.assertIn("<h3>", entry["proposed_cleanups"][0]["before_excerpt"])
        self.assertIn("<p>", entry["proposed_cleanups"][0]["after_excerpt"])

    def test_no_proposals_for_clean_post(self):
        wp = StrictReadOnlyWPClient({701: self.clean_post})

        report = proposals.generate_cleanup_proposals(wp, post_ids=[701], now=FIXED_NOW)

        self.assertEqual(report["cleanup_proposals"], [])
        self.assertEqual(report["clean_posts"], [701])
        self.assertEqual(report["summary"]["clean_count"], 1)

    def test_wp_write_call_zero(self):
        wp = StrictReadOnlyWPClient({702: self.heading_post})
        report = proposals.generate_cleanup_proposals(wp, post_ids=[702], now=FIXED_NOW)

        self.assertEqual(report["summary"]["with_proposals"], 1)
        self.assertEqual(wp.get_post_calls, [702])
        self.assertFalse(wp.write_attempted)

        forbidden = re.compile(r"create_post|update_post|delete_post|requests\.(post|put|delete)")
        for source_path in (Path(proposals.__file__), Path(cli.__file__)):
            self.assertIsNone(forbidden.search(source_path.read_text(encoding="utf-8")))

    def test_history_fallback_loads_today_publish(self):
        wp = StrictReadOnlyWPClient(
            {
                702: self.heading_post,
                703: self.site_component_post,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "post_id": 703,
                                "ts": "2026-04-26T12:10:00+09:00",
                                "status": "sent",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "post_id": 702,
                                "ts": "2026-04-26T11:40:00+09:00",
                                "status": "sent",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "post_id": 703,
                                "ts": "2026-04-26T11:00:00+09:00",
                                "status": "sent",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "post_id": 900,
                                "ts": "2026-04-26T10:30:00+09:00",
                                "status": "refused",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "post_id": 901,
                                "ts": "2026-04-25T23:50:00+09:00",
                                "status": "sent",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = proposals.generate_cleanup_proposals(
                wp,
                history_path=history_path,
                now=FIXED_NOW,
            )

        self.assertEqual(report["scan_meta"]["source"], "today_publish_history")
        self.assertEqual(report["scan_meta"]["target_post_ids"], [703, 702])
        self.assertEqual(wp.get_post_calls, [703, 702])
        self.assertEqual(report["summary"]["with_proposals"], 2)

    def test_cli_main_writes_json_output(self):
        report = proposals.generate_cleanup_proposals(
            StrictReadOnlyWPClient({702: self.heading_post}),
            post_ids=[702],
            now=FIXED_NOW,
        )
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "cleanup.json"
            with patch.object(cli, "_make_wp_client"), patch.object(
                cli, "generate_cleanup_proposals", return_value=report
            ), patch("sys.stdout", stdout):
                exit_code = cli.main(["--post-ids", "702", "--format", "json", "--output", str(output_path)])

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["with_proposals"], 1)
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
