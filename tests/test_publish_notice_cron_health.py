import itertools
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from src import publish_notice_cron_health as health
from src.tools import run_publish_notice_cron_health_check as cli


NOW = datetime(2026, 4, 26, 5, 0, tzinfo=health.JST)
MARKER = "# 095-WSL-CRON-FALLBACK"


class _FakeResponse:
    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class PublishNoticeCronHealthTests(unittest.TestCase):
    def _command_runner(self, mapping):
        def run(argv):
            key = tuple(argv)
            return mapping[key]

        return run

    def _write_queue(self, path: Path, entries):
        if not entries:
            return
        path.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
            encoding="utf-8",
        )

    def _write_history(self, path: Path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_cron_log(self, path: Path, lines, *, age_minutes=0):
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        mtime = (NOW - timedelta(minutes=age_minutes)).timestamp()
        path.touch()
        path.chmod(0o644)
        import os

        os.utime(path, (mtime, mtime))

    def _collect(
        self,
        *,
        tempdir: str,
        cron_lines=None,
        queue_entries=None,
        history_payload=None,
        age_minutes=0,
        fetch_publish_count=None,
        run_command=None,
        env=None,
    ):
        cron_log = Path(tempdir) / "publish_notice_cron.log"
        queue = Path(tempdir) / "publish_notice_queue.jsonl"
        history = Path(tempdir) / "publish_notice_history.json"
        if cron_lines is not None:
            self._write_cron_log(cron_log, cron_lines, age_minutes=age_minutes)
        if queue_entries is not None:
            self._write_queue(queue, queue_entries)
        if history_payload is not None:
            self._write_history(history, history_payload)
        command_runner = run_command or self._command_runner(
            {
                ("systemctl", "is-active", "cron"): health.CommandResult(0, "active\n", ""),
                ("crontab", "-l"): health.CommandResult(0, f"15 * * * * echo ok\n{MARKER}\n", ""),
            }
        )
        publish_counter = fetch_publish_count or (lambda after: 0)
        with patch.dict("os.environ", env or {}, clear=True):
            return health.collect_publish_notice_cron_health(
                cron_log_path=cron_log,
                queue_path=queue,
                history_path=history,
                crontab_marker=MARKER,
                now=NOW,
                run_command=command_runner,
                fetch_publish_count=publish_counter,
            )

    def test_check_cron_daemon_reports_active_stopped_and_crontab_missing(self):
        cases = [
            (
                "ok",
                {
                    ("systemctl", "is-active", "cron"): health.CommandResult(0, "active\n", ""),
                    ("crontab", "-l"): health.CommandResult(0, f"0 * * * * run\n{MARKER}\n", ""),
                },
                "ok",
            ),
            (
                "stopped",
                {
                    ("systemctl", "is-active", "cron"): health.CommandResult(1, "inactive\n", ""),
                    ("crontab", "-l"): health.CommandResult(0, f"0 * * * * run\n{MARKER}\n", ""),
                },
                "stopped",
            ),
            (
                "crontab_missing",
                {
                    ("systemctl", "is-active", "cron"): health.CommandResult(0, "active\n", ""),
                    ("crontab", "-l"): health.CommandResult(0, "0 * * * * run\n", ""),
                },
                "crontab_missing",
            ),
        ]

        for label, mapping, expected in cases:
            with self.subTest(case=label):
                result = health.check_cron_daemon(
                    crontab_marker=MARKER,
                    run_command=self._command_runner(mapping),
                )
                self.assertEqual(result["verdict"], expected)

    @patch("src.publish_notice_cron_health.requests.get")
    def test_check_publish_recent_uses_wp_rest_total_header(self, mock_get):
        mock_get.return_value = _FakeResponse([{"id": 1}], headers={"X-WP-Total": "3"})

        result = health.check_publish_recent(now=NOW, wp_url="https://example.com")

        self.assertEqual(result["publishes_last_24h"], 3)
        self.assertEqual(result["verdict"], "active")
        call = mock_get.call_args
        self.assertEqual(call.args[0], "https://example.com/wp-json/wp/v2/posts")
        self.assertEqual(call.kwargs["params"]["status"], "publish")
        self.assertEqual(call.kwargs["params"]["per_page"], 100)

    @patch("src.publish_notice_cron_health.requests.get")
    def test_check_publish_recent_reports_idle_when_wp_rest_returns_zero(self, mock_get):
        mock_get.return_value = _FakeResponse([], headers={"X-WP-Total": "0"})

        result = health.check_publish_recent(now=NOW, wp_url="https://example.com")

        self.assertEqual(result["publishes_last_24h"], 0)
        self.assertEqual(result["verdict"], "idle")

    def test_check_smtp_send_health_detects_no_recipient_and_credential_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue = Path(tmpdir) / "queue.jsonl"
            self._write_queue(
                queue,
                [
                    {
                        "status": "suppressed",
                        "reason": "NO_RECIPIENT",
                        "post_id": 1,
                        "recorded_at": NOW.isoformat(),
                    }
                ],
            )
            result = health.check_smtp_send_health(
                queue_path=queue,
                cron_log_analysis=health.CronLogAnalysis(
                    last_tick_ts=NOW.isoformat(),
                    last_tick_age_min=0,
                    last_emit_count=1,
                    last_send_count=0,
                    last_skip_count=0,
                    verdict="ok",
                    last_skip_reasons={},
                    last_error_messages=[],
                    last_status_counts={},
                ),
                now=NOW,
            )
            self.assertEqual(result["verdict"], "no_recipient")

        with tempfile.TemporaryDirectory() as tmpdir:
            queue = Path(tmpdir) / "queue.jsonl"
            result = health.check_smtp_send_health(
                queue_path=queue,
                cron_log_analysis=health.CronLogAnalysis(
                    last_tick_ts=NOW.isoformat(),
                    last_tick_age_min=0,
                    last_emit_count=1,
                    last_send_count=0,
                    last_skip_count=0,
                    verdict="ok",
                    last_skip_reasons={},
                    last_error_messages=["no Gmail app password configured"],
                    last_status_counts={"error": 1},
                ),
                now=NOW,
            )
            self.assertEqual(result["verdict"], "credential_missing")
            self.assertEqual(result["smtp_error_24h"], 1)

    def test_check_history_dedup_health_detects_too_long_and_duplicate_skip_share(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history.json"
            self._write_history(
                history,
                {str(index): NOW.isoformat() for index in range(1001)},
            )
            result = health.check_history_dedup_health(
                history_path=history,
                cron_log_analysis=health.CronLogAnalysis(
                    last_tick_ts=NOW.isoformat(),
                    last_tick_age_min=0,
                    last_emit_count=0,
                    last_send_count=0,
                    last_skip_count=0,
                    verdict="ok",
                    last_skip_reasons={},
                    last_error_messages=[],
                    last_status_counts={},
                ),
                now=NOW,
            )
            self.assertEqual(result["verdict"], "history_too_long")

        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history.json"
            self._write_history(history, {"1": NOW.isoformat()})
            result = health.check_history_dedup_health(
                history_path=history,
                cron_log_analysis=health.CronLogAnalysis(
                    last_tick_ts=NOW.isoformat(),
                    last_tick_age_min=0,
                    last_emit_count=1,
                    last_send_count=0,
                    last_skip_count=19,
                    verdict="ok",
                    last_skip_reasons={"RECENT_DUPLICATE": 19},
                    last_error_messages=[],
                    last_status_counts={},
                ),
                now=NOW,
            )
            self.assertEqual(result["verdict"], "all_duplicate_skip")
            self.assertEqual(result["duplicate_skip_share"], 0.95)

    def test_check_env_presence_only_handles_all_four_flag_combinations(self):
        keys = [
            "MAIL_BRIDGE_TO",
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD",
            "MAIL_BRIDGE_SMTP_USERNAME",
            "MAIL_BRIDGE_FROM",
        ]
        for flags in itertools.product([False, True], repeat=4):
            env = {
                key: f"value-{index}"
                for index, (key, enabled) in enumerate(zip(keys, flags), start=1)
                if enabled
            }
            with self.subTest(flags=flags):
                with patch.dict("os.environ", env, clear=True):
                    result = health.check_env_presence_only()
                self.assertEqual(
                    result,
                    {
                        "MAIL_BRIDGE_TO_set": flags[0],
                        "MAIL_BRIDGE_GMAIL_APP_PASSWORD_set": flags[1],
                        "MAIL_BRIDGE_SMTP_USERNAME_set": flags[2],
                        "MAIL_BRIDGE_FROM_set": flags[3],
                    },
                )

    def test_secret_values_are_never_rendered_to_stdout_or_json(self):
        cron_lines = ["[scan] emitted=0 skipped=0 cursor_before=old cursor_after=new"]
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "MAIL_BRIDGE_TO": "alerts@example.com",
                "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "abc123",
                "MAIL_BRIDGE_SMTP_USERNAME": "smtp-user@example.com",
                "MAIL_BRIDGE_FROM": "from@example.com",
            }
            snapshot = self._collect(
                tempdir=tmpdir,
                cron_lines=cron_lines,
                history_payload={},
                queue_entries=[],
                env=env,
            )
            human = health.render_human(snapshot)
            rendered_json = health.render_json(snapshot)

            stdout = StringIO()
            with patch.dict("os.environ", env, clear=True):
                with patch.object(cli, "collect_publish_notice_cron_health", return_value=snapshot):
                    with redirect_stdout(stdout):
                        exit_code = cli.main(
                            [
                                "--cron-log",
                                str(Path(tmpdir) / "publish_notice_cron.log"),
                                "--queue",
                                str(Path(tmpdir) / "publish_notice_queue.jsonl"),
                                "--history",
                                str(Path(tmpdir) / "publish_notice_history.json"),
                                "--format",
                                "json",
                            ]
                        )

        combined = human + rendered_json + stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertNotIn("abc123", combined)
        self.assertNotIn("alerts@example.com", combined)
        self.assertIn('"MAIL_BRIDGE_GMAIL_APP_PASSWORD_set": true', rendered_json)
        self.assertIn('"MAIL_BRIDGE_TO_set": true', rendered_json)

    def test_collect_publish_notice_cron_health_maps_overall_verdict_branches(self):
        cases = [
            (
                "healthy",
                {
                    "cron_lines": [
                        "[scan] emitted=2 skipped=0 cursor_before=old cursor_after=new",
                        "[result] post_id=10 status=sent reason=None subject='a' recipients=['x']",
                        "[result] post_id=11 status=sent reason=None subject='b' recipients=['x']",
                    ],
                    "queue_entries": [
                        {"status": "sent", "reason": None, "post_id": 10, "recorded_at": NOW.isoformat()},
                        {"status": "sent", "reason": None, "post_id": 11, "recorded_at": NOW.isoformat()},
                    ],
                    "history_payload": {"10": NOW.isoformat(), "11": NOW.isoformat()},
                    "fetch_publish_count": lambda after: 2,
                },
                "healthy",
            ),
            (
                "stopped",
                {
                    "cron_lines": ["[scan] emitted=0 skipped=0 cursor_before=old cursor_after=new"],
                    "history_payload": {},
                    "run_command": self._command_runner(
                        {
                            ("systemctl", "is-active", "cron"): health.CommandResult(1, "inactive\n", ""),
                            ("crontab", "-l"): health.CommandResult(0, f"0 * * * * run\n{MARKER}\n", ""),
                        }
                    ),
                },
                "stopped",
            ),
            (
                "no_publish",
                {
                    "cron_lines": ["[scan] emitted=0 skipped=0 cursor_before=old cursor_after=new"],
                    "history_payload": {},
                    "queue_entries": [],
                    "fetch_publish_count": lambda after: 0,
                },
                "no_publish",
            ),
            (
                "smtp_failure",
                {
                    "cron_lines": [
                        "[scan] emitted=1 skipped=0 cursor_before=old cursor_after=new",
                        "[result] post_id=20 status=suppressed reason=NO_RECIPIENT subject='x' recipients=[]",
                    ],
                    "queue_entries": [
                        {"status": "suppressed", "reason": "NO_RECIPIENT", "post_id": 20, "recorded_at": NOW.isoformat()},
                    ],
                    "history_payload": {},
                    "fetch_publish_count": lambda after: 1,
                },
                "smtp_failure",
            ),
            (
                "dedup_misjudgment",
                {
                    "cron_lines": [
                        "[scan] emitted=1 skipped=19 cursor_before=old cursor_after=new",
                    ]
                    + [f"[skip] post_id={index} reason=RECENT_DUPLICATE" for index in range(19)],
                    "queue_entries": [],
                    "history_payload": {"1": NOW.isoformat()},
                    "fetch_publish_count": lambda after: 1,
                },
                "dedup_misjudgment",
            ),
            (
                "investigate",
                {
                    "cron_lines": ["[scan] emitted=0 skipped=0 cursor_before=old cursor_after=new"],
                    "history_payload": {},
                    "queue_entries": [],
                    "fetch_publish_count": lambda after: 0,
                    "age_minutes": 120,
                },
                "investigate",
            ),
        ]

        for label, kwargs, expected in cases:
            with self.subTest(case=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    snapshot = self._collect(tempdir=tmpdir, **kwargs)
                self.assertEqual(snapshot["overall_verdict"], expected)


if __name__ == "__main__":
    unittest.main()
