import sys
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src import fact_check_notifier
from src import acceptance_auto_fix
from src.acceptance_fact_check import Finding, PostReport


class FactCheckNotifierTests(unittest.TestCase):
    def _fixed_now(self) -> datetime:
        return datetime(2026, 4, 17, 7, 0, tzinfo=fact_check_notifier.JST)

    def _report(self, post_id: int, result: str, *, title: str = "記事タイトル", findings=None) -> PostReport:
        return PostReport(
            post_id=post_id,
            title=title,
            status="draft",
            primary_category="試合速報",
            article_subtype="postgame",
            modified="2026-04-17T06:55:00+09:00",
            edit_url=f"https://yoshilover.com/wp-admin/post.php?post={post_id}&action=edit",
            result=result,
            findings=findings or [],
            source_urls=["https://example.com/source"],
        )

    def test_build_email_subject_uses_report_counts(self):
        reports = [
            self._report(1, "red"),
            self._report(2, "yellow"),
            self._report(3, "green"),
        ]

        subject = fact_check_notifier.build_email_subject(reports, now=self._fixed_now())

        self.assertEqual(subject, "ヨシラバー 04/17 07:00 🔴1 🟡1 ✅1")

    def test_should_send_email_returns_true_when_hourly_window_has_posts(self):
        reports = [self._report(10, "green")]

        should_send, reason = fact_check_notifier._should_send_email(reports, posts_in_last_hour=reports)

        self.assertTrue(should_send)
        self.assertEqual(reason, "hourly_window_has_posts")

    def test_should_send_email_returns_true_when_red_exists_without_recent_posts(self):
        reports = [self._report(11, "red")]

        should_send, reason = fact_check_notifier._should_send_email(reports, posts_in_last_hour=[])

        self.assertTrue(should_send)
        self.assertEqual(reason, "red_present")

    def test_should_send_email_returns_false_when_no_change_and_no_red(self):
        reports = [self._report(12, "green")]

        should_send, reason = fact_check_notifier._should_send_email(reports, posts_in_last_hour=[])

        self.assertFalse(should_send)
        self.assertEqual(reason, "no_change_no_red")

    def test_build_email_html_renders_sections_and_wp_links(self):
        reports = [
            self._report(
                62483,
                "red",
                title="巨人DeNA戦 神宮18:00試合開始",
                findings=[
                    Finding(
                        severity="red",
                        field="opponent",
                        current="DeNA",
                        expected="ヤクルト",
                        evidence_url="https://baseball.yahoo.co.jp/npb/game/2026041701/top",
                        message="opponent が不一致",
                        cause="title_rewrite_mismatch",
                        proposal="WP title の `DeNA` を `ヤクルト` に置換する",
                    )
                ],
            ),
            self._report(62484, "green", title="巨人ヤクルト戦 神宮18:00試合開始"),
        ]

        fix_summary = acceptance_auto_fix.AutoFixSummary(
            checked_posts=2,
            autofix_candidates=[],
            rejects=[],
            manual_reviews=[],
            no_action=[],
        )
        html = fact_check_notifier.build_email_html(reports, since="yesterday", fix_summary=fix_summary)

        self.assertIn("🔴 要対応", html)
        self.assertIn("✅ 公開候補", html)
        self.assertIn("自動修正候補", html)
        self.assertIn("差し戻し推奨", html)
        self.assertIn("手動確認必要", html)
        self.assertIn("post_id=62483", html)
        self.assertIn("WPで開く", html)
        self.assertIn("https://yoshilover.com/wp-admin/post.php?post=62483&amp;action=edit", html)

    def test_build_email_html_shows_happy_path_when_no_red(self):
        fix_summary = acceptance_auto_fix.AutoFixSummary(
            checked_posts=1,
            autofix_candidates=[],
            rejects=[],
            manual_reviews=[],
            no_action=[],
        )
        html = fact_check_notifier.build_email_html([self._report(62490, "green")], since="yesterday", fix_summary=fix_summary)

        self.assertIn("重大な事実誤りは検出されませんでした", html)

    @patch.object(fact_check_notifier, "_fetch_logging_entries")
    def test_load_recent_operations_summary_aggregates_recent_logs(self, mock_fetch_logging_entries):
        mock_fetch_logging_entries.return_value = [
            {
                "timestamp": "2026-04-18T06:30:00Z",
                "textPayload": '{"event":"rss_fetcher_run_summary","drafts_created":1,"skip_duplicate":2,"skip_filter":4,"error_count":1,"x_post_count":1}',
            },
            {
                "timestamp": "2026-04-18T06:30:01Z",
                "textPayload": '{"event":"rss_fetcher_flow_summary","created_subtype_counts":{"player":1}}',
            },
            {
                "timestamp": "2026-04-17T08:00:00Z",
                "textPayload": '{"event":"rss_fetcher_run_summary","drafts_created":2,"skip_duplicate":1,"skip_filter":3,"error_count":0,"x_post_count":5}',
            },
            {
                "timestamp": "2026-04-17T08:00:01Z",
                "textPayload": '{"event":"rss_fetcher_flow_summary","created_subtype_counts":{"lineup":2}}',
            },
            {
                "timestamp": "2026-04-17T06:00:00Z",
                "textPayload": '{"event":"rss_fetcher_run_summary","drafts_created":9,"skip_duplicate":9,"skip_filter":9,"error_count":9,"x_post_count":4}',
            },
        ]

        summary = fact_check_notifier._load_recent_operations_summary(
            now=datetime(2026, 4, 18, 16, 0, tzinfo=fact_check_notifier.JST)
        )

        self.assertEqual(summary.drafts_created, 3)
        self.assertEqual(summary.created_subtype_counts, {"lineup": 2, "player": 1})
        self.assertEqual(summary.skip_duplicate, 3)
        self.assertEqual(summary.skip_filter, 7)
        self.assertEqual(summary.error_count, 1)
        self.assertEqual(summary.x_post_count, 2)
        self.assertIsNone(summary.publish_count)
        self.assertEqual(summary.fetch_error, "")

    @patch.object(fact_check_notifier, "_fetch_secret_from_secret_manager", return_value="abcd efgh ijkl mnop")
    def test_load_gmail_app_password_uses_secret_manager_fallback(self, _mock_secret):
        with patch.dict("os.environ", {"GMAIL_APP_PASSWORD": "", "GMAIL_APP_PASSWORD_SECRET_NAME": "yoshilover-gmail-app-password"}, clear=False):
            password = fact_check_notifier._load_gmail_app_password()

        self.assertEqual(password, "abcd efgh ijkl mnop")

    def test_fetch_secret_uses_discovered_project_when_env_missing(self):
        mock_default = MagicMock(return_value=(object(), "baseballsite"))
        mock_session = MagicMock()
        mock_session.get.return_value.status_code = 200
        mock_session.get.return_value.json.return_value = {"payload": {"data": "YWJjZA=="}}
        mock_session_cls = MagicMock(return_value=mock_session)
        google_module = types.ModuleType("google")
        google_auth_module = types.ModuleType("google.auth")
        google_auth_module.default = mock_default
        google_transport_module = types.ModuleType("google.auth.transport")
        google_requests_module = types.ModuleType("google.auth.transport.requests")
        google_requests_module.AuthorizedSession = mock_session_cls
        with patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "", "GCP_PROJECT": "", "GCLOUD_PROJECT": ""}, clear=False):
            with patch.dict(
                sys.modules,
                {
                    "google": google_module,
                    "google.auth": google_auth_module,
                    "google.auth.transport": google_transport_module,
                    "google.auth.transport.requests": google_requests_module,
                },
            ):
                secret = fact_check_notifier._fetch_secret_from_secret_manager("yoshilover-gmail-app-password")

        self.assertEqual(secret, "abcd")

    @patch.object(fact_check_notifier, "_load_gmail_app_password", return_value="abcd efgh ijkl mnop")
    @patch.object(fact_check_notifier, "make_msgid", return_value="<test-message-id@yoshilover.com>")
    @patch.object(fact_check_notifier.smtplib, "SMTP_SSL")
    def test_send_email_returns_message_id_and_refused_recipients(
        self,
        mock_smtp_ssl,
        _mock_make_msgid,
        _mock_load_password,
    ):
        smtp = MagicMock()
        smtp.send_message.return_value = {}
        smtp.noop.return_value = (250, b"2.0.0 OK")
        mock_smtp_ssl.return_value.__enter__.return_value = smtp

        delivery = fact_check_notifier.send_email(
            subject="テスト件名",
            html_body="<p>html</p>",
            text_body="text",
            to_email="fwns6760@gmail.com",
            from_email="fwns6760@gmail.com",
        )

        self.assertEqual(delivery["mode"], "smtp")
        self.assertEqual(delivery["message_id"], "<test-message-id@yoshilover.com>")
        self.assertEqual(delivery["refused_recipients"], {})
        self.assertEqual(delivery["smtp_response"], [250, "2.0.0 OK"])
        smtp.login.assert_called_once_with("fwns6760@gmail.com", "abcd efgh ijkl mnop")
        smtp.send_message.assert_called_once()
        smtp.noop.assert_called_once()

    @patch.object(fact_check_notifier.acceptance_fact_check, "collect_reports")
    @patch.object(fact_check_notifier.acceptance_auto_fix, "analyze_reports")
    @patch.object(fact_check_notifier, "_load_recent_operations_summary")
    @patch.object(fact_check_notifier, "_now_jst")
    @patch.object(fact_check_notifier, "send_email")
    @patch.object(fact_check_notifier, "_log_event")
    def test_run_notification_sends_and_returns_summary(
        self,
        mock_log_event,
        mock_send_email,
        mock_now_jst,
        mock_load_recent_operations_summary,
        mock_analyze_reports,
        mock_collect_reports,
    ):
        mock_now_jst.return_value = self._fixed_now()
        mock_collect_reports.return_value = [self._report(62500, "green")]
        mock_analyze_reports.return_value = acceptance_auto_fix.AutoFixSummary(1, [], [], [], [])
        mock_load_recent_operations_summary.return_value = fact_check_notifier.OperationsSummary(
            drafts_created=3,
            created_subtype_counts={"lineup": 2, "postgame": 1},
            skip_duplicate=1,
            skip_filter=2,
            error_count=0,
            x_post_count=0,
        )
        mock_send_email.return_value = {
            "mode": "smtp",
            "message_id": "<fact-check-1@yoshilover.com>",
            "refused_recipients": {},
            "smtp_response": [250, "2.0.0 OK"],
        }
        with patch.dict("os.environ", {"FACT_CHECK_EMAIL_TO": "fwns6760@gmail.com", "FACT_CHECK_EMAIL_FROM": "fwns6760@gmail.com"}, clear=False):
            payload = fact_check_notifier.run_notification(since="yesterday", send=True)

        self.assertTrue(payload["sent"])
        self.assertEqual(payload["green"], 1)
        self.assertEqual(payload["reason"], "hourly_window_has_posts")
        self.assertEqual(payload["posts_in_last_hour_count"], 1)
        self.assertIn("📊 直近24h運用サマリ", payload["text_body"])
        mock_send_email.assert_called_once()
        sent_calls = [
            call for call in mock_log_event.call_args_list
            if call.args and call.args[0] == "fact_check_email_sent"
        ]
        self.assertEqual(len(sent_calls), 1)
        sent_payload = sent_calls[0].kwargs
        self.assertEqual(sent_payload["reason"], "hourly_window_has_posts")
        self.assertEqual(sent_payload["posts_in_last_hour_count"], 1)
        self.assertEqual(sent_payload["message_id"], "<fact-check-1@yoshilover.com>")
        self.assertEqual(sent_payload["refused_recipients"], {})
        self.assertEqual(sent_payload["smtp_response"], [250, "2.0.0 OK"])

    @patch.object(fact_check_notifier.acceptance_fact_check, "collect_reports")
    @patch.object(fact_check_notifier.acceptance_auto_fix, "analyze_reports")
    @patch.object(fact_check_notifier, "_load_recent_operations_summary")
    @patch.object(fact_check_notifier, "_now_jst")
    @patch.object(fact_check_notifier, "_fetch_secret_from_secret_manager", side_effect=RuntimeError("missing secret"))
    def test_send_email_falls_back_to_demo_mode_when_password_missing(
        self,
        _mock_secret,
        mock_now_jst,
        mock_load_recent_operations_summary,
        mock_analyze_reports,
        mock_collect_reports,
    ):
        mock_now_jst.return_value = self._fixed_now()
        mock_collect_reports.return_value = [self._report(62502, "red")]
        mock_analyze_reports.return_value = acceptance_auto_fix.AutoFixSummary(1, [], [], [], [])
        mock_load_recent_operations_summary.return_value = fact_check_notifier.OperationsSummary()
        with patch.dict("os.environ", {"GMAIL_APP_PASSWORD": "", "FACT_CHECK_EMAIL_TO": "fwns6760@gmail.com", "FACT_CHECK_EMAIL_FROM": "fwns6760@gmail.com"}, clear=False):
            payload = fact_check_notifier.run_notification(since="yesterday", send=True)

        self.assertFalse(payload["sent"])
        self.assertEqual(payload["delivery_mode"], "demo")

    @patch.object(fact_check_notifier.acceptance_fact_check, "collect_reports")
    @patch.object(fact_check_notifier, "_now_jst")
    @patch.object(fact_check_notifier, "send_email")
    @patch.object(fact_check_notifier, "_log_event")
    def test_run_notification_skips_when_no_recent_posts_and_no_red(
        self,
        mock_log_event,
        mock_send_email,
        mock_now_jst,
        mock_collect_reports,
    ):
        mock_now_jst.return_value = self._fixed_now()
        mock_collect_reports.return_value = [
            self._report(62503, "green", title="古い記事")
        ]
        mock_collect_reports.return_value[0].modified = "2026-04-17T04:30:00+09:00"

        with patch.dict("os.environ", {"FACT_CHECK_EMAIL_TO": "fwns6760@gmail.com", "FACT_CHECK_EMAIL_FROM": "fwns6760@gmail.com"}, clear=False):
            payload = fact_check_notifier.run_notification(since="yesterday", send=True)

        self.assertFalse(payload["sent"])
        self.assertEqual(payload["delivery_mode"], "skipped")
        self.assertEqual(payload["reason"], "no_change_no_red")
        self.assertEqual(payload["posts_in_last_hour_count"], 0)
        mock_send_email.assert_not_called()
        skipped_calls = [
            call for call in mock_log_event.call_args_list
            if call.args and call.args[0] == "fact_check_email_skipped"
        ]
        self.assertEqual(len(skipped_calls), 1)
        self.assertEqual(skipped_calls[0].kwargs["reason"], "no_change_no_red")

    @patch.object(fact_check_notifier.acceptance_fact_check, "collect_reports")
    @patch.object(fact_check_notifier.acceptance_auto_fix, "analyze_reports")
    @patch.object(fact_check_notifier, "_load_recent_operations_summary")
    @patch.object(fact_check_notifier, "_now_jst")
    @patch.object(fact_check_notifier, "send_email")
    def test_run_notification_sends_even_when_operations_summary_fetch_failed(
        self,
        mock_send_email,
        mock_now_jst,
        mock_load_recent_operations_summary,
        mock_analyze_reports,
        mock_collect_reports,
    ):
        mock_now_jst.return_value = self._fixed_now()
        mock_collect_reports.return_value = [self._report(62504, "green")]
        mock_analyze_reports.return_value = acceptance_auto_fix.AutoFixSummary(1, [], [], [], [])
        mock_load_recent_operations_summary.return_value = fact_check_notifier.OperationsSummary(
            fetch_error="RuntimeError: permission denied"
        )
        mock_send_email.return_value = {
            "mode": "smtp",
            "message_id": "<fact-check-2@yoshilover.com>",
            "refused_recipients": {},
            "smtp_response": [250, "2.0.0 OK"],
        }

        with patch.dict("os.environ", {"FACT_CHECK_EMAIL_TO": "fwns6760@gmail.com", "FACT_CHECK_EMAIL_FROM": "fwns6760@gmail.com"}, clear=False):
            payload = fact_check_notifier.run_notification(since="yesterday", send=True)

        self.assertTrue(payload["sent"])
        self.assertIn("集計取得失敗: RuntimeError: permission denied", payload["text_body"])
        mock_send_email.assert_called_once()

    @patch.object(fact_check_notifier.acceptance_fact_check, "collect_reports")
    @patch.object(fact_check_notifier.acceptance_auto_fix, "analyze_reports")
    @patch.object(fact_check_notifier, "_load_recent_operations_summary")
    @patch.object(fact_check_notifier, "_now_jst")
    @patch.object(fact_check_notifier, "send_email", side_effect=RuntimeError("smtp auth failed"))
    def test_run_notification_raises_when_send_fails(
        self,
        _mock_send_email,
        mock_now_jst,
        mock_load_recent_operations_summary,
        mock_analyze_reports,
        mock_collect_reports,
    ):
        mock_now_jst.return_value = self._fixed_now()
        mock_collect_reports.return_value = [self._report(62501, "yellow")]
        mock_analyze_reports.return_value = acceptance_auto_fix.AutoFixSummary(1, [], [], [], [])
        mock_load_recent_operations_summary.return_value = fact_check_notifier.OperationsSummary()
        with patch.dict("os.environ", {"FACT_CHECK_EMAIL_TO": "fwns6760@gmail.com", "FACT_CHECK_EMAIL_FROM": "fwns6760@gmail.com"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "smtp auth failed"):
                fact_check_notifier.run_notification(since="yesterday", send=True)


if __name__ == "__main__":
    unittest.main()
