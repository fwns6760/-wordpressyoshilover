"""RELIABILITY-2026-05-08-PING: Cloud Run 独立 daily ping job

yoshilover の fetcher / publish-notice path とは別の Cloud Run Job として動く独立
監視。1 日 1 回 mail を送るだけのシンプル job。yoshilover 本物 mail と独立に届く
ことで「mail 経路自体は生きてる」signal を user の Gmail に直接届ける。

mail パターンによる切り分け:
  - 本物 (heartbeat + per-post) ✓ + ping ✓ : 全部健全
  - 本物 ✗ + ping ✓                   : yoshilover 側 (fetcher / publish-notice) の障害
  - 本物 ✓ + ping ✗                   : ping job の問題 (限定的、本物が来てるなら一旦保留)
  - 本物 ✗ + ping ✗                   : external infra (Cloud Run / Scheduler / Gmail SMTP)
                                          全停止、user 緊急対応必須

本 job は existing mail_bridge env (MAIL_BRIDGE_*) を共有する。完全独立を求めるなら
別 SMTP credentials (例: user 個人 Gmail) を後日 user 作業で分離する。
"""

from __future__ import annotations

import os
import smtplib
import sys
import traceback
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

JST = timezone(timedelta(hours=9))


def _get_env(name: str, *, required: bool = True) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value and required:
        raise RuntimeError(f"required env {name} is not set")
    return value


def _build_mail_body(now_jst: datetime) -> str:
    return (
        f"{now_jst.strftime('%Y-%m-%d %H:%M:%S JST')}\n\n"
        "これは Cloud Run 独立 ping job (external-ping) からの daily 監視 mail です。\n"
        "yoshilover の fetcher / publish-notice path とは別の image / 別の Cloud Run\n"
        "Job / 別の scheduler 経路で送信されます。\n\n"
        "切り分け:\n"
        "  ✓ このメール届く + 本物 mail (heartbeat/per-post) も届く → 全健全\n"
        "  ✓ このメール届く + 本物 mail 届かない → yoshilover 内部 (fetcher/publish-notice) 障害\n"
        "  ✗ このメール届かない (and 本物も来ない) → external infra 全停止、緊急対応\n\n"
        "本 ping は単純な mail 送信のみで yoshilover 本物 path とは独立。\n"
        "観察 doc: /home/fwns6/code/wordpressyoshilover/doc/active/MORNING-VERIFY-2026-05-09.md\n"
    )


def main() -> int:
    now_jst = datetime.now(JST)
    try:
        smtp_host = _get_env("MAIL_BRIDGE_SMTP_HOST")
        smtp_port = int(_get_env("MAIL_BRIDGE_SMTP_PORT"))
        smtp_username = _get_env("MAIL_BRIDGE_SMTP_USERNAME")
        smtp_password = _get_env("MAIL_BRIDGE_GMAIL_APP_PASSWORD")
        mail_from = _get_env("MAIL_BRIDGE_FROM")
        mail_to = _get_env("MAIL_BRIDGE_TO")
    except Exception as exc:  # noqa: BLE001
        print(f"external_ping_env_missing: {exc}", file=sys.stderr)
        return 1

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = f"【外部監視】{now_jst:%Y-%m-%d %H:%M} yoshilover external ping"
    msg.set_content(_build_mail_body(now_jst))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        print(
            f"external_ping_smtp_failed at={now_jst.isoformat()} reason={exc}",
            file=sys.stderr,
        )
        traceback.print_exc()
        return 1

    print(
        f"external_ping_sent at={now_jst.isoformat()} to={mail_to} from={mail_from}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
