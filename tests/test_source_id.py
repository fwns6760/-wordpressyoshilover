import pytest

from src import source_id


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://Example.com/story/", "https://example.com/story"),
        (
            "https://example.com/story/?utm_source=rss&article=123&fbclid=abc",
            "https://example.com/story?article=123",
        ),
        ("https://example.com/story#top", "https://example.com/story"),
        ("https://www.hochi.news/giants/123/", "https://hochi.news/giants/123"),
        ("https://m.sanspo.com/baseball/giants?id=9", "https://sanspo.com/baseball/giants?id=9"),
    ],
)
def test_normalize_url(url, expected):
    assert source_id.normalize_url(url) == expected


def test_normalize_url_equates_folded_hosts():
    left = source_id.normalize_url("https://www.hochi.news/giants/123?utm_medium=social")
    right = source_id.normalize_url("https://hochi.news/giants/123")
    assert left == right


def test_source_id_collapses_x_and_twitter_status_urls():
    left = source_id.source_id("https://x.com/TokyoGiants/status/19001?ref_src=twsrc")
    right = source_id.source_id("https://twitter.com/tokyogiants/status/19001")
    assert left == right == "x:19001"


def test_source_id_absorbs_handle_case_variation():
    left = source_id.source_id("https://x.com/TokyoGiants/status/42")
    right = source_id.source_id("https://x.com/tokyogiants/status/42")
    assert left == right == "x:42"


def test_source_id_falls_back_for_non_numeric_x_paths():
    assert source_id.source_id("https://x.com/TokyoGiants/status/latest") == "x:tokyogiants:status/latest"



def test_source_id_normalizes_npb_hosts():
    left = source_id.source_id("https://www.npb.jp/scores/2026/04/21/g-t-01/")
    right = source_id.source_id("https://npb.jp/scores/2026/04/21/g-t-01")
    assert left == right == "https://npb.jp/scores/2026/04/21/g-t-01"


def test_source_id_returns_normalized_rss_article_url():
    url = "http://news.hochi.news/articles/2026/04/21/12345.html?utm_campaign=feed&article=123#body"
    assert source_id.source_id(url) == "https://hochi.news/articles/2026/04/21/12345.html?article=123"


@pytest.mark.parametrize("value", ["", "not a url"])
def test_edge_inputs_do_not_raise(value):
    result = source_id.source_id(value)
    assert isinstance(result, str)
