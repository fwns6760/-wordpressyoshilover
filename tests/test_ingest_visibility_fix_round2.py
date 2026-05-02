from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import publish_notice_scanner as scanner


NOW = datetime(2026, 5, 2, 15, 0, tzinfo=scanner.JST)


def _read_jsonl_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class IngestVisibilityFixRound2Tests(unittest.TestCase):
    def _post(self, **overrides):
        payload = {
            "id": 901,
            "title": {"rendered": "レビュー待ち記事"},
            "excerpt": {"rendered": "<p>レビュー待ち記事の要約。</p>"},
            "content": {"rendered": "<p>本文1段落目。</p>"},
            "link": "https://yoshilover.com/draft-901/",
            "date": "2026-04-20T10:00:00+09:00",
            "status": "draft",
            "meta": {"article_subtype": "postgame"},
        }
        payload.update(overrides)
        return payload

    def _publish_post(self, **overrides):
        payload = {
            "id": 301,
            "title": {"rendered": "巨人が阪神に競り勝った"},
            "excerpt": {"rendered": "<p>巨人が阪神に競り勝った。終盤の継投と決勝打が焦点になった。</p>"},
            "content": {"rendered": "<p>本文1段落目。</p><p>本文2段落目。</p>"},
            "link": "https://yoshilover.com/post-301/",
            "date": "2026-05-02T13:00:00+09:00",
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

    def _preflight_entry(self, **overrides):
        payload = {
            "ts": NOW.isoformat(),
            "record_type": "preflight_skip",
            "skip_layer": "preflight",
            "source_url": "https://example.com/article-1",
            "source_url_hash": "hash0001",
            "content_hash": "body0001",
            "source_title": "元記事タイトル 1",
            "category": "試合速報",
            "article_subtype": "postgame",
            "source_name": "スポーツ報知",
            "source_type": "news",
            "skip_reason": "placeholder_body",
        }
        payload.update(overrides)
        return payload

    def _capture_log_events(self):
        events: list[dict[str, object]] = []

        def fake_log_event(event: str, **payload):
            events.append({"event": event, **payload})

        return events, fake_log_event

    def _emit_events(self, events: list[dict[str, object]]) -> list[dict[str, object]]:
        return [event for event in events if event["event"] == "ingest_visibility_fix_v1_emit"]

    def _serialize_requests(self, requests):
        return [
            {
                "post_id": request.post_id,
                "title": request.title,
                "canonical_url": request.canonical_url,
                "subtype": request.subtype,
                "publish_time_iso": request.publish_time_iso,
                "notice_kind": request.notice_kind,
                "subject_override": request.subject_override,
                "record_type": getattr(request, "record_type", None),
                "skip_layer": getattr(request, "skip_layer", None),
            }
            for request in requests
        ]

    def _run_guarded_scan(
        self,
        root: Path,
        *,
        guarded_entries: list[dict[str, object]],
        fetch_post_detail,
        env: dict[str, str] | None = None,
        history_payload: dict[str, object] | None = None,
        max_per_run: int | None = None,
    ):
        guarded_history_path = root / "guarded_publish_history.jsonl"
        guarded_cursor_path = root / "guarded_publish_history_cursor.txt"
        history_path = root / "history.json"
        queue_path = root / "queue.jsonl"
        guarded_history_path.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in guarded_entries),
            encoding="utf-8",
        )
        if history_payload is not None:
            history_path.write_text(json.dumps(history_payload, ensure_ascii=False) + "\n", encoding="utf-8")

        events, fake_log_event = self._capture_log_events()
        with patch.dict("os.environ", env or {}, clear=True), patch.object(
            scanner,
            "_log_event",
            side_effect=fake_log_event,
        ):
            result = scanner.scan_guarded_publish_history(
                guarded_publish_history_path=guarded_history_path,
                cursor_path=guarded_cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                fetch_post_detail=fetch_post_detail,
                now=lambda: NOW,
                max_per_run=max_per_run,
            )

        return result, queue_path, events

    def _run_preflight_scan(
        self,
        root: Path,
        *,
        entries: list[dict[str, object]],
        env: dict[str, str] | None = None,
        queue_path: Path | None = None,
    ):
        preflight_path = root / "preflight_skip_history.jsonl"
        cursor_path = root / "preflight_skip_cursor.txt"
        history_path = root / "history.json"
        resolved_queue_path = queue_path or (root / "queue.jsonl")
        preflight_path.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
            encoding="utf-8",
        )

        events, fake_log_event = self._capture_log_events()
        with patch.dict("os.environ", env or {}, clear=True), patch.object(
            scanner,
            "_log_event",
            side_effect=fake_log_event,
        ):
            result = scanner.scan_preflight_skip_history(
                preflight_skip_history_path=preflight_path,
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=resolved_queue_path,
                now=lambda: NOW,
            )

        return result, resolved_queue_path, events

    def test_scanner_malformed_payload_visible_when_flag_on(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result, queue_path, events = self._run_guarded_scan(
                Path(tmpdir),
                guarded_entries=[self._guarded_entry(post_id=991)],
                fetch_post_detail=lambda base, post_id: (_ for _ in ()).throw(RuntimeError("boom")),
                env={"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"},
            )
            rows = _read_jsonl_rows(queue_path)

        self.assertEqual(result.emitted, [])
        self.assertEqual(result.skipped, [(991, "REVIEW_POST_DETAIL_ERROR")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "REVIEW_POST_DETAIL_ERROR")
        self.assertEqual(rows[0]["record_type"], "scanner_internal_skip")
        self.assertEqual(rows[0]["skip_layer"], "scanner_malformed_payload")
        self.assertEqual(rows[0]["notice_kind"], "post_gen_validate")
        self.assertEqual(rows[0]["source_path"], "src/publish_notice_scanner.py")
        self.assertEqual(rows[0]["source_post_id"], 991)
        self.assertTrue(str(rows[0]["candidate_id"]).startswith("scanner_internal_skip:post:991:"))
        emit_events = self._emit_events(events)
        self.assertEqual(len(emit_events), 1)
        self.assertEqual(emit_events[0]["path"], "scanner_malformed_payload")
        self.assertEqual(emit_events[0]["reason"], "REVIEW_POST_DETAIL_ERROR")
        self.assertEqual(emit_events[0]["source_post_id"], 991)
        self.assertEqual(emit_events[0]["candidate_id"], rows[0]["candidate_id"])

    def test_scanner_normal_payload_unchanged_when_flag_on(self):
        def run_case(env: dict[str, str]):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                cursor_path = root / "cursor.txt"
                history_path = root / "history.json"
                queue_path = root / "queue.jsonl"
                guarded_history_path = root / "guarded_publish_history.jsonl"
                guarded_cursor_path = root / "guarded_cursor.txt"
                cursor_path.write_text("2026-05-02T09:00:00+09:00\n", encoding="utf-8")
                history_path.write_text("{}\n", encoding="utf-8")
                guarded_history_path.write_text("", encoding="utf-8")
                events, fake_log_event = self._capture_log_events()

                with patch.dict("os.environ", env, clear=True), patch.object(
                    scanner,
                    "_log_event",
                    side_effect=fake_log_event,
                ):
                    result = scanner.scan(
                        cursor_path=cursor_path,
                        history_path=history_path,
                        queue_path=queue_path,
                        guarded_publish_history_path=guarded_history_path,
                        guarded_cursor_path=guarded_cursor_path,
                        fetch=lambda base, after: [self._publish_post()],
                        now=lambda: NOW,
                    )

                return result, _read_jsonl_rows(queue_path), events

        off_result, off_rows, off_events = run_case({})
        on_result, on_rows, on_events = run_case({"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"})

        self.assertEqual(self._serialize_requests(off_result.emitted), self._serialize_requests(on_result.emitted))
        self.assertEqual(off_result.skipped, on_result.skipped)
        self.assertEqual(off_rows, on_rows)
        self.assertEqual(len(on_rows), 1)
        self.assertEqual(on_rows[0]["post_id"], 301)
        self.assertEqual(self._emit_events(off_events), [])
        self.assertEqual(self._emit_events(on_events), [])

    def test_flag_off_baseline_malformed_silent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result, queue_path, events = self._run_preflight_scan(
                Path(tmpdir),
                entries=[
                    self._preflight_entry(
                        source_url="",
                        source_url_hash="hash0009",
                        skip_reason="placeholder_body",
                    )
                ],
                env={},
            )

        self.assertEqual(result.emitted, [])
        self.assertEqual(
            result.skipped,
            [("preflight_skip:hash0009:placeholder_body", "PREFLIGHT_SKIP_MISSING_SOURCE_URL")],
        )
        self.assertEqual(_read_jsonl_rows(queue_path), [])
        self.assertEqual(self._emit_events(events), [])

    def test_mail_volume_unchanged_when_flag_off(self):
        def fetch_post_detail(base, post_id):
            if int(post_id) == 992:
                raise RuntimeError("boom")
            return self._post(
                id=post_id,
                status="draft",
                link=f"https://yoshilover.com/draft-{post_id}/",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result, queue_path, events = self._run_guarded_scan(
                Path(tmpdir),
                guarded_entries=[
                    self._guarded_entry(post_id=991, ts="2026-05-02T14:00:00+09:00"),
                    self._guarded_entry(post_id=992, ts="2026-05-02T14:30:00+09:00"),
                ],
                fetch_post_detail=fetch_post_detail,
                env={},
            )
            rows = _read_jsonl_rows(queue_path)

        self.assertEqual([request.post_id for request in result.emitted], [991])
        self.assertEqual(result.skipped, [(992, "REVIEW_POST_DETAIL_ERROR")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["post_id"], 991)
        self.assertEqual(rows[0]["reason"], "backlog_only")
        self.assertEqual(self._emit_events(events), [])

    def test_existing_review_path_unchanged_in_both_modes(self):
        def run_case(env: dict[str, str]):
            with tempfile.TemporaryDirectory() as tmpdir:
                result, queue_path, events = self._run_guarded_scan(
                    Path(tmpdir),
                    guarded_entries=[
                        self._guarded_entry(
                            post_id=902,
                            judgment="review",
                            hold_reason="cleanup_required",
                        )
                    ],
                    fetch_post_detail=lambda base, post_id: self._post(
                        id=post_id,
                        status="draft",
                        title={"rendered": "レビュー待ち記事"},
                    ),
                    env=env,
                )
                return result, _read_jsonl_rows(queue_path), events

        off_result, off_rows, off_events = run_case({})
        on_result, on_rows, on_events = run_case({"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"})

        self.assertEqual(self._serialize_requests(off_result.emitted), self._serialize_requests(on_result.emitted))
        self.assertEqual(off_result.skipped, on_result.skipped)
        self.assertEqual(off_rows, on_rows)
        self.assertEqual(len(on_rows), 1)
        self.assertTrue(str(on_rows[0]["subject"]).startswith("【要review】"))
        self.assertEqual(self._emit_events(off_events), [])
        self.assertEqual(self._emit_events(on_events), [])

    def test_existing_old_candidate_dedup_unchanged_in_both_modes(self):
        def run_case(flag_on: bool):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                ledger_path = root / "publish_notice_old_candidate_once.json"
                ledger_payload = {"901": "2026-05-01T10:00:00+09:00"}
                ledger_path.write_text(json.dumps(ledger_payload, ensure_ascii=False) + "\n", encoding="utf-8")
                env = {
                    "ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE": "1",
                    "PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS": "3",
                    "PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_PATH": str(ledger_path),
                }
                if flag_on:
                    env["ENABLE_INGEST_VISIBILITY_FIX_V1"] = "1"
                result, queue_path, events = self._run_guarded_scan(
                    root,
                    guarded_entries=[self._guarded_entry(post_id=901)],
                    fetch_post_detail=lambda base, post_id: self._post(
                        id=post_id,
                        status="draft",
                        date="2026-04-20T10:00:00+09:00",
                    ),
                    env=env,
                )
                ledger_after = json.loads(ledger_path.read_text(encoding="utf-8"))
                return result, _read_jsonl_rows(queue_path), events, ledger_after

        off_result, off_rows, off_events, off_ledger = run_case(False)
        on_result, on_rows, on_events, on_ledger = run_case(True)

        self.assertEqual(off_result.emitted, [])
        self.assertEqual(off_result.skipped, [(901, "OLD_CANDIDATE_PERMANENT_DEDUP")])
        self.assertEqual(off_result.skipped, on_result.skipped)
        self.assertEqual(off_rows, [])
        self.assertEqual(on_rows, [])
        self.assertEqual(off_ledger, {"901": "2026-05-01T10:00:00+09:00"})
        self.assertEqual(off_ledger, on_ledger)
        self.assertEqual(self._emit_events(off_events), [])
        self.assertEqual(self._emit_events(on_events), [])

    def test_existing_ttl_prune_unchanged_in_both_modes(self):
        def run_case(flag_on: bool):
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                ledger_path = root / "publish_notice_old_candidate_once.json"
                ledger_path.write_text(
                    json.dumps({"901": {"ts": "2026-04-20T10:00:00+09:00"}}, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                env = {
                    "ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL": "1",
                    "PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_TTL_DAYS": "7",
                    "PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_PATH": str(ledger_path),
                }
                if flag_on:
                    env["ENABLE_INGEST_VISIBILITY_FIX_V1"] = "1"
                result, queue_path, events = self._run_guarded_scan(
                    root,
                    guarded_entries=[],
                    fetch_post_detail=lambda base, post_id: self.fail("fetch_post_detail should not be called"),
                    env=env,
                    max_per_run=0,
                )
                ledger_after = json.loads(ledger_path.read_text(encoding="utf-8"))
                ttl_events = [event for event in events if event["event"] == "permanent_dedup_ttl_prune"]
                return result, _read_jsonl_rows(queue_path), ttl_events, self._emit_events(events), ledger_after

        off_result, off_rows, off_ttl_events, off_emit_events, off_ledger = run_case(False)
        on_result, on_rows, on_ttl_events, on_emit_events, on_ledger = run_case(True)

        self.assertEqual(off_result.old_candidate_ledger_after, {})
        self.assertEqual(off_result.old_candidate_ledger_after, on_result.old_candidate_ledger_after)
        self.assertEqual(off_rows, [])
        self.assertEqual(on_rows, [])
        self.assertEqual(off_ttl_events, on_ttl_events)
        self.assertEqual(off_ttl_events[0]["count"], 1)
        self.assertEqual(off_emit_events, [])
        self.assertEqual(on_emit_events, [])
        self.assertEqual(off_ledger, {})
        self.assertEqual(off_ledger, on_ledger)

    def test_multiple_malformed_payloads_each_emit_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            queue_path = root / "queue.jsonl"
            guarded_history_path = root / "guarded_publish_history.jsonl"
            guarded_cursor_path = root / "guarded_cursor.txt"
            preflight_path = root / "preflight_skip_history.jsonl"
            preflight_cursor_path = root / "preflight_cursor.txt"
            history_path = root / "history.json"
            guarded_history_path.write_text(
                "".join(
                    json.dumps(entry, ensure_ascii=False) + "\n"
                    for entry in [
                        self._guarded_entry(post_id=1001, ts="2026-05-02T14:01:00+09:00"),
                        self._guarded_entry(post_id=1002, ts="2026-05-02T14:02:00+09:00"),
                    ]
                ),
                encoding="utf-8",
            )
            preflight_path.write_text(
                "".join(
                    json.dumps(entry, ensure_ascii=False) + "\n"
                    for entry in [
                        self._preflight_entry(
                            source_url="",
                            source_url_hash="",
                            skip_reason="placeholder_body",
                        ),
                        self._preflight_entry(
                            source_url="",
                            source_url_hash="hash1004",
                            skip_reason="placeholder_body",
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            def fetch_post_detail(base, post_id):
                if int(post_id) == 1001:
                    raise RuntimeError("boom")
                return None

            events, fake_log_event = self._capture_log_events()
            with patch.dict("os.environ", {"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"}, clear=True), patch.object(
                scanner,
                "_log_event",
                side_effect=fake_log_event,
            ):
                guarded_result = scanner.scan_guarded_publish_history(
                    guarded_publish_history_path=guarded_history_path,
                    cursor_path=guarded_cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    fetch_post_detail=fetch_post_detail,
                    now=lambda: NOW,
                )
                preflight_result = scanner.scan_preflight_skip_history(
                    preflight_skip_history_path=preflight_path,
                    cursor_path=preflight_cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    now=lambda: NOW,
                )
            rows = _read_jsonl_rows(queue_path)

        self.assertEqual(guarded_result.skipped, [(1002, "REVIEW_POST_MISSING"), (1001, "REVIEW_POST_DETAIL_ERROR")])
        self.assertEqual(
            preflight_result.skipped,
            [
                ("preflight_skip:hash1004:placeholder_body", "PREFLIGHT_SKIP_MISSING_SOURCE_URL"),
                ("", "PREFLIGHT_SKIP_MISSING_DEDUPE_KEY"),
            ],
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            {row["reason"] for row in rows},
            {
                "REVIEW_POST_DETAIL_ERROR",
                "REVIEW_POST_MISSING",
                "PREFLIGHT_SKIP_MISSING_DEDUPE_KEY",
                "PREFLIGHT_SKIP_MISSING_SOURCE_URL",
            },
        )
        candidate_ids = [str(row["candidate_id"]) for row in rows]
        self.assertEqual(len(candidate_ids), len(set(candidate_ids)))
        emit_events = self._emit_events(events)
        self.assertEqual(len(emit_events), 4)
        self.assertTrue(all(event["path"] == "scanner_malformed_payload" for event in emit_events))


if __name__ == "__main__":
    unittest.main()
