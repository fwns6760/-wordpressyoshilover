import io
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src.tools import run_mail_delivery_dry_run


def _request(**overrides):
    payload = {
        "to": ["reader@example.com"],
        "subject": "Bridge test",
        "text_body": "plain body",
        "html_body": None,
        "sender": None,
        "reply_to": None,
        "metadata": {},
    }
    payload.update(overrides)
    return mail_delivery_bridge.MailRequest(**payload)


class MailDeliveryBridgeTests(unittest.TestCase):
    def test_send_suppresses_empty_requests(self):
        cases = [
            ("NO_RECIPIENT", _request(to=[])),
            ("EMPTY_SUBJECT", _request(subject="   ")),
            ("EMPTY_BODY", _request(text_body=" ", html_body=" \n ")),
        ]

        for expected_reason, request in cases:
            with self.subTest(reason=expected_reason):
                with patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL") as mock_smtp:
                    result = mail_delivery_bridge.send(request, dry_run=False)

                self.assertEqual(result.status, "suppressed")
                self.assertEqual(result.reason, expected_reason)
                self.assertEqual(result.refused_recipients, {})
                self.assertEqual(result.smtp_response, [])
                mock_smtp.assert_not_called()

    def test_send_dry_run_returns_without_loading_credentials(self):
        request = _request()

        with patch.object(mail_delivery_bridge, "load_credentials_from_env") as mock_load_credentials:
            with patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL") as mock_smtp:
                result = mail_delivery_bridge.send(request)

        self.assertEqual(result.status, "dry_run")
        self.assertIsNone(result.reason)
        mock_load_credentials.assert_not_called()
        mock_smtp.assert_not_called()

    def test_send_dry_run_skips_smtp_even_when_credentials_are_provided(self):
        request = _request()
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="secret",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        with patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL") as mock_smtp:
            result = mail_delivery_bridge.send(request, dry_run=True, credentials=credentials)

        self.assertEqual(result.status, "dry_run")
        self.assertEqual(result.refused_recipients, {})
        self.assertEqual(result.smtp_response, [])
        mock_smtp.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
            "MAIL_BRIDGE_FROM": "bridge-from@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge, "make_msgid", return_value="<bridge-message-id@yoshilover.com>")
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_returns_serialized_delivery_details(
        self,
        mock_smtp_ssl,
        _mock_make_msgid,
    ):
        smtp = MagicMock()
        smtp.send_message.return_value = {"blocked@example.com": (550, b"5.1.1 user unknown")}
        smtp.noop.return_value = (250, b"2.0.0 OK")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(to=["reader@example.com", "second@example.com"]),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.refused_recipients, {"blocked@example.com": [550, "5.1.1 user unknown"]})
        self.assertEqual(result.smtp_response, [250, "2.0.0 OK"])
        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 2465, timeout=20)
        smtp.login.assert_called_once_with("bridge-login@example.com", "smtp-pass")
        smtp.send_message.assert_called_once()
        smtp.noop.assert_called_once()
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["From"], "bridge-from@example.com")
        self.assertEqual(message["To"], "reader@example.com, second@example.com")
        self.assertEqual(message["Message-ID"], "<bridge-message-id@yoshilover.com>")

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
            "FACT_CHECK_EMAIL_FROM": "fact-check@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_respects_request_sender_and_reply_to(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(sender="override@example.com", reply_to="reply@example.com"),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["From"], "override@example.com")
        self.assertEqual(message["Reply-To"], "reply@example.com")

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
            "MAIL_BRIDGE_FROM": "bridge-from@example.com",
            "NOTIFY_FROM": "notify@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_prefers_notify_from_over_mail_bridge_from(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["From"], "notify@example.com")

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_falls_back_to_smtp_username_when_sender_envs_unset(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["From"], "bridge-login@example.com")

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
            "MAIL_BRIDGE_REPLY_TO": "bridge-reply@example.com",
            "NOTIFY_REPLY_TO": "notify-reply@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_uses_reply_to_env_when_request_omitted(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["Reply-To"], "notify-reply@example.com")

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
            "MAIL_BRIDGE_REPLY_TO": "Reader <READER@example.com>",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_omits_reply_to_when_it_matches_recipient(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(to=["reader@example.com", "second@example.com"]),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertNotIn("Reply-To", message)

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_omits_request_reply_to_when_it_matches_recipient(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(to=["Reader <reader@example.com>"], reply_to="reader@example.com"),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertNotIn("Reply-To", message)

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_real_path_omits_reply_to_when_env_and_request_are_unset(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertNotIn("Reply-To", message)

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "primary-pass",
            "MAIL_BRIDGE_SMTP_HOST": "bridge.smtp.example.com",
            "MAIL_BRIDGE_SMTP_PORT": "1465",
        },
        clear=True,
    )
    def test_load_credentials_prefers_mail_bridge_primary_values(self):
        credentials = mail_delivery_bridge.load_credentials_from_env()

        self.assertEqual(credentials.app_password, "primary-pass")
        self.assertEqual(credentials.smtp_host, "bridge.smtp.example.com")
        self.assertEqual(credentials.smtp_port, 1465)

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "primary-pass",
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME": "bridge-secret",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge, "_load_secret", return_value="secret-pass")
    def test_load_credentials_prefers_direct_app_password_over_secret_name(self, mock_load_secret):
        credentials = mail_delivery_bridge.load_credentials_from_env()

        self.assertEqual(credentials.app_password, "primary-pass")
        mock_load_secret.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME": "bridge-secret",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge, "_load_secret", return_value="secret-pass")
    def test_load_credentials_uses_mail_bridge_secret_name_when_direct_password_unset(self, mock_load_secret):
        credentials = mail_delivery_bridge.load_credentials_from_env()

        self.assertEqual(credentials.app_password, "secret-pass")
        mock_load_secret.assert_called_once_with("bridge-secret")
        self.assertEqual(credentials.smtp_host, "smtp.gmail.com")
        self.assertEqual(credentials.smtp_port, 465)

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "",
            "GMAIL_APP_PASSWORD": "fallback-pass",
            "FACT_CHECK_SMTP_HOST": "fact.smtp.example.com",
            "FACT_CHECK_SMTP_PORT": "2465",
        },
        clear=True,
    )
    def test_load_credentials_falls_back_to_fact_check_gmail_password(self):
        credentials = mail_delivery_bridge.load_credentials_from_env()

        self.assertEqual(credentials.app_password, "fallback-pass")
        self.assertEqual(credentials.smtp_host, "fact.smtp.example.com")
        self.assertEqual(credentials.smtp_port, 2465)

    @patch.dict("os.environ", {}, clear=True)
    @patch.object(mail_delivery_bridge, "_load_secret", side_effect=RuntimeError("missing secret"))
    def test_load_credentials_raises_when_no_password_is_configured(self, _mock_load_secret):
        with self.assertRaisesRegex(RuntimeError, "no Gmail app password configured"):
            mail_delivery_bridge.load_credentials_from_env()

    def test_smtp_host_and_port_precedence(self):
        cases = [
            (
                {
                    "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "bridge-pass",
                    "MAIL_BRIDGE_SMTP_HOST": "bridge.smtp.example.com",
                    "MAIL_BRIDGE_SMTP_PORT": "1465",
                    "FACT_CHECK_SMTP_HOST": "fact.smtp.example.com",
                    "FACT_CHECK_SMTP_PORT": "2465",
                },
                ("bridge.smtp.example.com", 1465),
            ),
            (
                {
                    "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "bridge-pass",
                    "FACT_CHECK_SMTP_HOST": "fact.smtp.example.com",
                    "FACT_CHECK_SMTP_PORT": "2465",
                },
                ("fact.smtp.example.com", 2465),
            ),
            (
                {
                    "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "bridge-pass",
                },
                ("smtp.gmail.com", 465),
            ),
        ]

        for env_map, expected in cases:
            with self.subTest(expected=expected):
                with patch.dict("os.environ", env_map, clear=True):
                    credentials = mail_delivery_bridge.load_credentials_from_env()
                self.assertEqual((credentials.smtp_host, credentials.smtp_port), expected)

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_SMTP_USERNAME": "bridge-login@example.com",
            "FACT_CHECK_EMAIL_FROM": "fact-check@example.com",
        },
        clear=True,
    )
    @patch.object(mail_delivery_bridge.smtplib, "SMTP_SSL")
    def test_send_builds_multipart_message_when_html_body_is_present(self, mock_smtp_ssl):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"ok")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp
        credentials = mail_delivery_bridge.BridgeCredentials(
            app_password="smtp-pass",
            smtp_host="smtp.example.com",
            smtp_port=2465,
        )

        result = mail_delivery_bridge.send(
            _request(text_body="plain body", html_body="<p>html body</p>"),
            dry_run=False,
            credentials=credentials,
        )

        self.assertEqual(result.status, "sent")
        message = smtp.send_message.call_args.args[0]
        self.assertTrue(message.is_multipart())
        self.assertEqual(message.get_body(preferencelist=("plain",)).get_content().strip(), "plain body")
        self.assertIn("html body", message.get_body(preferencelist=("html",)).get_content())

    @patch.dict(
        "os.environ",
        {
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD": "",
            "MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME": "bridge-secret",
            "GMAIL_APP_PASSWORD": "fallback-pass",
        },
        clear=True,
    )
    def test_load_credentials_succeeds_when_secretmanager_import_is_missing(self):
        real_import_module = mail_delivery_bridge.importlib.import_module

        def _import_module(name: str):
            if name == "google.cloud.secretmanager":
                raise ImportError("not installed")
            return real_import_module(name)

        with patch.object(mail_delivery_bridge.importlib, "import_module", side_effect=_import_module):
            credentials = mail_delivery_bridge.load_credentials_from_env()

        self.assertEqual(credentials.app_password, "fallback-pass")


class RunMailDeliveryDryRunTests(unittest.TestCase):
    def test_cli_prints_dry_run_result(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = run_mail_delivery_dry_run.main(
                ["--to", "test@example.com", "--subject", "bridge smoke", "--body-text", "hello"]
            )

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("[request] to=['test@example.com'] subject='bridge smoke' body_text_len=5 has_html=no", output)
        self.assertIn("[result] status=dry_run reason=None", output)

    def test_cli_reports_suppressed_empty_body(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = run_mail_delivery_dry_run.main(
                ["--to", "test@example.com", "--subject", "bridge smoke", "--body-text", ""]
            )

        self.assertEqual(code, 0)
        self.assertIn("[result] status=suppressed reason=EMPTY_BODY", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
