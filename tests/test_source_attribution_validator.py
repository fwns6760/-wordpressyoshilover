import pytest

from src import source_attribution_validator


@pytest.mark.parametrize(
    ("source_name", "source_url"),
    [
        ("読売ジャイアンツ公式サイト", "https://www.giants.jp/news/20260427/1234/"),
        ("NPB公式", "https://www.npb.jp/news/20260427/notice.html"),
        (
            "スポニチ",
            "https://www.sponichi.co.jp/baseball/news/2026/04/27/kiji/20260427s00001173000000c.html",
        ),
        ("サンスポ", "https://www.sanspo.com/article/20260427-ABCDE12345/"),
        ("デイリー", "https://www.daily.co.jp/baseball/2026/04/27/0018588888.shtml"),
        ("読売新聞オンライン", "https://www.yomiuri.co.jp/sports/npb/20260427-OYT1T50123/"),
        ("Yahoo!ニュース", "https://news.yahoo.co.jp/articles/abcdef1234567890"),
    ],
)
def test_validate_source_attribution_accepts_210a_web_families(source_name, source_url):
    result = source_attribution_validator.validate_source_attribution(
        article_subtype="postgame",
        rendered_html="<p>本文のみ</p>",
        source_context={
            "source_name": source_name,
            "source_url": source_url,
            "source_type": "web",
        },
    )

    assert result["ok"] is True
    assert result["fail_axis"] == ""
    assert result["primary_source_kind"] == "t1_web"
    assert result["required"] is False
    assert result["has_t1_web_source"] is False
