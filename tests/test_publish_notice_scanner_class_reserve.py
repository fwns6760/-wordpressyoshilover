import json
import tempfile
import unittest
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import publish_notice_scanner as scanner


NOW = datetime(2026, 5, 1, 19, 0, tzinfo=scanner.JST)


class PublishNoticeScannerClassReserveTests(unittest.TestCase):
    def _request(self, notice_class: str, index: int) -> scanner.PublishNoticeRequest:
        kwargs = {
            "post_id": f"{notice_class}:{index}",
            "title": f"{notice_class} {index}",
            "canonical_url": f"https://example.com/{notice_class}/{index}",
            "subtype": "postgame",
            "publish_time_iso": NOW.isoformat(),
            "summary": None,
            "is_backlog": False,
        }
        if notice_class == "real_review":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要確認】real review {index} | YOSHILOVER",
            )
        elif notice_class == "guarded_review":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要review】guarded review {index} | YOSHILOVER",
            )
        elif notice_class == "old_candidate":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要確認(古い候補)】old candidate {index} | YOSHILOVER",
            )
        elif notice_class == "post_gen_validate":
            kwargs.update(
                notice_kind="post_gen_validate",
                subject_override=f"【要review｜post_gen_validate】post gen {index} | YOSHILOVER",
                record_type="post_gen_validate",
                skip_layer="post_gen_validate",
                skip_reason="weak_subject_title:related_info_escape",
                source_url_hash=f"postgen{index:04d}",
            )
        elif notice_class == "preflight_skip":
            kwargs.update(
                notice_kind="post_gen_validate",
                subject_override=f"【要review｜preflight_skip】preflight {index} | YOSHILOVER",
                record_type="preflight_skip",
                skip_layer="preflight",
                skip_reason="placeholder_body",
                source_url_hash=f"preflight{index:04d}",
            )
        elif notice_class == "error_notification":
            kwargs.update(
                notice_kind="alert",
                subject_override=f"【警告】post_id={index} | YOSHILOVER",
            )
        else:
            raise AssertionError(f"unsupported notice_class: {notice_class}")
        return scanner.PublishNoticeRequest(**kwargs)

    def _select(self, requests: list[scanner.PublishNoticeRequest], *, max_total: int = 10) -> list[scanner.PublishNoticeRequest]:
        return scanner._select_candidates_by_class_reserve(
            requests,
            max_total=max_total,
            reserve_map=scanner._resolve_class_reserve_map(),
            priority_order=scanner._CLASS_RESERVE_PRIORITY_ORDER,
        )

    def _classes(self, requests: list[scanner.PublishNoticeRequest]) -> list[str]:
        return [scanner._classify_notice_request(request) for request in requests]

    def _post(self, post_id: int, *, title: str) -> dict[str, object]:
        return {
            "id": post_id,
            "title": {"rendered": title},
            "excerpt": {"rendered": "<p>review body</p>"},
            "content": {"rendered": "<p>review body</p>"},
            "link": f"https://yoshilover.com/draft-{post_id}/",
            "date": "2026-05-01T18:00:00+09:00",
            "status": "draft",
            "meta": {"article_subtype": "postgame"},
        }

    def _guarded_entry(
        self,
        *,
        post_id: int,
        ts: str,
        judgment: str = "yellow",
        hold_reason: str = "",
    ) -> dict[str, object]:
        payload = {
            "post_id": post_id,
            "ts": ts,
            "status": "refused",
            "judgment": judgment,
            "publishable": True,
            "cleanup_required": False,
            "cleanup_success": False,
        }
        if hold_reason:
            payload["hold_reason"] = hold_reason
        return payload

    def _post_gen_entry(self, index: int) -> dict[str, object]:
        return {
            "ts": f"2026-05-01T18:{10 + index:02d}:00+09:00",
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

    def _preflight_entry(self, index: int) -> dict[str, object]:
        return {
            "ts": f"2026-05-01T18:{30 + index:02d}:00+09:00",
            "record_type": "preflight_skip",
            "skip_layer": "preflight",
            "source_url": f"https://example.com/preflight-{index}",
            "source_url_hash": f"preflight{index:04d}",
            "source_title": f"preflight source {index}",
            "category": "試合速報",
            "article_subtype": "postgame",
            "source_name": "スポーツ報知",
            "source_type": "news",
            "skip_reason": "placeholder_body",
        }

    def test_select_keeps_three_real_review_under_congestion(self):
        requests = [
            *(self._request("old_candidate", index) for index in range(6)),
            *(self._request("guarded_review", index) for index in range(2)),
            *(self._request("real_review", index) for index in range(3)),
            *(self._request("post_gen_validate", index) for index in range(4)),
        ]

        selected = self._select(list(requests))
        counts = Counter(self._classes(selected))

        self.assertEqual(len(selected), 10)
        self.assertEqual(counts["real_review"], 3)

    def test_select_keeps_two_post_gen_validate_minimum(self):
        requests = [
            *(self._request("guarded_review", index) for index in range(6)),
            *(self._request("old_candidate", index) for index in range(6)),
            *(self._request("post_gen_validate", index) for index in range(3)),
        ]

        selected = self._select(list(requests))
        counts = Counter(self._classes(selected))

        self.assertEqual(len(selected), 10)
        self.assertGreaterEqual(counts["post_gen_validate"], 2)

    def test_select_keeps_one_error_notification_minimum(self):
        requests = [
            *(self._request("guarded_review", index) for index in range(7)),
            *(self._request("old_candidate", index) for index in range(7)),
            *(self._request("error_notification", index) for index in range(2)),
        ]

        selected = self._select(list(requests))
        counts = Counter(self._classes(selected))

        self.assertEqual(len(selected), 10)
        self.assertGreaterEqual(counts["error_notification"], 1)

    def test_select_transfers_unused_reserve_slots(self):
        requests = [
            self._request("real_review", 1),
            *(self._request("old_candidate", index) for index in range(12)),
        ]

        selected = self._select(list(requests))
        counts = Counter(self._classes(selected))

        self.assertEqual(len(selected), 10)
        self.assertEqual(counts["real_review"], 1)
        self.assertEqual(counts["old_candidate"], 9)

    def test_select_preserves_priority_order_after_reserve(self):
        requests = [
            self._request("old_candidate", 1),
            self._request("preflight_skip", 1),
            self._request("post_gen_validate", 1),
            self._request("guarded_review", 1),
            self._request("real_review", 1),
            self._request("post_gen_validate", 2),
            self._request("real_review", 2),
            self._request("real_review", 3),
        ]

        selected = self._select(list(requests), max_total=8)

        self.assertEqual(
            self._classes(selected),
            [
                "real_review",
                "real_review",
                "real_review",
                "guarded_review",
                "post_gen_validate",
                "post_gen_validate",
                "preflight_skip",
                "old_candidate",
            ],
        )

    def test_scan_integration_applies_combined_cap_and_freezes_unselected_cursors(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "ENABLE_PUBLISH_NOTICE_CLASS_RESERVE": "1",
                "ENABLE_POST_GEN_VALIDATE_NOTIFICATION": "1",
                "ENABLE_PREFLIGHT_SKIP_NOTIFICATION": "1",
                "PUBLISH_NOTICE_REVIEW_MAX_PER_RUN": "10",
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
            preflight_history_path = Path(tmpdir) / "preflight_skip_history.jsonl"
            preflight_cursor_path = Path(tmpdir) / "preflight_skip_cursor.txt"

            cursor_path.write_text("2026-05-01T17:30:00+09:00\n", encoding="utf-8")
            history_path.write_text("{}\n", encoding="utf-8")
            guarded_history_path.write_text(
                "\n".join(
                    json.dumps(entry, ensure_ascii=False)
                    for entry in [
                        self._guarded_entry(post_id=901, ts="2026-05-01T18:01:00+09:00", judgment="yellow"),
                        self._guarded_entry(post_id=902, ts="2026-05-01T18:02:00+09:00", judgment="yellow"),
                        self._guarded_entry(post_id=903, ts="2026-05-01T18:03:00+09:00", judgment="yellow"),
                        self._guarded_entry(post_id=904, ts="2026-05-01T18:04:00+09:00", judgment="review"),
                        self._guarded_entry(post_id=905, ts="2026-05-01T18:05:00+09:00", judgment="review"),
                        self._guarded_entry(post_id=906, ts="2026-05-01T18:06:00+09:00", judgment="yellow", hold_reason="backlog_only"),
                        self._guarded_entry(post_id=907, ts="2026-05-01T18:07:00+09:00", judgment="yellow", hold_reason="backlog_only"),
                        self._guarded_entry(post_id=908, ts="2026-05-01T18:08:00+09:00", judgment="yellow", hold_reason="backlog_only"),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            post_gen_history_path.write_text(
                "\n".join(json.dumps(self._post_gen_entry(index), ensure_ascii=False) for index in range(4)) + "\n",
                encoding="utf-8",
            )
            preflight_history_path.write_text(
                "\n".join(json.dumps(self._preflight_entry(index), ensure_ascii=False) for index in range(2)) + "\n",
                encoding="utf-8",
            )

            with patch.object(
                scanner,
                "_default_fetch_post_detail",
                side_effect=lambda base_url, post_id: self._post(post_id, title=f"draft {post_id}"),
            ):
                result = scanner.scan(
                    cursor_path=cursor_path,
                    history_path=history_path,
                    queue_path=queue_path,
                    guarded_publish_history_path=guarded_history_path,
                    guarded_cursor_path=guarded_cursor_path,
                    post_gen_validate_history_path=post_gen_history_path,
                    post_gen_validate_cursor_path=post_gen_cursor_path,
                    preflight_skip_history_path=preflight_history_path,
                    preflight_skip_cursor_path=preflight_cursor_path,
                    fetch=lambda base_url, after_iso: [],
                    now=lambda: NOW,
                )
                self.assertEqual(len(result.emitted), 10)
                counts = Counter(self._classes(result.emitted))
                self.assertEqual(counts["real_review"], 3)
                self.assertEqual(counts["guarded_review"], 2)
                self.assertEqual(counts["post_gen_validate"], 4)
                self.assertEqual(counts["preflight_skip"], 1)
                self.assertFalse(guarded_cursor_path.exists())
                self.assertTrue(post_gen_cursor_path.exists())
                self.assertFalse(preflight_cursor_path.exists())
                queue_rows = [
                    json.loads(line)
                    for line in queue_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                self.assertEqual(len(queue_rows), 10)
                self.assertEqual(
                    [row.get("record_type") for row in queue_rows if row.get("record_type")],
                    ["post_gen_validate"] * 4 + ["preflight_skip"],
                )


if __name__ == "__main__":
    unittest.main()
