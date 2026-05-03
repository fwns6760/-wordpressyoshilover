import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import guarded_publish_runner as runner
from src import publish_notice_email_sender as notice_sender
from src.tools import run_guarded_publish as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T08:00:00+09:00")
LONG_EXTRA = (
    "ベンチワークの意図や終盤の継投まで追える内容で、攻守の流れも十分に整理できる一戦だった。"
    "守備位置の動きと追加点の意味も見え、ファン視点でも試合の核を追いやすかった。"
)
WIDGET_SCRIPT_URL = "https://platform.twitter.com/widgets.js"


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    status: str = "draft",
    link: str | None = None,
    subtype: str = "postgame",
    meta: dict | None = None,
) -> dict:
    post_meta = {"article_subtype": subtype}
    if meta:
        post_meta.update(meta)
    return {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": "", "rendered": ""},
        "meta": post_meta,
        "modified": "2026-04-26T06:55:00",
        "status": status,
        "link": link or f"https://yoshilover.com/{post_id}",
        "categories": [],
        "tags": [],
    }


def _green_entry(post_id: int, title: str, **overrides) -> dict:
    payload = {
        "post_id": post_id,
        "title": title,
        "category": "clean",
        "publishable": True,
        "cleanup_required": False,
        "repairable_flags": [],
    }
    payload.update(overrides)
    return payload


def _repairable_entry(
    post_id: int,
    title: str,
    *flags: str,
    yellow_reasons=None,
    cleanup_required: bool = True,
    **overrides,
) -> dict:
    payload = {
        "post_id": post_id,
        "title": title,
        "category": "repairable",
        "publishable": True,
        "cleanup_required": cleanup_required,
        "repairable_flags": list(flags),
        "yellow_reasons": list(yellow_reasons or []),
    }
    payload.update(overrides)
    return payload


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


def _review_entry(post_id: int, title: str, *flags: str) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "category": "review",
        "publishable": False,
        "cleanup_required": False,
        "review_flags": list(flags),
    }


def _report(*, green=None, yellow=None, review=None, red=None, cleanup_candidates=None) -> dict:
    return {
        "scan_meta": {"window_hours": 96, "max_pool": 10, "scanned": 0, "ts": FIXED_NOW.isoformat()},
        "green": list(green or []),
        "yellow": list(yellow or []),
        "review": list(review or []),
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
        self.publish_post_calls: list[tuple[int, dict]] = []
        self.list_posts_calls: list[dict] = []

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

    def publish_post(
        self,
        post_id: int,
        *,
        caller: str,
        source_lane: str,
        status_before: str | None = None,
        update_fields: dict | None = None,
    ) -> None:
        self.publish_post_calls.append(
            (
                post_id,
                {
                    "caller": caller,
                    "source_lane": source_lane,
                    "status_before": status_before,
                    "update_fields": dict(update_fields or {}),
                },
            )
        )
        if update_fields:
            self.update_post_fields(post_id, status="publish", **update_fields)
        else:
            self.update_post_status(post_id, "publish")

    def list_posts(
        self,
        status: str = "draft",
        per_page: int = 20,
        page: int = 1,
        orderby: str = "modified",
        order: str = "desc",
        search: str = "",
        context: str | None = "edit",
        fields: list[str] | None = None,
    ) -> list[dict]:
        self.list_posts_calls.append(
            {
                "status": status,
                "per_page": per_page,
                "page": page,
                "orderby": orderby,
                "order": order,
                "search": search,
                "context": context,
                "fields": list(fields or []),
            }
        )
        rows = []
        for post in self.posts.values():
            row_status = str((post or {}).get("status") or "").strip().lower()
            if status != "any" and row_status != status:
                continue
            rows.append(json.loads(json.dumps(post, ensure_ascii=False)))
        reverse = order.lower() != "asc"
        rows.sort(key=lambda item: str(item.get(orderby) or ""), reverse=reverse)
        start = max(0, (max(1, page) - 1) * per_page)
        end = start + max(1, per_page)
        return rows[start:end]


class GuardedPublishRunnerTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _write_verdict(self, tmpdir: str, payload: list[dict]) -> Path:
        path = Path(tmpdir) / "verdict.json"
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
    ) -> dict:
        article_source_url = source_url or f"https://example.com/{subtype}-{post_id}"
        body_html = (
            f"<p>{title}について整理した。</p>"
            f"<p>{LONG_EXTRA}</p>"
            f"<p>参照元: スポーツ報知 {article_source_url}</p>"
        )
        return _post(
            post_id,
            title,
            body_html,
            status=status,
            subtype=subtype,
            meta=meta,
        )

    def _make_duplicate_source_post(
        self,
        post_id: int,
        title: str,
        *,
        subtype: str,
        source_urls: list[str] | None = None,
        status: str = "draft",
        meta: dict | None = None,
    ) -> dict:
        normalized_source_urls = list(source_urls or [WIDGET_SCRIPT_URL])
        source_lines = "".join(f"<p>参照元: スポーツ報知 {url}</p>" for url in normalized_source_urls)
        post_meta = dict(meta or {})
        post_meta["source_url"] = normalized_source_urls if len(normalized_source_urls) > 1 else normalized_source_urls[0]
        return _post(
            post_id,
            title,
            f"<p>{title}について整理した。</p><p>{LONG_EXTRA}</p>{source_lines}",
            status=status,
            subtype=subtype,
            meta=post_meta,
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

    def _run_report(self, report: dict, posts: dict[int, dict], *, live: bool = False) -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            return runner.run_guarded_publish(
                input_from=self._write_input(tmpdir, report),
                live=live,
                daily_cap_allow=live,
                history_path=Path(tmpdir) / "history.jsonl",
                backup_dir=Path(tmpdir) / "cleanup_backup",
                yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                wp_client=FakeWPClient(posts),
                now=FIXED_NOW,
            )

    def _run_duplicate_case(
        self,
        candidate: dict,
        *existing_posts: dict,
        env: dict[str, str] | None = None,
    ) -> tuple[dict, FakeWPClient]:
        posts = {int(candidate["id"]): candidate}
        for existing in existing_posts:
            posts[int(existing["id"])] = existing
        wp = FakeWPClient(posts)
        report = _report(green=[_green_entry(int(candidate["id"]), str(candidate["title"]["raw"]))])

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict("os.environ", env or {}, clear=False):
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

        return result, wp

    def _run_backlog_case(
        self,
        *,
        post_id: int,
        title: str,
        subtype: str,
        age_hours: float,
        extra_posts: dict[int, dict] | None = None,
        backlog_only: bool = True,
        meta: dict | None = None,
        source_url: str | None = None,
        capture_stderr: bool = False,
    ) -> tuple[dict, dict, str]:
        candidate = self._make_candidate_post(post_id, title, subtype=subtype, meta=meta, source_url=source_url)
        posts = {post_id: candidate}
        if extra_posts:
            posts.update(extra_posts)
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
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            if capture_stderr:
                with patch("sys.stderr", stderr):
                    result = runner.run_guarded_publish(
                        input_from=self._write_input(tmpdir, report),
                        live=False,
                        daily_cap_allow=False,
                        history_path=Path(tmpdir) / "history.jsonl",
                        backup_dir=Path(tmpdir) / "cleanup_backup",
                        yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                        cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                        wp_client=FakeWPClient(posts),
                        now=FIXED_NOW,
                    )
            else:
                result = runner.run_guarded_publish(
                    input_from=self._write_input(tmpdir, report),
                    live=False,
                    daily_cap_allow=False,
                    history_path=Path(tmpdir) / "history.jsonl",
                    backup_dir=Path(tmpdir) / "cleanup_backup",
                    yellow_log_path=Path(tmpdir) / "yellow.jsonl",
                    cleanup_log_path=Path(tmpdir) / "cleanup.jsonl",
                    wp_client=FakeWPClient(posts),
                    now=FIXED_NOW,
                )
        return result, candidate, stderr.getvalue()

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

    def test_max_burst_per_run_default_3(self):
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
            for index in range(4)
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
        self.assertEqual(len(sent), 3)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(result["refused"][-1]["reason"], "burst_cap")
        self.assertEqual([row["hold_reason"] for row in rows if row["status"] == "skipped"], ["burst_cap"])

    def test_env_override_max_burst(self):
        posts = {
            950 + index: _post(
                950 + index,
                f"巨人が第{index + 1}戦に勝利",
                (
                    f"<p>巨人が第{index + 1}戦に勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p>"
                    f"<p>{LONG_EXTRA}</p>"
                    "<p>参照元: スポーツ報知 https://example.com/source</p>"
                ),
            )
            for index in range(6)
        }
        report = _report(green=[_green_entry(post_id, post["title"]["raw"]) for post_id, post in posts.items()])
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict("os.environ", {"MAX_BURST_PER_RUN": "5"}, clear=False):
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

        sent = [item for item in result["executed"] if item["status"] == "sent"]
        skipped = [item for item in result["executed"] if item["status"] == "skipped"]
        self.assertEqual(len(sent), 5)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(result["scan_meta"]["max_burst"], 5)

    def test_max_publish_per_hour_caps_at_10(self):
        post = _post(
            980,
            "巨人がヤクルトに3-2で勝利",
            f"<p>巨人がヤクルトに3-2で勝利した。投打が噛み合い、終盤まで試合を支配した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(green=[_green_entry(980, post["title"]["raw"])])
        wp = FakeWPClient({980: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            history_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "post_id": 3000 + index,
                            "ts": (FIXED_NOW - timedelta(minutes=30)).isoformat(),
                            "status": "sent",
                            "backup_path": "/tmp/backup.json",
                            "error": None,
                            "judgment": "green",
                            "is_backlog": False,
                        },
                        ensure_ascii=False,
                    )
                    for index in range(10)
                )
                + "\n",
                encoding="utf-8",
            )
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

        self.assertEqual(result["summary"]["would_publish"], 0)
        self.assertEqual(result["executed"][0]["status"], "skipped")
        self.assertEqual(result["refused"][0]["reason"], "hourly_cap")

    def test_fresh_publish_priority_over_backlog(self):
        fresh_post = _post(
            990,
            "巨人が中日に4-1で勝利",
            f"<p>巨人が中日に4-1で勝利した。試合の核が冒頭で分かり、投打の流れも整理されている。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        backlog_post = _post(
            991,
            "巨人OB戦の振り返り",
            f"<p>巨人OB戦の振り返りを整理した。試合の核が冒頭で分かり、流れも整理されている。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source</p>",
        )
        report = _report(
            green=[
                _green_entry(991, backlog_post["title"]["raw"], freshness_age_hours=12.0),
                _green_entry(990, fresh_post["title"]["raw"], freshness_age_hours=1.5),
            ]
        )
        wp = FakeWPClient({990: fresh_post, 991: backlog_post})

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

        self.assertEqual([item["post_id"] for item in result["proposed"]], [990])
        self.assertIn({"post_id": 991, "reason": "backlog_deferred_for_fresh", "hold_reason": "backlog_deferred_for_fresh"}, result["refused"])

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
        self.assertEqual(len(wp.publish_post_calls), 1)
        self.assertEqual(wp.publish_post_calls[0][1]["caller"], "guarded_publish_runner.run_guarded_publish")
        self.assertEqual(wp.publish_post_calls[0][1]["source_lane"], "guarded_publish")

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

    def test_review_entry_refused_without_publish(self):
        report = _report(
            review=[_review_entry(805, "巨人二軍 3-6 楽天 試合結果", "farm_result_required_facts_weak_review")]
        )

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
        self.assertEqual(result["refused"][0]["hold_reason"], "review_farm_result_required_facts_weak_review")
        self.assertEqual(row["judgment"], "review")
        self.assertEqual(row["error"], "review:farm_result_required_facts_weak_review")
        self.assertEqual(row["hold_reason"], "review_farm_result_required_facts_weak_review")

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
            yellow=[
                _repairable_entry(
                    308,
                    post["title"]["raw"],
                    "subtype_unresolved",
                    yellow_reasons=["subtype_unresolved"],
                    cleanup_required=False,
                    resolved_subtype="default",
                )
            ],
        )
        wp = FakeWPClient({308: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            result = runner.run_guarded_publish(
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

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_status_calls, [])
        self.assertEqual(wp.update_post_fields_calls[0][0], 308)
        self.assertEqual(wp.update_post_fields_calls[0][1]["status"], "publish")
        self.assertEqual(wp.update_post_fields_calls[0][1]["meta"]["article_subtype"], "default")
        self.assertEqual(yellow_row["applied_flags"], ["subtype_unresolved"])
        self.assertEqual(yellow_row["warning_lines"], ["[Warning] subtype unresolved; using default fallback"])

    def test_subtype_unresolved_with_other_cleanup_flag_uses_safe_meta_fallback(self):
        body_html = (
            "<p>主力の動向を整理した。公示で登録と抹消が発表され、ベンチの判断材料も見えてきた。</p>"
            "<p> </p><br><br><p>復帰時期の見立ても含めて全体像を追える内容だった。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source-subtype-combo</p>"
        )
        post = _post(324, "主力の動向を整理", body_html)
        post["meta"] = {"article_subtype": "other"}
        report = _report(
            yellow=[
                _repairable_entry(
                    324,
                    post["title"]["raw"],
                    "subtype_unresolved",
                    "light_structure_break",
                    yellow_reasons=["subtype_unresolved", "light_structure_break"],
                    resolved_subtype="notice",
                )
            ],
            cleanup_candidates=[
                {
                    "post_id": 324,
                    "repairable_flags": ["subtype_unresolved", "light_structure_break"],
                    "cleanup_types": ["light_structure_break"],
                }
            ],
        )
        wp = FakeWPClient({324: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            yellow_log_path = Path(tmpdir) / "yellow.jsonl"
            result = runner.run_guarded_publish(
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

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(wp.update_post_status_calls, [])
        self.assertEqual(wp.update_post_fields_calls[0][1]["status"], "publish")
        self.assertEqual(wp.update_post_fields_calls[0][1]["meta"]["article_subtype"], "notice")
        self.assertEqual(yellow_row["warning_lines"], ["[Warning] subtype unresolved; using notice fallback"])

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

    def test_freshness_source_logged_on_sent_yellow_publish(self):
        body_html = (
            "<p>巨人が阪神に3-2で勝利した。終盤の継投まで整理され、試合の核も十分に追える。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(312, "巨人が阪神に3-2で勝利", body_html)
        report = _report(
            yellow=[
                _repairable_entry(
                    312,
                    post["title"]["raw"],
                    "ai_tone_heading_or_lead",
                    yellow_reasons=["speculative_title"],
                    freshness_source="x_post_date",
                )
            ]
        )
        wp = FakeWPClient({312: post})

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
            yellow_row = json.loads(yellow_log_path.read_text(encoding="utf-8").strip())
            history_rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(result["executed"][0]["status"], "sent")
        self.assertEqual(yellow_row["freshness_source"], "x_post_date")
        self.assertEqual(history_rows[-1]["freshness_source"], "x_post_date")

    def test_backlog_only_skips_per_post_mail(self):
        body_html = (
            "<p>巨人が阪神に3-2で勝利した。終盤の継投まで整理され、試合の核も十分に追える。</p>"
            f"<p>{LONG_EXTRA}</p>"
            "<p>参照元: スポーツ報知 https://example.com/source</p>"
        )
        post = _post(312, "巨人が阪神に3-2で勝利", body_html)
        report = _report(
            yellow=[
                _repairable_entry(
                    312,
                    post["title"]["raw"],
                    "stale_for_breaking_board",
                    freshness_age_hours=120.0,
                    freshness_source="x_post_date",
                    backlog_only=True,
                )
            ]
        )
        wp = FakeWPClient({312: post})

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
                wp_client=wp,
                now=FIXED_NOW,
            )
            history_rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            mail_result = notice_sender.send(
                notice_sender.PublishNoticeRequest(
                    post_id=312,
                    title=post["title"]["raw"],
                    canonical_url=post["link"],
                    subtype="postgame",
                    publish_time_iso=FIXED_NOW.isoformat(),
                    summary="stale entry should stay backlog-only",
                ),
                dry_run=False,
                send_enabled=True,
                bridge_send=MagicMock(),
                guarded_publish_history_path=history_path,
            )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["executed"][0]["status"], "skipped")
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")
        self.assertEqual(history_rows[-1]["is_backlog"], True)
        self.assertEqual(history_rows[-1]["freshness_source"], "x_post_date")
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])
        self.assertEqual(mail_result.status, "suppressed")
        self.assertEqual(mail_result.reason, "BACKLOG_SUMMARY_ONLY")

    def test_backlog_only_postgame_narrow_allowlist_publishes(self):
        result, _, stderr = self._run_backlog_case(
            post_id=4301,
            title="巨人が阪神に3-2で勝利",
            subtype="postgame",
            age_hours=5.0,
            capture_stderr=True,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4301])
        self.assertEqual(result["refused"], [])
        self.assertIn("backlog_narrow_publish_eligible", stderr)
        self.assertIn('"subtype": "postgame"', stderr)
        self.assertIn('"narrow_kind": "allowlist"', stderr)

    def test_backlog_only_game_result_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4302,
            title="巨人が中日に4-1で勝利",
            subtype="game_result",
            age_hours=10.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4302])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_roster_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4303,
            title="巨人が登録入れ替えを発表",
            subtype="roster",
            age_hours=15.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4303])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_injury_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4304,
            title="巨人の主力野手がコンディション不良で別メニュー",
            subtype="injury",
            age_hours=8.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4304])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_notice_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4305,
            title="巨人が東京ドームイベントの開催概要を告知",
            subtype="notice",
            age_hours=20.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4305])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_comment_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4306,
            title="阿部監督が試合後に継投を説明",
            subtype="comment",
            age_hours=5.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4306])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_speech_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4307,
            title="巨人OBがラジオで打線の狙いを語る",
            subtype="speech",
            age_hours=10.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4307])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_manager_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4308,
            title="阿部監督が若手起用の意図を明かす",
            subtype="manager",
            age_hours=15.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4308])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_off_field_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4309,
            title="巨人選手が社会貢献活動に参加",
            subtype="off_field",
            age_hours=20.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4309])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_farm_feature_narrow_allowlist_publishes(self):
        result, _, _ = self._run_backlog_case(
            post_id=4310,
            title="巨人2軍の若手特集を整理",
            subtype="farm_feature",
            age_hours=8.0,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4310])
        self.assertEqual(result["refused"], [])

    def test_backlog_only_default_recent_unresolved_fallback_publishes(self):
        result, _, stderr = self._run_backlog_case(
            post_id=4320,
            title="巨人の話題を整理",
            subtype="default",
            age_hours=5.0,
            capture_stderr=True,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4320])
        self.assertEqual(result["refused"], [])
        self.assertIn('"narrow_kind": "unresolved_fallback"', stderr)

    def test_backlog_only_other_recent_unresolved_fallback_publishes(self):
        result, _, stderr = self._run_backlog_case(
            post_id=4321,
            title="巨人の動きを整理",
            subtype="other",
            age_hours=10.0,
            capture_stderr=True,
        )

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4321])
        self.assertEqual(result["refused"], [])
        self.assertIn('"narrow_kind": "unresolved_fallback"', stderr)

    def test_backlog_only_default_over_24h_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4322,
            title="巨人の話題を整理",
            subtype="default",
            age_hours=30.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_only_other_over_24h_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4323,
            title="巨人の話題を整理",
            subtype="other",
            age_hours=25.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_narrow_context_marks_postgame_as_allowlist(self):
        candidate = self._make_candidate_post(4324, "巨人が阪神に3-2で勝利", subtype="postgame")
        entry = self._make_backlog_entry(candidate, subtype="postgame", age_hours=5.0)

        context = runner._backlog_narrow_publish_context(entry, now=FIXED_NOW)

        self.assertIsNotNone(context)
        self.assertEqual(context["subtype"], "postgame")
        self.assertEqual(context["narrow_kind"], "allowlist")

    def test_backlog_narrow_context_keeps_recent_lineup_blocked(self):
        candidate = self._make_candidate_post(4325, "巨人スタメン発表 丸佳浩が1番", subtype="lineup")
        entry = self._make_backlog_entry(candidate, subtype="lineup", age_hours=1.0)

        context = runner._backlog_narrow_publish_context(entry, now=FIXED_NOW)

        self.assertIsNone(context)

    def test_backlog_only_lineup_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4311,
            title="巨人スタメン発表 丸佳浩が1番",
            subtype="lineup",
            age_hours=1.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_only_pregame_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4312,
            title="巨人の試合前情報を整理",
            subtype="pregame",
            age_hours=1.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_only_probable_starter_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4313,
            title="巨人の予告先発を整理",
            subtype="probable_starter",
            age_hours=1.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_only_farm_lineup_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4314,
            title="巨人2軍スタメン発表を整理",
            subtype="farm_lineup",
            age_hours=1.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_only_postgame_over_age_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4315,
            title="巨人が接戦を制した一戦を振り返る",
            subtype="postgame",
            age_hours=50.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_only_comment_over_age_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4316,
            title="阿部監督が翌日に試合運びを再度振り返る",
            subtype="comment",
            age_hours=60.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_backlog_only_unknown_subtype_stays_blocked(self):
        result, _, _ = self._run_backlog_case(
            post_id=4317,
            title="巨人の話題を整理",
            subtype="unknown_subtype",
            age_hours=5.0,
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "backlog_only")

    def test_non_backlog_green_entry_still_publishes(self):
        candidate = self._make_candidate_post(4318, "巨人が連勝を伸ばす", subtype="postgame")
        report = _report(green=[_green_entry(4318, candidate["title"]["raw"], freshness_age_hours=1.0)])

        result = self._run_report(report, {4318: candidate})

        self.assertEqual([item["post_id"] for item in result["proposed"]], [4318])
        self.assertEqual(result["refused"], [])

    def test_red_entry_still_holds(self):
        candidate = self._make_candidate_post(4319, "巨人の誤情報記事", subtype="postgame")
        report = _report(red=[_hard_stop_entry(4319, candidate["title"]["raw"], "death_or_grave_incident")])

        result = self._run_report(report, {4319: candidate})

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "hard_stop_death_or_grave_incident")

    def test_backlog_narrow_allowed_entry_still_honors_same_source_url_duplicate_guard(self):
        existing = self._make_candidate_post(
            9310,
            "阿部監督が終盤の継投を説明",
            subtype="comment",
            source_url="https://example.com/comment-shared-source",
            status="publish",
            meta={"speaker_name": "阿部監督"},
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, _, _ = self._run_backlog_case(
            post_id=4320,
            title="阿部監督が試合後に継投を振り返る",
            subtype="comment",
            age_hours=5.0,
            extra_posts={9310: existing},
            meta={"speaker_name": "阿部監督"},
            source_url="https://example.com/comment-shared-source",
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")

    def test_repairable_post_cleanup_failed_post_condition_publishes_warning(self):
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
        self.assertIsNone(result["executed"][0]["hold_reason"])
        self.assertIsNone(history_row["hold_reason"])
        self.assertEqual(history_row["cleanup_success"], False)
        self.assertIsNone(history_row["error"])
        self.assertTrue(history_row["backup_path"])
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(wp.update_post_status_calls, [(302, "publish")])
        self.assertEqual(
            yellow_row["warning_lines"],
            ["[Warning] cleanup_failed_post_condition fallback: prose_lt_100"],
        )
        self.assertEqual(cleanup_row["cleanups"][0]["type"], "cleanup_failed_post_condition")
        self.assertEqual(
            cleanup_row["cleanups"][0]["reason"],
            "warning_only:cleanup_failed_post_condition_fallback:prose_lt_100",
        )

    def test_cleanup_failed_with_empty_body_still_refused(self):
        post = _post(
            323,
            "巨人のメモ",
            (
                "<pre>"
                "python3 -m src.tools.run_guarded_publish\n"
                "git diff --stat\n"
                "commit_hash=abc12345\n"
                "changed_files=3\n"
                "tokens used: 10\n"
                "</pre>"
            ),
        )
        report = _report(
            yellow=[_repairable_entry(323, post["title"]["raw"], "dev_log_contamination", yellow_reasons=["dev_log_contamination"])],
            cleanup_candidates=[{"post_id": 323, "cleanup_types": ["dev_log_contamination"]}],
        )
        wp = FakeWPClient({323: post})

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
        self.assertEqual(history_row["error"], "body_empty")
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

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"MAX_BURST_PER_RUN": "11", "MAX_PUBLISH_PER_HOUR": "11"},
            clear=False,
        ):
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

    def test_duplicate_exact_title_against_existing_publish_holds_for_review(self):
        candidate = _post(
            4001,
            "巨人が阪神に3-2で勝利",
            f"<p>巨人が阪神に3-2で勝利した。先発が粘り、終盤の一打で競り勝った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source-a</p>",
        )
        existing = _post(
            9001,
            "巨人が阪神に3-2で勝利",
            "<p>既に publish 済みの記事。</p><p>参照元: スポーツ報知 https://example.com/source-old</p>",
            status="publish",
        )
        wp = FakeWPClient({4001: candidate, 9001: existing})
        report = _report(green=[_green_entry(4001, candidate["title"]["raw"])])

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

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["reason"], "review")
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_exact_title_match_publish")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9001)
        self.assertEqual(result["refused"][0]["duplicate_reason"], "exact_title_match_publish")
        self.assertEqual(history_row["duplicate_of_post_id"], 9001)
        self.assertEqual(history_row["duplicate_reason"], "exact_title_match_publish")
        self.assertEqual(wp.update_post_status_calls, [])

    def test_duplicate_exact_title_against_existing_draft_holds_for_review(self):
        candidate = _post(
            4002,
            "巨人が広島に4-1で勝利",
            f"<p>巨人が広島に4-1で勝利した。中盤の追加点で主導権を握った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source-b</p>",
        )
        existing = _post(
            9002,
            "巨人が広島に4-1で勝利",
            "<p>別の draft が既にある。</p><p>参照元: スポーツ報知 https://example.com/source-c</p>",
        )
        wp = FakeWPClient({4002: candidate, 9002: existing})
        report = _report(green=[_green_entry(4002, candidate["title"]["raw"])])

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

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_exact_title_match_draft")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9002)
        self.assertEqual(result["refused"][0]["duplicate_reason"], "exact_title_match_draft")
        self.assertEqual(wp.update_post_status_calls, [])

    def test_same_run_first_publish_wins_and_second_title_match_holds(self):
        first = _post(
            4003,
            "巨人スタメン 若手をどう並べたか",
            f"<p>巨人スタメンを整理した。起用意図と並び順の狙いが分かる内容だ。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source-d</p>",
        )
        second = _post(
            4004,
            "巨人スタメン 若手をどう並べたか",
            f"<p>同じタイトルの後続候補。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source-e</p>",
        )
        wp = FakeWPClient({4003: first, 4004: second})
        report = _report(
            green=[
                _green_entry(4003, first["title"]["raw"]),
                _green_entry(4004, second["title"]["raw"]),
            ]
        )

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

        sent_ids = [item["post_id"] for item in result["executed"] if item["status"] == "sent"]
        refused_rows = [item for item in result["refused"] if item["post_id"] == 4004]
        self.assertEqual(sent_ids, [4003])
        self.assertEqual(refused_rows[0]["hold_reason"], "review_duplicate_candidate_run_internal_dup")
        self.assertEqual(refused_rows[0]["duplicate_of_post_id"], 4003)
        self.assertEqual(refused_rows[0]["duplicate_reason"], "run_internal_dup")
        self.assertEqual(wp.update_post_status_calls, [(4003, "publish")])
        self.assertEqual([row["duplicate_reason"] for row in rows if row["post_id"] == 4004], ["run_internal_dup"])

    def test_duplicate_same_source_url_holds_even_when_title_differs(self):
        candidate = _post(
            4005,
            "巨人が勝ち越し打で接戦を制す",
            f"<p>巨人が接戦を制した。終盤の一打が勝敗を分けた。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/shared-source</p>",
        )
        existing = _post(
            9005,
            "巨人が終盤に勝ち越し",
            "<p>source は同じだが title は違う。</p><p>参照元: スポーツ報知 https://example.com/shared-source</p>",
            status="publish",
        )
        wp = FakeWPClient({4005: candidate, 9005: existing})
        report = _report(green=[_green_entry(4005, candidate["title"]["raw"])])

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

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9005)
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")

    def test_widget_script_source_url_helper_matches_allowlist(self):
        self.assertTrue(runner._is_widget_script_source_url(WIDGET_SCRIPT_URL))
        self.assertTrue(runner._is_widget_script_source_url(f"{WIDGET_SCRIPT_URL}?lang=ja"))
        self.assertFalse(runner._is_widget_script_source_url("https://platform.twitter.com/embed.js"))
        self.assertFalse(runner._is_widget_script_source_url("https://example.com/widgets.js"))

    def test_widget_script_only_source_anchor_helper_rejects_mixed_urls(self):
        self.assertTrue(runner._is_widget_script_only_source_anchor([WIDGET_SCRIPT_URL]))
        self.assertFalse(
            runner._is_widget_script_only_source_anchor([WIDGET_SCRIPT_URL, "https://example.com/source"])
        )
        self.assertFalse(runner._is_widget_script_only_source_anchor([]))

    def test_duplicate_widget_script_exempt_flag_off_preserves_same_source_duplicate(self):
        candidate = self._make_duplicate_source_post(
            4014,
            "巨人2軍が終盤に勝ち越して逃げ切る",
            subtype="farm_result",
        )
        existing = self._make_duplicate_source_post(
            9015,
            "巨人2軍が接戦を制して白星",
            subtype="farm_result",
            status="publish",
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, _ = self._run_duplicate_case(
            candidate,
            existing,
            env={
                runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "0",
            },
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")

    def test_duplicate_widget_script_exempt_allows_widget_only_same_source_subtypes(self):
        cases = [
            (4015, 9016, "farm_result", "巨人2軍が逆転勝ち", "巨人2軍が投手戦を制す"),
            (4016, 9017, "farm_lineup", "巨人2軍スタメン発表 秋広優人が4番", "巨人2軍スタメン発表 浅野翔吾が1番"),
            (4017, 9018, "lineup", "巨人スタメン発表 丸佳浩が1番", "巨人スタメン発表 吉川尚輝が1番"),
            (4018, 9019, "injury_recovery_notice", "浅野翔吾が実戦復帰へ", "大勢がブルペン投球を再開"),
        ]

        for candidate_id, existing_id, subtype, candidate_title, existing_title in cases:
            with self.subTest(subtype=subtype):
                candidate = self._make_duplicate_source_post(candidate_id, candidate_title, subtype=subtype)
                existing = self._make_duplicate_source_post(
                    existing_id,
                    existing_title,
                    subtype=subtype,
                    status="publish",
                )
                existing["date"] = "2026-04-26T07:00:00+09:00"

                result, wp = self._run_duplicate_case(
                    candidate,
                    existing,
                    env={
                        runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                        runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "1",
                    },
                )

                self.assertEqual(result["refused"], [])
                self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
                self.assertEqual(wp.update_post_status_calls, [(candidate_id, "publish")])

    def test_duplicate_widget_script_exempt_allows_when_only_matching_source_is_widget_script(self):
        candidate = self._make_duplicate_source_post(
            4018,
            "橋上コーチが配球意図を説明",
            subtype="manager",
            source_urls=[
                "https://twitter.com/hochi_giants/status/2050875183099953299",
                WIDGET_SCRIPT_URL,
                "https://twitter.com/SportsHochi/status/2050875630254776823",
            ],
        )
        existing = self._make_duplicate_source_post(
            9019,
            "立岡が打撃改造の背景を語る",
            subtype="player",
            source_urls=[
                "https://twitter.com/hochi_giants/status/2050800884783726956",
                WIDGET_SCRIPT_URL,
                "https://twitter.com/SportsHochi/status/2050801420740214841",
            ],
            status="publish",
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, wp = self._run_duplicate_case(
            candidate,
            existing,
            env={
                runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "1",
            },
        )

        self.assertEqual(result["refused"], [])
        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(wp.update_post_status_calls, [(4018, "publish")])

    def test_duplicate_widget_script_exempt_keeps_duplicate_when_candidate_has_non_widget_source(self):
        candidate = self._make_duplicate_source_post(
            4019,
            "巨人スタメン発表 門脇誠が2番",
            subtype="lineup",
            source_urls=["https://hochi.news/articles/lineup-source", WIDGET_SCRIPT_URL],
        )
        existing = self._make_duplicate_source_post(
            9020,
            "巨人スタメン発表 坂本勇人が3番",
            subtype="lineup",
            source_urls=["https://hochi.news/articles/lineup-source", WIDGET_SCRIPT_URL],
            status="publish",
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, _ = self._run_duplicate_case(
            candidate,
            existing,
            env={
                runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "1",
            },
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")

    def test_duplicate_widget_script_exempt_keeps_duplicate_when_matching_source_is_non_widget(self):
        candidate = self._make_duplicate_source_post(
            4020,
            "巨人2軍が接戦を制す",
            subtype="farm_result",
            source_urls=["https://hochi.news/articles/farm-result-source", WIDGET_SCRIPT_URL],
        )
        existing = self._make_duplicate_source_post(
            9021,
            "巨人2軍が投手戦をものにする",
            subtype="farm_result",
            source_urls=["https://hochi.news/articles/farm-result-source", WIDGET_SCRIPT_URL],
            status="publish",
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, _ = self._run_duplicate_case(
            candidate,
            existing,
            env={
                runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "1",
            },
        )

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")

    def test_duplicate_widget_script_exempt_keeps_duplicate_when_exact_title_signal_exists(self):
        candidate = self._make_duplicate_source_post(
            4021,
            "巨人2軍スタメン発表 浅野翔吾が1番",
            subtype="farm_lineup",
        )
        existing = self._make_duplicate_source_post(
            9022,
            "巨人2軍スタメン発表 浅野翔吾が1番",
            subtype="farm_lineup",
            status="publish",
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, _ = self._run_duplicate_case(
            candidate,
            existing,
            env={
                runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "1",
            },
        )

        self.assertEqual(result["proposed"], [])
        self.assertIn(
            result["refused"][0]["duplicate_reason"],
            {"same_source_url", "exact_title_match_publish"},
        )

    def test_duplicate_widget_script_exempt_keeps_duplicate_when_normalized_title_signal_exists(self):
        candidate = self._make_duplicate_source_post(
            4022,
            "巨人スタメン発表 吉川尚輝が1番！",
            subtype="lineup",
        )
        existing = self._make_duplicate_source_post(
            9023,
            "巨人スタメン発表 吉川尚輝が1番",
            subtype="lineup",
            status="publish",
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, _ = self._run_duplicate_case(
            candidate,
            existing,
            env={
                runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "1",
            },
        )

        self.assertEqual(result["proposed"], [])
        self.assertIn(
            result["refused"][0]["duplicate_reason"],
            {"same_source_url", "normalized_title_match_publish"},
        )

    def test_duplicate_widget_script_exempt_keeps_duplicate_when_same_game_signal_exists(self):
        candidate = self._make_duplicate_source_post(
            4023,
            "阿部監督が継投の意図を説明",
            subtype="comment",
            meta={"game_id": "20260503-g-t", "speaker_name": "阿部監督"},
        )
        existing = self._make_duplicate_source_post(
            9024,
            "阿部監督が終盤の勝負手を説明",
            subtype="comment",
            meta={"game_id": "20260503-g-t", "speaker_name": "阿部監督"},
            status="publish",
        )
        existing["date"] = "2026-04-26T07:00:00+09:00"

        result, _ = self._run_duplicate_case(
            candidate,
            existing,
            env={
                runner.DUPLICATE_TARGET_INTEGRITY_STRICT_ENV: "1",
                runner.DUPLICATE_WIDGET_SCRIPT_EXEMPT_ENV: "1",
            },
        )

        self.assertEqual(result["proposed"], [])
        self.assertIn(
            result["refused"][0]["duplicate_reason"],
            {"same_source_url", "same_game_subtype_speaker"},
        )

    def test_duplicate_same_source_url_allows_different_subtype(self):
        candidate = _post(
            4009,
            "巨人が延長戦を制してカード勝ち越し",
            f"<p>巨人が延長戦を制した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/shared-source-subtype</p>",
        )
        candidate["meta"] = {"article_subtype": "postgame"}
        existing = _post(
            9009,
            "巨人スタメン発表 丸佳浩が1番",
            "<p>同じ source だが lineup 記事。</p><p>参照元: スポーツ報知 https://example.com/shared-source-subtype</p>",
            status="publish",
        )
        existing["meta"] = {"article_subtype": "lineup"}
        existing["date"] = "2026-04-26T07:20:00+09:00"
        wp = FakeWPClient({4009: candidate, 9009: existing})
        report = _report(green=[_green_entry(4009, candidate["title"]["raw"])])

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

        self.assertEqual(result["refused"], [])
        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(wp.update_post_status_calls, [(4009, "publish")])

    def test_duplicate_same_source_url_allows_same_subtype_after_six_hours(self):
        candidate = _post(
            4010,
            "巨人が終盤の集中打で勝利",
            f"<p>巨人が終盤に突き放した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/shared-source-age</p>",
        )
        candidate["meta"] = {"article_subtype": "postgame"}
        existing = _post(
            9010,
            "巨人が接戦を制した前夜の試合",
            "<p>同じ source / same subtype だが前の試合。</p><p>参照元: スポーツ報知 https://example.com/shared-source-age</p>",
            status="publish",
        )
        existing["meta"] = {"article_subtype": "postgame"}
        existing["date"] = "2026-04-26T00:30:00+09:00"
        wp = FakeWPClient({4010: candidate, 9010: existing})
        report = _report(green=[_green_entry(4010, candidate["title"]["raw"])])

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

        self.assertEqual(result["refused"], [])
        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(wp.update_post_status_calls, [(4010, "publish")])

    def test_duplicate_same_source_url_allows_same_subtype_with_different_speaker(self):
        candidate = _post(
            4011,
            "岡本和真が試合後に打席を振り返る",
            f"<p>岡本和真が打席内容を振り返った。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/shared-source-speaker</p>",
        )
        candidate["meta"] = {"article_subtype": "comment", "speaker_name": "岡本和真"}
        existing = _post(
            9011,
            "阿部監督が継投の意図を説明",
            "<p>同じ source / same subtype だが speaker が違う。</p><p>参照元: スポーツ報知 https://example.com/shared-source-speaker</p>",
            status="publish",
        )
        existing["meta"] = {"article_subtype": "comment", "speaker_name": "阿部監督"}
        existing["date"] = "2026-04-26T07:10:00+09:00"
        wp = FakeWPClient({4011: candidate, 9011: existing})
        report = _report(green=[_green_entry(4011, candidate["title"]["raw"])])

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

        self.assertEqual(result["refused"], [])
        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(wp.update_post_status_calls, [(4011, "publish")])

    def test_duplicate_same_source_url_recent_same_subtype_and_speaker_still_holds(self):
        candidate = _post(
            4012,
            "阿部監督が試合後に継投を説明",
            f"<p>阿部監督が継投の意図を説明した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/shared-source-recent</p>",
        )
        candidate["meta"] = {"article_subtype": "comment", "speaker_name": "阿部監督"}
        existing = _post(
            9012,
            "阿部監督が終盤の勝負手を説明",
            "<p>same source / same subtype / same speaker。</p><p>参照元: スポーツ報知 https://example.com/shared-source-recent</p>",
            status="publish",
        )
        existing["meta"] = {"article_subtype": "comment", "speaker_name": "阿部監督"}
        existing["date"] = "2026-04-26T07:00:00+09:00"
        wp = FakeWPClient({4012: candidate, 9012: existing})
        report = _report(green=[_green_entry(4012, candidate["title"]["raw"])])

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

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9012)
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")

    def test_duplicate_same_source_url_checks_all_matching_publish_references(self):
        candidate = _post(
            4013,
            "巨人スタメン発表 坂本勇人が3番",
            f"<p>巨人の先発メンバーが発表された。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/shared-source-multi</p>",
        )
        candidate["meta"] = {"article_subtype": "lineup"}
        existing_complementary = _post(
            9013,
            "巨人が接戦を制した",
            "<p>same source の postgame 記事。</p><p>参照元: スポーツ報知 https://example.com/shared-source-multi</p>",
            status="publish",
        )
        existing_complementary["meta"] = {"article_subtype": "postgame"}
        existing_complementary["date"] = "2026-04-26T07:30:00+09:00"
        existing_complementary["modified"] = "2026-04-26T07:50:00"
        existing_same_subtype = _post(
            9014,
            "巨人スタメン発表 吉川尚輝が1番",
            "<p>same source の lineup 記事。</p><p>参照元: スポーツ報知 https://example.com/shared-source-multi</p>",
            status="publish",
        )
        existing_same_subtype["meta"] = {"article_subtype": "lineup"}
        existing_same_subtype["date"] = "2026-04-26T07:20:00+09:00"
        existing_same_subtype["modified"] = "2026-04-26T07:40:00"
        wp = FakeWPClient({4013: candidate, 9013: existing_complementary, 9014: existing_same_subtype})
        report = _report(green=[_green_entry(4013, candidate["title"]["raw"])])

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

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_source_url")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9014)
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_source_url")

    def test_duplicate_same_game_subtype_speaker_holds_for_review(self):
        candidate = _post(
            4006,
            "阿部監督 6回の継投を説明",
            f"<p>阿部監督が継投判断を説明した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/comment-a</p>",
        )
        candidate["meta"] = {"article_subtype": "comment", "game_id": "20260429-g-t", "speaker_name": "阿部監督"}
        existing = _post(
            9006,
            "阿部監督 7回の攻め方を説明",
            "<p>同試合・同 speaker の別記事。</p><p>参照元: スポーツ報知 https://example.com/comment-b</p>",
            status="publish",
        )
        existing["meta"] = {"article_subtype": "comment", "game_id": "20260429-g-t", "speaker_name": "阿部監督"}
        wp = FakeWPClient({4006: candidate, 9006: existing})
        report = _report(green=[_green_entry(4006, candidate["title"]["raw"])])

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

        self.assertEqual(result["proposed"], [])
        self.assertEqual(result["refused"][0]["hold_reason"], "review_duplicate_candidate_same_game_subtype_speaker")
        self.assertEqual(result["refused"][0]["duplicate_of_post_id"], 9006)
        self.assertEqual(result["refused"][0]["duplicate_reason"], "same_game_subtype_speaker")

    def test_same_game_with_different_subtype_is_not_held(self):
        candidate = _post(
            4007,
            "巨人が阪神に5-2で勝利",
            f"<p>巨人が阪神に5-2で勝利した。試合の核が冒頭で分かる。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/postgame-a</p>",
        )
        candidate["meta"] = {"article_subtype": "postgame", "game_id": "20260429-g-u", "speaker_name": "阿部監督"}
        existing = _post(
            9007,
            "阿部監督 継投の意図を説明",
            "<p>同 game だが comment 記事。</p><p>参照元: スポーツ報知 https://example.com/comment-c</p>",
            status="publish",
        )
        existing["meta"] = {"article_subtype": "comment", "game_id": "20260429-g-u", "speaker_name": "阿部監督"}
        wp = FakeWPClient({4007: candidate, 9007: existing})
        report = _report(green=[_green_entry(4007, candidate["title"]["raw"])])

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

        self.assertEqual(result["refused"], [])
        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(wp.update_post_status_calls, [(4007, "publish")])

    def test_same_speaker_with_different_game_day_is_not_held(self):
        candidate = _post(
            4008,
            "阿部監督 試合後に打線を評価",
            f"<p>阿部監督が試合後に打線を評価した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/comment-d</p>",
        )
        candidate["meta"] = {"article_subtype": "comment", "game_id": "20260430-g-v", "speaker_name": "阿部監督"}
        existing = _post(
            9008,
            "阿部監督 前日の継投を振り返る",
            "<p>speaker は同じだが別日の試合。</p><p>参照元: スポーツ報知 https://example.com/comment-e</p>",
            status="publish",
        )
        existing["meta"] = {"article_subtype": "comment", "game_id": "20260429-g-v", "speaker_name": "阿部監督"}
        wp = FakeWPClient({4008: candidate, 9008: existing})
        report = _report(green=[_green_entry(4008, candidate["title"]["raw"])])

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

        self.assertEqual(result["refused"], [])
        self.assertEqual([item["status"] for item in result["executed"]], ["sent"])
        self.assertEqual(wp.update_post_status_calls, [(4008, "publish")])

    def test_duplicate_reason_and_post_id_are_recorded_in_history(self):
        candidate = _post(
            4009,
            "巨人が中日に4-0で勝利",
            f"<p>巨人が中日に4-0で勝利した。主導権を握って完封した。</p><p>{LONG_EXTRA}</p><p>参照元: スポーツ報知 https://example.com/source-f</p>",
        )
        existing = _post(
            9009,
            "巨人が中日に4-0で勝利",
            "<p>既存 publish。</p><p>参照元: スポーツ報知 https://example.com/source-g</p>",
            status="publish",
        )
        wp = FakeWPClient({4009: candidate, 9009: existing})
        report = _report(green=[_green_entry(4009, candidate["title"]["raw"])])

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

        self.assertEqual(result["executed"][0]["duplicate_of_post_id"], 9009)
        self.assertEqual(result["executed"][0]["duplicate_reason"], "exact_title_match_publish")
        self.assertEqual(history_row["status"], "refused")
        self.assertEqual(history_row["duplicate_of_post_id"], 9009)
        self.assertEqual(history_row["duplicate_reason"], "exact_title_match_publish")


if __name__ == "__main__":
    unittest.main()
