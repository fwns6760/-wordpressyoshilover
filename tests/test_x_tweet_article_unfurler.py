"""Unit tests for src.x_tweet_article_unfurler."""
from __future__ import annotations

import logging
from unittest import mock

import pytest

from src import x_tweet_article_unfurler as mod

_TWEET_URL = "https://twitter.com/hochi_giants/status/2055016267476504682"
_TCO_URL = "https://t.co/GKOyLJDBh4"
_ARTICLE_URL = "https://hochi.news/articles/20260514-OHT1T51385.html"

_OEMBED_PAYLOAD = {
    "html": (
        '<blockquote class="twitter-tweet" data-dnt="true">'
        '<p lang="ja" dir="ltr">ヘッドライン'
        f'<a href="{_TCO_URL}">{_TCO_URL}</a></p>'
        '&mdash; スポーツ報知 巨人取材班 (@hochi_giants)</blockquote>'
    )
}


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_x_unfurler")


def _resp(status: int = 200, *, json_payload=None, headers=None, text: str = ""):
    r = mock.Mock()
    r.status_code = status
    r.headers = headers or {}
    r.text = text
    r.json = mock.Mock(return_value=json_payload or {})
    return r


def test_is_tweet_url_matches_twitter_and_x() -> None:
    assert mod.is_tweet_url("https://twitter.com/foo/status/1")
    assert mod.is_tweet_url("https://x.com/foo/status/1")
    assert mod.is_tweet_url("https://mobile.twitter.com/foo/status/1")
    assert not mod.is_tweet_url("https://hochi.news/articles/x.html")
    assert not mod.is_tweet_url("")


def test_source_name_for_known_hosts() -> None:
    assert mod.source_name_for_article_url(_ARTICLE_URL) == "スポーツ報知"
    assert mod.source_name_for_article_url(
        "https://www.sanspo.com/giants/x"
    ) == "サンスポ"
    assert mod.source_name_for_article_url("https://example.com/x") == ""


def test_full_chain_returns_article_html(logger: logging.Logger) -> None:
    def fake_get(url, *a, **kw):
        if url == mod._OEMBED_URL:
            return _resp(200, json_payload=_OEMBED_PAYLOAD)
        if url == _ARTICLE_URL:
            return _resp(200, text="<html>ARTICLE_BODY</html>")
        raise AssertionError(f"unexpected GET: {url}")

    def fake_head(url, *a, **kw):
        if url == _TCO_URL:
            return _resp(301, headers={"Location": _ARTICLE_URL})
        raise AssertionError(f"unexpected HEAD: {url}")

    with mock.patch.object(mod.requests, "get", side_effect=fake_get), \
         mock.patch.object(mod.requests, "head", side_effect=fake_head):
        article_url, html = mod.fetch_outbound_article_for_tweet(
            _TWEET_URL, logger
        )

    assert article_url == _ARTICLE_URL
    assert html == "<html>ARTICLE_BODY</html>"


def test_non_tweet_url_short_circuits(logger: logging.Logger) -> None:
    with mock.patch.object(mod.requests, "get") as g, \
         mock.patch.object(mod.requests, "head") as h:
        url, html = mod.fetch_outbound_article_for_tweet(_ARTICLE_URL, logger)
    assert (url, html) == ("", "")
    g.assert_not_called()
    h.assert_not_called()


def test_oembed_http_error_returns_empty(logger: logging.Logger) -> None:
    with mock.patch.object(mod.requests, "get",
                           return_value=_resp(500)), \
         mock.patch.object(mod.requests, "head") as h:
        url, html = mod.fetch_outbound_article_for_tweet(_TWEET_URL, logger)
    assert (url, html) == ("", "")
    h.assert_not_called()


def test_oembed_with_no_tco_returns_empty(logger: logging.Logger) -> None:
    with mock.patch.object(mod.requests, "get",
                           return_value=_resp(200, json_payload={"html": "<p>no link</p>"})), \
         mock.patch.object(mod.requests, "head") as h:
        url, html = mod.fetch_outbound_article_for_tweet(_TWEET_URL, logger)
    assert (url, html) == ("", "")
    h.assert_not_called()


def test_disallowed_host_skipped(logger: logging.Logger) -> None:
    payload = {"html": f'<a href="https://t.co/EVIL01">x</a>'}
    def fake_get(url, *a, **kw):
        if url == mod._OEMBED_URL:
            return _resp(200, json_payload=payload)
        raise AssertionError("article GET should not be called")

    def fake_head(url, *a, **kw):
        return _resp(
            301, headers={"Location": "https://evil.example.com/foo"}
        )

    with mock.patch.object(mod.requests, "get", side_effect=fake_get), \
         mock.patch.object(mod.requests, "head", side_effect=fake_head):
        url, html = mod.fetch_outbound_article_for_tweet(_TWEET_URL, logger)
    assert (url, html) == ("", "")


def test_tco_no_location_skipped(logger: logging.Logger) -> None:
    with mock.patch.object(mod.requests, "get",
                           return_value=_resp(200, json_payload=_OEMBED_PAYLOAD)), \
         mock.patch.object(mod.requests, "head",
                           return_value=_resp(200, headers={})):
        url, html = mod.fetch_outbound_article_for_tweet(_TWEET_URL, logger)
    assert (url, html) == ("", "")


def test_rss_fetcher_inserts_excerpt_before_topic_summary(
    logger: logging.Logger,
) -> None:
    """Integration: when an X-source draft body contains both
    「📌 関連ポスト」(with twitter-tweet) and 「【話題の要旨】」, the
    rss_fetcher helper must place the orange excerpt block AFTER the tweet
    and BEFORE 「【話題の要旨】」, with a link in the attribution.
    """
    from src import rss_fetcher
    from src import x_tweet_article_unfurler as unfurl_mod

    article_html = (
        '<html><head><script type="application/ld+json">{"@type":'
        '"NewsArticle","articleBody":"日本テレビは１６、１７日の巨人・'
        'ＤｅＮＡ戦（東京Ｄ）を地上波生中継（関東）する。「ＮＥＸＴ」'
        'と「ＮＯＷ」をテーマに、次のイニング、次の打席、次の１球で'
        '試合が動くか先読みしながら中継する。"}</script></head>'
        '<body></body></html>'
    )
    body = (
        '<!-- wp:html --><div>banner</div><!-- /wp:html -->'
        '<!-- wp:paragraph --><p>title rehash</p><!-- /wp:paragraph -->'
        '<!-- wp:heading {"level":4} --><h4>📌 関連ポスト</h4>'
        '<!-- /wp:heading -->'
        '<!-- wp:html --><div class="yoshilover-x-embed">'
        '<blockquote class="twitter-tweet" data-dnt="true">'
        '<a href="https://twitter.com/x/status/1">x</a></blockquote>'
        '</div><!-- /wp:html -->'
        '<!-- wp:heading --><h2>【話題の要旨】</h2><!-- /wp:heading -->'
        '<!-- wp:paragraph --><p>summary rehash</p><!-- /wp:paragraph -->'
    )

    with mock.patch.object(
        unfurl_mod,
        "fetch_outbound_article_for_tweet",
        return_value=("https://hochi.news/articles/x.html", article_html),
    ):
        out = rss_fetcher._maybe_insert_x_outbound_article_excerpt(
            body,
            source_url="https://twitter.com/hochi_giants/status/1",
            title="巨人ーＤｅＮＡ戦を日テレが２日連続地上波で生中継",
            summary="",
            logger=logger,
        )

    assert "nomotoke-source-excerpt" in out
    assert "スポーツ報知 原文</a>" in out
    assert 'color:#c54500' in out

    positions = [
        out.find(k)
        for k in (
            "📌 関連ポスト",
            'class="twitter-tweet"',
            "📖 本文抜粋",
            "【話題の要旨】",
        )
    ]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions), positions


def test_first_allowed_link_wins_over_disallowed(logger: logging.Logger) -> None:
    payload = {
        "html": (
            f'<a href="https://t.co/BAD0001">x</a>'
            f'<a href="{_TCO_URL}">y</a>'
        )
    }

    def fake_get(url, *a, **kw):
        if url == mod._OEMBED_URL:
            return _resp(200, json_payload=payload)
        if url == _ARTICLE_URL:
            return _resp(200, text="OK")
        raise AssertionError(f"unexpected GET: {url}")

    def fake_head(url, *a, **kw):
        if url == "https://t.co/BAD0001":
            return _resp(301, headers={"Location": "https://evil.example.com/x"})
        if url == _TCO_URL:
            return _resp(301, headers={"Location": _ARTICLE_URL})
        raise AssertionError(f"unexpected HEAD: {url}")

    with mock.patch.object(mod.requests, "get", side_effect=fake_get), \
         mock.patch.object(mod.requests, "head", side_effect=fake_head):
        url, html = mod.fetch_outbound_article_for_tweet(_TWEET_URL, logger)
    assert url == _ARTICLE_URL
    assert html == "OK"
