"""効果学習 v0: @yoshilover6760 の投稿エンゲージ収集 + 週次レポート。

X API Free tier は read 不可 (全 GET 401) のため、無料経路 2 本で測る:

* 投稿 ID / 本文 / 投稿時刻 — 自前 RSSHub ``/twitter/user/yoshilover6760``
  (feed は直近 ~12 件しか遡れないため、collect を 1 日複数回回して
  GCS に upsert する。自動投稿 lane / 手動投稿の両方を同じ経路で拾える)
* like / リプ数 — X syndication endpoint
  ``cdn.syndication.twimg.com/tweet-result`` (認証不要、無料)。
  impression と retweet_count は Free 環境では取れないので
  favorite_count + conversation_count を代理指標とする。

LLM は使わない (¥0)。GCS layout:

* ``x_engagement/posts/<YYYYMMDD JST>/<tweet_id>.json`` — collect の upsert 先
* ``x_engagement/reports/<YYYY-MM-DD>.json`` — 週次レポートのスナップショット
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")

ACCOUNT_HANDLE = "yoshilover6760"
_RSSHUB_BASE_ENV = "X_ENGAGEMENT_RSSHUB_BASE"
_DEFAULT_RSSHUB_BASE = "https://rsshub-487178857517.asia-northeast1.run.app"
_SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token={token}"

_BUCKET_ENV = "X_ENGAGEMENT_BUCKET"
_DEFAULT_BUCKET = "baseballsite-yoshilover-state"
_POSTS_PREFIX = "x_engagement/posts"
_REPORTS_PREFIX = "x_engagement/reports"

_FEED_LIMIT = 30
_METRICS_FETCH_INTERVAL_SECONDS = 0.5
_HTTP_TIMEOUT_SECONDS = 20
_USER_AGENT = "Mozilla/5.0 (compatible; yoshilover-engagement/0.1)"

_TWEET_ID_RE = re.compile(r"/status(?:es)?/(\d+)")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class PostRecord:
    """collect が GCS に upsert する 1 投稿分の record."""

    tweet_id: str
    text: str
    created_at_utc: str  # ISO8601 UTC
    is_reply: bool = False
    is_quote_rt: bool = False
    style: str = "voice"
    time_bucket: str = "unknown"
    collected_at_utc: str = ""
    schema_version: str = "x_engagement_post_v0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PostMetrics:
    tweet_id: str
    favorite_count: int = 0
    reply_count: int = 0
    fetched: bool = False
    error: str | None = None


@dataclass
class WeeklyReport:
    period_start_jst: str
    period_end_jst: str
    total_posts: int
    total_favorites: int
    total_replies: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    by_style: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_time_bucket: dict[str, dict[str, Any]] = field(default_factory=dict)
    schema_version: str = "x_engagement_report_v0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# syndication token (JS: ((id/1e15)*Math.PI).toString(36).replace(/(0+|\.)/g,''))
# ---------------------------------------------------------------------------

def syndication_token(tweet_id: str) -> str:
    value = int(tweet_id) / 1e15 * math.pi
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    int_part = int(value)
    frac = value - int_part
    out = ""
    if int_part == 0:
        out = "0"
    while int_part > 0:
        out = digits[int_part % 36] + out
        int_part //= 36
    out += "."
    for _ in range(12):
        frac *= 36
        d = int(frac)
        out += digits[d]
        frac -= d
    return re.sub(r"(0+|\.)", "", out)


# ---------------------------------------------------------------------------
# feed parse / classification
# ---------------------------------------------------------------------------

def _strip_description(raw: str) -> str:
    text = _BR_RE.sub("\n", raw or "")
    text = _TAG_RE.sub("", text)
    return text.strip()


def classify_style(text: str) -> str:
    """投稿文の見た目から ①事実型 / 引用コメント型 / 記事共有 / voice をタグ付け。

    厳密でなくてよい (集計の切り口が目的)。判定順が優先順位。
    """
    if "yoshilover.com" in text:
        return "article_share"
    if text.startswith("【") or re.search(r"直近\d", text[:48]):
        return "data_fact"
    if "「" in text and "」" in text:
        return "quote_comment"
    return "voice"


def time_bucket_jst(dt_utc: datetime) -> str:
    hour = dt_utc.astimezone(JST).hour
    if 5 <= hour < 11:
        return "morning_05-11"
    if 11 <= hour < 17:
        return "midday_11-17"
    if 17 <= hour < 22:
        return "game_17-22"
    return "night_22-05"


def parse_feed(xml_text: str, *, now_utc: datetime) -> list[PostRecord]:
    """RSSHub の RSS XML から自アカ投稿 record を抽出する。RT は除外。"""
    records: list[PostRecord] = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        logger.warning("x_engagement_feed_parse_error err=%r", exc)
        return records
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        match = _TWEET_ID_RE.search(link)
        if not match:
            continue
        if f"/{ACCOUNT_HANDLE}/" not in link:
            # 他アカウントの status link = RT 等。自分の投稿だけ測る。
            continue
        title = (item.findtext("title") or "").strip()
        if title.startswith("RT "):
            continue
        text = _strip_description(item.findtext("description") or "") or title
        pub = (item.findtext("pubDate") or "").strip()
        try:
            created = parsedate_to_datetime(pub).astimezone(timezone.utc)
        except (TypeError, ValueError):
            created = now_utc
        records.append(
            PostRecord(
                tweet_id=match.group(1),
                text=text,
                created_at_utc=created.strftime("%Y-%m-%dT%H:%M:%SZ"),
                is_reply=text.startswith("@") or title.startswith("Re "),
                is_quote_rt="x.com/" in text or "twitter.com/" in text,
                style=classify_style(text),
                time_bucket=time_bucket_jst(created),
                collected_at_utc=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
    return records


# ---------------------------------------------------------------------------
# HTTP fetchers (差し替え可能にしてテストは注入)
# ---------------------------------------------------------------------------

def _http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_feed_xml() -> str:
    base = os.environ.get(_RSSHUB_BASE_ENV, _DEFAULT_RSSHUB_BASE).rstrip("/")
    return _http_get(f"{base}/twitter/user/{ACCOUNT_HANDLE}?limit={_FEED_LIMIT}")


def fetch_metrics(
    tweet_id: str, *, http_get: Callable[[str], str] = _http_get
) -> PostMetrics:
    url = _SYNDICATION_URL.format(tweet_id=tweet_id, token=syndication_token(tweet_id))
    try:
        payload = json.loads(http_get(url) or "{}")
    except Exception as exc:  # noqa: BLE001 - 集計は他 ID で続行する
        logger.warning("x_engagement_metrics_fetch_failed id=%s err=%r", tweet_id, exc)
        return PostMetrics(tweet_id=tweet_id, error=repr(exc))
    if not isinstance(payload, dict) or "favorite_count" not in payload:
        return PostMetrics(tweet_id=tweet_id, error="unexpected_payload")
    return PostMetrics(
        tweet_id=tweet_id,
        favorite_count=int(payload.get("favorite_count") or 0),
        reply_count=int(payload.get("conversation_count") or 0),
        fetched=True,
    )


# ---------------------------------------------------------------------------
# GCS storage
# ---------------------------------------------------------------------------

def _get_bucket():
    from google.cloud import storage  # type: ignore[import-not-found]

    bucket_name = os.environ.get(_BUCKET_ENV, _DEFAULT_BUCKET)
    return storage.Client().bucket(bucket_name)


def _post_blob_name(record: PostRecord) -> str:
    created = datetime.strptime(record.created_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    day = created.astimezone(JST).strftime("%Y%m%d")
    return f"{_POSTS_PREFIX}/{day}/{record.tweet_id}.json"


def collect(*, now_utc: datetime | None = None) -> dict[str, int]:
    """feed を 1 回取得し、新規投稿だけ GCS に upsert する。"""
    now = now_utc or datetime.now(timezone.utc)
    records = parse_feed(fetch_feed_xml(), now_utc=now)
    bucket = _get_bucket()
    written = 0
    skipped = 0
    for record in records:
        blob = bucket.blob(_post_blob_name(record))
        if blob.exists():
            skipped += 1
            continue
        blob.upload_from_string(
            json.dumps(record.to_dict(), ensure_ascii=False),
            content_type="application/json",
        )
        written += 1
    logger.info(
        "x_engagement_collect feed=%d written=%d skipped=%d",
        len(records),
        written,
        skipped,
    )
    return {"feed": len(records), "written": written, "skipped": skipped}


def _load_posts_for_days(bucket, days_jst: list[str]) -> list[PostRecord]:
    posts: list[PostRecord] = []
    for day in days_jst:
        for blob in bucket.list_blobs(prefix=f"{_POSTS_PREFIX}/{day}/"):
            try:
                payload = json.loads(blob.download_as_text())
                posts.append(
                    PostRecord(
                        tweet_id=str(payload["tweet_id"]),
                        text=str(payload.get("text") or ""),
                        created_at_utc=str(payload.get("created_at_utc") or ""),
                        is_reply=bool(payload.get("is_reply")),
                        is_quote_rt=bool(payload.get("is_quote_rt")),
                        style=str(payload.get("style") or "voice"),
                        time_bucket=str(payload.get("time_bucket") or "unknown"),
                        collected_at_utc=str(payload.get("collected_at_utc") or ""),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 壊れ blob は飛ばす
                logger.warning(
                    "x_engagement_post_blob_corrupt blob=%s err=%r", blob.name, exc
                )
    return posts


# ---------------------------------------------------------------------------
# weekly report
# ---------------------------------------------------------------------------

def _aggregate(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        slot = out.setdefault(row[key], {"posts": 0, "favorites": 0, "replies": 0})
        slot["posts"] += 1
        slot["favorites"] += row["favorite_count"]
        slot["replies"] += row["reply_count"]
    for slot in out.values():
        slot["avg_favorites"] = round(slot["favorites"] / slot["posts"], 2)
    return out


def build_weekly_report(
    posts: list[PostRecord],
    metrics: dict[str, PostMetrics],
    *,
    period_start_jst: str,
    period_end_jst: str,
) -> WeeklyReport:
    rows: list[dict[str, Any]] = []
    for post in posts:
        metric = metrics.get(post.tweet_id) or PostMetrics(tweet_id=post.tweet_id)
        rows.append(
            {
                "tweet_id": post.tweet_id,
                "text_head": post.text.replace("\n", " ")[:60],
                "created_at_utc": post.created_at_utc,
                "style": post.style,
                "time_bucket": post.time_bucket,
                "is_reply": post.is_reply,
                "favorite_count": metric.favorite_count,
                "reply_count": metric.reply_count,
                "metrics_fetched": metric.fetched,
            }
        )
    rows.sort(key=lambda r: (r["favorite_count"], r["reply_count"]), reverse=True)
    return WeeklyReport(
        period_start_jst=period_start_jst,
        period_end_jst=period_end_jst,
        total_posts=len(rows),
        total_favorites=sum(r["favorite_count"] for r in rows),
        total_replies=sum(r["reply_count"] for r in rows),
        rows=rows,
        by_style=_aggregate(rows, "style") if rows else {},
        by_time_bucket=_aggregate(rows, "time_bucket") if rows else {},
    )


_STYLE_LABELS = {
    "data_fact": "①事実・データ型",
    "quote_comment": "引用コメント型",
    "article_share": "記事共有",
    "voice": "②voice型",
}

_BUCKET_LABELS = {
    "morning_05-11": "朝 05-11時",
    "midday_11-17": "昼 11-17時",
    "game_17-22": "試合 17-22時",
    "night_22-05": "夜 22-05時",
    "unknown": "不明",
}


def render_report_text(report: WeeklyReport) -> str:
    lines = [
        f"@{ACCOUNT_HANDLE} 週次エンゲージレポート",
        f"対象期間 (JST): {report.period_start_jst} 〜 {report.period_end_jst}",
        "指標: ♥=like / 💬=リプ (X Free 環境のため impression は取得不可、likeを代理指標とする)",
        "",
        f"投稿数 {report.total_posts} / ♥合計 {report.total_favorites} / 💬合計 {report.total_replies}",
        "",
        "■ 型別 (平均♥が高い型に枠を寄せる)",
    ]
    for key, slot in sorted(
        report.by_style.items(), key=lambda kv: -kv[1]["avg_favorites"]
    ):
        lines.append(
            f"  {_STYLE_LABELS.get(key, key)}: {slot['posts']}投稿 / 平均♥{slot['avg_favorites']} / ♥計{slot['favorites']}"
        )
    lines.append("")
    lines.append("■ 時間帯別")
    for key, slot in sorted(
        report.by_time_bucket.items(), key=lambda kv: -kv[1]["avg_favorites"]
    ):
        lines.append(
            f"  {_BUCKET_LABELS.get(key, key)}: {slot['posts']}投稿 / 平均♥{slot['avg_favorites']}"
        )
    lines.append("")
    lines.append("■ TOP 5")
    for row in report.rows[:5]:
        lines.append(
            f"  ♥{row['favorite_count']} 💬{row['reply_count']} [{_STYLE_LABELS.get(row['style'], row['style'])}] {row['text_head']}"
        )
    lines.append("")
    lines.append("■ WORST 5")
    for row in report.rows[-5:]:
        lines.append(
            f"  ♥{row['favorite_count']} 💬{row['reply_count']} [{_STYLE_LABELS.get(row['style'], row['style'])}] {row['text_head']}"
        )
    if any(not r["metrics_fetched"] for r in report.rows):
        miss = sum(1 for r in report.rows if not r["metrics_fetched"])
        lines.append("")
        lines.append(f"※ メトリクス取得失敗 {miss} 件 (♥0 として集計、silent skip 防止のため明記)")
    return "\n".join(lines)


def run_weekly_report(
    *,
    now_utc: datetime | None = None,
    days: int = 7,
    sleep_seconds: float = _METRICS_FETCH_INTERVAL_SECONDS,
) -> tuple[WeeklyReport, str]:
    """直近 days 日 (JST、当日は含まない) の投稿を集計しレポートを返す。"""
    now = now_utc or datetime.now(timezone.utc)
    today_jst = now.astimezone(JST).date()
    day_list = [
        (today_jst - timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(1, days + 1)
    ]
    bucket = _get_bucket()
    posts = _load_posts_for_days(bucket, day_list)
    metrics: dict[str, PostMetrics] = {}
    for post in posts:
        metrics[post.tweet_id] = fetch_metrics(post.tweet_id)
        time.sleep(sleep_seconds)
    report = build_weekly_report(
        posts,
        metrics,
        period_start_jst=(today_jst - timedelta(days=days)).isoformat(),
        period_end_jst=(today_jst - timedelta(days=1)).isoformat(),
    )
    report_blob = bucket.blob(
        f"{_REPORTS_PREFIX}/{today_jst.isoformat()}.json"
    )
    report_blob.upload_from_string(
        json.dumps(report.to_dict(), ensure_ascii=False),
        content_type="application/json",
    )
    return report, render_report_text(report)
