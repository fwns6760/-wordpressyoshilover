"""Cloud Run Job entrypoint: 今日のX投稿候補を毎朝メール送信(449 §5 準自動B)。

GCS から insight.db を pull(read-only)→ daily_x_candidates.generate() で候補生成 →
mail_delivery_bridge で SMTP 送信。投稿はしない・WP書き込みなし・LLM/Gemini なし・
X API なし。WP REST は read-only GET(昇格/抹消候補のタイトル取得)のみ。

env:
  - GOOGLE_CLOUD_PROJECT / INSIGHT_GCS_BUCKET (insight.db pull)
  - WP_URL / WP_USER / WP_APP_PASSWORD (read-only GET、無ければ一軍候補のみ)
  - DAILY_X_CANDIDATES_MAIL_TO or MAIL_BRIDGE_TO (宛先)
  - MAIL_BRIDGE_* (SMTP、kobayashi mail lane と同設定)

実行: python -m src.tools.run_daily_x_candidates_mail [--dry-run]
Scheduler: 毎朝 1 fire(朝の data 反映後)。1 fire = 1 mail。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from src import mail_delivery_bridge as bridge
from src import data_site_query as dsq
from src.tools import daily_x_candidates as dxc

LOG = logging.getLogger("daily_x_candidates_mail")
JST = ZoneInfo("Asia/Tokyo")


def _resolve_recipients(arg_to: str | None) -> list[str]:
    raw = arg_to or os.environ.get("DAILY_X_CANDIDATES_MAIL_TO") \
        or os.environ.get("MAIL_BRIDGE_TO") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily X candidate mail (449 §5).")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--to", default=None)
    p.add_argument("--send-empty", action="store_true",
                   help="候補0でも送る(既定は0件なら送らない)")
    p.add_argument("--max-mails", type=int,
                   default=int(os.environ.get("DAILY_X_CANDIDATES_MAX_MAILS", "10")),
                   help="1通に詰める候補の最大件数(既定10)")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO,
    )
    args = _parse_args(argv)
    recipients = _resolve_recipients(args.to)
    if not recipients and not args.dry_run:
        LOG.error("No recipients (set DAILY_X_CANDIDATES_MAIL_TO or MAIL_BRIDGE_TO). Abort.")
        return 1

    now = datetime.now(JST)
    date_label = now.strftime("%Y-%m-%d")
    LOG.info("daily-x-candidates mail fire @ %s JST (dry=%s)",
             now.strftime("%Y-%m-%d %H:%M"), args.dry_run)

    # insight.db を GCS から local cache に pull(INSIGHT_GCS_BUCKET 使用)。
    path = dsq._ensure_insight_db_local()
    if path:
        os.environ["INSIGHT_DB_PATH"] = path
        LOG.info("insight.db ready: %s", path)
    else:
        LOG.warning("insight.db unavailable → 一軍候補 skip(昇格候補のみになる可能性)")

    result = dxc.generate()
    cands = dxc.flatten_candidates(result)
    LOG.info("candidates: news=%d hidden_hot=%d total=%d",
             len(result.get("news", [])), len(result.get("hidden_hot", [])), len(cands))

    if not cands and not args.send_empty:
        LOG.info("候補0件 → 送信せず exit 0(--send-empty で強制送信可)")
        return 0

    cands = cands[: args.max_mails]  # 1通に詰める件数上限
    subject, text_body, html_body = dxc.build_combined_mail(cands, date_label=date_label)

    if args.dry_run:
        print(f"--- DRY RUN: {subject} ({len(cands)}件 / 1通) ---")
        print(text_body[:2500])
        return 0

    request = bridge.MailRequest(
        to=recipients,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        metadata={"lane": "daily-x-candidates", "count": str(len(cands))},
    )
    res = bridge.send(request, dry_run=False)
    LOG.info("daily-x-candidates done: status=%s count=%d reason=%s",
             res.status, len(cands), res.reason)
    return 0 if res.status == "sent" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
