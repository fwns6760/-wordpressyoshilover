import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import sns_topic_publish_bridge as bridge
from src.tools import run_sns_topic_publish_bridge as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T13:30:00+09:00")
LONG_EXTRA = (
    "ベンチワークの意図や終盤の継投まで追える内容で、攻守の流れも十分に整理できる一戦だった。"
    "守備位置の動きと追加点の意味も見え、ファン視点でも試合の核を追いやすかった。"
)


def _proposal(
    mock_draft_id: str,
    *,
    title_hint: str = "巨人が阪神に3-2で勝利",
    lead_hint: str = "巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合を作り、岡本和真が決勝打を放った。",
    source_urls: list[str] | None = None,
    source_recheck_passed: bool = True,
    publish_gate_required: bool = True,
    featured_media: int = 1,
    mock_body_html: str | None = None,
    meta: dict | None = None,
) -> dict:
    payload = {
        "mock_draft_id": mock_draft_id,
        "title_hint": title_hint,
        "lead_hint": lead_hint,
        "source_urls": list(source_urls or ["https://hochi.news/example"]),
        "topic_category": "player",
        "source_recheck_passed": source_recheck_passed,
        "publish_gate_required": publish_gate_required,
        "sns_topic_seed": True,
        "featured_media": featured_media,
    }
    if mock_body_html is not None:
        payload["mock_body_html"] = mock_body_html
    if meta is not None:
        payload["meta"] = meta
    return payload


def _fixture(*draft_proposals: dict) -> dict:
    return {"draft_proposals": list(draft_proposals)}


class SNSTopicPublishBridgeTests(unittest.TestCase):
    def _write_fixture(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "fixture.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _run_bridge(self, fixture_path: Path, **overrides):
        with tempfile.TemporaryDirectory() as tmpdir:
            kwargs = {
                "fixture_path": fixture_path,
                "history_path": Path(tmpdir) / "history.jsonl",
                "yellow_log_path": Path(tmpdir) / "yellow.jsonl",
                "cleanup_log_path": Path(tmpdir) / "cleanup.jsonl",
                "backup_dir": Path(tmpdir) / "cleanup_backup",
                "now": FIXED_NOW,
            }
            kwargs.update(overrides)
            report = bridge.run_sns_topic_publish_bridge(**kwargs)
            return report, Path(tmpdir)

    def test_only_source_recheck_passed_drafts_are_considered(self):
        fixture = _fixture(
            _proposal("mock_draft_a", source_recheck_passed=True),
            _proposal("mock_draft_b", source_recheck_passed=False),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)
            evaluated_post_ids: list[int] = []

            def _fake_evaluate_post(raw_post, *, now=None):
                del now
                evaluated_post_ids.append(int(raw_post["id"]))
                return {
                    "judgment": "green",
                    "entry": {
                        "post_id": int(raw_post["id"]),
                        "title": raw_post["title"]["raw"],
                        "category": "clean",
                        "publishable": True,
                        "cleanup_required": False,
                        "repairable_flags": [],
                    },
                    "cleanup_candidate": None,
                }

            with patch("src.sns_topic_publish_bridge.evaluate_post", side_effect=_fake_evaluate_post), patch(
                "src.sns_topic_publish_bridge.run_guarded_publish",
                return_value={"proposed": [], "refused": [], "summary": {}, "scan_meta": {}},
            ):
                report = bridge.run_sns_topic_publish_bridge(fixture_path=fixture_path, now=FIXED_NOW)

        self.assertEqual(len(evaluated_post_ids), 1)
        self.assertEqual(report["summary"]["source_recheck_passed_count"], 1)
        self.assertEqual(report["refused"][0]["reason"], "source_recheck_failed")

    def test_pub004_evaluator_is_mandatory_before_publish(self):
        fixture = _fixture(_proposal("mock_draft_gate"))
        order: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)

            def _fake_evaluate_post(raw_post, *, now=None):
                del now
                order.append("evaluate")
                return {
                    "judgment": "green",
                    "entry": {
                        "post_id": int(raw_post["id"]),
                        "title": raw_post["title"]["raw"],
                        "category": "clean",
                        "publishable": True,
                        "cleanup_required": False,
                        "repairable_flags": [],
                    },
                    "cleanup_candidate": None,
                }

            def _fake_runner(**kwargs):
                order.append("runner")
                report = json.loads(Path(kwargs["input_from"]).read_text(encoding="utf-8"))
                self.assertEqual(len(report["green"]), 1)
                self.assertEqual(report["yellow"], [])
                return {
                    "scan_meta": {"live": False, "max_burst": 20, "ts": FIXED_NOW.isoformat()},
                    "proposed": [
                        {
                            "post_id": report["green"][0]["post_id"],
                            "title": report["green"][0]["title"],
                            "judgment": "green",
                            "cleanup_required": False,
                            "cleanup_plan": [],
                            "post_cleanup_check": "not_required",
                            "repairable_flags": [],
                        }
                    ],
                    "refused": [],
                    "summary": {"proposed_count": 1, "refused_count": 0, "would_publish": 1, "would_skip": 0},
                }

            with patch("src.sns_topic_publish_bridge.evaluate_post", side_effect=_fake_evaluate_post), patch(
                "src.sns_topic_publish_bridge.run_guarded_publish",
                side_effect=_fake_runner,
            ):
                report = bridge.run_sns_topic_publish_bridge(fixture_path=fixture_path, now=FIXED_NOW)

        self.assertEqual(order, ["evaluate", "runner"])
        self.assertEqual(report["summary"]["publishable_count"], 1)
        self.assertEqual(report["summary"]["hard_stop_count"], 0)

    def test_hard_stop_draft_is_refused(self):
        fixture = _fixture(
            _proposal(
                "mock_draft_injury",
                title_hint="巨人の主力が故障で離脱",
                lead_hint="巨人の主力が故障で離脱した可能性があるという話題を整理する。",
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)
            report = bridge.run_sns_topic_publish_bridge(fixture_path=fixture_path, now=FIXED_NOW)

        self.assertEqual(report["summary"]["hard_stop_count"], 1)
        self.assertEqual(report["summary"]["publishable_count"], 0)
        self.assertEqual(report["proposed"], [])
        self.assertEqual(report["refused"][0]["reason"], "hard_stop")
        self.assertEqual(report["routed_drafts"][0]["evaluator_judgment"], "red")

    def test_repairable_draft_goes_through_cleanup_chain(self):
        body_html = (
            "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で今季3勝目を挙げた。</p>"
            "<p>岡本が先制打を放ち、序盤から主導権を握った。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
            "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
            "<pre>"
            "python3 -m src.tools.run_guarded_publish\n"
            "git diff --stat\n"
            "commit_hash=abc12345\n"
            "changed_files=3\n"
            "tokens used: 10\n"
            "</pre>"
        )
        fixture = _fixture(
            _proposal(
                "mock_draft_cleanup",
                title_hint="巨人が中日に5-1で勝利",
                lead_hint="巨人が中日に5-1で勝利した。戸郷が7回1失点で今季3勝目を挙げた。",
                source_urls=["https://example.com/source"],
                featured_media=1,
                mock_body_html=body_html,
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)
            history_path = Path(tmpdir) / "history.jsonl"
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            report = bridge.run_sns_topic_publish_bridge(
                fixture_path=fixture_path,
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                yellow_log_path=yellow_log_path,
                cleanup_log_path=cleanup_log_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                now=FIXED_NOW,
            )
            yellow_row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(report["summary"]["sent_count"], 1)
        self.assertEqual(report["mock_wp"]["update_post_fields_call_count"], 1)
        updated_content = report["mock_wp"]["update_post_fields_calls"][0]["fields"]["content"]
        self.assertIn("<p>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</p>", updated_content)
        self.assertNotIn("python3 -m src.tools.run_guarded_publish", updated_content)
        self.assertIn("heading_sentence_as_h3", yellow_row["applied_flags"])
        self.assertIn("dev_log_contamination", cleanup_row["applied_flags"])

    def test_dry_run_does_not_call_wp_write(self):
        fixture = _fixture(_proposal("mock_draft_dry"))

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)
            report = bridge.run_sns_topic_publish_bridge(fixture_path=fixture_path, now=FIXED_NOW)

        self.assertEqual(report["summary"]["publishable_count"], 1)
        self.assertEqual(report["mock_wp"]["update_post_fields_call_count"], 0)
        self.assertEqual(report["mock_wp"]["update_post_status_call_count"], 0)

    def test_live_mode_respects_burst_cap_20(self):
        fixture = _fixture(*[_proposal(f"mock_draft_{index}") for index in range(21)])

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)
            report = bridge.run_sns_topic_publish_bridge(
                fixture_path=fixture_path,
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                now=FIXED_NOW,
            )

        sent = [item for item in report["runner_report"]["executed"] if item["status"] == "sent"]
        skipped = [item for item in report["runner_report"]["executed"] if item["status"] == "skipped"]
        self.assertEqual(len(sent), 20)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(report["summary"]["sent_count"], 20)
        self.assertEqual(report["refused"][-1]["reason"], "burst_cap")

    def test_live_mode_respects_hard_cap_30(self):
        fixture = _fixture(_proposal("mock_draft_cap"))

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                exit_code = cli.main(["--fixture", str(fixture_path), "--max-burst", "31"])

        self.assertEqual(exit_code, 1)
        self.assertIn("--max-burst must be <= 30", stderr.getvalue())

    def test_no_x_sns_post_path(self):
        bridge_text = Path(bridge.__file__).read_text(encoding="utf-8")
        cli_text = Path(cli.__file__).read_text(encoding="utf-8")
        combined = bridge_text + "\n" + cli_text

        self.assertNotIn("src.x_api_client", combined)
        self.assertNotIn("import tweepy", combined)
        self.assertNotIn("send_email", combined)
        self.assertNotIn("requests.", combined)

    def test_sns_derived_yellow_logged_into_yellow_log(self):
        fixture = _fixture(
            _proposal(
                "mock_draft_yellow",
                featured_media=0,
                source_urls=["https://hochi.news/yellow"],
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = self._write_fixture(tmpdir, fixture)
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            report = bridge.run_sns_topic_publish_bridge(
                fixture_path=fixture_path,
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                yellow_log_path=yellow_log_path,
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                now=FIXED_NOW,
            )
            yellow_row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(report["summary"]["sent_count"], 1)
        self.assertIn("missing_featured_media", yellow_row["applied_flags"])
        self.assertEqual(yellow_row["post_id"], report["routed_drafts"][0]["post_id"])


if __name__ == "__main__":
    unittest.main()
