import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import morning_analyst_email_sender as analyst_sender
from src.tools import run_morning_analyst_dry_run


class MorningAnalystEmailSenderTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)

    def _digest_payload(self, *, latest_date="2026-04-24", comparison_ready=True, status="ready"):
        return {
            "window": {
                "latest_date": latest_date,
                "comparison_ready": comparison_ready,
                "status": status,
            },
            "kpis": {},
            "winners": [],
            "losers": [],
            "query_moves": [],
            "opportunities": [],
            "next_action_candidates": [],
            "revenue": None,
            "social_x": None,
        }

    def _write_digest(self, payload=None, *, filename="digest.json"):
        digest_path = self.root / filename
        digest_path.write_text(
            json.dumps(payload or self._digest_payload(), ensure_ascii=False),
            encoding="utf-8",
        )
        return digest_path

    def _write_body(self, text="今日の要点\n- sample\n", *, filename="body.txt"):
        body_path = self.root / filename
        body_path.write_text(text, encoding="utf-8")
        return body_path

    def _request(self, **overrides):
        payload = {
            "digest_json_path": None,
            "body_text_path": None,
            "body_html_path": None,
            "override_subject_date": None,
            "override_recipient": None,
        }
        payload.update(overrides)
        if payload["digest_json_path"] is None:
            payload["digest_json_path"] = str(self._write_digest())
        if payload["body_text_path"] is None:
            payload["body_text_path"] = str(self._write_body())
        return analyst_sender.AnalystEmailRequest(**payload)

    def test_load_digest_meta_reads_window_fields(self):
        digest_path = self._write_digest(
            self._digest_payload(latest_date="2026-04-23", comparison_ready=False, status="collecting")
        )

        meta = analyst_sender.load_digest_meta(str(digest_path))

        self.assertEqual(meta.latest_date, "2026-04-23")
        self.assertFalse(meta.comparison_ready)
        self.assertEqual(meta.status, "collecting")

    def test_build_subject_variants(self):
        cases = [
            (
                analyst_sender.AnalystDigestMeta("2026-04-24", True, "ready"),
                None,
                "[analyst] Giants morning digest 2026-04-24",
            ),
            (
                analyst_sender.AnalystDigestMeta("2026-04-24", False, "collecting"),
                None,
                "[analyst][蓄積中] Giants morning digest 2026-04-24",
            ),
            (
                analyst_sender.AnalystDigestMeta("2026-04-24", True, "ready"),
                "2026-04-25",
                "[analyst] Giants morning digest 2026-04-25",
            ),
        ]

        for meta, override_date, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(analyst_sender.build_subject(meta, override_date), expected)

    def test_resolve_recipients_uses_expected_precedence(self):
        cases = [
            (
                {"ANALYST_EMAIL_TO": "analyst@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                None,
                ["analyst@example.com"],
            ),
            (
                {"MAIL_BRIDGE_TO": "bridge@example.com, second@example.com"},
                None,
                ["bridge@example.com", "second@example.com"],
            ),
            (
                {"ANALYST_EMAIL_TO": "analyst@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                ["override@example.com, next@example.com"],
                ["override@example.com", "next@example.com"],
            ),
        ]

        for env_map, override, expected in cases:
            with self.subTest(expected=expected):
                with patch.dict("os.environ", env_map, clear=True):
                    self.assertEqual(analyst_sender.resolve_recipients(override), expected)

    def test_send_dry_run_skips_bridge_call(self):
        request = self._request()
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "dry_run")
        self.assertIsNone(result.reason)
        self.assertEqual(result.subject, "[analyst] Giants morning digest 2026-04-24")
        self.assertEqual(result.recipients, ["analyst@example.com"])
        self.assertIsNone(result.bridge_result)
        bridge_send.assert_not_called()

    def test_send_real_path_calls_bridge_once_with_mail_request(self):
        digest_path = self._write_digest()
        body_path = self._write_body("今日の要点\n- 上昇\n")
        html_path = self._write_body("<p>html</p>", filename="body.html")
        request = self._request(
            digest_json_path=str(digest_path),
            body_text_path=str(body_path),
            body_html_path=str(html_path),
        )
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertIs(result.bridge_result, bridge_result)
        bridge_send.assert_called_once()
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(bridge_send.call_args.kwargs, {"dry_run": False})
        self.assertIsInstance(mail_request, mail_delivery_bridge.MailRequest)
        self.assertEqual(mail_request.subject, "[analyst] Giants morning digest 2026-04-24")
        self.assertEqual(mail_request.text_body, "今日の要点\n- 上昇\n")
        self.assertEqual(mail_request.html_body, "<p>html</p>")
        self.assertEqual(mail_request.to, ["analyst@example.com"])
        self.assertEqual(
            mail_request.metadata,
            {"latest_date": "2026-04-24", "comparison_ready": True, "status": "ready"},
        )

    def test_send_suppresses_missing_digest(self):
        request = self._request(digest_json_path=str(self.root / "missing.json"))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "MISSING_DIGEST")
        self.assertIsNone(result.subject)
        bridge_send.assert_not_called()

    def test_send_suppresses_invalid_json_as_missing_digest(self):
        digest_path = self.root / "digest.json"
        digest_path.write_text("{invalid", encoding="utf-8")
        request = self._request(digest_json_path=str(digest_path))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "MISSING_DIGEST")
        bridge_send.assert_not_called()

    def test_send_suppresses_digest_without_window_key(self):
        digest_path = self._write_digest({"kpis": {}}, filename="digest-no-window.json")
        request = self._request(digest_json_path=str(digest_path))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "INVALID_DIGEST")
        bridge_send.assert_not_called()

    def test_send_suppresses_missing_body_text(self):
        request = self._request(body_text_path=str(self.root / "missing-body.txt"))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "EMPTY_BODY")
        bridge_send.assert_not_called()

    def test_send_suppresses_empty_body_text(self):
        body_path = self._write_body(" \n\t", filename="empty-body.txt")
        request = self._request(body_text_path=str(body_path))
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "EMPTY_BODY")
        bridge_send.assert_not_called()

    def test_send_suppresses_when_no_recipient_is_available(self):
        request = self._request()
        bridge_send = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "NO_RECIPIENT")
        self.assertEqual(result.recipients, [])
        bridge_send.assert_not_called()

    def test_send_uses_subject_override_on_real_path(self):
        request = self._request(override_subject_date="2026-04-25")
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.subject, "[analyst] Giants morning digest 2026-04-25")
        self.assertEqual(bridge_send.call_args.args[0].subject, "[analyst] Giants morning digest 2026-04-25")

    def test_send_uses_recipient_override_over_env(self):
        request = self._request(override_recipient=["override@example.com,second@example.com"])
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(
            "os.environ",
            {"ANALYST_EMAIL_TO": "analyst@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
            clear=True,
        ):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.recipients, ["override@example.com", "second@example.com"])
        self.assertEqual(bridge_send.call_args.args[0].to, ["override@example.com", "second@example.com"])

    def test_send_passes_accumulating_subject_when_comparison_is_not_ready(self):
        digest_path = self._write_digest(self._digest_payload(comparison_ready=False, status="collecting"))
        request = self._request(digest_json_path=str(digest_path))
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            result = analyst_sender.send(request, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.subject, "[analyst][蓄積中] Giants morning digest 2026-04-24")
        self.assertEqual(bridge_send.call_args.args[0].subject, "[analyst][蓄積中] Giants morning digest 2026-04-24")


class RunMorningAnalystDryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)

    def _write_digest(self, *, comparison_ready=True, status="ready"):
        digest_path = self.root / "digest.json"
        digest_path.write_text(
            json.dumps(
                {
                    "window": {
                        "latest_date": "2026-04-24",
                        "comparison_ready": comparison_ready,
                        "status": status,
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return digest_path

    def _write_body(self, text):
        body_path = self.root / "body.txt"
        body_path.write_text(text, encoding="utf-8")
        return body_path

    def test_cli_dry_run_prints_request_meta_subject_and_result(self):
        digest_path = self._write_digest()
        body_path = self._write_body("今日の要点\n- sample\n")
        stdout = io.StringIO()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            with patch("sys.stdout", stdout):
                code = run_morning_analyst_dry_run.main(
                    ["--digest-path", str(digest_path), "--body-text-path", str(body_path)]
                )

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn(
            f"[request] digest_path={str(digest_path)!r} body_text_len=15 body_html=no "
            "subject_date_override=none to_override=none",
            output,
        )
        self.assertIn("[meta] latest_date='2026-04-24' comparison_ready=true status='ready'", output)
        self.assertIn("[subject] '[analyst] Giants morning digest 2026-04-24'", output)
        self.assertIn("[result] status=dry_run reason=None recipients=['analyst@example.com']", output)

    def test_cli_suppressed_path_skips_subject(self):
        digest_path = self._write_digest(comparison_ready=False, status="collecting")
        body_path = self._write_body(" \n")
        stdout = io.StringIO()

        with patch.dict("os.environ", {"ANALYST_EMAIL_TO": "analyst@example.com"}, clear=True):
            with patch("sys.stdout", stdout):
                code = run_morning_analyst_dry_run.main(
                    [
                        "--digest-path",
                        str(digest_path),
                        "--body-text-path",
                        str(body_path),
                        "--subject-date",
                        "2026-04-25",
                        "--to",
                        "override@example.com",
                    ]
                )

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn(
            f"[request] digest_path={str(digest_path)!r} body_text_len=2 body_html=no "
            "subject_date_override=2026-04-25 to_override=['override@example.com']",
            output,
        )
        self.assertIn("[meta] latest_date='2026-04-24' comparison_ready=false status='collecting'", output)
        self.assertIn("[subject] <skipped>", output)
        self.assertIn("[result] status=suppressed reason=EMPTY_BODY recipients=[]", output)


if __name__ == "__main__":
    unittest.main()
