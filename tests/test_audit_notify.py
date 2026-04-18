import unittest
from datetime import datetime
from unittest.mock import patch

from src import audit_notify
from src.acceptance_fact_check import Finding, PostReport


class DummyWP:
    def __init__(self, posts):
        self._posts = posts
        self.base_url = "https://yoshilover.com"

    def get_categories(self):
        return [
            {"id": 663, "name": "試合速報", "slug": "game"},
            {"id": 665, "name": "首脳陣", "slug": "manager"},
            {"id": 672, "name": "コラム", "slug": "column"},
        ]

    def list_posts(self, **kwargs):
        status = kwargs.get("status")
        return [post for post in self._posts if post.get("status") == status]


def _post(
    post_id: int,
    *,
    status: str = "draft",
    featured_media: int = 0,
    content_html: str = "",
    title: str = "巨人が阪神に3-2で勝利",
):
    return {
        "id": post_id,
        "status": status,
        "date": "2026-04-19T10:10:00+09:00",
        "modified": "2026-04-19T10:20:00+09:00",
        "title": {"raw": title},
        "content": {"raw": content_html},
        "categories": [663],
        "link": f"https://yoshilover.com/archives/{post_id}",
        "featured_media": featured_media,
    }


class CoreBodyTests(unittest.TestCase):
    def test_core_body_text_removes_related_posts_block(self):
        content_html = """
        <p>巨人が阪神に3-2で勝利した。</p>
        <!-- wp:html -->
        <div class="yoshilover-related-posts">
          <div>【関連記事】</div>
          <ul><li><a href="https://example.com/1">関連記事</a></li></ul>
        </div>
        <!-- /wp:html -->
        <p>次戦へどうつなげるかが焦点です。</p>
        """

        core_text = audit_notify._core_body_text(content_html)

        self.assertIn("巨人が阪神に3-2で勝利した。", core_text)
        self.assertIn("次戦へどうつなげるかが焦点です。", core_text)
        self.assertNotIn("【関連記事】", core_text)
        self.assertNotIn("関連記事", core_text)


class RunAuditNotificationTests(unittest.TestCase):
    def _fixed_now(self) -> datetime:
        return datetime(2026, 4, 19, 10, 30, tzinfo=audit_notify.JST)

    @patch.object(audit_notify, "_build_pipeline_error_findings", return_value=[])
    @patch.object(audit_notify.fact_check_notifier, "_log_event")
    @patch.object(audit_notify.fact_check_notifier, "send_email")
    @patch.object(audit_notify.acceptance_fact_check, "build_post_report")
    @patch.object(audit_notify.draft_audit, "audit_post")
    def test_run_audit_notification_skips_email_when_no_findings(
        self,
        mock_audit_post,
        mock_build_post_report,
        mock_send_email,
        _mock_log_event,
        _mock_pipeline,
    ):
        post = _post(
            1001,
            featured_media=321,
            content_html="<p>個人的に今後も期待したいと思います。十分に長い本文をここに入れておきます。"
            "さらに試合の分岐点と投手運用についても振り返ります。"
            "まだ続きます。280文字を超えるだけの本文を用意するために文を重ねます。"
            "打線のつながり、守備の安定感、次戦への視点まで書いておきます。"
            "ベンチワークの狙い、継投判断の妥当性、終盤の代打策まで触れて、"
            "読後に内容が薄いと感じない程度の長さを確保します。</p>",
        )
        wp = DummyWP([post])
        mock_audit_post.return_value = {
            "id": 1001,
            "title": post["title"]["raw"],
            "status": "draft",
            "primary_category": "試合速報",
            "article_subtype": "general",
            "edit_url": "https://yoshilover.com/wp-admin/post.php?post=1001&action=edit",
        }
        mock_build_post_report.return_value = PostReport(
            post_id=1001,
            title=post["title"]["raw"],
            status="draft",
            primary_category="試合速報",
            article_subtype="general",
            modified=post["modified"],
            edit_url="https://yoshilover.com/wp-admin/post.php?post=1001&action=edit",
            result="green",
            findings=[],
            source_urls=[],
        )

        payload = audit_notify.run_audit_notification(window_minutes=60, send=True, now=self._fixed_now(), wp=wp)

        self.assertEqual(payload["counts"], {axis: 0 for axis in audit_notify.AUDIT_AXES})
        self.assertEqual(payload["total"], 0)
        self.assertFalse(payload["mail_sent"])
        mock_send_email.assert_not_called()

    @patch.object(audit_notify, "_fetch_pipeline_error_count", return_value=0)
    @patch.object(audit_notify, "_fetch_pipeline_error_post_events", return_value={1002: "x_post_ai_failed"})
    @patch.object(audit_notify.fact_check_notifier, "_log_event")
    @patch.object(audit_notify.fact_check_notifier, "send_email", return_value={"mode": "smtp", "message_id": "<id>"})
    @patch.object(audit_notify.acceptance_fact_check, "build_post_report")
    @patch.object(audit_notify.draft_audit, "audit_post")
    def test_run_audit_notification_builds_findings_and_sends_email(
        self,
        mock_audit_post,
        mock_build_post_report,
        mock_send_email,
        _mock_log_event,
        _mock_pipeline_events,
        _mock_pipeline_count,
    ):
        post = _post(
            1002,
            featured_media=0,
            content_html="""
            <p>巨人が阪神に3-2で勝利した。</p>
            <!-- wp:html -->
            <div class="yoshilover-related-posts">
              <div>【関連記事】</div>
            </div>
            <!-- /wp:html -->
            """,
        )
        wp = DummyWP([post])
        mock_audit_post.return_value = {
            "id": 1002,
            "title": post["title"]["raw"],
            "status": "draft",
            "primary_category": "試合速報",
            "article_subtype": "lineup",
            "edit_url": "https://yoshilover.com/wp-admin/post.php?post=1002&action=edit",
        }
        mock_build_post_report.return_value = PostReport(
            post_id=1002,
            title=post["title"]["raw"],
            status="draft",
            primary_category="試合速報",
            article_subtype="lineup",
            modified=post["modified"],
            edit_url="https://yoshilover.com/wp-admin/post.php?post=1002&action=edit",
            result="red",
            findings=[
                Finding(
                    severity="red",
                    field="opponent",
                    current="阪神",
                    expected="ヤクルト",
                    evidence_url="https://example.com/source",
                    message="opponent が不一致",
                    cause="title_rewrite_mismatch",
                    proposal="修正する",
                )
            ],
            source_urls=["https://example.com/source"],
        )

        payload = audit_notify.run_audit_notification(window_minutes=60, send=True, now=self._fixed_now(), wp=wp)

        self.assertEqual(payload["counts"]["title_body_mismatch"], 1)
        self.assertEqual(payload["counts"]["thin_body"], 1)
        self.assertEqual(payload["counts"]["no_opinion"], 1)
        self.assertEqual(payload["counts"]["no_eyecatch"], 1)
        self.assertEqual(payload["counts"]["pipeline_error"], 1)
        self.assertEqual(payload["total"], 5)
        self.assertTrue(payload["mail_sent"])
        self.assertEqual(len(payload["findings"]), 5)
        subject = mock_send_email.call_args.kwargs["subject"]
        self.assertIn("[yoshilover] 問題 5 件", subject)
        self.assertIn("タイトル矛盾 1", subject)
        self.assertIn("薄さ 1", subject)
        self.assertIn("意見なし 1", subject)
        self.assertIn("アイキャッチ 1", subject)
        self.assertIn("pipeline 1", subject)
        first_excerpt = payload["findings"][0]["excerpt"]
        self.assertIn("巨人が阪神に3-2で勝利した。", first_excerpt)
        self.assertNotIn("【関連記事】", first_excerpt)


if __name__ == "__main__":
    unittest.main()
