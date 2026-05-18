from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import publish_notice_scanner as scanner
from src.publish_notice_email_sender import PublishNoticeEmailResult, PublishNoticeRequest
from src.publish_notice_scanner import GuardedPublishHistoryScanResult, ScanResult
from src.tools import run_publish_notice_email_dry_run as runner


NOW = datetime(2026, 5, 6, 9, 0, tzinfo=scanner.JST)


class _DisabledSink:
    enabled = False


class PublishNoticeTwoPhaseTests(unittest.TestCase):
    def _publish_request(
        self,
        post_id: int | str,
        *,
        title: str | None = None,
        notice_kind: str = "publish",
        notice_origin: str | None = scanner._DIRECT_PUBLISH_NOTICE_ORIGIN,
        subject_override: str | None = None,
        record_type: str | None = None,
        skip_layer: str | None = None,
        skip_reason: str | None = None,
    ) -> PublishNoticeRequest:
        return PublishNoticeRequest(
            post_id=post_id,
            title=title or f"記事 {post_id}",
            canonical_url=f"https://yoshilover.com/{post_id}",
            subtype="postgame",
            publish_time_iso=NOW.isoformat(),
            notice_kind=notice_kind,
            notice_origin=notice_origin,
            subject_override=subject_override,
            record_type=record_type,
            skip_layer=skip_layer,
            skip_reason=skip_reason,
        )

    def _post(self, post_id: int, *, status: str = "draft", date: str = "2026-05-06T08:00:00+09:00") -> dict[str, object]:
        return {
            "id": post_id,
            "title": {"rendered": f"公開記事 {post_id}"},
            "excerpt": {"rendered": "<p>excerpt</p>"},
            "content": {"rendered": "<p>content</p>"},
            "link": f"https://yoshilover.com/{post_id}",
            "date": date,
            "status": status,
            "meta": {"article_subtype": "postgame"},
        }

    def _guarded_entry(self, post_id: int) -> dict[str, object]:
        return {
            "post_id": post_id,
            "ts": "2026-05-06T08:05:00+09:00",
            "status": "refused",
            "judgment": "yellow",
            "publishable": True,
            "cleanup_required": False,
            "cleanup_success": False,
            "hold_reason": "",
        }

    def _review_scan_result(
        self,
        request: PublishNoticeRequest,
        *,
        history_after: dict[str, str],
        cursor_path: Path,
        cursor_before: str = "2026-05-06T08:00:00+09:00",
        cursor_after: str = "2026-05-06T08:05:00+09:00",
    ) -> GuardedPublishHistoryScanResult:
        return GuardedPublishHistoryScanResult(
            emitted=[request],
            skipped=[],
            history_after=history_after,
            cursor_before=cursor_before,
            cursor_after=cursor_after,
            cursor_path=cursor_path,
            cursor_write_needed=True,
        )

    def _base_runner_patches(self, *, send_result: PublishNoticeEmailResult | None = None):
        return [
            patch(
                "src.tools.run_publish_notice_email_dry_run.send",
                return_value=send_result
                or PublishNoticeEmailResult(
                    status="dry_run",
                    reason=None,
                    subject="subject",
                    recipients=[],
                ),
            ),
            patch("src.tools.run_publish_notice_email_dry_run.append_send_result"),
            patch("src.tools.run_publish_notice_email_dry_run._emit_notice_ledger"),
            patch("src.tools.run_publish_notice_email_dry_run.build_execution_summary_log", return_value=""),
            patch("src.tools.run_publish_notice_email_dry_run.build_zero_sent_alert_log", return_value=None),
            patch(
                "src.tools.run_publish_notice_email_dry_run.runner_ledger_integration.BestEffortLedgerSink",
                return_value=_DisabledSink(),
            ),
        ]

    def test_flag_off_uses_legacy_scan_path(self) -> None:
        publish_request = self._publish_request(63105, title="公開済み記事")
        review_request = self._publish_request(
            63106,
            title="レビュー待ち記事",
            notice_kind="review_hold",
            notice_origin=None,
            subject_override="【要review】レビュー待ち記事 | YOSHILOVER",
        )
        scan_result = ScanResult(
            emitted=[publish_request, review_request],
            skipped=[],
            cursor_before="2026-05-06T08:00:00+09:00",
            cursor_after="2026-05-06T08:30:00+09:00",
        )
        captured_entries = []
        stdout = io.StringIO()

        def fake_build(entries, **kwargs):
            captured_entries.extend(entries)
            return []

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict("os.environ", {}, clear=True), patch(
            "src.tools.run_publish_notice_email_dry_run.scan",
            return_value=scan_result,
        ) as scan_mock, patch(
            "src.tools.run_publish_notice_email_dry_run.scan_direct_publish_only",
            side_effect=AssertionError("two-phase direct path must stay off by default"),
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_review_only",
            side_effect=AssertionError("two-phase review path must stay off by default"),
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.build_burst_summary_requests",
            side_effect=fake_build,
        ), patch("sys.stdout", stdout):
            patches = self._base_runner_patches()
            for item in patches:
                item.start()
            try:
                exit_code = runner.main(["--scan", "--queue-path", str(Path(tmpdir) / "queue.jsonl")])
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(exit_code, 0)
        scan_mock.assert_called_once()
        self.assertEqual(len(captured_entries), 1)
        self.assertEqual(captured_entries[0].post_id, 63105)

    def test_flag_on_sends_direct_before_review_scan(self) -> None:
        direct_request = self._publish_request(64101, title="公開記事")
        direct_result = ScanResult(
            emitted=[direct_request],
            skipped=[],
            cursor_before="2026-05-06T08:00:00+09:00",
            cursor_after="2026-05-06T08:10:00+09:00",
        )
        review_result = ScanResult(
            emitted=[],
            skipped=[],
            cursor_before=direct_result.cursor_after,
            cursor_after=direct_result.cursor_after,
        )
        call_order: list[str] = []
        stdout = io.StringIO()

        def fake_send(request, **kwargs):
            call_order.append(f"send:{request.post_id}")
            return PublishNoticeEmailResult(status="dry_run", reason=None, subject="subject", recipients=[])

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_TWO_PHASE": "1"},
            clear=True,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_direct_publish_only",
            side_effect=lambda **kwargs: call_order.append("scan:direct") or direct_result,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_review_only",
            side_effect=lambda **kwargs: call_order.append("scan:review") or review_result,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.build_burst_summary_requests",
            return_value=[],
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.send",
            side_effect=fake_send,
        ), patch("sys.stdout", stdout):
            patches = [
                patch("src.tools.run_publish_notice_email_dry_run.append_send_result"),
                patch("src.tools.run_publish_notice_email_dry_run._emit_notice_ledger"),
                patch("src.tools.run_publish_notice_email_dry_run.build_execution_summary_log", return_value=""),
                patch("src.tools.run_publish_notice_email_dry_run.build_zero_sent_alert_log", return_value=None),
                patch(
                    "src.tools.run_publish_notice_email_dry_run.runner_ledger_integration.BestEffortLedgerSink",
                    return_value=_DisabledSink(),
                ),
            ]
            for item in patches:
                item.start()
            try:
                exit_code = runner.main(["--scan", "--queue-path", str(Path(tmpdir) / "queue.jsonl")])
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(exit_code, 0)
        self.assertEqual(call_order, ["scan:direct", "send:64101", "scan:review"])

    def test_review_exception_does_not_block_direct_send(self) -> None:
        direct_request = self._publish_request(64102, title="direct only")
        direct_result = ScanResult(
            emitted=[direct_request],
            skipped=[],
            cursor_before="2026-05-06T08:00:00+09:00",
            cursor_after="2026-05-06T08:10:00+09:00",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_TWO_PHASE": "1"},
            clear=True,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_direct_publish_only",
            return_value=direct_result,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_review_only",
            side_effect=RuntimeError("review timed out"),
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.build_burst_summary_requests",
            return_value=[],
        ), patch("sys.stdout", stdout), patch("sys.stderr", stderr), patch(
            "src.tools.run_publish_notice_email_dry_run.send",
            return_value=PublishNoticeEmailResult(
                status="dry_run",
                reason=None,
                subject="subject",
                recipients=[],
            ),
        ) as send_mock:
            patches = [
                patch("src.tools.run_publish_notice_email_dry_run.append_send_result"),
                patch("src.tools.run_publish_notice_email_dry_run._emit_notice_ledger"),
                patch("src.tools.run_publish_notice_email_dry_run.build_execution_summary_log", return_value=""),
                patch("src.tools.run_publish_notice_email_dry_run.build_zero_sent_alert_log", return_value=None),
                patch(
                    "src.tools.run_publish_notice_email_dry_run.runner_ledger_integration.BestEffortLedgerSink",
                    return_value=_DisabledSink(),
                ),
            ]
            for item in patches:
                item.start()
            try:
                exit_code = runner.main(["--scan", "--queue-path", str(Path(tmpdir) / "queue.jsonl")])
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(exit_code, 0)
        self.assertIn("review timed out", stderr.getvalue())
        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(send_mock.call_args.args[0].post_id, 64102)

    def test_review_budget_zero_keeps_all_review_scans_active(self) -> None:
        history_after = {"guarded": NOW.isoformat()}
        guarded_request = self._publish_request(
            7001,
            notice_kind="review_hold",
            notice_origin=None,
            subject_override="【要review】guarded | YOSHILOVER",
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1",
                "ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1",
            },
            clear=True,
        ):
            tmp = Path(tmpdir)
            cursor_path = tmp / "cursor.txt"
            history_path = tmp / "history.json"
            queue_path = tmp / "queue.jsonl"
            guarded_cursor_path = tmp / "guarded_cursor.txt"
            post_gen_cursor_path = tmp / "post_gen_cursor.txt"
            preflight_cursor_path = tmp / "preflight_cursor.txt"
            cursor_path.write_text("2026-05-06T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            guarded_result = self._review_scan_result(
                guarded_request,
                history_after=history_after,
                cursor_path=guarded_cursor_path,
            )
            post_gen_result = GuardedPublishHistoryScanResult(
                emitted=[],
                skipped=[],
                history_after=history_after,
                cursor_before=None,
                cursor_after=None,
                cursor_path=post_gen_cursor_path,
                cursor_write_needed=False,
            )
            preflight_result = GuardedPublishHistoryScanResult(
                emitted=[],
                skipped=[],
                history_after=history_after,
                cursor_before=None,
                cursor_after=None,
                cursor_path=preflight_cursor_path,
                cursor_write_needed=False,
            )

            with patch.object(scanner, "scan_guarded_publish_history", return_value=guarded_result) as guarded_mock, patch.object(
                scanner,
                "scan_post_gen_validate_history",
                return_value=post_gen_result,
            ) as post_gen_mock, patch.object(
                scanner,
                "scan_preflight_skip_history",
                return_value=preflight_result,
            ) as preflight_mock, patch("src.publish_notice_scanner.time.monotonic", side_effect=[0.0]):
                result = scanner.scan_review_only(
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    guarded_cursor_path=guarded_cursor_path,
                    post_gen_validate_cursor_path=post_gen_cursor_path,
                    preflight_skip_cursor_path=preflight_cursor_path,
                    budget_seconds=0.0,
                    now=lambda: NOW,
                )

        self.assertEqual([request.post_id for request in result.emitted], [7001])
        guarded_mock.assert_called_once()
        post_gen_mock.assert_called_once()
        preflight_mock.assert_called_once()

    def test_review_budget_skips_late_scans_and_leaves_their_cursors_unchanged(self) -> None:
        review_request = self._publish_request(
            7002,
            notice_kind="review_hold",
            notice_origin=None,
            subject_override="【要review】guarded 7002 | YOSHILOVER",
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1",
                "ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1",
            },
            clear=True,
        ):
            tmp = Path(tmpdir)
            cursor_path = tmp / "cursor.txt"
            history_path = tmp / "history.json"
            queue_path = tmp / "queue.jsonl"
            guarded_cursor_path = tmp / "guarded_cursor.txt"
            post_gen_cursor_path = tmp / "post_gen_cursor.txt"
            preflight_cursor_path = tmp / "preflight_cursor.txt"
            cursor_path.write_text("2026-05-06T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            post_gen_cursor_path.write_text("post-gen-before\n", encoding="utf-8")
            preflight_cursor_path.write_text("preflight-before\n", encoding="utf-8")

            guarded_result = self._review_scan_result(
                review_request,
                history_after={"7002": NOW.isoformat()},
                cursor_path=guarded_cursor_path,
            )

            with patch.object(scanner, "scan_guarded_publish_history", return_value=guarded_result) as guarded_mock, patch.object(
                scanner,
                "scan_post_gen_validate_history",
                side_effect=AssertionError("budget should skip post_gen_validate"),
            ) as post_gen_mock, patch.object(
                scanner,
                "scan_preflight_skip_history",
                side_effect=AssertionError("budget should skip preflight_skip"),
            ) as preflight_mock, patch(
                "src.publish_notice_scanner.time.monotonic",
                side_effect=[0.0, 0.0, 5.0, 5.0],
            ):
                result = scanner.scan_review_only(
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    guarded_cursor_path=guarded_cursor_path,
                    post_gen_validate_cursor_path=post_gen_cursor_path,
                    preflight_skip_cursor_path=preflight_cursor_path,
                    budget_seconds=1.0,
                    now=lambda: NOW,
                )

            self.assertEqual([request.post_id for request in result.emitted], [7002])
            guarded_mock.assert_called_once()
            post_gen_mock.assert_not_called()
            preflight_mock.assert_not_called()
            self.assertEqual(post_gen_cursor_path.read_text(encoding="utf-8").strip(), "post-gen-before")
            self.assertEqual(preflight_cursor_path.read_text(encoding="utf-8").strip(), "preflight-before")

    def test_direct_phase_writes_history_and_cursor_before_review_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            cursor_path = tmp / "cursor.txt"
            history_path = tmp / "history.json"
            queue_path = tmp / "queue.jsonl"
            cursor_path.write_text("2026-05-06T07:30:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            direct_result = scanner.scan_direct_publish_only(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [self._post(7101, date="2026-05-06T08:15:00+09:00")],
                now=lambda: NOW,
            )
            with patch("src.publish_notice_scanner.time.monotonic", side_effect=[0.0, 10.0]):
                review_result = scanner.scan_review_only(
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    budget_seconds=1.0,
                    now=lambda: NOW,
                )

            history = json.loads(history_path.read_text(encoding="utf-8"))
            cursor_after = cursor_path.read_text(encoding="utf-8").strip()

            self.assertEqual([request.post_id for request in direct_result.emitted], [7101])
            self.assertEqual(review_result.emitted, [])
            self.assertEqual(cursor_after, "2026-05-06T08:15:00+09:00")
            self.assertIn("7101", history)

    def test_duplicate_guard_works_across_direct_and_review_phases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            cursor_path = tmp / "cursor.txt"
            history_path = tmp / "history.json"
            queue_path = tmp / "queue.jsonl"
            guarded_history_path = tmp / "guarded_publish_history.jsonl"
            guarded_cursor_path = tmp / "guarded_cursor.txt"
            cursor_path.write_text("2026-05-06T07:30:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            guarded_history_path.write_text(
                json.dumps(self._guarded_entry(7201), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            scanner.scan_direct_publish_only(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [self._post(7201, date="2026-05-06T08:10:00+09:00")],
                now=lambda: NOW,
            )
            with patch.object(
                scanner,
                "_default_fetch_post_detail",
                return_value=self._post(7201, status="draft", date="2026-05-06T08:10:00+09:00"),
            ):
                review_result = scanner.scan_review_only(
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    guarded_publish_history_path=guarded_history_path,
                    guarded_cursor_path=guarded_cursor_path,
                    budget_seconds=0.0,
                    now=lambda: NOW,
                )

        self.assertEqual(review_result.emitted, [])
        self.assertIn((7201, "REVIEW_RECENT_DUPLICATE"), review_result.skipped)

    def test_burst_summary_stays_disabled_in_two_phase_mode(self) -> None:
        direct_result = ScanResult(
            emitted=[self._publish_request(7300 + index) for index in range(11)],
            skipped=[],
            cursor_before="2026-05-06T08:00:00+09:00",
            cursor_after="2026-05-06T08:20:00+09:00",
        )
        review_result = ScanResult(
            emitted=[],
            skipped=[],
            cursor_before=direct_result.cursor_after,
            cursor_after=direct_result.cursor_after,
        )
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_PUBLISH_NOTICE_TWO_PHASE": "1",
                "DISABLE_BURST_SUMMARY_MAIL": "1",
            },
            clear=True,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_direct_publish_only",
            return_value=direct_result,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_review_only",
            return_value=review_result,
        ), patch("sys.stdout", stdout):
            patches = self._base_runner_patches()
            send_summary_patch = patch("src.tools.run_publish_notice_email_dry_run.send_summary")
            send_summary_mock = send_summary_patch.start()
            for item in patches:
                item.start()
            try:
                exit_code = runner.main(["--scan", "--queue-path", str(Path(tmpdir) / "queue.jsonl")])
            finally:
                send_summary_patch.stop()
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(exit_code, 0)
        send_summary_mock.assert_not_called()

    def test_review_notices_do_not_mix_into_direct_phase_summary(self) -> None:
        direct_result = ScanResult(
            emitted=[self._publish_request(7401, title="公開1")],
            skipped=[],
            cursor_before="2026-05-06T08:00:00+09:00",
            cursor_after="2026-05-06T08:10:00+09:00",
        )
        review_result = ScanResult(
            emitted=[
                self._publish_request(
                    "post_gen_validate:abc",
                    title="要review",
                    notice_kind="post_gen_validate",
                    notice_origin=None,
                    subject_override="【要review｜post_gen_validate】要review | YOSHILOVER",
                    record_type="post_gen_validate",
                    skip_layer="post_gen_validate",
                    skip_reason="weak_subject_title",
                )
            ],
            skipped=[],
            cursor_before=direct_result.cursor_after,
            cursor_after=direct_result.cursor_after,
        )
        captured_entries = []
        stdout = io.StringIO()

        def fake_build(entries, **kwargs):
            captured_entries.extend(entries)
            return []

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_TWO_PHASE": "1"},
            clear=True,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_direct_publish_only",
            return_value=direct_result,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.scan_review_only",
            return_value=review_result,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.build_burst_summary_requests",
            side_effect=fake_build,
        ), patch("sys.stdout", stdout):
            patches = self._base_runner_patches()
            for item in patches:
                item.start()
            try:
                exit_code = runner.main(["--scan", "--queue-path", str(Path(tmpdir) / "queue.jsonl")])
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertEqual(exit_code, 0)
        self.assertEqual([entry.post_id for entry in captured_entries], [7401])
        self.assertTrue(all(entry.title == "公開1" for entry in captured_entries))


if __name__ == "__main__":
    unittest.main()
