"""Cloud Run Job entrypoint for YOSHILOVER Giants news candidate mail.

Safety contract:
  - collects title/media/url/published/category/reason metadata only
  - sends Gmail candidate mail for human selection
  - never creates article bodies
  - never mutates WordPress
  - never posts to X

Local review:
  python3 -m src.tools.run_yoshilover_news_candidates_mail --dry-run --print-body
"""

from __future__ import annotations

import argparse
from datetime import datetime
import logging
import os
from pathlib import Path
import sys
from typing import Sequence
from zoneinfo import ZoneInfo

from src import mail_delivery_bridge as bridge
from src.tools import yoshilover_news_candidates as ync


LOG = logging.getLogger("yoshilover_news_candidates_mail")
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_SOURCES = Path(__file__).resolve().parents[2] / "config" / "yoshilover_news_candidates.example.json"


def _configure_logging() -> None:
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _resolve_recipients(override: str | None) -> list[str]:
    raw = (
        override
        or os.environ.get("YOSHILOVER_NEWS_CANDIDATE_MAIL_TO")
        or os.environ.get("MAIL_BRIDGE_TO")
        or ""
    )
    return [part.strip() for part in raw.split(",") if part.strip()]


def _resolve_sender() -> str | None:
    return (
        os.environ.get("MAIL_BRIDGE_FROM")
        or os.environ.get("NOTIFY_FROM")
        or os.environ.get("MAIL_BRIDGE_SMTP_USERNAME")
        or None
    )


def _resolve_reply_to() -> str | None:
    return os.environ.get("MAIL_BRIDGE_REPLY_TO") or os.environ.get("NOTIFY_REPLY_TO")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YOSHILOVER 巨人ニュース候補メール。")
    parser.add_argument("--dry-run", action="store_true", help="メールを送らない")
    parser.add_argument("--to", default=None, help="送信先（カンマ区切り）")
    parser.add_argument("--sources", default=os.environ.get("YOSHILOVER_NEWS_CANDIDATE_SOURCES_FILE") or str(DEFAULT_SOURCES))
    parser.add_argument("--send-empty", action="store_true", help="候補0件でもメールを送る")
    parser.add_argument("--print-body", action="store_true", help="本文をstdoutに出す")
    parser.add_argument("--max-candidates", type=int, default=int(os.environ.get("YOSHILOVER_NEWS_MAX_CANDIDATES", "18")))
    parser.add_argument("--max-items-per-source", type=int, default=int(os.environ.get("YOSHILOVER_NEWS_MAX_ITEMS_PER_SOURCE", "8")))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.environ.get("YOSHILOVER_NEWS_TIMEOUT_SECONDS", "6")))
    parser.add_argument("--ledger-path", default=os.environ.get("YOSHILOVER_NEWS_CANDIDATE_LEDGER_PATH"))
    parser.add_argument("--ledger-gcs-uri", default=os.environ.get("YOSHILOVER_NEWS_CANDIDATE_LEDGER_GCS_URI"))
    parser.add_argument("--no-resolve-google-news", action="store_true", help="GoogleニュースURLを元記事URLに解決しない")
    parser.add_argument("--no-excluded", action="store_true", help="除外候補セクションを出さない")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)
    recipients = _resolve_recipients(args.to)
    if not recipients and not args.dry_run:
        LOG.error("No recipients (set YOSHILOVER_NEWS_CANDIDATE_MAIL_TO or MAIL_BRIDGE_TO). Abort.")
        return 2
    if not recipients:
        recipients = ["dry-run@example.test"]

    now = datetime.now(JST)
    LOG.info(
        "yoshilover-news-candidates fire @ %s JST dry=%s sources=%s",
        now.strftime("%Y-%m-%d %H:%M"),
        args.dry_run,
        args.sources,
    )
    result = ync.build_candidates(
        source_path=args.sources,
        now=now,
        timeout_seconds=max(1, args.timeout_seconds),
        max_items_per_source=max(1, args.max_items_per_source),
        max_candidates=max(1, args.max_candidates),
        ledger_path=args.ledger_path,
        gcs_ledger_uri=args.ledger_gcs_uri,
        resolve_google_news=not args.no_resolve_google_news,
        include_excluded=not args.no_excluded,
    )
    candidates = result.candidates
    counts: dict[str, int] = {}
    for cand in candidates:
        counts[cand.category] = counts.get(cand.category, 0) + 1
    LOG.info(
        "yoshilover_news_result candidates=%d counts=%s loaded=%d fetched=%d raw=%d stale=%d scored=%d deduped=%d",
        len(candidates),
        counts,
        result.stats.loaded_sources,
        result.stats.fetched_sources,
        result.stats.raw_items,
        result.stats.stale_items,
        result.stats.scored_items,
        result.stats.deduped_items,
    )
    if not candidates and not args.send_empty:
        LOG.info("candidate count is 0; skip mail")
        return 0

    subject, text_body, html_body = ync.compose_mail(candidates, now=now, stats=result.stats)
    if args.print_body or args.dry_run:
        print(f"--- {subject} ---")
        print(text_body[:8000])

    request = bridge.MailRequest(
        to=recipients,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        sender=_resolve_sender(),
        reply_to=_resolve_reply_to(),
        metadata={"lane": "yoshilover-news-candidates", "candidate_count": str(len(candidates))},
    )
    send_result = bridge.send(request, dry_run=args.dry_run)
    LOG.info(
        "yoshilover-news-candidates mail result: status=%s reason=%s refused=%s",
        send_result.status,
        send_result.reason,
        send_result.refused_recipients,
    )
    if send_result.status not in {"sent", "dry_run"}:
        return 4
    if send_result.status == "sent" and candidates:
        ync.append_ledger(
            candidates,
            now=now,
            ledger_path=args.ledger_path,
            gcs_uri=args.ledger_gcs_uri,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
