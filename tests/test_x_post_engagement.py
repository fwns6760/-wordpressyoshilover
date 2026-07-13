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

# ---------------------------------------------------------------------------
# follower snapshot
# ---------------------------------------------------------------------------

_LEGACY_BODY = (
    '{"data": {"user": {"result": {"legacy": '
    '{"followers_count": 10650, "friends_count": 4409, "statuses_count": 45422}}}}}'
)


def test_fetch_follower_counts_happy_path():
    def fake_graphql(url: str, headers: dict[str, str]) -> tuple[int, str]:
        assert "UserByScreenName" in url
        assert "yoshilover6760" in url
        assert headers["x-csrf-token"] in headers["Cookie"]
        return 200, _LEGACY_BODY

    result = eng.fetch_follower_counts(
        "yoshilover6760", auth_token="tok", graphql_get=fake_graphql
    )
    assert result == {
        "followers_count": 10650,
        "friends_count": 4409,
        "statuses_count": 45422,
        "fetched": True,
    }


def test_fetch_follower_counts_retries_missing_features():
    calls: list[str] = []

    def fake_graphql(url: str, headers: dict[str, str]) -> tuple[int, str]:
        calls.append(url)
        if len(calls) == 1:
            return 400, (
                '{"errors": [{"message": "The following features cannot be null: '
                'rweb_tipjar_consumption_enabled, verified_phone_label_enabled"}]}'
            )
        return 200, _LEGACY_BODY

    result = eng.fetch_follower_counts(
        "yoshilover6760", auth_token="tok", graphql_get=fake_graphql
    )
    assert result["fetched"] is True
    # 2 回目の request に不足 feature が false で入っている
    assert "rweb_tipjar_consumption_enabled" in calls[1]
    assert "verified_phone_label_enabled" in calls[1]


def test_fetch_follower_counts_fails_soft():
    def fake_graphql(url: str, headers: dict[str, str]) -> tuple[int, str]:
        return 401, '{"errors": [{"message": "Could not authenticate you"}]}'

    result = eng.fetch_follower_counts("x", auth_token="bad", graphql_get=fake_graphql)
    assert result["fetched"] is False
    assert "authenticate" in result["error"]


class _FakeBlob:
    def __init__(self, store: dict[str, str], name: str):
        self._store = store
        self.name = name

    def exists(self) -> bool:
        return self.name in self._store

    def upload_from_string(self, data: str, content_type: str = "") -> None:
        self._store[self.name] = data

    def download_as_text(self) -> str:
        return self._store[self.name]


class _FakeBucket:
    def __init__(self, store: dict[str, str] | None = None):
        self.store: dict[str, str] = store or {}

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self.store, name)

    def list_blobs(self, prefix: str = ""):
        return [
            _FakeBlob(self.store, name)
            for name in sorted(self.store)
            if name.startswith(prefix)
        ]


def test_snapshot_followers_writes_once_per_jst_day(monkeypatch):
    monkeypatch.setenv("X_ENGAGEMENT_TWITTER_AUTH_TOKEN", "auth_token=tok")
    monkeypatch.setattr(
        eng,
        "fetch_follower_counts",
        lambda handle, *, auth_token: {"followers_count": 5, "fetched": True},
    )
    bucket = _FakeBucket()
    stats = eng.snapshot_followers(bucket, now_utc=_NOW)
    assert stats["written"] == 1
    # _NOW (03:00 UTC) = JST 6/12
    assert "x_engagement/followers/2026-06-12.json" in bucket.store
    again = eng.snapshot_followers(bucket, now_utc=_NOW)
    assert again == {"written": 0, "skipped": 1, "errors": 0, "no_token": 0}


def test_snapshot_followers_skips_without_token(monkeypatch):
    monkeypatch.delenv("X_ENGAGEMENT_TWITTER_AUTH_TOKEN", raising=False)
    stats = eng.snapshot_followers(_FakeBucket(), now_utc=_NOW)
    assert stats["no_token"] == 1


def test_snapshot_followers_no_blob_when_all_fetches_fail(monkeypatch):
    monkeypatch.setenv("X_ENGAGEMENT_TWITTER_AUTH_TOKEN", "tok")
    monkeypatch.setattr(
        eng,
        "fetch_follower_counts",
        lambda handle, *, auth_token: {"fetched": False, "error": "boom"},
    )
    bucket = _FakeBucket()
    stats = eng.snapshot_followers(bucket, now_utc=_NOW)
    assert stats["written"] == 0
    assert bucket.store == {}  # 次回 collect で再試行できるよう日付枠を潰さない


def test_load_follower_trend_and_report_render():
    import json as _json

    bucket = _FakeBucket(
        {
            "x_engagement/followers/2026-06-08.json": _json.dumps(
                {
                    "date_jst": "2026-06-08",
                    "accounts": {"yoshilover6760": {"followers_count": 100, "fetched": True}},
                }
            ),
            "x_engagement/followers/2026-06-11.json": _json.dumps(
                {
                    "date_jst": "2026-06-11",
                    "accounts": {"yoshilover6760": {"followers_count": 112, "fetched": True}},
                }
            ),
            # 期間外は無視される
            "x_engagement/followers/2026-06-30.json": _json.dumps(
                {
                    "date_jst": "2026-06-30",
                    "accounts": {"yoshilover6760": {"followers_count": 999, "fetched": True}},
                }
            ),
        }
    )
    trend = eng._load_follower_trend(
        bucket, period_start_jst="2026-06-05", period_end_jst="2026-06-11"
    )
    assert trend["yoshilover6760"]["start"] == 100
    assert trend["yoshilover6760"]["end"] == 112
    assert trend["yoshilover6760"]["delta"] == 12
    report = eng.build_weekly_report(
        [],
        {},
        period_start_jst="2026-06-05",
        period_end_jst="2026-06-11",
        followers=trend,
    )
    text = eng.render_report_text(report)
    assert "@yoshilover6760: 112 (+12 / 2026-06-08〜2026-06-11)" in text
