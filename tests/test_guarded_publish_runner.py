import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta
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


def _green_entry(post_id: int, title: str) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "category": "clean",
        "publishable": True,
        "cleanup_required": False,
        "repairable_flags": [],
    }


def _repairable_entry(post_id: int, title: str, *flags: str, yellow_reasons=None, cleanup_required: bool = True) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "category": "repairable",
        "publishable": True,
        "cleanup_required": cleanup_required,
        "repairable_flags": list(flags),
        "yellow_reasons": list(yellow_reasons or []),
    }


def _hard_stop_entry(post_id: int, title: str, *flags: str) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "category": "hard_stop",
        "publishable": False,
        "cleanup_required": False,
        "hard_stop_flags": list(flags),
        "red_flags": list(flags),
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
        post = self.posts[post_id]
        if "status" in fields:
            post["status"] = fields["status"]
        if "content" in fields:
            post["content"] = {"raw": fields["content"], "rendered": fields["content"]}
        if "meta" in fields:
            post["meta"] = dict(fields["meta"])

    def update_post_status(self, post_id: int, status: str) -> None:
        self.update_post_status_calls.append((post_id, status))
        self.posts[post_id]["status"] = status


class GuardedPublishRunnerTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _write_verdict(self, tmpdir: str, payload: list[dict]) -> Path:
        path = Path(tmpdir) / "verdict.json"
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
        report = _report(green=[_green_entry(101, post["title"]["raw"])])
        wp = FakeWPClient({101: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
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
                    daily_cap_allow=False,
                    now=FIXED_NOW,
                )

    def test_cap_hard_30_above_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                exit_code = cli.main(
                    [
                        "--input-from",
                        str(path),
                        "--max-burst",
                        "31",
                    ]
                )
        self.assertEqual(exit_code, 1)
        self.assertIn("--max-burst must be <= 30", stderr.getvalue())

    def test_cli_live_without_daily_cap_allow_returns_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_input(tmpdir, _report())
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                exit_code = cli.main(
                    [
                        "--input-from",
                        str(path),
                        "--live",
                    ]
                )
        self.assertEqual(exit_code, 1)
        self.assertIn("--live requires --daily-cap-allow", stderr.getvalue())

    def test_cap_default_20_burst_enforced(self):
        posts = {
            900 + index: _post(
                900 + index,
                f"巨人が試合{index + 1}に勝利",
                (
                    f"<p>巨人が試合{index + 1}に勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p>"
                    f"<p>{LONG_EXTRA}</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source</p>"
                ),
            )
            for index in range(21)
        }
        report = _report(green=[_green_entry(post_id, post["title"]["raw"]) for post_id, post in posts.items()])
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        sent = [item for item in result["executed"] if item["status"] == "sent"]
        skipped = [item for item in result["executed"] if item["status"] == "skipped"]
        self.assertEqual(len(sent), 20)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(result["refused"][-1]["reason"], "burst_cap")
        self.assertEqual([row["hold_reason"] for row in rows if row["status"] == "skipped"], ["burst_cap"])

    def test_daily_cap_100_enforced(self):
        posts = {
            1001: _post(1001, "巨人が阪神に3-2で勝利", f"<p>巨人が阪神に3-2で勝利した。投打が噛み合い、終盤まで試合を支配した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            1002: _post(1002, "巨人が中日に4-1で勝利", f"<p>巨人が中日に4-1で勝利した。先発が試合をつくり、打線も中盤に追加点を挙げた。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
        }
        report = _report(
            green=[
                _green_entry(1001, posts[1001]["title"]["raw"]),
                _green_entry(1002, posts[1002]["title"]["raw"]),
            ]
        )
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_lines = [
                json.dumps(
                    {
                        "post_id": 1100 + index,
                        "ts": "2026-04-26T01:00:00+09:00",
                        "status": "sent",
                        "backup_path": "/tmp/backup.json",
                        "error": None,
                        "judgment": "green",
                    },
                    ensure_ascii=False,
                )
                for index in range(99)
            ]
            history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        sent = [item for item in result["executed"] if item["status"] == "sent"]
        skipped = [item for item in result["executed"] if item["status"] == "skipped"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(result["refused"][-1]["reason"], "daily_cap")

    def test_daily_cap_counts_sent_only_not_refused(self):
        post = _post(
            1010,
            "巨人が広島に3-1で勝利",
            f"<p>巨人が広島に3-1で勝利した。序盤に主導権を握り、投手陣もリードを守り切った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(1010, post["title"]["raw"])])
        wp = FakeWPClient({1010: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_lines = [
                json.dumps(
                    {
                        "post_id": 1200 + index,
                        "ts": "2026-04-26T01:00:00+09:00",
                        "status": "refused",
                        "backup_path": None,
                        "error": "hard_stop:freshness_window",
                        "judgment": "hard_stop",
                    },
                    ensure_ascii=False,
                )
                for index in range(100)
            ]
            history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(result["refused"], [])

    def test_daily_cap_counts_sent_only_not_skipped(self):
        post = _post(
            1011,
            "巨人がDeNAに2-1で勝利",
            f"<p>巨人がDeNAに2-1で勝利した。終盤の一打で均衡を破り、救援陣もリードを守った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(1011, post["title"]["raw"])])
        wp = FakeWPClient({1011: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_lines = [
                json.dumps(
                    {
                        "post_id": 1300 + index,
                        "ts": "2026-04-26T01:00:00+09:00",
                        "status": "skipped",
                        "backup_path": None,
                        "error": "daily_cap",
                        "judgment": "green",
                        "hold_reason": "daily_cap",
                    },
                    ensure_ascii=False,
                )
                for index in range(100)
            ]
            history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(result["refused"], [])

    def test_recent_refused_history_within_24h_stays_skipped(self):
        post = _post(
            1012,
            "巨人が広島に2-0で勝利",
            f"<p>巨人が広島に2-0で勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(1012, post["title"]["raw"])])
        wp = FakeWPClient({1012: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 1012,
                        "ts": (FIXED_NOW - timedelta(hours=23)).isoformat(),
                        "status": "refused",
                        "backup_path": None,
                        "error": "hard_stop:freshness_window",
                        "judgment": "hard_stop",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                history_path=history_path,
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["proposed_count"], 0)
        self.assertEqual(result["proposed"], [])
        self.assertEqual(wp.get_post_calls, [])

    def test_old_refused_history_over_24h_can_be_reproposed(self):
        post = _post(
            1013,
            "巨人が中日に3-1で勝利",
            f"<p>巨人が中日に3-1で勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(1013, post["title"]["raw"])])
        wp = FakeWPClient({1013: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 1013,
                        "ts": (FIXED_NOW - timedelta(hours=25)).isoformat(),
                        "status": "refused",
                        "backup_path": None,
                        "error": "hard_stop:freshness_window",
                        "judgment": "hard_stop",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                history_path=history_path,
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["proposed_count"], 1)
        self.assertEqual([item["post_id"] for item in result["proposed"]], [1013])

    def test_sent_history_remains_permanently_skipped(self):
        post = _post(
            1015,
            "巨人がヤクルトに4-2で勝利",
            f"<p>巨人がヤクルトに4-2で勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(1015, post["title"]["raw"])])
        wp = FakeWPClient({1015: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 1015,
                        "ts": "2026-04-20T08:00:00+09:00",
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
                history_path=history_path,
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["proposed_count"], 0)
        self.assertEqual(result["proposed"], [])

    def test_refused_history_with_unparseable_ts_stays_skipped_for_safety(self):
        post = _post(
            1016,
            "巨人が阪神に5-3で勝利",
            f"<p>巨人が阪神に5-3で勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(1016, post["title"]["raw"])])
        wp = FakeWPClient({1016: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 1016,
                        "ts": "not-a-timestamp",
                        "status": "refused",
                        "backup_path": None,
                        "error": "hard_stop:freshness_window",
                        "judgment": "hard_stop",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                history_path=history_path,
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["proposed_count"], 0)
        self.assertEqual(result["proposed"], [])

    def test_daily_cap_current_run_hard_stop_does_not_burn_sent_budget(self):
        post = _post(
            1014,
            "巨人が広島に4-2で勝利",
            f"<p>巨人が広島に4-2で勝利した。中盤に勝ち越し、終盤の継投でも流れを渡さなかった。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(
            green=[_green_entry(1014, post["title"]["raw"])],
            red=[_hard_stop_entry(1500 + index, f"hard stop {index}", "freshness_window") for index in range(100)],
        )
        wp = FakeWPClient({1014: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        sent = [item for item in result["executed"] if item["status"] == "sent"]
        refused = [item for item in result["executed"] if item["status"] == "refused"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(refused), 100)
        self.assertNotIn("daily_cap", [item["reason"] for item in result["refused"]])

    def test_daily_cap_100_sent_blocks_next_sent(self):
        posts = {
            1012: _post(1012, "巨人がヤクルトに5-2で勝利", f"<p>巨人がヤクルトに5-2で勝利した。主砲の一発で流れを引き寄せ、終盤も突き放した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            1013: _post(1013, "巨人が中日に6-3で勝利", f"<p>巨人が中日に6-3で勝利した。序盤から得点を重ね、投手陣も粘って逃げ切った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
        }
        report = _report(
            green=[
                _green_entry(1012, posts[1012]["title"]["raw"]),
                _green_entry(1013, posts[1013]["title"]["raw"]),
            ]
        )
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_lines = [
                json.dumps(
                    {
                        "post_id": 1400 + index,
                        "ts": "2026-04-26T01:00:00+09:00",
                        "status": "sent",
                        "backup_path": "/tmp/backup.json",
                        "error": None,
                        "judgment": "green",
                    },
                    ensure_ascii=False,
                )
                for index in range(100)
            ]
            history_path.write_text("\n".join(history_lines) + "\n", encoding="utf-8")
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual([item["status"] for item in result["executed"]], ["skipped", "skipped"])
        self.assertEqual([item["reason"] for item in result["refused"]], ["daily_cap", "daily_cap"])

    def test_filter_verdict_ok_publishes(self):
        posts = {
            2001: _post(2001, "巨人が阪神に3-2で勝利", f"<p>巨人が阪神に3-2で勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            2002: _post(2002, "巨人が中日に4-1で勝利", f"<p>巨人が中日に4-1で勝利した。先発が試合をつくり、打線も中盤に追加点を挙げた。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
        }
        report = _report(
            green=[
                _green_entry(2001, posts[2001]["title"]["raw"]),
                _green_entry(2002, posts[2002]["title"]["raw"]),
            ]
        )
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                filter_verdict=self._write_verdict(
                    tmpdir,
                    [
                        {"post_id": 2001, "verdict": "ok", "reasons": []},
                        {"post_id": 2002, "verdict": "ng", "reasons": ["duplicate_title"]},
                    ],
                ),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        sent_ids = [item["post_id"] for item in result["executed"] if item["status"] == "sent"]
        self.assertEqual(sent_ids, [2001])
        self.assertEqual(wp.update_post_status_calls, [(2001, "publish")])
        self.assertEqual(result["summary"]["proposed_count"], 1)

    def test_filter_verdict_ng_held_with_reason(self):
        post = _post(
            2101,
            "巨人が広島に3-1で勝利",
            f"<p>巨人が広島に3-1で勝利した。序盤に主導権を握り、投手陣もリードを守り切った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(2101, post["title"]["raw"])])
        wp = FakeWPClient({2101: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                filter_verdict=self._write_verdict(
                    tmpdir,
                    [{"post_id": 2101, "verdict": "ng", "reasons": ["duplicate title"]}],
                ),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "codex_review_ng_duplicate_title")
        self.assertEqual(result["executed"][0]["status"], "skipped")
        self.assertEqual(history_row["status"], "skipped")
        self.assertEqual(history_row["hold_reason"], "codex_review_ng_duplicate_title")
        self.assertEqual(wp.update_post_status_calls, [])

    def test_filter_verdict_missing_post_id_held(self):
        posts = {
            2201: _post(2201, "巨人がヤクルトに5-2で勝利", f"<p>巨人がヤクルトに5-2で勝利した。主砲の一発で流れを引き寄せ、終盤も突き放した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
            2202: _post(2202, "巨人がDeNAに2-1で勝利", f"<p>巨人がDeNAに2-1で勝利した。終盤の一打で均衡を破り、救援陣もリードを守った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>"),
        }
        report = _report(
            green=[
                _green_entry(2201, posts[2201]["title"]["raw"]),
                _green_entry(2202, posts[2202]["title"]["raw"]),
            ]
        )
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                filter_verdict=self._write_verdict(
                    tmpdir,
                    [{"post_id": 2201, "verdict": "ok", "reasons": []}],
                ),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual([item["post_id"] for item in result["executed"] if item["status"] == "sent"], [2201])
        self.assertEqual(result["refused"][0]["hold_reason"], "codex_review_missing_verdict")
        self.assertEqual(rows[0]["hold_reason"], "codex_review_missing_verdict")
        self.assertEqual(rows[0]["status"], "skipped")

    def test_no_filter_verdict_backward_compat(self):
        post = _post(
            2301,
            "巨人が中日に4-1で勝利",
            f"<p>巨人が中日に4-1で勝利した。先発が試合をつくり、打線も中盤に追加点を挙げた。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(2301, post["title"]["raw"])])
        wp = FakeWPClient({2301: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(result["refused"], [])
        self.assertEqual(wp.update_post_status_calls, [(2301, "publish")])

    def test_hard_stop_post_skipped_no_global_abort(self):
        green_post = _post(
            801,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合を作り、岡本和真が決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            green=[_green_entry(801, green_post["title"]["raw"])],
            red=[_hard_stop_entry(800, "巨人の主力が重症で入院", "death_or_grave_incident")],
        )
        wp = FakeWPClient({801: green_post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual([item["status"] for item in result["executed"]], ["refused", "sent"])
        self.assertEqual(rows[0]["hold_reason"], "hard_stop_death_or_grave_incident")
        self.assertEqual(wp.update_post_status_calls, [(801, "publish")])

    def test_roster_movement_yellow_published(self):
        post = _post(
            802,
            "巨人主力が登録抹消 復帰目処を待つ",
            (
                "<p>巨人主力が登録抹消となった。スポーツ報知によると、復帰目処を見極めながら再調整を進める。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source-roster</p>"
            ),
        )
        report = _report(
            yellow=[
                _repairable_entry(
                    802,
                    post["title"]["raw"],
                    "roster_movement_yellow",
                    yellow_reasons=["roster_movement_yellow"],
                    cleanup_required=False,
                )
            ]
        )
        wp = FakeWPClient({802: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=yellow_log_path,
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").splitlines()[-1])
            yellow_row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(history_row["judgment"], "yellow")
        self.assertFalse(history_row["cleanup_required"])
        self.assertIsNone(history_row["cleanup_success"])
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [(802, "publish")])
        self.assertEqual(yellow_row["manual_x_post_block_reason"], "roster_movement_yellow")

    def test_death_grave_incident_refused(self):
        report = _report(red=[_hard_stop_entry(803, "巨人OBの訃報", "death_or_grave_incident")])

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=FakeWPClient({}),
                now=FIXED_NOW,
            )
            row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(row["error"], "hard_stop:death_or_grave_incident")
        self.assertEqual(row["hold_reason"], "hard_stop_death_or_grave_incident")

    def test_yellow_log_records_roster_movement_reason(self):
        post = _post(
            804,
            "巨人若手が一軍昇格 チームに合流",
            (
                "<p>巨人若手が一軍昇格し、チームに合流した。日刊スポーツによると、即戦力として起用が検討されている。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: 日刊スポーツ https://example.com/source-promotion</p>"
            ),
        )
        report = _report(
            yellow=[
                _repairable_entry(
                    804,
                    post["title"]["raw"],
                    "roster_movement_yellow",
                    yellow_reasons=["roster_movement_yellow"],
                    cleanup_required=False,
                )
            ]
        )
        wp = FakeWPClient({804: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=yellow_log_path,
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            yellow_row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(yellow_row["applied_flags"], ["roster_movement_yellow"])
        self.assertFalse(yellow_row["cleanup_required"])
        self.assertTrue(yellow_row["manual_x_post_blocked"])
        self.assertEqual(yellow_row["warning_lines"], ["[Warning] roster movement 系記事、X 自動投稿対象外"])

    def test_repairable_post_cleanup_then_publish(self):
        body_html = (
            "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で今季3勝目を挙げた。</p>"
            "<p>岡本が先制打を放ち、序盤から主導権を握った。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
            "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
            "<pre>"
            "python3 -m src.tools.run_guarded_publish\n"
            "git diff --stat\n"
            "commit_hash=abc12345\n"
            "changed_files=3\n"
            "tokens used: 10\n"
            "</pre>"
        )
        post = _post(301, "巨人が中日に5-1で勝利", body_html)
        report = _report(
            yellow=[
                _repairable_entry(
                    301,
                    post["title"]["raw"],
                    "heading_sentence_as_h3",
                    "dev_log_contamination",
                    yellow_reasons=["heading_sentence_as_h3", "dev_log_contamination"],
                )
            ],
            cleanup_candidates=[
                {
                    "post_id": 301,
                    "cleanup_types": ["heading_sentence_as_h3", "dev_log_contamination"],
                    "repairable_flags": ["heading_sentence_as_h3", "dev_log_contamination"],
                }
            ],
        )
        wp = FakeWPClient({301: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=yellow_log_path,
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())
            yellow_row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(history_row["cleanup_required"], True)
        self.assertEqual(history_row["cleanup_success"], True)
        self.assertIsNone(history_row["hold_reason"])
        self.assertEqual(yellow_row["applied_flags"], ["heading_sentence_as_h3", "dev_log_contamination"])
        self.assertEqual(cleanup_row["applied_flags"], ["heading_sentence_as_h3", "dev_log_contamination"])
        self.assertEqual(wp.update_post_fields_calls[0][0], 301)
        self.assertIn("<p>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</p>", wp.update_post_fields_calls[0][1]["content"])
        self.assertNotIn("python3 -m src.tools.run_guarded_publish", wp.update_post_fields_calls[0][1]["content"])

    def test_heading_sentence_relaxed_warning_only_publishes(self):
        body_html = (
            "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で今季3勝目を挙げた。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
            "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
        )
        post = _post(316, "巨人が中日に5-1で勝利", body_html)
        report = _report(
            yellow=[_repairable_entry(316, post["title"]["raw"], "heading_sentence_as_h3", yellow_reasons=["heading_sentence_as_h3"])],
            cleanup_candidates=[{"post_id": 316, "repairable_flags": ["heading_sentence_as_h3"]}],
        )
        wp = FakeWPClient({316: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [(316, "publish")])
        self.assertEqual(cleanup_row["applied_flags"], ["heading_sentence_as_h3"])
        self.assertEqual(cleanup_row["cleanups"][0]["type"], "heading_sentence_as_h3")
        self.assertEqual(cleanup_row["cleanups"][0]["reason"], "warning_only:relaxed_for_breaking_board")

    def test_weak_source_display_cleanup_appends_source_url(self):
        body_html = (
            "<p>巨人が中日に4-1で勝利した。序盤に主導権を握り、継投でも流れを渡さなかった。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: https://example.com/source</p>"
        )
        post = _post(306, "巨人が中日に4-1で勝利", body_html)
        report = _report(
            yellow=[_repairable_entry(306, post["title"]["raw"], "weak_source_display", yellow_reasons=["missing_primary_source"])],
            cleanup_candidates=[{"post_id": 306, "repairable_flags": ["weak_source_display"]}],
        )
        wp = FakeWPClient({306: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["executed"][0]["status"], "sent")
        cleaned_html = wp.update_post_fields_calls[0][1]["content"]
        self.assertIn('出典: <a href="https://example.com/source">https://example.com/source</a>', cleaned_html)

    def test_long_body_cleanup_trims_above_5000_chars(self):
        repeated = "".join(
            f"<p>巨人が流れを引き寄せた第{index}段落。攻守の切り替えと継投の意図を整理し、打線のつながりも追える内容だった。</p>"
            for index in range(1, 140)
        )
        body_html = repeated + "<p>参照元: スポーツ報知 https://example.com/source</p>"
        post = _post(307, "巨人が流れを引き寄せた", body_html)
        report = _report(
            yellow=[_repairable_entry(307, post["title"]["raw"], "long_body", yellow_reasons=["long_body"])],
            cleanup_candidates=[{"post_id": 307, "repairable_flags": ["long_body"]}],
        )
        wp = FakeWPClient({307: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["executed"][0]["status"], "sent")
        cleaned_html = wp.update_post_fields_calls[0][1]["content"]
        self.assertLess(len(cleaned_html), len(body_html))
        self.assertIn("参照元: スポーツ報知 https://example.com/source", cleaned_html)

    def test_subtype_unresolved_relaxed_warning_only_publishes(self):
        body_html = (
            "<p>巨人ベンチが終盤の狙いを整理した。阿部監督の説明を踏まえ、起用の意図も追える内容だった。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(308, "ベンチの狙いを整理", body_html)
        post["meta"] = {"article_subtype": "other"}
        report = _report(
            yellow=[_repairable_entry(308, post["title"]["raw"], "subtype_unresolved", yellow_reasons=["subtype_unresolved"])],
            cleanup_candidates=[{"post_id": 308, "repairable_flags": ["subtype_unresolved"]}],
        )
        wp = FakeWPClient({308: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [(308, "publish")])
        self.assertEqual(cleanup_row["applied_flags"], ["subtype_unresolved"])
        self.assertEqual(cleanup_row["cleanups"][0]["type"], "subtype_unresolved")
        self.assertEqual(cleanup_row["cleanups"][0]["reason"], "warning_only:relaxed_for_breaking_board")

    def test_light_structure_break_cleanup_regex(self):
        body_html = (
            "<p>巨人が終盤に突き放した。試合の分岐点と継投の意図が見える内容だった。</p>"
            "<p> </p><br><br><p>追加点の意味も整理でき、次戦への視点も残る。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(309, "巨人が終盤に突き放した", body_html)
        report = _report(
            yellow=[_repairable_entry(309, post["title"]["raw"], "light_structure_break", yellow_reasons=["light_structure_break"])],
            cleanup_candidates=[{"post_id": 309, "repairable_flags": ["light_structure_break"]}],
        )
        wp = FakeWPClient({309: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["executed"][0]["status"], "sent")
        cleaned_html = wp.update_post_fields_calls[0][1]["content"]
        self.assertNotIn("<p> </p>", cleaned_html)
        self.assertNotIn("<br><br>", cleaned_html)
        self.assertIn("<br />", cleaned_html)

    def test_unmapped_repairable_flag_held_with_reason(self):
        body_html = (
            "<p>巨人が接戦をものにした。冒頭で試合の核が分かり、投打の流れも追える内容だった。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(310, "巨人が接戦をものにした", body_html)
        report = _report(
            yellow=[_repairable_entry(310, post["title"]["raw"], "totally_unmapped_flag", yellow_reasons=["totally_unmapped_flag"])],
            cleanup_candidates=[{"post_id": 310, "repairable_flags": ["totally_unmapped_flag"]}],
        )
        wp = FakeWPClient({310: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(result["executed"][0]["hold_reason"], "cleanup_action_unmapped")
        self.assertEqual(history_row["hold_reason"], "cleanup_action_unmapped")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_ai_tone_repairable_warning_only_publishes(self):
        body_html = (
            "<p>注目したいのは継投のタイミングだ。巨人が終盤まで主導権を握り、試合の核も十分に追える。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(311, "巨人はどう動く？継投の狙い", body_html)
        report = _report(
            yellow=[_repairable_entry(311, post["title"]["raw"], "ai_tone_heading_or_lead", yellow_reasons=["speculative_title"])],
            cleanup_candidates=[{"post_id": 311, "repairable_flags": ["ai_tone_heading_or_lead"]}],
        )
        wp = FakeWPClient({311: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [(311, "publish")])
        self.assertEqual(cleanup_row["cleanups"][0]["type"], "ai_tone_heading_or_lead")

    def test_freshness_repairable_no_op_publishes_and_logs_observation(self):
        body_html = (
            "<p>巨人が阪神に3-2で勝利した。終盤の継投まで整理され、試合の核も十分に追える。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(312, "巨人が阪神に3-2で勝利", body_html)
        report = _report(yellow=[_repairable_entry(312, post["title"]["raw"], "stale_for_breaking_board")])
        wp = FakeWPClient({312: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [(312, "publish")])
        self.assertEqual(cleanup_row["applied_flags"], ["stale_for_breaking_board"])
        self.assertEqual(cleanup_row["cleanups"][0]["type"], "stale_for_breaking_board")
        self.assertEqual(cleanup_row["cleanups"][0]["reason"], "warning_only:freshness_audit_only_no_op")

    def test_repairable_post_cleanup_failed_post_condition_held_prose_short(self):
        short_prose = "巨人が阪神に1-0で勝利した。" + ("あ" * 34)
        post = _post(
            302,
            "巨人が阪神に1-0で勝利",
            (
                f"<p>{short_prose}</p>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "tokens used: 10\n"
                "</pre>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(302, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 302, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({302: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(result["executed"][0]["hold_reason"], "cleanup_failed_post_condition")
        self.assertEqual(history_row["hold_reason"], "cleanup_failed_post_condition")
        self.assertEqual(history_row["error"], "prose_lt_100")
        self.assertTrue(history_row["backup_path"])
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_repairable_post_cleanup_50_chars_publishes(self):
        prose = "巨人が阪神に1-0で勝利した。" + ("あ" * 35)
        post = _post(
            313,
            "巨人が阪神に1-0で勝利",
            (
                f"<p>{prose}</p>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "tokens used: 10\n"
                "</pre>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(313, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 313, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({313: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_fields_calls[0][0], 313)
        self.assertEqual(wp.update_post_fields_calls[0][1]["status"], "publish")
        self.assertNotIn("<pre>", wp.update_post_fields_calls[0][1]["content"])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_repairable_post_cleanup_80_chars_publishes(self):
        prose = "巨人が阪神に1-0で勝利した。" + ("あ" * 65)
        post = _post(
            314,
            "巨人が阪神に1-0で勝利",
            (
                f"<p>{prose}</p>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "tokens used: 10\n"
                "</pre>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(314, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 314, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({314: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_fields_calls[0][0], 314)
        self.assertEqual(wp.update_post_fields_calls[0][1]["status"], "publish")
        self.assertNotIn("<pre>", wp.update_post_fields_calls[0][1]["content"])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_repairable_post_cleanup_env_override_allows_40_chars(self):
        prose = "巨人が阪神に1-0で勝利した。" + ("あ" * 25)
        post = _post(
            315,
            "巨人が阪神に1-0で勝利",
            (
                f"<p>{prose}</p>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "tokens used: 10\n"
                "</pre>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(315, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 315, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({315: post})

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict("os.environ", {"MIN_PROSE_AFTER_CLEANUP": "30"}, clear=False):
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_fields_calls[0][0], 315)
        self.assertEqual(wp.update_post_fields_calls[0][1]["status"], "publish")
        self.assertNotIn("<pre>", wp.update_post_fields_calls[0][1]["content"])
        self.assertEqual(wp.update_post_status_calls, [])

    def test_post_cleanup_title_subject_missing_warning_only_by_default(self):
        post = _post(
            317,
            "岡本和真が阪神戦で決勝打",
            (
                "<p>阪神戦で勝ち越し打が飛び出し、終盤の一打で流れを引き寄せた。</p>"
                "<pre>岡本和真は今日も決勝打</pre>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        cleaned_html = (
            "<p>阪神戦で勝ち越し打が飛び出し、終盤の一打で流れを引き寄せた。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )

        ok, result = runner._post_cleanup_check(post, cleaned_html)

        self.assertTrue(ok)
        self.assertEqual(result, "warning_only:title_subject_missing")

    def test_post_cleanup_title_subject_missing_strict_rejects(self):
        post = _post(
            318,
            "岡本和真が阪神戦で決勝打",
            (
                "<p>阪神戦で勝ち越し打が飛び出し、終盤の一打で流れを引き寄せた。</p>"
                "<pre>岡本和真は今日も決勝打</pre>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        cleaned_html = (
            "<p>阪神戦で勝ち越し打が飛び出し、終盤の一打で流れを引き寄せた。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )

        with patch.dict("os.environ", {"STRICT_TITLE_SUBJECT": "true"}, clear=False):
            ok, result = runner._post_cleanup_check(post, cleaned_html)

        self.assertFalse(ok)
        self.assertEqual(result, "title_subject_missing")

    def test_post_cleanup_source_anchor_missing_warning_only_by_default(self):
        post = _post(
            319,
            "巨人がヤクルトに3-2で勝利",
            (
                "<p>巨人がヤクルトに3-2で勝利した。終盤の一打で試合を決め、継投でも逃げ切った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<pre>参照元: スポーツ報知 https://example.com/source</pre>"
            ),
        )
        cleaned_html = (
            "<p>巨人がヤクルトに3-2で勝利した。終盤の一打で試合を決め、継投でも逃げ切った。</p>"
            f"<p>{LONG_EXTRA}</p>"
        )

        ok, result = runner._post_cleanup_check(post, cleaned_html)

        self.assertTrue(ok)
        self.assertEqual(result, "warning_only:source_anchor_missing")

    def test_post_cleanup_source_anchor_missing_strict_rejects(self):
        post = _post(
            320,
            "巨人がヤクルトに3-2で勝利",
            (
                "<p>巨人がヤクルトに3-2で勝利した。終盤の一打で試合を決め、継投でも逃げ切った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<pre>参照元: スポーツ報知 https://example.com/source</pre>"
            ),
        )
        cleaned_html = (
            "<p>巨人がヤクルトに3-2で勝利した。終盤の一打で試合を決め、継投でも逃げ切った。</p>"
            f"<p>{LONG_EXTRA}</p>"
        )

        with patch.dict("os.environ", {"STRICT_SOURCE_ANCHOR": "true"}, clear=False):
            ok, result = runner._post_cleanup_check(post, cleaned_html)

        self.assertFalse(ok)
        self.assertEqual(result, "source_anchor_missing")

    def test_post_cleanup_source_hosts_mismatch_warning_only_by_default(self):
        post = _post(
            321,
            "巨人が広島に4-2で勝利",
            (
                "<p>巨人が広島に4-2で勝利した。中盤に勝ち越し、終盤の継投でも流れを渡さなかった。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        cleaned_html = (
            "<p>巨人が広島に4-2で勝利した。中盤に勝ち越し、終盤の継投でも流れを渡さなかった。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://other.example.net/source</p>"
        )

        ok, result = runner._post_cleanup_check(post, cleaned_html)

        self.assertTrue(ok)
        self.assertEqual(result, "warning_only:source_url_missing")

    def test_post_cleanup_source_hosts_mismatch_strict_rejects(self):
        post = _post(
            322,
            "巨人が広島に4-2で勝利",
            (
                "<p>巨人が広島に4-2で勝利した。中盤に勝ち越し、終盤の継投でも流れを渡さなかった。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        cleaned_html = (
            "<p>巨人が広島に4-2で勝利した。中盤に勝ち越し、終盤の継投でも流れを渡さなかった。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://other.example.net/source</p>"
        )

        with patch.dict("os.environ", {"STRICT_SOURCE_HOSTS": "true"}, clear=False):
            ok, result = runner._post_cleanup_check(post, cleaned_html)

        self.assertFalse(ok)
        self.assertEqual(result, "source_url_missing")

    def test_repairable_post_cleanup_source_lost_warning_only_publishes(self):
        post = _post(
            303,
            "巨人がヤクルトに3-2で勝利",
            (
                "<p>巨人がヤクルトに3-2で勝利した。終盤の一打で試合を決め、継投でも逃げ切った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<pre>"
                "参照元: スポーツ報知 https://example.com/source\n"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "</pre>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(303, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 303, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({303: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertIsNone(history_row["hold_reason"])
        self.assertEqual(wp.update_post_fields_calls[0][0], 303)
        self.assertIn("source_anchor_missing", [item["type"] for item in cleanup_row["cleanups"]])

    def test_repairable_post_cleanup_title_subject_lost_warning_only_publishes(self):
        post = _post(
            304,
            "岡本和真が阪神戦で決勝打",
            (
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
            ),
        )
        report = _report(
            yellow=[_repairable_entry(304, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 304, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({304: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            cleanup_log_path = Path(tmpdir) / "cleanup.jsonl"
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=history_path,
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=cleanup_log_path,
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())
            cleanup_row = json.loads(cleanup_log_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertIsNone(history_row["hold_reason"])
        self.assertEqual(wp.update_post_fields_calls[0][0], 304)
        self.assertIn("title_subject_missing", [item["type"] for item in cleanup_row["cleanups"]])

    def test_postcheck_every_10_posts_round_trip(self):
        posts = {
            1200 + index: _post(
                1200 + index,
                f"巨人が第{index + 1}戦に勝利",
                (
                    f"<p>巨人が第{index + 1}戦に勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p>"
                    f"<p>{LONG_EXTRA}</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source</p>"
                ),
            )
            for index in range(11)
        }
        report = _report(green=[_green_entry(post_id, post["title"]["raw"]) for post_id, post in posts.items()])
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=True,
                daily_cap_allow=True,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=wp,
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["postcheck_batch_count"], 2)
        self.assertEqual([batch["post_ids"] for batch in result["postcheck_batches"]], [list(range(1200, 1210)), [1210]])
        self.assertEqual(len(wp.get_post_calls), 22)

    def test_backup_required_before_cleanup_failure_holds(self):
        body_html = (
            "<p>巨人が中日に5-1で勝利した。戸郷が7回1失点で今季3勝目を挙げた。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
            "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
        )
        post = _post(305, "巨人が中日に5-1で勝利", body_html)
        report = _report(
            yellow=[_repairable_entry(305, post["title"]["raw"], "heading_sentence_as_h3", yellow_reasons=["heading_sentence_as_h3"])],
            cleanup_candidates=[{"post_id": 305, "cleanup_types": ["heading_sentence_as_h3"]}],
        )
        wp = FakeWPClient({305: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            with patch("src.guarded_publish_runner.create_publish_backup", side_effect=runner.BackupError("boom")):
                result = runner.run_guarded_publish(
                    input_from=self._write_input(tmpdir, report),
                    live=True,
                    daily_cap_allow=True,
                    history_path=history_path,
                    backup_dir=Path(tmpdir) / "cleanup_backup",
                    yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                    cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                    wp_client=wp,
                    now=FIXED_NOW,
                )
            history_row = json.loads(history_path.read_text(encoding="utf-8").strip())

        self.assertEqual(result["executed"][0]["status"], "refused")
        self.assertEqual(result["executed"][0]["hold_reason"], "cleanup_backup_failed")
        self.assertEqual(history_row["hold_reason"], "cleanup_backup_failed")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])


if __name__ == "__main__":
    unittest.main()
