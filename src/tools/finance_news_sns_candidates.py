"""Finance news SNS candidate builder.

Yoshilover-style lane:
  fetch public finance sources -> score candidate topics -> send Gmail
  candidate mail with X intent links. This module never posts to SNS and never
  mutates WordPress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import escape
from html.parser import HTMLParser
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, urljoin

import feedparser
import requests


LOG = logging.getLogger(__name__)
JST_TZ_NAME = "Asia/Tokyo"
DEFAULT_USER_AGENT = "yoshilover-finance-news-sns/0.1 (contact: yoshilover)"
DEFAULT_TIMEOUT_SECONDS = 6
DEFAULT_MAX_ITEMS_PER_SOURCE = 20
DEFAULT_MAX_CANDIDATES = 8
DEFAULT_MINIMUM_SCORE = 75
DEFAULT_DEDUPE_WINDOW_HOURS = 24
DEFAULT_SOURCE_FILE = Path(__file__).resolve().parents[2] / "config" / "finance_jp_us_stock_fund_sources.example.json"


@dataclass(frozen=True)
class FinanceSource:
    id: str
    name: str
    market: str
    kind: str
    url: str
    priority: str = "P2"
    post_lane: str = "market_trend"
    score_base: int = 55
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    include_forms: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    watchlist_only: bool = False


@dataclass(frozen=True)
class FinanceCandidate:
    source_id: str
    source_name: str
    market: str
    post_lane: str
    title: str
    url: str
    score: int
    priority: str
    matched_keywords: tuple[str, ...] = ()
    published: str | None = None
    summary: str = ""

    @property
    def dedupe_key(self) -> str:
        raw = f"{self.source_id}\n{self.url}\n{self.title}".encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()[:24]

    def post_text(self, *, max_chars: int = 260) -> str:
        label = _lane_label(self.post_lane)
        focus = " / ".join(self.matched_keywords[:3]) if self.matched_keywords else label
        text = (
            f"【{label}】\n"
            f"{self.title}\n"
            f"見る点: {focus}\n"
            f"出所: {self.source_name}\n"
            f"{self.url}"
        )
        return _trim_post_text(text, max_chars=max_chars)

    def x_intent_url(self) -> str:
        return "https://twitter.com/intent/tweet?text=" + quote(self.post_text(), safe="")


@dataclass
class FinanceBuildStats:
    loaded_sources: int = 0
    fetched_sources: int = 0
    skipped_sources: dict[str, int] = field(default_factory=dict)
    raw_items: int = 0
    scored_items: int = 0
    deduped_items: int = 0


@dataclass(frozen=True)
class FinanceBuildResult:
    candidates: list[FinanceCandidate]
    stats: FinanceBuildStats


class _FeedDiscoveryParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.feed_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        rel = attr.get("rel", "").lower()
        typ = attr.get("type", "").lower()
        href = attr.get("href", "").strip()
        if "alternate" not in rel or not href:
            return
        if typ in {"application/rss+xml", "application/atom+xml", "application/feed+json"}:
            self.feed_urls.append(urljoin(self.base_url, href))


class _AnchorParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._href_stack: list[str] = []
        self._text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        href = attr.get("href", "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            return
        self._href_stack.append(urljoin(self.base_url, href))
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href_stack:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href_stack:
            return
        href = self._href_stack.pop()
        text = _normalize_space(" ".join(self._text_parts))
        self._text_parts = []
        if len(text) >= 8:
            self.links.append((text, href))


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _priority_score(priority: str) -> int:
    return {"P0": 90, "P1": 70, "P2": 55, "P3": 45}.get(priority.upper(), 55)


def _lane_label(lane: str) -> str:
    return {
        "jp_equity_disclosure": "日本株材料",
        "jp_fund_etf_reit": "投信ETF材料",
        "us_equity_disclosure": "米国株材料",
        "stock_macro_news": "市場マクロ",
        "market_trend_media": "市場話題",
        "jp_market_trend": "日本株話題",
        "jp_stock_watchlist": "日本株話題",
        "market_trend": "市場話題",
    }.get(lane, "市場材料")


def _first_str(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_sources(path: Path | str = DEFAULT_SOURCE_FILE) -> tuple[list[FinanceSource], dict[str, Any]]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    raw_sources = list(data.get("sources", []))

    media_file = data.get("media_source_file")
    if media_file:
        media_path = Path(media_file)
        if not media_path.is_absolute():
            media_path = config_path.parents[0] / media_path.name
        if media_path.exists():
            media_data = json.loads(media_path.read_text(encoding="utf-8"))
            raw_sources.extend(media_data.get("sources", []))

    sources: list[FinanceSource] = []
    for raw in raw_sources:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or source_id).strip()
        url = str(raw.get("url") or raw.get("homepage") or "").strip()
        if not source_id or not url:
            continue
        priority = str(raw.get("priority") or "P2").strip().upper()
        sources.append(
            FinanceSource(
                id=source_id,
                name=name,
                market=str(raw.get("market") or "").strip(),
                kind=str(raw.get("kind") or data.get("default_kind") or "rss").strip(),
                url=url,
                priority=priority,
                post_lane=str(raw.get("post_lane") or "market_trend").strip(),
                score_base=int(raw.get("score_base") or _priority_score(priority)),
                include_keywords=tuple(str(x) for x in raw.get("include_keywords", []) if str(x).strip()),
                exclude_keywords=tuple(str(x) for x in raw.get("exclude_keywords", []) if str(x).strip()),
                include_forms=tuple(str(x) for x in raw.get("include_forms", []) if str(x).strip()),
                tags=tuple(str(x) for x in raw.get("tags", []) if str(x).strip()),
                watchlist_only=bool(raw.get("watchlist_only")),
            )
        )
    return sources, data


def _http_get(url: str, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    headers = {
        "User-Agent": os.environ.get("FINANCE_NEWS_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "application/rss+xml, application/atom+xml, text/xml, text/html;q=0.9, */*;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    return response.text


def _discover_feed_urls(homepage_url: str, html_text: str) -> list[str]:
    parser = _FeedDiscoveryParser(homepage_url)
    parser.feed(html_text)
    return list(dict.fromkeys(parser.feed_urls))


def _items_from_feed_text(source: FinanceSource, feed_text: str) -> list[dict[str, str]]:
    parsed = feedparser.parse(feed_text)
    items: list[dict[str, str]] = []
    for entry in parsed.entries:
        title = _normalize_space(getattr(entry, "title", ""))
        link = _first_str(entry, "link", "id")
        summary = _normalize_space(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        published = _first_str(entry, "published", "updated", "created")
        if not title or not link:
            continue
        items.append(
            {
                "source_id": source.id,
                "source_name": source.name,
                "market": source.market,
                "post_lane": source.post_lane,
                "title": title,
                "url": link,
                "summary": summary,
                "published": published,
            }
        )
    return items


def _items_from_homepage(source: FinanceSource, html_text: str) -> list[dict[str, str]]:
    parser = _AnchorParser(source.url)
    parser.feed(html_text)
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for title, href in parser.links:
        key = f"{title}\n{href}"
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "source_id": source.id,
                "source_name": source.name,
                "market": source.market,
                "post_lane": source.post_lane,
                "title": title,
                "url": href,
                "summary": "",
                "published": "",
            }
        )
    return items


def collect_raw_items(
    sources: list[FinanceSource],
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_items_per_source: int = DEFAULT_MAX_ITEMS_PER_SOURCE,
    stats: FinanceBuildStats | None = None,
) -> list[tuple[FinanceSource, dict[str, str]]]:
    output: list[tuple[FinanceSource, dict[str, str]]] = []
    for source in sources:
        try:
            body = _http_get(source.url, timeout_seconds=timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - source failure must not kill whole lane
            LOG.warning("finance_source_fetch_failed source=%s error=%s", source.id, type(exc).__name__)
            if stats:
                stats.skipped_sources["fetch_failed"] = stats.skipped_sources.get("fetch_failed", 0) + 1
            continue

        items: list[dict[str, str]] = []
        if source.kind in {"rss", "atom"}:
            items = _items_from_feed_text(source, body)
        elif "feed_discovery" in source.kind or "rss_if_available" in source.kind:
            feed_urls = _discover_feed_urls(source.url, body)
            for feed_url in feed_urls[:2]:
                try:
                    items.extend(_items_from_feed_text(source, _http_get(feed_url, timeout_seconds=timeout_seconds)))
                except Exception:
                    continue
            if not items:
                items = _items_from_homepage(source, body)
        elif "homepage_watch" in source.kind or "html_to_internal_rss" in source.kind:
            items = _items_from_homepage(source, body)
        else:
            if stats:
                stats.skipped_sources["unsupported_kind"] = stats.skipped_sources.get("unsupported_kind", 0) + 1
            continue

        if stats:
            stats.fetched_sources += 1
            stats.raw_items += len(items)
        for item in items[:max_items_per_source]:
            output.append((source, item))
    return output


def _matches_keyword(text: str, keyword: str) -> bool:
    return keyword.casefold() in text.casefold()


def _score_item(source: FinanceSource, item: dict[str, str]) -> FinanceCandidate | None:
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    if any(_matches_keyword(text, kw) for kw in source.exclude_keywords):
        return None

    matched = tuple(kw for kw in source.include_keywords if _matches_keyword(text, kw))
    form_matched = tuple(form for form in source.include_forms if _matches_keyword(text, form))
    if source.include_keywords and not matched and not form_matched:
        return None
    if source.include_forms and not form_matched and not matched:
        return None

    score = source.score_base + min(15, (len(matched) + len(form_matched)) * 5)
    if source.priority == "P0":
        score += 5
    if source.post_lane == "market_trend_media":
        score -= 15

    return FinanceCandidate(
        source_id=source.id,
        source_name=source.name,
        market=item.get("market", source.market),
        post_lane=source.post_lane,
        title=_normalize_space(item.get("title", "")),
        url=item.get("url", ""),
        score=score,
        priority=source.priority,
        matched_keywords=tuple(dict.fromkeys(matched + form_matched)),
        published=item.get("published") or None,
        summary=_normalize_space(item.get("summary", "")),
    )


def score_items(
    raw_items: list[tuple[FinanceSource, dict[str, str]]],
    *,
    minimum_score: int = DEFAULT_MINIMUM_SCORE,
    stats: FinanceBuildStats | None = None,
) -> list[FinanceCandidate]:
    candidates: list[FinanceCandidate] = []
    for source, item in raw_items:
        candidate = _score_item(source, item)
        if candidate is None:
            continue
        if stats:
            stats.scored_items += 1
        if candidate.score >= minimum_score:
            candidates.append(candidate)
    candidates.sort(key=lambda c: (c.score, c.priority == "P0"), reverse=True)
    return candidates


def _parse_timestamp(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        return None


def _read_gcs_text(uri: str) -> str:
    from google.cloud import storage  # type: ignore

    bucket_name, blob_name = uri[5:].split("/", 1)
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(blob_name)
    if not blob.exists():
        return ""
    return blob.download_as_text(encoding="utf-8")


def _write_gcs_text(uri: str, text: str) -> None:
    from google.cloud import storage  # type: ignore

    bucket_name, blob_name = uri[5:].split("/", 1)
    client = storage.Client()
    client.bucket(bucket_name).blob(blob_name).upload_from_string(text, content_type="application/jsonl")


def _ledger_text(path: Path, gcs_uri: str | None) -> str:
    if gcs_uri:
        try:
            return _read_gcs_text(gcs_uri)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("finance_news_ledger_gcs_read_failed error=%s", type(exc).__name__)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def normalize_dedupe_url(url: str) -> str:
    """重複判定用に URL を正規化（末尾スラッシュ・クエリ・フラグメント・スキーム差を吸収）。

    同一記事でもタイトルに「New」バッジや日付ラベルが付いて揺れるため、
    重複判定は「どのページか（URL）」を基準にする。
    """
    u = (url or "").strip()
    if not u:
        return ""
    u = re.sub(r"#.*$", "", u)          # フラグメント除去
    u = re.sub(r"\?.*$", "", u)         # クエリ除去（同一記事の追跡パラメータ差を無視）
    u = re.sub(r"^https?://", "", u, flags=re.IGNORECASE)  # スキーム差を無視
    u = u.rstrip("/")
    return u.casefold()


def load_ledger_keys(
    *,
    now: datetime,
    window_hours: int = DEFAULT_DEDUPE_WINDOW_HOURS,
    ledger_path: Path | str | None = None,
    gcs_uri: str | None = None,
) -> set[str]:
    path = Path(ledger_path or os.environ.get("FINANCE_NEWS_LEDGER_PATH", "logs/finance_news_sns_ledger.jsonl"))
    cutoff = now - timedelta(hours=window_hours)
    keys: set[str] = set()
    for line in _ledger_text(path, gcs_uri).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_timestamp(str(row.get("sent_at") or ""))
        if ts and ts < cutoff:
            continue
        key = str(row.get("key") or "").strip()
        if key:
            keys.add(key)
    return keys


def load_ledger_urls(
    *,
    now: datetime,
    window_hours: int = DEFAULT_DEDUPE_WINDOW_HOURS,
    ledger_path: Path | str | None = None,
    gcs_uri: str | None = None,
) -> set[str]:
    """過去に送信済みの URL（正規化済み）の集合を返す。

    タイトル揺れに強い URL ベースの重複判定に使う。ledger 行は以前から `url`
    を保持しているため後方互換（既存 ledger をそのまま使える）。
    """
    path = Path(ledger_path or os.environ.get("FINANCE_NEWS_LEDGER_PATH", "logs/finance_news_sns_ledger.jsonl"))
    cutoff = now - timedelta(hours=window_hours)
    urls: set[str] = set()
    for line in _ledger_text(path, gcs_uri).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_timestamp(str(row.get("sent_at") or ""))
        if ts and ts < cutoff:
            continue
        norm = normalize_dedupe_url(str(row.get("url") or ""))
        if norm:
            urls.add(norm)
    return urls


def append_ledger(
    candidates: list[FinanceCandidate],
    *,
    now: datetime,
    ledger_path: Path | str | None = None,
    gcs_uri: str | None = None,
) -> None:
    path = Path(ledger_path or os.environ.get("FINANCE_NEWS_LEDGER_PATH", "logs/finance_news_sns_ledger.jsonl"))
    existing = _ledger_text(path, gcs_uri)
    rows = [
        json.dumps(
            {
                "sent_at": now.isoformat(),
                "key": cand.dedupe_key,
                "source_id": cand.source_id,
                "title": cand.title,
                "url": cand.url,
            },
            ensure_ascii=False,
        )
        for cand in candidates
    ]
    text = (existing.rstrip("\n") + "\n" if existing.strip() else "") + "\n".join(rows) + ("\n" if rows else "")
    if gcs_uri:
        try:
            _write_gcs_text(gcs_uri, text)
            return
        except Exception as exc:  # noqa: BLE001
            LOG.warning("finance_news_ledger_gcs_write_failed error=%s", type(exc).__name__)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def filter_seen(
    candidates: list[FinanceCandidate],
    seen_keys: set[str],
    *,
    stats: FinanceBuildStats | None = None,
) -> list[FinanceCandidate]:
    filtered = [cand for cand in candidates if cand.dedupe_key not in seen_keys]
    if stats:
        stats.deduped_items = len(candidates) - len(filtered)
    return filtered


def build_candidates(
    *,
    source_path: Path | str = DEFAULT_SOURCE_FILE,
    now: datetime | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_items_per_source: int = DEFAULT_MAX_ITEMS_PER_SOURCE,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    minimum_score: int | None = None,
    ledger_path: Path | str | None = None,
    gcs_ledger_uri: str | None = None,
) -> FinanceBuildResult:
    active_now = now or datetime.now().astimezone()
    sources, config = load_sources(source_path)
    stats = FinanceBuildStats(loaded_sources=len(sources))
    raw_items = collect_raw_items(
        sources,
        timeout_seconds=timeout_seconds,
        max_items_per_source=max_items_per_source,
        stats=stats,
    )
    min_score = int(
        minimum_score
        if minimum_score is not None
        else config.get("scoring", {}).get("minimum_score_to_mail", DEFAULT_MINIMUM_SCORE)
    )
    scored = score_items(raw_items, minimum_score=min_score, stats=stats)
    ledger_uri = gcs_ledger_uri or os.environ.get("FINANCE_NEWS_LEDGER_GCS_URI") or ""
    seen = load_ledger_keys(
        now=active_now,
        window_hours=int(config.get("scoring", {}).get("dedupe_window_hours", DEFAULT_DEDUPE_WINDOW_HOURS)),
        ledger_path=ledger_path,
        gcs_uri=ledger_uri or None,
    )
    fresh = filter_seen(scored, seen, stats=stats)
    return FinanceBuildResult(candidates=fresh[:max_candidates], stats=stats)


def _trim_post_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    url = lines[-1] if lines and lines[-1].startswith("http") else ""
    body = "\n".join(lines[:-1] if url else lines)
    room = max_chars - len(url) - (1 if url else 0)
    if room < 40:
        return text[: max_chars - 1] + "…"
    trimmed = body[: room - 1].rstrip() + "…"
    return f"{trimmed}\n{url}" if url else trimmed


def compose_mail(
    candidates: list[FinanceCandidate],
    *,
    now: datetime,
    stats: FinanceBuildStats,
) -> tuple[str, str, str]:
    date_label = now.strftime("%Y-%m-%d %H:%M")
    subject = f"【金融SNS候補】株ニュース材料 {len(candidates)}件 {now.strftime('%m/%d %H:%M')}"
    if not candidates:
        subject = f"【金融SNS候補】株ニュース材料 0件 {now.strftime('%m/%d %H:%M')}"

    text_lines = [
        f"金融SNS投稿候補 ({date_label})",
        "",
        "売買指示ではありません。原典URLを確認してから投稿してください。",
        "",
        f"loaded_sources={stats.loaded_sources} raw_items={stats.raw_items} scored_items={stats.scored_items} deduped_items={stats.deduped_items}",
        "",
    ]
    html_parts = [
        "<html><body>",
        "<h2>金融SNS投稿候補</h2>",
        f"<p>{escape(date_label)} JST</p>",
        "<p><strong>注意:</strong> 売買指示ではありません。原典URLを確認してから投稿してください。</p>",
        f"<p>sources={stats.loaded_sources} / raw={stats.raw_items} / scored={stats.scored_items} / deduped={stats.deduped_items}</p>",
    ]

    if not candidates:
        text_lines.append("候補はありません。")
        html_parts.append("<p>候補はありません。</p>")
    for idx, cand in enumerate(candidates, 1):
        post_text = cand.post_text()
        text_lines.extend(
            [
                f"■ 候補 {idx}: {cand.title}",
                f"score={cand.score} source={cand.source_name} lane={cand.post_lane}",
                post_text,
                f"X投稿画面: {cand.x_intent_url()}",
                "",
            ]
        )
        html_parts.extend(
            [
                '<div style="border:1px solid #ddd;padding:14px;margin:12px 0;border-radius:8px">',
                f"<h3>候補 {idx}: {escape(cand.title)}</h3>",
                f"<p>score={cand.score} / source={escape(cand.source_name)} / lane={escape(cand.post_lane)}</p>",
                f"<pre style=\"white-space:pre-wrap;background:#f7f7f7;padding:10px\">{escape(post_text)}</pre>",
                f'<p><a href="{escape(cand.url)}">原典を開く</a></p>',
                f'<p><a href="{escape(cand.x_intent_url())}" style="background:#111;color:#fff;padding:10px 14px;text-decoration:none;border-radius:6px">X にポストする</a></p>',
                "</div>",
            ]
        )
    html_parts.append("</body></html>")
    return subject, "\n".join(text_lines), "\n".join(html_parts)
