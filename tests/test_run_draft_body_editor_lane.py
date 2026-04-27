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
LINEUP_BODY = (
    "【試合概要】\n横浜スタジアムでの一戦です。\n"
    "【スタメン一覧】\n1番吉川、2番坂本、3番岡本です。\n"
    "【先発投手】\n井上温大が先発です。\n"
    "【注目ポイント】\n上位打線の出塁が焦点です。"
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


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


def _build_lineup_body(
    *,
    leading_headings: tuple[str, ...] = (),
    extra_after: dict[str, tuple[str, ...]] | None = None,
    omit_headings: set[str] | None = None,
) -> str:
    sections = [
        ("【試合概要】", "横浜スタジアムでの一戦です。"),
        ("【スタメン一覧】", "1番吉川、2番坂本、3番岡本です。"),
        ("【先発投手】", "井上温大が先発です。"),
        ("【注目ポイント】", "上位打線の出塁が焦点です。"),
    ]
    lines: list[str] = []
    extra_after = extra_after or {}
    omit_headings = omit_headings or set()

    for heading in leading_headings:
        lines.extend([heading, "装飾見出しの補足です。"])

    for heading, text in sections:
        if heading in omit_headings:
            continue
        lines.extend([heading, text])
        for extra_heading in extra_after.get(heading, ()):
            lines.extend([extra_heading, "装飾見出しの補足です。"])

    return "\n".join(lines)


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


def _make_unresolved_post(post_id: int, *, modified: str) -> dict:
    return _make_post(
        post_id,
        title="巨人スタメン発表",
        subtype=None,
        modified=modified,
    )


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


def _write_queue_file(path: Path, *posts: dict) -> None:
    path.write_text(
        "\n".join(json.dumps(post, ensure_ascii=False) for post in posts) + "\n",
        encoding="utf-8",
    )


def _read_jsonl_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


class TestUnresolvedAndStale(unittest.TestCase):
    def test_resolved_subtype_old_post_returns_false(self):
        now = lane._now_jst("2026-04-26T14:30:00+09:00")
        post = _make_post(1151, subtype="postgame", modified="2026-04-24T09:00:00+09:00")
        self.assertFalse(lane._is_unresolved_and_stale(post, now))

    def test_unresolved_subtype_twelve_hours_old_returns_false(self):
        now = lane._now_jst("2026-04-26T14:30:00+09:00")
        post = _make_unresolved_post(1152, modified="2026-04-26T02:30:00+09:00")
        self.assertFalse(lane._is_unresolved_and_stale(post, now))

    def test_unresolved_subtype_thirty_hours_old_returns_true(self):
        now = lane._now_jst("2026-04-26T14:30:00+09:00")
        post = _make_unresolved_post(1153, modified="2026-04-25T08:30:00+09:00")
        self.assertTrue(lane._is_unresolved_and_stale(post, now))

    def test_unresolved_subtype_without_modified_returns_false(self):
        now = lane._now_jst("2026-04-26T14:30:00+09:00")
        post = _make_unresolved_post(1154, modified="2026-04-26T08:00:00+09:00")
        post["modified"] = ""
        self.assertFalse(lane._is_unresolved_and_stale(post, now))


class TestDecorativeHeadingStripper(unittest.TestCase):
    def test_decorative_only_returns_empty(self):
        headings = (
            "【📊 今日のスタメンデータ】",
            "【👀 スタメンの見どころ】",
            "【📌 関連ポスト】",
        )
        self.assertEqual(lane._strip_decorative_headings(headings), [])

    def test_mixed_headings_keep_expected_only(self):
        headings = (
            "【📊 今日のスタメンデータ】",
            "【試合概要】",
            "【📌 関連ポスト】",
            "【スタメン一覧】",
        )
        self.assertEqual(
            lane._strip_decorative_headings(headings),
            ["【試合概要】", "【スタメン一覧】"],
        )

    def test_empty_input_returns_empty(self):
        self.assertEqual(lane._strip_decorative_headings(()), [])

    def test_non_decorative_heading_is_preserved(self):
        headings = ("【関連情報】",)
        self.assertEqual(lane._strip_decorative_headings(headings), ["【関連情報】"])

    def test_all_known_emoji_prefixes_are_removed(self):
        for emoji in ("📊", "👀", "📌", "💬", "🔥", "⚾", "📝"):
            with self.subTest(emoji=emoji):
                heading = f"【{emoji} 装飾見出し】"
                self.assertEqual(lane._strip_decorative_headings((heading,)), [])


class TestLineupHeadingTolerance(unittest.TestCase):
    def test_lane_accepts_lineup_with_decorative_heading_insertions(self):
        body = _build_lineup_body(
            leading_headings=("【📊 今日のスタメンデータ】",),
            extra_after={"【スタメン一覧】": ("【👀 スタメンの見どころ】",)},
        )
        post = _make_post(
            1161,
            title="巨人スタメン一覧",
            subtype="lineup",
            modified="2026-04-26T13:30:00+09:00",
            body=body,
        )
        wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={1161: post})
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-26T14:55:00+09:00"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(1),
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(wp.put_calls), 1)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 1161, "verdict": "edited", "edited": "ok"}
        ])

    def test_lane_accepts_lineup_without_decorative_heading(self):
        post = _make_post(
            1162,
            title="巨人スタメン一覧",
            subtype="lineup",
            modified="2026-04-26T13:30:00+09:00",
            body=LINEUP_BODY,
        )
        wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={1162: post})
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-26T14:55:00+09:00"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(1),
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(wp.put_calls), 1)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 1162, "verdict": "edited", "edited": "ok"}
        ])

    def test_lane_rejects_lineup_when_expected_heading_is_missing(self):
        post = _make_post(
            1163,
            title="巨人スタメン一覧",
            subtype="lineup",
            modified="2026-04-26T13:30:00+09:00",
            body=_build_lineup_body(omit_headings={"【先発投手】"}),
        )
        wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={1163: post})
        code, stdout, _, _, _, editor_mock = _run_main(
            ["--now-iso", "2026-04-26T14:55:00+09:00"],
            wp=wp,
        )
        self.assertEqual(code, 0)
        self.assertFalse(editor_mock.called)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 0)
        self.assertEqual(payload["skip_reason_counts"], {"heading_mismatch": 1})
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 1163, "verdict": "skip", "skip_reason": "heading_mismatch"}
        ])

    def test_lane_accepts_each_known_decorative_emoji_prefix(self):
        for idx, emoji in enumerate(("📊", "👀", "📌", "💬", "🔥", "⚾", "📝"), start=1170):
            with self.subTest(emoji=emoji):
                post = _make_post(
                    idx,
                    title="巨人スタメン一覧",
                    subtype="lineup",
                    modified="2026-04-26T13:30:00+09:00",
                    body=_build_lineup_body(leading_headings=(f"【{emoji} 装飾見出し】",)),
                )
                wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={idx: post})
                code, stdout, _, _, _, _ = _run_main(
                    ["--now-iso", "2026-04-26T14:55:00+09:00"],
                    wp=wp,
                    run_editor_side_effect=_editor_success_runs(1),
                )
                self.assertEqual(code, 0)
                payload = json.loads(stdout.strip())
                self.assertEqual(payload["put_ok"], 1)
                self.assertEqual(payload["per_post_outcomes"], [
                    {"post_id": idx, "verdict": "edited", "edited": "ok"}
                ])


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

    def test_unresolved_and_stale_is_skipped_before_slot_selection(self):
        stale_unresolved = _make_unresolved_post(451, modified="2026-04-24T08:00:00+09:00")
        stale_resolved = _make_post(452, subtype="postgame", modified="2026-04-24T09:00:00+09:00")
        wp = _FakeWP(
            paged_posts={1: [stale_unresolved, stale_resolved], 2: []},
            get_post_map={452: stale_resolved},
        )
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-26T14:30:00+09:00", "--max-posts", "1"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(1),
        )
        self.assertEqual(code, 0)
        self.assertEqual(wp.get_post_calls, [452])
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["skip_reason_counts"], {"unresolved_and_stale": 1})
        self.assertEqual(payload["aggregate_counts"]["selected_for_processing"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 452, "verdict": "edited", "edited": "ok"}
        ])

    def test_fresh_unresolved_keeps_existing_subtype_unresolved_skip(self):
        fresh_unresolved = _make_unresolved_post(461, modified="2026-04-26T08:00:00+09:00")
        wp = _FakeWP(
            paged_posts={1: [fresh_unresolved], 2: []},
            get_post_map={461: fresh_unresolved},
        )
        code, stdout, _, _, _, editor_mock = _run_main(
            ["--now-iso", "2026-04-26T14:30:00+09:00"],
            wp=wp,
        )
        self.assertEqual(code, 0)
        self.assertFalse(editor_mock.called)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["skip_reason_counts"], {"subtype_unresolved": 1})
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 461, "verdict": "skip", "skip_reason": "subtype_unresolved"}
        ])

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

    def test_limit_alias_caps_processing_count(self):
        paged_posts = {
            1: [
                _make_post(861, modified="2026-04-20T08:00:00+09:00"),
                _make_post(862, modified="2026-04-20T08:10:00+09:00"),
            ],
            2: [],
        }
        get_post_map = {
            861: _make_post(861, modified="2026-04-20T08:00:00+09:00"),
            862: _make_post(862, modified="2026-04-20T08:10:00+09:00"),
        }
        wp = _FakeWP(paged_posts=paged_posts, get_post_map=get_post_map)
        code, stdout, _, wp, _, _ = _run_main(
            ["--now-iso", "2026-04-20T10:00:00+09:00", "--limit", "1"],
            wp=wp,
            run_editor_side_effect=_editor_success_runs(1),
        )
        self.assertEqual(code, 0)
        self.assertEqual(wp.get_post_calls, [861])
        self.assertEqual(len(wp.put_calls), 1)
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["aggregate_counts"]["selected_for_processing"], 1)

    def test_queue_path_uses_jsonl_without_wp_reads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "repair_queue.jsonl"
            queue_post = _make_post(871, modified="2026-04-20T08:00:00+09:00")
            _write_queue_file(queue_path, queue_post)
            wp = _FakeWP(paged_posts={1: [_make_post(9999)]}, get_post_map={9999: _make_post(9999)})
            code, stdout, _, wp, make_wp_client, _ = _run_main(
                [
                    "--now-iso", "2026-04-20T10:00:00+09:00",
                    "--queue-path", str(queue_path),
                    "--dry-run",
                ],
                wp=wp,
                run_editor_side_effect=_editor_success_runs(1),
                log_root=Path(tmpdir) / "lane_logs",
            )
        self.assertEqual(code, 0)
        self.assertFalse(make_wp_client.called)
        self.assertEqual(wp.list_calls, [])
        self.assertEqual(wp.get_post_calls, [])
        self.assertEqual(wp.put_calls, [])
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["fetch_mode"], lane.QUEUE_FETCH_MODE)
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 871, "verdict": "edited", "edited": "dry_run"}
        ])

    def test_provider_fallback_controller_dry_run_edits_without_subprocess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "repair_queue.jsonl"
            queue_post = _make_post(881, modified="2026-04-20T08:00:00+09:00")
            _write_queue_file(queue_path, queue_post)
            controller_instance = Mock()
            controller_instance.execute.return_value = lane.repair_fallback_controller.RepairResult(
                provider="gemini",
                fallback_used=True,
                body_text=SUCCESS_BODY,
                failure_chain=[
                    lane.repair_fallback_controller.FailureRecord(
                        provider="codex",
                        error_class="timeout",
                        error_message="primary timeout",
                        latency_ms=120000,
                    )
                ],
            )
            with patch(
                "src.tools.run_draft_body_editor_lane.repair_fallback_controller.RepairFallbackController",
                return_value=controller_instance,
            ):
                code, stdout, _, _, make_wp_client, editor_mock = _run_main(
                    [
                        "--now-iso", "2026-04-20T10:00:00+09:00",
                        "--queue-path", str(queue_path),
                        "--provider", "codex",
                        "--dry-run",
                    ],
                    log_root=Path(tmpdir) / "lane_logs",
                )

        self.assertEqual(code, 0)
        self.assertFalse(make_wp_client.called)
        self.assertFalse(editor_mock.called)
        controller_instance.execute.assert_called_once()
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 881, "verdict": "edited", "edited": "dry_run"}
        ])

    def test_provider_fallback_controller_live_puts_content_when_body_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "repair_queue.jsonl"
            queue_post = _make_post(882, modified="2026-04-20T08:00:00+09:00")
            _write_queue_file(queue_path, queue_post)
            controller_instance = Mock()
            controller_instance.execute.return_value = lane.repair_fallback_controller.RepairResult(
                provider="gemini",
                fallback_used=True,
                body_text=SUCCESS_BODY,
                failure_chain=[
                    lane.repair_fallback_controller.FailureRecord(
                        provider="openai_api",
                        error_class="rate_limit_429",
                        error_message="primary rate limit",
                        latency_ms=8000,
                    )
                ],
                wp_write_allowed=True,
            )
            wp = _FakeWP()
            with patch(
                "src.tools.run_draft_body_editor_lane.repair_fallback_controller.RepairFallbackController",
                return_value=controller_instance,
            ):
                code, stdout, _, wp, make_wp_client, editor_mock = _run_main(
                    [
                        "--now-iso", "2026-04-20T10:00:00+09:00",
                        "--queue-path", str(queue_path),
                        "--provider", "openai_api",
                    ],
                    wp=wp,
                    log_root=Path(tmpdir) / "lane_logs",
                )

        self.assertEqual(code, 0)
        self.assertTrue(make_wp_client.called)
        self.assertFalse(editor_mock.called)
        controller_instance.execute.assert_called_once()
        self.assertEqual(wp.put_calls, [(882, {"content": SUCCESS_BODY})])
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 882, "verdict": "edited", "edited": "ok"}
        ])

    def test_provider_fallback_controller_codex_shadow_only_skips_wp_put(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "repair_queue.jsonl"
            queue_post = _make_post(883, modified="2026-04-20T08:00:00+09:00")
            _write_queue_file(queue_path, queue_post)
            controller_instance = Mock()
            controller_instance.execute.return_value = lane.repair_fallback_controller.RepairResult(
                provider="codex",
                fallback_used=False,
                body_text=SUCCESS_BODY,
                failure_chain=[],
                wp_write_allowed=False,
            )
            wp = _FakeWP()
            with patch(
                "src.tools.run_draft_body_editor_lane.repair_fallback_controller.RepairFallbackController",
                return_value=controller_instance,
            ):
                code, stdout, _, wp, _, editor_mock = _run_main(
                    [
                        "--now-iso", "2026-04-20T10:00:00+09:00",
                        "--queue-path", str(queue_path),
                        "--provider", "codex",
                    ],
                    wp=wp,
                    log_root=Path(tmpdir) / "lane_logs",
                )

        self.assertEqual(code, 0)
        self.assertFalse(editor_mock.called)
        controller_instance.execute.assert_called_once()
        self.assertEqual(wp.put_calls, [])
        payload = json.loads(stdout.strip())
        self.assertEqual(payload["put_ok"], 1)
        self.assertEqual(payload["per_post_outcomes"], [
            {"post_id": 883, "verdict": "edited", "edited": "shadow_only"}
        ])

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


class TestPrimarySourceUrl(unittest.TestCase):
    def test_is_primary_source_accepts_twitter_team_official(self):
        self.assertTrue(
            lane._is_primary_source_url("https://twitter.com/TokyoGiants/status/1915758888888888888")
        )

    def test_is_primary_source_accepts_twitter_press_official(self):
        urls = (
            "https://twitter.com/hochi_giants/status/1915758888888888888",
            "https://twitter.com/sanspo_giants/status/1915758888888888888",
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(lane._is_primary_source_url(url))

    def test_is_primary_source_accepts_x_com_alias(self):
        self.assertTrue(
            lane._is_primary_source_url("https://x.com/TokyoGiants/status/1915758888888888888")
        )

    def test_is_primary_source_still_accepts_news_domains(self):
        urls = (
            "https://www.nikkansports.com/baseball/news/202604200001234.html",
            "https://www.sanspo.com/article/20260420-ABCDE12345/",
            "https://www.sponichi.co.jp/baseball/news/2026/04/20/kiji/20260420s00001173000000c.html",
            "https://hochi.news/articles/20260420-OHT1T51000.html",
            "https://www.nikkei.com/article/DGXZQOUC000000Q6A420C2000000/",
            "https://www.yomiuri.co.jp/sports/npb/20260420-OYT1T50123/",
            "https://www.daily.co.jp/baseball/2026/04/20/0018588888.shtml",
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(lane._is_primary_source_url(url))

    def test_is_primary_source_accepts_210a_family_domains(self):
        urls = (
            "https://www.giants.jp/game/20260420/preview/",
            "https://www.npb.jp/news/20260427/notice.html",
            "https://news.yahoo.co.jp/articles/abcdef1234567890",
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(lane._is_primary_source_url(url))

    def test_is_primary_source_rejects_non_whitelisted(self):
        self.assertFalse(lane._is_primary_source_url("https://example.com/article"))


class TestExtractSourceUrls(unittest.TestCase):
    def test_extract_source_urls_meta_present_uses_meta(self):
        post = _make_post(
            1401,
            source_urls=["https://www.giants.jp/game/20260420/preview/"],
            body=(
                '<p>本文</p>'
                '参照元: <a href="https://www.nikkansports.com/baseball/news/202604200001234.html">日刊</a>'
            ),
        )

        self.assertEqual(
            lane._extract_source_urls(post),
            ["https://www.giants.jp/game/20260420/preview/"],
        )

    def test_extract_source_urls_meta_empty_falls_back_to_body_footer(self):
        post = _make_post(
            1402,
            source_urls=[],
            body=(
                '<p>本文</p>'
                '参照元: <a href="https://www.nikkansports.com/baseball/news/202604200001234.html">日刊</a>'
            ),
        )

        self.assertEqual(
            lane._extract_source_urls(post),
            ["https://www.nikkansports.com/baseball/news/202604200001234.html"],
        )

    def test_extract_source_urls_meta_empty_body_no_footer_returns_empty(self):
        post = _make_post(
            1403,
            source_urls=[],
            body='<p>本文 <a href="https://www.nikkansports.com/baseball/news/202604200001234.html">関連</a></p>',
        )

        self.assertEqual(lane._extract_source_urls(post), [])

    def test_extract_source_urls_meta_empty_body_multiple_footers_uses_first(self):
        post = _make_post(
            1404,
            source_urls=[],
            body=(
                '参照元: <a href="https://www.nikkansports.com/baseball/news/202604200001234.html">日刊</a>'
                '<p>本文</p>'
                '参照元: <a href="https://hochi.news/articles/20260420-OHT1T51000.html">報知</a>'
            ),
        )

        self.assertEqual(
            lane._extract_source_urls(post),
            ["https://www.nikkansports.com/baseball/news/202604200001234.html"],
        )


class TestCloudLedgerIntegration(unittest.TestCase):
    def test_cloud_ledger_opt_in_is_best_effort(self):
        post = _make_post(1501, modified="2026-04-20T08:00:00+09:00")
        completed = lane.subprocess.CompletedProcess(args=[], returncode=0, stdout=b"token\n", stderr=b"")

        for mode in ("success", "firestore_failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmpdir:
                artifact_uris: list[str] = []

                def fake_requests(method, url, **kwargs):
                    if method == "POST" and "repair_ledger_locks" in url:
                        return _FakeResponse(200, {"name": "lock-doc"})
                    if method == "GET" and "repair_ledger/" in url:
                        return _FakeResponse(404, {"error": {"message": "missing"}})
                    if method == "POST" and "repair_ledger" in url:
                        if mode == "firestore_failure":
                            raise lane.repair_provider_ledger.requests.RequestException("firestore down")
                        artifact_uris.append(kwargs["json"]["fields"]["artifact_uri"]["stringValue"])
                        return _FakeResponse(200, {"name": "ledger-doc"})
                    if method == "DELETE" and "repair_ledger_locks" in url:
                        return _FakeResponse(200, {})
                    raise AssertionError(f"unexpected request: {method} {url}")

                def fake_run_editor(candidate, *, dry_run, ledger_path, now):
                    entry = lane.runner_ledger_integration.build_entry(
                        lane="repair",
                        provider="gemini",
                        model="gemini-2.5-flash",
                        source_post_id=candidate["post_id"],
                        before_body=candidate["current_body"],
                        after_body="" if dry_run else SUCCESS_BODY,
                        status="success",
                        quality_flags=["dry_run" if dry_run else "exec"],
                        input_payload={
                            "post_id": candidate["post_id"],
                            "dry_run": dry_run,
                        },
                        artifact_uri="file:///tmp/local-artifact.json",
                    )
                    ledger_path.parent.mkdir(parents=True, exist_ok=True)
                    with ledger_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
                    return (
                        0,
                        {"guards": "pass", "provider": "gemini", "fallback_used": False, "wp_write_allowed": True},
                        "",
                        SUCCESS_BODY if not dry_run else None,
                    )

                wp = _FakeWP(paged_posts={1: [post], 2: []}, get_post_map={1501: post})
                with patch.dict(
                    "os.environ",
                    {
                        lane.runner_ledger_integration.ENV_LEDGER_FIRESTORE_ENABLED: "true",
                        lane.runner_ledger_integration.ENV_LEDGER_GCS_ARTIFACT_ENABLED: "true",
                        "GOOGLE_CLOUD_PROJECT": "project-id",
                    },
                    clear=False,
                ), patch(
                    "src.repair_provider_ledger.subprocess.run",
                    return_value=completed,
                ), patch(
                    "src.cloud_run_persistence.subprocess.run",
                    return_value=completed,
                ), patch(
                    "src.repair_provider_ledger.requests.request",
                    side_effect=fake_requests,
                ):
                    code, stdout, stderr, wp, _, _ = _run_main(
                        ["--now-iso", "2026-04-20T10:00:00+09:00"],
                        wp=wp,
                        run_editor_side_effect=fake_run_editor,
                        log_root=Path(tmpdir) / "lane_logs",
                    )

                self.assertEqual(code, 0)
                self.assertEqual(wp.put_calls, [(1501, {"content": SUCCESS_BODY})])
                payload = json.loads(stdout.strip())
                self.assertEqual(payload["put_ok"], 1)
                if mode == "success":
                    self.assertTrue(artifact_uris)
                    self.assertTrue(all(uri.startswith("gs://yoshilover-history/repair_artifacts/") for uri in artifact_uris))
                else:
                    self.assertIn("firestore write failed", stderr)


if __name__ == "__main__":
    unittest.main()
