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


def test_giants_official_recognized():
    assert source_trust.classify_url_family("https://www.giants.jp/news/20260427/1234/") == "giants_official"


def test_npb_official_recognized():
    assert source_trust.classify_url_family("https://www.npb.jp/news/20260427/notice.html") == "npb_official"


def test_sponichi_web_recognized():
    assert (
        source_trust.classify_url_family(
            "https://www.sponichi.co.jp/baseball/news/2026/04/27/kiji/20260427s00001173000000c.html"
        )
        == "sponichi"
    )


def test_sanspo_web_recognized():
    assert source_trust.classify_url_family("https://www.sanspo.com/article/20260427-ABCDE12345/") == "sanspo"


def test_daily_web_recognized():
    assert source_trust.classify_url_family("https://www.daily.co.jp/baseball/2026/04/27/0018588888.shtml") == "daily"


def test_yomiuri_online_recognized():
    assert source_trust.classify_url_family("https://www.yomiuri.co.jp/sports/npb/20260427-OYT1T50123/") == "yomiuri_online"


def test_yahoo_aggregator_recognized():
    assert source_trust.classify_url_family("https://news.yahoo.co.jp/articles/abcdef1234567890") == "yahoo_news_aggregator"


def test_trust_level_giants_official_is_high():
    assert source_trust.get_family_trust_level("giants_official") == "high"


def test_trust_level_yahoo_aggregator_is_mid():
    assert source_trust.get_family_trust_level("yahoo_news_aggregator") == "mid"


def test_existing_families_unchanged():
    assert source_trust.classify_url("https://news.hochi.news/articles/2026/04/21?foo=1") == "secondary"
    assert source_trust.classify_url("https://m.nikkansports.com/baseball/news/202604210000001_m.html") == "secondary"
    assert source_trust.classify_url_family("https://news.hochi.news/articles/2026/04/21?foo=1") == "hochi"
    assert source_trust.classify_url_family("https://m.nikkansports.com/baseball/news/202604210000001_m.html") == "nikkansports"
    assert source_trust.classify_handle_family("@sponichiyakyu") == "sponichi"
    assert source_trust.get_family_trust_level("hochi") == "mid"
    assert source_trust.get_family_trust_level("nikkansports") == "mid"
