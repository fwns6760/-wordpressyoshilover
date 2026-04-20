import pytest

from src import source_trust


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.giants.jp/news/123?ref=top", "primary"),
        ("https://news.hochi.news/articles/2026/04/21?foo=1", "secondary"),
        ("https://www.reddit.com/r/baseball/comments/abc123/", "rumor"),
        ("https://example.org/story", "unknown"),
        ("https://NPB.jp/news/article?game=1", "primary"),
        ("https://m.nikkansports.com/baseball/news/202604210000001_m.html", "secondary"),
        ("https://x.com/TokyoGiants/status/1?ref_src=twsrc", "primary"),
    ],
)
def test_classify_url(url, expected):
    assert source_trust.classify_url(url) == expected


@pytest.mark.parametrize(
    ("handle", "expected"),
    [
        ("@TokyoGiants", "primary"),
        ("nikkansports", "secondary"),
        ("@SaNsPo_GiAnTs", "secondary"),
        ("unknown_account", "unknown"),
    ],
)
def test_classify_handle(handle, expected):
    assert source_trust.classify_handle(handle) == expected
