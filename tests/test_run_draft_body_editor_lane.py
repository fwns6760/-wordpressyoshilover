"""Tests for ``src.tools.run_draft_body_editor_lane``."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.tools import run_draft_body_editor_lane as lane


SUCCESS_BODY = (
    "【試合結果】\n巨人が2-1で勝利した。\n"
    "【ハイライト】\n戸郷が抑えた。\n"
    "【選手成績】\n岡本が本塁打。\n"
    "【試合展開】\n終盤を守った。"
)


def _decorated_body_attrs(width: int = 4) -> str:
    return " ".join(f'data-lane-{idx}="{"y" * 90}"' for idx in range(width))


def _build_html_heavy_short_prose_body() -> str:
    attrs = _decorated_body_attrs()
    sections = [
        ("【試合結果】", "結果の要点を整理します。" * 16),
        ("【ハイライト】", "流れを左右した場面をまとめます。" * 14),
        ("【選手成績】", "主力選手の内容を振り返ります。" * 14),
        ("【試合展開】", "終盤までの運びを簡潔に整理します。" * 13),
    ]
    return "".join(
        f'<section class="lane-block" {attrs}>'
        f'<div class="lane-block__head" {attrs}><h2>{heading}</h2></div>'
        f'<div class="lane-block__body" {attrs}><p>{text}</p></div>'
        f'<footer class="lane-block__footer" {attrs}></footer>'
        f"</section>"
        for heading, text in sections
    )


def _build_true_prose_too_long_body() -> str:
    return (
        "【試合結果】\n"
        + ("あ" * 1300)
        + "\n【ハイライト】\n簡潔です。\n【選手成績】\n簡潔です。\n【試合展開】\n簡潔です。"
    )


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
    def __init__(self, *, paged_posts=None, get_post_map=None, put_side_effect=None, raise_on_page=None):
        self.paged_posts = paged_posts or {1: []}
        self.get_post_map = get_post_map or {}
        self.put_calls = []
        self.put_side_effect = put_side_effect
        self.raise_on_page = raise_on_page
        self.list_calls = []
        self.get_post_calls = []

    def list_posts(self, **kwargs):
        self.list_calls.append(kwargs)
        page = int(kwargs.get("page", 1))
        if self.raise_on_page is not None and page == self.raise_on_page:
            raise RuntimeError("pagination failed")
        return list(self.paged_posts.get(page, []))

    def get_post(self, post_id):
        self.get_post_calls.append(post_id)
        value = self.get_post_map[post_id]
        if isinstance(value, Exception):
            raise value
        return value

    def update_post_fields(self, post_id, **fields):
        if self.put_side_effect is not None:
            raise self.put_side_effect
        self.put_calls.append((post_id, fields))


def _editor_success_runs(count: int) -> list[tuple[int, dict, str, str | None]]:
    runs = []
    for _ in range(count):
        runs.extend(
            [
                (0, {"guards": "pass"}, "[dry-run] ok", None),
                (0, {"guards": "pass"}, "", SUCCESS_BODY),
            ]
        )
    return runs


def _run_main(argv, *, wp=None, run_editor_side_effect=None, touched_ids=None, log_root=None):
    stdout = io.StringIO()
    stderr = io.StringIO()
    wp = wp or _FakeWP()
    make_wp_client = Mock(return_value=wp)
    editor_mock = Mock(
        side_effect=run_editor_side_effect if run_editor_side_effect is not None else AssertionError("unexpected _run_editor call")
    )
    with patch("src.tools.run_draft_body_editor_lane._make_wp_client", make_wp_client), \
         patch("src.tools.run_draft_body_editor_lane._run_editor", editor_mock), \
         patch("src.tools.run_draft_body_editor_lane._read_recent_touched_post_ids", return_value=touched_ids or set()), \
         patch("sys.stdout", stdout), \
         patch("sys.stderr", stderr):
        isolated_tmp = None
        if log_root is None:
            isolated_tmp = tempfile.TemporaryDirectory()
            log_root = Path(isolated_tmp.name)
        with patch.object(lane, "LOG_ROOT", log_root):
            code = lane.main(list(argv))
        if isolated_tmp is not None:
            isolated_tmp.cleanup()
    return code, stdout.getvalue(), stderr.getvalue(), wp, make_wp_client, editor_mock


class TestBodyTooLongUsesProseLength(unittest.TestCase):
    def test_html_heavy_short_prose_stays_editable(self):
        now = lane._now_jst("2026-04-20T10:00:00+09:00")
        post = _make_post(1101, body=_build_html_heavy_short_prose_body())
        self.assertGreater(len(post["content"]["raw"]), lane.CURRENT_BODY_MAX_CHARS)
        self.assertLess(
            len(lane._extract_prose_text(post["content"]["raw"])),
            lane.CURRENT_BODY_MAX_CHARS,
        )
        for checker in (lane._draft_looks_editable, lane._list_level_looks_editable):
            with self.subTest(checker=checker.__name__):
                self.assertEqual(checker(post, now, set()), (True, "ok"))

    def test_true_prose_too_long_is_rejected(self):
        now = lane._now_jst("2026-04-20T10:00:00+09:00")
        post = _make_post(1102, body=_build_true_prose_too_long_body())
        self.assertGreater(
            len(lane._extract_prose_text(post["content"]["raw"])),
            lane.CURRENT_BODY_MAX_CHARS,
        )
        for checker in (lane._draft_looks_editable, lane._list_level_looks_editable):
            with self.subTest(checker=checker.__name__):
                self.assertEqual(checker(post, now, set()), (False, "body_too_long"))


class TestLaneMain(unittest.TestCase):
    def test_quiet_hours_stop_without_wp_interaction(self):
        code, stdout, _, _, make_wp_client, editor_mock = _run_main(["--now-iso", "2026-04-20T09:30:00+09:00"])
        self.assertEqual(code, 0)
        self.assertFalse(make_wp_client.called)
        self.assertFalse(editor_mock.called)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "quiet_hours")
        self.assertEqual(payload["edit_window_jst"], "10:00-23:59 JST")
        self.assertEqual(payload["current_quiet_hours_before_change"], "18:00-21:59 JST")

    def test_empty_candidates_returns_ok(self):
        wp = _FakeWP(paged_posts={1: []})
        code, stdout, _, _, _, _ = _run_main(["--now-iso", "2026-04-20T10:00:00+09:00"], wp=wp)
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "no_candidate")
        self.assertEqual(payload["put_ok"], 0)
        self.assertEqual(payload["candidates_before_filter"], 0)
        self.assertEqual(payload["skip_reason_counts"], {})
        self.assertEqual(payload["fetch_mode"], "draft_list_paginated")

    def test_pagination_across_three_pages_with_mixed_outcomes(self):
        paged_posts = {
            1: [
                _make_post(101, modified="2026-04-20T09:55:00+09:00"),
                _make_post(102, modified="2026-04-20T08:00:00+09:00"),
            ],
            2: [
                _make_post(201, subtype="live_update", modified="2026-04-20T08:10:00+09:00"),
                _make_post(202, modified="2026-04-20T08:30:00+09:00"),
            ],
            3: [
                _make_post(301, modified="2026-04-20T09:00:00+09:00"),
            ],
            4: [],
        }
        get_post_map = {
            102: _make_post(102, modified="2026-04-20T08:00:00+09:00"),
            202: _make_post(202, modified="2026-04-20T08:30:00+09:00", source_urls=[]),
            301: _make_post(301, modified="2026-04-20T09:00:00+09:00"),
        }
        wp = _FakeWP(
            paged_posts=paged_posts,
            get_post_map=get_post_map,
        )
        editor_runs = [
            (0, {"guards": "pass"}, "[dry-run] ok", None),
            (0, {"guards": "pass"}, "", SUCCESS_BODY),
            (10, None, "Guard A failed", None),
        ]
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00", "--max-posts", "3"],
            wp=wp,
            run_editor_side_effect=editor_runs,
        )
        self.assertEqual(code, 0)
        self.assertEqual(wp.get_post_calls, [102, 202, 301])
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "completed")
        self.assertEqual(payload["aggregate_counts"]["pages_fetched"], 4)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 102, "verdict": "edited", "edited": "ok"},
            {"post_id": 202, "verdict": "skip", "skip_reason": "missing_primary_source"},
            {"post_id": 301, "verdict": "guard_fail", "guard_fail": "guard_a"},
        ])
        self.assertEqual(payload["skip_reason_counts"], {
            "live_update_excluded": 1,
            "missing_primary_source": 1,
            "recently_touched": 1,
        })

    def test_default_max_posts_is_five(self):
        paged_posts = {
            1: [
                _make_post(101, modified="2026-04-20T07:00:00+09:00"),
                _make_post(102, modified="2026-04-20T07:10:00+09:00"),
            ],
            2: [
                _make_post(103, modified="2026-04-20T07:20:00+09:00"),
                _make_post(104, modified="2026-04-20T07:30:00+09:00"),
            ],
            3: [
                _make_post(105, modified="2026-04-20T07:40:00+09:00"),
                _make_post(106, modified="2026-04-20T07:50:00+09:00"),
            ],
            4: [],
        }
        get_post_map = {post_id: _make_post(post_id, modified=f"2026-04-20T07:{(post_id - 101) * 10:02d}:00+09:00") for post_id in range(101, 107)}
        wp = _FakeWP(paged_posts=paged_posts, get_post_map=get_post_map)
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(5),
        )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 5)
        self.assertEqual(len(payload["per_post_outcomes"]), 5)
        self.assertEqual(payload["aggregate_counts"]["selected_for_processing"], 5)
        self.assertEqual(wp.get_post_calls, [101, 102, 103, 104, 105])
        self.assertEqual(len(wp.put_calls), 5)

    def test_recently_edited_by_lane_skips(self):
        wp = _FakeWP(paged_posts={1: [_make_post(401)], 2: []})
        code, stdout, _, _, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00"],
            wp=wp,
            touched_ids={401},
        )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "no_candidate")
        self.assertEqual(payload["candidates_before_filter"], 1)
        self.assertEqual(payload["skip_reason_counts"], {"recently_edited_by_lane": 1})

    def test_editor_input_error_stops(self):
        post = _make_post(501)
        wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={501: post})
        code, stdout, _, _, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00"],
            wp=wp,
            run_editor_side_effect=[(30, None, "bad input", None)],
        )
        self.assertEqual(code, lane.EXIT_INPUT_ERROR)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "input_error")
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 501, "verdict": "skip", "skip_reason": "input_error"}
        ])

    def test_editor_api_fail_twice_stops(self):
        post = _make_post(601)
        wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={601: post})
        code, stdout, _, _, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00"],
            wp=wp,
            run_editor_side_effect=[(20, None, "api fail", None), (20, None, "api fail", None)],
        )
        self.assertEqual(code, lane.EXIT_API_FAIL)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "api_fail")
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 601, "verdict": "skip", "skip_reason": "api_fail"}
        ])

    def test_guard_reject_three_streak_stops(self):
        posts = {
            1: [
                _make_post(701, modified="2026-04-20T07:00:00+09:00"),
                _make_post(702, modified="2026-04-20T07:10:00+09:00"),
                _make_post(703, modified="2026-04-20T07:20:00+09:00"),
            ],
            2: [],
        }
        get_post_map = {701: _make_post(701, modified="2026-04-20T07:00:00+09:00"), 702: _make_post(702, modified="2026-04-20T07:10:00+09:00"), 703: _make_post(703, modified="2026-04-20T07:20:00+09:00")}
        wp = _FakeWP(paged_posts=posts, get_post_map=get_post_map)
        code, stdout, _, _, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00", "--max-posts", "3"],
            wp=wp,
            run_editor_side_effect=[
                (10, None, "guard a", None),
                (11, None, "guard b", None),
                (12, None, "guard c", None),
            ],
        )
        self.assertEqual(code, lane.EXIT_REJECT_STREAK)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "reject_streak")
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 701, "verdict": "guard_fail", "guard_fail": "guard_a"},
            {"post_id": 702, "verdict": "guard_fail", "guard_fail": "guard_b"},
            {"post_id": 703, "verdict": "guard_fail", "guard_fail": "guard_c"},
        ])

    def test_dry_run_does_not_put(self):
        post = _make_post(801)
        wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={801: post})
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00", "--dry-run"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(1),
        )
        self.assertEqual(code, 0)
        self.assertEqual(wp.put_calls, [])
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 801, "verdict": "edited", "edited": "dry_run"}
        ])

    def test_content_only_put_payload(self):
        post = _make_post(851)
        wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={851: post})
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(1),
        )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 851, "verdict": "edited", "edited": "ok"}
        ])
        self.assertEqual(len(wp.put_calls), 1)
        self.assertEqual(wp.put_calls[0][0], 851)
        self.assertEqual(wp.put_calls[0][1], {"content": SUCCESS_BODY})
        self.assertEqual(set(wp.put_calls[0][1].keys()), {"content"})
        self.assertEqual(len(wp.put_calls[0][1]), 1)

    def test_put_fail_twice_stops(self):
        paged_posts = {
            1: [
                _make_post(901, modified="2026-04-20T08:00:00+09:00"),
                _make_post(902, modified="2026-04-20T08:10:00+09:00"),
            ],
            2: [],
        }
        get_post_map = {
            901: _make_post(901, modified="2026-04-20T08:00:00+09:00"),
            902: _make_post(902, modified="2026-04-20T08:10:00+09:00"),
        }
        wp = _FakeWP(paged_posts=paged_posts, get_post_map=get_post_map, put_side_effect=RuntimeError("403"))
        code, stdout, _, _, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00", "--max-posts", "2"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(2),
        )
        self.assertEqual(code, lane.EXIT_PUT_FAIL)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "put_fail")
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 901, "verdict": "skip", "skip_reason": "put_fail"},
            {"post_id": 902, "verdict": "skip", "skip_reason": "put_fail"},
        ])

    def test_wp_pagination_failure_stops_nonzero(self):
        paged_posts = {
            1: [_make_post(1001, modified="2026-04-20T08:00:00+09:00")],
            2: [_make_post(1002, modified="2026-04-20T08:10:00+09:00")],
        }
        wp = _FakeWP(paged_posts=paged_posts, raise_on_page=2)
        code, stdout, _, wp, _, editor_mock = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00"],
            wp=wp,
        )
        self.assertEqual(code, lane.EXIT_WP_GET_FAILED)
        self.assertEqual(wp.get_post_calls, [])
        self.assertFalse(editor_mock.called)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["stop_reason"], "wp_pagination_failed")
        self.assertEqual(payload["aggregate_counts"]["pages_fetched"], 1)


class TestCollectPaginatedCandidates(unittest.TestCase):
    def test_page_overflow_gracefully_returns_collected_candidates(self):
        now = lane._now_jst("2026-04-20T10:00:00+09:00")
        paged_posts = {
            1: [_make_post(1201, modified="2026-04-20T08:00:00+09:00")],
            2: [_make_post(1202, modified="2026-04-20T08:10:00+09:00")],
        }

        def _list_posts(**kwargs):
            page = int(kwargs["page"])
            if page == 3:
                raise RuntimeError("400 rest_post_invalid_page_number")
            return list(paged_posts.get(page, []))

        wp = Mock()
        wp.list_posts.side_effect = _list_posts

        candidates, fetch_mode, stats, skip_counter = lane._collect_paginated_candidates(
            wp,
            now=now,
            touched_ids=set(),
        )

        self.assertEqual(fetch_mode, "draft_list_paginated")
        self.assertEqual(candidates, [
            {"post_id": 1201, "modified_at": lane._parse_post_datetime(paged_posts[1][0], "modified_gmt", "modified", "date_gmt", "date")},
            {"post_id": 1202, "modified_at": lane._parse_post_datetime(paged_posts[2][0], "modified_gmt", "modified", "date_gmt", "date")},
        ])
        self.assertEqual(stats, {"pages_fetched": 3, "posts_seen": 2})
        self.assertEqual(skip_counter, {})

    def test_page_one_overflow_returns_empty_candidates(self):
        now = lane._now_jst("2026-04-20T10:00:00+09:00")
        wp = Mock()
        wp.list_posts.side_effect = RuntimeError("400 rest_post_invalid_page_number")

        candidates, fetch_mode, stats, skip_counter = lane._collect_paginated_candidates(
            wp,
            now=now,
            touched_ids=set(),
        )

        self.assertEqual(fetch_mode, "draft_list_paginated")
        self.assertEqual(candidates, [])
        self.assertEqual(stats, {"pages_fetched": 1, "posts_seen": 0})
        self.assertEqual(skip_counter, {})

    def test_non_overflow_runtime_error_still_returns_none(self):
        now = lane._now_jst("2026-04-20T10:00:00+09:00")
        paged_posts = {
            1: [_make_post(1301, modified="2026-04-20T08:00:00+09:00")],
        }

        def _list_posts(**kwargs):
            page = int(kwargs["page"])
            if page == 2:
                raise RuntimeError("network down")
            return list(paged_posts.get(page, []))

        wp = Mock()
        wp.list_posts.side_effect = _list_posts

        candidates, fetch_mode, stats, skip_counter = lane._collect_paginated_candidates(
            wp,
            now=now,
            touched_ids=set(),
        )

        self.assertIsNone(candidates)
        self.assertEqual(fetch_mode, "draft_list_paginated")
        self.assertEqual(stats, {"pages_fetched": 1, "posts_seen": 1})
        self.assertEqual(skip_counter, {})


if __name__ == "__main__":
    unittest.main()
