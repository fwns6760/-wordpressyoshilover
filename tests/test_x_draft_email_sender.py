import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import x_draft_email_sender as sender
from src.tools import run_x_draft_email_send_dry_run


class XDraftEmailSenderTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)

    def _body_text(self, count=1):
        lines = [
            "X Draft Email Digest",
            f"items: {count}",
            "excluded: 0",
        ]
        for index in range(1, count + 1):
            lines.extend(
                [
                    "",
                    f"candidate {index}",
                    "recommended_account: official",
                    "source_tier: fact",
                    f"safe_fact: sample fact {index}",
                    f"official_draft: draft {index}",
                    f"official_alt: alt {index}",
                    f"inner_angle: angle {index}",
                    "risk_note: ",
                    f"source_ref: https://example.com/{index}",
                ]
            )
        return "\n".join(lines) + "\n"

    def _write_body(self, text=None, *, filename="body.txt"):
        path = self.root / filename
        path.write_text(text if text is not None else self._body_text(), encoding="utf-8")
        return path

    def _write_html(self, text="<p>html</p>", *, filename="body.html"):
        path = self.root / filename
        path.write_text(text, encoding="utf-8")
        return path

    def _request(self, **overrides):
        payload = {
            "body_text_path": None,
            "body_html_path": None,
            "override_subject_datetime": None,
            "override_recipient": None,
            "item_count_override": None,
        }
        payload.update(overrides)
        if payload["body_text_path"] is None:
            payload["body_text_path"] = str(self._write_body())
        return sender.XDraftEmailRequest(**payload)

    def test_count_items_matches_b1_candidate_marker(self):
        cases = [
            (self._body_text(count=0), 0),
            (self._body_text(count=1), 1),
            (self._body_text(count=3), 3),
        ]

        for body_text, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(sender.count_items(body_text), expected)

    def test_build_subject_variants(self):
        cases = [
            ("2026-04-24 08:00", None, "[X下書き] Giants news drafts 2026-04-24 08:00"),
            ("2026-04-24 08:00", "2026-04-24 12:30", "[X下書き] Giants news drafts 2026-04-24 12:30"),
            (None, "2026-04-25 09:15", "[X下書き] Giants news drafts 2026-04-25 09:15"),
        ]

        for now_jst, override, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(sender.build_subject(now_jst, override), expected)

    def test_resolve_recipients_uses_expected_precedence(self):
        cases = [
            (
                {"X_DRAFT_EMAIL_TO": "xdraft@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                None,
                ["xdraft@example.com"],
            ),
            (
                {"MAIL_BRIDGE_TO": "bridge@example.com, second@example.com"},
                None,
                ["bridge@example.com", "second@example.com"],
            ),
            (
                {"X_DRAFT_EMAIL_TO": "xdraft@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                ["override@example.com, next@example.com"],
                ["override@example.com", "next@example.com"],
            ),
        ]

        for env_map, override, expected in cases:
            with self.subTest(expected=expected):
                with patch.dict("os.environ", env_map, clear=True):
                    self.assertEqual(sender.resolve_recipients(override), expected)

    def test_send_dry_run_skips_bridge_call_with_item_count_override(self):
        request = self._request(item_count_override=3)
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(
                request,
                dry_run=True,
                bridge_send=bridge_send,
                now_provider=lambda: datetime(2026, 4, 24, 8, 0, tzinfo=sender.JST),
            )

        self.assertEqual(result.status, "dry_run")
        self.assertIsNone(result.reason)
        self.assertEqual(result.subject, "[X下書き] Giants news drafts 2026-04-24 08:00")
        self.assertEqual(result.recipients, ["xdraft@example.com"])
        self.assertEqual(result.item_count, 3)
        self.assertIsNone(result.bridge_result)
        bridge_send.assert_not_called()

    def test_send_real_path_calls_bridge_once_with_mail_request(self):
        body_path = self._write_body(self._body_text(count=3))
        request = self._request(body_text_path=str(body_path), item_count_override=3)
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(
                request,
                dry_run=False,
                bridge_send=bridge_send,
                now_provider=lambda: datetime(2026, 4, 24, 8, 0, tzinfo=sender.JST),
            )

        self.assertEqual(result.status, "sent")
        self.assertIs(result.bridge_result, bridge_result)
        bridge_send.assert_called_once()
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(bridge_send.call_args.kwargs, {"dry_run": False})
        self.assertIsInstance(mail_request, mail_delivery_bridge.MailRequest)
        self.assertEqual(mail_request.subject, "[X下書き] Giants news drafts 2026-04-24 08:00")
        self.assertEqual(mail_request.text_body, self._body_text(count=3))
        self.assertEqual(mail_request.to, ["xdraft@example.com"])

    def test_send_suppresses_missing_body_when_path_is_blank(self):
        request = self._request(body_text_path=" ")
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "MISSING_BODY")
        self.assertEqual(result.item_count, 0)
        bridge_send.assert_not_called()

    def test_send_suppresses_missing_body_when_file_is_absent(self):
        request = self._request(body_text_path=str(self.root / "missing-body.txt"))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "MISSING_BODY")
        self.assertEqual(result.item_count, 0)
        bridge_send.assert_not_called()

    def test_send_suppresses_empty_body_text(self):
        body_path = self._write_body(" \n\t", filename="empty-body.txt")
        request = self._request(body_text_path=str(body_path))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "EMPTY_BODY")
        self.assertEqual(result.item_count, 0)
        bridge_send.assert_not_called()

    def test_send_suppresses_no_items_when_override_is_zero(self):
        body_path = self._write_body(self._body_text(count=2), filename="body-no-items-override.txt")
        request = self._request(body_text_path=str(body_path), item_count_override=0)
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "NO_ITEMS")
        self.assertEqual(result.item_count, 0)
        bridge_send.assert_not_called()

    def test_send_suppresses_no_items_when_body_has_no_candidate_markers(self):
        body_path = self._write_body("X Draft Email Digest\nitems: 0\nexcluded: 0\n", filename="body-no-markers.txt")
        request = self._request(body_text_path=str(body_path))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "NO_ITEMS")
        self.assertEqual(result.item_count, 0)
        bridge_send.assert_not_called()

    def test_send_suppresses_when_no_recipient_is_available(self):
        request = self._request(item_count_override=1)
        bridge_send = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "NO_RECIPIENT")
        self.assertEqual(result.recipients, [])
        self.assertEqual(result.item_count, 1)
        bridge_send.assert_not_called()

    def test_send_uses_mail_bridge_to_fallback_when_x_draft_recipient_missing(self):
        request = self._request(item_count_override=1)
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
        request = self._request(item_count_override=1, override_recipient=["override@example.com,second@example.com"])
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(
            "os.environ",
            {"X_DRAFT_EMAIL_TO": "xdraft@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
            clear=True,
        ):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.recipients, ["override@example.com", "second@example.com"])
        self.assertEqual(bridge_send.call_args.args[0].to, ["override@example.com", "second@example.com"])

    def test_send_uses_subject_override_on_real_path(self):
        request = self._request(item_count_override=1, override_subject_datetime="2026-04-24 12:30")
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(
                request,
                dry_run=False,
                bridge_send=bridge_send,
                now_provider=lambda: datetime(2026, 4, 24, 8, 0, tzinfo=sender.JST),
            )

        self.assertEqual(result.subject, "[X下書き] Giants news drafts 2026-04-24 12:30")
        self.assertEqual(bridge_send.call_args.args[0].subject, "[X下書き] Giants news drafts 2026-04-24 12:30")

    def test_send_uses_html_body_when_path_given(self):
        html_path = self._write_html()
        request = self._request(item_count_override=1, body_html_path=str(html_path))
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(bridge_send.call_args.args[0].html_body, "<p>html</p>")

    def test_send_wraps_bridge_result_in_sent_path(self):
        request = self._request(item_count_override=1)
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            result = sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertIs(result.bridge_result, bridge_result)


class RunXDraftEmailSendDryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)

    def _write_body(self, text, *, filename="body.txt"):
        path = self.root / filename
        path.write_text(text, encoding="utf-8")
        return path

    def test_cli_dry_run_prints_request_item_count_subject_and_result(self):
        body_text = (
            "X Draft Email Digest\n"
            "items: 2\n"
            "excluded: 0\n\n"
            "candidate 1\n"
            "recommended_account: official\n\n"
            "candidate 2\n"
            "recommended_account: inner\n"
        )
        body_path = self._write_body(body_text)
        stdout = io.StringIO()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            with patch("sys.stdout", stdout):
                code = run_x_draft_email_send_dry_run.main(
                    [
                        "--body-text-path",
                        str(body_path),
                        "--subject-datetime",
                        "2026-04-24 08:00",
                    ]
                )

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn(
            f"[request] body_text_path={str(body_path)!r} body_text_len={len(body_text)} "
            "body_html=no subject_override=2026-04-24 08:00 item_count_override=none to_override=none",
            output,
        )
        self.assertIn("[item_count] 2", output)
        self.assertIn("[subject] '[X下書き] Giants news drafts 2026-04-24 08:00'", output)
        self.assertIn(
            "[result] status=dry_run reason=None recipients=['xdraft@example.com'] item_count=2",
            output,
        )

    def test_cli_suppressed_empty_body_skips_subject(self):
        body_path = self._write_body(" \n")
        stdout = io.StringIO()

        with patch.dict("os.environ", {"X_DRAFT_EMAIL_TO": "xdraft@example.com"}, clear=True):
            with patch("sys.stdout", stdout):
                code = run_x_draft_email_send_dry_run.main(
                    [
                        "--body-text-path",
                        str(body_path),
                        "--subject-datetime",
                        "2026-04-24 08:00",
                        "--to",
                        "override@example.com",
                    ]
                )

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn(
            f"[request] body_text_path={str(body_path)!r} body_text_len=2 "
            "body_html=no subject_override=2026-04-24 08:00 item_count_override=none "
            "to_override=['override@example.com']",
            output,
        )
        self.assertIn("[item_count] 0", output)
        self.assertIn("[subject] <skipped>", output)
        self.assertIn(
            "[result] status=suppressed reason=EMPTY_BODY recipients=[] item_count=0",
            output,
        )


if __name__ == "__main__":
    unittest.main()
