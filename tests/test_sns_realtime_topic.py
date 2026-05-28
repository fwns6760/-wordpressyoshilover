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
    build_article,
    collect_all_posts,
    filter_recent_24h,
    section_oembeds,
    should_run_now,
    split_by_level,
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


# ----- build_article smoke -----

def test_build_article_empty_posts_smoke():
    """No posts → still returns valid title/html/slug/meta with empty trend section."""
    fixed_now = datetime(2026, 5, 28, 10, 0, tzinfo=JST)
    with patch("sns_realtime_topic.collect_all_posts", return_value=[]):
        title, html, slug, meta = build_article(fixed_now)
    assert "2026-05-28 10:00" in title
    assert slug == "giants-sns-realtime-2026-05-28"
    assert meta["post_count_24h"] == 0
    # トレンド section は無いが 出典 footer はある
    assert "出典" in html
