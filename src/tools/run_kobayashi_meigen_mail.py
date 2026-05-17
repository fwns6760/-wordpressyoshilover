"""377-ARCHIVE Phase 2: Cloud Run Job entrypoint for the 小林誠司 名言 mail lane.

GCS の archives/kobayashi_meigen/tweets.jsonl から N 件 (default 3) pick、
HTML mail で SMTP 送信、 sent_cursor.jsonl に append。 1 fire = 1 mail。

Cloud Scheduler から 12:00 / 17:00 / 20:00 JST に 3 fire。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from google.cloud import storage  # noqa: F401

from src import kobayashi_meigen_mail_lane as lane
from src import mail_delivery_bridge as bridge

LOG = logging.getLogger("kobayashi_meigen_mail")
JST = ZoneInfo("Asia/Tokyo")


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )


def _resolve_recipients(arg_to: str | None) -> list[str]:
    raw = arg_to or os.environ.get("KOBAYASHI_MEIGEN_MAIL_TO") \
        or os.environ.get("MAIL_BRIDGE_TO") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one 小林誠司 名言 mail (377-ARCHIVE Phase 2).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--n", type=int, default=1,
                        help="Tweets per mail (default 1)")
    parser.add_argument("--bucket", default=lane.DEFAULT_BUCKET)
    parser.add_argument("--archive-key", default=lane.ARCHIVE_KEY)
    parser.add_argument("--cursor-key", default=lane.CURSOR_KEY)
    parser.add_argument("--to", default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)
    recipients = _resolve_recipients(args.to)
    if not recipients and not args.dry_run:
        LOG.error("No recipients (set KOBAYASHI_MEIGEN_MAIL_TO or MAIL_BRIDGE_TO). Abort.")
        return 1

    now = datetime.now(JST)
    LOG.info("kobayashi-meigen mail fire @ %s JST (n=%d, dry=%s)",
             now.strftime("%Y-%m-%d %H:%M"), args.n, args.dry_run)

    gcs_client = storage.Client()
    bucket = gcs_client.bucket(args.bucket)

    records = lane.load_archive(bucket, archive_key=args.archive_key)
    LOG.info("Archive loaded: %d records", len(records))
    if not records:
        LOG.error("Archive empty, abort.")
        return 1

    sent_ids = lane.load_sent_cursor(bucket, cursor_key=args.cursor_key)
    LOG.info("Cursor loaded: %d sent so far", len(sent_ids))

    candidates = lane.pick_candidates(records, sent_ids=sent_ids, n=args.n)
    LOG.info("Picked %d candidates (oldest_first, unsent)", len(candidates))

    # 周回 loop: 1 周配信し切ったら cursor を消して oldest からまた回す。
    # archive 836 件 / 3 件/日 = 約 9 ヶ月で 1 周完了。
    if not candidates and len(sent_ids) >= len(records):
        LOG.info(
            "Cycle complete (sent=%d / archive=%d) — rotating cursor to start.",
            len(sent_ids), len(records),
        )
        try:
            bucket.blob(args.cursor_key).delete()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("cursor delete failed: %r", exc)
        sent_ids = set()
        candidates = lane.pick_candidates(records, sent_ids=sent_ids, n=args.n)
        LOG.info("Picked %d candidates (cycle restart, oldest_first)",
                 len(candidates))

    if not candidates:
        LOG.info("No unsent candidates remain — exit 0.")
        return 0

    mail = lane.compose_mail(candidates, now=now)
    LOG.info("Composed: subject=%r", mail.subject)

    if args.dry_run:
        print("--- DRY RUN TEXT ---")
        print(mail.text_body[:2000])
        return 0

    request = bridge.MailRequest(
        to=recipients,
        subject=mail.subject,
        text_body=mail.text_body,
        html_body=mail.html_body,
        metadata={"lane": "kobayashi-meigen", "n": str(len(candidates))},
    )
    LOG.info("Sending mail to %s ...", recipients)
    result = bridge.send(request, dry_run=False)
    LOG.info("mail send result: status=%s reason=%s refused=%s",
             result.status, result.reason, result.refused_recipients)
    if result.status != "sent":
        LOG.error("Mail send failed, abort cursor update.")
        return 2

    tweet_ids = [c.tweet_id for c in candidates]
    ok = lane.append_sent_cursor(
        bucket, sent_tweet_ids=tweet_ids, now=now, cursor_key=args.cursor_key,
    )
    LOG.info("Cursor updated: %s (ids=%d)", ok, len(tweet_ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
