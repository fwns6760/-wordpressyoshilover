import json
import logging
import smtplib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
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

    def _event_notice_request(self, **overrides):
        payload = {
            "post_id": 63797,
            "title": "隠善智也監督「伝統の一戦」 ベンチの狙いはどこか",
            "canonical_url": "https://yoshilover.com/63797",
            "subtype": "default",
            "publish_time_iso": "2026-04-27T10:05:00+09:00",
            "summary": (
                "📰 報知新聞 / スポーツ報知巨人班X⚾ GIANTS MANAGER NOTE "
                "【巨人】女子チームの「伝統の一戦」を6・27と7・18に開催 "
                "隠善智也監督「見応 【巨人】女子チームの「伝統の一戦」を6・27と7・18に […]"
            ),
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
                "x_post_2_postgame_turning_point: 試合の分岐点を整理。終盤の継投と一打が勝敗を分けた。 https://yoshilover.com/post-123/",
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
            [
                "x_post_1_article_intro",
                "x_post_2_postgame_turning_point",
                "x_post_3_inside_voice",
            ],
        )
        self.assertTrue(all(len(text) <= sender.MAX_MANUAL_X_POST_LENGTH for _label, text in candidates))

    def test_manual_x_post_candidates_vary_by_subtype(self):
        lineup_labels = [
            label for label, _text in sender.build_manual_x_post_candidates(self._request(subtype="lineup"))
        ]
        program_labels = [
            label for label, _text in sender.build_manual_x_post_candidates(self._request(subtype="program"))
        ]
        default_labels = [
            label for label, _text in sender.build_manual_x_post_candidates(self._request(subtype="other"))
        ]

        self.assertIn("x_post_2_lineup_focus", lineup_labels)
        self.assertIn("x_post_2_program_memo", program_labels)
        self.assertIn("x_post_3_inside_voice", lineup_labels)
        self.assertNotEqual(lineup_labels, default_labels)

    def test_manual_x_notice_omits_fan_reaction_hook(self):
        candidates = sender.build_manual_x_post_candidates(self._request(subtype="notice"))

        self.assertEqual(len(candidates), 3)
        self.assertFalse(any("fan_reaction_hook" in label for label, _text in candidates))

    def test_manual_x_sensitive_words_omit_fan_reaction_hook(self):
        candidates = sender.build_manual_x_post_candidates(
            self._request(title="巨人主力が怪我から復帰へ", subtype="postgame")
        )

        self.assertFalse(any("fan_reaction_hook" in label for label, _text in candidates))

    def test_manual_x_candidates_skipped_for_roster_movement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            yellow_log_path.write_text(
                json.dumps(
                    {
                        "post_id": 123,
                        "applied_flags": ["roster_movement_yellow"],
                        "manual_x_post_block_reason": "roster_movement_yellow",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            candidates = sender.build_manual_x_post_candidates(self._request(), yellow_log_path=yellow_log_path)
            body = sender.build_body_text(self._request(), yellow_log_path=yellow_log_path)

        self.assertEqual(candidates, [])
        self.assertIn("warning: [Warning] roster movement 系記事、X 自動投稿対象外", body.splitlines())
        self.assertIn("suppressed: roster_movement_yellow", body.splitlines())
        self.assertFalse(any(line.startswith("x_post_") for line in body.splitlines()))

    def test_manual_x_inside_voice_is_conditional(self):
        farm_labels = [label for label, _text in sender.build_manual_x_post_candidates(self._request(subtype="farm"))]
        default_labels = [
            label for label, _text in sender.build_manual_x_post_candidates(self._request(subtype="default"))
        ]
        notice_labels = [
            label for label, _text in sender.build_manual_x_post_candidates(self._request(subtype="notice"))
        ]

        self.assertTrue(any("inside_voice" in label for label in farm_labels))
        self.assertFalse(any("inside_voice" in label for label in default_labels))
        self.assertFalse(any("inside_voice" in label for label in notice_labels))

    def test_manual_x_post_candidates_limit_url_candidates_to_three(self):
        candidates = sender.build_manual_x_post_candidates(self._request(subtype="program"))

        self.assertLessEqual(
            sum("https://yoshilover.com/post-123/" in text for _label, text in candidates),
            3,
        )

    def test_summary_cleanup_removes_source_header(self):
        cleaned = sender._clean_summary_for_x_candidate(
            "📰 報知新聞 / スポーツ報知巨人班X 巨人が逆転勝ち",
            title="巨人が逆転勝ち",
        )

        self.assertEqual(cleaned, "巨人が逆転勝ち")

    def test_summary_cleanup_removes_emoji_and_label(self):
        cleaned = sender._clean_summary_for_x_candidate(
            "⚾ GIANTS MANAGER NOTE 隠善智也監督が見どころを説明",
            title="隠善智也監督が見どころを説明",
        )

        self.assertEqual(cleaned, "隠善智也監督が見どころを説明")

    def test_summary_cleanup_removes_title_duplicate(self):
        cleaned = sender._clean_summary_for_x_candidate(
            "【巨人】阿部監督が方針説明 今回の狙いを整理 【巨人】阿部監督が方針説明",
            title="【巨人】阿部監督が方針説明",
        )

        self.assertEqual(cleaned, "今回の狙いを整理")

    def test_summary_cleanup_handles_truncation_marker(self):
        cleaned = sender._clean_summary_for_x_candidate(
            "巨人女子チームのイベント情報を更新 […]",
            title="巨人女子チームのイベント情報を更新",
        )

        self.assertEqual(cleaned, "巨人女子チームのイベント情報を更新")

    def test_summary_cleanup_short_falls_back_to_title(self):
        context = sender._manual_x_context(
            self._request(
                subtype="default",
                title="巨人ニュースを整理",
                summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】速報 […]",
            )
        )

        self.assertTrue(context.summary_fallback)
        self.assertEqual(context.hook_source, "巨人ニュースを整理")

    def test_notice_event_subtype_detected_for_event_announcement(self):
        context = sender._manual_x_context(self._event_notice_request())

        self.assertEqual(context.article_type, "notice_event")

    def test_notice_event_no_fan_reaction_hook(self):
        candidates = sender.build_manual_x_post_candidates(self._event_notice_request())

        self.assertEqual(
            [label for label, _text in candidates],
            [
                "x_post_1_article_intro",
                "x_post_2_event_detail",
                "x_post_3_event_inside_voice",
            ],
        )
        self.assertFalse(any("fan_reaction_hook" in label for label, _text in candidates))

    def test_default_subtype_skips_dirty_summary(self):
        candidates = sender.build_manual_x_post_candidates(
            self._request(
                subtype="default",
                title="巨人イベント情報を更新",
                summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】イベント告知 […]",
            )
        )

        candidate_map = dict(candidates)
        self.assertIn("x_post_3_fan_reaction_hook", candidate_map)
        self.assertTrue(candidate_map["x_post_3_fan_reaction_hook"].startswith("巨人ニュースを更新しました。"))
        self.assertNotIn("どう見る？", candidate_map["x_post_3_fan_reaction_hook"])
        self.assertNotIn("📰", candidate_map["x_post_3_fan_reaction_hook"])

    def test_63797_full_candidates_are_copy_ready(self):
        candidates = sender.build_manual_x_post_candidates(self._event_notice_request())

        self.assertEqual(len(candidates), 3)
        self.assertTrue(all(len(text) <= sender.MAX_MANUAL_X_POST_LENGTH for _label, text in candidates))
        self.assertTrue(all("https://yoshilover.com/63797" in text for _label, text in candidates))
        self.assertTrue(all("📰" not in text and "GIANTS MANAGER NOTE" not in text for _label, text in candidates))
        self.assertTrue(all("[…]" not in text and "..." not in text for _label, text in candidates))
        self.assertEqual(
            [text for _label, text in candidates],
            [
                "巨人女子チームの「伝統の一戦」開催情報を更新しました。隠善智也監督のコメントも紹介しています。 https://yoshilover.com/63797",
                "巨人女子チームの注目イベント「伝統の一戦」。開催日程と隠善智也監督のコメントを整理しました。 https://yoshilover.com/63797",
                "6月27日と7月18日に行われる巨人女子チームの「伝統の一戦」。試合前に押さえておきたいポイントです。 https://yoshilover.com/63797",
            ],
        )

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
                "x_post_2_postgame_turning_point: 試合の分岐点を整理。終盤の継投と一打が勝敗を分けた。 https://yoshilover.com/post-123/",
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

    def test_send_result_logged_to_queue_path_sent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = f"{tmpdir}/queue.jsonl"
            result = sender.PublishNoticeEmailResult(
                status="sent",
                reason=None,
                subject="[公開通知] Giants 巨人が接戦を制した",
                recipients=["notice@example.com"],
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=63781,
                result=result,
                publish_time_iso="2026-04-27T09:05:37+09:00",
                recorded_at=datetime.fromisoformat("2026-04-27T11:31:14+09:00"),
            )

            rows = [
                json.loads(line)
                for line in Path(queue_path).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "status": "sent",
                "reason": None,
                "subject": "[公開通知] Giants 巨人が接戦を制した",
                "recipients": ["notice@example.com"],
                "post_id": 63781,
                "recorded_at": "2026-04-27T11:31:14+09:00",
                "sent_at": "2026-04-27T11:31:14+09:00",
                "notice_kind": "per_post",
                "publish_time_iso": "2026-04-27T09:05:37+09:00",
            },
        )

    def test_send_result_logged_to_queue_path_suppressed_no_recipient(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = f"{tmpdir}/queue.jsonl"
            result = sender.PublishNoticeEmailResult(
                status="suppressed",
                reason="NO_RECIPIENT",
                subject="[公開通知] Giants 巨人が接戦を制した",
                recipients=[],
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=63781,
                result=result,
                publish_time_iso="2026-04-27T09:05:37+09:00",
                recorded_at=datetime.fromisoformat("2026-04-27T11:31:14+09:00"),
            )

            row = json.loads(Path(queue_path).read_text(encoding="utf-8").strip())

        self.assertEqual(row["status"], "suppressed")
        self.assertEqual(row["reason"], "NO_RECIPIENT")
        self.assertEqual(row["recipients"], [])
        self.assertEqual(row["notice_kind"], "per_post")
        self.assertEqual(row["publish_time_iso"], "2026-04-27T09:05:37+09:00")

    def test_send_result_logged_to_queue_path_smtp_error(self):
        def raising_bridge(*_args, **_kwargs):
            raise smtplib.SMTPServerDisconnected("lost connection")

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            queue_path = f"{tmpdir}/queue.jsonl"
            result = sender.send(
                self._request(),
                dry_run=False,
                send_enabled=True,
                bridge_send=raising_bridge,
            )
            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=63781,
                result=result,
                publish_time_iso="2026-04-27T09:05:37+09:00",
                recorded_at=datetime.fromisoformat("2026-04-27T11:31:14+09:00"),
            )
            row = json.loads(Path(queue_path).read_text(encoding="utf-8").strip())

        self.assertEqual(result.status, "error")
        self.assertEqual(result.reason, "SMTPServerDisconnected")
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["reason"], "SMTPServerDisconnected")
        self.assertEqual(row["subject"], "[公開通知] Giants 巨人が接戦を制した")

    def test_alert_log_when_emit_gt_zero_sent_zero(self):
        summary = sender.summarize_execution_results(
            [
                sender.PublishNoticeEmailResult(
                    status="suppressed",
                    reason="NO_RECIPIENT",
                    subject="subject-a",
                    recipients=[],
                ),
                sender.PublishNoticeEmailResult(
                    status="error",
                    reason="SMTPServerDisconnected",
                    subject="subject-b",
                    recipients=["notice@example.com"],
                ),
            ],
            emitted=2,
        )

        summary_line = sender.build_execution_summary_log(summary)
        alert_line = sender.build_zero_sent_alert_log(summary)

        self.assertTrue(summary.should_alert)
        self.assertEqual(summary.sent, 0)
        self.assertEqual(summary.suppressed, 1)
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.reasons, {"NO_RECIPIENT": 1, "SMTPServerDisconnected": 1})
        self.assertIn("[summary] sent=0 suppressed=1 errors=1", summary_line)
        self.assertIsNotNone(alert_line)
        self.assertIn("emitted=2 but sent=0", alert_line)
        with self.assertLogs(level="WARNING") as captured:
            logging.warning(alert_line)
        self.assertIn("[ALERT] publish-notice emitted=2 but sent=0", captured.output[0])

    def test_no_alert_when_some_sent(self):
        summary = sender.summarize_execution_results(
            [
                sender.PublishNoticeEmailResult(
                    status="sent",
                    reason=None,
                    subject="subject-a",
                    recipients=["notice@example.com"],
                ),
                sender.PublishNoticeEmailResult(
                    status="suppressed",
                    reason="NO_RECIPIENT",
                    subject="subject-b",
                    recipients=[],
                ),
            ],
            emitted=2,
        )

        self.assertFalse(summary.should_alert)
        self.assertIsNone(sender.build_zero_sent_alert_log(summary))

    def test_no_alert_when_emit_zero(self):
        summary = sender.summarize_execution_results([], emitted=0)

        self.assertFalse(summary.should_alert)
        self.assertIsNone(sender.build_zero_sent_alert_log(summary))


if __name__ == "__main__":
    unittest.main()
