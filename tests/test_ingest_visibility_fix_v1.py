from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src import repair_fallback_controller as controller
from src import repair_provider_ledger
from src.tools import draft_body_editor as dbe
from src.tools import run_draft_body_editor_lane as lane


POSTGAME_BODY = (
    "【試合結果】\n"
    "巨人が勝利しました。\n"
    "【ハイライト】\n"
    "序盤の得点が決め手でした。\n"
    "【選手成績】\n"
    "打線が好調でした。\n"
    "【試合展開】\n"
    "終盤は守備で締めました。"
)
POSTGAME_SOURCE = "・巨人が勝利\n・序盤の得点\n・打線が好調\n・終盤の守備"
POSTGAME_NEW = (
    "【試合結果】\n"
    "巨人が勝利を収めました。\n"
    "【ハイライト】\n"
    "序盤の得点が試合を決めました。\n"
    "【選手成績】\n"
    "打線が好調で流れを掴みました。\n"
    "【試合展開】\n"
    "終盤は守備で締めました。"
)
SUCCESS_BODY = (
    "【試合結果】\n"
    "巨人が勝利した。\n"
    "【ハイライト】\n"
    "要点を整理した本文です。\n"
    "【選手成績】\n"
    "主力選手の内容です。\n"
    "【試合展開】\n"
    "終盤までの流れです。"
)


def _read_jsonl_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _json_lines(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        rows.append(json.loads(stripped))
    return rows


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _make_dbe_argv(workspace: Path, *, post_id: int = 1234) -> list[str]:
    current_path = _write(workspace / "current.txt", POSTGAME_BODY)
    source_path = _write(workspace / "source.txt", POSTGAME_SOURCE)
    out_path = workspace / "out.txt"
    return [
        "--post-id", str(post_id),
        "--subtype", "postgame",
        "--fail", "density",
        "--current-body", str(current_path),
        "--source-block", str(source_path),
        "--out", str(out_path),
    ]


def _run_dbe_main(
    argv: list[str],
    *,
    dedupe_path: Path,
    queue_path: Path,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    env_overrides = {"GEMINI_API_KEY": "test-key"}
    if env:
        env_overrides.update(env)
    with patch.object(dbe.llm_call_dedupe, "DEFAULT_LEDGER_PATH", dedupe_path), \
         patch.object(dbe, "PUBLISH_NOTICE_QUEUE_PATH", queue_path), \
         patch("sys.stdout", stdout), patch("sys.stderr", stderr), \
         patch.dict(os.environ, env_overrides, clear=False):
        code = dbe.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


def _make_lane_post(
    post_id: int,
    *,
    modified: str = "2026-04-20T09:00:00+09:00",
) -> dict:
    return {
        "id": post_id,
        "status": "draft",
        "modified": modified,
        "title": {"raw": "巨人 2-1 勝利のポイント"},
        "content": {"raw": POSTGAME_BODY},
        "featured_media": 1,
        "meta": {
            "article_subtype": "postgame",
            "source_urls": ["https://www.giants.jp/game/20260420/report/"],
        },
    }


class _FakeWP:
    def __init__(
        self,
        *,
        paged_posts: dict[int, list[dict]] | None = None,
        get_post_map: dict[int, dict] | None = None,
    ) -> None:
        self.paged_posts = paged_posts or {1: [], 2: []}
        self.get_post_map = get_post_map or {}
        self.get_post_calls: list[int] = []
        self.put_calls: list[tuple[int, dict]] = []

    def list_posts(self, **kwargs):
        page = int(kwargs["page"])
        return list(self.paged_posts.get(page, []))

    def get_post(self, post_id):
        self.get_post_calls.append(int(post_id))
        return dict(self.get_post_map[int(post_id)])

    def update_post_fields(self, post_id, **fields):
        self.put_calls.append((int(post_id), dict(fields)))


def _run_lane_main(
    argv: list[str],
    *,
    wp: _FakeWP,
    queue_path: Path,
    touched_ids: set[int] | None = None,
    run_editor_side_effect=None,
    env: dict[str, str] | None = None,
    guarded_history_path: Path | None = None,
    dedupe_path: Path | None = None,
) -> tuple[int, str, str, _FakeWP, Mock]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    make_wp_client = Mock(return_value=wp)
    editor_mock = Mock(
        side_effect=run_editor_side_effect
        if run_editor_side_effect is not None
        else AssertionError("unexpected _run_editor call")
    )
    env_overrides = {} if env is None else dict(env)
    with patch.object(dbe, "PUBLISH_NOTICE_QUEUE_PATH", queue_path), \
         patch("src.tools.run_draft_body_editor_lane._make_wp_client", make_wp_client), \
         patch("src.tools.run_draft_body_editor_lane._run_editor", editor_mock), \
         patch("src.tools.run_draft_body_editor_lane._read_recent_touched_post_ids", return_value=touched_ids or set()), \
         patch("sys.stdout", stdout), patch("sys.stderr", stderr), \
         patch.dict(os.environ, env_overrides, clear=False):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_root = Path(tmpdir) / "lane_logs"
            with patch.object(lane, "LOG_ROOT", log_root):
                if guarded_history_path is None:
                    code = lane.main(list(argv))
                else:
                    with patch.object(lane, "GUARDED_PUBLISH_HISTORY_PATH", guarded_history_path), \
                         patch.object(lane, "LLM_DEDUPE_LEDGER_PATH", dedupe_path or (Path(tmpdir) / "llm_call_dedupe.jsonl")):
                        code = lane.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue(), wp, editor_mock


def _lane_summary(stdout: str) -> dict:
    rows = _json_lines(stdout)
    if not rows:
        raise AssertionError("stdout did not contain JSON")
    return rows[-1]


class IngestVisibilityFixV1Tests(unittest.TestCase):
    def test_draft_body_editor_no_op_skip_visible_when_flag_on(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            queue_path = Path(tmpdir) / "publish_notice_queue.jsonl"
            dedupe_path = Path(tmpdir) / "llm_call_dedupe.jsonl"
            argv = _make_dbe_argv(workspace)
            content_hash = dbe.llm_call_dedupe.compute_content_hash(1234, POSTGAME_BODY)
            dbe.llm_call_dedupe.record_call(
                1234,
                content_hash,
                "failed",
                ledger_path=dedupe_path,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                error_code="gemini_api_error",
            )

            code, _, stderr = _run_dbe_main(
                argv,
                dedupe_path=dedupe_path,
                queue_path=queue_path,
                env={"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"},
            )
            rows = _read_jsonl_rows(queue_path)

        self.assertEqual(code, 20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "content_hash_dedupe")
        self.assertEqual(rows[0]["record_type"], "repair_skip")
        self.assertEqual(rows[0]["skip_layer"], "repair_lane")
        self.assertEqual(rows[0]["source_path"], "src/tools/draft_body_editor.py")
        self.assertEqual(rows[0]["source_post_id"], 1234)
        self.assertEqual(rows[0]["notice_kind"], "post_gen_validate")
        self.assertTrue(str(rows[0]["subject"]).startswith("【要review｜repair_skip】"))
        self.assertTrue(str(rows[0]["candidate_id"]).startswith("repair_skip:1234:content_hash_dedupe:"))
        stderr_events = [row for row in _json_lines(stderr) if row.get("event") == "ingest_visibility_fix_v1_emit"]
        self.assertEqual(len(stderr_events), 1)

    def test_draft_body_editor_llm_skip_visible_when_flag_on(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            queue_path = Path(tmpdir) / "publish_notice_queue.jsonl"
            dedupe_path = Path(tmpdir) / "llm_call_dedupe.jsonl"
            argv = _make_dbe_argv(workspace)
            content_hash = dbe.llm_call_dedupe.compute_content_hash(1234, POSTGAME_BODY)
            dbe.llm_call_dedupe.record_call(
                1234,
                content_hash,
                "failed",
                ledger_path=dedupe_path,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                error_code="gemini_api_error",
            )

            code, _, stderr = _run_dbe_main(
                argv,
                dedupe_path=dedupe_path,
                queue_path=queue_path,
                env={"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"},
            )

        self.assertEqual(code, 20)
        events = _json_lines(stderr)
        self.assertTrue(any(row.get("event") == "llm_skip" for row in events))
        emitted = [row for row in events if row.get("event") == "ingest_visibility_fix_v1_emit"]
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["path"], "src/tools/draft_body_editor.py")
        self.assertEqual(emitted[0]["reason"], "content_hash_dedupe")
        self.assertTrue(str(emitted[0]["candidate_id"]).startswith("repair_skip:1234:content_hash_dedupe:"))

    def test_run_draft_body_editor_lane_no_op_skip_visible_when_flag_on(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wp = _FakeWP(paged_posts={1: [], 2: []})
            queue_path = Path(tmpdir) / "publish_notice_queue.jsonl"
            code, stdout, _, _, editor_mock = _run_lane_main(
                ["--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                queue_path=queue_path,
                env={"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"},
            )
            rows = _read_jsonl_rows(queue_path)

        self.assertEqual(code, 0)
        self.assertFalse(editor_mock.called)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "no_repair_candidates")
        self.assertEqual(rows[0]["record_type"], "repair_skip")
        self.assertEqual(rows[0]["skip_layer"], "repair_lane")
        self.assertEqual(rows[0]["source_path"], "src/tools/run_draft_body_editor_lane.py")
        self.assertEqual(rows[0]["provider"], "gemini")
        self.assertEqual(_lane_summary(stdout)["stop_reason"], "no_candidate")

    def test_run_draft_body_editor_lane_llm_skip_visible_when_flag_on(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "guarded_publish_history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 402,
                        "ts": "2026-04-20T08:30:00+09:00",
                        "status": "refused",
                        "error": "hard_stop:freshness_window",
                        "hold_reason": "hard_stop_freshness_window",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            post = _make_lane_post(402)
            wp = _FakeWP(
                paged_posts={1: [post], 2: []},
                get_post_map={402: post},
            )
            queue_path = Path(tmpdir) / "publish_notice_queue.jsonl"
            dedupe_path = Path(tmpdir) / "llm_call_dedupe.jsonl"
            code, stdout, _, _, editor_mock = _run_lane_main(
                ["--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                queue_path=queue_path,
                env={"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"},
                guarded_history_path=history_path,
                dedupe_path=dedupe_path,
            )
            rows = _read_jsonl_rows(queue_path)

        self.assertEqual(code, 0)
        self.assertFalse(editor_mock.called)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "refused_cooldown")
        self.assertEqual(rows[0]["source_path"], "src/tools/run_draft_body_editor_lane.py")
        self.assertEqual(rows[0]["source_post_id"], 402)
        self.assertTrue(str(rows[0]["candidate_id"]).startswith("repair_skip:402:refused_cooldown:"))
        self.assertEqual(_lane_summary(stdout)["skip_reason_counts"], {"refused_cooldown": 1})

    def test_repair_fallback_controller_silent_fallback_visible_when_flag_on(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "repair-ledger.jsonl"
            queue_path = Path(tmpdir) / "publish_notice_queue.jsonl"
            dedupe_path = Path(tmpdir) / "llm_call_dedupe.jsonl"
            writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)
            post = {
                "post_id": 1701,
                "subtype": "postgame",
                "current_body": SUCCESS_BODY,
                "fail_axes": ["density", "source"],
                "source_block": "・ref1: https://www.giants.jp/game/20260420/report/",
            }
            content_hash = controller.llm_call_dedupe.compute_content_hash(post["post_id"], post["current_body"])
            controller.llm_call_dedupe.record_call(
                post["post_id"],
                content_hash,
                "failed",
                ledger_path=dedupe_path,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                error_code="gemini_api_error",
                failure_chain=[{
                    "provider": "gemini",
                    "error_class": "gemini_api_error",
                    "error_message": "cached failure",
                    "latency_ms": 0,
                }],
            )
            stderr = io.StringIO()
            with patch.object(controller.llm_call_dedupe, "DEFAULT_LEDGER_PATH", dedupe_path), \
                 patch.object(dbe, "PUBLISH_NOTICE_QUEUE_PATH", queue_path), \
                 patch.dict(os.environ, {"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"}, clear=False), \
                 patch("sys.stderr", stderr), \
                 patch("src.repair_fallback_controller.call_provider") as mocked_call:
                result = controller.RepairFallbackController(
                    primary_provider="codex",
                    ledger_writer=writer,
                ).execute(dict(post), "repair prompt")
            rows = _read_jsonl_rows(queue_path)

        mocked_call.assert_not_called()
        self.assertIsNone(result.body_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "content_hash_dedupe")
        self.assertEqual(rows[0]["source_path"], "src/repair_fallback_controller.py")
        self.assertEqual(rows[0]["source_post_id"], 1701)
        self.assertTrue(str(rows[0]["candidate_id"]).startswith("repair_skip:1701:content_hash_dedupe:"))

    def test_flag_off_baseline_all_3_paths_silent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            queue_path = base / "publish_notice_queue.jsonl"

            dbe_workspace = base / "dbe"
            dbe_workspace.mkdir()
            dbe_dedupe = base / "dbe_dedupe.jsonl"
            dbe_hash = dbe.llm_call_dedupe.compute_content_hash(1234, POSTGAME_BODY)
            dbe.llm_call_dedupe.record_call(
                1234,
                dbe_hash,
                "failed",
                ledger_path=dbe_dedupe,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                error_code="gemini_api_error",
            )
            dbe_code, _, _ = _run_dbe_main(
                _make_dbe_argv(dbe_workspace),
                dedupe_path=dbe_dedupe,
                queue_path=queue_path,
            )

            history_path = base / "guarded_publish_history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "post_id": 402,
                        "ts": "2026-04-20T08:30:00+09:00",
                        "status": "refused",
                        "error": "hard_stop:freshness_window",
                        "hold_reason": "hard_stop_freshness_window",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            lane_post = _make_lane_post(402)
            lane_wp = _FakeWP(
                paged_posts={1: [lane_post], 2: []},
                get_post_map={402: lane_post},
            )
            lane_code, _, _, _, lane_editor_mock = _run_lane_main(
                ["--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=lane_wp,
                queue_path=queue_path,
                guarded_history_path=history_path,
                dedupe_path=base / "lane_dedupe.jsonl",
            )

            repair_dedupe = base / "repair_dedupe.jsonl"
            repair_ledger = base / "repair-ledger.jsonl"
            repair_writer = repair_provider_ledger.JsonlLedgerWriter(repair_ledger)
            controller.llm_call_dedupe.record_call(
                1701,
                controller.llm_call_dedupe.compute_content_hash(1701, SUCCESS_BODY),
                "failed",
                ledger_path=repair_dedupe,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                error_code="gemini_api_error",
            )
            with patch.object(controller.llm_call_dedupe, "DEFAULT_LEDGER_PATH", repair_dedupe), \
                 patch.object(dbe, "PUBLISH_NOTICE_QUEUE_PATH", queue_path), \
                 patch("src.repair_fallback_controller.call_provider") as mocked_call:
                repair_result = controller.RepairFallbackController(
                    primary_provider="codex",
                    ledger_writer=repair_writer,
                ).execute(
                    {
                        "post_id": 1701,
                        "subtype": "postgame",
                        "current_body": SUCCESS_BODY,
                        "fail_axes": ["density"],
                        "source_block": "・source",
                    },
                    "repair prompt",
                )
            queue_exists_after = queue_path.exists()

        self.assertEqual(dbe_code, 20)
        self.assertEqual(lane_code, 0)
        self.assertFalse(lane_editor_mock.called)
        mocked_call.assert_not_called()
        self.assertIsNone(repair_result.body_text)
        self.assertFalse(queue_exists_after)

    def test_mail_volume_unchanged_when_flag_off(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "publish_notice_queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "status": "queued",
                        "reason": "baseline",
                        "subject": "baseline",
                        "recipients": [],
                        "post_id": "baseline:1",
                        "recorded_at": "2026-05-02T10:00:00+09:00",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            dedupe_path = Path(tmpdir) / "llm_call_dedupe.jsonl"
            ledger_path = Path(tmpdir) / "repair-ledger.jsonl"
            writer = repair_provider_ledger.JsonlLedgerWriter(ledger_path)
            controller.llm_call_dedupe.record_call(
                1701,
                controller.llm_call_dedupe.compute_content_hash(1701, SUCCESS_BODY),
                "failed",
                ledger_path=dedupe_path,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                error_code="gemini_api_error",
            )
            with patch.object(controller.llm_call_dedupe, "DEFAULT_LEDGER_PATH", dedupe_path), \
                 patch.object(dbe, "PUBLISH_NOTICE_QUEUE_PATH", queue_path), \
                 patch("src.repair_fallback_controller.call_provider") as mocked_call:
                result = controller.RepairFallbackController(
                    primary_provider="codex",
                    ledger_writer=writer,
                ).execute(
                    {
                        "post_id": 1701,
                        "subtype": "postgame",
                        "current_body": SUCCESS_BODY,
                        "fail_axes": ["density"],
                        "source_block": "・source",
                    },
                    "repair prompt",
                )
            row_count = len(_read_jsonl_rows(queue_path))

        mocked_call.assert_not_called()
        self.assertIsNone(result.body_text)
        self.assertEqual(row_count, 1)

    def test_publish_path_unchanged_in_both_modes(self):
        def run_case(env: dict[str, str]) -> tuple[dict, list[tuple[int, dict]], list[dict]]:
            with tempfile.TemporaryDirectory() as tmpdir:
                queue_path = Path(tmpdir) / "publish_notice_queue.jsonl"
                post = _make_lane_post(501)
                wp = _FakeWP(
                    paged_posts={1: [post], 2: []},
                    get_post_map={501: post},
                )
                editor_runs = [
                    (0, {"guards": "pass", "content_hash": "hash-501"}, "[dry-run] ok", None),
                    (0, {"guards": "pass", "content_hash": "hash-501"}, "", POSTGAME_NEW),
                ]
                code, stdout, _, wp_after, editor_mock = _run_lane_main(
                    ["--now-iso", "2026-04-20T10:00:00+09:00", "--max-posts", "1"],
                    wp=wp,
                    queue_path=queue_path,
                    run_editor_side_effect=editor_runs,
                    env=env,
                )

                self.assertEqual(code, 0)
                self.assertEqual(editor_mock.call_count, 2)
                return _lane_summary(stdout), list(wp_after.put_calls), _read_jsonl_rows(queue_path)

        off_summary, off_puts, off_rows = run_case({})
        on_summary, on_puts, on_rows = run_case({"ENABLE_INGEST_VISIBILITY_FIX_V1": "1"})

        self.assertEqual(off_summary, on_summary)
        self.assertEqual(off_summary["put_ok"], 1)
        self.assertEqual(off_summary["per_post_outcomes"], [{"post_id": 501, "verdict": "edited", "edited": "ok"}])
        self.assertEqual(off_puts, on_puts)
        self.assertEqual(len(off_puts), 1)
        self.assertEqual(off_rows, [])
        self.assertEqual(on_rows, [])


if __name__ == "__main__":
    unittest.main()
