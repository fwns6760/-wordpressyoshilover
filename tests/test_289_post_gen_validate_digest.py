import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src import publish_notice_email_sender as sender
from src import publish_notice_scanner as scanner


NOW = datetime(2026, 5, 2, 19, 35, tzinfo=scanner.JST)


class PostGenValidateDigestTests(unittest.TestCase):
    def _request(
        self,
        index: int,
        *,
        title: str | None = None,
        skip_reason: str = "weak_subject_title:related_info_escape",
        skip_reason_label: str | None = None,
    ) -> scanner.PublishNoticeRequest:
        resolved_title = title or f"元記事タイトル {index}"
        resolved_label = skip_reason_label or scanner._post_gen_validate_reason_label(skip_reason)
        return scanner.PublishNoticeRequest(
            post_id=f"post_gen_validate:hash{index:04d}:{skip_reason}",
            title=resolved_title,
            canonical_url=f"https://example.com/article-{index}",
            subtype="postgame",
            publish_time_iso=NOW.isoformat(),
            summary=None,
            is_backlog=False,
            notice_kind="post_gen_validate",
            subject_override=f"【要review｜post_gen_validate】{resolved_title} | YOSHILOVER",
            source_title=resolved_title,
            generated_title=f"生成タイトル {index}",
            skip_reason=skip_reason,
            skip_reason_label=resolved_label,
            source_url_hash=f"hash{index:04d}",
            category="試合速報",
            record_type="post_gen_validate",
            skip_layer="post_gen_validate",
            fail_axes=(skip_reason,),
        )

    def _old_candidate_request(self, index: int) -> scanner.PublishNoticeRequest:
        return scanner.PublishNoticeRequest(
            post_id=f"old_candidate:{index}",
            title=f"old candidate {index}",
            canonical_url=f"https://example.com/old/{index}",
            subtype="postgame",
            publish_time_iso=NOW.isoformat(),
            summary=None,
            is_backlog=False,
            notice_kind="review_hold",
            subject_override=f"【要確認(古い候補)】old candidate {index} | YOSHILOVER",
        )

    def _write_queue_rows(self, path: Path, rows: list[dict[str, object]]) -> None:
        path.write_text(
            "".join(f"{json.dumps(row, ensure_ascii=False)}\n" for row in rows),
            encoding="utf-8",
        )

    def _sent_row(
        self,
        *,
        subject: str,
        post_id: str,
        minutes_ago: int,
    ) -> dict[str, object]:
        sent_at = (NOW - timedelta(minutes=minutes_ago)).isoformat()
        return {
            "status": "sent",
            "reason": None,
            "subject": subject,
            "recipients": ["notice@example.com"],
            "post_id": post_id,
            "recorded_at": sent_at,
            "sent_at": sent_at,
            "notice_kind": "per_post",
        }

    def _digest_state(
        self,
        queue_path: Path,
        *,
        env: dict[str, str] | None = None,
    ) -> scanner.PublishNotice289DigestState:
        values = {"ENABLE_289_POST_GEN_VALIDATE_DIGEST": "1"}
        if env:
            values.update(env)
        with patch.dict("os.environ", values, clear=True):
            return scanner.evaluate_289_digest_state(queue_path=queue_path, now=NOW)

    def test_289_digest_state_calculation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            digest_subject = scanner._build_post_gen_validate_digest_subject(
                count=4,
                representative_subject="digest representative",
            )
            self._write_queue_rows(
                queue_path,
                [
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 1 | YOSHILOVER",
                        post_id="post_gen_validate:hash0001:weak_subject_title:related_info_escape",
                        minutes_ago=10,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 2 | YOSHILOVER",
                        post_id="post_gen_validate:hash0002:weak_subject_title:related_info_escape",
                        minutes_ago=55,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】old mail | YOSHILOVER",
                        post_id="post_gen_validate:hash0003:weak_subject_title:related_info_escape",
                        minutes_ago=90,
                    ),
                    self._sent_row(
                        subject=digest_subject,
                        post_id="post_gen_validate_digest:window-a",
                        minutes_ago=5,
                    ),
                ],
            )

            state = self._digest_state(queue_path)

        self.assertTrue(state.enabled)
        self.assertEqual(state.hour_count, 2)
        self.assertEqual(state.keep_per_hour, 3)
        self.assertTrue(state.digest_already_sent)

    def test_keep_under_per_hour_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            queue_path.write_text("", encoding="utf-8")
            state = self._digest_state(queue_path)
            requests = [self._request(1), self._request(2)]

            transformed, updated_state = scanner.apply_289_digest(requests, digest_state=state)

        self.assertEqual([request.post_id for request in transformed], [request.post_id for request in requests])
        self.assertEqual(updated_state.kept_count, 2)
        self.assertEqual(updated_state.digested_count, 0)
        self.assertFalse(updated_state.digest_emitted)

    def test_digest_overflow_above_per_hour_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_queue_rows(
                queue_path,
                [
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 1 | YOSHILOVER",
                        post_id="post_gen_validate:hash0001:weak_subject_title:related_info_escape",
                        minutes_ago=5,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 2 | YOSHILOVER",
                        post_id="post_gen_validate:hash0002:weak_subject_title:related_info_escape",
                        minutes_ago=15,
                    ),
                ],
            )
            state = self._digest_state(queue_path)
            requests = [self._request(10), self._request(11), self._request(12)]

            transformed, updated_state = scanner.apply_289_digest(requests, digest_state=state)

        self.assertEqual(len(transformed), 2)
        self.assertEqual(transformed[0].post_id, requests[0].post_id)
        self.assertEqual(transformed[1].record_type, "post_gen_validate_digest")
        self.assertEqual(updated_state.kept_count, 1)
        self.assertEqual(updated_state.digested_count, 2)
        self.assertTrue(updated_state.digest_emitted)

    def test_digest_subject_includes_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_queue_rows(
                queue_path,
                [
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 1 | YOSHILOVER",
                        post_id="post_gen_validate:hash0001:weak_subject_title:related_info_escape",
                        minutes_ago=5,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 2 | YOSHILOVER",
                        post_id="post_gen_validate:hash0002:weak_subject_title:related_info_escape",
                        minutes_ago=15,
                    ),
                ],
            )
            state = self._digest_state(queue_path)
            transformed, _ = scanner.apply_289_digest(
                [self._request(20), self._request(21), self._request(22)],
                digest_state=state,
            )

        digest_request = transformed[1]
        self.assertEqual(digest_request.subject_override, "【要review｜post_gen_validate digest｜2件】元記事タイトル 21 | YOSHILOVER")

    def test_digest_body_preserves_titles_post_ids_reasons(self):
        state = scanner.PublishNotice289DigestState(
            enabled=True,
            hour_count=3,
            keep_per_hour=3,
            window_start_iso=(NOW - timedelta(hours=1)).isoformat(),
            window_end_iso=NOW.isoformat(),
        )
        transformed, _ = scanner.apply_289_digest(
            [self._request(31), self._request(32)],
            digest_state=state,
        )

        digest_request = transformed[0]
        body = sender.build_body_text(digest_request)

        self.assertIn("[post_gen_validate:hash0031:weak_subject_title:related_info_escape] 元記事タイトル 31", body)
        self.assertIn("[post_gen_validate:hash0032:weak_subject_title:related_info_escape] 元記事タイトル 32", body)
        self.assertIn("理由: タイトルが『関連情報』『発言ポイント』だけで、人名や文脈を拾えなかったため / source_url_hash: hash0031", body)
        self.assertIn("理由: タイトルが『関連情報』『発言ポイント』だけで、人名や文脈を拾えなかったため / source_url_hash: hash0032", body)
        self.assertIn("url: https://example.com/article-31", body)
        self.assertIn("url: https://example.com/article-32", body)

    def test_digest_defers_overflow_when_window_already_has_digest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_queue_rows(
                queue_path,
                [
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 1 | YOSHILOVER",
                        post_id="post_gen_validate:hash0001:weak_subject_title:related_info_escape",
                        minutes_ago=10,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 2 | YOSHILOVER",
                        post_id="post_gen_validate:hash0002:weak_subject_title:related_info_escape",
                        minutes_ago=20,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 3 | YOSHILOVER",
                        post_id="post_gen_validate:hash0003:weak_subject_title:related_info_escape",
                        minutes_ago=30,
                    ),
                    self._sent_row(
                        subject=scanner._build_post_gen_validate_digest_subject(
                            count=2,
                            representative_subject="digest representative",
                        ),
                        post_id="post_gen_validate_digest:window-a",
                        minutes_ago=5,
                    ),
                ],
            )
            state = self._digest_state(queue_path)
            transformed, updated_state = scanner.apply_289_digest(
                [self._request(41), self._request(42)],
                digest_state=state,
            )

        self.assertEqual(transformed, [])
        self.assertEqual(updated_state.deferred_count, 2)
        self.assertEqual(
            updated_state.deferred_post_ids,
            (
                "post_gen_validate:hash0041:weak_subject_title:related_info_escape",
                "post_gen_validate:hash0042:weak_subject_title:related_info_escape",
            ),
        )
        self.assertFalse(updated_state.digest_emitted)

    def test_24h_budget_governor_runs_before_289_digest(self):
        budget_state = scanner.PublishNotice24hBudgetState(
            enabled=True,
            cumulative=80,
            projected_cumulative=80,
            limit=100,
            soft_threshold=80,
            hard_threshold=95,
            soft_breach=True,
            hard_breach=False,
        )
        requests = [
            self._old_candidate_request(1),
            self._request(51),
            self._request(52),
        ]
        after_budget, _ = scanner._apply_24h_budget_governor(requests, budget_state=budget_state)
        digest_state = scanner.PublishNotice289DigestState(
            enabled=True,
            hour_count=3,
            keep_per_hour=3,
            window_start_iso=(NOW - timedelta(hours=1)).isoformat(),
            window_end_iso=NOW.isoformat(),
        )

        after_digest, updated_state = scanner.apply_289_digest(after_budget, digest_state=digest_state)

        self.assertTrue(scanner._is_24h_budget_summary_only_request(after_digest[0]))
        self.assertEqual(after_digest[1].record_type, "post_gen_validate_digest")
        self.assertEqual(updated_state.digested_count, 2)

    def test_scan_defers_overflow_after_digest_without_advancing_cursor(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1",
                "ENABLE_289_POST_GEN_VALIDATE_DIGEST": "1",
                "PUBLISH_NOTICE_REVIEW_MAX_PER_RUN": "5",
            },
            clear=True,
        ):
            cursor_path = Path(tmpdir) / "cursor.txt"
            history_path = Path(tmpdir) / "history.json"
            queue_path = Path(tmpdir) / "queue.jsonl"
            post_gen_history_path = Path(tmpdir) / "post_gen_validate_history.jsonl"
            post_gen_cursor_path = Path(tmpdir) / "post_gen_validate_cursor.txt"
            cursor_path.write_text("2026-05-02T18:00:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            post_gen_history_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "ts": (NOW - timedelta(minutes=index + 1)).isoformat(),
                            "source_url": f"https://example.com/deferred-{index}",
                            "source_url_hash": f"deferred{index:04d}",
                            "source_title": f"deferred title {index}",
                            "generated_title": f"generated {index}",
                            "category": "試合速報",
                            "article_subtype": "postgame",
                            "skip_reason": "weak_subject_title:related_info_escape",
                            "fail_axis": ["weak_subject_title:related_info_escape"],
                        },
                        ensure_ascii=False,
                    )
                    for index in range(2)
                )
                + "\n",
                encoding="utf-8",
            )
            self._write_queue_rows(
                queue_path,
                [
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 1 | YOSHILOVER",
                        post_id="post_gen_validate:hash0001:weak_subject_title:related_info_escape",
                        minutes_ago=10,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 2 | YOSHILOVER",
                        post_id="post_gen_validate:hash0002:weak_subject_title:related_info_escape",
                        minutes_ago=20,
                    ),
                    self._sent_row(
                        subject="【要review｜post_gen_validate】mail 3 | YOSHILOVER",
                        post_id="post_gen_validate:hash0003:weak_subject_title:related_info_escape",
                        minutes_ago=30,
                    ),
                    self._sent_row(
                        subject=scanner._build_post_gen_validate_digest_subject(
                            count=2,
                            representative_subject="digest representative",
                        ),
                        post_id="post_gen_validate_digest:window-a",
                        minutes_ago=5,
                    ),
                ],
            )

            result = scanner.scan(
                cursor_path=cursor_path,
                history_path=history_path,
                queue_path=queue_path,
                post_gen_validate_history_path=post_gen_history_path,
                post_gen_validate_cursor_path=post_gen_cursor_path,
                fetch=lambda base, after: [],
                now=lambda: NOW,
            )
            history_after = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(result.emitted, [])
        self.assertFalse(post_gen_cursor_path.exists())
        self.assertEqual(history_after, {})


if __name__ == "__main__":
    unittest.main()
