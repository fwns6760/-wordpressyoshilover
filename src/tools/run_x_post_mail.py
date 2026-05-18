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


LOG = logging.getLogger("x_post_mail")
DEFAULT_MAX_DB_STALENESS_DAYS = 2
DEFAULT_DEDUP_MIN_CANDIDATES = 3
DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES = 1
DEFAULT_NEWS_FALLBACK_SOURCE_LIMIT = 32
DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT = 5
DEFAULT_NEWS_FALLBACK_TIMEOUT_SECONDS = 4
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


def _backfill_dedup_starved_candidates(
    candidates: list[lane.Candidate],
    relaxed_candidates: list[lane.Candidate],
    *,
    max_candidates: int,
) -> list[lane.Candidate]:
    """Keep fresh dedup-safe candidates first, then fill with relaxed ones.

    The 24h dedup gate is useful while there are enough alternative
    combos. When it leaves the mail nearly empty, the operator loses the
    actual review queue, so duplicate suppression must become a soft
    preference instead of a hard skip.
    """
    merged = list(candidates)
    seen_signatures = {c.signature for c in merged if c.signature}
    for cand in relaxed_candidates:
        if len(merged) >= max_candidates:
            break
        if cand.signature and cand.signature in seen_signatures:
            continue
        merged.append(cand)
        if cand.signature:
            seen_signatures.add(cand.signature)
    return merged


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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)

    recipients = _resolve_recipients(args.to)
    if not recipients and not args.dry_run:
        LOG.error("No recipients configured (MAIL_BRIDGE_TO env or --to). Aborting.")
        return 2

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
    if len(candidates) < args.max_candidates:
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
