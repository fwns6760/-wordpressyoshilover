"""効果学習 v0 (x_post_engagement) のネットワーク非依存テスト。"""

from __future__ import annotations

from datetime import datetime, timezone

from src import x_post_engagement as eng


_NOW = datetime(2026, 6, 12, 3, 0, 0, tzinfo=timezone.utc)

_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Twitter @yoshilover</title>
<item>
  <title>大城卓三、直近7日で打率.294。 18打席で見せた頼もしさ。</title>
  <description>大城卓三、直近7日で打率.294。&lt;br&gt;18打席で見せた頼もしさ。&lt;br&gt;「どの球団も羨ましいんじゃないですか」</description>
  <link>https://x.com/yoshilover6760/status/2065202444842434906</link>
  <pubDate>Thu, 11 Jun 2026 22:40:07 GMT</pubDate>
</item>
<item>
  <title>RT 報知の記事</title>
  <description>RT mention</description>
  <link>https://x.com/hochi_giants/status/111</link>
  <pubDate>Thu, 11 Jun 2026 12:00:00 GMT</pubDate>
</item>
<item>
  <title>【巨人】今日の試合データ</title>
  <description>【巨人】今日の試合データ yoshilover.com/data</description>
  <link>https://x.com/yoshilover6760/status/2065202403444695398</link>
  <pubDate>Thu, 11 Jun 2026 09:20:11 GMT</pubDate>
</item>
</channel></rss>
"""


def test_syndication_token_golden():
    # 実 endpoint で 200 を確認済みの golden pair (2026-06-12)
    assert eng.syndication_token("2065202444842434906") == "58w6f6zrk9es"


def test_parse_feed_extracts_own_posts_and_skips_rt():
    records = eng.parse_feed(_FEED_XML, now_utc=_NOW)
    ids = [r.tweet_id for r in records]
    assert ids == ["2065202444842434906", "2065202403444695398"]


def test_parse_feed_classification_and_bucket():
    records = eng.parse_feed(_FEED_XML, now_utc=_NOW)
    first = records[0]
    # 22:40 UTC = JST 07:40 (翌朝)
    assert first.time_bucket == "morning_05-11"
    assert first.style == "data_fact"  # 「直近」数字パターン
    second = records[1]
    assert second.style == "article_share"  # yoshilover.com リンク優先


def test_classify_style_priorities():
    assert eng.classify_style("yoshilover.com/x 【巨人】") == "article_share"
    assert eng.classify_style("【巨人】岡本和真2本塁打") == "data_fact"
    assert eng.classify_style("岡本和真「最高です」しびれた") == "quote_comment"
    assert eng.classify_style("今日の継投は見事だった") == "voice"


def test_fetch_metrics_parses_syndication_payload():
    def fake_get(url: str) -> str:
        assert "tweet-result" in url
        return '{"favorite_count": 7, "conversation_count": 2}'

    metrics = eng.fetch_metrics("2065202444842434906", http_get=fake_get)
    assert metrics.fetched is True
    assert metrics.favorite_count == 7
    assert metrics.reply_count == 2


def test_fetch_metrics_handles_failure_without_raising():
    def fake_get(url: str) -> str:
        raise RuntimeError("boom")

    metrics = eng.fetch_metrics("123", http_get=fake_get)
    assert metrics.fetched is False
    assert metrics.error is not None


def test_collect_survives_feed_unavailable(monkeypatch):
    # RSSHub 失効 (503/401) などで feed 取得が落ちても collect は raise せず
    # feed_errors=1 を返してジョブを正常終了させる (アラート抑止)。
    def boom() -> str:
        raise eng.urllib.error.HTTPError(
            url="https://rsshub.example/twitter/user/yoshilover6760",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(eng, "fetch_feed_xml", boom)
    stats = eng.collect(now_utc=_NOW)
    assert stats == {"feed": 0, "written": 0, "skipped": 0, "feed_errors": 1}


def test_http_get_does_not_retry_4xx(monkeypatch):
    # 4xx (認証失効など) はリトライせず即 raise する。sleep も呼ばれない。
    calls = {"open": 0, "sleep": 0}

    def fake_urlopen(req, timeout=None):
        calls["open"] += 1
        raise eng.urllib.error.HTTPError(
            url="https://rsshub.example", code=401, msg="Unauthorized", hdrs=None, fp=None
        )

    monkeypatch.setattr(eng.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(eng.time, "sleep", lambda s: calls.__setitem__("sleep", calls["sleep"] + 1))
    try:
        eng._http_get("https://rsshub.example")
        assert False, "should have raised"
    except eng.urllib.error.HTTPError as exc:
        assert exc.code == 401
    assert calls["open"] == 1
    assert calls["sleep"] == 0


def test_http_get_retries_5xx_then_succeeds(monkeypatch):
    # 一時的な 5xx はリトライして最終的に成功する。
    calls = {"open": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(req, timeout=None):
        calls["open"] += 1
        if calls["open"] < 3:
            raise eng.urllib.error.HTTPError(
                url="https://rsshub.example", code=503, msg="busy", hdrs=None, fp=None
            )
        return _Resp()

    monkeypatch.setattr(eng.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(eng.time, "sleep", lambda s: None)
    assert eng._http_get("https://rsshub.example") == "ok"
    assert calls["open"] == 3


def test_build_weekly_report_aggregates_and_sorts():
    posts = eng.parse_feed(_FEED_XML, now_utc=_NOW)
    metrics = {
        "2065202444842434906": eng.PostMetrics(
            tweet_id="2065202444842434906", favorite_count=5, reply_count=1, fetched=True
        ),
        "2065202403444695398": eng.PostMetrics(
            tweet_id="2065202403444695398", favorite_count=9, reply_count=0, fetched=True
        ),
    }
    report = eng.build_weekly_report(
        posts, metrics, period_start_jst="2026-06-05", period_end_jst="2026-06-11"
    )
    assert report.total_posts == 2
    assert report.total_favorites == 14
    assert report.rows[0]["favorite_count"] == 9  # 降順
    assert report.by_style["data_fact"]["avg_favorites"] == 5.0
    text = eng.render_report_text(report)
    assert "週次エンゲージレポート" in text
    assert "TOP 5" in text
    assert "取得失敗" not in text  # 全件 fetched なら明記行なし


def test_render_report_marks_metrics_misses():
    posts = eng.parse_feed(_FEED_XML, now_utc=_NOW)
    report = eng.build_weekly_report(
        posts, {}, period_start_jst="2026-06-05", period_end_jst="2026-06-11"
    )
    assert "メトリクス取得失敗 2 件" in eng.render_report_text(report)
