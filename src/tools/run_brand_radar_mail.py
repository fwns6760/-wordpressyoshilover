"""CLI entry for ticket 382 Yoshilover branding radar mail.

Default mode is dry-run. Pass ``--send`` to deliver mail through the
shared Gmail bridge. The lane never posts to X and never mutates WP.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import Sequence

if __package__ in {None, ""}:  # pragma: no cover
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src import brand_radar  # noqa: E402
from src import mail_delivery_bridge as mdb  # noqa: E402


LOG = logging.getLogger("brand_radar_mail")
RSS_SOURCES_FILE = Path(__file__).resolve().parents[2] / "config" / "rss_sources.json"


def _configure_logging() -> None:
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _resolve_recipients(override: str | None) -> list[str]:
    if override:
        return [item.strip() for item in override.split(",") if item.strip()]
    raw = os.environ.get("BRAND_RADAR_MAIL_TO") or os.environ.get("MAIL_BRIDGE_TO") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


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
    parser = argparse.ArgumentParser(
        description="Compose Yoshilover branding X post planning mail from fresh Giants news.",
    )
    parser.add_argument("--send", action="store_true", help="Send mail. Default is dry-run.")
    parser.add_argument("--to", help="Override recipients, comma-separated.")
    parser.add_argument("--sources", default=str(RSS_SOURCES_FILE), help="rss_sources.json path.")
    parser.add_argument("--max-plans", type=int, default=brand_radar.DEFAULT_MAX_TOPICS)
    parser.add_argument("--x-search-cap", type=int, default=brand_radar.DEFAULT_X_SEARCH_CAP)
    parser.add_argument("--source-limit", type=int, default=brand_radar.DEFAULT_SOURCE_LIMIT)
    parser.add_argument("--entry-limit", type=int, default=brand_radar.DEFAULT_ENTRY_LIMIT)
    parser.add_argument("--timeout-seconds", type=int, default=4)
    parser.add_argument(
        "--print-body",
        action="store_true",
        help="Print the composed text body to stdout (safe for dry-run review).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)
    recipients = _resolve_recipients(args.to)
    if args.send and not recipients:
        LOG.error("No recipients configured (BRAND_RADAR_MAIL_TO, MAIL_BRIDGE_TO, or --to).")
        return 2
    if not recipients:
        recipients = ["dry-run@example.test"]

    now = brand_radar.now_jst()
    sources = brand_radar.load_brand_sources(Path(args.sources))
    LOG.info("loaded brand sources: %d", len(sources))
    client = brand_radar.XAIResponsesXSearchClient()
    result = brand_radar.build_brand_radar(
        sources=sources,
        x_search_client=client,
        now=now,
        max_plans=max(1, args.max_plans),
        x_search_call_cap=max(0, args.x_search_cap),
        source_limit=max(0, args.source_limit),
        entry_limit=max(1, args.entry_limit),
        timeout_seconds=max(1, args.timeout_seconds),
    )
    mail = brand_radar.compose_brand_radar_mail(result.plans, now=now, stats=result.stats)
    LOG.info(
        "brand_radar_result candidates=%d x_search_calls_used=%d cap=%d provider_errors=%d skipped=%s",
        mail.candidate_count,
        result.stats.x_search_calls_used,
        result.stats.x_search_call_cap,
        result.stats.provider_error_count,
        result.stats.skipped_by_reason,
    )
    if args.print_body:
        print(mail.text_body)

    request = mdb.MailRequest(
        to=recipients,
        subject=mail.subject,
        text_body=mail.text_body,
        html_body=mail.html_body,
        sender=_resolve_sender(),
        reply_to=_resolve_reply_to(),
        metadata={
            "ticket": "382",
            "lane": "brand_radar",
            "candidate_count": mail.candidate_count,
            "x_search_calls_used": result.stats.x_search_calls_used,
            "x_search_call_cap": result.stats.x_search_call_cap,
        },
    )
    send_result = mdb.send(request, dry_run=not args.send)
    LOG.info(
        "mail result: status=%s reason=%s refused=%s",
        send_result.status,
        send_result.reason,
        send_result.refused_recipients,
    )
    if send_result.status not in {"sent", "dry_run"}:
        return 4
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
