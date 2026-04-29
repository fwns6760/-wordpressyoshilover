from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urljoin, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
HISTORY_FILE = ROOT / "data" / "rss_history.json"
GCS_BUCKET = os.environ.get("GCS_BUCKET", "").strip()
GCS_HISTORY_KEY = "rss_history.json"
REQUEST_TIMEOUT_SECONDS = 5
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
JST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)

SPAM_MARKER_RE = re.compile(r"(噂|らしい|だってさ|やばい|草|w{3,}|ふざけ|クソ|アンチ)", re.IGNORECASE)

_FETCHER_HISTORY_CACHE: dict[str, Any] | None = None
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_LIST_ITEM_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_SCORE_RE = re.compile(r"(?:\d{1,2}|[０-９]{1,2})\s*[－\-–]\s*(?:\d{1,2}|[０-９]{1,2})")
_LINEUP_ORDER_RE = re.compile(r"(?<![0-9０-９])[1-9１-９]番(?!手)")
_RANK_PATTERNS = (
    re.compile(r"data-rank=[\"'](\d{1,2})[\"']", re.IGNORECASE),
    re.compile(r"aria-label=[\"'][^\"']*?(\d{1,2})位[^\"']*[\"']", re.IGNORECASE),
    re.compile(r"<span\b[^>]*class=[\"'][^\"']*rank[^\"']*[\"'][^>]*>\s*(\d{1,2})\s*</span>", re.IGNORECASE | re.DOTALL),
)
_VOLUME_PATTERNS = (
    re.compile(r"data-(?:trend-)?volume=[\"']([^\"']+)[\"']", re.IGNORECASE),
    re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?\s*(?:件|回|万|万件))"),
)
_GIANTS_MARKERS = ("巨人", "ジャイアンツ", "読売")
_FARM_MARKERS = ("二軍", "２軍", "2軍", "ファーム", "イースタン", "三軍")
_LINEUP_MARKERS = ("スタメン", "スターティングメンバー", "オーダー", "先発メンバー")
_POSTGAME_MARKERS = ("試合結果", "勝利", "敗戦", "引き分け", "サヨナラ", "完投勝利", "白星", "黒星", "快勝")
_PROBABLE_STARTER_MARKERS = ("予告先発", "先発予想", "予想先発")
_PREGAME_MARKERS = ("試合前", "見どころ", "プレビュー", "先発", "あす", "明日", "前日")
_NOTICE_MARKERS = ("公示", "登録", "抹消", "復帰", "怪我", "離脱", "診断", "昇格", "降格")
_PROGRAM_MARKERS = ("GIANTS TV", "ジャイアンツTV", "番組", "配信", "中継", "放送")
_STOPWORD_TOKENS = {"巨人", "ジャイアンツ", "読売", "速報", "ニュース", "野球", "プロ野球"}


def fetch_yahoo_realtime_search_giants() -> list[dict]:
    """Yahoo realtime search "巨人" scrape, timeout 5s, retry なし、失敗 → []"""
    return _fetch_and_parse(
        "https://search.yahoo.co.jp/realtime/search?p=巨人",
        _parse_yahoo_realtime_search_html,
        log_label="yahoo_realtime_search",
    )


def fetch_yahoo_news_baseball_ranking() -> list[dict]:
    """Yahoo news baseball ranking scrape, timeout 5s, retry なし"""
    return _fetch_and_parse(
        "https://news.yahoo.co.jp/ranking/access/news/baseball",
        _parse_yahoo_news_baseball_ranking_html,
        log_label="yahoo_news_ranking",
    )


def build_topic_candidate(raw_signal: dict, source: str) -> dict:
    """candidate JSON schema (doc/active/246-viral-topic-detection.md 参照) に整形"""
    return {
        "schema_version": 1,
        "detected_at": str(raw_signal.get("detected_at") or _now_iso()),
        "source": str(source or "").strip(),
        "raw_signal": {
            "keyword": _clean_text(raw_signal.get("keyword")),
            "rank": _coerce_int(raw_signal.get("rank")),
            "trend_volume": _string_or_none(raw_signal.get("trend_volume") or raw_signal.get("volume")),
            "title": _clean_text(raw_signal.get("title")),
            "url": _string_or_none(raw_signal.get("url")),
            "context_excerpt": _clean_text(raw_signal.get("context_excerpt")),
        },
        "expected_subtype": None,
        "subtype_confidence": "unresolved",
        "source_confirmation": {
            "confirmed": False,
            "primary_source_url": None,
            "primary_subtype": None,
            "reason": None,
        },
        "skip_reason": None,
        "publish_blocked": True,
        "next_action": "default_review",
    }


def classify_expected_subtype(keyword: str, title: str = "") -> tuple[str | None, str]:
    """既存 subtype 文字列のうち 1 つ + confidence (high/medium/low/unresolved) を返す。"""
    text = _normalize_text(" ".join(part for part in (keyword, title) if part))
    if not text:
        return None, "unresolved"

    is_farm = any(marker in text for marker in _FARM_MARKERS)
    has_lineup = any(marker in text for marker in _LINEUP_MARKERS) or bool(_LINEUP_ORDER_RE.search(text))
    has_score = bool(_SCORE_RE.search(text))
    has_postgame = has_score or any(marker in text for marker in _POSTGAME_MARKERS)
    has_probable_starter = any(marker in text for marker in _PROBABLE_STARTER_MARKERS)
    has_pregame = any(marker in text for marker in _PREGAME_MARKERS)
    has_notice = any(marker in text for marker in _NOTICE_MARKERS)
    has_program = any(marker in text for marker in _PROGRAM_MARKERS)

    if is_farm and has_lineup:
        return "farm_lineup", "high"
    if is_farm and has_postgame:
        return "farm_result", "high"
    if has_lineup:
        return "lineup", "high"
    if has_probable_starter:
        return "probable_starter", "high"
    if has_pregame and "先発" in text:
        return "pregame", "medium"
    if has_notice:
        return "notice", "high"
    if has_program:
        return "program", "high"
    if has_postgame:
        return "postgame", "high"
    return None, "unresolved"


def load_fetcher_history() -> dict[str, Any] | None:
    history = _load_gcs_history()
    if history is not None:
        _cache_fetcher_history(history)
        return history
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("viral topic history local load skipped: %s", exc)
        else:
            if isinstance(history, dict):
                _cache_fetcher_history(history)
                return history
            logger.warning("viral topic history local load skipped: root is not an object")
    if _FETCHER_HISTORY_CACHE is not None:
        return dict(_FETCHER_HISTORY_CACHE)
    return None


def cross_reference_official_sources(
    keyword: str,
    fetcher_history: dict | None = None,
    *,
    history_window_hours: int = 24,
) -> dict:
    """既存 fetcher が直近取得した RSS / SNS history 内で同 keyword hit 確認。"""
    history = fetcher_history if fetcher_history is not None else load_fetcher_history()
    if history is None:
        return {
            "confirmed": False,
            "primary_source_url": None,
            "primary_subtype": None,
            "reason": "history_unavailable",
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(int(history_window_hours or 0), 0))
    for row in _iter_history_rows(history):
        timestamp = _parse_history_timestamp(row.get("timestamp"))
        if timestamp is None or timestamp < cutoff:
            continue
        haystack = _normalize_text(" ".join(str(row.get(key) or "") for key in ("text", "url", "subtype")))
        if not _keyword_matches(keyword, haystack):
            continue
        return {
            "confirmed": True,
            "primary_source_url": _string_or_none(row.get("url")),
            "primary_subtype": _string_or_none(row.get("subtype")),
            "reason": "ok",
        }

    return {
        "confirmed": False,
        "primary_source_url": None,
        "primary_subtype": None,
        "reason": f"no_official_source_within_{int(history_window_hours)}h",
    }


def has_spam_marker(text: str) -> bool:
    """誹謗中傷・噂 marker を簡単 regex で検出"""
    return bool(SPAM_MARKER_RE.search(text or ""))


def is_giants_related_signal(raw_signal: Mapping[str, Any], source: str) -> bool:
    if source == "yahoo_realtime_search":
        return True
    text = _normalize_text(
        " ".join(
            str(raw_signal.get(field) or "")
            for field in ("keyword", "title", "context_excerpt", "url")
        )
    )
    return any(marker in text for marker in _GIANTS_MARKERS)


def _fetch_and_parse(
    url: str,
    parser: callable,
    *,
    log_label: str,
) -> list[dict]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": HTTP_USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        rows = parser(response.text)
        if not rows:
            raise ValueError("no rows parsed")
        return rows
    except (requests.RequestException, ValueError) as exc:
        logger.warning("%s detection skipped: %s", log_label, exc)
        return []


def _parse_yahoo_realtime_search_html(html_text: str) -> list[dict]:
    detected_at = _now_iso()
    rows: list[dict] = []
    for match in _LIST_ITEM_RE.finditer(html_text):
        item_html = match.group(0)
        fragment = match.group(1)
        anchor = _find_anchor(fragment, href_hint="/realtime/search")
        if not anchor:
            continue
        href, label_html = anchor
        keyword = _extract_realtime_keyword(href, label_html)
        if not keyword:
            continue
        text = _clean_text(fragment)
        rows.append(
            {
                "keyword": keyword,
                "rank": _extract_rank(item_html, text),
                "volume": _extract_volume(fragment, text),
                "detected_at": detected_at,
            }
        )
    return rows


def _parse_yahoo_news_baseball_ranking_html(html_text: str) -> list[dict]:
    detected_at = _now_iso()
    rows: list[dict] = []
    for match in _LIST_ITEM_RE.finditer(html_text):
        item_html = match.group(0)
        fragment = match.group(1)
        anchor = _find_anchor(fragment, href_hint="/articles/")
        if not anchor:
            anchor = _find_anchor(fragment, href_hint="news.yahoo.co.jp/articles/")
        if not anchor:
            continue
        href, label_html = anchor
        title = _clean_text(label_html)
        if not title:
            continue
        rows.append(
            {
                "title": title,
                "url": urljoin("https://news.yahoo.co.jp/", href),
                "rank": _extract_rank(item_html, _clean_text(fragment)),
                "detected_at": detected_at,
            }
        )
    return rows


def _find_anchor(fragment: str, *, href_hint: str) -> tuple[str, str] | None:
    fallback: tuple[str, str] | None = None
    for match in _ANCHOR_RE.finditer(fragment):
        href = unescape(match.group("href") or "")
        label_html = match.group("label") or ""
        if not fallback:
            fallback = (href, label_html)
        if href_hint in href:
            return href, label_html
    return fallback


def _extract_realtime_keyword(href: str, label_html: str) -> str:
    parsed = urlparse(urljoin("https://search.yahoo.co.jp/", href))
    values = parse_qs(parsed.query).get("p") or []
    if values:
        return _clean_text(values[0])
    return _clean_text(label_html)


def _extract_rank(fragment: str, text: str) -> int | None:
    for pattern in _RANK_PATTERNS:
        match = pattern.search(fragment)
        if match:
            return _coerce_int(match.group(1))
    leading = re.match(r"[^\d０-９]*([0-9０-９]{1,2})\b", text)
    if leading:
        return _coerce_int(leading.group(1))
    return None


def _extract_volume(fragment: str, text: str) -> str | None:
    for pattern in _VOLUME_PATTERNS:
        match = pattern.search(fragment) or pattern.search(text)
        if match:
            return _clean_text(match.group(1))
    return None


def _load_gcs_history() -> dict[str, Any] | None:
    if not GCS_BUCKET:
        return None
    try:
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(GCS_HISTORY_KEY)
        if not blob.exists():
            return {}
        raw = blob.download_as_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("GCS history root is not an object")
        return payload
    except Exception as exc:
        logger.warning("viral topic history GCS load skipped: %s", exc)
        return None


def _cache_fetcher_history(history: dict[str, Any]) -> None:
    global _FETCHER_HISTORY_CACHE
    _FETCHER_HISTORY_CACHE = dict(history)


def _iter_history_rows(fetcher_history: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for list_key in ("entries", "items"):
        value = fetcher_history.get(list_key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "text": " ".join(
                        str(item.get(field) or "")
                        for field in ("keyword", "title", "summary", "url")
                    ),
                    "url": item.get("url") or item.get("primary_source_url"),
                    "subtype": item.get("article_subtype") or item.get("primary_subtype"),
                    "timestamp": item.get("detected_at") or item.get("published_at") or item.get("saved_at"),
                }
            )

    for key, value in fetcher_history.items():
        if key in {"entries", "items"}:
            continue
        if not isinstance(key, str) or key.startswith("live_state:"):
            continue
        if key.startswith("rewritten_title_norm:") and isinstance(value, Mapping):
            rows.append(
                {
                    "text": " ".join(
                        filter(
                            None,
                            (
                                key.removeprefix("rewritten_title_norm:"),
                                str(value.get("original_title") or ""),
                                str(value.get("rewritten_title") or ""),
                            ),
                        )
                    ),
                    "url": value.get("post_url"),
                    "subtype": value.get("primary_subtype") or _infer_history_subtype(str(value.get("post_url") or "")),
                    "timestamp": value.get("saved_at"),
                }
            )
            continue
        if key.startswith("title_norm:"):
            rows.append(
                {
                    "text": key.removeprefix("title_norm:"),
                    "url": None,
                    "subtype": None,
                    "timestamp": value,
                }
            )
            continue
        if key.startswith("http://") or key.startswith("https://"):
            rows.append(
                {
                    "text": key,
                    "url": key.split("#", 1)[0],
                    "subtype": _infer_history_subtype(key),
                    "timestamp": value,
                }
            )
    return rows


def _infer_history_subtype(value: str) -> str | None:
    text = value or ""
    if "#lineup" in text:
        return "lineup"
    if "#postgame" in text:
        return "postgame"
    if "#live-" in text:
        return "postgame"
    if "probable" in text or "pregame" in text:
        return "pregame"
    if "farm" in text:
        return "farm_result"
    return None


def _parse_history_timestamp(value: Any) -> datetime | None:
    if isinstance(value, Mapping):
        for key in ("saved_at", "detected_at", "published_at", "updated_at"):
            parsed = _parse_history_timestamp(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _keyword_matches(keyword: str, haystack: str) -> bool:
    normalized_keyword = _normalize_text(keyword)
    normalized_haystack = _normalize_text(haystack)
    if not normalized_keyword or not normalized_haystack:
        return False
    if normalized_keyword in normalized_haystack:
        return True
    tokens = _keyword_tokens(normalized_keyword)
    return any(token in normalized_haystack for token in tokens)


def _keyword_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in re.split(r"[\s/,:：、。・()（）【】\[\]\-－–]+", text):
        clean = token.strip()
        if len(clean) < 2 or clean in _STOPWORD_TOKENS:
            continue
        tokens.append(clean)
    return tokens


def _clean_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _normalize_text(value: Any) -> str:
    return _clean_text(value).lower()


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    match = re.search(r"\d+", normalized)
    return int(match.group(0)) if match else None


def _string_or_none(value: Any) -> str | None:
    text = _clean_text(value)
    return text or None


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")
