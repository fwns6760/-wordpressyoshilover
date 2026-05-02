import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src import publish_notice_scanner as scanner


NOW = datetime(2026, 5, 2, 19, 35, tzinfo=scanner.JST)


class PublishNotice24hBudgetGovernorTests(unittest.TestCase):
    def _write_sent_queue_rows(
        self,
        path: Path,
        *,
        count: int,
        start: datetime | None = None,
    ) -> None:
        base = start or (NOW - timedelta(seconds=count + 5))
        rows = []
        for index in range(count):
            sent_at = (base + timedelta(seconds=index)).isoformat()
            rows.append(
                {
                    "status": "sent",
                    "reason": None,
                    "subject": f"mail {index}",
                    "recipients": ["notify@example.com"],
                    "post_id": f"sent:{index}",
                    "recorded_at": sent_at,
                    "sent_at": sent_at,
                    "notice_kind": "per_post",
                }
            )
        path.write_text(
            "".join(f"{json.dumps(row, ensure_ascii=False)}\n" for row in rows),
            encoding="utf-8",
        )

    def _write_budget_ledger_rows(
        self,
        path: Path,
        *,
        counts: list[tuple[datetime, int]],
    ) -> None:
        rows = [
            {
                "ts": ts.isoformat(),
                "mail_count": count,
                "projected_cumulative": count,
                "demoted_count": {},
                "source": "scanner_planned",
            }
            for ts, count in counts
        ]
        path.write_text(
            "".join(f"{json.dumps(row, ensure_ascii=False)}\n" for row in rows),
            encoding="utf-8",
        )

    def _request(self, notice_class: str, index: int) -> scanner.PublishNoticeRequest:
        kwargs = {
            "post_id": f"{notice_class}:{index}",
            "title": f"{notice_class} title {index}",
            "canonical_url": f"https://example.com/{notice_class}/{index}",
            "subtype": "postgame",
            "publish_time_iso": NOW.isoformat(),
            "summary": None,
            "is_backlog": False,
        }
        if notice_class == "old_candidate":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要確認(古い候補)】old candidate {index} | YOSHILOVER",
            )
        elif notice_class == "guarded_review":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要review】guarded review {index} | YOSHILOVER",
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
        elif notice_class == "real_review":
            kwargs.update(
                notice_kind="review_hold",
                subject_override=f"【要確認】real review {index} | YOSHILOVER",
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

    def _state(
        self,
        queue_path: Path,
        *,
        budget_ledger_path: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> scanner.PublishNotice24hBudgetState:
        env = {
            "ENABLE_PUBLISH_NOTICE_24H_BUDGET_GOVERNOR": "1",
        }
        if extra_env:
            env.update(extra_env)
        with patch.dict("os.environ", env, clear=True):
            return scanner.evaluate_24h_budget_state(
                queue_path=queue_path,
                budget_ledger_path=budget_ledger_path,
                now=NOW,
            )

    def test_24h_budget_state_calculation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            ledger_path = Path(tmpdir) / "budget.jsonl"
            self._write_sent_queue_rows(queue_path, count=37, start=NOW - timedelta(hours=2))
            self._write_budget_ledger_rows(
                ledger_path,
                counts=[
                    (NOW - timedelta(hours=3), 40),
                    (NOW - timedelta(hours=30), 9),
                ],
            )

            state = self._state(queue_path, budget_ledger_path=ledger_path)

            self.assertTrue(state.enabled)
            self.assertEqual(state.cumulative, 40)
            self.assertEqual(state.projected_cumulative, 40)
            self.assertEqual(state.source, "ledger")
            self.assertFalse(state.soft_breach)
            self.assertFalse(state.hard_breach)

    def test_demotion_below_soft_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_sent_queue_rows(queue_path, count=79)
            state = self._state(queue_path)
            request = self._request("old_candidate", 1)

            transformed, updated_state = scanner._apply_24h_budget_governor(
                [request],
                budget_state=state,
            )

            self.assertEqual(transformed[0].notice_kind, "review_hold")
            self.assertFalse(updated_state.summary_reserved)
            self.assertEqual(updated_state.demoted_count, {})
            self.assertEqual(updated_state.projected_cumulative, 80)

    def test_demotion_at_soft_threshold_old_candidate_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_sent_queue_rows(queue_path, count=80)
            state = self._state(queue_path)
            requests = [
                self._request("old_candidate", 1),
                self._request("guarded_review", 1),
                self._request("post_gen_validate", 1),
            ]

            transformed, updated_state = scanner._apply_24h_budget_governor(
                requests,
                budget_state=state,
            )

            self.assertTrue(scanner._is_24h_budget_summary_only_request(transformed[0]))
            self.assertFalse(scanner._is_24h_budget_summary_only_request(transformed[1]))
            self.assertFalse(scanner._is_24h_budget_summary_only_request(transformed[2]))
            self.assertEqual(updated_state.demoted_count, {"old_candidate": 1})
            self.assertTrue(updated_state.summary_reserved)
            self.assertEqual(updated_state.projected_cumulative, 83)

    def test_demotion_at_hard_threshold_three_classes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_sent_queue_rows(queue_path, count=95)
            state = self._state(queue_path)
            requests = [
                self._request("old_candidate", 1),
                self._request("guarded_review", 1),
                self._request("post_gen_validate", 1),
                self._request("real_review", 1),
            ]

            transformed, updated_state = scanner._apply_24h_budget_governor(
                requests,
                budget_state=state,
            )

            self.assertTrue(scanner._is_24h_budget_summary_only_request(transformed[0]))
            self.assertTrue(scanner._is_24h_budget_summary_only_request(transformed[1]))
            self.assertTrue(scanner._is_24h_budget_summary_only_request(transformed[2]))
            self.assertFalse(scanner._is_24h_budget_summary_only_request(transformed[3]))
            self.assertEqual(
                updated_state.demoted_count,
                {
                    "guarded_review": 1,
                    "old_candidate": 1,
                    "post_gen_validate": 1,
                },
            )
            self.assertTrue(updated_state.hard_breach)
            self.assertEqual(updated_state.projected_cumulative, 97)

    def test_protected_classes_never_demoted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_sent_queue_rows(queue_path, count=120)
            state = self._state(queue_path)
            requests = [
                self._request("error_notification", 1),
                self._request("real_review", 1),
                self._request("preflight_skip", 1),
            ]

            transformed, updated_state = scanner._apply_24h_budget_governor(
                requests,
                budget_state=state,
            )

            self.assertFalse(any(scanner._is_24h_budget_summary_only_request(request) for request in transformed))
            self.assertEqual(updated_state.demoted_count, {})
            self.assertEqual(updated_state.projected_cumulative, 123)

    def test_demoted_summary_preserves_title_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            self._write_sent_queue_rows(queue_path, count=80)
            state = self._state(queue_path)
            requests = [
                self._request("old_candidate", 1),
                self._request("old_candidate", 2),
            ]
            original_titles = [request.title for request in requests]

            transformed, updated_state = scanner._apply_24h_budget_governor(
                requests,
                budget_state=state,
            )

            summary_titles = [request.title for request in transformed if scanner._is_24h_budget_summary_only_request(request)]
            self.assertEqual(summary_titles, original_titles)
            self.assertTrue(all(request.is_backlog for request in transformed))
            self.assertTrue(all(request.notice_kind == "publish" for request in transformed))
            self.assertEqual(updated_state.demoted_count, {"old_candidate": 2})
            self.assertEqual(updated_state.projected_cumulative, 81)


if __name__ == "__main__":
    unittest.main()
