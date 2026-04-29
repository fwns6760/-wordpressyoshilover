from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.publish_notice_email_sender import PublishNoticeEmailResult, PublishNoticeRequest
from src.publish_notice_scanner import ScanResult
from src.tools import run_publish_notice_email_dry_run as runner


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class RunPublishNoticeEmailDryRunLedgerTests(unittest.TestCase):
    def test_notice_results_are_mirrored_best_effort(self) -> None:
        completed = runner.repair_provider_ledger.subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b"token\n",
            stderr=b"",
        )

        for mode in ("success", "firestore_failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                fixture_path = tmp / "fixture.json"
                queue_path = tmp / "queue.jsonl"
                fallback_path = tmp / "fallback.jsonl"
                artifact_uris: list[str] = []

                fixture_path.write_text(
                    json.dumps(
                        {
                            "post_id": 63105,
                            "title": "巨人が阪神に勝利",
                            "canonical_url": "https://yoshilover.com/63105",
                            "subtype": "postgame",
                            "publish_time_iso": "2026-04-26T23:20:00+09:00",
                            "summary": "summary",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                def fake_requests(method, url, **kwargs):
                    if method == "POST" and "notice_ledger_locks" in url:
                        return _FakeResponse(200, {"name": "lock-doc"})
                    if method == "GET" and "notice_ledger/" in url:
                        return _FakeResponse(404, {"error": {"message": "missing"}})
                    if method == "POST" and "notice_ledger" in url:
                        if mode == "firestore_failure":
                            raise runner.repair_provider_ledger.requests.RequestException("firestore down")
                        artifact_uris.append(kwargs["json"]["fields"]["artifact_uri"]["stringValue"])
                        return _FakeResponse(200, {"name": "ledger-doc"})
                    if method == "DELETE" and "notice_ledger_locks" in url:
                        return _FakeResponse(200, {})
                    raise AssertionError(f"unexpected request: {method} {url}")

                stdout = io.StringIO()
                with patch.dict(
                    "os.environ",
                    {
                        runner.runner_ledger_integration.ENV_LEDGER_FIRESTORE_ENABLED: "true",
                        runner.runner_ledger_integration.ENV_LEDGER_GCS_ARTIFACT_ENABLED: "true",
                        "GOOGLE_CLOUD_PROJECT": "project-id",
                    },
                    clear=False,
                ), patch(
                    "src.tools.run_publish_notice_email_dry_run.send",
                    return_value=PublishNoticeEmailResult(
                        status="sent",
                        reason=None,
                        subject="[公開通知] Giants 巨人が阪神に勝利",
                        recipients=["ops@example.com"],
                    ),
                ), patch(
                    "src.tools.run_publish_notice_email_dry_run.repair_provider_ledger.resolve_jsonl_ledger_path",
                    return_value=fallback_path,
                ), patch(
                    "src.repair_provider_ledger.subprocess.run",
                    return_value=completed,
                ), patch(
                    "src.cloud_run_persistence.subprocess.run",
                    return_value=completed,
                ), patch(
                    "src.repair_provider_ledger.requests.request",
                    side_effect=fake_requests,
                ), patch("sys.stdout", stdout):
                    exit_code = runner.main(
                        [
                            "--input",
                            str(fixture_path),
                            "--queue-path",
                            str(queue_path),
                        ]
                    )

                self.assertEqual(exit_code, 0)
                if mode == "success":
                    self.assertTrue(artifact_uris)
                    self.assertTrue(artifact_uris[0].startswith("gs://yoshilover-history/repair_artifacts/"))
                else:
                    rows = [
                        json.loads(line)
                        for line in fallback_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["lane"], "publish_notice")
                    self.assertTrue(rows[0]["artifact_uri"].startswith("gs://yoshilover-history/repair_artifacts/"))


class RunPublishNoticeEmailDryRunScanTests(unittest.TestCase):
    def test_scan_summary_ignores_review_hold_notices(self) -> None:
        publish_request = PublishNoticeRequest(
            post_id=63105,
            title="公開済み記事",
            canonical_url="https://yoshilover.com/63105",
            subtype="postgame",
            publish_time_iso="2026-04-26T23:20:00+09:00",
        )
        review_request = PublishNoticeRequest(
            post_id=63106,
            title="レビュー待ち記事",
            canonical_url="https://yoshilover.com/63106",
            subtype="default",
            publish_time_iso="2026-04-26T23:25:00+09:00",
            notice_kind="review_hold",
            subject_override="【要review】レビュー待ち記事 | YOSHILOVER",
        )
        scan_result = ScanResult(
            emitted=[publish_request, review_request],
            skipped=[],
            cursor_before="2026-04-26T23:00:00+09:00",
            cursor_after="2026-04-26T23:30:00+09:00",
        )
        captured_entries = []
        stdout = io.StringIO()

        class _Sink:
            enabled = False

        def fake_build(entries, **kwargs):
            captured_entries.extend(entries)
            return []

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "src.tools.run_publish_notice_email_dry_run.scan",
            return_value=scan_result,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.send",
            return_value=PublishNoticeEmailResult(
                status="dry_run",
                reason=None,
                subject="subject",
                recipients=[],
            ),
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.append_send_result",
        ), patch(
            "src.tools.run_publish_notice_email_dry_run._emit_notice_ledger",
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.build_burst_summary_requests",
            side_effect=fake_build,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.build_execution_summary_log",
            return_value="",
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.build_zero_sent_alert_log",
            return_value=None,
        ), patch(
            "src.tools.run_publish_notice_email_dry_run.runner_ledger_integration.BestEffortLedgerSink",
            return_value=_Sink(),
        ), patch("sys.stdout", stdout):
            exit_code = runner.main(["--scan", "--queue-path", str(Path(tmpdir) / "queue.jsonl")])

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(captured_entries), 1)
        self.assertEqual(captured_entries[0].post_id, 63105)


if __name__ == "__main__":
    unittest.main()
