"""Tests for sns_realtime_topic main module (ticket 445, page split)."""

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
    PAGE_1GUN,
    PAGE_FARM,
    WP_AUTO_POST_CATEGORY_ID,
    build_pages,
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

def test_section_oembeds_limit():
    posts = [{"url": f"https://x.com/u/status/{i}", "text": ""} for i in range(20)]
    blocks = section_oembeds(posts, limit=15)
    assert len(blocks) == 15


def test_section_oembeds_skip_empty_url():
    posts = [
        {"url": "", "text": ""},
        {"url": "https://x.com/u/status/1", "text": ""},
    ]
    blocks = section_oembeds(posts, limit=5)
    assert len(blocks) == 1
    assert "twitter-tweet" in blocks[0]


# ----- collect_all_posts (dedup) -----

def test_collect_all_posts_dedup():
    fake = [
        {"url": "https://x.com/a/status/1", "text": "a1", "handle": "h1", "published": None},
        {"url": "https://x.com/a/status/1", "text": "dup", "handle": "h2", "published": None},
        {"url": "https://x.com/b/status/2", "text": "b1", "handle": "h1", "published": None},
    ]
    with patch("sns_realtime_topic.fetch_handle_posts") as mock_fetch:
        mock_fetch.side_effect = [[fake[0], fake[2]], [fake[1]]]
        out = collect_all_posts(["h1", "h2"])
    urls = [p["url"] for p in out]
    assert urls == ["https://x.com/a/status/1", "https://x.com/b/status/2"]


# ----- wp_tag_url_for -----

def test_wp_tag_url_for_japanese():
    url = wp_tag_url_for("坂本勇人")
    assert url.startswith("https://yoshilover.com/tag/")
    assert url.endswith("/")
    assert "%E5%9D%82%E6%9C%AC%E5%8B%87%E4%BA%BA" in url


# ----- wp_upsert -----

def test_wp_upsert_creates_when_not_exists_with_category():
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
        op, pid = wp_upsert("t", "c", "slug-x", mock_client)
    assert op == "created"
    assert pid == 100
    # create payload に category と draft が入ってる
    payload = mock_req.post.call_args.kwargs["json"]
    assert payload["status"] == "draft"
    assert payload["categories"] == [WP_AUTO_POST_CATEGORY_ID]


def test_wp_upsert_updates_when_exists_no_status_change():
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
        op, pid = wp_upsert("t", "c", "slug-x", mock_client)
    assert op == "updated"
    assert pid == 200
    # update payload には status / categories を含めない (既存 publish 状態を保つ)
    payload = mock_req.post.call_args.kwargs["json"]
    assert "status" not in payload
    assert "categories" not in payload


# ----- build_pages (page split) -----

def test_build_pages_two_pages_with_correct_slugs():
    now = datetime(2026, 5, 28, 17, 0, tzinfo=JST)
    with patch("sns_realtime_topic.collect_all_posts", return_value=[]):
        pages, counts_by_page = build_pages(now, prev_counts_by_page={})
    assert len(pages) == 2
    slugs = {p["slug"] for p in pages}
    assert slugs == {"giants-sns-realtime-1gun", "giants-sns-realtime-farm"}
    assert PAGE_1GUN["slug"] == "giants-sns-realtime-1gun"
    assert PAGE_FARM["slug"] == "giants-sns-realtime-farm"


def test_build_pages_titles_have_suffix():
    now = datetime(2026, 5, 28, 17, 0, tzinfo=JST)
    with patch("sns_realtime_topic.collect_all_posts", return_value=[]):
        pages, _ = build_pages(now)
    by_key = {p["page_key"]: p for p in pages}
    assert "(一軍)" in by_key["1gun"]["title"]
    assert "(二軍・三軍)" in by_key["farm"]["title"]
    assert "最終更新: 2026-05-28 17:00" in by_key["1gun"]["title"]


def test_build_pages_separates_levels():
    """一軍 page は一軍 post のみ、 farm page は二軍/三軍 のみ含む。"""
    now = datetime(2026, 5, 28, 17, 0, tzinfo=JST)
    fake_posts = [
        {"url": "https://x.com/u/1", "text": "坂本勇人 3 安打", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"url": "https://x.com/u/2", "text": "ファームで好投", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"url": "https://x.com/u/3", "text": "育成 三軍 で初登板", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
    ]
    with patch("sns_realtime_topic.collect_all_posts", return_value=fake_posts):
        pages, _ = build_pages(now)
    by_key = {p["page_key"]: p for p in pages}
    # 一軍 page = 1 post
    assert by_key["1gun"]["meta"]["post_count"] == 1
    # farm page = 二軍 1 + 三軍 1 = 2 post
    assert by_key["farm"]["meta"]["post_count"] == 2
    # 一軍 page の HTML に「最新の投稿」 section、 farm に「二軍」「三軍」
    assert "最新の投稿" in by_key["1gun"]["html"]
    assert "二軍" in by_key["farm"]["html"]
    assert "三軍" in by_key["farm"]["html"]


def test_build_pages_first_day_no_badge():
    """前日 counts なし (初日) は badge 抑制で ↑+N が出ない。"""
    now = datetime(2026, 5, 28, 10, 0, tzinfo=JST)
    fake_posts = [
        {"url": "https://x.com/u/1", "text": "坂本勇人 大爆発 / 坂本勇人 ヒット", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"url": "https://x.com/u/2", "text": "坂本勇人 また打った", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
    ]
    with patch("sns_realtime_topic.collect_all_posts", return_value=fake_posts):
        pages, _ = build_pages(now, prev_counts_by_page={})
    by_key = {p["page_key"]: p for p in pages}
    # 初日なので ↑+ は出ない
    assert "↑+" not in by_key["1gun"]["html"]


def test_build_pages_day2_shows_badge():
    """前日 counts あり (2 日目以降) は ↑+N が出る。"""
    now = datetime(2026, 5, 28, 10, 0, tzinfo=JST)
    fake_posts = [
        {"url": "https://x.com/u/1", "text": "坂本勇人 ヒット", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"url": "https://x.com/u/2", "text": "坂本勇人 また", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
    ]
    prev = {"1gun": {"坂本勇人": 0}, "farm": {}}
    with patch("sns_realtime_topic.collect_all_posts", return_value=fake_posts):
        pages, _ = build_pages(now, prev_counts_by_page=prev)
    by_key = {p["page_key"]: p for p in pages}
    assert "↑+" in by_key["1gun"]["html"]


# ----- run() -----

def test_run_outside_slot():
    not_slot = datetime(2026, 5, 28, 11, 30, tzinfo=JST)
    from sns_realtime_topic import run as _run
    result = _run(now=not_slot)
    assert result["ran"] is False
    assert result["reason"] == "outside_fire_slot"


def test_run_loads_prev_and_saves_counts_for_both_pages():
    now = datetime(2026, 5, 28, 17, 0, tzinfo=JST)
    mock_wp = MagicMock()
    mock_wp.api = "https://example.com/wp-json/wp/v2"
    mock_wp.auth = ("u", "p")
    fake_posts = [
        {"url": f"https://x.com/u/{i}", "text": "坂本勇人 安打" if i < 3 else "ファーム好投", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)}
        for i in range(5)
    ]
    with patch("sns_realtime_topic.collect_all_posts", return_value=fake_posts), \
         patch("sns_realtime_topic.load_previous_counts", return_value={"1gun": {"坂本勇人": 1}, "farm": {}}) as mock_load, \
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
        result = _run(wp_client=mock_wp, now=now)

    assert result["ran"] is True
    assert result["save_counts_ok"] is True
    assert len(result["results"]) == 2  # 2 pages
    mock_load.assert_called_once()
    mock_save.assert_called_once()
    # save_counts に渡された data は nested per-page
    saved = mock_save.call_args.args[0]
    assert "1gun" in saved
    assert "farm" in saved
