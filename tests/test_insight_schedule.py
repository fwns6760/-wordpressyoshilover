"""Tests for src.analysis.insight_schedule."""

from __future__ import annotations

import datetime as dt

from src.analysis import insight_schedule as sch


_SCHEDULE_HTML_SAMPLE = """
<html><body>
<a href="/scores/2026/0510/d-g-08/box.html">中日 vs 巨人</a>
<a href="/scores/2026/0510/t-yb-08/box.html">阪神 vs 横浜</a>
<a href="/scores/2026/0511/g-c-09/box.html">巨人 vs 広島</a>
<a href="/scores/2026/0510/d-g-08/index.html">無関係 anchor</a>
</body></html>
"""


def test_parse_schedule_returns_all_box_anchors_when_no_target():
    out = sch.parse_npb_schedule_html(_SCHEDULE_HTML_SAMPLE)
    slugs = {c["slug"] for c in out}
    assert slugs == {
        "2026/0510/d-g-08",
        "2026/0510/t-yb-08",
        "2026/0511/g-c-09",
    }


def test_parse_schedule_filters_by_target_date():
    out = sch.parse_npb_schedule_html(_SCHEDULE_HTML_SAMPLE, target_date="2026-05-10")
    slugs = {c["slug"] for c in out}
    assert slugs == {"2026/0510/d-g-08", "2026/0510/t-yb-08"}


def test_parse_schedule_marks_giants_involvement():
    out = sch.parse_npb_schedule_html(_SCHEDULE_HTML_SAMPLE)
    by_slug = {c["slug"]: c for c in out}
    assert by_slug["2026/0510/d-g-08"]["involves_giants"] is True
    assert by_slug["2026/0511/g-c-09"]["involves_giants"] is True
    assert by_slug["2026/0510/t-yb-08"]["involves_giants"] is False


def test_resolve_giants_slug_returns_first_match():
    slug = sch.resolve_giants_slug_for_date(_SCHEDULE_HTML_SAMPLE, "2026-05-10")
    assert slug == "2026/0510/d-g-08"


def test_resolve_giants_slug_none_when_no_giants_game():
    html_no_giants = """<a href="/scores/2026/0510/t-yb-08/box.html">x</a>"""
    assert sch.resolve_giants_slug_for_date(html_no_giants, "2026-05-10") is None


def test_resolve_giants_slug_none_when_wrong_date():
    assert sch.resolve_giants_slug_for_date(_SCHEDULE_HTML_SAMPLE, "1999-01-01") is None


def test_parse_schedule_empty_html_returns_empty():
    assert sch.parse_npb_schedule_html("") == []
    assert sch.parse_npb_schedule_html(None) == []  # type: ignore[arg-type]


def test_url_helpers():
    assert sch.npb_monthly_schedule_url(2026, 5) == "https://npb.jp/games/2026/schedule_202605_01.html"
    assert sch.npb_daily_schedule_url(dt.date(2026, 5, 10)) == "https://npb.jp/games/2026/0510/index.html"


def test_previous_jst_date_morning():
    """JST 早朝 (00-09 時) は前日扱いになる。"""
    JST = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime(2026, 5, 13, 6, 0, tzinfo=JST)
    assert sch.previous_jst_date(now) == dt.date(2026, 5, 12)


def test_previous_jst_date_afternoon():
    JST = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime(2026, 5, 13, 15, 0, tzinfo=JST)
    assert sch.previous_jst_date(now) == dt.date(2026, 5, 12)


def test_parse_schedule_dedupes_duplicate_anchors():
    html = (
        '<a href="/scores/2026/0510/d-g-08/box.html">x</a>'
        '<a href="/scores/2026/0510/d-g-08/box.html">y</a>'
    )
    out = sch.parse_npb_schedule_html(html)
    assert len(out) == 1
