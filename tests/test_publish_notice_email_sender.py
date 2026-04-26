import unittest
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import publish_notice_email_sender as sender


class PublishNoticeEmailSenderTests(unittest.TestCase):
    def _request(self, **overrides):
        payload = {
            "post_id": 123,
            "title": "巨人が接戦を制した",
            "canonical_url": "https://yoshilover.com/post-123/",
            "subtype": "postgame",
            "publish_time_iso": "2026-04-24T21:15:00+09:00",
            "summary": "終盤の継投と一打が勝敗を分けた。",
        }
        payload.update(overrides)
        return sender.PublishNoticeRequest(**payload)

    def test_build_subject_formats_publish_notice_prefix(self):
        self.assertEqual(
            sender.build_subject("巨人が接戦を制した"),
            "[公開通知] Giants 巨人が接戦を制した",
        )

    def test_build_subject_uses_override(self):
        self.assertEqual(
            sender.build_subject("ignored", override="[override] manual subject"),
            "[override] manual subject",
        )

    def test_resolve_recipients_uses_expected_precedence(self):
        cases = [
            (
                {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                None,
                ["notice@example.com"],
            ),
            (
                {"MAIL_BRIDGE_TO": "bridge@example.com, backup@example.com"},
                None,
                ["bridge@example.com", "backup@example.com"],
            ),
            (
                {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
                ["override@example.com, second@example.com"],
                ["override@example.com", "second@example.com"],
            ),
            ({}, None, []),
        ]

        for env_map, override, expected in cases:
            with self.subTest(expected=expected):
                with patch.dict("os.environ", env_map, clear=True):
                    self.assertEqual(sender.resolve_recipients(override), expected)

    def test_build_body_text_includes_manual_x_post_candidates(self):
        body = sender.build_body_text(self._request())

        self.assertEqual(
            body.splitlines(),
            [
                "title: 巨人が接戦を制した",
                "url: https://yoshilover.com/post-123/",
                "subtype: postgame",
                "publish time: 2026-04-24 21:15 JST",
                "summary: 終盤の継投と一打が勝敗を分けた。",
                "manual_x_post_candidates:",
                "article_url: https://yoshilover.com/post-123/",
                "x_post_1_article_intro: 巨人の試合結果を更新しました。巨人が接戦を制した https://yoshilover.com/post-123/",
                "x_post_2_reaction_hook: この試合、巨人ファンはどう見る？ 終盤の継投と一打が勝敗を分けた。 https://yoshilover.com/post-123/",
                "x_post_3_inside_voice: これは試合後にもう一度見たいポイント。巨人が接戦を制した",
            ],
        )

    def test_build_body_text_truncates_summary_over_120_chars(self):
        summary = "あ" * 130
        body = sender.build_body_text(self._request(summary=summary))

        self.assertIn(f"summary: {'あ' * 119}…", body.splitlines())

    def test_build_body_text_uses_none_marker_for_blank_summary(self):
        cases = [None, "", " \n\t "]

        for summary in cases:
            with self.subTest(summary=summary):
                body = sender.build_body_text(self._request(summary=summary))
                self.assertIn("summary: (なし)", body.splitlines())

    def test_manual_x_post_candidates_stay_within_x_limit(self):
        request = self._request(title="巨人" * 80, summary="終盤の継投と一打が勝敗を分けた。" * 20)

        candidates = sender.build_manual_x_post_candidates(request)

        self.assertEqual(
            [label for label, _text in candidates],
            ["x_post_1_article_intro", "x_post_2_reaction_hook", "x_post_3_inside_voice"],
        )
        self.assertTrue(all(len(text) <= sender.MAX_MANUAL_X_POST_LENGTH for _label, text in candidates))

    def test_send_dry_run_default_skips_bridge_call(self):
        request = self._request()
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(request, bridge_send=bridge_send)

        self.assertEqual(result.status, "dry_run")
        self.assertIsNone(result.reason)
        self.assertEqual(result.subject, "[公開通知] Giants 巨人が接戦を制した")
        self.assertEqual(result.recipients, ["notice@example.com"])
        self.assertIsNone(result.bridge_result)
        bridge_send.assert_not_called()

    def test_send_suppresses_empty_title(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(self._request(title="  "), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "EMPTY_TITLE")
        bridge_send.assert_not_called()

    def test_send_suppresses_missing_url(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(self._request(canonical_url=" "), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "MISSING_URL")
        bridge_send.assert_not_called()

    def test_send_suppresses_when_no_recipient_is_available(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            result = sender.send(self._request(), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "NO_RECIPIENT")
        self.assertEqual(result.recipients, [])
        bridge_send.assert_not_called()

    def test_send_suppresses_gate_off_when_send_requested_without_enable_flag(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(self._request(), dry_run=False, send_enabled=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "GATE_OFF")
        bridge_send.assert_not_called()

    def test_send_real_path_calls_bridge_once(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(self._request(), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()
        mail_request = bridge_send.call_args.args[0]
        self.assertEqual(bridge_send.call_args.kwargs, {"dry_run": False})
        self.assertEqual(mail_request.to, ["notice@example.com"])
        self.assertEqual(mail_request.subject, "[公開通知] Giants 巨人が接戦を制した")
        self.assertEqual(
            mail_request.text_body.splitlines(),
            [
                "title: 巨人が接戦を制した",
                "url: https://yoshilover.com/post-123/",
                "subtype: postgame",
                "publish time: 2026-04-24 21:15 JST",
                "summary: 終盤の継投と一打が勝敗を分けた。",
                "manual_x_post_candidates:",
                "article_url: https://yoshilover.com/post-123/",
                "x_post_1_article_intro: 巨人の試合結果を更新しました。巨人が接戦を制した https://yoshilover.com/post-123/",
                "x_post_2_reaction_hook: この試合、巨人ファンはどう見る？ 終盤の継投と一打が勝敗を分けた。 https://yoshilover.com/post-123/",
                "x_post_3_inside_voice: これは試合後にもう一度見たいポイント。巨人が接戦を制した",
            ],
        )
        self.assertEqual(mail_request.metadata["post_id"], 123)
        self.assertEqual(result.bridge_result, bridge_result)

    def test_send_includes_bridge_result_object(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(self._request(), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertIs(result.bridge_result, bridge_result)

    def test_send_uses_recipient_override_over_env(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", "MAIL_BRIDGE_TO": "bridge@example.com"},
            clear=True,
        ):
            result = sender.send(
                self._request(),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                override_recipient=["override@example.com, second@example.com"],
            )

        self.assertEqual(result.recipients, ["override@example.com", "second@example.com"])
        self.assertEqual(bridge_send.call_args.args[0].to, ["override@example.com", "second@example.com"])

    def test_send_uses_subject_override(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(
                self._request(),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                override_subject="[公開通知] Giants override",
            )

        self.assertEqual(result.subject, "[公開通知] Giants override")
        self.assertEqual(bridge_send.call_args.args[0].subject, "[公開通知] Giants override")

    def test_send_wraps_bridge_suppression_reason(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="suppressed",
            refused_recipients={},
            smtp_response=[],
            reason="EMPTY_BODY",
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(self._request(), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "EMPTY_BODY")
        self.assertIs(result.bridge_result, bridge_result)


if __name__ == "__main__":
    unittest.main()
