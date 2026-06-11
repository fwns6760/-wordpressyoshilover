"""Cloud Run Job entrypoint: X 投稿エンゲージ収集 + 週次レポート (効果学習 v0)。

modes:
* ``collect`` — RSSHub feed を 1 回取得し GCS へ upsert (¥0、LLM なし)
* ``report`` — 直近 7 日分のメトリクスを取得し週次レポートをメール送信
* ``auto`` — collect を実行し、JST 月曜なら report も実行 (scheduler 既定)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src import mail_delivery_bridge  # noqa: E402
from src import x_post_engagement as eng  # noqa: E402

LOG = logging.getLogger("x_post_engagement")


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
    return (
        os.environ.get("MAIL_BRIDGE_FROM")
        or os.environ.get("NOTIFY_FROM")
        or os.environ.get("MAIL_BRIDGE_SMTP_USERNAME")
        or None
    )


def _send_report_mail(text: str, *, recipients: list[str], dry_run: bool) -> str:
    report_date = datetime.now(timezone.utc).astimezone(eng.JST).strftime("%m/%d")
    request = mail_delivery_bridge.MailRequest(
        to=recipients,
        subject=f"【X効果学習】週次エンゲージレポート {report_date}",
        text_body=text,
        sender=_resolve_sender(),
        reply_to=os.environ.get("MAIL_BRIDGE_REPLY_TO") or None,
    )
    result = mail_delivery_bridge.send(request, dry_run=dry_run)
    LOG.info("x_engagement_mail status=%s reason=%s", result.status, result.reason)
    return result.status


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("collect", "report", "auto"), default="auto")
    parser.add_argument("--dry-run", action="store_true", help="メール送信せず本文を log に出す")
    parser.add_argument("--to", default=None, help="recipient override (comma separated)")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    is_monday_jst = now.astimezone(eng.JST).weekday() == 0

    if args.mode in ("collect", "auto"):
        stats = eng.collect(now_utc=now)
        LOG.info("x_engagement_collect_done %s", stats)

    want_report = args.mode == "report" or (args.mode == "auto" and is_monday_jst)
    if want_report:
        report, text = eng.run_weekly_report(now_utc=now, days=args.days)
        LOG.info(
            "x_engagement_report posts=%d favorites=%d replies=%d",
            report.total_posts,
            report.total_favorites,
            report.total_replies,
        )
        recipients = _resolve_recipients(args.to)
        if not recipients:
            LOG.warning("x_engagement_report no recipients; printing body only")
            print(text)
            return 0
        if args.dry_run:
            print(text)
        status = _send_report_mail(text, recipients=recipients, dry_run=args.dry_run)
        if status not in ("sent", "dry_run"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
