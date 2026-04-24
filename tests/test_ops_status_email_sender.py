import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import ops_status_email_sender as sender
from src.tools import run_ops_status_email_send_dry_run


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ops_secretary"


def _fixture(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class OpsStatusEmailSenderTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)

    def _snapshot(self, **overrides):
        payload = _fixture("typical.json")
        payload.update(overrides)
        return payload

    def _request(self, **overrides):
        payload = {
            "snapshot": self._snapshot(),
            "body_html": None,
            "override_subject_datetime": None,
            "override_recipient": None,
            "strict": False,
        }
        payload.update(overrides)
        return sender.OpsStatusEmailRequest(**payload)

    def _write_snapshot(self, payload=None, *, filename="snapshot.json"):
        path = self.root / filename
        path.write_text(json.dumps(payload or self._snapshot(), ensure_ascii=False), encoding="utf-8")
        return path

    def _write_text(self, filename: str, text: str) -> Path:
        path = self.root / filename
        path.write_text(text, encoding="utf-8")
        return path

    def test_build_subject_variants(self):
        cases = [
            ("2026-04-24 11:30", None, "[ops] Giants ops status 2026-04-24 11:30"),
            ("2026-04-24 11:30", "2026-04-24 14:00", "[ops] Giants ops status 2026-04-24 14:00"),
            (None, "2026-04-25 09:15", "[ops] Giants ops status 2026-04-25 09:15"),
        ]

        for now_jst, override, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(sender.build_subject(now_jst, override), expected)

    def test_resolve_recipients_uses_expected_precedence(self):
        cases = [
            (
                {"OPS_EMAIL_TO": "ops@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                None,
                ["ops@example.com"],
            ),
            (
                {"MAIL_BRIDGE_TO": "bridge@example.com, second@example.com"},
                None,
                ["bridge@example.com", "second@example.com"],
            ),
            (
                {"OPS_EMAIL_TO": "ops@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                ["override@example.com, next@example.com"],
                ["override@example.com", "next@example.com"],
            ),
        ]

        for env_map, override, expected in cases:
            with self.subTest(expected=expected):
                with patch.dict("os.environ", env_map, clear=True):
                    self.assertEqual(sender.resolve_recipients(override), expected)

    def test_send_dry_run_skips_bridge_and_sets_preview(self):
        request = self._request()
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            result = sender.send(
                request,
                dry_run=True,
                bridge_send=bridge_send,
                now_provider=lambda: datetime(2026, 4, 24, 11, 30, tzinfo=sender.JST),
            )

        self.assertEqual(result.status, "dry_run")
        self.assertIsNone(result.reason)
        self.assertEqual(result.subject, "[ops] Giants ops status 2026-04-24 11:30")
        self.assertEqual(result.recipients, ["ops@example.com"])
        self.assertTrue(result.body_text_preview.startswith("進行中: B: 048 formatter in-flight"))
        self.assertLessEqual(len(result.body_text_preview), 200)
        self.assertIsNone(result.bridge_result)
        bridge_send.assert_not_called()

    def test_send_real_path_calls_bridge_once_with_mail_request(self):
        request = self._request()
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            result = sender.send(
                request,
                dry_run=False,
                bridge_send=bridge_send,
                now_provider=lambda: datetime(2026, 4, 24, 11, 30, tzinfo=sender.JST),
            )

        self.assertEqual(result.status, "sent")
        self.assertIs(result.bridge_result, bridge_result)
        bridge_send.assert_called_once()
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(bridge_send.call_args.kwargs, {"dry_run": False})
        self.assertIsInstance(mail_request, mail_delivery_bridge.MailRequest)
        self.assertEqual(mail_request.subject, "[ops] Giants ops status 2026-04-24 11:30")
        self.assertIn("進行中: B: 048 formatter in-flight", mail_request.text_body)
        self.assertEqual(mail_request.to, ["ops@example.com"])

    def test_send_suppresses_invalid_snapshot_for_non_mapping_inputs(self):
        cases = [
            [],
            "not-a-dict",
        ]

        for value in cases:
            with self.subTest(value=value):
                request = self._request(snapshot=value)
                result = sender.send(request, dry_run=False, bridge_send=MagicMock())
                self.assertEqual(result.status, "suppressed")
                self.assertEqual(result.reason, "INVALID_SNAPSHOT")

    def test_send_suppresses_renderer_error_when_strict_rejects_forbidden_content(self):
        request = self._request(
            snapshot=self._snapshot(in_flight=["token=abcDEF1234567890"]),
            strict=True,
        )
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertIn("RENDERER_ERROR:", result.reason)
        self.assertIn("renderer rejected forbidden field", result.reason)
        bridge_send.assert_not_called()

    def test_send_allows_redaction_when_strict_is_false(self):
        request = self._request(snapshot=self._snapshot(in_flight=["token=abcDEF1234567890"]))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            result = sender.send(request, dry_run=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "dry_run")
        self.assertIn("[REDACTED:secret]", result.body_text_preview)
        bridge_send.assert_not_called()

    def test_send_suppresses_empty_body_when_formatter_returns_blank(self):
        request = self._request()

        with patch("src.ops_status_email_sender.format_digest_human", return_value="   "):
            with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
                result = sender.send(request, dry_run=False, bridge_send=MagicMock())

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "EMPTY_BODY")

    def test_send_suppresses_when_no_recipient_is_available(self):
        request = self._request()
        bridge_send = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "NO_RECIPIENT")
        self.assertEqual(result.recipients, [])
        self.assertIsNotNone(result.body_text_preview)
        bridge_send.assert_not_called()

    def test_send_uses_ops_email_to_over_mail_bridge_to(self):
        request = self._request()
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(
            "os.environ",
            {"OPS_EMAIL_TO": "ops@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
            clear=True,
        ):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.recipients, ["ops@example.com"])
        self.assertEqual(bridge_send.call_args.args[0].to, ["ops@example.com"])

    def test_send_uses_mail_bridge_to_fallback_when_ops_recipient_missing(self):
        request = self._request()
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"MAIL_BRIDGE_TO": "bridge@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.recipients, ["bridge@example.com"])
        self.assertEqual(bridge_send.call_args.args[0].to, ["bridge@example.com"])

    def test_send_uses_recipient_override_over_env(self):
        request = self._request(override_recipient=["override@example.com, second@example.com"])
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(
            "os.environ",
            {"OPS_EMAIL_TO": "ops@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
            clear=True,
        ):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.recipients, ["override@example.com", "second@example.com"])
        self.assertEqual(bridge_send.call_args.args[0].to, ["override@example.com", "second@example.com"])

    def test_send_subject_uses_now_provider(self):
        request = self._request()

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            result = sender.send(
                request,
                dry_run=True,
                bridge_send=MagicMock(),
                now_provider=lambda: datetime(2026, 4, 24, 11, 30, tzinfo=sender.JST),
            )

        self.assertEqual(result.subject, "[ops] Giants ops status 2026-04-24 11:30")

    def test_send_subject_override_wins(self):
        request = self._request(override_subject_datetime="2026-04-24 14:00")

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            result = sender.send(
                request,
                dry_run=True,
                bridge_send=MagicMock(),
                now_provider=lambda: datetime(2026, 4, 24, 11, 30, tzinfo=sender.JST),
            )

        self.assertEqual(result.subject, "[ops] Giants ops status 2026-04-24 14:00")

    def test_send_passes_body_html_into_mail_request(self):
        request = self._request(body_html="<p>html</p>")
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(bridge_send.call_args.args[0].html_body, "<p>html</p>")

    def test_send_wraps_bridge_result_object(self):
        request = self._request()
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={"ignored@example.com": [550, "rejected"]},
            smtp_response=[250, "ok"],
            reason="partial",
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertIs(result.bridge_result, bridge_result)
        self.assertEqual(result.reason, "partial")

    def test_cli_smoke_dry_run_snapshot_path(self):
        snapshot_path = self._write_snapshot()
        stdout = io.StringIO()

        with patch.dict("os.environ", {"OPS_EMAIL_TO": "ops@example.com"}, clear=True):
            with patch("sys.stdout", stdout):
                code = run_ops_status_email_send_dry_run.main(["--snapshot-path", str(snapshot_path)])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn(f"[request] source={snapshot_path}", output)
        self.assertIn("[subject] '[ops] Giants ops status ", output)
        self.assertIn("[result] status=dry_run reason=None recipients=['ops@example.com']", output)
        self.assertIn("[body_preview] 進行中:", output)

    def test_cli_smoke_missing_snapshot(self):
        missing_path = self.root / "missing.json"
        stdout = io.StringIO()

        with patch("sys.stdout", stdout):
            code = run_ops_status_email_send_dry_run.main(["--snapshot-path", str(missing_path)])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("[subject] <skipped>", output)
        self.assertIn("[result] status=suppressed reason=MISSING_SNAPSHOT recipients=[]", output)
        self.assertIn("[body_preview] <skipped>", output)

    def test_cli_smoke_invalid_snapshot_json(self):
        invalid_path = self._write_text("invalid.json", "{invalid")
        stdout = io.StringIO()

        with patch("sys.stdout", stdout):
            code = run_ops_status_email_send_dry_run.main(["--snapshot-path", str(invalid_path)])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("[subject] <skipped>", output)
        self.assertIn("[result] status=suppressed reason=INVALID_SNAPSHOT recipients=[]", output)
        self.assertIn("[body_preview] <skipped>", output)

    def test_cli_smoke_stdin_path(self):
        stdout = io.StringIO()
        stdin = io.StringIO(json.dumps(self._snapshot(), ensure_ascii=False))

        with patch.dict("os.environ", {"MAIL_BRIDGE_TO": "bridge@example.com"}, clear=True):
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                code = run_ops_status_email_send_dry_run.main(["--stdin"])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("[request] source=stdin", output)
        self.assertIn("[result] status=dry_run reason=None recipients=['bridge@example.com']", output)


if __name__ == "__main__":
    unittest.main()
