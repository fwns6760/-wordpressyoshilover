import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import guarded_publish_runner as runner
from src.tools import run_guarded_publish as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T08:00:00+09:00")
LONG_EXTRA = (
    "ベンチワークの意図や終盤の継投まで追える内容で、攻守の流れも十分に整理できる一戦だった。"
    "守備位置の動きと追加点の意味も見え、ファン視点でも試合の核を追いやすかった。"
)


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    status: str = "draft",
    link: str | None = None,
) -> dict:
    return {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": "", "rendered": ""},
        "meta": {"article_subtype": "postgame"},
        "modified": "2026-04-26T06:55:00",
        "status": status,
        "link": link or f"https://yoshilover.com/{post_id}",
        "categories": [],
        "tags": [],
    }


def _report(*, green=None, yellow=None, red=None, cleanup_candidates=None) -> dict:
    return {
        "scan_meta": {"window_hours": 96, "max_pool": 10, "scanned": 0, "ts": FIXED_NOW.isoformat()},
        "green": list(green or []),
        "yellow": list(yellow or []),
        "red": list(red or []),
        "cleanup_candidates": list(cleanup_candidates or []),
        "summary": {},
    }


class FakeWPClient:
    def __init__(self, posts: dict[int, dict]):
        self.posts = posts
        self.get_post_calls: list[int] = []
        self.update_post_fields_calls: list[tuple[int, dict]] = []
        self.update_post_status_calls: list[tuple[int, str]] = []

    def get_post(self, post_id: int) -> dict:
        self.get_post_calls.append(post_id)
        return json.loads(json.dumps(self.posts[post_id], ensure_ascii=False))

    def update_post_fields(self, post_id: int, **fields) -> None:
        self.update_post_fields_calls.append((post_id, fields))

    def update_post_status(self, post_id: int, status: str) -> None:
        self.update_post_status_calls.append((post_id, status))


class GuardedPublishRunnerTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_dry_run_keeps_wp_write_zero(self):
        post = _post(
            101,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合を作り、岡本和真が終盤に決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(green=[{"post_id": 101, "title": post["title"]["raw"]}])
        wp = FakeWPClient({101: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                max_burst=3,
                wp_client=wp,
                history_path=Path(tmpdir) / "history.jsonl",
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["proposed_count"], 1)
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_gate_refuses_live_without_daily_cap_allow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            with self.assertRaises(runner.GuardedPublishAbortError):
                runner.run_guarded_publish(
                    input_from=path,
                    live=True,
                    max_burst=3,
                    daily_cap_allow=False,
                    now=FIXED_NOW,
                )

    def test_gate_refuses_max_burst_over_three(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            with self.assertRaises(runner.GuardedPublishAbortError):
                runner.run_guarded_publish(
                    input_from=path,
                    max_burst=4,
                    now=FIXED_NOW,
                )

    def test_cli_live_without_daily_cap_allow_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                exit_code = cli.main(
                    [
                        "--input-from",
                        str(path),
                        "--max-burst",
                        "3",
                        "--live",
                    ]
                )
        self.assertEqual(exit_code, 1)
        self.assertIn("--live requires --daily-cap-allow", stderr.getvalue())

    def test_backup_creation_path_and_content(self):
        post = _post(
            202,
            "巨人がヤクルトに4-1で勝利",
            (
                "<p>巨人がヤクルトに4-1で勝利した。先発投手が序盤から流れを作り、打線も中盤に加点した。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(green=[{"post_id": 202, "title": post["title"]["raw"]}])
        wp = FakeWPClient({202: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backups" / "wp_publish"
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                max_burst=3,
                daily_cap_allow=True,
                backup_dir=backup_dir,
                history_path=history_path,
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

            executed = result["executed"][0]
            backup_path = Path(executed["backup_path"])
            payload = json.loads(backup_path.read_text(encoding="utf-8"))

        self.assertEqual(backup_path.relative_to(backup_dir).parts[0], "2026-04-26")
        self.assertEqual(backup_path.name, "post_202_20260425T230000.json")
        self.assertEqual(
            sorted(payload.keys()),
            sorted(["id", "status", "title", "content", "excerpt", "meta", "modified", "link", "fetched_at"]),
        )
        self.assertEqual(payload["id"], 202)
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(wp.update_post_status_calls, [(202, "publish")])

    def test_heading_sentence_cleanup_converts_h3_to_p(self):
        body_html = (
            "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で流れを作り、打線も序盤から先手を取った。</p>"
            "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(301, "巨人が中日に5-1で勝利", body_html)
        plan = runner._build_plan(
            post,
            judgment="green",
            yellow_reasons=[],
            cleanup_candidate={"cleanup_types": ["heading_sentence_as_h3"]},
        )

        self.assertIn("<p>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</p>", plan["cleaned_html"])
        self.assertNotIn("<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>", plan["cleaned_html"])
        self.assertEqual(plan["cleanup_plan"][0]["type"], "heading_sentence_as_h3")

    def test_dev_log_contamination_clear_pre_block_is_removed(self):
        body_html = (
            "<p>巨人が広島に3-1で勝利した。先発が試合を作り、打線も追加点を重ねた。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<pre>"
            "python3 -m src.tools.run_guarded_publish\n"
            "git diff --stat\n"
            "commit_hash=abc12345\n"
            "changed_files=3\n"
            "tokens used: 10\n"
            "</pre>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(302, "巨人が広島に3-1で勝利", body_html)
        plan = runner._build_plan(
            post,
            judgment="green",
            yellow_reasons=[],
            cleanup_candidate={"cleanup_types": ["dev_log_contamination"]},
        )

        self.assertNotIn("python3 -m src.tools.run_guarded_publish", plan["cleaned_html"])
        self.assertEqual(plan["cleanup_plan"][0]["type"], "dev_log_contamination")

    def test_cleanup_ambiguous_is_refused(self):
        body_html = (
            "<p>巨人がDeNAに4-2で勝利した。中盤に勝ち越し、継投でも逃げ切った。</p>"
            "<p>python3 -m src.tools.run_guarded_publish</p>"
            "<p>changed_files=3</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(303, "巨人がDeNAに4-2で勝利", body_html)

        with self.assertRaises(runner.CandidateRefusedError) as ctx:
            runner._build_plan(
                post,
                judgment="green",
                yellow_reasons=[],
                cleanup_candidate={"cleanup_types": ["dev_log_contamination"]},
            )

        self.assertEqual(ctx.exception.reason, "cleanup_ambiguous")

    def test_post_cleanup_abort_when_prose_too_short(self):
        body_html = (
            "<p>巨人が勝った。</p>"
            "<pre>"
            "python3 -m src.tools.run_guarded_publish\n"
            "git diff --stat\n"
            "commit_hash=abc12345\n"
            "changed_files=3\n"
            "tokens used: 10\n"
            "</pre>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(304, "巨人が阪神に1-0で勝利", body_html)

        with self.assertRaises(runner.CandidateRefusedError) as ctx:
            runner._build_plan(
                post,
                judgment="green",
                yellow_reasons=[],
                cleanup_candidate={"cleanup_types": ["dev_log_contamination"]},
            )

        self.assertEqual(ctx.exception.reason, "post_cleanup_abort")
        self.assertIn("prose_lt_100", ctx.exception.detail)

    def test_post_cleanup_abort_when_title_subject_disappears(self):
        body_html = (
            "<p>阪神戦で勝ち越し打が飛び出し、終盤の一打で流れを引き寄せた。</p>"
            "<pre>"
            "岡本和真は今日も決勝打\n"
            "python3 -m src.tools.run_guarded_publish\n"
            "git diff --stat\n"
            "commit_hash=abc12345\n"
            "tokens used: 10\n"
            "</pre>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(305, "岡本和真が阪神戦で決勝打", body_html)

        with self.assertRaises(runner.CandidateRefusedError) as ctx:
            runner._build_plan(
                post,
                judgment="green",
                yellow_reasons=[],
                cleanup_candidate={"cleanup_types": ["dev_log_contamination"]},
            )

        self.assertEqual(ctx.exception.reason, "post_cleanup_abort")
        self.assertIn("title_subject_missing", ctx.exception.detail)

    def test_post_cleanup_abort_when_source_disappears(self):
        body_html = (
            "<p>巨人がヤクルトに3-2で勝利した。終盤の一打で試合を決め、継投でも逃げ切った。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<pre>"
            "参照元: スポーツ報知 https://example.com/source\n"
            "python3 -m src.tools.run_guarded_publish\n"
            "git diff --stat\n"
            "commit_hash=abc12345\n"
            "changed_files=3\n"
            "</pre>"
        )
        post = _post(306, "巨人がヤクルトに3-2で勝利", body_html)

        with self.assertRaises(runner.CandidateRefusedError) as ctx:
            runner._build_plan(
                post,
                judgment="green",
                yellow_reasons=[],
                cleanup_candidate={"cleanup_types": ["dev_log_contamination"]},
            )

        self.assertEqual(ctx.exception.reason, "post_cleanup_abort")
        self.assertIn("source_missing", ctx.exception.detail)

    def test_history_dedup_skips_silently(self):
        post = _post(
            401,
            "巨人が勝利",
            (
                "<p>巨人が勝利した。試合を通じて主導権を握り、投打がかみ合った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(green=[{"post_id": 401, "title": post["title"]["raw"]}])
        wp = FakeWPClient({401: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 401,
                        "ts": "2026-04-26T07:00:00+09:00",
                        "status": "sent",
                        "backup_path": "/tmp/backup.json",
                        "error": None,
                        "judgment": "green",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                max_burst=3,
                history_path=history_path,
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"], [])
        self.assertEqual(wp.get_post_calls, [])

    def test_daily_cap_trims_and_stops(self):
        posts = {
            501: _post(501, "巨人が阪神に3-2で勝利", f"<p>巨人が阪神に3-2で勝利した。投打が噛み合い、終盤まで試合を支配した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            502: _post(502, "巨人が中日に4-1で勝利", f"<p>巨人が中日に4-1で勝利した。先発が試合をつくり、打線も中盤に追加点を挙げた。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            503: _post(503, "巨人が広島に5-3で勝利", f"<p>巨人が広島に5-3で勝利した。中盤に逆転し、その後も継投で逃げ切った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
        }
        report = _report(
            green=[
                {"post_id": 501, "title": posts[501]["title"]["raw"]},
                {"post_id": 502, "title": posts[502]["title"]["raw"]},
                {"post_id": 503, "title": posts[503]["title"]["raw"]},
            ]
        )
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_lines = []
            for index in range(9):
                history_lines.append(
                    json.dumps(
                        {
                            "post_id": 800 + index,
                            "ts": "2026-04-26T01:00:00+09:00",
                            "status": "sent",
                            "backup_path": "/tmp/backup.json",
                            "error": None,
                            "judgment": "green",
                        },
                        ensure_ascii=False,
                    )
                )
            history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                max_burst=3,
                history_path=history_path,
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [501])
        self.assertEqual(
            [item["reason"] for item in result["refused"]],
            ["daily_cap", "daily_cap"],
        )

    def test_live_skipped_entries_are_logged_for_daily_and_burst_caps(self):
        posts = {
            511: _post(511, "巨人が阪神に3-2で勝利", f"<p>巨人が阪神に3-2で勝利した。投打が噛み合い、終盤まで試合を支配した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            512: _post(512, "巨人が中日に4-1で勝利", f"<p>巨人が中日に4-1で勝利した。先発が試合をつくり、打線も中盤に追加点を挙げた。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
        }
        report = _report(
            green=[
                {"post_id": 511, "title": posts[511]["title"]["raw"]},
                {"post_id": 512, "title": posts[512]["title"]["raw"]},
            ]
        )
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            for index in range(10):
                status = "sent" if index < 9 else "refused"
                with history_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "post_id": 900 + index,
                                "ts": "2026-04-26T02:00:00+09:00",
                                "status": status,
                                "backup_path": None,
                                "error": None if status == "sent" else "fail",
                                "judgment": "green",
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                max_burst=1,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "backups",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(result["executed"][0]["status"], "skipped")
        self.assertEqual(result["executed"][1]["status"], "skipped")
        self.assertEqual(rows[-2]["status"], "skipped")
        self.assertEqual(rows[-1]["status"], "skipped")

    def test_yellow_publish_writes_yellow_log(self):
        post = _post(
            601,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が試合をつくり、岡本和真が終盤に勝ち越し打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            yellow=[
                {
                    "post_id": 601,
                    "title": post["title"]["raw"],
                    "yellow_reasons": ["missing_featured_media"],
                }
            ]
        )
        wp = FakeWPClient({601: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                max_burst=3,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "backups",
                yellow_log_path=yellow_log_path,
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(
            sorted(row.keys()),
            sorted(["post_id", "ts", "title", "yellow_reasons", "publish_link"]),
        )
        self.assertEqual(row["yellow_reasons"], ["missing_featured_media"])

    def test_cleanup_log_records_before_after_reason(self):
        body_html = (
            "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で試合を作り、岡本和真が先制打を放った。</p>"
            "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
            "<p>終盤まで継投も安定し、内容を整理できる一戦だった。</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(602, "巨人が中日に5-1で勝利", body_html)
        report = _report(
            green=[{"post_id": 602, "title": post["title"]["raw"]}],
            cleanup_candidates=[
                {
                    "post_id": 602,
                    "cleanup_types": ["heading_sentence_as_h3"],
                    "post_judgment": "green",
                }
            ],
        )
        wp = FakeWPClient({602: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                max_burst=3,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "backups",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(sorted(row.keys()), sorted(["post_id", "ts", "cleanups", "publish_link"]))
        self.assertEqual(row["cleanups"][0]["type"], "heading_sentence_as_h3")
        self.assertIn("<h3>", row["cleanups"][0]["before"])
        self.assertIn("<p>", row["cleanups"][0]["after"])

    def test_history_log_records_sent_and_refused(self):
        ok_post = _post(
            701,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合を作り、岡本和真が決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        bad_post = _post(
            702,
            "巨人が勝利",
            "<p>短い本文。</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(
            green=[
                {"post_id": 701, "title": ok_post["title"]["raw"]},
                {"post_id": 702, "title": bad_post["title"]["raw"]},
            ]
        )
        wp = FakeWPClient({701: ok_post, 702: bad_post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                max_burst=3,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "backups",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual([item["status"] for item in result["executed"]], ["refused", "sent"])
        self.assertEqual(rows[0]["status"], "refused")
        self.assertEqual(rows[0]["judgment"], "green")
        self.assertEqual(rows[1]["status"], "sent")
        self.assertEqual(rows[1]["judgment"], "green")


if __name__ == "__main__":
    unittest.main()
