import inspect
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import publish_notice_email_sender as sender


class PublishNoticeBurstSummaryTests(unittest.TestCase):
    def _bridge_result(self):
        return mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )

    def _request(self, **overrides):
        payload = {
            "post_id": 100,
            "title": "巨人が接戦を制した",
            "canonical_url": "https://yoshilover.com/post-100/",
            "subtype": "postgame",
            "publish_time_iso": "2026-04-26T20:15:00+09:00",
            "summary": "終盤の一打で試合を決めた。",
        }
        payload.update(overrides)
        return sender.PublishNoticeRequest(**payload)

    def _summary_entry(self, index: int) -> sender.BurstSummaryEntry:
        return sender.BurstSummaryEntry(
            post_id=index,
            title=f"公開記事 {index}",
            category="試合速報" if index % 2 else "球団情報",
            publishable=True,
            cleanup_required=index % 3 == 0,
            cleanup_success=True if index % 3 == 0 else None,
        )

    def _alert_request(self, alert_type: str, **overrides) -> sender.AlertMailRequest:
        payload = {
            "alert_type": alert_type,
            "post_id": 501,
            "title": "公開アラート対象",
            "category": "試合速報",
            "reason": "wp_rest_500",
            "detail": "detail text",
            "publishable": True,
            "cleanup_required": False,
            "cleanup_success": None,
            "hold_reason": None,
        }
        payload.update(overrides)
        return sender.AlertMailRequest(**payload)

    def test_layer1_per_post_mail_sent_for_each_post(self):
        bridge_send = MagicMock(return_value=self._bridge_result())

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            requests = [
                self._request(post_id=201, title="公開1"),
                self._request(post_id=202, title="公開2"),
                self._request(post_id=203, title="公開3"),
            ]
            results = [
                sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send) for request in requests
            ]

        self.assertEqual([result.status for result in results], ["sent", "sent", "sent"])
        self.assertEqual(bridge_send.call_count, 3)
        subjects = [call.args[0].subject for call in bridge_send.call_args_list]
        self.assertEqual(
            subjects,
            [
                "【投稿候補】公開1 | YOSHILOVER",
                "【投稿候補】公開2 | YOSHILOVER",
                "【投稿候補】公開3 | YOSHILOVER",
            ],
        )

    def test_layer2_summary_mail_sent_every_10_posts(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        summary_requests = sender.build_burst_summary_requests(
            [self._summary_entry(index) for index in range(1, 21)],
            summary_every=10,
            daily_cap=100,
        )
        summary_requests = [
            sender.BurstSummaryRequest(
                entries=request.entries,
                cumulative_published_count=request.cumulative_published_count,
                daily_cap=request.daily_cap,
                hard_stop_count=1 if idx == 0 else 0,
                hold_count=2 if idx == 0 else 1,
            )
            for idx, request in enumerate(summary_requests)
        ]

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            results = [
                sender.send_summary(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)
                for request in summary_requests
            ]

        self.assertEqual(len(summary_requests), 2)
        self.assertEqual([result.status for result in results], ["sent", "sent"])
        self.assertEqual(
            [call.args[0].subject for call in bridge_send.call_args_list],
            [
                "【まとめ】直近10件 | YOSHILOVER",
                "【まとめ】直近10件 | YOSHILOVER",
            ],
        )
        first_body = bridge_send.call_args_list[0].args[0].text_body
        self.assertIn("hard_stop_count: 1", first_body)
        self.assertIn("hold_count: 2", first_body)
        self.assertIn("daily_cap_remaining: 90", first_body)
        self.assertIn("post_id=1 | title=公開記事 1 | category=試合速報", first_body)

    def test_layer3_alert_mail_for_publish_failure(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._alert_request("publish_failure", reason="wp_rest_500", detail="HTTP 500 from WP REST API")

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send_alert(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(mail_request.subject, "【警告】post_id=501 | YOSHILOVER")
        self.assertIn("reason: wp_rest_500", mail_request.text_body)

    def test_layer3_alert_mail_for_hard_stop(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._alert_request(
            "hard_stop",
            reason="hard_stop_subject_missing",
            detail="subject missing in body",
            publishable=False,
        )

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send_alert(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(mail_request.subject, "【警告】post_id=501 | YOSHILOVER")
        self.assertIn("publishable: false", mail_request.text_body)

    def test_layer3_alert_mail_for_postcheck_failure(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._alert_request(
            "postcheck_failure",
            reason="status_mismatch",
            detail="GET status=draft after publish attempt",
        )

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send_alert(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(mail_request.subject, "【警告】post_id=501 | YOSHILOVER")
        self.assertIn("detail: GET status=draft after publish attempt", mail_request.text_body)

    def test_layer3_alert_mail_for_cleanup_hold(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._alert_request(
            "cleanup_hold",
            reason="cleanup_failed_post_condition",
            detail="prose_lt_100",
            cleanup_required=True,
            cleanup_success=False,
            hold_reason="cleanup_failed_post_condition",
        )

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send_alert(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(mail_request.subject, "【警告】post_id=501 | YOSHILOVER")
        self.assertIn("cleanup_required: true", mail_request.text_body)
        self.assertIn("cleanup_success: false", mail_request.text_body)

    def test_layer3_alert_mail_for_x_sns_risk_flag(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._alert_request(
            "x_sns_auto_post_risk",
            reason="x_sns_auto_post_risk",
            detail="meta flag detected before publish",
        )

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send_alert(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(mail_request.subject, "【警告】post_id=501 | YOSHILOVER")
        self.assertIn("reason: x_sns_auto_post_risk", mail_request.text_body)

    def test_layer4_emergency_hook_signature_present(self):
        signature = inspect.signature(sender.emit_emergency_hook)
        self.assertEqual(list(signature.parameters.keys()), ["request", "hook"])
        request = sender.EmergencyMailRequest(post_id=777, title="緊急通知")
        result = sender.emit_emergency_hook(request, hook=lambda payload: payload.post_id)
        self.assertEqual(result, 777)
        self.assertEqual(sender.build_emergency_subject(request), "【緊急】X/SNS 確認 | YOSHILOVER")

    def test_layer5_duplicate_within_30min_suppressed(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 4, 26, 21, 0, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "reason": None,
                        "post_id": 100,
                        "recorded_at": (now - timedelta(minutes=20)).isoformat(),
                        "notice_kind": "per_post",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
                result = sender.send(
                    self._request(post_id=100),
                    dry_run=False,
                    send_enabled=True,
                    bridge_send=bridge_send,
                    duplicate_history_path=queue_path,
                    now=now,
                )

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "DUPLICATE_WITHIN_30MIN")
        bridge_send.assert_not_called()

    def test_layer5_duplicate_after_30min_not_suppressed(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 4, 26, 21, 0, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "reason": None,
                        "post_id": 100,
                        "recorded_at": (now - timedelta(minutes=31)).isoformat(),
                        "notice_kind": "per_post",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
                result = sender.send(
                    self._request(post_id=100),
                    dry_run=False,
                    send_enabled=True,
                    bridge_send=bridge_send,
                    duplicate_history_path=queue_path,
                    now=now,
                )

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
