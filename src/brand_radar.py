"""Yoshilover branding radar for source-backed X post planning.

This lane is intentionally mail-only:

* reads public article/RSS/tag sources
* optionally enriches top topics with xAI Responses API ``x_search``
* composes suggested X copy and evidence for manual posting

It does not call the X posting API, WordPress, or production databases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import html
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import quote as url_quote
from zoneinfo import ZoneInfo


LOG = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")
X_INTENT_URL_BASE = "https://twitter.com/intent/tweet"
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-4-1-fast-non-reasoning"
DEFAULT_MAX_TOPICS = 3
DEFAULT_X_SEARCH_CAP = 3
DEFAULT_SOURCE_LIMIT = 32
DEFAULT_ENTRY_LIMIT = 5
DEFAULT_TIMEOUT_SECONDS = 30

GIANTS_KEYWORDS = ("巨人", "読売ジャイアンツ", "ジャイアンツ")
MAGAZINE_SOURCE_HINTS = (
    "FRIDAY",
    "FLASH",
    "週刊",
    "文春",
    "女性",
    "ポストセブン",
    "新潮",
    "現代",
    "アサ芸",
)
LOW_VALUE_TOPIC_PATTERNS = (
    "プレゼント",
    "キャンペーン",
    "フォロー",
    "リポスト",
    "抽選",
    "チケット発売",
)
URL_RE = re.compile(r"https?://[^\s<>()\"']+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
TITLE_CLEAN_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class FreshArticleTopic:
    title: str
    url: str
    source_name: str
    source_type: str
    summary: str = ""
    published_at: datetime | None = None
    observed_at: datetime | None = None
    topic_type: str = "fresh_news"
    freshness_hours: float | None = None
    source_priority: int = 50
    base_score: float = 0.0
    skip_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class XSearchSignal:
    query: str
    from_date: str
    to_date: str
    status: str
    summary: str = ""
    evidence_urls: tuple[str, ...] = ()
    error_type: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    attempted: bool = False


@dataclass(frozen=True)
class BrandPostPlan:
    topic: FreshArticleTopic
    signal: XSearchSignal
    post_text: str
    why_now: str
    brand_judgement: str
    risk_label: str
    confidence_label: str
    score: float
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BrandRadarMail:
    subject: str
    text_body: str
    html_body: str
    candidate_count: int


@dataclass
class BrandRadarStats:
    x_search_calls_used: int = 0
    x_search_call_cap: int = DEFAULT_X_SEARCH_CAP
    provider_error_count: int = 0
    candidates_sent: int = 0
    skipped_by_reason: dict[str, int] = field(default_factory=dict)

    def add_skip(self, reason: str) -> None:
        key = reason or "unknown"
        self.skipped_by_reason[key] = self.skipped_by_reason.get(key, 0) + 1


@dataclass(frozen=True)
class BrandRadarRunResult:
    plans: list[BrandPostPlan]
    stats: BrandRadarStats


class XSearchClient(Protocol):
    def search(self, topic: FreshArticleTopic, *, now: datetime) -> XSearchSignal:
        ...


def now_jst() -> datetime:
    return datetime.now(JST)


def encode_x_intent_url(text: str) -> str:
    return f"{X_INTENT_URL_BASE}?text={url_quote(text or '', safe='')}"


def _one_line(value: str) -> str:
    return TITLE_CLEAN_RE.sub(" ", str(value or "")).strip()


def _shorten(value: str, limit: int) -> str:
    text = _one_line(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _normal_title_key(title: str) -> str:
    text = _one_line(title).casefold()
    text = re.sub(r"[「」『』【】\[\]（）()、。,.!！?？\s]+", "", text)
    return text[:80]


def _title_has_giants_player(title: str) -> bool:
    try:
        from src import x_post_mail_lane
    except Exception:  # noqa: BLE001
        return False
    try:
        return bool(x_post_mail_lane.detect_giants_player_name(title))
    except Exception:  # noqa: BLE001
        return False


def _has_giants_topic(title: str, summary: str, source_name: str) -> bool:
    title_source = f"{title} {source_name}"
    if any(keyword in title_source for keyword in GIANTS_KEYWORDS):
        return True
    # Summary-only Giants hits are too weak for general RSS feeds; they
    # allowed non-Giants-looking titles into the branding radar. A title
    # with a known Giants player is still accepted even without "巨人".
    if _title_has_giants_player(title):
        return True
    return False


def _low_value_reason(title: str, summary: str) -> str:
    haystack = f"{title} {summary}"
    for pattern in LOW_VALUE_TOPIC_PATTERNS:
        if pattern in haystack:
            return "low_value_campaign_or_promo"
    return ""


def _is_magazine_source(source_name: str) -> bool:
    return any(hint in (source_name or "") for hint in MAGAZINE_SOURCE_HINTS)


def source_priority(source: dict[str, Any]) -> int:
    source_type = str(source.get("type") or "").strip()
    name = str(source.get("name") or "").strip()
    if source_type == "social_news":
        if "公式X" in name or "ジャイアンツX" in name:
            return 80
        return 65
    if _is_magazine_source(name):
        return 25
    if source_type == "tag_scrape":
        return 15
    if source_type == "news":
        return 10
    return 50


def _topic_type(title: str, summary: str, source_name: str) -> str:
    haystack = f"{title} {summary}"
    if _is_magazine_source(source_name):
        return "magazine_angle"
    if any(word in haystack for word in ("スタメン", "オーダー", "打順")):
        return "lineup"
    if any(word in haystack for word in ("先発", "登板", "ローテ")):
        return "starter"
    if any(word in haystack for word in ("阿部監督", "監督", "コーチ", "采配")):
        return "manager"
    if any(word in haystack for word in ("2軍", "二軍", "ファーム", "育成")):
        return "farm"
    if any(word in haystack for word in ("けが", "怪我", "故障", "復帰", "リハビリ")):
        return "injury_recovery"
    if any(word in haystack for word in ("登録", "抹消", "昇格", "降格", "支配下")):
        return "roster_move"
    if any(word in haystack for word in ("批判", "物議", "炎上", "波紋")):
        return "controversy"
    return "fresh_news"


def _published_datetime_from_entry(entry: dict[str, Any], *, now: datetime) -> datetime | None:
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if struct:
        try:
            return datetime(*struct[:6], tzinfo=timezone.utc).astimezone(JST)
        except Exception:  # noqa: BLE001
            return None
    raw = str(entry.get("published") or entry.get("updated") or "").strip()
    if not raw:
        return None
    # Keep this parser intentionally narrow; unknown strings become observed-only.
    try:
        parsed = time.strptime(raw[:25], "%a, %d %b %Y %H:%M:%S")
        return datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(JST)
    except Exception:  # noqa: BLE001
        return None


def _freshness_hours(published_at: datetime | None, *, now: datetime) -> float | None:
    if published_at is None:
        return None
    return max(0.0, (now.astimezone(JST) - published_at.astimezone(JST)).total_seconds() / 3600.0)


def _base_score(
    *,
    freshness_hours: float | None,
    source_pri: int,
    topic_type: str,
    magazine_context: bool,
) -> float:
    score = 100.0 - float(source_pri)
    if freshness_hours is None:
        score += 6.0
    elif freshness_hours <= 6:
        score += 45.0
    elif freshness_hours <= 24:
        score += 28.0
    elif magazine_context:
        score += 12.0
    else:
        score -= 30.0
    if topic_type in {"lineup", "starter", "manager", "roster_move", "controversy"}:
        score += 10.0
    if topic_type == "magazine_angle":
        score += 7.0
    return score


def topic_from_entry(
    entry: dict[str, Any],
    source: dict[str, Any],
    *,
    now: datetime,
) -> tuple[FreshArticleTopic | None, str]:
    title = _one_line(str(entry.get("title") or ""))
    url = _one_line(str(entry.get("link") or entry.get("id") or ""))
    summary = _one_line(
        str(entry.get("summary") or entry.get("description") or entry.get("subtitle") or "")
    )
    source_name = _one_line(str(source.get("name") or ""))
    source_type = _one_line(str(source.get("type") or ""))
    if not title:
        return None, "missing_title"
    if not url.startswith(("http://", "https://")):
        return None, "missing_source_url"
    if not _has_giants_topic(title, summary, source_name):
        return None, "non_giants_topic"
    low_value = _low_value_reason(title, summary)
    if low_value:
        return None, low_value
    published_at = _published_datetime_from_entry(entry, now=now)
    freshness = _freshness_hours(published_at, now=now)
    magazine_context = _is_magazine_source(source_name)
    if freshness is not None and freshness > 24 and not magazine_context:
        return None, "stale_article"
    topic_type = _topic_type(title, summary, source_name)
    source_pri = source_priority(source)
    notes: list[str] = []
    if freshness is not None and freshness > 24 and magazine_context:
        notes.append("magazine_context_older_than_24h")
    score = _base_score(
        freshness_hours=freshness,
        source_pri=source_pri,
        topic_type=topic_type,
        magazine_context=magazine_context,
    )
    return (
        FreshArticleTopic(
            title=title,
            url=url,
            source_name=source_name,
            source_type=source_type,
            summary=summary,
            published_at=published_at,
            observed_at=now,
            topic_type=topic_type,
            freshness_hours=freshness,
            source_priority=source_pri,
            base_score=score,
            skip_notes=tuple(notes),
        ),
        "",
    )


def load_brand_sources(path: Path) -> list[dict[str, Any]]:
    try:
        sources = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("brand_radar_source_load_failed path=%s error=%r", path, exc)
        return []
    out: list[dict[str, Any]] = []
    for source in sources:
        source_type = str(source.get("type") or "")
        roles = source.get("role") or []
        if isinstance(roles, str):
            roles = [roles]
        if source_type not in {"news", "tag_scrape", "social_news"}:
            continue
        if roles and "article_source" not in roles:
            continue
        if source_type == "tag_scrape" and not str(source.get("scraper") or "").strip():
            continue
        url = str(source.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        out.append(dict(source))
    return sorted(out, key=lambda src: (source_priority(src), str(src.get("name") or "")))


def fetch_source_entries(source: dict[str, Any], *, timeout_seconds: int, entry_limit: int) -> list[dict[str, Any]]:
    source_type = str(source.get("type") or "")
    if source_type == "tag_scrape":
        from src import tag_page_scraper

        return tag_page_scraper.fetch_tag_page_entries(
            scraper=str(source.get("scraper") or ""),
            url=str(source.get("url") or ""),
            max_age_days=int(source.get("max_age_days") or 7),
            article_limit=max(1, min(int(source.get("article_limit") or entry_limit), entry_limit)),
            logger=LOG,
        )
    try:
        import feedparser
    except Exception as exc:  # noqa: BLE001
        LOG.warning("brand_radar_feedparser_import_failed error=%r", exc)
        return []
    req = urlrequest.Request(
        str(source.get("url") or ""),
        headers={
            "User-Agent": "yoshilover-brand-radar/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            data = response.read()
    except (OSError, urlerror.URLError) as exc:
        LOG.warning(
            "brand_radar_source_fetch_failed source=%s url=%s error=%r",
            source.get("name"),
            source.get("url"),
            exc,
        )
        return []
    parsed = feedparser.parse(data)
    return list(parsed.entries or [])[:entry_limit]


def collect_fresh_article_topics(
    *,
    sources: Sequence[dict[str, Any]],
    now: datetime | None = None,
    source_limit: int = DEFAULT_SOURCE_LIMIT,
    entry_limit: int = DEFAULT_ENTRY_LIMIT,
    timeout_seconds: int = 4,
    fetch_entries: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
    stats: BrandRadarStats | None = None,
) -> list[FreshArticleTopic]:
    active_now = now or now_jst()
    out: list[FreshArticleTopic] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    fetcher = fetch_entries or (
        lambda source: fetch_source_entries(
            source,
            timeout_seconds=timeout_seconds,
            entry_limit=entry_limit,
        )
    )
    for source in list(sources)[: max(0, source_limit)]:
        try:
            entries = fetcher(source)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("brand_radar_source_fetch_failed source=%s error=%r", source.get("name"), exc)
            if stats:
                stats.add_skip("source_fetch_failed")
            continue
        if not entries and stats:
            stats.add_skip("no_fresh_article")
        for entry in entries[:entry_limit]:
            topic, reason = topic_from_entry(entry, source, now=active_now)
            if topic is None:
                if stats:
                    stats.add_skip(reason)
                continue
            title_key = _normal_title_key(topic.title)
            if topic.url in seen_urls or title_key in seen_titles:
                if stats:
                    stats.add_skip("duplicate_topic")
                continue
            seen_urls.add(topic.url)
            seen_titles.add(title_key)
            out.append(topic)
    return sort_topics_for_branding(out)


def sort_topics_for_branding(topics: Iterable[FreshArticleTopic]) -> list[FreshArticleTopic]:
    return sorted(
        topics,
        key=lambda t: (
            -float(t.base_score),
            t.source_priority,
            t.freshness_hours if t.freshness_hours is not None else 999.0,
            t.title,
        ),
    )


def build_x_search_query(topic: FreshArticleTopic) -> str:
    title = re.sub(r"【[^】]+】", "", topic.title)
    title = _shorten(title, 36)
    if "巨人" in title or "ジャイアンツ" in title:
        return title
    return f"巨人 {title}".strip()


def _parse_response_text(data: dict[str, Any]) -> str:
    for item in data.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                return str(content.get("text") or "").strip()
    return ""


def _urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text or ""):
        urls.append(match.group(2).rstrip(".,、。)）]】"))
    for match in URL_RE.finditer(text or ""):
        urls.append(match.group(0).rstrip(".,、。)）]】"))
    return urls


def _urls_from_obj(obj: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(obj, str):
        urls.extend(_urls_from_text(obj))
    elif isinstance(obj, dict):
        for value in obj.values():
            urls.extend(_urls_from_obj(value))
    elif isinstance(obj, list):
        for value in obj:
            urls.extend(_urls_from_obj(value))
    return urls


def _dedupe_urls(urls: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        clean = str(url or "").strip()
        if not clean.startswith(("http://", "https://")) or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return tuple(out)


def _http_error_type(code: int) -> str:
    if code in {401, 403}:
        return "x_search_auth_required"
    if code == 429:
        return "rate_limited"
    return f"http_{code}"


class XAIResponsesXSearchClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.environ.get("GROK_API_KEY", "")).strip()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.opener = opener or urlrequest.urlopen

    def search(self, topic: FreshArticleTopic, *, now: datetime) -> XSearchSignal:
        active_now = now.astimezone(JST)
        from_date = (active_now - timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = active_now.strftime("%Y-%m-%d")
        query = build_x_search_query(topic)
        if not self.api_key:
            return XSearchSignal(
                query=query,
                from_date=from_date,
                to_date=to_date,
                status="x_search_error",
                error_type="missing_api_key",
                attempted=False,
            )

        prompt = (
            "読売ジャイアンツ専門ブログ「ヨシラバー」のX投稿企画用に、"
            "以下のニュースについてX上のファン温度感を調べてください。\n\n"
            f"ニュース: {topic.title}\n"
            f"ソース: {topic.source_name}\n"
            f"URL: {topic.url}\n\n"
            "要件:\n"
            "- 実際にX検索で確認できた反応だけを要約する\n"
            "- 推測でファン反応を作らない\n"
            "- 見つかった証拠URLがあれば必ず含める\n"
            "- 見つからない場合は X_SIGNAL_EMPTY と書く\n"
            "- 80文字以内で温度感を1行要約する\n"
        )
        payload = json.dumps(
            {
                "model": self.model,
                "max_turns": 1,
                "max_output_tokens": 500,
                "input": [{"role": "user", "content": prompt}],
                "tools": [{"type": "x_search", "from_date": from_date, "to_date": to_date}],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            req = urlrequest.Request(
                XAI_RESPONSES_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            with self.opener(req, timeout=self.timeout_seconds) as response:
                data = json.load(response)
        except urlerror.HTTPError as exc:
            return XSearchSignal(
                query=query,
                from_date=from_date,
                to_date=to_date,
                status="x_search_error",
                error_type=_http_error_type(int(getattr(exc, "code", 0) or 0)),
                attempted=True,
            )
        except TimeoutError:
            return XSearchSignal(
                query=query,
                from_date=from_date,
                to_date=to_date,
                status="x_search_error",
                error_type="timeout",
                attempted=True,
            )
        except Exception:  # noqa: BLE001
            return XSearchSignal(
                query=query,
                from_date=from_date,
                to_date=to_date,
                status="x_search_error",
                error_type="request_error",
                attempted=True,
            )

        text = _parse_response_text(data)
        urls = _dedupe_urls([*_urls_from_text(text), *_urls_from_obj(data)])
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        if not text or "X_SIGNAL_EMPTY" in text:
            return XSearchSignal(
                query=query,
                from_date=from_date,
                to_date=to_date,
                status="x_search_empty",
                summary="",
                evidence_urls=urls,
                usage=usage,
                attempted=True,
            )
        status = "x_search_cited" if urls else "x_search_uncited"
        return XSearchSignal(
            query=query,
            from_date=from_date,
            to_date=to_date,
            status=status,
            summary=_shorten(re.sub(r"X_SIGNAL_EMPTY", "", text), 120),
            evidence_urls=urls[:5],
            usage=usage,
            attempted=True,
        )


def _empty_signal(topic: FreshArticleTopic, *, now: datetime, status: str, error_type: str = "") -> XSearchSignal:
    active_now = now.astimezone(JST)
    return XSearchSignal(
        query=build_x_search_query(topic),
        from_date=(active_now - timedelta(days=1)).strftime("%Y-%m-%d"),
        to_date=active_now.strftime("%Y-%m-%d"),
        status=status,
        error_type=error_type,
        attempted=False,
    )


def _signal_score(signal: XSearchSignal) -> float:
    if signal.status == "x_search_cited":
        return 35.0
    if signal.status == "x_search_uncited":
        return 18.0
    if signal.status == "x_search_empty":
        return 0.0
    return -8.0


def _risk_label(topic: FreshArticleTopic, signal: XSearchSignal) -> str:
    if signal.status == "x_search_cited" and (
        topic.freshness_hours is None or topic.freshness_hours <= 24
    ):
        return "low"
    if signal.status in {"x_search_empty", "x_search_error"} or "magazine_context_older_than_24h" in topic.skip_notes:
        return "medium"
    return "medium"


def _confidence_label(signal: XSearchSignal) -> str:
    if signal.status == "x_search_cited":
        return "source+x_search_url"
    if signal.status == "x_search_uncited":
        return "source+x_search_uncited"
    if signal.status == "x_search_empty":
        return "source_only_x_empty"
    return f"source_only_x_error:{signal.error_type or 'unknown'}"


def _topic_type_jp(topic_type: str) -> str:
    labels = {
        "lineup": "スタメン/起用",
        "starter": "先発/登板",
        "manager": "監督・采配",
        "farm": "ファーム",
        "injury_recovery": "故障/復帰",
        "roster_move": "登録/昇格",
        "controversy": "論点/炎上",
        "magazine_angle": "週刊誌・読み物",
        "fresh_news": "新着ニュース",
    }
    return labels.get(topic_type, topic_type)


def compose_post_text(topic: FreshArticleTopic, signal: XSearchSignal) -> str:
    title = _shorten(topic.title, 62)
    topic_label = _topic_type_jp(topic.topic_type)
    if signal.status in {"x_search_cited", "x_search_uncited"} and signal.summary:
        hook = _shorten(signal.summary, 42)
        text = (
            f"巨人ファン的に今日見るべき論点。\n"
            f"{title}\n"
            f"Xでは「{hook}」が気になる流れ。\n"
            f"ヨシラバーでは{topic_label}として追います。\n"
            "#巨人 #ジャイアンツ"
        )
    else:
        text = (
            f"巨人ファン的に今日見るべき論点。\n"
            f"{title}\n"
            f"ヨシラバーでは{topic_label}として、事実ベースで整理します。\n"
            "#巨人 #ジャイアンツ"
        )
    if len(text) <= 140:
        return text
    return (
        f"巨人ファン的に今日見るべき論点。\n"
        f"{_shorten(topic.title, 54)}\n"
        f"ヨシラバーでは{topic_label}として追います。\n"
        "#巨人 #ジャイアンツ"
    )


def _format_source_time(topic: FreshArticleTopic) -> str:
    if topic.published_at:
        return topic.published_at.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    return "unknown"


def _why_now(topic: FreshArticleTopic, signal: XSearchSignal) -> str:
    if topic.freshness_hours is None:
        fresh = "source time unknown"
    elif topic.freshness_hours <= 6:
        fresh = f"fresh {topic.freshness_hours:.1f}h"
    elif topic.freshness_hours <= 24:
        fresh = f"within 24h {topic.freshness_hours:.1f}h"
    else:
        fresh = f"magazine context {topic.freshness_hours:.1f}h"
    if signal.status == "x_search_cited":
        x_part = f"X evidence URLs={len(signal.evidence_urls)}"
    elif signal.status == "x_search_uncited":
        x_part = "X summary returned without URL"
    elif signal.status == "x_search_empty":
        x_part = "X signal empty"
    else:
        x_part = f"X unavailable: {signal.error_type or signal.status}"
    return f"{fresh}; {x_part}; source={topic.source_name}"


def _brand_judgement(topic: FreshArticleTopic, signal: XSearchSignal) -> str:
    parts = [
        "巨人文脈あり",
        _topic_type_jp(topic.topic_type),
        "記事URLあり",
    ]
    if signal.status == "x_search_cited":
        parts.append("X Search URL証拠あり")
    elif signal.status == "x_search_uncited":
        parts.append("X Search要約のみ")
    else:
        parts.append("X Search証拠なし")
    return " / ".join(parts)


def build_brand_post_plans(
    topics: Sequence[FreshArticleTopic],
    *,
    x_search_client: XSearchClient,
    now: datetime | None = None,
    max_plans: int = DEFAULT_MAX_TOPICS,
    x_search_call_cap: int = DEFAULT_X_SEARCH_CAP,
    stats: BrandRadarStats | None = None,
) -> BrandRadarRunResult:
    active_now = now or now_jst()
    active_stats = stats or BrandRadarStats(x_search_call_cap=x_search_call_cap)
    active_stats.x_search_call_cap = x_search_call_cap
    plans: list[BrandPostPlan] = []
    provider_disabled = False
    for topic in sort_topics_for_branding(topics):
        if len(plans) >= max_plans:
            break
        if provider_disabled:
            signal = _empty_signal(topic, now=active_now, status="x_search_error", error_type="provider_disabled")
        elif active_stats.x_search_calls_used >= x_search_call_cap:
            signal = _empty_signal(topic, now=active_now, status="x_search_error", error_type="x_search_cap_exceeded")
            active_stats.add_skip("x_search_cap_exceeded")
        else:
            signal = x_search_client.search(topic, now=active_now)
            if signal.attempted:
                active_stats.x_search_calls_used += 1
            if signal.status == "x_search_error":
                active_stats.provider_error_count += 1
                if active_stats.provider_error_count >= 2:
                    provider_disabled = True
        score = topic.base_score + _signal_score(signal)
        post_text = compose_post_text(topic, signal)
        notes = tuple([*topic.skip_notes, signal.error_type] if signal.error_type else topic.skip_notes)
        plans.append(
            BrandPostPlan(
                topic=topic,
                signal=signal,
                post_text=post_text,
                why_now=_why_now(topic, signal),
                brand_judgement=_brand_judgement(topic, signal),
                risk_label=_risk_label(topic, signal),
                confidence_label=_confidence_label(signal),
                score=score,
                notes=notes,
            )
        )
    active_stats.candidates_sent = len(plans)
    return BrandRadarRunResult(plans=plans, stats=active_stats)


def build_brand_radar(
    *,
    sources: Sequence[dict[str, Any]],
    x_search_client: XSearchClient,
    now: datetime | None = None,
    max_plans: int = DEFAULT_MAX_TOPICS,
    x_search_call_cap: int = DEFAULT_X_SEARCH_CAP,
    source_limit: int = DEFAULT_SOURCE_LIMIT,
    entry_limit: int = DEFAULT_ENTRY_LIMIT,
    timeout_seconds: int = 4,
    fetch_entries: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
) -> BrandRadarRunResult:
    active_now = now or now_jst()
    stats = BrandRadarStats(x_search_call_cap=x_search_call_cap)
    topics = collect_fresh_article_topics(
        sources=sources,
        now=active_now,
        source_limit=source_limit,
        entry_limit=entry_limit,
        timeout_seconds=timeout_seconds,
        fetch_entries=fetch_entries,
        stats=stats,
    )
    return build_brand_post_plans(
        topics,
        x_search_client=x_search_client,
        now=active_now,
        max_plans=max_plans,
        x_search_call_cap=x_search_call_cap,
        stats=stats,
    )


def build_subject(now: datetime, n_candidates: int) -> str:
    return f"ヨシラバー投稿企画案｜巨人ニュース鮮度レーダー {now.astimezone(JST).strftime('%H:%M')} JST ({n_candidates}件)"


def _format_signal_text(signal: XSearchSignal) -> list[str]:
    lines = [
        f"- X Search status: {signal.status}",
        f"- X Search query: {signal.query}",
        f"- X Search date range: {signal.from_date}..{signal.to_date}",
    ]
    if signal.summary:
        lines.append(f"- X Search summary: {signal.summary}")
    if signal.evidence_urls:
        lines.append("- X evidence URLs:")
        lines.extend(f"  - {url}" for url in signal.evidence_urls)
    else:
        reason = signal.error_type or signal.status
        lines.append(f"- X signal unavailable: {reason}")
    if signal.usage:
        lines.append(f"- provider usage: {json.dumps(signal.usage, ensure_ascii=False, sort_keys=True)}")
    return lines


def compose_brand_radar_mail(
    plans: Sequence[BrandPostPlan],
    *,
    now: datetime | None = None,
    stats: BrandRadarStats | None = None,
) -> BrandRadarMail:
    active_now = now or now_jst()
    active_stats = stats or BrandRadarStats(candidates_sent=len(plans))
    subject = build_subject(active_now, len(plans))
    text_lines = [
        f"ヨシラバー投稿企画案 — 巨人ニュース鮮度レーダー / {active_now.astimezone(JST).strftime('%Y-%m-%d %H:%M')} JST",
        "",
        "公開通知ではありません。X自動投稿もWP更新もしません。",
        "目的: ヨシラバーのポストを見たいと思わせるため、巨人ニュース + X温度感 + 証拠で候補を絞る。",
        "",
        "run evidence:",
        f"- x_search_calls_used: {active_stats.x_search_calls_used}",
        f"- x_search_call_cap: {active_stats.x_search_call_cap}",
        f"- provider_error_count: {active_stats.provider_error_count}",
        f"- candidates_sent: {len(plans)}",
        f"- candidates_skipped_by_reason: {json.dumps(active_stats.skipped_by_reason, ensure_ascii=False, sort_keys=True)}",
        "",
    ]
    html_cards: list[str] = []
    for idx, plan in enumerate(plans, start=1):
        topic = plan.topic
        signal = plan.signal
        text_lines.extend(
            [
                "━" * 40,
                f"【{idx}】投稿案",
                plan.post_text,
                "",
                "狙い:",
                plan.why_now,
                "",
                "証拠:",
                f"- source: {topic.source_name} ({topic.source_type})",
                f"- source_url: {topic.url}",
                f"- source_time: {_format_source_time(topic)}",
                *_format_signal_text(signal),
                "",
                "ブランド判定:",
                f"- {plan.brand_judgement}",
                f"- topic_type: {topic.topic_type}",
                f"- confidence: {plan.confidence_label}",
                f"- risk: {plan.risk_label}",
                f"- score: {plan.score:.1f}",
                "",
                "注意:",
                "- DBが古い場合でも、この候補は記事ソースとX Search証拠だけで扱う。",
                "- X signal unavailable の場合は、ファン反応を作らない。",
                *[f"- note: {note}" for note in plan.notes],
                "",
                "X投稿URL:",
                encode_x_intent_url(plan.post_text),
                "",
            ]
        )
        evidence_html = "".join(
            f"<li>{html.escape(line)}</li>" for line in _format_signal_text(signal)
        )
        html_cards.append(
            "<section style=\"border-left:4px solid #f57f17;padding:12px 14px;margin:16px 0;"
            "background:#fff8e1;border-radius:4px;\">"
            f"<h3 style=\"margin:0 0 8px;font-size:16px;\">【{idx}】投稿案</h3>"
            "<pre style=\"white-space:pre-wrap;word-break:keep-all;font-family:-apple-system,"
            "BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',monospace;font-size:13px;"
            f"line-height:1.5;background:#fff;border:1px solid #ddd;padding:10px;\">{html.escape(plan.post_text)}</pre>"
            f"<p><strong>狙い:</strong> {html.escape(plan.why_now)}</p>"
            "<p><strong>証拠:</strong></p>"
            "<ul>"
            f"<li>source: {html.escape(topic.source_name)} ({html.escape(topic.source_type)})</li>"
            f"<li>source_url: <a href=\"{html.escape(topic.url)}\">{html.escape(topic.url)}</a></li>"
            f"<li>source_time: {html.escape(_format_source_time(topic))}</li>"
            f"{evidence_html}"
            "</ul>"
            f"<p><strong>ブランド判定:</strong> {html.escape(plan.brand_judgement)}"
            f" / confidence={html.escape(plan.confidence_label)}"
            f" / risk={html.escape(plan.risk_label)}"
            f" / score={plan.score:.1f}</p>"
            f"<p><a href=\"{html.escape(encode_x_intent_url(plan.post_text))}\" "
            "style=\"display:inline-block;background:#000;color:#fff;text-decoration:none;"
            "padding:8px 14px;border-radius:6px;\">Xで手動投稿</a></p>"
            "</section>"
        )
    html_body = (
        "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(subject)}</title></head>"
        "<body style=\"font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',sans-serif;"
        "max-width:720px;margin:0 auto;padding:18px;color:#222;\">"
        f"<h2>{html.escape(subject)}</h2>"
        "<p>公開通知ではありません。X自動投稿もWP更新もしません。</p>"
        "<p>目的: ヨシラバーのポストを見たいと思わせるため、巨人ニュース + X温度感 + 証拠で候補を絞る。</p>"
        "<ul>"
        f"<li>x_search_calls_used: {active_stats.x_search_calls_used}</li>"
        f"<li>x_search_call_cap: {active_stats.x_search_call_cap}</li>"
        f"<li>provider_error_count: {active_stats.provider_error_count}</li>"
        f"<li>candidates_sent: {len(plans)}</li>"
        f"<li>candidates_skipped_by_reason: {html.escape(json.dumps(active_stats.skipped_by_reason, ensure_ascii=False, sort_keys=True))}</li>"
        "</ul>"
        + "".join(html_cards)
        + "</body></html>"
    )
    return BrandRadarMail(
        subject=subject,
        text_body="\n".join(text_lines),
        html_body=html_body,
        candidate_count=len(plans),
    )
