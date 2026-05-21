"""347 CLI entry — send one セ・リーグ X post candidate mail.

Default is **live send** (matches publish-notice job semantics); pass
``--dry-run`` to skip the SMTP call.

Hard constraints (mirror ticket 347):
    - LLM API never called.
    - insight.db: read-only via miq.query_rank.
    - article_candidates table: never touched (348 owns it).
    - パ・リーグ 6 teams: filtered out, only セ 6 teams reach the mail.

Cloud Run Job entrypoint: ``python -m src.tools.run_x_post_mail``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence
from urllib import request as urlrequest
from urllib.error import URLError
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src import manual_intake_insight_query as miq  # noqa: E402
from src import mail_delivery_bridge as mdb  # noqa: E402
from src import x_post_mail_lane as lane  # noqa: E402
# 392: optional import — only used when X_POST_MAIL_GEMMA_GEN_ENABLED=1。
# 既存 (flag OFF) 経路で import 失敗時に mail を止めないため lazy import。
try:
    from src import x_post_branding_gen as _xbg  # noqa: E402
except Exception:  # noqa: BLE001 - keep mail lane working even if 392 deps missing
    _xbg = None  # type: ignore[assignment]


LOG = logging.getLogger("x_post_mail")
DEFAULT_MAX_DB_STALENESS_DAYS = 2
DEFAULT_DEDUP_MIN_CANDIDATES = 3
DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES = 1
DEFAULT_NEWS_FALLBACK_SOURCE_LIMIT = 32
DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT = 5
DEFAULT_NEWS_FALLBACK_TIMEOUT_SECONDS = 4
DEFAULT_NEWS_PRIORITY_CANDIDATES = 5
RSS_SOURCES_FILE = Path(__file__).resolve().parents[2] / "config" / "rss_sources.json"


def _configure_logging() -> None:
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _resolve_recipients(override: str | None) -> list[str]:
    if override:
        return [r.strip() for r in override.split(",") if r.strip()]
    raw = os.environ.get("MAIL_BRIDGE_TO") or os.environ.get("X_POST_MAIL_TO") or ""
    return [r.strip() for r in raw.split(",") if r.strip()]


def _resolve_sender() -> str | None:
    # Match the env precedence mail_delivery_bridge honours so the
    # observed From: address matches the publish-notice convention.
    return (
        os.environ.get("MAIL_BRIDGE_FROM")
        or os.environ.get("NOTIFY_FROM")
        or os.environ.get("MAIL_BRIDGE_SMTP_USERNAME")
        or None
    )


def _resolve_reply_to() -> str | None:
    return os.environ.get("MAIL_BRIDGE_REPLY_TO") or os.environ.get("NOTIFY_REPLY_TO")


def _resolve_max_db_staleness_days() -> int:
    raw = (
        os.environ.get("X_POST_MAIL_MAX_DB_STALENESS_DAYS")
        or str(DEFAULT_MAX_DB_STALENESS_DAYS)
    ).strip()
    try:
        return int(raw)
    except ValueError:
        LOG.warning(
            "Invalid X_POST_MAIL_MAX_DB_STALENESS_DAYS=%r; using default %d",
            raw,
            DEFAULT_MAX_DB_STALENESS_DAYS,
        )
        return DEFAULT_MAX_DB_STALENESS_DAYS


def _resolve_dedup_min_candidates() -> int:
    raw = (
        os.environ.get("X_POST_MAIL_DEDUP_MIN_CANDIDATES")
        or str(DEFAULT_DEDUP_MIN_CANDIDATES)
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        LOG.warning(
            "Invalid X_POST_MAIL_DEDUP_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_DEDUP_MIN_CANDIDATES,
        )
        return DEFAULT_DEDUP_MIN_CANDIDATES
    if value < 0:
        LOG.warning(
            "Invalid X_POST_MAIL_DEDUP_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_DEDUP_MIN_CANDIDATES,
        )
        return DEFAULT_DEDUP_MIN_CANDIDATES
    return value


def _resolve_lineup_focus_min_candidates() -> int:
    raw = (
        os.environ.get("X_POST_MAIL_LINEUP_FOCUS_MIN_CANDIDATES")
        or str(DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES)
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        LOG.warning(
            "Invalid X_POST_MAIL_LINEUP_FOCUS_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES,
        )
        return DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES
    if value < 0:
        LOG.warning(
            "Invalid X_POST_MAIL_LINEUP_FOCUS_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES,
        )
        return DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES
    return value


def _lineup_focus_disabled() -> bool:
    raw = (os.environ.get("X_POST_MAIL_LINEUP_FOCUS_DISABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _news_fallback_disabled() -> bool:
    raw = (os.environ.get("X_POST_MAIL_NEWS_FALLBACK_DISABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _gemma_branding_enabled() -> bool:
    """392: env flag for Gemma 4 + Tavily REST branding candidate.

    Default OFF。 ON 時のみ news_opinion fallback を skip して Gemma 候補
    を mail に append する。 flag OFF では既存挙動完全不変。
    """
    raw = (os.environ.get("X_POST_MAIL_GEMMA_GEN_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _gemma_branding_max_per_run() -> int:
    """392: Gemma 候補数 / fire の上限 (default 2)。"""
    return _resolve_int_env(
        "X_POST_MAIL_GEMMA_GEN_MAX",
        2,
        min_value=0,
    )


def _fan_voice_enabled() -> bool:
    """397: env flag for fan_voice (参考) candidate.

    Default OFF。 ON 時のみ x-post-mail-evening (17:30) / postgame
    (22:30) 便で fan_voice candidate を append する。 flag OFF では
    既存挙動完全不変。
    """
    raw = (os.environ.get("X_POST_MAIL_FAN_VOICE_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _fan_voice_max_per_run() -> int:
    """397: fan_voice 候補数 / fire の上限 (default 2)。"""
    return _resolve_int_env(
        "X_POST_MAIL_FAN_VOICE_MAX",
        2,
        min_value=0,
    )


def _is_fan_voice_fire_window(now_jst: datetime) -> bool:
    """397: 試合時間帯 (= postgame 便相当) なら True。

    2026-05-20 user 方針更新: 試合中はファンツイートがまだ熟しておらず
    (= 試合開始直後の 17:30 evening は意味薄)、 試合がある程度進んだ
    19:00 以降のツイートに価値がある。 現スケジュール 5 便 (07:00 /
    12:00 / 15:00 / 17:30 / 22:30) のうち 19:00 以降は 22:30 postgame
    のみが該当する。

    手動 fire / cron drift を考慮し 19:00-23:59 を許容レンジ。
    朝 / 昼 / 午後 / 17:30 evening は False (= fan_voice 発動なし)。
    """
    if now_jst.tzinfo is None:
        return False
    minutes_since_midnight = now_jst.hour * 60 + now_jst.minute
    # 19:00 - 23:59 を試合進行〜試合直後 window とする
    return 19 * 60 <= minutes_since_midnight <= 23 * 60 + 59


def _resolve_int_env(name: str, default: int, *, min_value: int = 0) -> int:
    raw = (os.environ.get(name) or str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        LOG.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    if value < min_value:
        LOG.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    return value


def _resolve_news_priority_candidates(max_candidates: int) -> int:
    value = _resolve_int_env(
        "X_POST_MAIL_NEWS_PRIORITY_CANDIDATES",
        DEFAULT_NEWS_PRIORITY_CANDIDATES,
        min_value=0,
    )
    return max(0, min(value, max_candidates))


def _fetch_today_lineup_focus_names() -> list[str]:
    """Scrape today's Giants lineup and return canonical player names.

    Failure is a soft fallback: the X post mail still works from the
    existing data-ranking pool when lineup is not published yet or Yahoo
    changes markup.
    """
    if _lineup_focus_disabled():
        LOG.info("Lineup focus disabled by X_POST_MAIL_LINEUP_FOCUS_DISABLED")
        return []
    try:
        from src.rss_fetcher import fetch_today_giants_lineup_stats_from_yahoo
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Lineup focus import failed; continuing without focus: %r", exc)
        return []
    try:
        rows = fetch_today_giants_lineup_stats_from_yahoo()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Lineup focus fetch failed; continuing without focus: %r", exc)
        return []
    names = lane.focus_player_names_from_lineup_rows(rows)
    if names:
        LOG.info("Lineup focus enabled: %d players %s", len(names), names)
    else:
        LOG.info("Lineup focus unavailable: no lineup rows returned")
    return names


def _load_news_fallback_sources(path: Path = RSS_SOURCES_FILE) -> list[dict]:
    try:
        sources = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("news/opinion fallback source load failed: %r", exc)
        return []
    out: list[dict] = []
    for source in sources:
        source_type = str(source.get("type") or "")
        roles = source.get("role") or []
        if isinstance(roles, str):
            roles = [roles]
        if source_type not in {"news", "social_news", "tag_scrape"}:
            continue
        if source_type == "social_news" and "article_source" not in roles:
            continue
        if source_type == "tag_scrape" and roles and "article_source" not in roles:
            continue
        if source_type == "tag_scrape" and not str(source.get("scraper") or "").strip():
            continue
        url = str(source.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        out.append(source)
    return out


def _fetch_feed_entries(source: dict, *, timeout_seconds: int) -> list[dict]:
    if str(source.get("type") or "") == "tag_scrape":
        from src import tag_page_scraper

        article_limit = int(source.get("article_limit") or DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT)
        article_limit = max(1, min(article_limit, DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT))
        return tag_page_scraper.fetch_tag_page_entries(
            scraper=str(source.get("scraper") or ""),
            url=str(source.get("url") or ""),
            max_age_days=int(source.get("max_age_days") or 7),
            article_limit=article_limit,
            logger=LOG,
        )
    try:
        import feedparser
    except Exception as exc:  # noqa: BLE001
        LOG.warning("news/opinion fallback feedparser import failed: %r", exc)
        return []
    url = str(source.get("url") or "")
    req = urlrequest.Request(
        url,
        headers={
            "User-Agent": "yoshilover-x-post-mail/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            data = response.read()
    except (OSError, URLError) as exc:
        LOG.warning(
            "news/opinion fallback fetch failed source=%s url=%s error=%r",
            source.get("name"),
            url,
            exc,
        )
        return []
    parsed = feedparser.parse(data)
    return list(parsed.entries or [])


def _entry_text(entry: dict) -> tuple[str, str, str]:
    title = str(entry.get("title") or "").strip()
    link = str(entry.get("link") or entry.get("id") or "").strip()
    summary = str(
        entry.get("summary")
        or entry.get("description")
        or entry.get("subtitle")
        or ""
    ).strip()
    return title, link, summary


def _fetch_news_opinion_fallback_candidates(
    existing_candidates: list[lane.Candidate],
    *,
    max_candidates: int,
    now: datetime,
    recent_player_counts: dict[str, int] | None = None,
) -> list[lane.Candidate]:
    """Fill sparse data mails with source-backed news/opinion candidates.

    This fallback reads public RSS/Atom feeds only. It does not call WP,
    X API, LLMs, or the ``article_candidates`` table.
    """
    needed = max(0, max_candidates - len(existing_candidates))
    if needed <= 0:
        return []
    if _news_fallback_disabled():
        LOG.info("News/opinion fallback disabled by X_POST_MAIL_NEWS_FALLBACK_DISABLED")
        return []
    source_limit = _resolve_int_env(
        "X_POST_MAIL_NEWS_FALLBACK_SOURCE_LIMIT",
        DEFAULT_NEWS_FALLBACK_SOURCE_LIMIT,
        min_value=0,
    )
    entry_limit = _resolve_int_env(
        "X_POST_MAIL_NEWS_FALLBACK_ENTRY_LIMIT",
        DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT,
        min_value=1,
    )
    timeout_seconds = _resolve_int_env(
        "X_POST_MAIL_NEWS_FALLBACK_TIMEOUT_SECONDS",
        DEFAULT_NEWS_FALLBACK_TIMEOUT_SECONDS,
        min_value=1,
    )
    if source_limit <= 0:
        return []
    existing_player_keys = {
        lane._normalize_player_name(c.focus_player)
        for c in existing_candidates
        if lane._normalize_player_name(c.focus_player)
    }
    history_player_counts = {
        lane._normalize_player_name(name): int(count or 0)
        for name, count in (recent_player_counts or {}).items()
        if lane._normalize_player_name(name) and int(count or 0) > 0
    }
    history_player_keys = set(history_player_counts)
    seen_urls: set[str] = set()
    out: list[lane.Candidate] = []
    for source in _load_news_fallback_sources()[:source_limit]:
        if len(out) >= needed:
            break
        for entry in _fetch_feed_entries(source, timeout_seconds=timeout_seconds)[:entry_limit]:
            if len(out) >= needed:
                break
            title, link, summary = _entry_text(entry)
            if not title or not link or link in seen_urls:
                continue
            player = lane.detect_giants_player_name(f"{title} {summary}")
            player_key = lane._normalize_player_name(player)
            if not player_key or player_key in existing_player_keys:
                continue
            if player_key in history_player_keys:
                LOG.info(
                    "news_opinion_fallback_player_history_skip source=%s "
                    "player=%s previous_count=%d url=%s",
                    source.get("name"),
                    player,
                    history_player_counts.get(player_key, 0),
                    link,
                )
                continue
            cand = lane.build_news_opinion_candidate(
                source_title=title,
                source_url=link,
                source_excerpt=summary,
                source_name=str(source.get("name") or ""),
                player_name=player,
                now=now,
            )
            if cand is None:
                continue
            out.append(cand)
            seen_urls.add(link)
            existing_player_keys.add(player_key)
            LOG.info(
                "news_opinion_fallback_candidate_added source=%s player=%s url=%s",
                source.get("name"),
                player,
                link,
            )
    return out


def _build_fan_voice_candidates(
    existing_candidates: list[lane.Candidate],
    *,
    bucket_name: str,
    now: datetime,
    max_count: int,
    recent_player_counts: dict[str, int] | None = None,
    lookback_hours: int = 24,
) -> list[lane.Candidate]:
    """397: build 「(参考) 巨人ファン X 投稿」 candidates from GCS-cached
    fan_voice_pool entries (uploaded by yoshilover-fetcher).

    Filters:
    - tweet text length 20-280
    - text contains a verified Giants player name (NER via
      :func:`lane.detect_giants_player_name`)
    - URL not already present in another candidate of this mail
    - player not in 24h history (``recent_player_counts``)
    - player not already in current candidate list

    Returns up to ``max_count`` candidates, newest-first (by ``pub_iso``
    if available, else by ``ts``).
    """
    if max_count <= 0 or not bucket_name:
        return []
    try:
        entries = lane.load_recent_fan_voice_pool_entries(
            bucket_name,
            now,
            lookback_hours=lookback_hours,
        )
    except Exception as exc:  # noqa: BLE001 - silent skip per fan_voice contract
        LOG.warning("fan_voice load failed (silent skip): %r", exc)
        return []
    if not entries:
        LOG.info("fan_voice: 0 entries in GCS cache within last %dh", lookback_hours)
        return []
    # newest-first sort
    def _sort_key(rec: dict) -> str:
        return str(rec.get("pub_iso") or rec.get("ts") or "")
    entries = sorted(entries, key=_sort_key, reverse=True)

    existing_urls = {
        getattr(c, "signature", "") for c in existing_candidates
    }
    existing_player_keys = {
        lane._normalize_player_name(c.focus_player)
        for c in existing_candidates
        if lane._normalize_player_name(c.focus_player)
    }
    history_player_keys = {
        lane._normalize_player_name(name)
        for name, count in (recent_player_counts or {}).items()
        if lane._normalize_player_name(name) and int(count or 0) > 0
    }
    out: list[lane.Candidate] = []
    seen_handles: set[str] = set()
    for entry in entries:
        if len(out) >= max_count:
            break
        text = str(entry.get("text") or "").strip()
        url = str(entry.get("url") or "").strip()
        handle = str(entry.get("handle") or "").strip()
        if not text or not url:
            continue
        # diversity: at most 1 candidate per handle within one mail
        if handle and handle in seen_handles:
            LOG.info(
                "fan_voice_skip reason=handle_diversity handle=%s url=%s",
                handle, url,
            )
            continue
        player = lane.detect_giants_player_name(text)
        player_key = lane._normalize_player_name(player)
        if not player_key:
            LOG.info("fan_voice_skip reason=no_giants_player_in_text url=%s", url)
            continue
        if player_key in existing_player_keys:
            LOG.info(
                "fan_voice_skip reason=player_in_current_mail player=%s url=%s",
                player, url,
            )
            continue
        if player_key in history_player_keys:
            LOG.info(
                "fan_voice_skip reason=player_in_24h_history player=%s url=%s",
                player, url,
            )
            continue
        cand = lane.build_fan_voice_candidate(entry, detected_player=player)
        if cand is None:
            continue
        if cand.signature in existing_urls:
            continue
        out.append(cand)
        existing_player_keys.add(player_key)
        if handle:
            seen_handles.add(handle)
        LOG.info(
            "fan_voice_candidate_added handle=%s player=%s url=%s",
            handle, player, url,
        )
    LOG.info("fan_voice: built %d candidates (max=%d)", len(out), max_count)
    return out


def _backfill_dedup_starved_candidates(
    candidates: list[lane.Candidate],
    relaxed_candidates: list[lane.Candidate],
    *,
    max_candidates: int,
    recent_player_counts: dict[str, int] | None = None,
    min_candidates: int = 0,
) -> list[lane.Candidate]:
    """Keep fresh dedup-safe candidates first, then fill with relaxed ones.

    The 24h dedup gate is useful while there are enough alternative
    combos. When it leaves the mail nearly empty, the operator loses the
    actual review queue, so duplicate suppression must become a soft
    preference instead of a hard skip.

    397: player-level dedup を 2 段で適用する。
    Stage A: signature dedup + player dedup ON (24h history と current mail
    の両方を見て同一 player をスキップ)。これで浦田連発を抑止する。
    Stage B: Stage A 終了後の candidate 数が ``min_candidates`` 未満で
    残りに player_dedup_skipped 候補が残っているなら、最後の手段として
    signature dedup だけ守って詰め直す。これは mail が「ほぼ空」に
    なるよりは構造的 top player を再採用する方を優先する保険である。
    Stage B のしきい値は caller の ``min_candidates`` (= dedup_min_candidates
    と同じ意図、default 0 = Stage B 無効) で制御する。
    """
    merged = list(candidates)
    seen_signatures = {c.signature for c in merged if c.signature}
    history_player_keys = {
        lane._normalize_player_name(name)
        for name, count in (recent_player_counts or {}).items()
        if lane._normalize_player_name(name) and int(count or 0) > 0
    }
    seen_player_keys = {
        lane._normalize_player_name(c.focus_player)
        for c in merged
        if lane._normalize_player_name(c.focus_player)
    }
    player_dedup_skipped: list[lane.Candidate] = []
    for cand in relaxed_candidates:
        if len(merged) >= max_candidates:
            break
        if cand.signature and cand.signature in seen_signatures:
            continue
        cand_key = lane._normalize_player_name(cand.focus_player)
        if cand_key and (cand_key in seen_player_keys or cand_key in history_player_keys):
            LOG.info(
                "dedup_fallback_player_skip metric=%s period=%s player=%s reason=%s",
                cand.metric,
                cand.period_label,
                cand.focus_player,
                "in_current_mail" if cand_key in seen_player_keys else "in_24h_history",
            )
            player_dedup_skipped.append(cand)
            continue
        merged.append(cand)
        if cand.signature:
            seen_signatures.add(cand.signature)
        if cand_key:
            seen_player_keys.add(cand_key)
    if (
        min_candidates > 0
        and len(merged) < min_candidates
        and player_dedup_skipped
    ):
        for cand in player_dedup_skipped:
            if len(merged) >= max_candidates:
                break
            if cand.signature and cand.signature in seen_signatures:
                continue
            LOG.warning(
                "dedup_fallback_player_skip_overridden metric=%s period=%s player=%s "
                "(mail would otherwise be too sparse: %d < %d)",
                cand.metric,
                cand.period_label,
                cand.focus_player,
                len(merged),
                min_candidates,
            )
            merged.append(cand)
            if cand.signature:
                seen_signatures.add(cand.signature)
            if len(merged) >= min_candidates:
                # Stage B fills up to min_candidates only; do not blow past.
                break
    return merged


def _candidate_identity(candidate: lane.Candidate) -> str:
    if candidate.signature:
        return candidate.signature
    return "|".join(
        [
            str(candidate.metric or ""),
            str(candidate.period_label or ""),
            str(candidate.title or ""),
        ]
    )


def _resolve_gemma_api_keys() -> tuple[str, str]:
    """392: env var から Gemini / Tavily API key を読む。

    Cloud Run Job では Secret Manager binding 経由で ``GEMINI_API_KEY`` と
    ``TAVILY_API_KEY`` が env として渡る前提。 未設定なら空文字を返し、
    caller (Gemma builder) が None 返却で silent skip する。
    """
    gemini = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    )
    tavily = os.environ.get("TAVILY_API_KEY") or ""
    return gemini, tavily


def _pick_gemma_branding_players(
    existing_candidates: list[lane.Candidate],
    *,
    lineup_focus_names: list[str] | None,
    recent_player_counts: dict[str, int] | None,
    max_count: int,
) -> list[tuple[str, str]]:
    """392: Gemma 生成対象の player を最大 max_count 件選ぶ。

    優先順位:
        1. lineup focus names (今日のスタメン): まだ既存 candidates に居ない player
        2. 既存 candidates の focus_player で db_fact_line を持つもの
        3. 既存 candidates の focus_player (DB fact line 空でも)
        4. 既存 candidates から取れない場合は giants_roster default を使わず空返却

    返り値: ``(player_name, db_fact_line)`` の tuple list。
    """
    if max_count <= 0:
        return []
    history = {k: v for k, v in (recent_player_counts or {}).items() if v}
    seen_keys: set[str] = set()
    picks: list[tuple[str, str]] = []

    def _add(name: str, fact: str) -> None:
        nonlocal picks, seen_keys
        if len(picks) >= max_count:
            return
        n = str(name or "").strip()
        if not n:
            return
        key = lane._normalize_player_name(n)
        if not key or key in seen_keys:
            return
        if history.get(key, 0) >= 3:
            # 24h で 3 回以上既出は skip (既存 player diversity 思想継承)
            return
        seen_keys.add(key)
        picks.append((n, fact))

    # 1. lineup focus (今日のスタメン)
    for name in (lineup_focus_names or []):
        _add(name, "")
    # 2-3. 既存 candidates から (db_fact_line 持ち優先)
    candidates_with_fact = [c for c in existing_candidates if (c.db_fact_line or "").strip()]
    candidates_without_fact = [c for c in existing_candidates if not (c.db_fact_line or "").strip()]
    for cand in candidates_with_fact + candidates_without_fact:
        _add(cand.focus_player, cand.db_fact_line or "")
    return picks


def _build_gemma_branding_candidates(
    existing_candidates: list[lane.Candidate],
    *,
    lineup_focus_names: list[str] | None,
    recent_player_counts: dict[str, int] | None,
    max_count: int,
    db_path: str | None = None,
    bucket_name: str | None = None,
) -> list[lane.Candidate]:
    """392: max_count 件まで Gemma branding candidate を生成。

    silent skip 設計: 例外 / Tavily 失敗 / Gemma 失敗 / validator drop で
    None 返却された分は単に出力 list から除外。 既存 mail は止めない。

    db_path が渡された場合、 player ごとに ``build_db_fact_line()`` で
    insight.db の今日試合 / player log / 直近連勝 を fact line に整形し、
    Gemma 入力 prompt に注入する (RAG hallucination 抑制)。 DB 該当 record
    が無ければ空 string、 caller fact (lineup pick の補助 fact) を fallback。
    """
    if _xbg is None:
        LOG.info(
            "Gemma branding skipped: src.x_post_branding_gen import failed at module load"
        )
        return []
    gemini_key, tavily_key = _resolve_gemma_api_keys()
    if not gemini_key or not tavily_key:
        LOG.warning(
            "Gemma branding skipped: missing API key (gemini=%s tavily=%s)",
            bool(gemini_key),
            bool(tavily_key),
        )
        return []
    players = _pick_gemma_branding_players(
        existing_candidates,
        lineup_focus_names=lineup_focus_names,
        recent_player_counts=recent_player_counts,
        max_count=max_count,
    )
    if not players:
        LOG.info("Gemma branding skipped: no eligible players from lineup/candidates")
        return []
    out: list[lane.Candidate] = []

    # 試合 in DB + 勝利時は roundup mode を 1 件 priority で fire (時間帯
    # 問わず)。 朝 fire でも前夜の勝利 game が DB にあれば roundup 出せる。
    # roundup fact line が空 (no game / loss / draw) なら single-player のみ。
    # 今日試合が DB に無ければ昨日も試す (朝 fire で前夜試合を拾うため)。
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    roundup_added = False
    roundup_fact = ""
    if db_path:
        for offset in (0, 1):
            target_date = (now_jst - timedelta(days=offset)).strftime("%Y-%m-%d")
            try:
                rf = _xbg.build_team_roundup_fact_line(db_path, target_date=target_date)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("build_team_roundup_fact_line failed err=%r", exc)
                rf = ""
            if rf:
                roundup_fact = rf
                LOG.info("roundup fact found at offset=%d (date=%s)", offset, target_date)
                break
        if roundup_fact:
            try:
                rc = _xbg.build_team_roundup_candidate(
                    roundup_fact,
                    gemini_api_key=gemini_key,
                    tavily_api_key=tavily_key,
                    logger=LOG,
                )
            except Exception as exc:  # noqa: BLE001
                LOG.warning("build_team_roundup_candidate failed err=%r", exc)
                rc = None
            if rc is not None:
                out.append(rc)
                roundup_added = True
                LOG.info("Gemma roundup candidate appended (postgame win)")

    # roundup が出た時は残り枠 = max_count - 1、 出てない時は max_count 全部 single-player
    remaining = max_count - (1 if roundup_added else 0)
    if remaining <= 0:
        return out
    # 414 axis E7 wire: fan_voice_pool から直近 24h の 1 件を snippet として注入
    # (試合前 prompt themes に組み込まれる、 fault-tolerant)
    fan_voice_snippet = ""
    if bucket_name:
        try:
            entries = lane.load_recent_fan_voice_pool_entries(
                bucket_name, now_jst, lookback_hours=24
            )
            if entries:
                top = entries[0]
                text_preview = str(top.get("text") or "").strip()[:120]
                handle = str(top.get("handle") or "").strip()
                if text_preview:
                    fan_voice_snippet = (
                        f"@{handle}: {text_preview}" if handle else text_preview
                    )
        except Exception as exc:  # noqa: BLE001
            LOG.info("fan_voice_snippet_skip reason=%r", exc)

    # 414 axis E1 wire: Yahoo schedule で今日の先発を fetch、 axis E6 用 opponent
    # 先発も同時に取得 (build_pregame_themes に渡して相手投手相性 SQL 集計に活用)
    starting_pitcher_today = ""
    opponent_starter = ""
    try:
        from src.analysis.pregame_themes import fetch_today_starting_pitchers
        starting_pitcher_today, opponent_starter, _ = fetch_today_starting_pitchers()
    except Exception as exc:  # noqa: BLE001
        LOG.info("starting_pitcher_fetch_skip reason=%r", exc)

    # 414 axis E4 + E5 wire: 日次 snapshot 経由で打順変更 / 昇格 diff を計算。
    # 今日の値を save (翌日 fire の前日 snapshot として使う) + 前日 snapshot から
    # build summary を返す。 bucket_name 不在時は silent fallback (空文字)。
    lineup_change_summary = ""
    promotion_summary = ""
    if bucket_name:
        try:
            from src.analysis.daily_snapshot import (
                build_lineup_change_string,
                build_promotion_string,
                save_lineup_snapshot,
                save_roster_active_snapshot,
            )
            today_str = now_jst.strftime("%Y-%m-%d")
            if lineup_focus_names:
                lineup_change_summary = build_lineup_change_string(
                    bucket_name,
                    list(lineup_focus_names),
                    now_jst=now_jst,
                    logger=LOG,
                )
                save_lineup_snapshot(
                    bucket_name, today_str, list(lineup_focus_names), logger=LOG
                )
            try:
                roster_path = Path(__file__).resolve().parent.parent.parent / "config" / "giants_roster.json"
                roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
                today_active = [
                    str(p.get("name") or "").strip()
                    for p in roster_data
                    if p.get("active") and p.get("role") == "player"
                ]
                today_active_set = {n for n in today_active if n}
                if today_active_set:
                    promotion_summary = build_promotion_string(
                        bucket_name, today_active_set, now_jst=now_jst, logger=LOG
                    )
                    save_roster_active_snapshot(
                        bucket_name, today_str, list(today_active_set), logger=LOG
                    )
            except Exception as roster_exc:  # noqa: BLE001
                LOG.info("roster_snapshot_skip reason=%r", roster_exc)
        except Exception as snap_exc:  # noqa: BLE001
            LOG.info("daily_snapshot_skip reason=%r", snap_exc)
    for player, lineup_fact in players[:remaining]:
        db_fact = ""
        if db_path:
            try:
                db_fact = _xbg.build_db_fact_line(player, db_path)
            except Exception as exc:  # noqa: BLE001 - silent skip per fault-tolerance contract
                LOG.warning(
                    "build_db_fact_line failed (player=%s err=%r); falling back to lineup fact",
                    player,
                    exc,
                )
                db_fact = ""
        fact = db_fact or lineup_fact
        # 414 axis E wire: focused_players (= 今日のスタメン focus name list) と
        # fan_voice_snippet を pass、 build_gemma_branding_candidate が
        # build_pregame_themes に転送して prompt 注入する。
        cand = _xbg.build_gemma_branding_candidate(
            player,
            gemini_api_key=gemini_key,
            tavily_api_key=tavily_key,
            db_fact_line=fact,
            logger=LOG,
            db_path=db_path or "",
            focused_players=list(lineup_focus_names) if lineup_focus_names else None,
            fan_voice_snippet=fan_voice_snippet,
            starting_pitcher_today=starting_pitcher_today,
            opponent_pitcher_canonical=opponent_starter,
            lineup_change_summary=lineup_change_summary,
            promotion_summary=promotion_summary,
        )
        if cand is not None:
            out.append(cand)
    return out


def _build_comment_numeric_priority(
    news_candidates: list[lane.Candidate],
    data_candidates: list[lane.Candidate],
) -> tuple[list[lane.Candidate], set[str], set[str]]:
    combined: list[lane.Candidate] = []
    consumed_news: set[str] = set()
    consumed_data: set[str] = set()
    for news_candidate in news_candidates:
        news_id = _candidate_identity(news_candidate)
        news_player = lane._normalize_player_name(news_candidate.focus_player)
        if not news_player:
            continue
        for data_candidate in data_candidates:
            data_id = _candidate_identity(data_candidate)
            if data_id in consumed_data:
                continue
            if lane._normalize_player_name(data_candidate.focus_player) != news_player:
                continue
            comment_db = lane.build_comment_numeric_candidate(
                news_candidate,
                data_candidate,
            )
            if comment_db is None:
                continue
            combined.append(comment_db)
            consumed_news.add(news_id)
            consumed_data.add(data_id)
            break
    return combined, consumed_news, consumed_data


def _merge_news_priority_candidates(
    news_candidates: list[lane.Candidate],
    data_candidates: list[lane.Candidate],
    *,
    max_candidates: int,
) -> list[lane.Candidate]:
    """Put source-backed news/comment candidates first, then DB data.

    This keeps the mail schedule and UI unchanged while shifting the
    content from repeated metric-only candidates toward RSS/comment
    hooks. Player diversity is enforced first; if that would leave the
    mail short, DB candidates may backfill as a second pass.
    """
    merged: list[lane.Candidate] = []
    seen_identities: set[str] = set()
    used_players: set[str] = set()
    comment_db_candidates, consumed_news, consumed_data = _build_comment_numeric_priority(
        news_candidates,
        data_candidates,
    )

    def add(candidate: lane.Candidate, *, enforce_player: bool) -> bool:
        if len(merged) >= max_candidates:
            return False
        identity = _candidate_identity(candidate)
        if identity in seen_identities:
            return False
        player_key = lane._normalize_player_name(candidate.focus_player)
        if enforce_player and player_key and player_key in used_players:
            return False
        merged.append(candidate)
        seen_identities.add(identity)
        if player_key:
            used_players.add(player_key)
        return True

    for candidate in comment_db_candidates:
        add(candidate, enforce_player=True)
    for candidate in news_candidates:
        if _candidate_identity(candidate) in consumed_news:
            continue
        add(candidate, enforce_player=True)
    for candidate in data_candidates:
        if _candidate_identity(candidate) in consumed_data:
            continue
        add(candidate, enforce_player=True)
    for candidate in data_candidates:
        if _candidate_identity(candidate) in consumed_data:
            continue
        add(candidate, enforce_player=False)
    return merged[:max_candidates]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one セ・リーグ X post candidate mail (347).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compose mail and log it but do not call SMTP.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Maximum candidates to include (default 10).",
    )
    parser.add_argument(
        "--to",
        help="Override recipients (comma-separated). Defaults to MAIL_BRIDGE_TO env.",
    )
    parser.add_argument(
        "--min-sample",
        type=int,
        default=30,
        help="Minimum AB/IP/opps sample size for ranking inclusion (default 30, 350: tightened from 10).",
    )
    parser.add_argument(
        "--mode",
        choices=("scheduled", "on-queue"),
        default="scheduled",
        help=(
            "scheduled (default) = existing 5 便 flow (insight ranking + Gemma/fan_voice). "
            "on-queue (417) = drain x_post_candidate_queue (報知/サンスポ source) + Gemma 4 で 候補生成 + mail。"
        ),
    )
    return parser.parse_args(argv)


def _main_on_queue(args: argparse.Namespace, recipients: list[str]) -> int:
    """417: drain x_post_candidate_queue → Gemma 4 で候補生成 → mail.

    queue 0 件なら silent skip (mail を送らない、 return 0)。
    Gemma 候補生成失敗 (safety_check / unverified) は個別 skip、 1 件でも候補が
    残れば mail compose、 全件 skip なら mail 送らない。
    mail 送信成功時のみ mark_processed (失敗時は次 fire で再 drain)。
    """
    LOG.info("on-queue mode: starting queue flush flow")
    try:
        from src import x_post_candidate_queue as _xpcq
    except Exception as exc:  # noqa: BLE001
        LOG.error("on-queue mode: x_post_candidate_queue import failed err=%r", exc)
        return 5
    if _xbg is None:
        LOG.error("on-queue mode: x_post_branding_gen unavailable (392 deps missing)")
        return 5

    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
    if not gemini_key:
        LOG.error("on-queue mode: GEMINI_API_KEY env missing")
        return 5

    # 417 follow-up (RPM safety): drain max を args.max_candidates に絞る (= 10)。
    # 旧 max_count = max_candidates * 3 (= 30) だと filter で skip された item も
    # Gemma call は走るため、 1 fire で 30 call → 15 RPM 上限超過 risk。 cap=10 で
    # 1 fire 最大 10 call、 ~30 sec、 < 15 RPM 安全圏。
    queue_items = _xpcq.drain(max_count=args.max_candidates)
    if not queue_items:
        LOG.info("on-queue mode: queue is empty — silent skip (no mail sent)")
        return 0
    LOG.info("on-queue mode: drained %d queue items", len(queue_items))

    # db_path (DB fact line は使わないが、 persona 自動選択 (is_giants_game_day)
    # のために必要。 利用不可なら None で渡す = persona は時刻ベース fallback)
    db_path: str | None = None
    try:
        db_info = miq.ensure_local_db()
        if db_info.get("ok"):
            db_path = db_info.get("path")
    except Exception as exc:  # noqa: BLE001
        LOG.info("on-queue mode: insight.db unavailable (persona fallback): %r", exc)

    candidates: list[lane.Candidate] = []
    processed_items: list = []
    for item in queue_items:
        try:
            cand = _xbg.build_x_post_from_article_info(
                item,
                gemini_api_key=gemini_key,
                db_path=db_path or "",
                logger=LOG,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning(
                "on-queue mode: build_x_post_from_article_info exception source_url=%s err=%r",
                item.source_url,
                exc,
            )
            cand = None
        if cand is None:
            # silent skip — gate hit / no player / API error
            # NOTE: do NOT mark_processed; let it stay queued for next fire retry.
            # (rss_fetcher dedup will prevent re-enqueue of same source_url.)
            continue
        candidates.append(cand)
        processed_items.append(item)
        if len(candidates) >= args.max_candidates:
            break

    if not candidates:
        LOG.info(
            "on-queue mode: drained %d items but all produced 0 candidates (gate hit / no player) — skip mail",
            len(queue_items),
        )
        return 0

    LOG.info(
        "on-queue mode: composing mail with %d candidates (drained %d)",
        len(candidates),
        len(queue_items),
    )
    mail = lane.compose_mail(
        candidates,
        context_label="報知/サンスポ 直結 (queue 417)",
        context_note="",
    )

    if args.dry_run:
        LOG.info("[dry-run on-queue] subject=%s", mail.subject)
        LOG.info("[dry-run on-queue] candidate count=%d", mail.candidate_count)
        LOG.info(
            "[dry-run on-queue] text body preview (first 600 chars):\n%s",
            mail.text_body[:600],
        )
        # dry-run でも mark_processed しない (次回も同じ queue を見れるように)
        return 0

    LOG.info("on-queue mode: sending mail to %s …", recipients)
    request = mdb.MailRequest(
        to=recipients,
        subject=mail.subject,
        text_body=mail.text_body,
        html_body=mail.html_body,
        sender=_resolve_sender(),
        reply_to=_resolve_reply_to(),
        metadata={"ticket": "417", "lane": "x_post_mail", "mode": "on-queue", "candidate_count": mail.candidate_count},
    )
    result = mdb.send(request, dry_run=False)
    LOG.info(
        "on-queue mode: mail send result status=%s reason=%s refused=%s",
        result.status,
        result.reason,
        result.refused_recipients,
    )
    if result.status not in {"sent", "dry_run"}:
        LOG.error("on-queue mode: mail not sent (status=%s) — keep queue items for retry", result.status)
        return 4

    # mail 送信成功 → 該当 queue items を mark_processed
    marked = 0
    for item in processed_items:
        if _xpcq.mark_processed(item):
            marked += 1
    LOG.info("on-queue mode: mark_processed %d / %d items", marked, len(processed_items))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)

    recipients = _resolve_recipients(args.to)
    if not recipients and not args.dry_run:
        LOG.error("No recipients configured (MAIL_BRIDGE_TO env or --to). Aborting.")
        return 2

    # 417: on-queue mode は別 entry — drain queue → Gemma → mail の完結 flow。
    if args.mode == "on-queue":
        return _main_on_queue(args, recipients)

    LOG.info("Downloading insight.db cache (read-only)…")
    db_path: str | None = None
    try:
        db_info = miq.ensure_local_db()
        if db_info.get("ok"):
            db_path = db_info.get("path")
    except Exception as exc:  # noqa: BLE001
        LOG.exception("ensure_local_db failed: %r", exc)
        return 3
    now_jst = datetime.now(ZoneInfo("Asia/Tokyo"))
    if not db_path:
        LOG.error("insight.db cache unavailable: %s", db_info)
        return 3
    latest_game_date = lane.query_db_latest_game_date(db_path)
    staleness_days = lane.db_staleness_days(latest_game_date, now=now_jst)
    max_staleness_days = _resolve_max_db_staleness_days()
    LOG.info(
        "insight.db freshness latest_game_date=%s staleness_days=%s max=%d path=%s",
        latest_game_date,
        staleness_days,
        max_staleness_days,
        db_path,
    )
    if max_staleness_days >= 0 and (
        staleness_days is None or staleness_days > max_staleness_days
    ):
        LOG.error(
            "insight.db stale; aborting mail latest_game_date=%s staleness_days=%s max=%d",
            latest_game_date,
            staleness_days,
            max_staleness_days,
        )
        return 4

    # 355: load 24h dedup set so combos already mailed in the past day
    # do not repeat. Disabled when ``X_POST_MAIL_DEDUP_DISABLED=1`` or
    # bucket env missing. GCS errors are logged and treated as empty
    # state (= dedup off for this run, mail still sends).
    dedup_set: set[str] | None = None
    recent_player_counts: dict[str, int] = {}
    bucket_name = os.environ.get("INSIGHT_GCS_BUCKET") or ""
    dedup_disabled = (os.environ.get("X_POST_MAIL_DEDUP_DISABLED") or "").strip()
    if bucket_name and dedup_disabled not in {"1", "true", "yes"}:
        try:
            dedup_records = lane._load_recent_dedup_records(bucket_name, now_jst)
            dedup_set = {
                str(rec.get("signature") or "")
                for rec in dedup_records
                if str(rec.get("signature") or "")
            }
            LOG.info("Loaded 24h dedup set: %d signatures", len(dedup_set))
            recent_player_counts = lane._player_counts_from_dedup_records(dedup_records)
            LOG.info(
                "Loaded 24h player history: %d players, %d appearances",
                len(recent_player_counts),
                sum(recent_player_counts.values()),
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("dedup load failed (continuing without dedup): %r", exc)
            dedup_set = set()
            recent_player_counts = {}
    else:
        LOG.info("Dedup disabled (bucket=%s, disabled_env=%s)",
                 bool(bucket_name), dedup_disabled)

    LOG.info("Picking candidates (max=%d, min_sample=%d, db_path=%s, dedup=%s)…",
             args.max_candidates, args.min_sample, bool(db_path),
             len(dedup_set) if dedup_set is not None else "off")
    lineup_focus_names = _fetch_today_lineup_focus_names()
    context_label = "今日のスタメン" if lineup_focus_names else ""
    candidates = lane.pick_candidates(
        miq.query_rank,
        now=now_jst,
        max_candidates=args.max_candidates,
        min_sample=args.min_sample,
        db_path=db_path,
        dedup_set=dedup_set,
        focus_player_names=lineup_focus_names,
        context_label=context_label,
        recent_player_counts=recent_player_counts,
    )
    if lineup_focus_names and len(candidates) < _resolve_lineup_focus_min_candidates():
        LOG.warning(
            "Lineup focus produced only %d candidates; retrying without lineup "
            "focus so the scheduled mail does not disappear entirely.",
            len(candidates),
        )
        candidates = lane.pick_candidates(
            miq.query_rank,
            now=now_jst,
            max_candidates=args.max_candidates,
            min_sample=args.min_sample,
            db_path=db_path,
            dedup_set=dedup_set,
            recent_player_counts=recent_player_counts,
        )
        context_label = ""
    dedup_min_candidates = _resolve_dedup_min_candidates()
    if dedup_set is not None and len(candidates) < dedup_min_candidates:
        LOG.warning(
            "24h dedup left only %d candidates (<%d); retrying without dedup "
            "to avoid starving scheduled mail.",
            len(candidates),
            dedup_min_candidates,
        )
        relaxed_candidates = lane.pick_candidates(
            miq.query_rank,
            now=now_jst,
            max_candidates=args.max_candidates,
            min_sample=args.min_sample,
            db_path=db_path,
            dedup_set=None,
            focus_player_names=lineup_focus_names if context_label else None,
            context_label=context_label,
            recent_player_counts=recent_player_counts,
        )
        backfilled = _backfill_dedup_starved_candidates(
            candidates,
            relaxed_candidates,
            max_candidates=args.max_candidates,
            recent_player_counts=recent_player_counts,
            min_candidates=dedup_min_candidates,
        )
        if len(backfilled) > len(candidates):
            LOG.info(
                "Dedup fallback backfilled candidates: %d -> %d",
                len(candidates),
                len(backfilled),
            )
            candidates = backfilled
        else:
            LOG.info(
                "Dedup fallback found no additional candidates (relaxed=%d)",
                len(relaxed_candidates),
            )
    # 392: flag ON 時は news_opinion fallback (template) を skip し、 Gemma 4
    # + Tavily REST で branding candidate を 1-3 件生成して append する。
    # flag OFF (default) では既存挙動を 100% 維持 (rollback 余地)。
    gemma_enabled = _gemma_branding_enabled()
    if gemma_enabled:
        gemma_count = _gemma_branding_max_per_run()
        if gemma_count > 0:
            gemma_candidates = _build_gemma_branding_candidates(
                candidates,
                lineup_focus_names=lineup_focus_names,
                recent_player_counts=recent_player_counts,
                max_count=gemma_count,
                db_path=db_path,
                bucket_name=bucket_name or None,
            )
            if gemma_candidates:
                before = len(candidates)
                candidates = candidates + gemma_candidates
                LOG.info(
                    "Gemma branding appended: data=%d gemma=%d total=%d",
                    before,
                    len(gemma_candidates),
                    len(candidates),
                )
            else:
                LOG.info(
                    "Gemma branding produced 0 candidates "
                    "(silent skip on Tavily / Gemini errors or validator drops)."
                )
        # flag ON ルートでは template-based news_opinion fallback を呼ばない
        news_fallback_enabled = False
        fallback_candidates: list[lane.Candidate] = []
    else:
        news_fallback_enabled = not _news_fallback_disabled()
        fallback_candidates = []
    news_priority_count = _resolve_news_priority_candidates(args.max_candidates)
    if not news_fallback_enabled and not gemma_enabled:
        LOG.info("News/opinion fallback disabled by X_POST_MAIL_NEWS_FALLBACK_DISABLED")
    if news_fallback_enabled and news_priority_count:
        fallback_candidates = _fetch_news_opinion_fallback_candidates(
            [],
            max_candidates=news_priority_count,
            now=now_jst,
            recent_player_counts=recent_player_counts,
        )
        if fallback_candidates:
            before = len(candidates)
            candidates = _merge_news_priority_candidates(
                fallback_candidates,
                candidates,
                max_candidates=args.max_candidates,
            )
            LOG.info(
                "News/opinion priority merged candidates: data=%d news=%d total=%d",
                before,
                len(fallback_candidates),
                len(candidates),
            )
    if (
        news_fallback_enabled
        and not fallback_candidates
        and len(candidates) < args.max_candidates
    ):
        fallback_candidates = _fetch_news_opinion_fallback_candidates(
            candidates,
            max_candidates=args.max_candidates,
            now=now_jst,
            recent_player_counts=recent_player_counts,
        )
        if fallback_candidates:
            before = len(candidates)
            candidates = candidates + fallback_candidates
            LOG.info(
                "News/opinion fallback filled candidates: %d -> %d",
                before,
                len(candidates),
            )
    # 397: fan_voice (参考) candidate append。
    # X_POST_MAIL_FAN_VOICE_ENABLED=1 で ON、 evening (17:30) / postgame
    # (22:30) 便 (= _is_fan_voice_fire_window) でのみ append。 朝 / 昼 /
    # 午後便には出さない (試合時間帯のファン熱を mail に届けるため)。
    # flag OFF or 試合時間帯外なら完全 skip (no-op、 既存挙動不変)。
    if _fan_voice_enabled() and _is_fan_voice_fire_window(now_jst):
        fan_voice_max = _fan_voice_max_per_run()
        if fan_voice_max > 0 and bucket_name:
            remaining_slots = max(0, args.max_candidates - len(candidates))
            fan_voice_count = min(fan_voice_max, remaining_slots)
            if fan_voice_count > 0:
                fan_voice_candidates = _build_fan_voice_candidates(
                    candidates,
                    bucket_name=bucket_name,
                    now=now_jst,
                    max_count=fan_voice_count,
                    recent_player_counts=recent_player_counts,
                )
                if fan_voice_candidates:
                    before = len(candidates)
                    candidates = candidates + fan_voice_candidates
                    LOG.info(
                        "fan_voice appended: data=%d fan_voice=%d total=%d",
                        before,
                        len(fan_voice_candidates),
                        len(candidates),
                    )
                else:
                    LOG.info(
                        "fan_voice produced 0 candidates "
                        "(empty GCS cache / NER mismatch / dedup)."
                    )
            else:
                LOG.info(
                    "fan_voice skip: mail already full (candidates=%d, max=%d)",
                    len(candidates),
                    args.max_candidates,
                )
    elif _fan_voice_enabled():
        LOG.info(
            "fan_voice skip: not in fire window (now=%s, allowed 17:00-23:30 JST)",
            now_jst.strftime("%H:%M"),
        )

    if not candidates and recent_player_counts:
        LOG.warning(
            "Player history left 0 candidates after news/opinion fallback; "
            "retrying without player history to avoid starving scheduled mail.",
        )
        relaxed_history_candidates = lane.pick_candidates(
            miq.query_rank,
            now=now_jst,
            max_candidates=args.max_candidates,
            min_sample=args.min_sample,
            db_path=db_path,
            dedup_set=None,
            focus_player_names=lineup_focus_names if context_label else None,
            context_label=context_label,
            recent_player_counts={},
        )
        if relaxed_history_candidates:
            candidates = _backfill_dedup_starved_candidates(
                candidates,
                relaxed_history_candidates,
                max_candidates=args.max_candidates,
            )
            LOG.info(
                "Player history fallback backfilled candidates: 0 -> %d",
                len(candidates),
            )
    if not candidates:
        LOG.warning("No candidates generated — skip send (insight.db likely sparse).")
        return 0

    LOG.info("Composing mail with %d candidates…", len(candidates))
    context_note = ""
    if context_label and lineup_focus_names:
        context_note = "今日のスタメン優先: " + "、".join(lineup_focus_names)
    mail = lane.compose_mail(
        candidates,
        context_label=context_label,
        context_note=context_note,
    )

    if args.dry_run:
        LOG.info("[dry-run] subject=%s", mail.subject)
        LOG.info("[dry-run] candidate count=%d", mail.candidate_count)
        LOG.info("[dry-run] text body preview (first 600 chars):\n%s",
                 mail.text_body[:600])
        return 0

    LOG.info("Sending mail to %s …", recipients)
    request = mdb.MailRequest(
        to=recipients,
        subject=mail.subject,
        text_body=mail.text_body,
        html_body=mail.html_body,
        sender=_resolve_sender(),
        reply_to=_resolve_reply_to(),
        metadata={"ticket": "347", "lane": "x_post_mail", "candidate_count": mail.candidate_count},
    )
    result = mdb.send(request, dry_run=False)
    LOG.info("mail send result: status=%s reason=%s refused=%s",
             result.status, result.reason, result.refused_recipients)
    if result.status not in {"sent", "dry_run"}:
        LOG.error("mail send not sent (status=%s) — exit non-zero", result.status)
        return 4
    # 355: record the signatures of the candidates we just shipped so
    # subsequent runs (within 24h) can dedup them. Only runs when the
    # dedup feature is enabled (bucket env present + not opted-out).
    if (
        dedup_set is not None
        and bucket_name
        and result.status == "sent"
    ):
        signatures = [c.signature for c in candidates if c.signature]
        if signatures:
            signed_candidates = [c for c in candidates if c.signature]
            ok = lane._record_dedup_signatures(
                bucket_name,
                signatures,
                now_jst,
                focus_players=[c.focus_player for c in signed_candidates],
                metrics=[c.metric for c in signed_candidates],
                period_labels=[c.period_label for c in signed_candidates],
            )
            LOG.info("Recorded %d dedup signatures (ok=%s)",
                     len(signatures), ok)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
