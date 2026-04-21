"""Tests for ``src.tools.run_quality_monitor``."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools import run_quality_monitor as monitor


def _make_post(
    post_id: int,
    *,
    title: str = "巨人 2-1 勝利のポイント",
    status: str = "draft",
    subtype: str | None = "postgame",
    modified: str = "2026-04-20T09:00:00+09:00",
    featured_media: int = 1,
    fact_check_status: str | None = None,
    audit_flag: bool | None = None,
    source_urls: list[str] | None = None,
    body: str | None = None,
) -> dict:
    meta: dict[str, object] = {}
    if subtype is not None:
        meta["article_subtype"] = subtype
    if fact_check_status is not None:
        meta["fact_check_status"] = fact_check_status
    if audit_flag is not None:
        meta["audit_flag"] = audit_flag
    if source_urls is None:
        source_urls = ["https://www.giants.jp/game/20260420/preview/"]
    meta["source_urls"] = source_urls
    body = body or (
        "【試合結果】\n巨人が2-1で勝利した。\n"
        "【ハイライト】\n戸郷の投球が流れを作った。\n"
        "【選手成績】\n岡本が1本塁打。\n"
        "【試合展開】\n終盤にリードを守った。"
    )
    return {
        "id": post_id,
        "status": status,
        "modified": modified,
        "title": {"raw": title},
        "content": {"raw": body},
        "featured_media": featured_media,
        "meta": meta,
    }


class _FakeWP:
    """Paginated fake WP client.

    ``draft_pages`` / ``any_pages`` are lists of lists: one inner list per
    page. ``list_exception`` raises on every call when set.
    """

    def __init__(
        self,
        draft_pages: list[list[dict]] | None = None,
        any_pages: list[list[dict]] | None = None,
        draft_exception: Exception | None = None,
        any_exception: Exception | None = None,
    ) -> None:
        self.draft_pages = draft_pages if draft_pages is not None else []
        self.any_pages = any_pages if any_pages is not None else []
        self.draft_exception = draft_exception
        self.any_exception = any_exception
        self.calls: list[dict] = []

    def list_posts(self, **kwargs):
        self.calls.append(kwargs)
        status = kwargs.get("status")
        page = int(kwargs.get("page", 1))
        if status == "draft":
            if self.draft_exception is not None:
                raise self.draft_exception
            if page - 1 < len(self.draft_pages):
                return list(self.draft_pages[page - 1])
            return []
        if status == "any":
            if self.any_exception is not None:
                raise self.any_exception
            if page - 1 < len(self.any_pages):
                return list(self.any_pages[page - 1])
            return []
        return []


def _run_main(argv, *, wp=None, touched_ids=None, log_root=None, wp_init_exception=None):
    stdout = io.StringIO()
    stderr = io.StringIO()
    wp_client = wp if wp is not None else _FakeWP()

    if wp_init_exception is not None:
        client_patch = patch(
            "src.tools.run_quality_monitor._make_wp_client",
            side_effect=wp_init_exception,
        )
    else:
        client_patch = patch(
            "src.tools.run_quality_monitor._make_wp_client",
            return_value=wp_client,
        )

    patchers = [
        client_patch,
        patch(
            "src.tools.run_quality_monitor._read_recent_touched_post_ids",
            return_value=touched_ids or set(),
        ),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ]

    isolated_tmp: tempfile.TemporaryDirectory | None = None
    if log_root is None:
        isolated_tmp = tempfile.TemporaryDirectory()
        log_root = Path(isolated_tmp.name)
    patchers.append(patch.object(monitor, "LOG_ROOT", log_root))

    for p in patchers:
        p.start()
    try:
        code = monitor.main(list(argv))
    finally:
        for p in reversed(patchers):
            p.stop()
        if isolated_tmp is not None:
            isolated_tmp.cleanup()
    return code, stdout.getvalue(), stderr.getvalue(), wp_client, log_root


class TestQualityMonitor(unittest.TestCase):
    def test_draft_scan_success_no_issues(self):
        post = _make_post(101)
        wp = _FakeWP(draft_pages=[[post]])
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, root = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["target"], "draft")
        self.assertEqual(payload["scanned_count"], 1)
        self.assertEqual(payload["flagged_count"], 0)
        self.assertEqual(payload["fetch_mode"], "draft_list")

    def test_pagination_spans_multiple_pages(self):
        p1 = [_make_post(i) for i in range(100, 200)]  # 100
        p2 = [_make_post(i) for i in range(200, 220)]  # 20 -> partial -> stop
        wp = _FakeWP(draft_pages=[p1, p2])
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, wp, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00", "--page-limit", "5"],
                wp=wp,
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["scanned_count"], 120)
        self.assertEqual(len(wp.calls), 2)

    def test_page_limit_caps_fetch(self):
        pages = [[_make_post(1000 + j * 100 + i) for i in range(100)] for j in range(5)]
        wp = _FakeWP(draft_pages=pages)
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _, wp, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00", "--page-limit", "2"],
                wp=wp,
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        self.assertEqual(len(wp.calls), 2)

    def test_benign_reason_recently_touched_excluded(self):
        post = _make_post(201)
        wp = _FakeWP(draft_pages=[[post]])
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                touched_ids={201},
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["scanned_count"], 1)
        self.assertEqual(payload["flagged_count"], 0)

    def test_benign_reason_outside_edit_window_excluded(self):
        post = _make_post(202, modified="2026-04-20T09:59:00+09:00")  # <15min
        wp = _FakeWP(draft_pages=[[post]])
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["flagged_count"], 0)

    def test_quality_flag_fact_check_high(self):
        post = _make_post(301, fact_check_status="fail")
        wp = _FakeWP(draft_pages=[[post]])
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                log_root=Path(tmp),
            )
            log_path = Path(tmp) / "2026-04-20.jsonl"
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["flagged_count"], 1)
        self.assertEqual(payload["severity_counts"]["high"], 1)
        self.assertEqual(record["event"], "quality_scan")
        self.assertEqual(len(record["flagged_posts"]), 1)
        self.assertEqual(record["flagged_posts"][0]["reason"], "fact_check_blocked")
        self.assertEqual(record["flagged_posts"][0]["severity"], "high")
        self.assertEqual(record["reason_counts"], {"fact_check_blocked": 1})

    def test_quality_flag_missing_featured_media_low(self):
        post = _make_post(302, featured_media=0)
        wp = _FakeWP(draft_pages=[[post]])
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["flagged_count"], 1)
        self.assertEqual(payload["severity_counts"]["low"], 1)

    def test_fetch_failure_falls_back_then_fails(self):
        wp = _FakeWP(
            draft_exception=RuntimeError("draft endpoint 500"),
            any_exception=RuntimeError("any endpoint 500"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                log_root=Path(tmp),
            )
        self.assertEqual(code, monitor.EXIT_WP_GET_FAILED)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["fetch_mode"], "fallback_failed")
        self.assertEqual(payload["stop_reason"], "wp_get_failed")

    def test_fetch_fallback_to_status_any(self):
        post_draft = _make_post(401, status="draft")
        post_publish = _make_post(402, status="publish")
        wp = _FakeWP(
            draft_exception=RuntimeError("draft endpoint 500"),
            any_pages=[[post_draft, post_publish]],
        )
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["fetch_mode"], "status_any_fallback")
        self.assertEqual(payload["scanned_count"], 1)

    def test_wp_init_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp_init_exception=RuntimeError("WP env missing"),
                log_root=Path(tmp),
            )
        self.assertEqual(code, monitor.EXIT_WP_GET_FAILED)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "wp_init_failed")

    def test_published_target_is_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "published", "--now-iso", "2026-04-20T10:00:00+09:00"],
                log_root=Path(tmp),
            )
            log_path = Path(tmp) / "2026-04-20.jsonl"
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["target"], "published")
        self.assertEqual(payload["fetch_mode"], "stub")
        self.assertEqual(payload["stop_reason"], "published_stub")
        self.assertEqual(record["stop_reason"], "published_stub")

    def test_both_target_is_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _, _, _ = _run_main(
                ["--target", "both", "--now-iso", "2026-04-20T10:00:00+09:00"],
                log_root=Path(tmp),
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["target"], "both")
        self.assertEqual(payload["stop_reason"], "published_stub")

    def test_raw_log_schema(self):
        post = _make_post(501, fact_check_status="fail")
        wp = _FakeWP(draft_pages=[[post]])
        with tempfile.TemporaryDirectory() as tmp:
            _run_main(
                ["--target", "draft", "--now-iso", "2026-04-20T10:00:00+09:00"],
                wp=wp,
                log_root=Path(tmp),
            )
            log_path = Path(tmp) / "2026-04-20.jsonl"
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
        for key in (
            "event",
            "ts",
            "target",
            "scanned_count",
            "flagged_posts",
            "pagination",
            "fetch_mode",
            "reason_counts",
        ):
            self.assertIn(key, record, msg=f"missing key: {key}")
        self.assertEqual(record["event"], "quality_scan")
        self.assertEqual(record["pagination"], {"pages": 1, "total": 1})


if __name__ == "__main__":
    unittest.main()
