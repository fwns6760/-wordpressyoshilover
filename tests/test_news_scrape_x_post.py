"""news_scrape_x_post の純ロジック検証(Gemini は stub 注入で API 不要)。"""

import urllib.parse

from src import news_scrape_x_post as nsx


def test_extract_quotes_dedupes_and_limits():
    body = (
        "彼は「一度は大きな番号をつけてやってみよう」と話した。"
        "さらに「米国で学んだ変化球をミックスして活躍を誓った」と語った。"
        "再び「一度は大きな番号をつけてやってみよう」と繰り返した。"  # 重複
        "短い「うん」は拾わない。"  # 8字未満
    )
    quotes = nsx.extract_quotes_from_text(body, max_quotes=3)
    assert quotes == [
        "一度は大きな番号をつけてやってみよう",
        "米国で学んだ変化球をミックスして活躍を誓った",
    ]


def test_format_scrape_post_uses_injected_generate_and_passes_facts():
    seen = {}

    def stub(prompt, *, model, api_key):
        seen["prompt"] = prompt
        seen["model"] = model
        return "  整形済みポスト  "

    facts = {"選手": "小笠原慎之介", "背番号": "98"}
    out = nsx.format_scrape_post(facts, model="m1", generate=stub)
    assert out == "整形済みポスト"  # strip される
    assert seen["model"] == "m1"
    assert "小笠原慎之介" in seen["prompt"]  # facts が prompt に入る
    assert "98" in seen["prompt"]


def test_build_intent_url_roundtrips_text():
    text = "【速報】テスト #巨人"
    url = nsx.build_intent_url(text)
    assert url.startswith(nsx.X_INTENT_URL_BASE + "?text=")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["text"][0] == text


def test_build_quote_intent_url_has_text_and_url():
    url = nsx.build_quote_intent_url("コメント", "https://x.com/foo/status/1")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["text"][0] == "コメント"
    assert q["url"][0] == "https://x.com/foo/status/1"


def test_build_email_html_contains_button_and_count_ok():
    html = nsx.build_email_html("短い投稿", label="テスト")
    assert nsx.X_INTENT_URL_BASE in html
    assert "タップして投稿する" in html
    assert "✅" in html  # 280 以内
    assert "テスト" in html


def test_build_email_html_flags_over_limit():
    html = nsx.build_email_html("あ" * (nsx.X_CHAR_LIMIT + 1))
    assert "超過" in html


def test_build_email_html_escapes_and_adds_quote_button():
    html = nsx.build_email_html("<script>x</script>", quote_url="https://x.com/a/status/9")
    assert "<script>x</script>" not in html  # エスケープされる
    assert "&lt;script&gt;" in html
    assert "引用RTで投稿" in html
