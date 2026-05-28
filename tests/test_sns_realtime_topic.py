"""Tests for sns_realtime_topic main module (ticket 445)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sns_realtime_topic import (  # noqa: E402
    PERMANENT_SLUG,
    build_article,
    collect_all_posts,
    filter_recent_24h,
    section_oembeds,
    should_run_now,
    split_by_level,
    wp_tag_url_for,
    wp_upsert,
)
from sns_realtime_topic_classifier import load_roster_aliases  # noqa: E402

JST = timezone(timedelta(hours=9))


# ----- should_run_now -----

def test_should_run_in_slot():
    assert should_run_now(datetime(2026, 5, 28, 10, 0, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 13, 4, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 17, 2, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 21, 0, tzinfo=JST))


def test_should_not_run_outside_slot():
    assert not should_run_now(datetime(2026, 5, 28, 11, 0, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 10, 5, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 9, 0, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 23, 0, tzinfo=JST))


# ----- filter_recent_24h -----

def test_filter_recent_24h_keeps_in_window():
    now = datetime(2026, 5, 28, 12, 0, tzinfo=JST)
    # 12 hours ago in UTC = 2026-05-28 03:00 JST → within 24h
    posts = [
        {"url": "u1", "published": (2026, 5, 28, 3, 0, 0, 0, 0, 0)},
        {"url": "u2", "published": (2026, 5, 26, 3, 0, 0, 0, 0, 0)},  # > 24h
    ]
    out = filter_recent_24h(posts, now)
    urls = {p["url"] for p in out}
    assert "u1" in urls
    assert "u2" not in urls


def test_filter_recent_24h_drops_no_published():
    now = datetime(2026, 5, 28, 12, 0, tzinfo=JST)
    out = filter_recent_24h([{"url": "u1", "published": None}], now)
    assert out == []


# ----- split_by_level -----

def test_split_by_level():
    roster = load_roster_aliases()
    posts = [
        {"text": "坂本勇人 が打った"},
        {"text": "ファームで好投"},
        {"text": "育成選手が三軍で活躍"},
    ]
    by = split_by_level(posts, roster)
    assert len(by["一軍"]) == 1
    assert len(by["二軍"]) == 1
    assert len(by["三軍"]) == 1


# ----- section_oembeds -----

def test_section_oembeds_limit_5():
    posts = [{"url": f"https://x.com/u/status/{i}", "text": ""} for i in range(10)]
    blocks = section_oembeds(posts)
    assert len(blocks) == 5


def test_section_oembeds_skip_empty_url():
    posts = [
        {"url": "", "text": ""},
        {"url": "https://x.com/u/status/1", "text": ""},
    ]
    blocks = section_oembeds(posts)
    assert len(blocks) == 1
    assert "twitter-tweet" in blocks[0]


# ----- collect_all_posts (dedup by URL) -----

def test_collect_all_posts_dedup():
    fake_posts = [
        {"url": "https://x.com/a/status/1", "text": "a1", "handle": "h1", "published": None},
        {"url": "https://x.com/a/status/1", "text": "a1 dup", "handle": "h2", "published": None},
        {"url": "https://x.com/b/status/2", "text": "b1", "handle": "h1", "published": None},
    ]
    with patch("sns_realtime_topic.fetch_handle_posts") as mock_fetch:
        # 1st call returns 2 posts (1 dup), 2nd call returns 1 post (dup of 1st)
        mock_fetch.side_effect = [
            [fake_posts[0], fake_posts[2]],
            [fake_posts[1]],
        ]
        out = collect_all_posts(["h1", "h2"])
    urls = [p["url"] for p in out]
    assert urls == ["https://x.com/a/status/1", "https://x.com/b/status/2"]


# ----- wp_upsert -----

def test_wp_upsert_creates_when_not_exists():
    mock_client = MagicMock()
    mock_client.api = "https://example.com/wp-json/wp/v2"
    mock_client.auth = ("u", "p")
    with patch("sns_realtime_topic.requests") as mock_req:
        get_resp = MagicMock()
        get_resp.json.return_value = []
        get_resp.raise_for_status.return_value = None
        mock_req.get.return_value = get_resp

        post_resp = MagicMock()
        post_resp.json.return_value = {"id": 100}
        post_resp.raise_for_status.return_value = None
        mock_req.post.return_value = post_resp

        op, pid = wp_upsert("title", "content", "slug-x", mock_client)
    assert op == "created"
    assert pid == 100


def test_wp_upsert_updates_when_exists():
    mock_client = MagicMock()
    mock_client.api = "https://example.com/wp-json/wp/v2"
    mock_client.auth = ("u", "p")
    with patch("sns_realtime_topic.requests") as mock_req:
        get_resp = MagicMock()
        get_resp.json.return_value = [{"id": 200}]
        get_resp.raise_for_status.return_value = None
        mock_req.get.return_value = get_resp

        post_resp = MagicMock()
        post_resp.json.return_value = {"id": 200}
        post_resp.raise_for_status.return_value = None
        mock_req.post.return_value = post_resp

        op, pid = wp_upsert("title", "content", "slug-x", mock_client)
    assert op == "updated"
    assert pid == 200


def test_wp_upsert_create_uses_draft_status():
    mock_client = MagicMock()
    mock_client.api = "https://example.com/wp-json/wp/v2"
    mock_client.auth = ("u", "p")
    with patch("sns_realtime_topic.requests") as mock_req:
        get_resp = MagicMock()
        get_resp.json.return_value = []
        get_resp.raise_for_status.return_value = None
        mock_req.get.return_value = get_resp

        post_resp = MagicMock()
        post_resp.json.return_value = {"id": 1}
        post_resp.raise_for_status.return_value = None
        mock_req.post.return_value = post_resp

        wp_upsert("t", "c", "slug-x", mock_client)

        create_call = mock_req.post.call_args_list[0]
        payload = create_call.kwargs.get("json") or create_call.args[-1]
        assert payload["status"] == "draft"
        assert payload["slug"] == "slug-x"


# ----- wp_tag_url_for -----

def test_wp_tag_url_for_japanese_name():
    url = wp_tag_url_for("坂本勇人")
    # URL-encoded UTF-8
    assert url.startswith("https://yoshilover.com/tag/")
    assert url.endswith("/")
    assert "%E5%9D%82%E6%9C%AC%E5%8B%87%E4%BA%BA" in url


def test_wp_tag_url_for_abe():
    url = wp_tag_url_for("阿部慎之助")
    assert "%E9%98%BF%E9%83%A8%E6%85%8E%E4%B9%8B%E5%8A%A9" in url


# ----- build_article smoke (permanent slug + counts return) -----

def test_build_article_permanent_slug():
    fixed_now = datetime(2026, 5, 28, 10, 0, tzinfo=JST)
    with patch("sns_realtime_topic.collect_all_posts", return_value=[]):
        title, html, slug, counts, meta = build_article(fixed_now)
    # permanent slug (Yahoo リアルタイム式 1 URL)
    assert slug == PERMANENT_SLUG == "giants-sns-realtime"
    # title は更新時刻入り
    assert "2026-05-28 10:00" in title
    assert "最終更新" in title
    assert meta["post_count_24h"] == 0
    assert counts == {}
    assert "出典" in html


def test_build_article_with_prev_counts_shows_delta():
    fixed_now = datetime(2026, 5, 28, 10, 0, tzinfo=JST)
    fake_posts = [
        {"text": "坂本勇人が3安打 また坂本勇人 / 別 post で坂本勇人", "url": "https://x.com/u/status/1", "handle": "h"},
    ]
    # 3 alias 含むので canonical count = 1 (alias dedup)、 でも post 3 件分にしたい:
    fake_posts = [
        {"text": "坂本勇人が3安打", "url": "https://x.com/u/status/1", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"text": "坂本勇人 また打った", "url": "https://x.com/u/status/2", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
    ]
    with patch("sns_realtime_topic.collect_all_posts", return_value=fake_posts):
        title, html, slug, counts, meta = build_article(
            fixed_now,
            prev_counts={"坂本勇人": 0},
        )
    # 今日 2 回、 昨日 0 → ↑+2 が出る
    assert counts.get("坂本勇人") == 2
    assert "↑+2" in html or "↑+" in html  # delta badge


# ----- run() delegates to load_previous_counts and save_counts -----

def test_run_loads_prev_and_saves_counts():
    fixed_now = datetime(2026, 5, 28, 17, 0, tzinfo=JST)
    mock_wp = MagicMock()
    mock_wp.api = "https://example.com/wp-json/wp/v2"
    mock_wp.auth = ("u", "p")
    fake_posts = [
        {
            "text": "坂本勇人 3 安打",
            "url": "https://x.com/u/status/1",
            "handle": "h",
            "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0),
        },
        {
            "text": "坂本勇人 また",
            "url": "https://x.com/u/status/2",
            "handle": "h",
            "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0),
        },
    ]
    with patch("sns_realtime_topic.collect_all_posts", return_value=fake_posts), \
         patch("sns_realtime_topic.load_previous_counts", return_value={"坂本勇人": 1}) as mock_load, \
         patch("sns_realtime_topic.save_counts", return_value=True) as mock_save, \
         patch("sns_realtime_topic.requests") as mock_req:
        get_resp = MagicMock()
        get_resp.json.return_value = []
        get_resp.raise_for_status.return_value = None
        mock_req.get.return_value = get_resp
        post_resp = MagicMock()
        post_resp.json.return_value = {"id": 999}
        post_resp.raise_for_status.return_value = None
        mock_req.post.return_value = post_resp

        from sns_realtime_topic import run as _run
        result = _run(wp_client=mock_wp, now=fixed_now)

    assert result["ran"] is True
    assert result["slug"] == PERMANENT_SLUG
    assert result["save_counts_ok"] is True
    mock_load.assert_called_once()
    mock_save.assert_called_once()
