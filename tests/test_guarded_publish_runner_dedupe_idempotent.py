import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import guarded_publish_runner as runner
from tests.test_guarded_publish_runner import (
    FIXED_NOW,
    LONG_EXTRA,
    FakeWPClient,
    _green_entry,
    _hard_stop_entry,
    _post,
    _repairable_entry,
    _report,
    _review_entry,
)


class GuardedPublishRunnerIdempotentHistoryTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _make_candidate_post(
        self,
        post_id: int,
        title: str,
        *,
        subtype: str,
        source_url: str | None = None,
    ) -> dict:
        article_source_url = source_url or f"https://example.com/{subtype}-{post_id}"
        body_html = (
            f"<p>{title}について整理した。</p>"
            f"<p>{LONG_EXTRA}</p>"
            f"<p>参照元: スポーツ報知 {article_source_url}</p>"
        )
        return _post(post_id, title, body_html, subtype=subtype)

    def _make_backlog_entry(
        self,
        post: dict,
        *,
        subtype: str,
        age_hours: float,
        backlog_only: bool,
    ) -> dict:
        return _repairable_entry(
            int(post["id"]),
            str(post["title"]["raw"]),
            "expired_lineup_or_pregame" if subtype in {"lineup", "pregame", "probable_starter", "farm_lineup"} else "expired_game_context",
            yellow_reasons=[
                "expired_lineup_or_pregame"
                if subtype in {"lineup", "pregame", "probable_starter", "farm_lineup"}
                else "expired_game_context"
            ],
            cleanup_required=False,
            freshness_age_hours=age_hours,
            freshness_source="x_post_date",
            backlog_only=backlog_only,
            subtype=subtype,
            resolved_subtype=subtype,
        )

    def _history_row(
        self,
        *,
        post_id: int,
        ts: str,
        judgment: str = "yellow",
        status: str = "skipped",
        error: str = "backlog_only",
        hold_reason: str = "backlog_only",
        publishable: bool = True,
        cleanup_required: bool = False,
        is_backlog: bool = True,
        freshness_source: str = "x_post_date",
    ) -> dict:
        return runner._history_row(
            post_id=post_id,
            judgment=judgment,
            status=status,
            ts=ts,
            backup_path=None,
            error=error,
            publishable=publishable,
            cleanup_required=cleanup_required,
            cleanup_success=False,
            hold_reason=hold_reason,
            is_backlog=is_backlog,
            freshness_source=freshness_source,
        )

    def _run_report(
        self,
        report: dict,
        posts: dict[int, dict],
        *,
        history_rows: list[dict] | None = None,
        capture_stderr: bool = False,
        max_burst: int = runner.DEFAULT_MAX_BURST,
    ) -> tuple[dict, list[dict], str]:
        wp = FakeWPClient(posts)
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            if history_rows:
                history_path.write_text(
                    "\n".join(json.dumps(row, ensure_ascii=False) for row in history_rows) + "\n",
                    encoding="utf-8",
                )
            stderr_buffer = io.StringIO()
            patcher = patch("sys.stderr", stderr_buffer) if capture_stderr else patch("sys.stderr", io.StringIO())
            with patcher:
                result = runner.run_guarded_publish(
                    input_from=self._write_input(tmpdir, report),
                    live=True,
                    max_burst=max_burst,
                    daily_cap_allow=True,
                    history_path=history_path,
                    backup_dir=Path(tmpdir) / "cleanup_backup",
                    yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                    cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                    wp_client=wp,
                    now=FIXED_NOW,
                )
            rows_after = []
            if history_path.exists():
                rows_after = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return result, rows_after, stderr_buffer.getvalue()

    def _rows_for_post(self, rows: list[dict], post_id: int) -> list[dict]:
        return [row for row in rows if int(row.get("post_id")) == post_id]

    def test_unchanged_backlog_only_latest_row_skips_append(self):
        post = self._make_candidate_post(901, "巨人戦 試合前にどこを見たいか", subtype="pregame")
        report = _report(yellow=[self._make_backlog_entry(post, subtype="pregame", age_hours=12.0, backlog_only=True)])
        prior_row = self._history_row(post_id=901, ts="2026-05-01T08:00:00+09:00")

        with patch.dict("os.environ", {"ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY": "1"}, clear=False):
            result, history_rows, stderr = self._run_report(
                report,
                {901: post},
                history_rows=[prior_row],
                capture_stderr=True,
            )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"], [{"post_id": 901, "reason": "backlog_only", "hold_reason": "backlog_only"}])
        self.assertEqual(self._rows_for_post(history_rows, 901), [prior_row])
        self.assertIn('"event": "guarded_publish_idempotent_history_skip"', stderr)
        self.assertIn('"reason": "unchanged_backlog_only"', stderr)

    def test_new_post_without_prior_state_appends_once(self):
        post = self._make_candidate_post(902, "巨人戦 試合前にどこを見たいか", subtype="pregame")
        report = _report(yellow=[self._make_backlog_entry(post, subtype="pregame", age_hours=12.0, backlog_only=True)])

        with patch.dict("os.environ", {"ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY": "1"}, clear=False):
            result, history_rows, _ = self._run_report(report, {902: post})

        self.assertEqual(result["refused"], [{"post_id": 902, "reason": "backlog_only", "hold_reason": "backlog_only"}])
        self.assertEqual(len(self._rows_for_post(history_rows, 902)), 1)
        self.assertEqual(self._rows_for_post(history_rows, 902)[0]["hold_reason"], "backlog_only")

    def test_same_post_changed_hold_reason_appends(self):
        stale_post = self._make_candidate_post(903, "巨人が阪神に3-2で勝利", subtype="postgame")
        fresh_post = self._make_candidate_post(904, "巨人がヤクルトに3-1で勝利", subtype="postgame")
        report = _report(
            green=[
                _green_entry(
                    904,
                    fresh_post["title"]["raw"],
                    resolved_subtype="postgame",
                    freshness_age_hours=1.0,
                    freshness_source="x_post_date",
                )
            ],
            yellow=[self._make_backlog_entry(stale_post, subtype="postgame", age_hours=48.0, backlog_only=False)],
        )
        prior_row = self._history_row(post_id=903, ts="2026-05-01T08:00:00+09:00")

        with patch.dict("os.environ", {"ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY": "1"}, clear=False):
            result, history_rows, _ = self._run_report(
                report,
                {903: stale_post, 904: fresh_post},
                history_rows=[prior_row],
            )

        target_rows = self._rows_for_post(history_rows, 903)
        self.assertEqual(len(target_rows), 2)
        self.assertEqual(target_rows[-1]["hold_reason"], "backlog_deferred_for_fresh")
        self.assertIn(
            {"post_id": 903, "reason": "backlog_deferred_for_fresh", "hold_reason": "backlog_deferred_for_fresh"},
            result["refused"],
        )

    def test_same_post_changed_status_appends(self):
        report = _report(review=[_review_entry(905, "阿部監督が継投を説明", "needs_human_review")])
        prior_row = self._history_row(post_id=905, ts="2026-05-01T08:00:00+09:00")

        with patch.dict("os.environ", {"ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY": "1"}, clear=False):
            result, history_rows, _ = self._run_report(report, {}, history_rows=[prior_row])

        target_rows = self._rows_for_post(history_rows, 905)
        self.assertEqual(len(target_rows), 2)
        self.assertEqual(target_rows[-1]["status"], "refused")
        self.assertEqual(target_rows[-1]["judgment"], "review")
        self.assertEqual(
            result["refused"],
            [{"post_id": 905, "reason": "review", "hold_reason": "review_needs_human_review"}],
        )

    def test_same_post_changed_judgment_appends(self):
        report = _report(red=[_hard_stop_entry(906, "巨人戦で数値不整合が残る", "fabricated_result")])
        prior_row = self._history_row(post_id=906, ts="2026-05-01T08:00:00+09:00")

        with patch.dict("os.environ", {"ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY": "1"}, clear=False):
            result, history_rows, _ = self._run_report(report, {}, history_rows=[prior_row])

        target_rows = self._rows_for_post(history_rows, 906)
        self.assertEqual(len(target_rows), 2)
        self.assertEqual(target_rows[-1]["judgment"], "hard_stop")
        self.assertEqual(target_rows[-1]["status"], "refused")
        self.assertEqual(result["refused"][0]["post_id"], 906)
        self.assertEqual(result["refused"][0]["hold_reason"], "hard_stop_fabricated_result")

    def test_latest_row_match_is_based_on_state_not_ts(self):
        post = self._make_candidate_post(907, "巨人戦 試合前にどこを見たいか", subtype="pregame")
        report = _report(yellow=[self._make_backlog_entry(post, subtype="pregame", age_hours=18.0, backlog_only=True)])
        prior_rows = [
            self._history_row(post_id=907, ts="2026-04-30T07:00:00+09:00", error="older_backlog_only"),
            self._history_row(post_id=907, ts="2026-05-01T20:00:00+09:00"),
        ]

        with patch.dict("os.environ", {"ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY": "1"}, clear=False):
            _, history_rows, stderr = self._run_report(
                report,
                {907: post},
                history_rows=prior_rows,
                capture_stderr=True,
            )

        self.assertEqual(self._rows_for_post(history_rows, 907), prior_rows)
        self.assertIn('"reason": "unchanged_backlog_only"', stderr)

    def test_non_backlog_skip_reasons_remain_appending(self):
        with patch.dict("os.environ", {"ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY": "1"}, clear=False):
            cases = []

            daily_post = self._make_candidate_post(908, "巨人が阪神に3-2で勝利", subtype="postgame")
            daily_history = [
                self._history_row(
                    post_id=1000 + index,
                    ts="2026-04-26T02:00:00+09:00",
                    judgment="green",
                    status="sent",
                    error=None,
                    hold_reason=None,
                    is_backlog=False,
                )
                for index in range(runner.DAILY_CAP_HARD_CAP)
            ]
            daily_report = _report(
                green=[
                    _green_entry(
                        908,
                        daily_post["title"]["raw"],
                        resolved_subtype="postgame",
                        freshness_age_hours=1.0,
                        freshness_source="x_post_date",
                    )
                ]
            )
            cases.append(("daily_cap", daily_report, {908: daily_post}, daily_history, runner.DEFAULT_MAX_BURST, 908))

            hourly_post = self._make_candidate_post(909, "巨人が広島に2-1で勝利", subtype="postgame")
            hourly_history = [
                self._history_row(
                    post_id=1100 + index,
                    ts=f"2026-04-26T07:{index:02d}:00+09:00",
                    judgment="green",
                    status="sent",
                    error=None,
                    hold_reason=None,
                    is_backlog=False,
                )
                for index in range(runner.DEFAULT_MAX_PUBLISH_PER_HOUR)
            ]
            hourly_report = _report(
                green=[
                    _green_entry(
                        909,
                        hourly_post["title"]["raw"],
                        resolved_subtype="postgame",
                        freshness_age_hours=1.0,
                        freshness_source="x_post_date",
                    )
                ]
            )
            cases.append(("hourly_cap", hourly_report, {909: hourly_post}, hourly_history, runner.DEFAULT_MAX_BURST, 909))

            first_post = self._make_candidate_post(910, "巨人が中日に4-1で勝利", subtype="postgame")
            second_post = self._make_candidate_post(911, "巨人がDeNAに5-2で勝利", subtype="postgame")
            burst_report = _report(
                green=[
                    _green_entry(
                        910,
                        first_post["title"]["raw"],
                        resolved_subtype="postgame",
                        freshness_age_hours=1.0,
                        freshness_source="x_post_date",
                    ),
                    _green_entry(
                        911,
                        second_post["title"]["raw"],
                        resolved_subtype="postgame",
                        freshness_age_hours=1.0,
                        freshness_source="x_post_date",
                    ),
                ]
            )
            cases.append(("burst_cap", burst_report, {910: first_post, 911: second_post}, None, 1, 911))

            fresh_post = self._make_candidate_post(912, "巨人がヤクルトに6-3で勝利", subtype="postgame")
            stale_post = self._make_candidate_post(913, "巨人が阪神に2-1で勝利", subtype="postgame")
            deferred_report = _report(
                green=[
                    _green_entry(
                        912,
                        fresh_post["title"]["raw"],
                        resolved_subtype="postgame",
                        freshness_age_hours=1.0,
                        freshness_source="x_post_date",
                    )
                ],
                yellow=[self._make_backlog_entry(stale_post, subtype="postgame", age_hours=36.0, backlog_only=False)],
            )
            cases.append(
                ("backlog_deferred_for_fresh", deferred_report, {912: fresh_post, 913: stale_post}, None, runner.DEFAULT_MAX_BURST, 913)
            )

            for hold_reason, report, posts, history_rows, max_burst, target_post_id in cases:
                with self.subTest(hold_reason=hold_reason):
                    result, rows_after, _ = self._run_report(
                        report,
                        posts,
                        history_rows=history_rows,
                        max_burst=max_burst,
                    )
                    target_rows = self._rows_for_post(rows_after, target_post_id)
                    self.assertGreaterEqual(len(target_rows), 1)
                    self.assertEqual(target_rows[-1]["hold_reason"], hold_reason)
                    self.assertIn(target_post_id, [row["post_id"] for row in result["refused"]])

    def test_flag_off_baseline_appends_per_run(self):
        post = self._make_candidate_post(914, "巨人戦 試合前にどこを見たいか", subtype="pregame")
        report = _report(yellow=[self._make_backlog_entry(post, subtype="pregame", age_hours=12.0, backlog_only=True)])
        prior_row = self._history_row(post_id=914, ts="2026-05-01T08:00:00+09:00")

        for flag_value in (None, "0"):
            with self.subTest(flag_value=flag_value):
                with patch.dict("os.environ", {}, clear=False):
                    if flag_value is None:
                        os.environ.pop("ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY", None)
                    else:
                        os.environ["ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY"] = flag_value
                    result, history_rows, stderr = self._run_report(
                        report,
                        {914: post},
                        history_rows=[prior_row],
                        capture_stderr=True,
                    )
                self.assertEqual(
                    result["refused"],
                    [{"post_id": 914, "reason": "backlog_only", "hold_reason": "backlog_only"}],
                )
                self.assertEqual(len(self._rows_for_post(history_rows, 914)), 2)
                self.assertNotIn("guarded_publish_idempotent_history_skip", stderr)


if __name__ == "__main__":
    unittest.main()
