import json
import logging
import re
import smtplib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
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
            "https://twitter.com/intent/tweet?text=%E5%B7%A8%E4%BA%BA%E3%81%AE%E8%A9%A6%E5%90%88%E7%B5%90%E6%9E%9C%E3%82%92%E6%9B%B4%E6%96%B0%E3%81%97%E3%81%BE%E3%81%97%E3%81%9F%E3%80%82%E5%B7%A8%E4%BA%BA%E3%81%8C%E6%8E%A5%E6%88%A6%E3%82%92%E5%88%B6%E3%81%97%E3%81%9F%20https%3A%2F%2Fyoshilover.com%2Fpost-123%2F",
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
            f"https://twitter.com/intent/tweet?text={quote(text, safe='')}",
        )

    def test_intent_url_encoding_special_chars(self):
        text = "#巨人 #ジャイアンツ https://yoshilover.com/post-123/"
        intent_url = sender._build_x_intent_url(text)

        self.assertEqual(intent_url, f"https://twitter.com/intent/tweet?text={quote(text, safe='')}")
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
            "https://twitter.com/intent/tweet?text="
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

        with patch.dict("os.environ", {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = sender.send(request, bridge_send=bridge_send)

        self.assertEqual(result.status, "dry_run")
        self.assertIsNone(result.reason)
        self.assertEqual(result.subject, "【投稿候補】巨人が接戦を制した | YOSHILOVER")
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


if __name__ == "__main__":
    unittest.main()
