import json
import logging
import os
import re
import smtplib
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import publish_notice_email_sender as sender


class PublishNoticeEmailSenderTests(unittest.TestCase):
    def setUp(self):
        # These tests assert the verbose body / legacy subject shape;
        # opt out of the default-on minimal body and detailed subject.
        self._prev_minimal = os.environ.get(sender._MINIMAL_BODY_ENV)
        self._prev_subject = os.environ.get(sender._SUBJECT_DETAIL_ENV)
        os.environ[sender._MINIMAL_BODY_ENV] = "0"
        os.environ[sender._SUBJECT_DETAIL_ENV] = "0"

    def tearDown(self):
        for key, prev in (
            (sender._MINIMAL_BODY_ENV, self._prev_minimal),
            (sender._SUBJECT_DETAIL_ENV, self._prev_subject),
        ):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev

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

    def _summary_request(self, **overrides):
        payload = {
            "entries": [
                sender.BurstSummaryEntry(
                    post_id=123,
                    title="巨人が接戦を制した",
                    category="試合速報",
                    publishable=True,
                    cleanup_required=False,
                    cleanup_success=True,
                ),
                sender.BurstSummaryEntry(
                    post_id=124,
                    title="巨人の先発が決定",
                    category="選手情報",
                    publishable=True,
                    cleanup_required=False,
                    cleanup_success=True,
                ),
            ],
            "cumulative_published_count": 12,
            "daily_cap": 100,
        }
        payload.update(overrides)
        return sender.BurstSummaryRequest(**payload)

    def _alert_request(self, **overrides):
        payload = {
            "alert_type": "publish_failure",
            "post_id": 123,
            "title": "巨人が接戦を制した",
            "category": "試合速報",
            "reason": "SMTPServerDisconnected",
            "detail": "lost connection",
            "publishable": True,
            "cleanup_required": False,
            "cleanup_success": True,
        }
        payload.update(overrides)
        return sender.AlertMailRequest(**payload)

    def _bridge_result(self):
        return mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )

    def _per_post_metadata_lines(
        self,
        *,
        mail_class="x_candidate",
        action="copy_x_post",
        priority="normal",
        post_id=123,
        subtype="postgame",
        x_post_ready="true",
        reason="manual_x_candidates_clean",
    ):
        return [
            "--- metadata ---",
            "mail_type: per_post",
            f"mail_class: {mail_class}",
            f"action: {action}",
            f"priority: {priority}",
            f"post_id: {post_id}",
            f"subtype: {subtype}",
            f"x_post_ready: {x_post_ready}",
            f"reason: {reason}",
            "---",
        ]

    def test_build_subject_formats_publish_notice_prefix(self):
        self.assertEqual(
            sender.build_subject("巨人が接戦を制した"),
            "【公開済】巨人が接戦を制した | YOSHILOVER",
        )

    def test_build_subject_uses_override(self):
        self.assertEqual(
            sender.build_subject("ignored", override="[override] manual subject"),
            "[override] manual subject",
        )

    def test_subject_prefix_x_candidate(self):
        request = self._request()
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【投稿候補】巨人が接戦を制した | YOSHILOVER",
        )

    def test_subject_prefix_publish(self):
        request = self._request(summary=None)
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "publish")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【公開済】巨人が接戦を制した | YOSHILOVER",
        )

    def test_subject_prefix_draft_notice_does_not_use_publish_label(self):
        request = self._request(summary=None, record_type="draft_notice")
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "draft")
        self.assertEqual(classification["reason"], "draft_notice_default")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【下書き】巨人が接戦を制した | YOSHILOVER",
        )

    def test_send_draft_notice_default_is_labeled_as_draft(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._request(summary=None, record_type="draft_notice")

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
            },
            clear=True,
        ):
            result = sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.subject, "【下書き】巨人が接戦を制した | YOSHILOVER")
        bridge_send.assert_called_once()

    def test_subject_prefix_review_dirty_summary(self):
        request = self._request(
            subtype="default",
            title="巨人イベント情報を更新",
            summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】イベント告知 […]",
        )
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "summary_dirty_review")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】巨人イベント情報を更新 | YOSHILOVER",
        )

    def test_subject_prefix_review_roster_movement_yellow(self):
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
            classification = sender._classify_mail(self._request(), yellow_log_path=yellow_log_path)

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "roster_movement_yellow_x_blocked")
        self.assertEqual(
            sender.build_subject("巨人が接戦を制した", classification=classification),
            "【要確認・X見送り】巨人が接戦を制した | YOSHILOVER",
        )

    def test_subject_prefix_warning_smtp_error(self):
        self.assertEqual(
            sender.build_alert_subject(self._alert_request()),
            "【警告】post_id=123 | YOSHILOVER",
        )

    def test_subject_prefix_summary_batch(self):
        self.assertEqual(
            sender.build_summary_subject(self._summary_request()),
            "【まとめ】直近2件 | YOSHILOVER",
        )

    def test_review_subject_x_block_prefix_sensitive(self):
        request = self._request(
            subtype="postgame",
            summary="主力選手は全治 6 ヶ月の見込みと発表された。",
        )
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "sensitive_content_x_blocked")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認・X見送り】巨人が接戦を制した | YOSHILOVER",
        )

    def test_review_subject_general_prefix_cautious_subtype(self):
        request = self._request(
            post_id=63323,
            subtype="notice",
            title="巨人戦の観戦案内を更新",
            summary="対象試合と受付条件を整理した。",
        )
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "cautious_subtype_review")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】巨人戦の観戦案内を更新 | YOSHILOVER",
        )

    def test_body_metadata_block_format(self):
        body_lines = sender.build_body_text(self._request()).splitlines()

        self.assertEqual(body_lines[0], "次アクション: 内容確認後 X 投稿候補から選んで投稿")
        self.assertEqual(
            body_lines[-10:],
            self._per_post_metadata_lines(),
        )

    def test_classify_mail_publish_default(self):
        classification = sender._classify_mail(self._request(summary=None))

        self.assertEqual(classification["mail_class"], "publish")
        self.assertEqual(classification["action"], "check_article")
        self.assertEqual(classification["priority"], "normal")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(classification["reason"], "publish_notice_default")

    def test_classify_mail_x_candidate_safe(self):
        classification = sender._classify_mail(self._request())

        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(classification["action"], "copy_x_post")
        self.assertEqual(classification["priority"], "normal")
        self.assertEqual(classification["x_post_ready"], "true")
        self.assertEqual(classification["reason"], "manual_x_candidates_clean")

    def test_existing_manual_x_post_candidates_unchanged(self):
        self.assertEqual(
            sender.build_manual_x_post_candidates(self._request()),
            [
                (
                    "x_post_1_article_intro",
                    "巨人の試合結果を更新しました。巨人が接戦を制した https://yoshilover.com/post-123/",
                ),
                (
                    "x_post_2_postgame_turning_point",
                    "試合の分岐点を整理。終盤の継投と一打が勝敗を分けた。 https://yoshilover.com/post-123/",
                ),
                (
                    "x_post_3_inside_voice",
                    "これは試合後にもう一度見たいポイント。巨人が接戦を制した",
                ),
            ],
        )

    def test_subject_long_title_truncation(self):
        long_title = "巨人" * 50
        classification = {"mail_class": "publish"}
        subject = sender.build_subject(long_title, classification=classification)

        self.assertTrue(subject.startswith("【公開済】"))
        self.assertTrue(subject.endswith(" | YOSHILOVER"))
        self.assertIn("… | YOSHILOVER", subject)
        self.assertNotIn(long_title, subject)

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
                {"FACT_CHECK_EMAIL_TO": "fact@example.com"},
                None,
                ["fact@example.com"],
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
        text_1 = "巨人の試合結果を更新しました。巨人が接戦を制した https://yoshilover.com/post-123/"
        text_2 = "試合の分岐点を整理。終盤の継投と一打が勝敗を分けた。 https://yoshilover.com/post-123/"
        text_3 = "これは試合後にもう一度見たいポイント。巨人が接戦を制した"

        self.assertEqual(
            body.splitlines(),
            [
                "次アクション: 内容確認後 X 投稿候補から選んで投稿",
                "title: 巨人が接戦を制した",
                "url: https://yoshilover.com/post-123/",
                "subtype: postgame",
                "publish time: 2026-04-24 21:15 JST",
                "summary: 終盤の継投と一打が勝敗を分けた。",
                "manual_x_post_candidates:",
                "article_url: https://yoshilover.com/post-123/",
                f"投稿文1: {text_1}",
                f"文字数: {len(text_1)}",
                f"Xで開く: {sender._build_x_intent_url(text_1)}",
                f"投稿文2: {text_2}",
                f"文字数: {len(text_2)}",
                f"Xで開く: {sender._build_x_intent_url(text_2)}",
                f"投稿文3: {text_3}",
                f"文字数: {len(text_3)}",
                f"Xで開く: {sender._build_x_intent_url(text_3)}",
                *self._per_post_metadata_lines(),
            ],
        )

    def test_x_candidate_class_still_shows(self):
        body_lines = sender.build_body_text(self._request()).splitlines()

        self.assertIn("投稿文1: 巨人の試合結果を更新しました。巨人が接戦を制した https://yoshilover.com/post-123/", body_lines)
        self.assertIn("manual_x_post_candidates:", body_lines)
        self.assertIn(
            "Xで開く: "
            "https://x.com/intent/post?text=%E5%B7%A8%E4%BA%BA%E3%81%AE%E8%A9%A6%E5%90%88%E7%B5%90%E6%9E%9C%E3%82%92%E6%9B%B4%E6%96%B0%E3%81%97%E3%81%BE%E3%81%97%E3%81%9F%E3%80%82%E5%B7%A8%E4%BA%BA%E3%81%8C%E6%8E%A5%E6%88%A6%E3%82%92%E5%88%B6%E3%81%97%E3%81%9F%20https%3A%2F%2Fyoshilover.com%2Fpost-123%2F",
            body_lines,
        )
        self.assertFalse(any("(コピー用)" in line for line in body_lines))

    def test_63323_review_class_no_candidate_displayed(self):
        request = self._request(
            post_id=63323,
            subtype="notice",
            title="巨人戦の観戦案内を更新",
            summary="対象試合と受付条件を整理した。",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(classification["reason"], "cautious_subtype_review")
        self.assertNotIn("manual_x_post_candidates:", body_lines)
        self.assertFalse(any(line.startswith("article_url: ") for line in body_lines))
        self.assertFalse(any(line.startswith("投稿文") for line in body_lines))

    def test_review_class_shows_alternative_message(self):
        request = self._request(
            post_id=63323,
            subtype="notice",
            title="巨人戦の観戦案内を更新",
            summary="対象試合と受付条件を整理した。",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertIn("[X 投稿候補] 非表示: 本文確認後に必要なら手動で判断してください", body_lines)

    def test_review_class_no_intent_link(self):
        request = self._request(
            post_id=63323,
            subtype="notice",
            title="巨人戦の観戦案内を更新",
            summary="対象試合と受付条件を整理した。",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertFalse(any(line.startswith("Xで開く: ") for line in body_lines))

    def test_review_reason_japanese_label_summary_dirty(self):
        request = self._request(
            subtype="default",
            title="巨人イベント情報を更新",
            summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】イベント告知 […]",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["reason"], "summary_dirty_review")
        self.assertIn("判定: 要確認", body_lines)
        self.assertIn("理由: 要約に元記事断片や重複文が混ざっています(本文確認推奨)", body_lines)

    def test_review_reason_japanese_label_roster_movement(self):
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
            request = self._request()
            classification = sender._classify_mail(request, yellow_log_path=yellow_log_path)
            body_lines = sender.build_body_text(
                request,
                yellow_log_path=yellow_log_path,
                classification=classification,
            ).splitlines()

        self.assertIn("判定: 見送り推奨", body_lines)
        self.assertIn("理由: 登録/抹消/復帰系のため X 投稿候補なし", body_lines)

    def test_review_reason_japanese_label_cautious_subtype(self):
        request = self._request(
            post_id=63323,
            subtype="notice",
            title="巨人戦の観戦案内を更新",
            summary="対象試合と受付条件を整理した。",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertIn("判定: 要確認", body_lines)
        self.assertIn("理由: 公示・注意系の記事です(本文確認推奨)", body_lines)

    def test_review_reason_japanese_label_sensitive(self):
        request = self._request(
            subtype="postgame",
            summary="主力選手は全治 6 ヶ月の見込みと発表された。",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["reason"], "sensitive_content_x_blocked")
        self.assertIn("判定: 見送り", body_lines)
        self.assertIn("理由: センシティブ要素のため X 投稿候補なし", body_lines)

    def test_next_action_line_for_review_x_block(self):
        request = self._request(
            subtype="postgame",
            summary="主力選手は全治 6 ヶ月の見込みと発表された。",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(body_lines[0], "次アクション: 記事だけ確認。X 投稿は見送り")

    def test_next_action_line_for_review_summary_dirty(self):
        request = self._request(
            subtype="default",
            title="巨人イベント情報を更新",
            summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】イベント告知 […]",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(body_lines[0], "次アクション: 後で確認。急ぎ投稿不要")

    def test_next_action_line_for_publish(self):
        request = self._request(summary=None)
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["mail_class"], "publish")
        self.assertEqual(body_lines[0], "次アクション: 問題なければ放置")

    def test_dirty_summary_truncated_to_short_form(self):
        dirty_summary = "📰 報知新聞 / " + ("【巨人】イベント情報を更新 " * 20) + "[…]"
        request = self._request(
            subtype="default",
            title="巨人イベント情報を更新",
            summary=dirty_summary,
        )
        classification = {
            **sender._classify_mail(self._request(summary=None)),
            "mail_class": "review",
            "action": "review_article",
            "priority": "high",
            "reason": "summary_dirty_review",
            "x_post_ready": "false",
        }
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertIn("summary: 要約は確認用に短縮表示(本文 URL を確認してください)", body_lines)
        excerpt_line = next(line for line in body_lines if line.startswith("summary_excerpt: "))
        excerpt = excerpt_line.removeprefix("summary_excerpt: ")
        self.assertLessEqual(len(excerpt), 100)
        self.assertTrue(excerpt.endswith("…"))
        self.assertNotIn(dirty_summary, body_lines)

    def test_x_candidates_hidden_for_review_classes(self):
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
            review_cases = [
                (
                    "summary_dirty_review",
                    self._request(
                        subtype="default",
                        title="巨人イベント情報を更新",
                        summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】イベント告知 […]",
                    ),
                    sender._classify_mail(
                        self._request(
                            subtype="default",
                            title="巨人イベント情報を更新",
                            summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】イベント告知 […]",
                        )
                    ),
                ),
                (
                    "cautious_subtype_review",
                    self._request(
                        post_id=63323,
                        subtype="notice",
                        title="巨人戦の観戦案内を更新",
                        summary="対象試合と受付条件を整理した。",
                    ),
                    sender._classify_mail(
                        self._request(
                            post_id=63323,
                            subtype="notice",
                            title="巨人戦の観戦案内を更新",
                            summary="対象試合と受付条件を整理した。",
                        )
                    ),
                ),
                (
                    "roster_movement_yellow_x_blocked",
                    self._request(),
                    sender._classify_mail(self._request(), yellow_log_path=yellow_log_path),
                ),
                (
                    "sensitive_content_x_blocked",
                    self._request(
                        subtype="postgame",
                        summary="主力選手は全治 6 ヶ月の見込みと発表された。",
                    ),
                    sender._classify_mail(
                        self._request(
                            subtype="postgame",
                            summary="主力選手は全治 6 ヶ月の見込みと発表された。",
                        )
                    ),
                ),
            ]

            for reason, request, classification in review_cases:
                with self.subTest(reason=reason):
                    body_lines = sender.build_body_text(
                        request,
                        yellow_log_path=yellow_log_path,
                        classification=classification,
                    ).splitlines()
                    self.assertNotIn("manual_x_post_candidates:", body_lines)
                    self.assertFalse(any(line.startswith("article_url: ") for line in body_lines))
                    self.assertFalse(any(line.startswith("投稿文") for line in body_lines))
                    self.assertFalse(any(line.startswith("Xで開く: ") for line in body_lines))

    def test_x_candidate_mail_unchanged(self):
        request = self._request()
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(sender.build_subject(request.title, classification=classification), "【投稿候補】巨人が接戦を制した | YOSHILOVER")
        self.assertIn("manual_x_post_candidates:", body_lines)
        self.assertIn("次アクション: 内容確認後 X 投稿候補から選んで投稿", body_lines)
        self.assertEqual(body_lines[-10:], self._per_post_metadata_lines())

    def test_publish_mail_unchanged(self):
        request = self._request(summary=None)
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["mail_class"], "publish")
        self.assertEqual(sender.build_subject(request.title, classification=classification), "【公開済】巨人が接戦を制した | YOSHILOVER")
        self.assertEqual(body_lines[0], "次アクション: 問題なければ放置")
        self.assertNotIn("manual_x_post_candidates:", body_lines)
        self.assertEqual(
            body_lines[-10:],
            self._per_post_metadata_lines(
                mail_class="publish",
                action="check_article",
                priority="normal",
                x_post_ready="false",
                reason="publish_notice_default",
            ),
        )

    def test_metadata_block_keeps_internal_codes(self):
        request = self._request(
            subtype="default",
            title="巨人イベント情報を更新",
            summary="📰 報知新聞 / ⚾ GIANTS TV 【巨人】イベント告知 […]",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(body_lines[-10:], self._per_post_metadata_lines(
            mail_class="review",
            action="review_article",
            priority="high",
            subtype="default",
            x_post_ready="false",
            reason="summary_dirty_review",
        ))

    def test_review_class_still_builds_internal_candidates(self):
        request = self._request(
            post_id=63323,
            subtype="notice",
            title="巨人戦の観戦案内を更新",
            summary="対象試合と受付条件を整理した。",
        )
        body_lines = sender.build_body_text(request).splitlines()

        self.assertTrue(sender.build_manual_x_post_candidates(request))
        self.assertIn("[X 投稿候補] 非表示: 本文確認後に必要なら手動で判断してください", body_lines)
        self.assertFalse(any(line.startswith("投稿文") for line in body_lines))

    def test_warning_class_no_candidate(self):
        request = self._request()
        classification = {
            **sender._classify_mail(request),
            "mail_class": "warning",
            "action": "check_article",
            "priority": "high",
            "reason": "SMTPServerDisconnected",
            "x_post_ready": "false",
        }
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertIn("[X 投稿候補] 非表示: 警告対応を優先してください", body_lines)
        self.assertNotIn("manual_x_post_candidates:", body_lines)
        self.assertFalse(any(line.startswith("投稿文") for line in body_lines))
        self.assertFalse(any(line.startswith("Xで開く: ") for line in body_lines))

    def test_warning_class_hides_article_url_section(self):
        request = self._request()
        classification = {
            **sender._classify_mail(request),
            "mail_class": "warning",
            "action": "check_article",
            "priority": "high",
            "reason": "SMTPServerDisconnected",
            "x_post_ready": "false",
        }
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertFalse(any(line.startswith("article_url: ") for line in body_lines))

    def test_urgent_class_no_candidate(self):
        request = self._request()
        classification = {
            **sender._classify_mail(request),
            "mail_class": "urgent",
            "action": "check_x_now",
            "priority": "urgent",
            "reason": "urgent_keyword_detected",
            "x_post_ready": "false",
        }
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertIn("[X 投稿候補] 非表示: 緊急確認を優先してください", body_lines)
        self.assertNotIn("manual_x_post_candidates:", body_lines)
        self.assertFalse(any(line.startswith("投稿文") for line in body_lines))
        self.assertFalse(any(line.startswith("Xで開く: ") for line in body_lines))

    def test_urgent_class_hides_article_url_section(self):
        request = self._request()
        classification = {
            **sender._classify_mail(request),
            "mail_class": "urgent",
            "action": "check_x_now",
            "priority": "urgent",
            "reason": "urgent_keyword_detected",
            "x_post_ready": "false",
        }
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertFalse(any(line.startswith("article_url: ") for line in body_lines))

    def test_x_post_not_ready_override_shows_alternative_message(self):
        request = self._request()
        classification = {
            **sender._classify_mail(request),
            "x_post_ready": "false",
        }
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertIn("[X 投稿候補] 非表示: X 投稿候補を表示できません", body_lines)
        self.assertNotIn("manual_x_post_candidates:", body_lines)
        self.assertFalse(any(line.startswith("Xで開く: ") for line in body_lines))

    def test_publish_class_default_no_candidate(self):
        request = self._request(summary=None)
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["mail_class"], "publish")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertNotIn("manual_x_post_candidates:", body_lines)
        self.assertFalse(any(line.startswith("投稿文") for line in body_lines))
        self.assertFalse(any(line.startswith("Xで開く: ") for line in body_lines))
        self.assertFalse(any(line.startswith("[X 投稿候補] ") for line in body_lines))

    def test_intent_url_encoding_japanese(self):
        text = "巨人が勝利しました https://yoshilover.com/post-123/"

        self.assertEqual(
            sender._build_x_intent_url(text),
            f"https://x.com/intent/post?text={quote(text, safe='')}",
        )

    def test_intent_url_encoding_special_chars(self):
        text = "#巨人 #ジャイアンツ https://yoshilover.com/post-123/"
        intent_url = sender._build_x_intent_url(text)

        self.assertEqual(intent_url, f"https://x.com/intent/post?text={quote(text, safe='')}")
        self.assertIn("%23%E5%B7%A8%E4%BA%BA", intent_url)
        self.assertIn("%23%E3%82%B8%E3%83%A3%E3%82%A4%E3%82%A2%E3%83%B3%E3%83%84", intent_url)

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

    def test_farm_result_clean_candidates_use_narrow_templates(self):
        request = self._request(
            subtype="farm_result",
            title="巨人二軍 4-2 楽天 試合結果",
            publish_time_iso="2026-04-28T11:00:00+09:00",
            summary="巨人二軍が楽天に4-2で勝利した。浅野翔吾が2安打1打点、先発の山崎伊織は5回1失点だった。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 12, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        labels = [label for label, _text in sender.build_manual_x_post_candidates(request)]
        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(labels, ["x_post_1_article_intro", "x_post_2_farm_watch", "x_post_3_inside_voice"])
        self.assertFalse(any("fan_reaction_hook" in label for label in labels))

    def test_farm_result_dirty_forces_review_subject_prefix(self):
        request = self._request(
            subtype="farm_result",
            title="巨人二軍 楽天戦 試合結果",
            publish_time_iso="2026-04-28T11:00:00+09:00",
            summary="巨人二軍が楽天戦の結果を更新した。スポーツ報知が伝えた。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 12, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "farm_result_review")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】巨人二軍 楽天戦 試合結果 | YOSHILOVER",
        )

    def test_farm_lineup_clean_candidates_use_narrow_templates(self):
        request = self._request(
            subtype="farm_lineup",
            title="【二軍】巨人 vs DeNA 18:00試合開始 1番浅野、4番ティマでスタメン",
            publish_time_iso="2026-04-28T15:00:00+09:00",
            summary="巨人二軍がDeNA戦のスタメンを発表した。1番浅野翔吾、4番ティマ、先発は西舘勇陽投手。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 12, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        labels = [label for label, _text in sender.build_manual_x_post_candidates(request)]
        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(labels, ["x_post_1_article_intro", "x_post_2_farm_watch"])
        self.assertFalse(any("inside_voice" in label for label in labels))
        self.assertFalse(any("fan_reaction_hook" in label for label in labels))

    def test_farm_lineup_stale_forces_review_and_x_post_off(self):
        request = self._request(
            subtype="farm_lineup",
            title="【二軍】巨人 vs DeNA 18:00試合開始 1番浅野、4番ティマでスタメン",
            publish_time_iso="2026-04-27T18:00:00+09:00",
            summary="巨人二軍がDeNA戦のスタメンを発表した。1番浅野翔吾、4番ティマ、先発は西舘勇陽投手。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 12, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        body_lines = sender.build_body_text(request, classification=classification).splitlines()
        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "farm_lineup_review")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】【二軍】巨人 vs DeNA 18:00試合開始 1番浅野、4番ティマでスタメン | YOSHILOVER",
        )
        self.assertIn("[X 投稿候補] 非表示: 本文確認後に必要なら手動で判断してください", body_lines)

    def test_first_team_postgame_clean_uses_x_candidate(self):
        request = self._request(
            subtype="postgame",
            title="巨人 vs 阪神 3-2 戸郷が好投",
            publish_time_iso="2026-04-28T21:15:00+09:00",
            summary="戸郷が7回1失点、岡本が決勝打。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 22, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        labels = [label for label, _text in sender.build_manual_x_post_candidates(request)]
        self.assertTrue(sender._is_first_team_article(request.title, request.summary or "", request.subtype))
        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(classification["reason"], "manual_x_candidates_clean")
        self.assertEqual(
            labels,
            [
                "x_post_1_article_intro",
                "x_post_2_postgame_turning_point",
                "x_post_3_inside_voice",
            ],
        )
        self.assertIn("fan_reaction_hook", sender._manual_x_template_sequence("postgame", sensitive=False))

    def test_first_team_postgame_dirty_forces_review(self):
        request = self._request(
            subtype="postgame",
            title="巨人試合結果",
            publish_time_iso="2026-04-28T21:15:00+09:00",
            summary="試合結果のお知らせ。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 22, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        self.assertTrue(sender._is_first_team_article(request.title, request.summary or "", request.subtype))
        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "first_team_postgame_review")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】巨人試合結果 | YOSHILOVER",
        )

    def test_first_team_lineup_clean_uses_x_candidate(self):
        request = self._request(
            subtype="lineup",
            title="巨人スタメン発表 1番丸佳浩 先発は戸郷翔征",
            publish_time_iso="2026-04-28T17:45:00+09:00",
            summary="巨人スタメン発表。1番丸佳浩、2番吉川尚輝、先発は戸郷翔征。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 12, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        labels = [label for label, _text in sender.build_manual_x_post_candidates(request)]
        self.assertTrue(sender._is_first_team_article(request.title, request.summary or "", request.subtype))
        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(classification["reason"], "manual_x_candidates_clean")
        self.assertIn("x_post_2_lineup_focus", labels)

    def test_first_team_lineup_stale_forces_review_and_x_off(self):
        request = self._request(
            subtype="lineup",
            title="巨人スタメン発表 1番丸佳浩 先発は戸郷翔征",
            publish_time_iso="2026-04-27T17:45:00+09:00",
            summary="巨人スタメン発表。1番丸佳浩、2番吉川尚輝、先発は戸郷翔征。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 12, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        self.assertTrue(sender._is_first_team_article(request.title, request.summary or "", request.subtype))
        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "first_team_lineup_review")
        self.assertEqual(classification["x_post_ready"], "false")

    def test_program_notice_helper_hits_for_giants_tv_subject(self):
        request = self._request(
            subtype="program",
            title="GIANTS TV『直前トーク』を4月29日20:00配信",
            summary="阿部慎之助監督が出演予定。",
        )

        self.assertTrue(sender._is_program_notice(request.title, request.summary or "", request.subtype))

    def test_program_notice_review_forces_x_post_off(self):
        request = self._request(
            subtype="program",
            title="GIANTS TV出演情報",
            summary="坂本勇人が出演予定。",
        )
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "program_notice_review")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】GIANTS TV出演情報 | YOSHILOVER",
        )

    def test_roster_notice_helper_hits_for_registration(self):
        request = self._request(
            subtype="notice",
            title="【巨人】浅野翔吾が出場選手登録",
            summary="一軍に合流した。",
        )

        self.assertTrue(sender._is_roster_notice(request.title, request.summary or "", request.subtype))

    def test_roster_notice_review_forces_x_post_off(self):
        request = self._request(
            subtype="notice",
            title="【巨人】浅野翔吾が出場選手登録",
            summary="一軍に合流した。",
        )
        classification = sender._classify_mail(request)

        self.assertTrue(sender._is_roster_notice(request.title, request.summary or "", request.subtype))
        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】【巨人】浅野翔吾が出場選手登録 | YOSHILOVER",
        )

    def test_injury_recovery_notice_helper_hits_for_kega_marker(self):
        request = self._request(
            subtype="notice",
            title="【巨人】赤星優志が右肩離脱",
            summary="別メニュー調整となった。",
        )

        self.assertTrue(sender._is_injury_recovery_notice(request.title, request.summary or "", request.subtype))

    def test_injury_recovery_notice_review_forces_x_post_off(self):
        request = self._request(
            subtype="notice",
            title="【巨人】赤星優志が右肩離脱",
            summary="状態を見ながら調整する。",
        )
        context = sender._manual_x_context(request)
        with patch.object(sender, "_CAUTIOUS_REVIEW_ARTICLE_TYPES", frozenset()):
            classification = sender._classify_mail(request)

        self.assertEqual(
            sender._injury_recovery_notice_review_reason(request, context),
            "injury_recovery_notice_review",
        )
        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "injury_recovery_notice_review")
        self.assertEqual(classification["x_post_ready"], "false")

    def test_default_review_helper_hits_for_unknown_subtype(self):
        self.assertTrue(sender._is_default_review("default"))
        self.assertTrue(sender._is_default_review(""))

    def test_default_review_forces_x_post_off(self):
        request = self._request(
            subtype="default",
            title="巨人イベント情報を更新",
            summary=None,
        )
        classification = sender._classify_mail(request)

        self.assertEqual(classification["mail_class"], "review")
        self.assertEqual(classification["reason"], "default_review")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【要確認】巨人イベント情報を更新 | YOSHILOVER",
        )

    def test_clean_injury_with_full_diagnosis_keeps_x_candidate(self):
        request = self._request(
            subtype="notice",
            title="【巨人】赤星優志が右肩離脱",
            summary="右肩の張りと診断され、復帰時期は5月上旬を見込む。",
        )
        context = sender._manual_x_context(request)
        with patch.object(
            sender,
            "_SAFE_X_CANDIDATE_ARTICLE_TYPES",
            sender._SAFE_X_CANDIDATE_ARTICLE_TYPES | frozenset({"notice"}),
        ), patch.object(sender, "_CAUTIOUS_REVIEW_ARTICLE_TYPES", frozenset()), patch.object(
            sender, "_manual_x_has_sensitive_word", return_value=False
        ):
            classification = sender._classify_mail(request)

        self.assertIsNone(sender._injury_recovery_notice_review_reason(request, context))
        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(classification["reason"], "manual_x_candidates_clean")
        self.assertEqual(classification["x_post_ready"], "true")

    def test_clean_program_with_full_metadata_keeps_x_candidate(self):
        request = self._request(
            subtype="program",
            title="GIANTS TV『直前トーク』を4月29日20:00配信",
            summary="GIANTS TVで4月29日20:00から配信。阿部慎之助監督が出演し見どころを語る。",
        )
        classification = sender._classify_mail(request)

        labels = [label for label, _text in sender.build_manual_x_post_candidates(request)]
        self.assertTrue(sender._is_program_notice(request.title, request.summary or "", request.subtype))
        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(classification["reason"], "manual_x_candidates_clean")
        self.assertEqual(classification["x_post_ready"], "true")
        self.assertIn("x_post_2_program_memo", labels)
        self.assertEqual(
            sender.build_subject(request.title, classification=classification),
            "【投稿候補】GIANTS TV『直前トーク』を4月29日20:00配信 | YOSHILOVER",
        )

    def test_farm_postgame_path_unchanged_by_first_team_helper(self):
        request = self._request(
            subtype="postgame",
            title="巨人二軍 4-2 楽天",
            publish_time_iso="2026-04-28T15:00:00+09:00",
            summary="浅野翔吾が決勝打を放ち、先発は5回1失点だった。",
        )
        with patch.object(sender, "_coerce_now", return_value=datetime(2026, 4, 28, 18, 0, tzinfo=sender.JST)):
            classification = sender._classify_mail(request)

        labels = [label for label, _text in sender.build_manual_x_post_candidates(request)]
        self.assertFalse(sender._is_first_team_article(request.title, request.summary or "", request.subtype))
        self.assertEqual(classification["mail_class"], "x_candidate")
        self.assertEqual(classification["reason"], "manual_x_candidates_clean")
        self.assertEqual(
            labels,
            [
                "x_post_1_article_intro",
                "x_post_2_postgame_turning_point",
                "x_post_3_inside_voice",
            ],
        )

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
        self.assertIn("[X 投稿候補] 非表示: X 投稿は見送りです", body.splitlines())
        self.assertNotIn("manual_x_post_candidates:", body.splitlines())
        self.assertFalse(any(line.startswith("投稿文") for line in body.splitlines()))
        self.assertFalse(any(line.startswith("Xで開く: ") for line in body.splitlines()))

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

    def test_polish_normalizes_consecutive_spaces(self):
        self.assertEqual(sender._polish_x_post_text("巨人  勝利"), "巨人 勝利")

    def test_polish_normalizes_full_width_space(self):
        self.assertEqual(sender._polish_x_post_text("巨人　勝利"), "巨人 勝利")

    def test_polish_limits_repeated_punctuation(self):
        self.assertEqual(sender._polish_x_post_text("巨人勝利!!! すごい……"), "巨人勝利! すごい…")

    def test_polish_dedupes_hashtags(self):
        self.assertEqual(
            sender._polish_x_post_text("巨人勝利 #巨人 #ジャイアンツ #巨人"),
            "巨人勝利 #巨人 #ジャイアンツ",
        )

    def test_polish_orders_hashtags_standard(self):
        self.assertEqual(
            sender._polish_x_post_text("巨人勝利 #ジャイアンツ #巨人"),
            "巨人勝利 #巨人 #ジャイアンツ",
        )

    def test_polish_url_trailing_whitespace_removed(self):
        self.assertEqual(
            sender._polish_x_post_text("巨人勝利。https://yoshilover.com/post-123/ \n"),
            "巨人勝利。 https://yoshilover.com/post-123/",
        )

    def test_truncation_at_punctuation(self):
        text = ("あ" * 265) + "。 " + ("い" * 30)
        trimmed = sender._trim_manual_x_post_text(text)

        self.assertLessEqual(len(trimmed), sender.MAX_MANUAL_X_POST_LENGTH)
        self.assertTrue(trimmed.endswith("。…"))
        self.assertNotIn("い", trimmed)

    def test_sensitive_keyword_blocks_x_candidates(self):
        request = self._request(
            subtype="default",
            summary="球団OBの死去を受けてコメントを更新した。",
        )
        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(sender.build_manual_x_post_candidates(request), [])
        self.assertEqual(classification["mail_class"], "urgent")
        self.assertEqual(classification["reason"], "sensitive_content_x_blocked")
        self.assertEqual(classification["suppression_reason"], "sensitive_content_x_blocked")
        self.assertIn("[X 投稿候補] 非表示: 緊急確認を優先してください", body_lines)
        self.assertFalse(any(line.startswith("投稿文1") for line in body_lines))

    def test_sensitive_injury_long_term_blocks(self):
        request = self._request(
            subtype="postgame",
            summary="主力選手は全治 6 ヶ月の見込みと発表された。",
        )
        classification = sender._classify_mail(request)

        self.assertEqual(sender.build_manual_x_post_candidates(request), [])
        self.assertEqual(classification["reason"], "sensitive_content_x_blocked")
        self.assertEqual(classification["suppression_reason"], "sensitive_content_x_blocked")

    def test_existing_218_cleanup_preserved(self):
        cleaned = sender._clean_summary_for_x_candidate(
            "📰 報知新聞 / スポーツ報知巨人班X 巨人が逆転勝ち",
            title="巨人が逆転勝ち",
        )

        self.assertEqual(cleaned, "巨人が逆転勝ち")

    def test_existing_222_intent_url_preserved(self):
        text = "巨人の試合結果を更新しました。巨人が接戦を制した https://yoshilover.com/post-123/"

        self.assertEqual(
            sender._build_x_intent_url(text),
            "https://x.com/intent/post?text="
            "%E5%B7%A8%E4%BA%BA%E3%81%AE%E8%A9%A6%E5%90%88%E7%B5%90%E6%9E%9C%E3%82%92%E6%9B%B4%E6%96%B0"
            "%E3%81%97%E3%81%BE%E3%81%97%E3%81%9F%E3%80%82%E5%B7%A8%E4%BA%BA%E3%81%8C%E6%8E%A5%E6%88%A6"
            "%E3%82%92%E5%88%B6%E3%81%97%E3%81%9F%20https%3A%2F%2Fyoshilover.com%2Fpost-123%2F",
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

    def test_280_char_limit_unchanged(self):
        request = self._request(title="巨人" * 80, summary="終盤の継投と一打が勝敗を分けた。" * 20)
        candidates = sender.build_manual_x_post_candidates(request)

        self.assertTrue(all(len(text) <= sender.MAX_MANUAL_X_POST_LENGTH for _label, text in candidates))

    def test_send_dry_run_default_skips_bridge_call(self):
        request = self._request()
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
            result = sender.send(request, bridge_send=bridge_send)

        self.assertEqual(result.status, "dry_run")
        self.assertIsNone(result.reason)
        self.assertEqual(result.subject, "【投稿候補】巨人が接戦を制した | YOSHILOVER")
        self.assertEqual(result.recipients, ["notice@example.com"])
        self.assertIsNone(result.bridge_result)
        bridge_send.assert_not_called()

    def test_send_suppresses_empty_title(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
            result = sender.send(self._request(title="  "), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "EMPTY_TITLE")
        bridge_send.assert_not_called()

    def test_send_suppresses_missing_url(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
            result = sender.send(self._request(canonical_url=" "), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "MISSING_URL")
        bridge_send.assert_not_called()

    def test_send_suppresses_when_no_recipient_is_available(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
            result = sender.send(self._request(), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "NO_RECIPIENT")
        self.assertEqual(result.recipients, [])
        bridge_send.assert_not_called()

    def test_send_suppresses_gate_off_when_send_requested_without_enable_flag(self):
        bridge_send = MagicMock()

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
            result = sender.send(self._request(), dry_run=False, send_enabled=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "GATE_OFF")
        bridge_send.assert_not_called()

    def test_send_publish_only_filter_direct_publish_review_subject_suppresses_with_bypass_flag_off(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._request(
            title="巨人戦の観戦案内を更新",
            subtype="notice",
            summary="対象試合と受付条件を整理した。",
            notice_origin="direct_publish_scan",
        )

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
                "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                "ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS": "0",
            },
            clear=True,
        ):
            result = sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
        self.assertEqual(result.subject, "【要確認】巨人戦の観戦案内を更新 | YOSHILOVER")
        bridge_send.assert_not_called()

    def test_send_publish_only_filter_direct_publish_review_subject_bypasses_with_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._request(
            title="巨人戦の観戦案内を更新",
            subtype="notice",
            summary="対象試合と受付条件を整理した。",
            notice_origin="direct_publish_scan",
        )

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
                "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                "ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS": "1",
            },
            clear=True,
        ):
            result = sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.subject, "【要確認】巨人戦の観戦案内を更新 | YOSHILOVER")
        bridge_send.assert_called_once()

    def test_send_publish_only_filter_direct_publish_publish_subject_is_sent_with_or_without_bypass(self):
        request = self._request(summary=None, notice_origin="direct_publish_scan")

        for bypass_flag in ("0", "1"):
            with self.subTest(bypass_flag=bypass_flag):
                bridge_send = MagicMock(return_value=self._bridge_result())

                with patch.dict(
                    "os.environ",
                    {
                        "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                        sender._MINIMAL_BODY_ENV: "0",
                        sender._SUBJECT_DETAIL_ENV: "0",
                        "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                        "ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS": bypass_flag,
                    },
                    clear=True,
                ):
                    result = sender.send(
                        request,
                        dry_run=False,
                        send_enabled=True,
                        bridge_send=bridge_send,
                    )

                self.assertEqual(result.status, "sent")
                self.assertEqual(result.subject, "【公開済】巨人が接戦を制した | YOSHILOVER")
                bridge_send.assert_called_once()

    def test_send_publish_only_filter_non_direct_review_paths_remain_suppressed_with_bypass_flag_on(self):
        cases = [
            (
                "guarded_review",
                self._request(
                    title="レビュー待ち記事",
                    summary=None,
                    notice_kind="review_hold",
                    notice_origin="guarded_publish_history",
                    subject_override="【要review】レビュー待ち記事 | YOSHILOVER",
                ),
                "【要review】レビュー待ち記事 | YOSHILOVER",
            ),
            (
                "post_gen_validate",
                self._request(
                    title="post gen validate skip",
                    summary=None,
                    notice_kind="post_gen_validate",
                    notice_origin="post_gen_validate_history",
                    subject_override="【要review｜post_gen_validate】post gen validate skip | YOSHILOVER",
                ),
                "【要review｜post_gen_validate】post gen validate skip | YOSHILOVER",
            ),
            (
                "old_candidate",
                self._request(
                    title="古い候補記事",
                    summary=None,
                    notice_kind="review_hold",
                    notice_origin="direct_publish_scan",
                    subject_override="【要確認(古い候補)】古い候補記事 | YOSHILOVER",
                ),
                "【要確認(古い候補)】古い候補記事 | YOSHILOVER",
            ),
        ]

        for label, request, expected_subject in cases:
            with self.subTest(case=label):
                bridge_send = MagicMock(return_value=self._bridge_result())

                with patch.dict(
                    "os.environ",
                    {
                        "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                        sender._MINIMAL_BODY_ENV: "0",
                        sender._SUBJECT_DETAIL_ENV: "0",
                        "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                        "ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS": "1",
                    },
                    clear=True,
                ):
                    result = sender.send(
                        request,
                        dry_run=False,
                        send_enabled=True,
                        bridge_send=bridge_send,
                    )

                self.assertEqual(result.status, "suppressed")
                self.assertEqual(result.reason, "PUBLISH_ONLY_FILTER")
                self.assertEqual(result.subject, expected_subject)
                bridge_send.assert_not_called()

    def test_send_backlog_direct_publish_bypasses_with_backlog_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._request(
            summary=None,
            notice_origin="direct_publish_scan",
            is_backlog=True,
        )

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
                "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "1",
            },
            clear=True,
        ):
            result = sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.subject, "【公開済】巨人が接戦を制した | YOSHILOVER")
        bridge_send.assert_called_once()

    def test_send_backlog_direct_review_bypasses_with_backlog_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._request(
            title="巨人戦の観戦案内を更新",
            subtype="notice",
            summary="対象試合と受付条件を整理した。",
            notice_origin="direct_publish_scan",
            is_backlog=True,
        )

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
                "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                "ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS": "1",
                "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "1",
            },
            clear=True,
        ):
            result = sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.subject, "【要確認】巨人戦の観戦案内を更新 | YOSHILOVER")
        bridge_send.assert_called_once()

    def test_send_backlog_direct_publish_budget_summary_only_stays_suppressed_with_backlog_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._request(
            summary=None,
            notice_origin="direct_publish_scan",
            record_type="24h_budget_summary_only",
            is_backlog=True,
        )

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                    sender._SUBJECT_DETAIL_ENV: "0",
                    "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "1",
            },
            clear=True,
        ):
            result = sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "BACKLOG_SUMMARY_ONLY")
        bridge_send.assert_not_called()

    def test_send_backlog_non_direct_publish_stays_suppressed_with_backlog_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        request = self._request(
            summary=None,
            notice_origin="guarded_publish_history",
            is_backlog=True,
        )

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                    sender._SUBJECT_DETAIL_ENV: "0",
                    "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "1",
            },
            clear=True,
        ):
            result = sender.send(request, dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "BACKLOG_SUMMARY_ONLY")
        bridge_send.assert_not_called()

    def test_send_backlog_bypass_flag_off_keeps_existing_behavior(self):
        cases = [
            (
                "direct_publish",
                self._request(
                    summary=None,
                    notice_origin="direct_publish_scan",
                    is_backlog=True,
                ),
                {
                    "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                    sender._MINIMAL_BODY_ENV: "0",
                    sender._SUBJECT_DETAIL_ENV: "0",
                    "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "0",
                },
                "BACKLOG_SUMMARY_ONLY",
                "【公開済】巨人が接戦を制した | YOSHILOVER",
            ),
            (
                "direct_review",
                self._request(
                    title="巨人戦の観戦案内を更新",
                    subtype="notice",
                    summary="対象試合と受付条件を整理した。",
                    notice_origin="direct_publish_scan",
                    is_backlog=True,
                ),
                {
                    "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                    sender._MINIMAL_BODY_ENV: "0",
                    sender._SUBJECT_DETAIL_ENV: "0",
                    "ENABLE_PUBLISH_ONLY_MAIL_FILTER": "1",
                    "ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS": "1",
                    "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "0",
                },
                "BACKLOG_SUMMARY_ONLY",
                "【要確認】巨人戦の観戦案内を更新 | YOSHILOVER",
            ),
            (
                "budget_summary_only",
                self._request(
                    summary=None,
                    notice_origin="direct_publish_scan",
                    record_type="24h_budget_summary_only",
                    is_backlog=True,
                ),
                {
                    "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                    sender._MINIMAL_BODY_ENV: "0",
                    sender._SUBJECT_DETAIL_ENV: "0",
                    "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "0",
                },
                "BACKLOG_SUMMARY_ONLY",
                "【公開済】巨人が接戦を制した | YOSHILOVER",
            ),
            (
                "non_direct_publish",
                self._request(
                    summary=None,
                    notice_origin="guarded_publish_history",
                    is_backlog=True,
                ),
                {
                    "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                    sender._MINIMAL_BODY_ENV: "0",
                    sender._SUBJECT_DETAIL_ENV: "0",
                    "ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS": "0",
                },
                "BACKLOG_SUMMARY_ONLY",
                "【公開済】巨人が接戦を制した | YOSHILOVER",
            ),
        ]

        for label, request, env_map, expected_reason, expected_subject in cases:
            with self.subTest(case=label):
                bridge_send = MagicMock(return_value=self._bridge_result())

                with patch.dict("os.environ", env_map, clear=True):
                    result = sender.send(
                        request,
                        dry_run=False,
                        send_enabled=True,
                        bridge_send=bridge_send,
                    )

                self.assertEqual(result.status, "suppressed")
                self.assertEqual(result.reason, expected_reason)
                self.assertEqual(result.subject, expected_subject)
                bridge_send.assert_not_called()

    def test_backlog_post_skips_per_post_mail(self):
        bridge_send = MagicMock(return_value=self._bridge_result())

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 123,
                        "ts": "2026-04-24T21:15:10+09:00",
                        "status": "sent",
                        "judgment": "green",
                        "is_backlog": True,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                guarded_publish_history_path=history_path,
            )

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "BACKLOG_SUMMARY_ONLY")
        bridge_send.assert_not_called()

    def test_fresh_post_sends_per_post_mail(self):
        bridge_send = MagicMock(return_value=self._bridge_result())

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 123,
                        "ts": "2026-04-24T21:15:10+09:00",
                        "status": "sent",
                        "judgment": "green",
                        "is_backlog": False,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                guarded_publish_history_path=history_path,
            )

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()

    def test_burst_over_10_forces_summary_mode(self):
        bridge_send = MagicMock(return_value=self._bridge_result())

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            recorded_at = "2026-04-27T11:31:14+09:00"
            queue_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "status": "queued",
                            "reason": None,
                            "subject": f"queued-{index}",
                            "recipients": [],
                            "post_id": 8000 + index,
                            "recorded_at": recorded_at,
                        },
                        ensure_ascii=False,
                    )
                    for index in range(11)
                )
                + "\n",
                encoding="utf-8",
            )
            history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path.write_text("", encoding="utf-8")
            result = sender.send(
                self._request(),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
                guarded_publish_history_path=history_path,
            )

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "BURST_SUMMARY_ONLY")
        bridge_send.assert_not_called()

    def test_summary_mail_aggregates_backlog(self):
        bridge_send = MagicMock(return_value=self._bridge_result())

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "post_id": 9100 + index,
                            "ts": "2026-04-27T09:05:37+09:00",
                            "status": "sent",
                            "judgment": "green",
                            "is_backlog": True,
                        },
                        ensure_ascii=False,
                    )
                    for index in range(3)
                )
                + "\n",
                encoding="utf-8",
            )
            summary_requests = sender.build_burst_summary_requests(
                [
                    sender.BurstSummaryEntry(
                        post_id=9100 + index,
                        title=f"backlog-{index}",
                        category="試合速報",
                        publishable=True,
                        cleanup_required=False,
                        cleanup_success=True,
                    )
                    for index in range(3)
                ],
                guarded_publish_history_path=history_path,
            )
            result = sender.send_summary(
                summary_requests[0],
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
            )

        self.assertEqual(len(summary_requests), 1)
        self.assertEqual(summary_requests[0].summary_mode, "backlog_only")
        self.assertEqual([entry.post_id for entry in summary_requests[0].entries], [9100, 9101, 9102])
        self.assertEqual(result.status, "sent")
        self.assertEqual(bridge_send.call_args.args[0].subject, "【まとめ】直近3件 | YOSHILOVER")
        self.assertIn("summary_posts: 3", bridge_send.call_args.args[0].text_body)

    def test_send_replay_window_recent_sent_suppresses_when_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 5, 4, 6, 45, 29, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                "ENABLE_REPLAY_WINDOW_DEDUP": "1",
                "PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES": "10",
            },
            clear=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "reason": None,
                        "subject": "【公開済】巨人が接戦を制した | YOSHILOVER",
                        "recipients": ["notice@example.com"],
                        "post_id": 123,
                        "recorded_at": (now - timedelta(minutes=5)).isoformat(),
                        "sent_at": (now - timedelta(minutes=5)).isoformat(),
                        "notice_kind": "per_post",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(notice_origin="manual_replay"),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
                now=now,
                duplicate_window=timedelta(minutes=1),
            )

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "DUPLICATE_WITHIN_REPLAY_WINDOW")
        bridge_send.assert_not_called()

    def test_send_replay_window_outside_window_allows_send_when_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 5, 4, 6, 45, 29, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                "ENABLE_REPLAY_WINDOW_DEDUP": "1",
                "PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES": "10",
            },
            clear=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "reason": None,
                        "subject": "【公開済】巨人が接戦を制した | YOSHILOVER",
                        "recipients": ["notice@example.com"],
                        "post_id": 123,
                        "recorded_at": (now - timedelta(minutes=11)).isoformat(),
                        "sent_at": (now - timedelta(minutes=11)).isoformat(),
                        "notice_kind": "per_post",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(notice_origin="manual_replay"),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
                now=now,
                duplicate_window=timedelta(minutes=1),
            )

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()

    def test_send_replay_window_different_post_id_does_not_affect_send_when_flag_on(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 5, 4, 6, 45, 29, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                "ENABLE_REPLAY_WINDOW_DEDUP": "1",
                "PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES": "10",
            },
            clear=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "reason": None,
                        "subject": "【公開済】別記事 | YOSHILOVER",
                        "recipients": ["notice@example.com"],
                        "post_id": 64416,
                        "recorded_at": (now - timedelta(minutes=3)).isoformat(),
                        "sent_at": (now - timedelta(minutes=3)).isoformat(),
                        "notice_kind": "per_post",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(post_id=64366, notice_origin="manual_replay"),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
                now=now,
                duplicate_window=timedelta(minutes=1),
            )

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()

    def test_send_replay_window_64416_like_manual_scheduler_overlap_fixture(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 5, 4, 6, 45, 29, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                "ENABLE_REPLAY_WINDOW_DEDUP": "1",
                "PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES": "10",
            },
            clear=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text("", encoding="utf-8")
            history_path = Path(tmpdir) / "history.json"
            history_path.write_text(
                json.dumps(
                    {
                        "64416": (now - timedelta(minutes=4)).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(
                    post_id=64416,
                    canonical_url="https://yoshilover.com/64416",
                    notice_origin="manual_replay",
                    subject_override="【公開済】巨人・育成選手が支配下登録 | YOSHILOVER",
                ),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
                now=now,
                duplicate_window=timedelta(minutes=1),
            )

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "DUPLICATE_WITHIN_REPLAY_WINDOW")
        bridge_send.assert_not_called()

    def test_send_replay_window_flag_off_keeps_existing_duplicate_reason(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 5, 4, 6, 45, 29, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "reason": None,
                        "subject": "【公開済】巨人が接戦を制した | YOSHILOVER",
                        "recipients": ["notice@example.com"],
                        "post_id": 123,
                        "recorded_at": (now - timedelta(minutes=5)).isoformat(),
                        "sent_at": (now - timedelta(minutes=5)).isoformat(),
                        "notice_kind": "per_post",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(notice_origin="manual_replay"),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
                now=now,
            )

        self.assertEqual(result.status, "suppressed")
        self.assertEqual(result.reason, "DUPLICATE_WITHIN_24H")
        bridge_send.assert_not_called()

    def test_send_replay_window_flag_off_ignores_recent_publish_history_overlap(self):
        bridge_send = MagicMock(return_value=self._bridge_result())
        now = datetime(2026, 5, 4, 6, 45, 29, tzinfo=sender.JST)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text("", encoding="utf-8")
            history_path = Path(tmpdir) / "history.json"
            history_path.write_text(
                json.dumps(
                    {
                        "64416": (now - timedelta(minutes=4)).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            result = sender.send(
                self._request(
                    post_id=64416,
                    canonical_url="https://yoshilover.com/64416",
                    notice_origin="manual_replay",
                ),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                duplicate_history_path=queue_path,
                now=now,
                duplicate_window=timedelta(minutes=1),
            )

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()

    def test_send_real_path_calls_bridge_once(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
            },
            clear=True,
        ):
            result = sender.send(self._request(), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()
        mail_request = bridge_send.call_args.args[0]
        text_1 = "巨人の試合結果を更新しました。巨人が接戦を制した https://yoshilover.com/post-123/"
        text_2 = "試合の分岐点を整理。終盤の継投と一打が勝敗を分けた。 https://yoshilover.com/post-123/"
        text_3 = "これは試合後にもう一度見たいポイント。巨人が接戦を制した"
        self.assertEqual(bridge_send.call_args.kwargs, {"dry_run": False})
        self.assertEqual(mail_request.to, ["notice@example.com"])
        self.assertEqual(mail_request.subject, "【投稿候補】巨人が接戦を制した | YOSHILOVER")
        self.assertEqual(
            mail_request.text_body.splitlines(),
            [
                "次アクション: 内容確認後 X 投稿候補から選んで投稿",
                "title: 巨人が接戦を制した",
                "url: https://yoshilover.com/post-123/",
                "subtype: postgame",
                "publish time: 2026-04-24 21:15 JST",
                "summary: 終盤の継投と一打が勝敗を分けた。",
                "manual_x_post_candidates:",
                "article_url: https://yoshilover.com/post-123/",
                f"投稿文1: {text_1}",
                f"文字数: {len(text_1)}",
                f"Xで開く: {sender._build_x_intent_url(text_1)}",
                f"投稿文2: {text_2}",
                f"文字数: {len(text_2)}",
                f"Xで開く: {sender._build_x_intent_url(text_2)}",
                f"投稿文3: {text_3}",
                f"文字数: {len(text_3)}",
                f"Xで開く: {sender._build_x_intent_url(text_3)}",
                *self._per_post_metadata_lines(),
            ],
        )
        self.assertEqual(mail_request.metadata["post_id"], 123)
        self.assertEqual(result.bridge_result, bridge_result)

    def test_send_keeps_yoshilover_subject_when_sender_envs_change(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(
            "os.environ",
            {
                "PUBLISH_NOTICE_EMAIL_TO": "fwns6760@gmail.com",
                "MAIL_BRIDGE_SMTP_USERNAME": "y.sebata@shiny-lab.org",
                "MAIL_BRIDGE_FROM": "y.sebata@shiny-lab.org",
                "MAIL_BRIDGE_REPLY_TO": "fwns6760@gmail.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
            },
            clear=True,
        ):
            result = sender.send(self._request(), dry_run=False, send_enabled=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.subject, "【投稿候補】巨人が接戦を制した | YOSHILOVER")
        self.assertEqual(bridge_send.call_args.args[0].subject, "【投稿候補】巨人が接戦を制した | YOSHILOVER")

    def test_send_includes_bridge_result_object(self):
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
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

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
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

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com", sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True):
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
                subject="【公開済】巨人が接戦を制した | YOSHILOVER",
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
                "subject": "【公開済】巨人が接戦を制した | YOSHILOVER",
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
                subject="【公開済】巨人が接戦を制した | YOSHILOVER",
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
            {
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
                sender._MINIMAL_BODY_ENV: "0",
                sender._SUBJECT_DETAIL_ENV: "0",
            },
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
        self.assertEqual(row["subject"], "【投稿候補】巨人が接戦を制した | YOSHILOVER")

    def test_append_send_result_does_not_serialize_secret_like_bridge_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = f"{tmpdir}/queue.jsonl"
            result = sender.PublishNoticeEmailResult(
                status="error",
                reason="SMTPServerDisconnected",
                subject="【公開済】巨人が接戦を制した | YOSHILOVER",
                recipients=["notice@example.com"],
                bridge_result={"smtp_password": "should-not-leak-secret"},
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=63781,
                result=result,
                publish_time_iso="2026-04-27T09:05:37+09:00",
                recorded_at=datetime.fromisoformat("2026-04-27T11:31:14+09:00"),
            )
            raw = Path(queue_path).read_text(encoding="utf-8")

        self.assertNotIn("should-not-leak-secret", raw)
        self.assertNotIn("smtp_password", raw)

    def test_append_send_result_strict_stamp_records_history_only_after_sent_publish_verify(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP": "1"},
            clear=False,
        ), patch(
            "src.publish_notice_email_sender._verify_wp_status_publish",
            return_value=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            result = sender.PublishNoticeEmailResult(
                status="sent",
                reason=None,
                subject="【公開済】巨人が接戦を制した | YOSHILOVER",
                recipients=["notice@example.com"],
            )
            recorded_at = datetime.fromisoformat("2026-05-04T10:06:36.373219+09:00")

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=123,
                result=result,
                publish_time_iso="2026-05-04T09:55:49+09:00",
                recorded_at=recorded_at,
                request=self._request(summary=None, notice_origin="manual_replay"),
                history_path=history_path,
            )

            history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(history, {"123": "2026-05-04T10:06:36.373219+09:00"})

    def test_append_send_result_strict_stamp_skips_history_for_replay_window_suppression(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP": "1"},
            clear=False,
        ), patch(
            "src.publish_notice_email_sender._verify_wp_status_publish",
            return_value=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            result = sender.PublishNoticeEmailResult(
                status="suppressed",
                reason="DUPLICATE_WITHIN_REPLAY_WINDOW",
                subject="【公開済】巨人が接戦を制した | YOSHILOVER",
                recipients=["notice@example.com"],
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=123,
                result=result,
                publish_time_iso="2026-05-04T09:55:49+09:00",
                recorded_at=datetime.fromisoformat("2026-05-04T10:06:36.373219+09:00"),
                request=self._request(summary=None, notice_origin="manual_replay"),
                history_path=history_path,
            )

        self.assertFalse(history_path.exists())

    def test_append_send_result_strict_stamp_skips_history_for_publish_only_filter_suppression(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP": "1"},
            clear=False,
        ), patch(
            "src.publish_notice_email_sender._verify_wp_status_publish",
            return_value=True,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            result = sender.PublishNoticeEmailResult(
                status="suppressed",
                reason="PUBLISH_ONLY_FILTER",
                subject="【要確認】巨人戦の観戦案内を更新 | YOSHILOVER",
                recipients=["notice@example.com"],
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=123,
                result=result,
                publish_time_iso="2026-05-04T09:55:49+09:00",
                recorded_at=datetime.fromisoformat("2026-05-04T10:06:36.373219+09:00"),
                request=self._request(
                    title="巨人戦の観戦案内を更新",
                    subtype="notice",
                    summary="対象試合と受付条件を整理した。",
                    notice_origin="guarded_publish_history",
                ),
                history_path=history_path,
            )

        self.assertFalse(history_path.exists())

    def test_append_send_result_strict_stamp_skips_numeric_history_when_wp_status_not_publish(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP": "1"},
            clear=False,
        ), patch(
            "src.publish_notice_email_sender._verify_wp_status_publish",
            return_value=False,
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            result = sender.PublishNoticeEmailResult(
                status="sent",
                reason=None,
                subject="【要確認】巨人戦の観戦案内を更新 | YOSHILOVER",
                recipients=["notice@example.com"],
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=123,
                result=result,
                publish_time_iso="2026-05-04T09:55:49+09:00",
                recorded_at=datetime.fromisoformat("2026-05-04T10:06:36.373219+09:00"),
                request=self._request(
                    title="巨人戦の観戦案内を更新",
                    subtype="notice",
                    summary="対象試合と受付条件を整理した。",
                    notice_origin="direct_publish_scan",
                ),
                history_path=history_path,
            )

        self.assertFalse(history_path.exists())

    def test_append_send_result_strict_stamp_keeps_string_history_keys_without_wp_verify(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP": "1"},
            clear=False,
        ), patch(
            "src.publish_notice_email_sender._verify_wp_status_publish",
            side_effect=AssertionError("verify should not run for non-numeric keys"),
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            result = sender.PublishNoticeEmailResult(
                status="sent",
                reason=None,
                subject="【要review｜post_gen_validate】title rescue | YOSHILOVER",
                recipients=["notice@example.com"],
            )
            request = self._request(
                post_id="post_gen_validate:abc123",
                title="title rescue",
                summary=None,
                notice_kind="post_gen_validate",
                notice_origin="post_gen_validate_history",
                subject_override="【要review｜post_gen_validate】title rescue | YOSHILOVER",
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=request.post_id,
                result=result,
                publish_time_iso=request.publish_time_iso,
                recorded_at=datetime.fromisoformat("2026-05-04T10:45:35.435312+09:00"),
                request=request,
                history_path=history_path,
            )

            history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(history, {"post_gen_validate:abc123": "2026-05-04T10:45:35.435312+09:00"})

    def test_append_send_result_flag_off_keeps_existing_no_history_side_effect(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict("os.environ", {sender._MINIMAL_BODY_ENV: "0", sender._SUBJECT_DETAIL_ENV: "0"}, clear=True), patch(
            "src.publish_notice_email_sender._verify_wp_status_publish",
            side_effect=AssertionError("verify should not run when flag is off"),
        ):
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            result = sender.PublishNoticeEmailResult(
                status="sent",
                reason=None,
                subject="【公開済】巨人が接戦を制した | YOSHILOVER",
                recipients=["notice@example.com"],
            )

            sender.append_send_result(
                queue_path,
                notice_kind="per_post",
                post_id=123,
                result=result,
                publish_time_iso="2026-05-04T09:55:49+09:00",
                recorded_at=datetime.fromisoformat("2026-05-04T10:06:36.373219+09:00"),
                request=self._request(summary=None, notice_origin="manual_replay"),
                history_path=history_path,
            )

        self.assertFalse(history_path.exists())

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

    def test_summarize_merges_state_fetch_reasons_into_summary_reasons(self):
        summary = sender.summarize_execution_results(
            [],
            emitted=0,
            state_fetch_reasons={
                "transient_gcloud_attribute_error": 1,
                "permanent_auth": 2,
                "noisy_zero_count": 0,
            },
        )

        self.assertEqual(summary.sent, 0)
        self.assertEqual(summary.suppressed, 0)
        self.assertEqual(summary.errors, 0)
        self.assertEqual(
            summary.reasons,
            {
                "state_fetch_failed:permanent_auth": 2,
                "state_fetch_failed:transient_gcloud_attribute_error": 1,
            },
        )
        summary_line = sender.build_execution_summary_log(summary)
        self.assertIn("state_fetch_failed:permanent_auth", summary_line)
        self.assertIn("state_fetch_failed:transient_gcloud_attribute_error", summary_line)
        # send-side reasons must still merge cleanly when both sources are present
        merged = sender.summarize_execution_results(
            [
                sender.PublishNoticeEmailResult(
                    status="suppressed",
                    reason="NO_RECIPIENT",
                    subject="subject-a",
                    recipients=[],
                ),
            ],
            emitted=1,
            state_fetch_reasons={"transient_gcloud_other": 1},
        )
        self.assertEqual(
            merged.reasons,
            {
                "NO_RECIPIENT": 1,
                "state_fetch_failed:transient_gcloud_other": 1,
            },
        )

    def test_numeric_mismatch_suppresses_x_candidates_only(self):
        request = self._request(
            title="巨人 1-11 楽天",
            summary="巨人が楽天に19-1で勝利した。終盤も主導権を握った。",
        )

        classification = sender._classify_mail(request)
        body_lines = sender.build_body_text(request, classification=classification).splitlines()

        self.assertEqual(classification["mail_class"], "publish")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(classification["suppression_reason"], "x_post_numeric_mismatch")
        self.assertEqual(sender.build_manual_x_post_candidates(request), [])
        self.assertNotIn("manual_x_post_candidates:", body_lines)

    def test_unverified_player_name_suppresses_x_candidates_only(self):
        request = self._request(
            title="巨人が楽天に3-2で勝利",
            summary="巨人が楽天に3-2で勝利した。継投で逃げ切った。",
        )
        patched_candidates = [("x_post_1_article_intro", "戸郷翔征が完投した試合を更新。https://yoshilover.com/post-123/")]

        with patch.object(sender, "_render_manual_x_post_candidates", return_value=patched_candidates):
            classification = sender._classify_mail(request)
            body_lines = sender.build_body_text(request, classification=classification).splitlines()
            candidates = sender.build_manual_x_post_candidates(request)

        self.assertEqual(classification["mail_class"], "publish")
        self.assertEqual(classification["x_post_ready"], "false")
        self.assertEqual(classification["suppression_reason"], "x_post_unverified_player_name")
        self.assertEqual(candidates, [])
        self.assertNotIn("manual_x_post_candidates:", body_lines)


class MinimalBodyTests(unittest.TestCase):
    """User-requested minimal body — title + URL only."""

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

    def setUp(self):
        self._prev = os.environ.get(sender._MINIMAL_BODY_ENV)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(sender._MINIMAL_BODY_ENV, None)
        else:
            os.environ[sender._MINIMAL_BODY_ENV] = self._prev

    def test_default_is_minimal_body_with_title_and_url_only(self):
        os.environ.pop(sender._MINIMAL_BODY_ENV, None)
        body = sender.build_body_text(self._request())
        self.assertEqual(
            body,
            "巨人が接戦を制した\nhttps://yoshilover.com/post-123/",
        )

    def test_explicit_enable_yields_minimal_body(self):
        os.environ[sender._MINIMAL_BODY_ENV] = "1"
        body = sender.build_body_text(self._request())
        self.assertEqual(body.splitlines(), ["巨人が接戦を制した", "https://yoshilover.com/post-123/"])

    def test_env_zero_restores_verbose_body(self):
        os.environ[sender._MINIMAL_BODY_ENV] = "0"
        body = sender.build_body_text(self._request())
        # The verbose body still carries the "title:" / "url:" / "subtype:" markers.
        self.assertIn("title: 巨人が接戦を制した", body)
        self.assertIn("url: https://yoshilover.com/post-123/", body)
        self.assertIn("subtype: postgame", body)

    def test_minimal_body_skips_blank_url(self):
        os.environ[sender._MINIMAL_BODY_ENV] = "1"
        body = sender.build_body_text(self._request(canonical_url=""))
        self.assertEqual(body, "巨人が接戦を制した")


class HtmlBodyPerPostTests(unittest.TestCase):
    """build_body_html_per_post: HTML alternative for draft-first mail."""

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

    def test_returns_none_when_title_missing(self):
        result = sender.build_body_html_per_post(self._request(title=""))
        self.assertIsNone(result)

    def test_returns_none_when_url_missing(self):
        result = sender.build_body_html_per_post(self._request(canonical_url=""))
        self.assertIsNone(result)

    def test_returns_none_for_post_gen_validate_kind(self):
        # post_gen_validate notifications go to ops review, not the
        # publish-with-X workflow.
        result = sender.build_body_html_per_post(
            self._request(notice_kind="post_gen_validate"),
        )
        self.assertIsNone(result)

    def test_html_contains_title_url_and_article_button_only(self):
        html_body = sender.build_body_html_per_post(self._request())
        self.assertIsNotNone(html_body)
        # Title is escaped and rendered
        self.assertIn("巨人が接戦を制した", html_body)
        # Canonical URL appears as the 「記事を見る」 button href + text
        self.assertIn('href="https://yoshilover.com/post-123/"', html_body)
        self.assertIn("記事を見る", html_body)
        self.assertNotIn("x.com/intent/post", html_body)
        self.assertNotIn("𝕏 で投稿", html_body)

    def test_html_escapes_dangerous_title_chars(self):
        # If a title contained < > & " they must be HTML-escaped so the
        # rendered button does NOT execute as markup.
        req = self._request(title='<script>alert("x")</script>')
        html_body = sender.build_body_html_per_post(req)
        self.assertNotIn("<script>", html_body)
        self.assertIn("&lt;script&gt;", html_body)

    def test_html_omits_x_intent_hashtag_param(self):
        html_body = sender.build_body_html_per_post(self._request())
        self.assertNotIn("&amp;hashtags=", html_body)

    def test_html_omits_player_hashtag_intent_from_title(self):
        req = self._request(
            title="坂本勇人の逆転サヨナラ３００号",
        )
        html_body = sender.build_body_html_per_post(req)
        self.assertIn("坂本勇人の逆転サヨナラ３００号", html_body)
        self.assertNotIn("&amp;hashtags=", html_body)
        self.assertNotIn("x.com/intent/post", html_body)

    def test_html_omits_x_intent_for_non_player_title(self):
        req = self._request(
            title="逆転サヨナラ３００号",  # no player name in title
        )
        html_body = sender.build_body_html_per_post(req)
        self.assertIn("逆転サヨナラ３００号", html_body)
        self.assertNotIn("&amp;hashtags=", html_body)
        self.assertNotIn("x.com/intent/post", html_body)

    # --- 379-OPS (GH #53): 「公開してX投稿画面へ」 + 「WP編集画面で確認」 button ---

    def test_publish_button_html_omitted_when_url_not_set(self):
        html_body = sender.build_body_html_per_post(self._request())
        self.assertNotIn("公開してX投稿画面へ", html_body)
        self.assertNotIn("/publish-and-tweet", html_body)

    def test_publish_button_html_included_when_url_set(self):
        url = "https://yoshilover-fetcher.example.com/publish-and-tweet?post_id=123&token=1700.abc"
        req = self._request(publish_button_url=url)
        html_body = sender.build_body_html_per_post(req)
        self.assertIn("🚀 公開してX投稿画面へ", html_body)
        # URL は href に HTML-escape された形で含まれる
        self.assertIn("/publish-and-tweet?post_id=123", html_body)
        self.assertIn("&amp;token=1700.abc", html_body)

    def test_publish_button_html_escapes_dangerous_chars_in_url(self):
        url = 'https://x.test/?a=1&b="><script>'
        req = self._request(publish_button_url=url)
        html_body = sender.build_body_html_per_post(req)
        # raw script tag は HTML 内に live で出ない
        self.assertNotIn('"><script>', html_body)
        self.assertIn("&quot;", html_body)

    def test_admin_edit_button_html_included_when_url_set(self):
        req = self._request(
            admin_edit_url="https://yoshilover.com/wp-admin/post.php?post=123&action=edit",
        )
        html_body = sender.build_body_html_per_post(req)
        self.assertIn("✏️ WP編集画面で確認", html_body)
        self.assertIn("wp-admin/post.php?post=123", html_body)

    def test_publish_button_is_primary_without_x_intent_button(self):
        url = "https://fetcher.test/publish-and-tweet?post_id=1&token=t.h"
        req = self._request(publish_button_url=url)
        html_body = sender.build_body_html_per_post(req)
        publish_pos = html_body.find("公開してX投稿画面へ")
        self.assertGreater(publish_pos, 0)
        self.assertNotIn("𝕏 で投稿", html_body)
        self.assertNotIn("x.com/intent/post", html_body)


class XIntentHashtagBuilderTests(unittest.TestCase):
    """Unit tests for _build_x_post_intent_url(hashtags=...) and
    _derive_x_intent_hashtags(title) — the helpers behind the per-post
    HTML mail intent URL."""

    def test_intent_url_without_hashtags_unchanged(self):
        url = sender._build_x_post_intent_url(
            "test title", "https://example.com/p"
        )
        self.assertIn("text=", url)
        self.assertIn("url=", url)
        self.assertNotIn("hashtags=", url)

    def test_intent_url_with_hashtags_appended(self):
        url = sender._build_x_post_intent_url(
            "test title", "https://example.com/p", hashtags=["巨人", "坂本勇人"]
        )
        from urllib.parse import quote
        self.assertIn("hashtags=", url)
        self.assertIn(quote("巨人", safe=""), url)
        self.assertIn(quote("坂本勇人", safe=""), url)

    def test_intent_url_hashtag_normalization_strips_pound_and_whitespace(self):
        url = sender._build_x_post_intent_url(
            "t", "https://example.com/p", hashtags=["#巨人", " 坂本勇人 ", "巨人"]
        )
        from urllib.parse import quote, unquote
        from urllib.parse import urlparse, parse_qs
        parsed = parse_qs(urlparse(url).query)
        hashtags_value = unquote(parsed["hashtags"][0])
        # leading # stripped, whitespace stripped, duplicates removed
        self.assertEqual(hashtags_value.split(","), ["巨人", "坂本勇人"])

    def test_intent_url_empty_hashtags_omits_param(self):
        url = sender._build_x_post_intent_url(
            "t", "https://example.com/p", hashtags=[]
        )
        self.assertNotIn("hashtags=", url)

    def test_derive_hashtags_returns_only_fixed_when_no_player(self):
        out = sender._derive_x_intent_hashtags("逆転サヨナラ勝利")
        self.assertEqual(out, ("巨人",))

    def test_derive_hashtags_extends_with_player_names(self):
        out = sender._derive_x_intent_hashtags("坂本勇人の逆転サヨナラ３００号")
        self.assertIn("巨人", out)
        self.assertIn("坂本勇人", out)

    def test_derive_hashtags_caps_at_max(self):
        # Construct a title with many players — the cap is 5 total
        # (1 fixed + 4 players).
        title = "戸郷翔征 大城卓三 岡本和真 坂本勇人 吉川尚輝 浦田俊輔 が登場"
        out = sender._derive_x_intent_hashtags(title)
        self.assertLessEqual(len(out), sender._X_INTENT_HASHTAGS_MAX)
        self.assertEqual(out[0], "巨人")


class DetailedSubjectTests(unittest.TestCase):
    """279-QA — subject prefix carries subtype + state info by default."""

    def _request(self, **overrides):
        # Use a publish_time that is recent (now) so age=0 unless overridden.
        from datetime import datetime, timezone, timedelta
        jst_now = datetime.now(timezone(timedelta(hours=9)))
        payload = {
            "post_id": 64900,
            "title": "巨人・吉川尚輝が今季初本塁打",
            "canonical_url": "https://yoshilover.com/post-64900/",
            "subtype": "postgame",
            "publish_time_iso": jst_now.isoformat(timespec="seconds"),
            "summary": "",
        }
        payload.update(overrides)
        return sender.PublishNoticeRequest(**payload)

    def setUp(self):
        self._prev = os.environ.get(sender._SUBJECT_DETAIL_ENV)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(sender._SUBJECT_DETAIL_ENV, None)
        else:
            os.environ[sender._SUBJECT_DETAIL_ENV] = self._prev

    def test_publish_subject_carries_subtype(self):
        os.environ[sender._SUBJECT_DETAIL_ENV] = "1"
        prefix = sender._subject_prefix_for_classification(
            {"mail_class": "publish", "reason": None},
            request=self._request(subtype="lineup"),
        )
        self.assertEqual(prefix, "【公開済｜lineup】")

    def test_review_subject_carries_short_reason_and_subtype(self):
        os.environ[sender._SUBJECT_DETAIL_ENV] = "1"
        prefix = sender._subject_prefix_for_classification(
            {"mail_class": "review", "reason": "farm_result_review"},
            request=self._request(subtype="farm_result"),
        )
        # Short label "farm" comes first; subtype "farm-result" appended.
        self.assertEqual(prefix, "【要確認｜farm｜farm-result】")

    def test_review_x_blocked_keeps_legacy_marker_and_appends_subtype(self):
        os.environ[sender._SUBJECT_DETAIL_ENV] = "1"
        prefix = sender._subject_prefix_for_classification(
            {"mail_class": "review", "reason": "roster_movement_yellow_x_blocked"},
            request=self._request(subtype="roster"),
        )
        self.assertEqual(prefix, "【要確認・X見送り｜roster-yellow｜roster】")

    def test_stale_review_marks_old_candidate(self):
        os.environ[sender._SUBJECT_DETAIL_ENV] = "1"
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(timezone(timedelta(hours=9))) - timedelta(hours=48)).isoformat(timespec="seconds")
        prefix = sender._subject_prefix_for_classification(
            {"mail_class": "review", "reason": "default_review"},
            request=self._request(subtype="manager", publish_time_iso=old),
        )
        self.assertIn("(古い候補)", prefix)
        self.assertIn("manager", prefix)

    def test_unknown_subtype_falls_back_to_bare_prefix(self):
        os.environ[sender._SUBJECT_DETAIL_ENV] = "1"
        prefix = sender._subject_prefix_for_classification(
            {"mail_class": "publish", "reason": None},
            request=self._request(subtype="unknown"),
        )
        self.assertEqual(prefix, "【公開済】")

    def test_env_disable_restores_legacy_prefix(self):
        os.environ[sender._SUBJECT_DETAIL_ENV] = "0"
        prefix = sender._subject_prefix_for_classification(
            {"mail_class": "publish", "reason": None},
            request=self._request(subtype="lineup"),
        )
        self.assertEqual(prefix, "【公開済】")

    def test_no_request_falls_back_to_legacy(self):
        # Backward-compat for callers that don't pass a request.
        os.environ[sender._SUBJECT_DETAIL_ENV] = "1"
        prefix = sender._subject_prefix_for_classification(
            {"mail_class": "review", "reason": "farm_result_review"},
        )
        self.assertEqual(prefix, "【要確認】")


class MorningHeartbeatTests(unittest.TestCase):
    """B-plan reliability layer — guaranteed 06:00 JST mail."""

    def setUp(self):
        self._prev = os.environ.get(sender._MORNING_HEARTBEAT_ENV)
        os.environ[sender._MORNING_HEARTBEAT_ENV] = "1"
        self.tmpdir = tempfile.TemporaryDirectory()
        self.queue_path = Path(self.tmpdir.name) / "queue.jsonl"

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(sender._MORNING_HEARTBEAT_ENV, None)
        else:
            os.environ[sender._MORNING_HEARTBEAT_ENV] = self._prev
        self.tmpdir.cleanup()

    def _morning_now(self):
        from datetime import datetime, timezone, timedelta
        return datetime(2026, 5, 9, 6, 5, tzinfo=timezone(timedelta(hours=9)))

    def _afternoon_now(self):
        from datetime import datetime, timezone, timedelta
        return datetime(2026, 5, 9, 15, 0, tzinfo=timezone(timedelta(hours=9)))

    def test_fires_at_06_00_jst(self):
        bridge = MagicMock(return_value=mail_delivery_bridge.MailResult(
            status="sent", refused_recipients={}, smtp_response=[250, "ok"], reason=None
        ))
        with patch.dict("os.environ", {
            "PUBLISH_NOTICE_EMAIL_TO": "user@example.com",
            sender._MORNING_HEARTBEAT_ENV: "1",
        }, clear=True):
            sent = sender.maybe_send_morning_heartbeat(
                queue_path=self.queue_path,
                dry_run=False,
                send_enabled=True,
                processed_this_fire=0,
                bridge_send=bridge,
                now=self._morning_now(),
            )
        self.assertTrue(sent)
        bridge.assert_called_once()

    def test_no_fire_outside_window(self):
        bridge = MagicMock()
        with patch.dict("os.environ", {
            "PUBLISH_NOTICE_EMAIL_TO": "user@example.com",
            sender._MORNING_HEARTBEAT_ENV: "1",
        }, clear=True):
            sent = sender.maybe_send_morning_heartbeat(
                queue_path=self.queue_path,
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge,
                now=self._afternoon_now(),
            )
        self.assertFalse(sent)
        bridge.assert_not_called()

    def test_no_fire_when_disabled(self):
        bridge = MagicMock()
        with patch.dict("os.environ", {
            "PUBLISH_NOTICE_EMAIL_TO": "user@example.com",
            sender._MORNING_HEARTBEAT_ENV: "0",
        }, clear=True):
            sent = sender.maybe_send_morning_heartbeat(
                queue_path=self.queue_path,
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge,
                now=self._morning_now(),
            )
        self.assertFalse(sent)
        bridge.assert_not_called()

    def test_double_fire_within_same_morning_skipped(self):
        bridge = MagicMock(return_value=mail_delivery_bridge.MailResult(
            status="sent", refused_recipients={}, smtp_response=[250, "ok"], reason=None
        ))
        with patch.dict("os.environ", {
            "PUBLISH_NOTICE_EMAIL_TO": "user@example.com",
            sender._MORNING_HEARTBEAT_ENV: "1",
        }, clear=True):
            first = sender.maybe_send_morning_heartbeat(
                queue_path=self.queue_path,
                dry_run=False, send_enabled=True,
                bridge_send=bridge, now=self._morning_now(),
            )
            second = sender.maybe_send_morning_heartbeat(
                queue_path=self.queue_path,
                dry_run=False, send_enabled=True,
                bridge_send=bridge, now=self._morning_now(),
            )
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(bridge.call_count, 1)

    def test_subject_format(self):
        from datetime import datetime, timezone, timedelta
        n = datetime(2026, 5, 9, 6, 5, tzinfo=timezone(timedelta(hours=9)))
        subject = sender.build_morning_heartbeat_subject(now=n)
        self.assertIn("【朝サマリー】", subject)
        self.assertIn("5月9日", subject)
        self.assertTrue(subject.endswith(" | YOSHILOVER"))

    def test_body_includes_processed_count(self):
        from datetime import datetime, timezone, timedelta
        n = datetime(2026, 5, 9, 6, 5, tzinfo=timezone(timedelta(hours=9)))
        body = sender.build_morning_heartbeat_body(now=n, processed_this_fire=3)
        self.assertIn("06:05 JST", body)
        self.assertIn("処理: 3件", body)

    def test_retry_fires_at_06_30_when_06_00_failed(self):
        """If 06:00 fire returned an error, 06:30 fire must retry."""
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        first = datetime(2026, 5, 9, 6, 5, tzinfo=jst)
        second = datetime(2026, 5, 9, 6, 35, tzinfo=jst)
        bridge_fail = MagicMock(side_effect=Exception("smtp down"))
        bridge_ok = MagicMock(return_value=mail_delivery_bridge.MailResult(
            status="sent", refused_recipients={}, smtp_response=[250, "ok"], reason=None
        ))
        with patch.dict("os.environ", {
            "PUBLISH_NOTICE_EMAIL_TO": "user@example.com",
            sender._MORNING_HEARTBEAT_ENV: "1",
        }, clear=True):
            r1 = sender.maybe_send_morning_heartbeat(
                queue_path=self.queue_path, dry_run=False, send_enabled=True,
                bridge_send=bridge_fail, now=first,
            )
            r2 = sender.maybe_send_morning_heartbeat(
                queue_path=self.queue_path, dry_run=False, send_enabled=True,
                bridge_send=bridge_ok, now=second,
            )
        self.assertTrue(r1)  # attempted (recorded as error)
        self.assertTrue(r2)  # retried successfully
        self.assertEqual(bridge_ok.call_count, 1)

    def test_retry_window_includes_07_00_but_not_07_30(self):
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        # 07:00 still in window
        self.assertTrue(sender._is_first_morning_publish_notice_fire(
            now=datetime(2026, 5, 9, 7, 0, tzinfo=jst)
        ))
        # 07:30 outside window
        self.assertFalse(sender._is_first_morning_publish_notice_fire(
            now=datetime(2026, 5, 9, 7, 30, tzinfo=jst)
        ))


if __name__ == "__main__":
    unittest.main()
