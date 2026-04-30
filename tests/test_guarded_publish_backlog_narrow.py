import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import guarded_publish_runner as runner
from src import publish_notice_email_sender as notice_sender
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


class GuardedPublishBacklogNarrowTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _backlog_flag_for_subtype(self, subtype: str) -> str:
        if subtype in {"lineup", "pregame", "probable_starter", "farm_lineup"}:
            return "expired_lineup_or_pregame"
        if subtype in {"postgame", "game_result"}:
            return "expired_game_context"
        return "stale_for_breaking_board"

    def _make_candidate_post(
        self,
        post_id: int,
        title: str,
        *,
        subtype: str,
        source_url: str | None = None,
        status: str = "draft",
        meta: dict | None = None,
        body_html: str | None = None,
    ) -> dict:
        article_source_url = source_url or f"https://example.com/{subtype}-{post_id}"
        content = body_html or (
            f"<p>{title}について整理した。</p>"
            f"<p>{LONG_EXTRA}</p>"
            f"<p>参照元: スポーツ報知 {article_source_url}</p>"
        )
        return _post(
            post_id,
            title,
            content,
            status=status,
            subtype=subtype,
            meta=meta,
        )

    def _make_backlog_entry(
        self,
        post: dict,
        *,
        subtype: str,
        age_hours: float,
        backlog_only: bool = True,
    ) -> dict:
        flag = self._backlog_flag_for_subtype(subtype)
        return _repairable_entry(
            int(post["id"]),
            str(post["title"]["raw"]),
            flag,
            yellow_reasons=[flag],
            cleanup_required=False,
            freshness_age_hours=age_hours,
            freshness_source="x_post_date",
            backlog_only=backlog_only,
            subtype=subtype,
            resolved_subtype=subtype,
        )

    def _run_report(
        self,
        report: dict,
        posts: dict[int, dict],
        *,
        live: bool = False,
        capture_stderr: bool = False,
        history_path: Path | None = None,
    ) -> tuple[dict, FakeWPClient, list[dict], str]:
        wp = FakeWPClient(posts)
        with tempfile.TemporaryDirectory() as tmpdir:
            history = history_path or (Path(tmpdir) / "history.jsonl")
            stderr_buffer = Path(tmpdir) / "stderr.txt"
            if capture_stderr:
                with stderr_buffer.open("w", encoding="utf-8") as handle, patch("sys.stderr", handle):
                    result = runner.run_guarded_publish(
                        input_from=self._write_input(tmpdir, report),
                        live=live,
                        daily_cap_allow=live,
                        history_path=history,
                        backup_dir=Path(tmpdir) / "cleanup_backup",
                        yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                        cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                        wp_client=wp,
                        now=FIXED_NOW,
                    )
                stderr_text = stderr_buffer.read_text(encoding="utf-8")
            else:
                result = runner.run_guarded_publish(
                    input_from=self._write_input(tmpdir, report),
                    live=live,
                    daily_cap_allow=live,
                    history_path=history,
                    backup_dir=Path(tmpdir) / "cleanup_backup",
                    yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                    cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                    wp_client=wp,
                    now=FIXED_NOW,
                )
                stderr_text = ""
            history_rows = []
            if history.exists():
                history_rows = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
        return result, wp, history_rows, stderr_text

    def _run_backlog_case(
        self,
        *,
        post_id: int,
        title: str,
        subtype: str,
        age_hours: float,
        backlog_only: bool = True,
        live: bool = False,
        capture_stderr: bool = False,
        source_url: str | None = None,
        body_html: str | None = None,
    ) -> tuple[dict, FakeWPClient, list[dict], str]:
        candidate = self._make_candidate_post(
            post_id,
            title,
            subtype=subtype,
            source_url=source_url,
            body_html=body_html,
        )
        report = _report(
            yellow=[
                self._make_backlog_entry(
                    candidate,
                    subtype=subtype,
                    age_hours=age_hours,
                    backlog_only=backlog_only,
                )
            ]
        )
        return self._run_report(report, {post_id: candidate}, live=live, capture_stderr=capture_stderr)

    def test_farm_result_fresh_path_stays_publishable(self):
        post = self._make_candidate_post(5101, "巨人二軍 4-2 楽天 試合結果", subtype="farm_result")
        report = _report(
            green=[
                _green_entry(
                    5101,
                    post["title"]["raw"],
                    subtype="farm_result",
                    resolved_subtype="farm_result",
                    freshness_age_hours=2.0,
                    freshness_source="x_post_date",
                )
            ]
        )

        result, _, _, _ = self._run_report(report, {5101: post})

        self.assertEqual([entry["post_id"] for entry in result["proposed"]], [5101])
        self.assertEqual(result["refused"], [])

    def test_farm_result_backlog_within_24h_is_eligible(self):
        result, _, _, stderr = self._run_backlog_case(
            post_id=5102,
            title="巨人二軍 4-2 楽天 試合結果",
            subtype="farm_result",
            age_hours=12.0,
            capture_stderr=True,
        )

        self.assertEqual([entry["post_id"] for entry in result["proposed"]], [5102])
        self.assertEqual(result["refused"], [])
        self.assertIn('"narrow_kind": "farm_result_age_within_24h"', stderr)

    def test_farm_result_backlog_borderline_under_24h_is_eligible(self):
        candidate = self._make_candidate_post(5103, "巨人二軍 5-3 楽天 試合結果", subtype="farm_result")
        entry = self._make_backlog_entry(candidate, subtype="farm_result", age_hours=23.5)

        context = runner._backlog_narrow_publish_context(entry, now=FIXED_NOW)

        self.assertEqual(context["subtype"], "farm_result")
        self.assertEqual(context["threshold_hours"], 24.0)
        self.assertEqual(context["narrow_kind"], "farm_result_age_within_24h")
        self.assertEqual(context["reason"], "farm_result_age_within_24h")

    def test_farm_result_backlog_at_or_over_24h_stays_held(self):
        at_limit, _, _, _ = self._run_backlog_case(
            post_id=5104,
            title="巨人二軍 1-0 楽天 試合結果",
            subtype="farm_result",
            age_hours=24.0,
        )
        stale, _, _, _ = self._run_backlog_case(
            post_id=5105,
            title="巨人二軍 3-1 楽天 試合結果",
            subtype="farm_result",
            age_hours=72.0,
        )

        self.assertEqual(at_limit["proposed"], [])
        self.assertEqual(at_limit["refused"][0]["reason"], "backlog_only")
        self.assertEqual(stale["proposed"], [])
        self.assertEqual(stale["refused"][0]["reason"], "backlog_only")

    def test_farm_lineup_backlog_stays_blocked_but_fresh_stays_publishable(self):
        backlog_result, _, _, _ = self._run_backlog_case(
            post_id=5106,
            title="巨人二軍スタメン発表を整理",
            subtype="farm_lineup",
            age_hours=2.0,
        )
        fresh_post = self._make_candidate_post(5107, "巨人二軍スタメン発表を整理", subtype="farm_lineup")
        fresh_report = _report(
            green=[
                _green_entry(
                    5107,
                    fresh_post["title"]["raw"],
                    subtype="farm_lineup",
                    resolved_subtype="farm_lineup",
                    freshness_age_hours=1.0,
                    freshness_source="x_post_date",
                )
            ]
        )

        fresh_result, _, _, _ = self._run_report(fresh_report, {5107: fresh_post})

        self.assertEqual(backlog_result["proposed"], [])
        self.assertEqual(backlog_result["refused"][0]["reason"], "backlog_only")
        self.assertEqual([entry["post_id"] for entry in fresh_result["proposed"]], [5107])

    def test_existing_allowlist_and_unresolved_paths_stay_unchanged(self):
        postgame_result, _, _, _ = self._run_backlog_case(
            post_id=5108,
            title="巨人が阪神に3-2で勝利",
            subtype="postgame",
            age_hours=8.0,
        )
        comment_result, _, _, _ = self._run_backlog_case(
            post_id=5109,
            title="阿部監督が継投を説明",
            subtype="comment",
            age_hours=10.0,
        )
        default_result, _, _, stderr = self._run_backlog_case(
            post_id=5110,
            title="巨人の動きを整理",
            subtype="default",
            age_hours=20.0,
            capture_stderr=True,
        )

        self.assertEqual([entry["post_id"] for entry in postgame_result["proposed"]], [5108])
        self.assertEqual([entry["post_id"] for entry in comment_result["proposed"]], [5109])
        self.assertEqual([entry["post_id"] for entry in default_result["proposed"]], [5110])
        self.assertIn('"narrow_kind": "unresolved_fallback"', stderr)

    def test_red_and_review_paths_stay_ahead_of_backlog_narrowing(self):
        placeholder_post = self._make_candidate_post(5111, "巨人二軍 楽天戦 試合結果", subtype="farm_result")
        placeholder_report = _report(red=[_hard_stop_entry(5111, placeholder_post["title"]["raw"], "farm_result_placeholder_body")])
        placeholder_result, _, _, _ = self._run_report(placeholder_report, {5111: placeholder_post})

        score_post = self._make_candidate_post(5112, "巨人二軍 4-3 楽天 試合結果", subtype="farm_result")
        score_report = _report(red=[_hard_stop_entry(5112, score_post["title"]["raw"], "win_loss_score_conflict")])
        score_result, _, _, _ = self._run_report(score_report, {5112: score_post})

        duplicate_post = self._make_candidate_post(5113, "巨人二軍 2-1 楽天 試合結果", subtype="farm_result")
        duplicate_report = _report(review=[_review_entry(5113, duplicate_post["title"]["raw"], "duplicate_candidate_same_source_url")])
        duplicate_result, _, _, _ = self._run_report(duplicate_report, {5113: duplicate_post})

        self.assertEqual(placeholder_result["refused"][0]["hold_reason"], "hard_stop_farm_result_placeholder_body")
        self.assertEqual(score_result["refused"][0]["hold_reason"], "hard_stop_win_loss_score_conflict")
        self.assertEqual(duplicate_result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")

    def test_farm_result_backlog_publish_routes_into_backlog_summary_mail(self):
        bridge_send = MagicMock(return_value=MagicMock())
        post = self._make_candidate_post(5114, "巨人二軍 4-2 楽天 試合結果", subtype="farm_result")
        report = _report(
            yellow=[
                self._make_backlog_entry(
                    post,
                    subtype="farm_result",
                    age_hours=12.0,
                    backlog_only=True,
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=FakeWPClient({5114: post}),
                now=FIXED_NOW,
            )
            summary_requests = notice_sender.build_burst_summary_requests(
                [
                    notice_sender.BurstSummaryEntry(
                        post_id=5114,
                        title=post["title"]["raw"],
                        category="試合速報",
                        publishable=True,
                        cleanup_required=False,
                        cleanup_success=True,
                    )
                ],
                guarded_publish_history_path=history_path,
            )
            mail_result = notice_sender.send_summary(
                summary_requests[0],
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
            )

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(summary_requests[0].summary_mode, "backlog_only")
        self.assertEqual([entry.post_id for entry in summary_requests[0].entries], [5114])
        self.assertEqual(mail_result.status, "sent")
        bridge_send.assert_called_once()

    def test_farm_result_hold_and_review_mail_paths_stay_distinct(self):
        bridge_send = MagicMock(return_value=MagicMock())

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"},
            clear=True,
        ):
            hold_history_path = Path(tmpdir) / "hold_history.jsonl"
            hold_history_path.write_text(
                json.dumps(
                    {
                        "post_id": 5115,
                        "ts": FIXED_NOW.isoformat(),
                        "status": "sent",
                        "judgment": "yellow",
                        "is_backlog": True,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            hold_result = notice_sender.send(
                notice_sender.PublishNoticeRequest(
                    post_id=5115,
                    title="巨人二軍 1-0 楽天 試合結果",
                    canonical_url="https://yoshilover.com/5115",
                    subtype="farm_result",
                    publish_time_iso=FIXED_NOW.isoformat(),
                    summary="巨人二軍が楽天に1-0で勝利した。投手戦を制した。",
                ),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                guarded_publish_history_path=hold_history_path,
            )

            review_history_path = Path(tmpdir) / "review_history.jsonl"
            review_history_path.write_text(
                json.dumps(
                    {
                        "post_id": 5116,
                        "ts": FIXED_NOW.isoformat(),
                        "status": "refused",
                        "judgment": "review",
                        "is_backlog": False,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            review_result = notice_sender.send(
                notice_sender.PublishNoticeRequest(
                    post_id=5116,
                    title="巨人二軍 楽天戦 試合結果",
                    canonical_url="https://yoshilover.com/5116",
                    subtype="farm_result",
                    publish_time_iso=FIXED_NOW.isoformat(),
                    summary="巨人二軍が楽天戦の結果を更新した。スポーツ報知が伝えた。",
                ),
                dry_run=False,
                send_enabled=True,
                bridge_send=bridge_send,
                guarded_publish_history_path=review_history_path,
            )

        self.assertEqual(hold_result.status, "suppressed")
        self.assertEqual(hold_result.reason, "BACKLOG_SUMMARY_ONLY")
        self.assertEqual(review_result.status, "sent")
        self.assertEqual(review_result.subject, "【要確認】巨人二軍 楽天戦 試合結果 | YOSHILOVER")

    def test_live_update_flag_does_not_change_farm_result_backlog_behavior(self):
        with patch.dict("os.environ", {"ENABLE_LIVE_UPDATE_ARTICLES": "0"}, clear=False):
            off_result, _, _, _ = self._run_backlog_case(
                post_id=5117,
                title="巨人二軍 4-2 楽天 試合結果",
                subtype="farm_result",
                age_hours=12.0,
            )
        with patch.dict("os.environ", {"ENABLE_LIVE_UPDATE_ARTICLES": "1"}, clear=False):
            on_result, _, _, _ = self._run_backlog_case(
                post_id=5117,
                title="巨人二軍 4-2 楽天 試合結果",
                subtype="farm_result",
                age_hours=12.0,
            )

        self.assertEqual(off_result["proposed"], on_result["proposed"])
        self.assertEqual(off_result["refused"], on_result["refused"])

    def test_guarded_publish_runner_stays_free_of_gemini_and_live_update_tokens(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")

        self.assertNotIn("ENABLE_LIVE_UPDATE_ARTICLES", source)
        self.assertNotIn("gemini", source.lower())
        self.assertNotIn("prosports", source.lower())


if __name__ == "__main__":
    unittest.main()
