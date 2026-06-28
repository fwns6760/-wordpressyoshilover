"""YOSHILOVER Giants news candidate mail lane.

This lane collects public news/video feeds, classifies only the metadata, and
builds an email for human review. It must not create article bodies, mutate
WordPress, publish posts, or post to X.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from src.tools import finance_news_sns_candidates as fnc

try:
    from src.google_news_url_resolver import (
        is_google_news_url,
        resolve_google_news_url,
        reset_circuit as reset_gnews_circuit,
        split_publisher_from_title,
    )
except Exception:  # pragma: no cover - resolver is best-effort
    is_google_news_url = lambda u: False  # type: ignore  # noqa: E731
    resolve_google_news_url = lambda u, **k: None  # type: ignore  # noqa: E731
    reset_gnews_circuit = lambda: None  # type: ignore  # noqa: E731
    split_publisher_from_title = lambda t: (t, None)  # type: ignore  # noqa: E731

try:
    from src.youtube_ob_source_registry import load_youtube_ob_sources
except Exception:  # pragma: no cover - optional broad source shelf
    load_youtube_ob_sources = None  # type: ignore


LOG = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_SOURCE_FILE = (
    Path(__file__).resolve().parents[2] / "config" / "yoshilover_news_candidates.example.json"
)
DEFAULT_LEDGER_PATH = "logs/yoshilover_news_candidates_ledger.jsonl"
DEFAULT_USER_AGENT = "yoshilover-news-candidates/0.1 (metadata-only)"

CATEGORY_ARTICLE = "記事化候補"
CATEGORY_X = "X候補"
CATEGORY_OB = "OBネタ"
CATEGORY_WEEKLY = "週刊誌系"
CATEGORY_CONFIRM = "要確認"
CATEGORY_EXCLUDE = "除外候補"
CATEGORIES = (
    CATEGORY_ARTICLE,
    CATEGORY_X,
    CATEGORY_OB,
    CATEGORY_WEEKLY,
    CATEGORY_CONFIRM,
    CATEGORY_EXCLUDE,
)

SECTION_TITLES = {
    CATEGORY_ARTICLE: "記事化候補",
    CATEGORY_X: "X候補",
    CATEGORY_OB: "OBネタ",
    CATEGORY_WEEKLY: "週刊誌・一般紙",
    CATEGORY_CONFIRM: "要確認",
    CATEGORY_EXCLUDE: "除外候補",
}

REQUIRED_OB_NAMES = (
    "松井秀喜",
    "原辰徳",
    "高橋由伸",
    "桑田真澄",
    "上原浩治",
    "江川卓",
    "中畑清",
    "槙原寛己",
    "斎藤雅樹",
    "清原和博",
    "元木大介",
    "仁志敏久",
    "デーブ大久保",
    "大久保博元",
)

MLB_TRACKED_GIANTS_NAMES = (
    "岡本和真",
    "Kazuma Okamoto",
    "Okamoto",
    "菅野智之",
    "すがのともゆき",
    "Tomoyuki Sugano",
    "Sugano",
)

GIANTS_RELATION_KEYWORDS = (
    "巨人",
    "読売ジャイアンツ",
    "ジャイアンツ",
    "東京ドーム",
    "阿部慎之助",
    "阿部監督",
    "二軍",
    "2軍",
    "三軍",
    "3軍",
    "育成",
    "登録抹消",
    "昇格",
    "降格",
    "支配下",
    "読売",
    "元巨人",
    "MLB",
    "メジャー",
    "大リーグ",
)

ARTICLE_KEYWORDS = (
    "分析",
    "考察",
    "背景",
    "理由",
    "なぜ",
    "課題",
    "復活",
    "若手",
    "二軍",
    "2軍",
    "三軍",
    "3軍",
    "育成",
    "ドラフト",
    "インタビュー",
    "密着",
    "特集",
    "証言",
    "解説",
    "戦略",
    "采配",
    "起用",
)

X_KEYWORDS = (
    "速報",
    "公示",
    "登録抹消",
    "出場選手登録",
    "昇格",
    "降格",
    "スタメン",
    "先発",
    "試合結果",
    "勝利",
    "敗戦",
    "本塁打",
    "ホームラン",
    "サヨナラ",
    "完封",
    "完投",
    "移籍",
    "トレード",
    "獲得",
    "契約",
)

WEEKLY_MEDIA_KEYWORDS = (
    "FRIDAY",
    "Smart FLASH",
    "FLASH",
    "NEWSポストセブン",
    "ポストセブン",
    "週刊文春",
    "文春オンライン",
    "週刊女性",
    "週刊女性PRIME",
    "デイリー新潮",
    "現代ビジネス",
    "日刊ゲンダイ",
    "夕刊フジ",
    "東スポ",
    "アサ芸",
    "週刊ベースボール",
)

GENERAL_PAPER_KEYWORDS = (
    "読売新聞",
    "朝日新聞",
    "毎日新聞",
    "産経新聞",
    "日本経済新聞",
    "共同通信",
    "時事通信",
    "地方紙",
)

CLICKBAIT_KEYWORDS = (
    "衝撃",
    "騒然",
    "炎上",
    "物議",
    "批判殺到",
    "波紋",
    "激怒",
    "暴露",
    "疑惑",
    "不仲",
    "確執",
    "泥沼",
    "ヤバい",
    "まさか",
    "緊急事態",
    "電撃",
    "悲鳴",
    "ブチギレ",
)

EXCLUDE_KEYWORDS = (
    "求人",
    "採用",
    "チケット転売",
    "オークション",
    "予想オッズ",
    "賭け",
    "カジノ",
    "ゲーム攻略",
    "なんJ",
    "掲示板",
)


@dataclass(frozen=True)
class YoshiNewsCandidate:
    source_id: str
    source_name: str
    title: str
    media: str
    url: str
    published: str
    category: str
    reason: str
    score: int
    summary: str = ""
    relation_person: str = ""
    caution: str = ""
    original_url: str = ""
    title_signature: str = ""
    matched_terms: tuple[str, ...] = ()

    @property
    def dedupe_key(self) -> str:
        raw = f"{fnc.normalize_dedupe_url(self.url)}\n{self.title_signature}".encode(
            "utf-8", errors="ignore"
        )
        return hashlib.sha256(raw).hexdigest()[:24]

    @property
    def category_label(self) -> str:
        return f"【{self.category}】"


@dataclass
class YoshiNewsBuildStats:
    loaded_sources: int = 0
    fetched_sources: int = 0
    skipped_sources: dict[str, int] = field(default_factory=dict)
    raw_items: int = 0
    scored_items: int = 0
    deduped_items: int = 0
    resolved_google_news: int = 0
    unresolved_google_news: int = 0


@dataclass(frozen=True)
class YoshiNewsBuildResult:
    candidates: list[YoshiNewsCandidate]
    stats: YoshiNewsBuildStats


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _contains_any(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    folded = text.casefold()
    return any(keyword.casefold() in folded for keyword in keywords if keyword)


def _matched(text: str, keywords: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    folded = text.casefold()
    return tuple(dict.fromkeys(k for k in keywords if k and k.casefold() in folded))


def _title_signature(title: str) -> str:
    clean_title, _publisher = split_publisher_from_title(title)
    base = re.sub(r"\s+[-–—]\s+[^-–—]+$", "", clean_title or title)
    base = re.sub(r"[「」『』【】\[\]（）()〈〉《》\"'“”‘’・|｜:：,，.。!！?？\s　…]", "", base)
    return base.casefold()[:64]


def _parse_timestamp(raw: str) -> datetime | None:
    if not raw:
        return None
    parsed = fnc._parse_timestamp(raw)  # reuse existing tolerant parser
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _format_published(raw: str) -> str:
    parsed = _parse_timestamp(raw)
    if parsed:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return _normalize_space(raw) or "不明"


def _read_json(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _google_news_search_url(query_text: str, config: dict[str, Any]) -> str:
    google_cfg = config.get("google_news", {}) if isinstance(config.get("google_news"), dict) else {}
    hl = str(google_cfg.get("hl") or "ja")
    gl = str(google_cfg.get("gl") or "JP")
    ceid = str(google_cfg.get("ceid") or "JP:ja")
    freshness_suffix = str(google_cfg.get("freshness_query_suffix") or "").strip()
    query = query_text.strip()
    if freshness_suffix and freshness_suffix not in query:
        query = f"{query} {freshness_suffix}"
    return (
        "https://news.google.com/rss/search?q="
        + quote(query, safe="")
        + f"&hl={quote(hl)}&gl={quote(gl)}&ceid={quote(ceid, safe=':')}"
    )


def _source_from_raw(raw: dict[str, Any]) -> fnc.FinanceSource | None:
    source_id = str(raw.get("id") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not source_id or not url:
        return None
    kind = str(raw.get("kind") or raw.get("type") or "rss").strip()
    if kind in {"news", "video"}:
        kind = "rss"
    return fnc.FinanceSource(
        id=source_id,
        name=str(raw.get("name") or source_id).strip(),
        market="JP",
        kind=kind,
        url=url,
        priority=str(raw.get("priority") or "P2").strip().upper(),
        post_lane=str(raw.get("post_lane") or raw.get("lane") or "general").strip(),
        score_base=int(raw.get("score_base") or 60),
        include_keywords=tuple(str(x) for x in raw.get("include_keywords", []) if str(x).strip()),
        exclude_keywords=tuple(str(x) for x in raw.get("exclude_keywords", []) if str(x).strip()),
        tags=tuple(str(x) for x in raw.get("tags", []) if str(x).strip()),
    )


def load_sources(path: Path | str = DEFAULT_SOURCE_FILE) -> tuple[list[fnc.FinanceSource], dict[str, Any]]:
    config = _read_json(path)
    sources: list[fnc.FinanceSource] = []

    for raw in config.get("google_news_queries", []):
        if not isinstance(raw, dict):
            continue
        query_text = str(raw.get("query") or "").strip()
        if not query_text:
            continue
        source_id = str(raw.get("id") or hashlib.sha1(query_text.encode("utf-8")).hexdigest()[:12])
        lane = str(raw.get("lane") or "general").strip()
        sources.append(
            fnc.FinanceSource(
                id=f"gnews_{source_id}",
                name=str(raw.get("name") or f"Googleニュース: {query_text}").strip(),
                market="JP",
                kind="rss",
                url=_google_news_search_url(query_text, config),
                priority=str(raw.get("priority") or "P1").strip().upper(),
                post_lane=lane,
                score_base=int(raw.get("score_base") or 70),
                tags=(query_text,),
            )
        )

    for raw in config.get("sources", []):
        if not isinstance(raw, dict):
            continue
        source = _source_from_raw(raw)
        if source is not None:
            sources.append(source)

    yt_cfg = config.get("youtube_ob_registry", {})
    if isinstance(yt_cfg, dict) and yt_cfg.get("enabled", False) and load_youtube_ob_sources:
        registry_path = yt_cfg.get("path")
        if registry_path:
            registry_file = Path(registry_path)
            if not registry_file.is_absolute():
                registry_file = Path(path).resolve().parents[0] / registry_path
        else:
            registry_file = None
        statuses = set(yt_cfg.get("statuses") or ["confirmed", "candidate"])
        roles = set(yt_cfg.get("roles") or ["official", "giants_ob", "broadcast", "media"])
        max_sources = int(yt_cfg.get("max_sources") or 40)
        try:
            yt_sources = load_youtube_ob_sources(registry_file)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            LOG.warning("yoshilover_youtube_registry_load_failed error=%s", type(exc).__name__)
            yt_sources = []
        for source in yt_sources[:max_sources]:
            if source.status not in statuses or source.role not in roles or source.role == "excluded":
                continue
            lane = "youtube_ob" if source.role == "giants_ob" else "youtube_video"
            if source.role == "official":
                lane = "official_video"
            sources.append(
                fnc.FinanceSource(
                    id=f"yt_{source.channel_id}",
                    name=source.display_name,
                    market="JP",
                    kind="rss",
                    url=f"https://www.youtube.com/feeds/videos.xml?channel_id={source.channel_id}",
                    priority="P1" if source.role in {"official", "giants_ob"} else "P2",
                    post_lane=lane,
                    score_base=68,
                    tags=(source.role,),
                )
            )

    return sources, config


def _ledger_text(path: Path, gcs_uri: str | None) -> str:
    return fnc._ledger_text(path, gcs_uri)  # reuse GCS/local fallback


def _write_ledger_text(path: Path, gcs_uri: str | None, text: str) -> None:
    if gcs_uri:
        try:
            fnc._write_gcs_text(gcs_uri, text)
            return
        except Exception as exc:  # noqa: BLE001
            LOG.warning("yoshilover_news_ledger_gcs_write_failed error=%s", type(exc).__name__)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_seen(
    *,
    now: datetime,
    window_hours: int,
    ledger_path: Path | str | None = None,
    gcs_uri: str | None = None,
) -> tuple[set[str], set[str], set[str]]:
    path = Path(ledger_path or os.environ.get("YOSHILOVER_NEWS_CANDIDATE_LEDGER_PATH", DEFAULT_LEDGER_PATH))
    cutoff = now - timedelta(hours=window_hours)
    keys: set[str] = set()
    urls: set[str] = set()
    title_sigs: set[str] = set()
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
        norm_url = fnc.normalize_dedupe_url(str(row.get("url") or ""))
        if norm_url:
            urls.add(norm_url)
        title_sig = str(row.get("title_sig") or row.get("title_signature") or "").strip()
        if title_sig:
            title_sigs.add(title_sig)
    return keys, urls, title_sigs


def append_ledger(
    candidates: list[YoshiNewsCandidate],
    *,
    now: datetime,
    ledger_path: Path | str | None = None,
    gcs_uri: str | None = None,
) -> None:
    path = Path(ledger_path or os.environ.get("YOSHILOVER_NEWS_CANDIDATE_LEDGER_PATH", DEFAULT_LEDGER_PATH))
    existing = _ledger_text(path, gcs_uri)
    rows = [
        json.dumps(
            {
                "sent_at": now.isoformat(),
                "key": cand.dedupe_key,
                "title": cand.title,
                "title_sig": cand.title_signature,
                "url": cand.url,
                "media": cand.media,
                "category": cand.category,
            },
            ensure_ascii=False,
        )
        for cand in candidates
    ]
    text = (existing.rstrip("\n") + "\n" if existing.strip() else "") + "\n".join(rows)
    if rows:
        text += "\n"
    _write_ledger_text(path, gcs_uri, text)


def _media_from_title_or_source(title: str, source_name: str) -> str:
    _clean_title, publisher = split_publisher_from_title(title)
    if not publisher:
        pipe_match = re.match(r"^(.*\S)\s+[|｜]\s+([^|｜]+)$", (title or "").strip())
        if pipe_match:
            publisher = pipe_match.group(2).strip()
    return _normalize_space(publisher or source_name or "不明")


def _inherently_related_source(source: fnc.FinanceSource) -> bool:
    blob = f"{source.name} {source.post_lane} {' '.join(source.tags)}"
    if source.post_lane in {"official_video", "youtube_ob", "mlb_alumni"}:
        return True
    return _contains_any(blob, GIANTS_RELATION_KEYWORDS + REQUIRED_OB_NAMES + MLB_TRACKED_GIANTS_NAMES)


def _relation_people(text: str) -> tuple[str, ...]:
    return _matched(text, REQUIRED_OB_NAMES)


def _tracked_mlb_people(text: str) -> tuple[str, ...]:
    return _matched(text, MLB_TRACKED_GIANTS_NAMES)


def _is_youtube(source: fnc.FinanceSource, url: str) -> bool:
    blob = f"{source.name} {source.post_lane} {url}"
    return "youtube" in blob.casefold() or "youtu.be" in blob.casefold()


def _category_reason(
    *,
    source: fnc.FinanceSource,
    title: str,
    media: str,
    url: str,
    summary: str,
    google_unresolved: bool,
) -> tuple[str, str, str, tuple[str, ...], int]:
    media_for_ob = "" if media.startswith("Googleニュース:") else media
    item_text = f"{title} {summary} {media_for_ob}"
    source_text = f"{source.name} {' '.join(source.tags)}"
    text = f"{item_text} {source_text}"
    relation_people = _relation_people(text)
    mlb_people = _tracked_mlb_people(text)
    matched_terms = _matched(
        text,
        GIANTS_RELATION_KEYWORDS + REQUIRED_OB_NAMES + MLB_TRACKED_GIANTS_NAMES + ARTICLE_KEYWORDS + X_KEYWORDS,
    )
    related = bool(
        relation_people
        or mlb_people
        or _contains_any(text, GIANTS_RELATION_KEYWORDS)
        or _inherently_related_source(source)
    )
    if _contains_any(text, EXCLUDE_KEYWORDS):
        return CATEGORY_EXCLUDE, "広告・転売・賭け系などニュース候補から外す語を含むため。", "", matched_terms, 10
    if not related:
        return CATEGORY_EXCLUDE, "巨人・現役選手・監督コーチ・OBとの関係が薄いため。", "", matched_terms, 15

    is_weekly = _contains_any(f"{title} {summary} {media} {source.name}", WEEKLY_MEDIA_KEYWORDS)
    is_general_paper = _contains_any(f"{media} {source.name}", GENERAL_PAPER_KEYWORDS)
    is_clickbait = _contains_any(text, CLICKBAIT_KEYWORDS) or google_unresolved
    explicit_ob_item = _contains_any(
        item_text,
        ("OB", "元巨人", "巨人OB", "解説", "YouTube", "ユーチューブ", "回顧", "発言", "語る"),
    )
    is_ob = bool(relation_people) or source.post_lane == "youtube_ob" or (
        source.post_lane == "ob" and explicit_ob_item
    )
    is_video = _is_youtube(source, url)
    is_x = _contains_any(text, X_KEYWORDS) or source.post_lane in {"notice", "breaking"}
    is_article = _contains_any(text, ARTICLE_KEYWORDS) or source.post_lane in {
        "general",
        "manager",
        "farm",
        "young",
        "article",
        "mlb_alumni",
    }

    score = int(source.score_base)
    if relation_people:
        score += 18
    if mlb_people:
        score += 16
    if is_video:
        score += 8
    if is_general_paper:
        score += 5
    if is_weekly:
        score += 7
    if is_article:
        score += 10
    if is_x:
        score += 8
    if is_clickbait:
        score -= 12

    if is_clickbait:
        caution = "GoogleニュースURL未解決、または釣り・炎上寄りの表現を含むため、原典確認が必要。"
        return CATEGORY_CONFIRM, caution, caution, matched_terms, max(score, 45)
    if is_ob:
        person = "、".join(relation_people) if relation_people else "巨人OB"
        caution = "週刊誌・夕刊紙系の媒体なので表現と事実関係を確認。" if is_weekly else ""
        return CATEGORY_OB, f"{person}の発言・動画・回顧として話題化しやすいため。", caution, matched_terms, score
    if mlb_people:
        person = "、".join(mlb_people)
        if is_x and not is_article:
            return CATEGORY_X, f"{person}のMLB動向として短く反応を取りやすいため。", "", matched_terms, score
        return CATEGORY_ARTICLE, f"{person}の元巨人・現MLB動向としてYOSHILOVERで追跡価値があるため。", "", matched_terms, score
    if is_weekly:
        caution = "週刊誌・夕刊紙・ゴシップ寄り媒体のため、表現と事実関係を確認して扱う。"
        return CATEGORY_WEEKLY, "公式・大手紙とは違う角度があり、ファンの反応を見込めるため。", caution, matched_terms, score
    if is_x and not is_article:
        return CATEGORY_X, "速報性があり、短いX投稿で反応を取りやすいため。", "", matched_terms, score
    if is_article:
        return CATEGORY_ARTICLE, "YOSHILOVERで独自コメントや考察を足しやすい素材のため。", "", matched_terms, score
    return CATEGORY_X, "短く拾うニュース候補として扱いやすいため。", "", matched_terms, score


def _candidate_from_item(
    source: fnc.FinanceSource,
    item: dict[str, str],
    *,
    timeout_seconds: int,
    resolve_google_news: bool,
    stats: YoshiNewsBuildStats,
) -> YoshiNewsCandidate:
    title = _normalize_space(item.get("title", ""))
    summary = _normalize_space(item.get("summary", ""))
    original_url = item.get("url", "").strip()
    url = original_url
    media = _media_from_title_or_source(title, item.get("source_name") or source.name)
    google_unresolved = False

    if resolve_google_news and is_google_news_url(original_url):
        resolved = resolve_google_news_url(original_url, timeout=timeout_seconds, retries=1)
        _clean_title, publisher = split_publisher_from_title(title)
        if publisher:
            media = publisher
        if resolved:
            url = resolved
            stats.resolved_google_news += 1
        else:
            google_unresolved = True
            stats.unresolved_google_news += 1

    category, reason, caution, matched_terms, score = _category_reason(
        source=source,
        title=title,
        media=media,
        url=url,
        summary=summary,
        google_unresolved=google_unresolved,
    )
    people = _relation_people(f"{title} {summary} {media} {source.name}")
    mlb_people = _tracked_mlb_people(f"{title} {summary} {media} {source.name} {' '.join(source.tags)}")
    title_sig = _title_signature(title)
    return YoshiNewsCandidate(
        source_id=source.id,
        source_name=source.name,
        title=title,
        media=media,
        url=url,
        original_url=original_url,
        published=_format_published(item.get("published") or ""),
        category=category,
        reason=reason,
        caution=caution,
        relation_person="、".join(people or mlb_people),
        score=score,
        summary=summary,
        title_signature=title_sig,
        matched_terms=matched_terms,
    )


def _sort_candidates(candidates: list[YoshiNewsCandidate]) -> list[YoshiNewsCandidate]:
    category_rank = {
        CATEGORY_ARTICLE: 5,
        CATEGORY_OB: 5,
        CATEGORY_X: 4,
        CATEGORY_WEEKLY: 3,
        CATEGORY_CONFIRM: 2,
        CATEGORY_EXCLUDE: 1,
    }
    return sorted(candidates, key=lambda c: (category_rank.get(c.category, 0), c.score), reverse=True)


def build_candidates(
    *,
    source_path: Path | str = DEFAULT_SOURCE_FILE,
    now: datetime | None = None,
    timeout_seconds: int = 6,
    max_items_per_source: int = 8,
    max_candidates: int = 18,
    ledger_path: Path | str | None = None,
    gcs_ledger_uri: str | None = None,
    resolve_google_news: bool = True,
    include_excluded: bool | None = None,
) -> YoshiNewsBuildResult:
    reset_gnews_circuit()
    active_now = now or datetime.now(JST)
    sources, config = load_sources(source_path)
    stats = YoshiNewsBuildStats(loaded_sources=len(sources))
    finance_stats = fnc.FinanceBuildStats(loaded_sources=len(sources))
    raw_items = fnc.collect_raw_items(
        sources,
        timeout_seconds=timeout_seconds,
        max_items_per_source=max_items_per_source,
        stats=finance_stats,
    )
    stats.fetched_sources = finance_stats.fetched_sources
    stats.skipped_sources = dict(finance_stats.skipped_sources)
    stats.raw_items = finance_stats.raw_items

    scoring_cfg = config.get("scoring", {}) if isinstance(config.get("scoring"), dict) else {}
    window = int(scoring_cfg.get("dedupe_window_hours", 168))
    ledger_uri = gcs_ledger_uri or os.environ.get("YOSHILOVER_NEWS_CANDIDATE_LEDGER_GCS_URI") or None
    seen_keys, seen_urls, seen_titles = load_seen(
        now=active_now,
        window_hours=window,
        ledger_path=ledger_path,
        gcs_uri=ledger_uri,
    )
    if include_excluded is None:
        include_excluded = bool(scoring_cfg.get("include_excluded", True))
    max_excluded = int(scoring_cfg.get("max_excluded_to_mail", 3))
    max_attempts = int(scoring_cfg.get("max_candidate_attempts", max(max_candidates * 6, 80)))
    resolve_deadline = time.monotonic() + float(scoring_cfg.get("max_resolve_seconds", 240))

    candidates: list[YoshiNewsCandidate] = []
    excluded: list[YoshiNewsCandidate] = []
    run_seen_urls: set[str] = set()
    run_seen_titles: set[str] = set()

    for source, item in raw_items[:max_attempts]:
        if time.monotonic() > resolve_deadline:
            LOG.info("yoshilover_news_resolve_time_budget_reached candidates=%d", len(candidates))
            break
        if not item.get("title") or not item.get("url"):
            continue
        cand = _candidate_from_item(
            source,
            item,
            timeout_seconds=timeout_seconds,
            resolve_google_news=resolve_google_news,
            stats=stats,
        )
        stats.scored_items += 1
        norm_url = fnc.normalize_dedupe_url(cand.url)
        if (
            cand.dedupe_key in seen_keys
            or (norm_url and norm_url in seen_urls)
            or (cand.title_signature and cand.title_signature in seen_titles)
            or (norm_url and norm_url in run_seen_urls)
            or (cand.title_signature and cand.title_signature in run_seen_titles)
        ):
            stats.deduped_items += 1
            continue
        if norm_url:
            run_seen_urls.add(norm_url)
        if cand.title_signature:
            run_seen_titles.add(cand.title_signature)
        if cand.category == CATEGORY_EXCLUDE:
            excluded.append(cand)
        else:
            candidates.append(cand)

    picked = _sort_candidates(candidates)[:max_candidates]
    if include_excluded and max_excluded > 0:
        picked.extend(_sort_candidates(excluded)[:max_excluded])
    return YoshiNewsBuildResult(candidates=picked, stats=stats)


def _items_by_category(candidates: list[YoshiNewsCandidate]) -> dict[str, list[YoshiNewsCandidate]]:
    buckets = {category: [] for category in CATEGORIES}
    for cand in candidates:
        buckets.setdefault(cand.category, []).append(cand)
    return buckets


def recommendation_top3(candidates: list[YoshiNewsCandidate]) -> list[YoshiNewsCandidate]:
    usable = [c for c in candidates if c.category not in {CATEGORY_EXCLUDE, CATEGORY_CONFIRM}]
    return sorted(
        usable,
        key=lambda c: (
            c.score
            + (18 if c.category == CATEGORY_OB else 0)
            + (10 if c.category == CATEGORY_WEEKLY else 0)
            + (8 if c.category == CATEGORY_ARTICLE else 0)
        ),
        reverse=True,
    )[:3]


def _candidate_text(cand: YoshiNewsCandidate) -> list[str]:
    lines = [cand.category_label]
    if cand.category == CATEGORY_OB:
        lines.extend(
            [
                f"タイトル：{cand.title}",
                f"媒体：{cand.media}",
                f"公開日時：{cand.published}",
                f"URL：{cand.url}",
                f"関係者：{cand.relation_person or '巨人OB'}",
                f"理由：{cand.reason}",
            ]
        )
    elif cand.category == CATEGORY_WEEKLY:
        lines.extend(
            [
                f"タイトル：{cand.title}",
                f"媒体：{cand.media}",
                f"公開日時：{cand.published}",
                f"URL：{cand.url}",
                f"注意点：{cand.caution or cand.reason}",
            ]
        )
    elif cand.category == CATEGORY_CONFIRM:
        lines.extend(
            [
                f"タイトル：{cand.title}",
                f"媒体：{cand.media}",
                f"公開日時：{cand.published}",
                f"URL：{cand.url}",
                f"要確認理由：{cand.caution or cand.reason}",
            ]
        )
    else:
        lines.extend(
            [
                f"タイトル：{cand.title}",
                f"媒体：{cand.media}",
                f"公開日時：{cand.published}",
                f"URL：{cand.url}",
                f"理由：{cand.reason}",
            ]
        )
    return lines


def compose_mail(
    candidates: list[YoshiNewsCandidate],
    *,
    now: datetime,
    stats: YoshiNewsBuildStats,
) -> tuple[str, str, str]:
    now_jst = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    subject = f"【YOSHILOVER】巨人ニュース候補：{now_jst.strftime('%Y-%m-%d %H')}"
    buckets = _items_by_category(candidates)
    text_lines = [
        "【巨人ニュース候補】",
        "",
        "本文は作成していません。自動公開・X自動投稿もしません。URLと原典を確認してから採用してください。",
        (
            f"sources={stats.loaded_sources} fetched={stats.fetched_sources} "
            f"raw={stats.raw_items} scored={stats.scored_items} "
            f"deduped={stats.deduped_items} gnews_resolved={stats.resolved_google_news} "
            f"gnews_unresolved={stats.unresolved_google_news}"
        ),
        "",
    ]

    html_parts = [
        "<html><body>",
        "<h2>巨人ニュース候補</h2>",
        "<p>本文は作成していません。自動公開・X自動投稿もしません。URLと原典を確認してから採用してください。</p>",
        (
            f"<p>sources={stats.loaded_sources} / fetched={stats.fetched_sources} / "
            f"raw={stats.raw_items} / scored={stats.scored_items} / "
            f"deduped={stats.deduped_items} / gnews_resolved={stats.resolved_google_news} / "
            f"gnews_unresolved={stats.unresolved_google_news}</p>"
        ),
    ]

    for category in CATEGORIES:
        items = buckets.get(category, [])
        heading = SECTION_TITLES.get(category, category)
        text_lines.extend([f"■ {heading}", ""])
        html_parts.append(f"<h3>{escape(heading)}</h3>")
        if not items:
            text_lines.extend(["該当なし", ""])
            html_parts.append("<p>該当なし</p>")
            continue
        html_parts.append("<ol>")
        for cand in items:
            text_lines.extend(_candidate_text(cand))
            text_lines.append("")
            details = "<br>".join(escape(line) for line in _candidate_text(cand))
            html_parts.append(
                "<li style=\"margin-bottom:14px;\">"
                f"{details}<br>"
                f'<a href="{escape(cand.url)}">原典を開く</a>'
                "</li>"
            )
        html_parts.append("</ol>")

    top3 = recommendation_top3(candidates)
    text_lines.extend(["今日のおすすめ上位3件", ""])
    html_parts.append("<h3>今日のおすすめ上位3件</h3>")
    if not top3:
        text_lines.extend(["該当なし", ""])
        html_parts.append("<p>該当なし</p>")
    else:
        html_parts.append("<ol>")
        for idx, cand in enumerate(top3, 1):
            text_lines.extend(
                [
                    f"{idx}. {cand.category_label} {cand.title}",
                    f"媒体：{cand.media}",
                    f"URL：{cand.url}",
                    f"理由：{cand.reason}",
                    "",
                ]
            )
            html_parts.append(
                "<li style=\"margin-bottom:10px;\">"
                f"<strong>{escape(cand.category_label)} {escape(cand.title)}</strong><br>"
                f"媒体：{escape(cand.media)}<br>"
                f"理由：{escape(cand.reason)}<br>"
                f'<a href="{escape(cand.url)}">原典を開く</a>'
                "</li>"
            )
        html_parts.append("</ol>")
    html_parts.append("</body></html>")
    return subject, "\n".join(text_lines).rstrip() + "\n", "\n".join(html_parts)
