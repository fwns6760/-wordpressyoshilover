import json
import logging
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import publish_notice_email_sender as sender
from src import publish_notice_scanner as scanner
from src import rss_fetcher


NOW = datetime(2026, 5, 1, 15, 0, tzinfo=scanner.JST)


class PreflightSkipNotificationTests(unittest.TestCase):
    def _candidate(self, **overrides):
        payload = {
            "title": "【巨人】阿部監督が継投の狙いを説明",
            "summary": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
            "body_text": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
            "source_body": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
            "category": "首脳陣",
            "article_subtype": "manager",
            "source_name": "スポーツ報知",
            "source_url": "https://news.hochi.news/articles/example.html",
            "source_type": "news",
            "source_links": [],
            "published_at": NOW,
            "has_game": True,
            "duplicate_guard_context": {},
        }
        payload.update(overrides)
        return payload

    def _entry(self, index: int = 0, **overrides):
        payload = {
            "ts": NOW.isoformat(),
            "record_type": "preflight_skip",
            "skip_layer": "preflight",
            "source_url": f"https://example.com/article-{index}",
            "source_url_hash": f"hash{index:04d}",
            "content_hash": f"body{index:04d}",
            "source_title": f"元記事タイトル {index}",
            "category": "試合速報",
            "article_subtype": "postgame",
            "source_name": "スポーツ報知",
            "source_type": "news",
            "skip_reason": "placeholder_body",
        }
        payload.update(overrides)
        return payload

    def _post_gen_entry(self, index: int = 0, **overrides):
        payload = {
            "ts": f"2026-05-01T14:{index:02d}:00+09:00",
            "record_type": "post_gen_validate",
            "skip_layer": "post_gen_validate",
            "source_url": f"https://example.com/post-gen-{index}",
            "source_url_hash": f"postgen{index:04d}",
            "source_title": f"post gen source {index}",
            "generated_title": f"generated {index}",
            "category": "試合速報",
            "article_subtype": "postgame",
            "skip_reason": "weak_subject_title:related_info_escape",
            "fail_axis": ["weak_subject_title:related_info_escape"],
        }
        payload.update(overrides)
        return payload

    def _write_entries(self, name: str, entries: list[dict[str, object]]) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        ledger_path = Path(tempdir.name) / name
        ledger_path.write_text(
            "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
            encoding="utf-8",
        )
        return ledger_path

    def _temp_path(self, name: str) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        return Path(tempdir.name) / name

    def _capture_log_events(self):
        events: list[dict[str, object]] = []

        def fake_log_event(event: str, **payload):
            events.append({"event": event, **payload})

        return events, fake_log_event

    def test_fetcher_flag_on_writes_preflight_skip_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "preflight_skip_history.jsonl"
            logger = logging.getLogger("test_preflight_fetcher_flag_on")
            logger.info = MagicMock()

            with patch.dict(
                "os.environ",
                {
                    "ENABLE_GEMINI_PREFLIGHT": "1",
                    "ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1",
                },
                clear=True,
            ), patch.object(
                rss_fetcher, "PREFLIGHT_SKIP_HISTORY_DEFAULT_PATH", history_path
            ), patch.object(
                rss_fetcher, "_gcs_client", return_value=None
            ), patch.object(
                rss_fetcher,
                "_gemini_cache_lookup",
                side_effect=AssertionError("cache lookup should not run"),
            ), patch.object(
                rss_fetcher,
                "_request_gemini_strict_text",
                side_effect=AssertionError("Gemini request should not run"),
            ):
                text, telemetry = rss_fetcher._gemini_text_with_cache(
                    api_key="api-key",
                    prompt="PROMPT",
                    logger=logger,
                    attempt_limit=3,
                    min_chars=1,
                    source_url="https://example.com/preflight-skip",
                    content_text="本文A",
                    prompt_template_id="prompt-v1",
                    cache_manager=object(),
                    candidate_meta=self._candidate(existing_publish_same_source_url=True),
                    now=NOW,
                    log_label="test",
                )

            rows = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(text, "")
        self.assertFalse(telemetry["gemini_call_made"])
        self.assertEqual(telemetry["skip_reason"], "existing_publish_same_source_url")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_type"], "preflight_skip")
        self.assertEqual(rows[0]["skip_layer"], "preflight")
        self.assertEqual(rows[0]["skip_reason"], "existing_publish_same_source_url")
        self.assertEqual(rows[0]["source_title"], "【巨人】阿部監督が継投の狙いを説明")
        self.assertEqual(rows[0]["source_name"], "スポーツ報知")
        self.assertEqual(rows[0]["source_type"], "news")
        self.assertTrue(rows[0]["has_game"])
        self.assertTrue(rows[0]["existing_publish_same_source_url"])
        self.assertEqual(rows[0]["content_hash"], telemetry["content_hash"])

    def test_scan_emits_preflight_skip_mail_when_flag_on(self):
        with patch.dict(
            "os.environ",
            {"ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1"},
            clear=True,
        ):
            result = scanner.scan_preflight_skip_history(
                preflight_skip_history_path=self._write_entries(
                    "preflight_skip_history.jsonl",
                    [
                        self._entry(
                            index=2,
                            ts="2026-05-01T14:05:00+09:00",
                            article_subtype="pregame",
                            source_title="巨人の試合前情報を整理",
                            skip_reason="placeholder_body",
                        )
                    ],
                ),
                cursor_path=self._temp_path("preflight_skip_cursor.txt"),
                history_path=self._temp_path("history.json"),
                queue_path=self._temp_path("queue.jsonl"),
                now=lambda: NOW,
                write_history=False,
                write_cursor=False,
            )

        self.assertEqual(len(result.emitted), 1)
        request = result.emitted[0]
        body = sender.build_body_text(request)
        self.assertEqual(request.record_type, "preflight_skip")
        self.assertEqual(request.skip_layer, "preflight")
        self.assertTrue(str(request.subject_override).startswith("【要review｜preflight_skip】"))
        self.assertTrue(str(request.subject_override).endswith("| YOSHILOVER"))
        self.assertIn("理由: source body が placeholder のままで、本文生成に進めないため", body)
        self.assertIn("source_title: 巨人の試合前情報を整理", body)
        self.assertIn("source_url_hash: hash0002", body)
        self.assertIn("record_type: preflight_skip", body)
        self.assertIn("skip_layer: preflight", body)

    def test_preflight_skip_reason_label_mapping_covers_all_supported_cases(self):
        cases = [
            ("existing_publish_same_source_url", "同じ source_url の publish 済み記事が既に存在するため"),
            ("placeholder_body", "source body が placeholder のままで、本文生成に進めないため"),
            ("not_giants_related", "巨人関連の記事と判定できず、対象外のため"),
            ("live_update_target_disabled", "live_update 記事は現行運用で無効化されているため"),
            ("farm_lineup_backlog_blocked", "二軍スタメン記事が backlog 条件に入り、現時点では対象外のため"),
            ("farm_result_age_exceeded", "二軍試合結果の記事が許容期限を超えたため"),
            ("unofficial_source_only", "非公式ソースのみで、公式・準公式の裏取りがないため"),
            ("expected_hard_stop_death_or_grave", "死亡・重篤系のセンシティブ話題で hard stop 対象のため"),
        ]

        with patch.dict("os.environ", {"ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1"}, clear=True):
            for index, (skip_reason, expected_label) in enumerate(cases, start=1):
                with self.subTest(skip_reason=skip_reason):
                    result = scanner.scan_preflight_skip_history(
                        preflight_skip_history_path=self._write_entries(
                            f"preflight_skip_history_{index}.jsonl",
                            [self._entry(index=index, skip_reason=skip_reason)],
                        ),
                        cursor_path=self._temp_path(f"preflight_skip_cursor_{index}.txt"),
                        history_path=self._temp_path(f"history_{index}.json"),
                        queue_path=self._temp_path(f"queue_{index}.jsonl"),
                        now=lambda: NOW,
                        write_history=False,
                        write_cursor=False,
                    )
                    body = sender.build_body_text(result.emitted[0])
                    self.assertIn(f"理由: {expected_label}", body)

    def test_preflight_skip_dedup_24h_window(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1"},
            clear=True,
        ):
            ledger_path = Path(tmpdir) / "preflight_skip_history.jsonl"
            cursor_path = Path(tmpdir) / "preflight_skip_cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            entries = [
                self._entry(index=1, ts="2026-05-01T14:01:00+09:00", source_url_hash="samehash"),
                self._entry(index=2, ts="2026-05-01T14:02:00+09:00", source_url_hash="samehash"),
                self._entry(
                    index=3,
                    ts="2026-05-01T14:03:00+09:00",
                    source_url_hash="samehash",
                    skip_reason="not_giants_related",
                ),
            ]
            ledger_path.write_text(
                "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
                encoding="utf-8",
            )

            result = scanner.scan_preflight_skip_history(
                preflight_skip_history_path=ledger_path,
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                max_per_run=5,
                now=lambda: NOW,
            )
            queue_rows = [
                json.loads(line)
                for line in queue_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(
            [request.post_id for request in result.emitted],
            [
                "preflight_skip:samehash:not_giants_related",
                "preflight_skip:samehash:placeholder_body",
            ],
        )
        self.assertEqual([row["record_type"] for row in queue_rows], ["preflight_skip", "preflight_skip"])
        self.assertTrue(all(row["skip_layer"] == "preflight" for row in queue_rows))
        self.assertEqual(result.skipped, [("preflight_skip:samehash:placeholder_body", "PREFLIGHT_SKIP_RECENT_DUPLICATE")])

    def test_preflight_skip_shared_cap_with_post_gen_validate_keeps_priority(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1",
                "ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1",
                "PUBLISH_NOTICE_REVIEW_MAX_PER_RUN": "10",
            },
            clear=True,
        ):
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            post_gen_history_path = Path(tmpdir) / "post_gen_validate_history.jsonl"
            post_gen_cursor_path = Path(tmpdir) / "post_gen_validate_cursor.txt"
            preflight_history_path = Path(tmpdir) / "preflight_skip_history.jsonl"
            preflight_cursor_path = Path(tmpdir) / "preflight_skip_cursor.txt"
            cursor_path.write_text("2026-05-01T13:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            post_gen_history_path.write_text(
                "\n".join(
                    json.dumps(self._post_gen_entry(index=index), ensure_ascii=False)
                    for index in range(6)
                )
                + "\n",
                encoding="utf-8",
            )
            preflight_history_path.write_text(
                "\n".join(
                    json.dumps(
                        self._entry(
                            index=index,
                            ts=f"2026-05-01T14:{10 + index:02d}:00+09:00",
                            source_url_hash=f"pre{index:04d}",
                        ),
                        ensure_ascii=False,
                    )
                    for index in range(6)
                )
                + "\n",
                encoding="utf-8",
            )

            first = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                post_gen_validate_history_path=post_gen_history_path,
                post_gen_validate_cursor_path=post_gen_cursor_path,
                preflight_skip_history_path=preflight_history_path,
                preflight_skip_cursor_path=preflight_cursor_path,
                fetch=lambda base, after: [],
                now=lambda: NOW,
            )
            preflight_cursor_exists_after_first = preflight_cursor_path.exists()
            second = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                post_gen_validate_history_path=post_gen_history_path,
                post_gen_validate_cursor_path=post_gen_cursor_path,
                preflight_skip_history_path=preflight_history_path,
                preflight_skip_cursor_path=preflight_cursor_path,
                fetch=lambda base, after: [],
                now=lambda: NOW,
            )
            preflight_cursor_after_second = preflight_cursor_path.read_text(encoding="utf-8").strip()

        self.assertEqual(len(first.emitted), 10)
        self.assertEqual(
            [request.record_type for request in first.emitted[:6]],
            ["post_gen_validate"] * 6,
        )
        self.assertEqual(
            [request.record_type for request in first.emitted[6:]],
            ["preflight_skip"] * 4,
        )
        self.assertFalse(preflight_cursor_exists_after_first)
        self.assertEqual(len(second.emitted), 2)
        self.assertEqual([request.record_type for request in second.emitted], ["preflight_skip", "preflight_skip"])
        self.assertEqual(preflight_cursor_after_second, "2026-05-01T14:15:00+09:00")

    def test_preflight_skip_payload_missing_fields_are_dropped_and_logged(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1"},
            clear=True,
        ):
            ledger_path = Path(tmpdir) / "preflight_skip_history.jsonl"
            cursor_path = Path(tmpdir) / "preflight_skip_cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            ledger_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            self._entry(
                                index=1,
                                source_url="https://example.com/article-bad-1",
                                source_url_hash="bad0001",
                                skip_reason="",
                            ),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            self._entry(
                                index=2,
                                source_url="",
                                source_url_hash="bad0002",
                                skip_reason="placeholder_body",
                            ),
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            events, fake_log_event = self._capture_log_events()

            with patch.object(scanner, "_log_event", side_effect=fake_log_event):
                result = scanner.scan_preflight_skip_history(
                    preflight_skip_history_path=ledger_path,
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    now=lambda: NOW,
                )

        self.assertEqual(result.emitted, [])
        self.assertEqual(
            result.skipped,
            [
                ("preflight_skip:bad0002:placeholder_body", "PREFLIGHT_SKIP_MISSING_SOURCE_URL"),
                ("", "PREFLIGHT_SKIP_MISSING_DEDUPE_KEY"),
            ],
        )
        self.assertTrue(any(event["event"] == "preflight_skip_history_scan_summary" for event in events))
        self.assertTrue(any(event["event"] == "preflight_skip_history_scan_zero_emitted" for event in events))

    def test_preflight_skip_flag_off_keeps_ledger_absent_and_scanner_silent(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"ENABLE_GEMINI_PREFLIGHT": "1"},
            clear=True,
        ):
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            preflight_history_path = Path(tmpdir) / "preflight_skip_history.jsonl"
            preflight_cursor_path = Path(tmpdir) / "preflight_skip_cursor.txt"
            cursor_path.write_text("2026-05-01T13:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            logger = logging.getLogger("test_preflight_fetcher_flag_off")
            logger.info = MagicMock()

            with patch.object(
                rss_fetcher, "PREFLIGHT_SKIP_HISTORY_DEFAULT_PATH", preflight_history_path
            ), patch.object(
                rss_fetcher, "_gcs_client", return_value=None
            ), patch.object(
                rss_fetcher,
                "_gemini_cache_lookup",
                side_effect=AssertionError("cache lookup should not run"),
            ), patch.object(
                rss_fetcher,
                "_request_gemini_strict_text",
                side_effect=AssertionError("Gemini request should not run"),
            ):
                text, telemetry = rss_fetcher._gemini_text_with_cache(
                    api_key="api-key",
                    prompt="PROMPT",
                    logger=logger,
                    attempt_limit=3,
                    min_chars=1,
                    source_url="https://example.com/preflight-skip-off",
                    content_text="本文A",
                    prompt_template_id="prompt-v1",
                    cache_manager=object(),
                    candidate_meta=self._candidate(existing_publish_same_source_url=True),
                    now=NOW,
                    log_label="test",
                )

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                preflight_skip_history_path=preflight_history_path,
                preflight_skip_cursor_path=preflight_cursor_path,
                fetch=lambda base, after: [],
                now=lambda: NOW,
            )

        self.assertEqual(text, "")
        self.assertFalse(telemetry["gemini_call_made"])
        self.assertFalse(preflight_history_path.exists())
        self.assertEqual(result.emitted, [])
        self.assertFalse(preflight_cursor_path.exists())
        self.assertFalse(queue_path.exists())


if __name__ == "__main__":
    unittest.main()
