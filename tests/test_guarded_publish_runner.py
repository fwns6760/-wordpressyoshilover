import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import guarded_publish_runner as runner
from src.tools import run_guarded_publish as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T08:00:00+09:00")
LONG_EXTRA = (
    "ベンチワークの意図や終盤の継投まで追える内容で、攻守の流れも十分に整理できる一戦だった。"
    "守備位置の動きと追加点の意味も見え、ファン視点でも試合の核を追いやすかった。"
)


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    status: str = "draft",
    link: str | None = None,
) -> dict:
    return {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": "", "rendered": ""},
        "meta": {"article_subtype": "postgame"},
        "modified": "2026-04-26T06:55:00",
        "status": status,
        "link": link or f"https://yoshilover.com/{post_id}",
        "categories": [],
        "tags": [],
    }


def _green_entry(post_id: int, title: str) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "category": "clean",
        "publishable": True,
        "cleanup_required": False,
        "repairable_flags": [],
    }


def _repairable_entry(post_id: int, title: str, *flags: str, yellow_reasons=None) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "category": "repairable",
        "publishable": True,
        "cleanup_required": True,
        "repairable_flags": list(flags),
        "yellow_reasons": list(yellow_reasons or []),
    }


def _hard_stop_entry(post_id: int, title: str, *flags: str) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "category": "hard_stop",
        "publishable": False,
        "cleanup_required": False,
        "hard_stop_flags": list(flags),
        "red_flags": list(flags),
    }


def _report(*, green=None, yellow=None, red=None, cleanup_candidates=None) -> dict:
    return {
        "scan_meta": {"window_hours": 96, "max_pool": 10, "scanned": 0, "ts": FIXED_NOW.isoformat()},
        "green": list(green or []),
        "yellow": list(yellow or []),
        "red": list(red or []),
        "cleanup_candidates": list(cleanup_candidates or []),
        "summary": {},
    }


class FakeWPClient:
    def __init__(self, posts: dict[int, dict]):
        self.posts = posts
        self.get_post_calls: list[int] = []
        self.update_post_fields_calls: list[tuple[int, dict]] = []
        self.update_post_status_calls: list[tuple[int, str]] = []

    def get_post(self, post_id: int) -> dict:
        self.get_post_calls.append(post_id)
        return json.loads(json.dumps(self.posts[post_id], ensure_ascii=False))

    def update_post_fields(self, post_id: int, **fields) -> None:
        self.update_post_fields_calls.append((post_id, fields))
        post = self.posts[post_id]
        if "status" in fields:
            post["status"] = fields["status"]
        if "content" in fields:
            post["content"] = {"raw": fields["content"], "rendered": fields["content"]}

    def update_post_status(self, post_id: int, status: str) -> None:
        self.update_post_status_calls.append((post_id, status))
        self.posts[post_id]["status"] = status


class GuardedPublishRunnerTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_dry_run_keeps_wp_write_zero(self):
        post = _post(
            101,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合を作り、岡本和真が終盤に決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(green=[_green_entry(101, post["title"]["raw"])])
        wp = FakeWPClient({101: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                wp_client=wp,
                history_path=Path(tmpdir) / "history.jsonl",
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["proposed_count"], 1)
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_gate_refuses_live_without_daily_cap_allow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            with self.assertRaises(runner.GuardedPublishAbortError):
                runner.run_guarded_publish(
                    input_from=path,
                    live=True,
                    daily_cap_allow=False,
                    now=FIXED_NOW,
                )

    def test_cap_hard_30_above_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                exit_code = cli.main(
                    [
                        "--input-from",
                        str(path),
                        "--max-burst",
                        "31",
                    ]
                )
        self.assertEqual(exit_code, 1)
        self.assertIn("--max-burst must be <= 30", stderr.getvalue())

    def test_cli_live_without_daily_cap_allow_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                exit_code = cli.main(
                    [
                        "--input-from",
                        str(path),
                        "--live",
                    ]
                )
        self.assertEqual(exit_code, 1)
        self.assertIn("--live requires --daily-cap-allow", stderr.getvalue())

    def test_cap_default_20_burst_enforced(self):
        posts = {
            900 + index: _post(
                900 + index,
                f"巨人が試合{index + 1}に勝利",
                (
                    f"<p>巨人が試合{index + 1}に勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p>"
                    f"<p>{LONG_EXTRA}</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source</p>"
                ),
            )
            for index in range(21)
        }
        report = _report(green=[_green_entry(post_id, post["title"]["raw"]) for post_id, post in posts.items()])
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        sent = [item for item in result["executed"] if item["status"] == "sent"]
        skipped = [item for item in result["executed"] if item["status"] == "skipped"]
        self.assertEqual(len(sent), 20)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(result["refused"][-1]["reason"], "burst_cap")
        self.assertEqual([row["hold_reason"] for row in rows if row["status"] == "skipped"], ["burst_cap"])

    def test_daily_cap_100_enforced(self):
        posts = {
            1001: _post(1001, "巨人が阪神に3-2で勝利", f"<p>巨人が阪神に3-2で勝利した。投打が噛み合い、終盤まで試合を支配した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            1002: _post(1002, "巨人が中日に4-1で勝利", f"<p>巨人が中日に4-1で勝利した。先発が試合をつくり、打線も中盤に追加点を挙げた。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
        }
        report = _report(
            green=[
                _green_entry(1001, posts[1001]["title"]["raw"]),
                _green_entry(1002, posts[1002]["title"]["raw"]),
            ]
        )
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_lines = [
                json.dumps(
                    {
                        "post_id": 1100 + index,
                        "ts": "2026-04-26T01:00:00+09:00",
                        "status": "sent",
                        "backup_path": "/tmp/backup.json",
                        "error": None,
                        "judgment": "green",
                    },
                    ensure_ascii=False,
                )
                for index in range(99)
            ]
            history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        sent = [item for item in result["executed"] if item["status"] == "sent"]
        skipped = [item for item in result["executed"] if item["status"] == "skipped"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(result["refused"][-1]["reason"], "daily_cap")

    def test_hard_stop_post_skipped_no_global_abort(self):
        green_post = _post(
            801,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合を作り、岡本和真が決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            green=[_green_entry(801, green_post["title"]["raw"])],
            red=[_hard_stop_entry(800, "巨人の主力が故障で離脱", "injury_death")],
        )
        wp = FakeWPClient({801: green_post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual([item["status"] for item in result["executed"]], ["refused", "sent"])
        self.assertEqual(rows[0]["hold_reason"], "hard_stop_injury_death")
        self.assertEqual(wp.update_post_status_calls, [(801, "publish")])

    def test_repairable_post_cleanup_then_publish(self):
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
        post = _post(301, "巨人が中日に5-1で勝利", body_html)
        report = _report(
            yellow=[
                _repairable_entry(
                    301,
                    post["title"]["raw"],
                    "heading_sentence_as_h3",
                    "dev_log_contamination",
                    yellow_reasons=["heading_sentence_as_h3", "dev_log_contamination"],
                )
            ],
            cleanup_candidates=[
                {
                    "post_id": 301,
                    "cleanup_types": ["heading_sentence_as_h3", "dev_log_contamination"],
                    "repairable_flags": ["heading_sentence_as_h3", "dev_log_contamination"],
                }
            ],
        )
        wp = FakeWPClient({301: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=yellow_log_path,
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())
            yellow_row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(history_row["cleanup_required"], True)
        self.assertEqual(history_row["cleanup_success"], True)
        self.assertIsNone(history_row["hold_reason"])
        self.assertEqual(yellow_row["applied_flags"], ["heading_sentence_as_h3", "dev_log_contamination"])
        self.assertEqual(cleanup_row["applied_flags"], ["heading_sentence_as_h3", "dev_log_contamination"])
        self.assertEqual(wp.update_post_fields_calls[0][0], 301)
        self.assertIn("<p>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</p>", wp.update_post_fields_calls[0][1]["content"])
        self.assertNotIn("python3 -m src.tools.run_guarded_publish", wp.update_post_fields_calls[0][1]["content"])

    def test_repairable_post_cleanup_failed_post_condition_held_prose_short(self):
        post = _post(
            302,
            "巨人が阪神に1-0で勝利",
            (
                "<p>巨人が勝った。</p>"
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
        report = _report(
            yellow=[_repairable_entry(302, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 302, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({302: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(result["executed"][0]["hold_reason"], "cleanup_failed_post_condition")
        self.assertEqual(history_row["hold_reason"], "cleanup_failed_post_condition")
        self.assertTrue(history_row["backup_path"])
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_repairable_post_cleanup_source_lost_held(self):
        post = _post(
            303,
            "巨人がヤクルトに3-2で勝利",
            (
                "<p>巨人がヤクルトに3-2で勝利した。終盤の一打で試合を決め、継投でも逃げ切った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<pre>"
                "参照元: スポーツ報知 https://example.com/source\n"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "</pre>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(303, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 303, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({303: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(history_row["hold_reason"], "cleanup_failed_post_condition")
        self.assertIn("source_", history_row["error"])

    def test_repairable_post_cleanup_title_subject_lost_held(self):
        post = _post(
            304,
            "岡本和真が阪神戦で決勝打",
            (
                "<p>阪神戦で勝ち越し打が飛び出し、終盤の一打で流れを引き寄せた。</p>"
                "<pre>"
                "岡本和真は今日も決勝打\n"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "tokens used: 10\n"
                "</pre>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(304, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 304, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({304: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(history_row["hold_reason"], "cleanup_failed_post_condition")
        self.assertIn("title_subject_missing", history_row["error"])

    def test_postcheck_every_10_posts_round_trip(self):
        posts = {
            1200 + index: _post(
                1200 + index,
                f"巨人が第{index + 1}戦に勝利",
                (
                    f"<p>巨人が第{index + 1}戦に勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p>"
                    f"<p>{LONG_EXTRA}</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source</p>"
                ),
            )
            for index in range(11)
        }
        report = _report(green=[_green_entry(post_id, post["title"]["raw"]) for post_id, post in posts.items()])
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["postcheck_batch_count"], 2)
        self.assertEqual([batch["post_ids"] for batch in result["postcheck_batches"]], [list(range(1200, 1210)), [1210]])
        self.assertEqual(len(wp.get_post_calls), 22)

    def test_backup_required_before_cleanup_failure_holds(self):
        body_html = (
            "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で今季3勝目を挙げた。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
            "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
        )
        post = _post(305, "巨人が中日に5-1で勝利", body_html)
        report = _report(
            yellow=[_repairable_entry(305, post["title"]["raw"], "heading_sentence_as_h3", yellow_reasons=["heading_sentence_as_h3"])],
            cleanup_candidates=[{"post_id": 305, "cleanup_types": ["heading_sentence_as_h3"]}],
        )
        wp = FakeWPClient({305: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            with patch("src.guarded_publish_runner.create_publish_backup", side_effect=runner.BackupError("boom")):
                result = runner.run_guarded_publish(
                    input_from=self._write_input(tmpdir, report),
                    live=True,
                    daily_cap_allow=True,
                    history_path=history_path,
                    backup_dir=Path(tmpdir) / "cleanup_backup",
                    yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                    cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                    wp_client=wp,
                    now=FIXED_NOW,
                )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(result["executed"][0]["hold_reason"], "cleanup_backup_failed")
        self.assertEqual(history_row["hold_reason"], "cleanup_backup_failed")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])


if __name__ == "__main__":
    unittest.main()
