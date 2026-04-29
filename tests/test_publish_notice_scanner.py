import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import publish_notice_scanner as scanner


NOW = datetime(2026, 4, 24, 12, 0, tzinfo=scanner.JST)


class PublishNoticeScannerTests(unittest.TestCase):
    def _post(self, **overrides):
        payload = {
            "id": 101,
            "title": {"rendered": "巨人が阪神に競り勝った"},
            "excerpt": {"rendered": "<p>巨人が阪神に競り勝った。終盤の継投と決勝打が焦点になった。</p>"},
            "content": {"rendered": "<p>本文1段落目。</p><p>本文2段落目。</p>"},
            "link": "https://yoshilover.com/post-101/",
            "date": "2026-04-24T10:00:00+09:00",
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

    def test_scan_initial_run_sets_cursor_to_now_and_emits_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            fetch_calls = []

            def fetch(base_url: str, after_iso: str):
                fetch_calls.append((base_url, after_iso))
                return []

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=fetch,
                now=lambda: NOW,
            )

            self.assertEqual(result.emitted, [])
            self.assertEqual(result.skipped, [])
            self.assertIsNone(result.cursor_before)
            self.assertEqual(result.cursor_after, NOW.isoformat())
            self.assertEqual(cursor_path.read_text(encoding="utf-8").strip(), NOW.isoformat())
            self.assertEqual(fetch_calls, [])
            self.assertFalse(queue_path.exists())

    def test_scan_with_existing_cursor_emits_two_requests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            def fetch(base_url: str, after_iso: str):
                self.assertEqual(base_url, "https://custom.example/wp-json/wp/v2")
                self.assertEqual(after_iso, "2026-04-24T08:00:00+09:00")
                return [
                    self._post(id=201, link="https://yoshilover.com/post-201/", date="2026-04-24T09:00:00+09:00"),
                    self._post(
                        id=202,
                        title={"rendered": "巨人の公示情報"},
                        meta={"article_subtype": "fact_notice"},
                        link="https://yoshilover.com/post-202/",
                        date="2026-04-24T09:30:00+09:00",
                    ),
                ]

            result = scanner.scan(
                wp_api_base="https://custom.example/wp-json/wp/v2",
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=fetch,
                now=lambda: NOW,
            )

        self.assertEqual(len(result.emitted), 2)
        self.assertEqual(result.emitted[0].post_id, 201)
        self.assertEqual(result.emitted[0].subtype, "postgame")
        self.assertEqual(result.emitted[1].subtype, "fact_notice")
        self.assertEqual(result.cursor_before, "2026-04-24T08:00:00+09:00")
        self.assertEqual(result.cursor_after, "2026-04-24T09:30:00+09:00")

    def test_scan_skips_recent_duplicate_from_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text(
                json.dumps({"301": "2026-04-24T11:00:00+09:00"}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [self._post(id=301, date="2026-04-24T11:30:00+09:00")],
                now=lambda: NOW,
            )

        self.assertEqual(result.emitted, [])
        self.assertEqual(result.skipped, [(301, "RECENT_DUPLICATE")])
        self.assertFalse(queue_path.exists())

    def test_scan_prunes_history_entries_older_than_24_hours(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text(
                json.dumps(
                    {
                        "401": "2026-04-23T08:59:59+09:00",
                        "402": "2026-04-24T10:00:00+09:00",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [self._post(id=401, date="2026-04-24T11:00:00+09:00")],
                now=lambda: NOW,
            )

            self.assertEqual([item.post_id for item in result.emitted], [401])
            history = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertIn("401", history)
            self.assertIn("402", history)

    def test_scan_advances_cursor_to_latest_post_date_for_any_fetch_order(self):
        cases = [
            (
                "ascending",
                [
                    self._post(id=501, date="2026-04-24T09:00:00+09:00"),
                    self._post(id=502, date="2026-04-24T10:30:00+09:00"),
                ],
            ),
            (
                "descending",
                [
                    self._post(id=503, date="2026-04-24T10:30:00+09:00"),
                    self._post(id=504, date="2026-04-24T09:00:00+09:00"),
                ],
            ),
        ]

        for label, posts in cases:
            with self.subTest(order=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    cursor_path = Path(tmpdir) / "cursor.txt"
                    history_path = Path(tmpdir) / "history.json"
                    queue_path = Path(tmpdir) / "queue.jsonl"
                    cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
                    history_path.write_text("{}\n", encoding="utf-8")

                    result = scanner.scan(
                        cursor_path=cursor_path,
                        history_path=history_path,
                        queue_path=queue_path,
                        fetch=lambda base, after, items=posts: list(items),
                        now=lambda: NOW,
                    )

                self.assertEqual(result.cursor_after, "2026-04-24T10:30:00+09:00")

    def test_scan_with_empty_fetch_result_advances_cursor_to_now(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [],
                now=lambda: NOW,
            )

            self.assertEqual(result.emitted, [])
            self.assertEqual(result.cursor_after, NOW.isoformat())
            self.assertEqual(cursor_path.read_text(encoding="utf-8").strip(), NOW.isoformat())

    def test_scan_resolves_wp_api_base_from_argument_env_and_default(self):
        cases = [
            ("arg", "https://arg.example/wp-json/wp/v2", {}, "https://arg.example/wp-json/wp/v2"),
            ("env", None, {"WP_API_BASE": "https://env.example/wp-json/wp/v2"}, "https://env.example/wp-json/wp/v2"),
            ("default", None, {}, "https://yoshilover.com/wp-json/wp/v2"),
        ]

        for label, wp_api_base, env_map, expected in cases:
            with self.subTest(source=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    cursor_path = Path(tmpdir) / "cursor.txt"
                    history_path = Path(tmpdir) / "history.json"
                    queue_path = Path(tmpdir) / "queue.jsonl"
                    cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
                    history_path.write_text("{}\n", encoding="utf-8")
                    captured = []

                    def fetch(base_url: str, after_iso: str):
                        captured.append((base_url, after_iso))
                        return []

                    with patch.dict("os.environ", env_map, clear=True):
                        scanner.scan(
                            wp_api_base=wp_api_base,
                            cursor_path=cursor_path,
                            history_path=history_path,
                            queue_path=queue_path,
                            fetch=fetch,
                            now=lambda: NOW,
                        )

                self.assertEqual(captured[0][0], expected)

    def test_scan_uses_excerpt_summary_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [
                    self._post(
                        id=601,
                        excerpt={"rendered": "<p>抜粋1。</p><p>抜粋2。</p>"},
                        content={"rendered": "<p>本文1。</p><p>本文2。</p>"},
                    )
                ],
                now=lambda: NOW,
            )

        self.assertEqual(result.emitted[0].summary, "抜粋1。")

    def test_scan_falls_back_to_content_summary_when_excerpt_is_blank(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [
                    self._post(
                        id=602,
                        excerpt={"rendered": " "},
                        content={"rendered": "<p>本文1。</p><p>本文2。</p>"},
                    )
                ],
                now=lambda: NOW,
            )

        self.assertEqual(result.emitted[0].summary, "本文1。")

    def test_scan_returns_none_summary_when_excerpt_and_content_are_blank(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [
                    self._post(
                        id=603,
                        excerpt={"rendered": " "},
                        content={"rendered": " "},
                    )
                ],
                now=lambda: NOW,
            )

        self.assertIsNone(result.emitted[0].summary)

    def test_scan_appends_queue_entries_for_emitted_posts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [
                    self._post(id=701, title={"rendered": "公開通知A"}),
                    self._post(id=702, title={"rendered": "公開通知B"}, date="2026-04-24T10:30:00+09:00"),
                ],
                now=lambda: NOW,
            )

            rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["post_id"] for row in rows], [701, 702])
            self.assertEqual([row["status"] for row in rows], ["queued", "queued"])

    def test_scan_deduplicates_same_post_within_single_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            cursor_path.write_text("2026-04-24T08:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch=lambda base, after: [
                    self._post(id=801, date="2026-04-24T09:00:00+09:00"),
                    self._post(id=801, date="2026-04-24T09:30:00+09:00"),
                ],
                now=lambda: NOW,
            )

        self.assertEqual([item.post_id for item in result.emitted], [801])
        self.assertEqual(result.skipped, [(801, "RECENT_DUPLICATE")])

    def test_extract_subtype_from_rest_article_subtype(self):
        subtype = scanner._extract_subtype(
            self._post(meta={"article_subtype": "lineup"}, subtype="program", article_subtype="notice")
        )

        self.assertEqual(subtype, "lineup")

    def test_extract_subtype_from_rest_subtype(self):
        subtype = scanner._extract_subtype(self._post(meta={}, article_subtype="", subtype="program"))

        self.assertEqual(subtype, "program")

    def test_extract_subtype_fallback_lineup(self):
        subtype = scanner._extract_subtype(self._post(title={"rendered": "スタメン"}, meta={}, article_subtype="", subtype=""))

        self.assertEqual(subtype, "lineup")

    def test_extract_subtype_fallback_postgame(self):
        subtype = scanner._extract_subtype(
            self._post(title={"rendered": "巨人 7-2 勝利"}, meta={}, article_subtype="", subtype="")
        )

        self.assertEqual(subtype, "postgame")

    def test_extract_subtype_fallback_farm(self):
        subtype = scanner._extract_subtype(
            self._post(title={"rendered": "巨人二軍 4-0"}, meta={}, article_subtype="", subtype="")
        )

        self.assertEqual(subtype, "farm")

    def test_extract_subtype_fallback_notice_injury(self):
        subtype = scanner._extract_subtype(
            self._post(title={"rendered": "○○が抹消"}, meta={}, article_subtype="", subtype="")
        )

        self.assertEqual(subtype, "notice")

    def test_extract_subtype_fallback_notice_recovery(self):
        subtype = scanner._extract_subtype(
            self._post(title={"rendered": "○○が復帰"}, meta={}, article_subtype="", subtype="")
        )

        self.assertEqual(subtype, "notice")

    def test_extract_subtype_fallback_program(self):
        subtype = scanner._extract_subtype(
            self._post(title={"rendered": "番組情報"}, meta={}, article_subtype="", subtype="")
        )

        self.assertEqual(subtype, "program")

    def test_extract_subtype_fallback_default(self):
        subtype = scanner._extract_subtype(
            self._post(title={"rendered": "雑感"}, meta={}, article_subtype="", subtype="")
        )

        self.assertEqual(subtype, "default")

    def test_extract_subtype_fallback_priority_lineup_over_postgame(self):
        subtype = scanner._extract_subtype(
            self._post(title={"rendered": "スタメン発表 試合結果も速報"}, meta={}, article_subtype="", subtype="")
        )

        self.assertEqual(subtype, "lineup")

    def test_scan_guarded_publish_history_queues_backlog_only_yellow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_history_path.write_text(
                json.dumps(self._guarded_entry(post_id=901), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=lambda base, post_id: self._post(
                    id=post_id,
                    status="draft",
                    link=f"https://yoshilover.com/draft-{post_id}/",
                ),
                now=lambda: NOW,
            )
            rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([request.post_id for request in result.emitted], [901])
        self.assertEqual(result.emitted[0].notice_kind, "review_hold")
        self.assertFalse(result.emitted[0].is_backlog)
        self.assertTrue(str(result.emitted[0].subject_override).startswith("【要確認(古い候補)】"))
        self.assertEqual(rows[0]["post_id"], 901)
        self.assertEqual(rows[0]["reason"], "backlog_only")
        self.assertTrue(rows[0]["subject"].startswith("【要確認(古い候補)】"))

    def test_scan_guarded_publish_history_queues_cleanup_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_history_path.write_text(
                json.dumps(
                    self._guarded_entry(
                        post_id=902,
                        judgment="review",
                        hold_reason="cleanup_required",
                    ),
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=lambda base, post_id: self._post(
                    id=post_id,
                    status="draft",
                    title={"rendered": "レビュー待ち記事"},
                ),
                now=lambda: NOW,
            )
            rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([request.post_id for request in result.emitted], [902])
        self.assertTrue(str(result.emitted[0].subject_override).startswith("【要review】"))
        self.assertEqual(rows[0]["reason"], "cleanup_required")
        self.assertTrue(rows[0]["subject"].startswith("【要review】"))

    def test_scan_guarded_publish_history_excludes_red_hard_stop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_history_path.write_text(
                json.dumps(
                    self._guarded_entry(
                        post_id=903,
                        judgment="red",
                        hold_reason="hard_stop_injury_death",
                    ),
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=lambda base, post_id: self.fail("fetch_post_detail should not be called"),
                now=lambda: NOW,
            )

        self.assertEqual(result.emitted, [])
        self.assertEqual(result.skipped, [(903, "REVIEW_EXCLUDED")])
        self.assertFalse(queue_path.exists())

    def test_scan_guarded_publish_history_excludes_same_source_duplicate_hold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_history_path.write_text(
                json.dumps(
                    self._guarded_entry(
                        post_id=904,
                        judgment="review",
                        hold_reason="review_duplicate_candidate_same_source_url",
                    ),
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=lambda base, post_id: self.fail("fetch_post_detail should not be called"),
                now=lambda: NOW,
            )

        self.assertEqual(result.emitted, [])
        self.assertEqual(result.skipped, [(904, "REVIEW_EXCLUDED")])
        self.assertFalse(queue_path.exists())

    def test_scan_guarded_publish_history_skips_recent_notified_post(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            guarded_history_path.write_text(
                json.dumps(self._guarded_entry(post_id=905), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            history_path.write_text(
                json.dumps({"905": NOW.isoformat()}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=lambda base, post_id: self.fail("fetch_post_detail should not be called"),
                now=lambda: NOW,
            )

        self.assertEqual(result.emitted, [])
        self.assertEqual(result.skipped, [(905, "REVIEW_RECENT_DUPLICATE")])
        self.assertFalse(queue_path.exists())

    def test_scan_guarded_publish_history_respects_max_per_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guarded_history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            entries = [
                self._guarded_entry(post_id=906, ts="2026-04-24T09:00:00+09:00"),
                self._guarded_entry(post_id=907, ts="2026-04-24T10:00:00+09:00"),
                self._guarded_entry(post_id=908, ts="2026-04-24T11:00:00+09:00"),
            ]
            guarded_history_path.write_text(
                "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
                encoding="utf-8",
            )

            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=lambda base, post_id: self._post(id=post_id, status="draft"),
                max_per_run=2,
                now=lambda: NOW,
            )
            rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([request.post_id for request in result.emitted], [908, 907])
        self.assertEqual([row["post_id"] for row in rows], [908, 907])


if __name__ == "__main__":
    unittest.main()
