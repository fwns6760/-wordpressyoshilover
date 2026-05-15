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
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src import manual_intake_insight_query as miq  # noqa: E402
from src import mail_delivery_bridge as mdb  # noqa: E402
from src import x_post_mail_lane as lane  # noqa: E402


LOG = logging.getLogger("x_post_mail")


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

    # 355: load 24h dedup set so combos already mailed in the past day
    # do not repeat. Disabled when ``X_POST_MAIL_DEDUP_DISABLED=1`` or
    # bucket env missing. GCS errors silently return empty set
    # (= dedup off for this run, mail still sends).
    dedup_set: set[str] | None = None
    bucket_name = os.environ.get("INSIGHT_GCS_BUCKET") or ""
    dedup_disabled = (os.environ.get("X_POST_MAIL_DEDUP_DISABLED") or "").strip()
    now_jst = datetime.now(ZoneInfo("Asia/Tokyo"))
    if bucket_name and dedup_disabled not in {"1", "true", "yes"}:
        try:
            dedup_set = lane._load_recent_dedup_signatures(bucket_name, now_jst)
            LOG.info("Loaded 24h dedup set: %d signatures", len(dedup_set))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("dedup load failed (continuing without dedup): %r", exc)
            dedup_set = set()
    else:
        LOG.info("Dedup disabled (bucket=%s, disabled_env=%s)",
                 bool(bucket_name), dedup_disabled)

    LOG.info("Picking candidates (max=%d, min_sample=%d, db_path=%s, dedup=%s)…",
             args.max_candidates, args.min_sample, bool(db_path),
             len(dedup_set) if dedup_set is not None else "off")
    candidates = lane.pick_candidates(
        miq.query_rank,
        now=now_jst,
        max_candidates=args.max_candidates,
        min_sample=args.min_sample,
        db_path=db_path,
        dedup_set=dedup_set,
    )
    if not candidates:
        LOG.warning("No candidates generated — skip send (insight.db likely sparse).")
        return 0

    LOG.info("Composing mail with %d candidates…", len(candidates))
    mail = lane.compose_mail(candidates)

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
            ok = lane._record_dedup_signatures(bucket_name, signatures, now_jst)
            LOG.info("Recorded %d dedup signatures (ok=%s)",
                     len(signatures), ok)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
