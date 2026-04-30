import json
import logging
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import publish_notice_email_sender as sender
from src import publish_notice_scanner as scanner
from src import rss_fetcher


NOW = datetime(2026, 4, 30, 15, 0, tzinfo=scanner.JST)


class PostGenValidateNotificationTests(unittest.TestCase):
    def _entry(self, index: int = 0, **overrides):
        payload = {
            "ts": NOW.isoformat(),
            "source_url": f"https://example.com/article-{index}",
            "source_url_hash": f"hash{index:04d}",
            "source_title": f"元記事タイトル {index}",
            "generated_title": f"自動生成タイトル {index}",
            "category": "試合速報",
            "article_subtype": "postgame",
            "skip_reason": "weak_subject_title:related_info_escape",
            "fail_axis": ["weak_subject_title:related_info_escape"],
        }
        payload.update(overrides)
        return payload

    def _post(self, **overrides):
        payload = {
            "id": 101,
            "title": {"rendered": "巨人が阪神に競り勝った"},
            "excerpt": {"rendered": "<p>巨人が阪神に競り勝った。終盤の継投と決勝打が焦点になった。</p>"},
            "content": {"rendered": "<p>本文1段落目。</p><p>本文2段落目。</p>"},
            "link": "https://yoshilover.com/post-101/",
            "date": "2026-04-30T14:55:00+09:00",
            "status": "publish",
            "meta": {"article_subtype": "postgame"},
        }
        payload.update(overrides)
        return payload

    def _guarded_entry(self, **overrides):
        payload = {
            "post_id": 901,
            "ts": NOW.isoformat(),
            "status": "refused",
            "judgment": "yellow",
            "publishable": True,
            "cleanup_required": False,
            "cleanup_success": False,
            "hold_reason": "backlog_only",
        }
        payload.update(overrides)
        return payload

    def _bridge_result(self):
        return mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )

    def _capture_log_events(self):
        events: list[dict[str, object]] = []

        def fake_log_event(event: str, **payload):
            events.append({"event": event, **payload})

        return events, fake_log_event

    def test_fetcher_default_off_keeps_logger_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "post_gen_validate_history.jsonl"
            logger = logging.getLogger("test_fetcher_default_off")
            logger.info = MagicMock()

            with patch.dict("os.environ", {}, clear=True), patch.object(
                rss_fetcher, "POST_GEN_VALIDATE_HISTORY_DEFAULT_PATH", history_path
            ), patch.object(rss_fetcher, "_gcs_client", return_value=None):
                rss_fetcher._log_article_skipped_post_gen_validate(
                    logger,
                    title="生成タイトル",
                    source_title="元タイトル",
                    post_url="https://example.com/post-1",
                    category="試合速報",
                    article_subtype="postgame",
                    fail_axes=["weak_subject_title:related_info_escape"],
                    stop_reason="weak_subject_title_review",
                )

        self.assertFalse(history_path.exists())
        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "article_skipped_post_gen_validate")
        self.assertEqual(payload["skip_layer"], "post_gen_validate")
        self.assertEqual(payload["skip_reason"], "weak_subject_title:related_info_escape")

    def test_fetcher_flag_on_writes_post_gen_validate_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "post_gen_validate_history.jsonl"
            logger = logging.getLogger("test_fetcher_flag_on")
            logger.info = MagicMock()

            with patch.dict(
                "os.environ",
                {"ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1"},
                clear=True,
            ), patch.object(rss_fetcher, "POST_GEN_VALIDATE_HISTORY_DEFAULT_PATH", history_path), patch.object(
                rss_fetcher, "_gcs_client", return_value=None
            ):
                rss_fetcher._log_article_skipped_post_gen_validate(
                    logger,
                    title="生成タイトル",
                    source_title="元タイトル",
                    post_url="https://example.com/post-2",
                    category="試合速報",
                    article_subtype="postgame",
                    fail_axes=["weak_generated_title:no_strong_marker"],
                    stop_reason="weak_generated_title_review",
                )

            rows = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_title"], "元タイトル")
        self.assertEqual(rows[0]["generated_title"], "生成タイトル")
        self.assertEqual(rows[0]["skip_reason"], "weak_generated_title:no_strong_marker")
        self.assertEqual(rows[0]["fail_axis"], ["weak_generated_title:no_strong_marker"])
        self.assertEqual(len(rows[0]["source_url_hash"]), 16)

    def test_scan_and_send_twenty_two_post_gen_validate_notifications(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1",
                "PUBLISH_NOTICE_EMAIL_TO": "notice@example.com",
            },
            clear=True,
        ):
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path = Path(tmpdir) / "post_gen_validate_cursor.txt"
            ledger_path = Path(tmpdir) / "post_gen_validate_history.jsonl"
            ledger_path.write_text(
                "\n".join(
                    json.dumps(
                        self._entry(
                            index=index,
                            ts=f"2026-04-30T14:{index:02d}:00+09:00",
                        ),
                        ensure_ascii=False,
                    )
                    for index in range(22)
                )
                + "\n",
                encoding="utf-8",
            )
            result = scanner.scan_post_gen_validate_history(
                post_gen_validate_history_path=ledger_path,
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                max_per_run=25,
                now=lambda: NOW,
            )

            bridge_send = MagicMock(return_value=self._bridge_result())
            send_results = []
            for request in result.emitted:
                mail_result = sender.send(
                    request,
                    dry_run=False,
                    send_enabled=True,
                    bridge_send=bridge_send,
                    duplicate_history_path=queue_path,
                )
                sender.append_send_result(
                    queue_path,
                    notice_kind="per_post",
                    post_id=request.post_id,
                    result=mail_result,
                    publish_time_iso=request.publish_time_iso,
                )
                send_results.append(mail_result)

        self.assertEqual(len(result.emitted), 22)
        self.assertEqual(len(send_results), 22)
        self.assertTrue(all(item.status == "sent" for item in send_results))
        self.assertEqual(bridge_send.call_count, 22)

    def test_subject_prefix_and_reason_mapping_cover_all_supported_cases(self):
        cases = [
            (
                "weak_subject_title:related_info_escape",
                "タイトルが『関連情報』『発言ポイント』だけで、人名や文脈を拾えなかったため",
            ),
            (
                "weak_generated_title:no_strong_marker",
                "タイトルが弱い表現で、強いニュース要素を判定できなかったため",
            ),
            (
                "weak_generated_title:blacklist_phrase",
                "タイトルに blacklist phrase を含み、そのまま publish 候補にできないため",
            ),
            (
                "postgame_strict:strict_validation_fail:required_facts_missing:scoreline",
                "postgame strict template に必要な fact が不足しているため",
            ),
            (
                "close_marker",
                "close marker を検出できず、後追い記事の疑いがあるため",
            ),
            (
                "manager_quote_zero_review:missing_named_quote",
                "manager_quote_zero_review:missing_named_quote",
            ),
        ]

        for index, (skip_reason, expected_label) in enumerate(cases, start=1):
            with self.subTest(skip_reason=skip_reason):
                entry = self._entry(
                    index=index,
                    skip_reason=skip_reason,
                    fail_axis=[skip_reason],
                    source_title=f"元記事 {index}",
                    generated_title=f"生成記事 {index}",
                )
                result = scanner.scan_post_gen_validate_history(
                    post_gen_validate_history_path=self._write_single_entry(entry),
                    cursor_path=self._temp_path("cursor"),
                    history_path=self._temp_path("history"),
                    queue_path=self._temp_path("queue"),
                    max_per_run=5,
                    now=lambda: NOW,
                    write_history=False,
                    write_cursor=False,
                )
                request = result.emitted[0]
                body = sender.build_body_text(request)

                self.assertTrue(str(request.subject_override).startswith("【要review｜post_gen_validate】"))
                self.assertTrue(str(request.subject_override).endswith("| YOSHILOVER"))
                self.assertIn(f"理由: {expected_label}", body)
                self.assertIn(f"source_title: 元記事 {index}", body)
                self.assertIn(f"generated_title: 生成記事 {index}", body)
                self.assertIn(f"source_url: {entry['source_url']}", body)
                self.assertIn(f"skip_reason: {skip_reason}", body)
                self.assertIn("record_type: post_gen_validate", body)
                self.assertIn("skip_layer: post_gen_validate", body)
                self.assertNotIn("manual_x_post_candidates", body)

    def test_post_gen_validate_dedup_and_cap_carryover(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1"},
            clear=True,
        ):
            ledger_path = Path(tmpdir) / "post_gen_validate_history.jsonl"
            cursor_path = Path(tmpdir) / "post_gen_validate_cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            entries = [
                self._entry(index=1, ts="2026-04-30T14:01:00+09:00", source_url_hash="samehash"),
                self._entry(index=2, ts="2026-04-30T14:02:00+09:00", source_url_hash="samehash"),
                self._entry(index=3, ts="2026-04-30T14:03:00+09:00", source_url_hash="samehash", skip_reason="close_marker", fail_axis=["close_marker"]),
                self._entry(index=4, ts="2026-04-30T14:04:00+09:00", source_url_hash="hash0004"),
            ]
            ledger_path.write_text(
                "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
                encoding="utf-8",
            )
            events, fake_log_event = self._capture_log_events()

            with patch.object(scanner, "_log_event", side_effect=fake_log_event):
                first = scanner.scan_post_gen_validate_history(
                    post_gen_validate_history_path=ledger_path,
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    max_per_run=2,
                    now=lambda: NOW,
                )
                first_cursor_exists = cursor_path.exists()
                second = scanner.scan_post_gen_validate_history(
                    post_gen_validate_history_path=ledger_path,
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    max_per_run=2,
                    now=lambda: NOW,
                )
                second_cursor = cursor_path.read_text(encoding="utf-8").strip()
                queue_rows = [
                    json.loads(line)
                    for line in queue_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]

        self.assertEqual([request.post_id for request in first.emitted], ["post_gen_validate:hash0004:weak_subject_title:related_info_escape", "post_gen_validate:samehash:close_marker"])
        self.assertFalse(first_cursor_exists)
        self.assertEqual([request.post_id for request in second.emitted], ["post_gen_validate:samehash:weak_subject_title:related_info_escape"])
        self.assertEqual(second_cursor, "2026-04-30T14:04:00+09:00")
        self.assertEqual([row["record_type"] for row in queue_rows], ["post_gen_validate", "post_gen_validate", "post_gen_validate"])
        self.assertTrue(all(row["skip_layer"] == "post_gen_validate" for row in queue_rows))
        self.assertTrue(any(event["event"] == "post_gen_validate_history_scan_cap_exceeded" for event in events))
        self.assertTrue(any(event["event"] == "post_gen_validate_history_scan_summary" for event in events))

    def test_scan_integration_keeps_publish_and_guarded_paths_and_adds_post_gen_validate(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1",
                "PUBLISH_NOTICE_REVIEW_MAX_PER_RUN": "5",
            },
            clear=True,
        ):
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            guarded_cursor_path = Path(tmpdir) / "guarded_publish_history_cursor.txt"
            post_gen_history_path = Path(tmpdir) / "post_gen_validate_history.jsonl"
            post_gen_cursor_path = Path(tmpdir) / "post_gen_validate_cursor.txt"
            cursor_path.write_text("2026-04-30T14:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            guarded_history_path.write_text(
                json.dumps(self._guarded_entry(post_id=902, ts="2026-04-30T14:40:00+09:00"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            post_gen_history_path.write_text(
                json.dumps(self._entry(index=9, ts="2026-04-30T14:50:00+09:00"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with patch.object(
                scanner,
                "_default_fetch_post_detail",
                side_effect=lambda base, post_id: self._post(
                    id=post_id,
                    status="draft",
                    link=f"https://yoshilover.com/draft-{post_id}/",
                ),
            ):
                result = scanner.scan(
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    guarded_publish_history_path=guarded_history_path,
                    guarded_cursor_path=guarded_cursor_path,
                    post_gen_validate_history_path=post_gen_history_path,
                    post_gen_validate_cursor_path=post_gen_cursor_path,
                    fetch=lambda base, after: [self._post(id=701, date="2026-04-30T14:45:00+09:00")],
                    now=lambda: NOW,
                )

        self.assertEqual([request.post_id for request in result.emitted[:3]], [701, 902, "post_gen_validate:hash0009:weak_subject_title:related_info_escape"])
        self.assertEqual(result.emitted[0].notice_kind, "publish")
        self.assertEqual(result.emitted[1].notice_kind, "review_hold")
        self.assertEqual(result.emitted[2].notice_kind, "post_gen_validate")
        self.assertEqual(result.emitted[2].record_type, "post_gen_validate")

    def _write_single_entry(self, entry: dict[str, object]) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        ledger_path = Path(tempdir.name) / "post_gen_validate_history.jsonl"
        ledger_path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
        return ledger_path

    def _temp_path(self, name: str) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        return Path(tempdir.name) / f"{name}.json"


if __name__ == "__main__":
    unittest.main()
