import unittest
from unittest.mock import patch

from src import fact_check_notifier
from src.acceptance_fact_check import Finding, PostReport


class FactCheckNotifierTests(unittest.TestCase):
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

        subject = fact_check_notifier.build_email_subject(reports, since="yesterday")

        self.assertIn("🔴1件 / 🟡1件 / ✅1件", subject)
        self.assertIn("事実チェック結果", subject)

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

        html = fact_check_notifier.build_email_html(reports, since="yesterday")

        self.assertIn("🔴 要対応", html)
        self.assertIn("✅ 公開候補", html)
        self.assertIn("post_id=62483", html)
        self.assertIn("WPで開く", html)
        self.assertIn("https://yoshilover.com/wp-admin/post.php?post=62483&amp;action=edit", html)

    def test_build_email_html_shows_happy_path_when_no_red(self):
        html = fact_check_notifier.build_email_html([self._report(62490, "green")], since="yesterday")

        self.assertIn("重大な事実誤りは検出されませんでした", html)

    @patch.object(fact_check_notifier, "_fetch_secret_from_secret_manager", return_value="abcd efgh ijkl mnop")
    def test_load_gmail_app_password_uses_secret_manager_fallback(self, _mock_secret):
        with patch.dict("os.environ", {"GMAIL_APP_PASSWORD": "", "GMAIL_APP_PASSWORD_SECRET_NAME": "yoshilover-gmail-app-password"}, clear=False):
            password = fact_check_notifier._load_gmail_app_password()

        self.assertEqual(password, "abcd efgh ijkl mnop")

    @patch.object(fact_check_notifier.acceptance_fact_check, "collect_reports")
    @patch.object(fact_check_notifier, "send_email")
    def test_run_notification_sends_and_returns_summary(self, mock_send_email, mock_collect_reports):
        mock_collect_reports.return_value = [self._report(62500, "green")]
        with patch.dict("os.environ", {"FACT_CHECK_EMAIL_TO": "fwns6760@gmail.com", "FACT_CHECK_EMAIL_FROM": "fwns6760@gmail.com"}, clear=False):
            payload = fact_check_notifier.run_notification(since="yesterday", send=True)

        self.assertTrue(payload["sent"])
        self.assertEqual(payload["green"], 1)
        mock_send_email.assert_called_once()

    @patch.object(fact_check_notifier.acceptance_fact_check, "collect_reports")
    @patch.object(fact_check_notifier, "send_email", side_effect=RuntimeError("smtp auth failed"))
    def test_run_notification_raises_when_send_fails(self, _mock_send_email, mock_collect_reports):
        mock_collect_reports.return_value = [self._report(62501, "yellow")]
        with patch.dict("os.environ", {"FACT_CHECK_EMAIL_TO": "fwns6760@gmail.com", "FACT_CHECK_EMAIL_FROM": "fwns6760@gmail.com"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "smtp auth failed"):
                fact_check_notifier.run_notification(since="yesterday", send=True)


if __name__ == "__main__":
    unittest.main()
