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
    WP_POST_TYPE,
    build_pages,
    collect_all_posts,
    filter_recent_24h,
    is_redundant_after_game_dense_slot,
    is_sns_only_game_dense_slot,
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
    assert should_run_now(datetime(2026, 5, 28, 15, 4, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 18, 15, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 18, 30, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 18, 45, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 21, 15, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 22, 0, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 17, 2, tzinfo=JST))
    assert should_run_now(datetime(2026, 5, 28, 21, 0, tzinfo=JST))


def test_should_not_run_outside_slot():
    assert not should_run_now(datetime(2026, 5, 28, 11, 0, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 10, 5, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 9, 0, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 21, 30, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 21, 45, tzinfo=JST))
    assert not should_run_now(datetime(2026, 5, 28, 23, 0, tzinfo=JST))


def test_game_dense_slots_are_sns_only_until_2115():
    assert is_sns_only_game_dense_slot(datetime(2026, 5, 28, 18, 15, tzinfo=JST))
    assert is_sns_only_game_dense_slot(datetime(2026, 5, 28, 18, 30, tzinfo=JST))
    assert is_sns_only_game_dense_slot(datetime(2026, 5, 28, 18, 45, tzinfo=JST))
    assert is_sns_only_game_dense_slot(datetime(2026, 5, 28, 21, 15, tzinfo=JST))
    assert not is_sns_only_game_dense_slot(datetime(2026, 5, 28, 18, 0, tzinfo=JST))
    assert not is_sns_only_game_dense_slot(datetime(2026, 5, 28, 21, 30, tzinfo=JST))
    assert not is_sns_only_game_dense_slot(datetime(2026, 5, 28, 21, 45, tzinfo=JST))


def test_extra_day_game_slots_are_sns_only_with_env():
    env = {
        "SNS_REALTIME_EXTRA_GAME_DATE": "2026-06-07",
        "SNS_REALTIME_EXTRA_GAME_START": "13:45",
        "SNS_REALTIME_EXTRA_GAME_END": "17:15",
    }
    with patch.dict("os.environ", env):
        assert should_run_now(datetime(2026, 6, 7, 13, 45, tzinfo=JST))
        assert should_run_now(datetime(2026, 6, 7, 14, 15, tzinfo=JST))
        assert should_run_now(datetime(2026, 6, 7, 17, 15, tzinfo=JST))
        assert not should_run_now(datetime(2026, 6, 7, 13, 30, tzinfo=JST))
        assert not should_run_now(datetime(2026, 6, 7, 17, 30, tzinfo=JST))
        assert is_sns_only_game_dense_slot(datetime(2026, 6, 7, 13, 45, tzinfo=JST))
        assert is_sns_only_game_dense_slot(datetime(2026, 6, 7, 14, 15, tzinfo=JST))
        assert is_sns_only_game_dense_slot(datetime(2026, 6, 7, 17, 15, tzinfo=JST))
        assert not is_sns_only_game_dense_slot(datetime(2026, 6, 7, 14, 0, tzinfo=JST))


def test_extra_day_game_does_not_mask_regular_night_dense_slots():
    env = {
        "SNS_REALTIME_EXTRA_GAME_DATE": "2026-06-07",
        "SNS_REALTIME_EXTRA_GAME_START": "13:45",
        "SNS_REALTIME_EXTRA_GAME_END": "18:00",
    }
    with patch.dict("os.environ", env):
        assert not is_sns_only_game_dense_slot(datetime(2026, 6, 7, 18, 0, tzinfo=JST))
        assert is_sns_only_game_dense_slot(datetime(2026, 6, 7, 18, 15, tzinfo=JST))


def test_after_2115_dense_slots_are_redundant_skip():
    assert is_redundant_after_game_dense_slot(datetime(2026, 5, 28, 21, 30, tzinfo=JST))
    assert is_redundant_after_game_dense_slot(datetime(2026, 5, 28, 21, 45, tzinfo=JST))
    assert not is_redundant_after_game_dense_slot(datetime(2026, 5, 28, 21, 15, tzinfo=JST))
    assert not is_redundant_after_game_dense_slot(datetime(2026, 5, 28, 22, 30, tzinfo=JST))


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


def test_collect_all_posts_filters_general_handles():
    """大手の野球全般 handle は巨人 relevance filter で他球団 post を落とす。"""
    from sns_realtime_topic import MAJOR_GENERAL_HANDLES, GIANTS_SPECIALIST_HANDLES

    general = MAJOR_GENERAL_HANDLES[0]
    specialist = GIANTS_SPECIALIST_HANDLES[0]
    general_posts = [
        {"url": "https://x.com/g/status/1", "text": "巨人 坂本勇人 3安打", "handle": general, "published": None},
        {"url": "https://x.com/g/status/2", "text": "阪神 佐藤輝明 満塁弾", "handle": general, "published": None},
    ]
    specialist_posts = [
        {"url": "https://x.com/s/status/3", "text": "本日の試合は雨天中止", "handle": specialist, "published": None},
    ]
    with patch("sns_realtime_topic.fetch_handle_posts") as mock_fetch:
        mock_fetch.side_effect = [general_posts, specialist_posts]
        out = collect_all_posts([general, specialist])
    urls = [p["url"] for p in out]
    # general: 巨人 post のみ通過 (阪神 post は drop) / specialist: keyword 無くても通過
    assert "https://x.com/g/status/1" in urls
    assert "https://x.com/g/status/2" not in urls
    assert "https://x.com/s/status/3" in urls


# ----- wp_tag_url_for -----

def test_wp_tag_url_for_japanese():
    url = wp_tag_url_for("坂本勇人")
    assert url.startswith("https://yoshilover.com/tag/")
    assert url.endswith("/")
    assert "%E5%9D%82%E6%9C%AC%E5%8B%87%E4%BA%BA" in url


# ----- wp_upsert -----

def test_wp_upsert_creates_page_when_not_exists():
    """post type = page で create (noindex 回避)。"""
    assert WP_POST_TYPE == "pages"
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
    # GET の endpoint が /pages であること
    get_url = mock_req.get.call_args.args[0]
    assert get_url.endswith("/pages")
    # POST の endpoint も /pages
    post_url = mock_req.post.call_args.args[0]
    assert "/pages" in post_url
    payload = mock_req.post.call_args.kwargs["json"]
    assert payload["status"] == "draft"
    # page は category 不要
    assert "categories" not in payload
    # _yoshilover_index 等の meta 操作も不要
    assert "meta" not in payload


def test_wp_upsert_updates_page_when_exists():
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
    payload = mock_req.post.call_args.kwargs["json"]
    assert "status" not in payload
    assert "categories" not in payload
    assert "meta" not in payload
    # update URL も /pages
    post_url = mock_req.post.call_args.args[0]
    assert "/pages/200" in post_url


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
    assert "今日のX話題まとめ" in by_key["1gun"]["title"]
    assert "2026-05-28" not in by_key["1gun"]["title"]
    assert "17:00" not in by_key["1gun"]["title"]


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


def test_build_pages_adds_editor_summary_and_human_excerpt():
    now = datetime(2026, 5, 28, 10, 0, tzinfo=JST)
    fake_posts = [
        {"url": "https://x.com/u/1", "text": "坂本勇人 ヒット", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"url": "https://x.com/u/2", "text": "坂本勇人 また打った", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"url": "https://x.com/u/3", "text": "岡本和真 本塁打", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
        {"url": "https://x.com/u/4", "text": "岡本和真 打点", "handle": "h", "published": (2026, 5, 28, 0, 0, 0, 0, 0, 0)},
    ]
    prev = {"1gun": {"坂本勇人": 0, "岡本和真": 1}, "farm": {}}
    with patch("sns_realtime_topic.collect_all_posts", return_value=fake_posts):
        pages, _ = build_pages(now, prev_counts_by_page=prev)
    one = {p["page_key"]: p for p in pages}["1gun"]
    assert "ヨシラバー注目ポイント" in one["html"]
    assert "今日の一軍SNSは坂本勇人、岡本和真を中心に動いています。" in one["html"]
    assert "X埋め込みは出典確認用" in one["html"]
    assert "ヨシラバーが整理" in one["excerpt"]
    assert "投稿/24h" not in one["excerpt"]
    assert "注目: 坂本勇人、岡本和真。" in one["excerpt"]


def test_merge_entry_text_removes_rsshub_duplicate_title_summary():
    from sns_realtime_topic import _merge_entry_text

    text = _merge_entry_text("坂本勇人が好守", "坂本勇人が好守")
    assert text == "坂本勇人が好守"
    text = _merge_entry_text("坂本勇人が好守", "坂本勇人が好守 詳細はこちら")
    assert text == "坂本勇人が好守 詳細はこちら"


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


# ----- 445 個人: 注目選手カード (Tier 1) -----

def test_build_featured_players_ranks_and_filters():
    from sns_realtime_topic import build_featured_players
    counts = {"戸郷翔征": 12, "岡本和真": 5, "坂本勇人": 1, "大勢": 3}
    prev = {"戸郷翔征": 8, "岡本和真": 5}
    html = build_featured_players(
        counts, prev, tag_resolver=lambda n: f"https://yoshilover.com/tag/{n}/",
        db_path=None, top_n=8, min_count=2,
    )
    # min_count=2 で 坂本(1) は除外、 件数降順
    assert "戸郷翔征" in html
    assert "大勢" in html
    assert "坂本勇人" not in html
    # 内部リンク + 件数 + 注目選手見出し
    assert "https://yoshilover.com/tag/" in html
    assert "注目選手" in html
    assert "12件" in html
    # db_path=None なら成績は空 (graceful、 page は出る)
    assert "今季" not in html


def test_build_featured_players_empty_when_no_counts():
    from sns_realtime_topic import build_featured_players
    assert build_featured_players({}, {}, tag_resolver=None, db_path=None) == ""


def test_render_featured_players_includes_stat_line():
    from sns_realtime_topic_template import render_featured_players
    html = render_featured_players([
        {"name": "戸郷翔征", "count": 12, "badge": "", "stat_line": "今季 8登板・防御率2.10・60K",
         "url": "https://yoshilover.com/data/togo/"},
    ])
    assert "今季 8登板" in html
    assert 'href="https://yoshilover.com/data/togo/"' in html
    assert "ysn-fp-section" in html
