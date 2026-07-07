"""名言メール統合 dispatcher — 4 lane を 1 Cloud Run Job + 1 Scheduler で回す。

2026-07-02 user 決定 (Scheduler 費用効率化「坂本原小林吉川名言を一緒にするとか」):
旧 4 job / 4 scheduler を、JST 時刻で振り分ける本 dispatcher に統合する。

2026-07-07 user「あまり名言集のびない…あと時間かね」: インプ実測 (17-22時=47fav
vs 朝=8.7fav、坂本761fav回は18:12投稿) に合わせ、配信をゴールデン帯へ再配置。

- 12時: 小林 (毎日、昼帯は 23.6fav で維持)
- 17時: 吉川 (月水金) / 小林 (他曜日)
- 18時: 坂本 (毎日)
- 19時: 原 (毎日、旧 8時から移動)
- 20時: 小林 (毎日)

scheduler は 1 本: `0 12,17,18,19,20 * * *` (Asia/Tokyo)。
手動実行は `--lane=hara` などで時刻に関係なく指定できる。

小林 lane だけ送信アカウントが別 (y.sebata@shiny-lab.org + 専用 app password、
他 3 lane は mail-bridge-* secrets) のため、KOBA_* env を MAIL_BRIDGE_* へ
差し替えてから lane module を import する。lane module は import 時に env を
読むものがあるので、remap → import の順序を必ず守ること。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

JST = timezone(timedelta(hours=9))
LOG = logging.getLogger("meigen_mail_dispatch")

# 旧 scheduler `0 15 * * 1,3,5` (月水金) と同じ。Python weekday: 月=0 水=2 金=4。
_YOSHIKAWA_WEEKDAYS = frozenset({0, 2, 4})

_LANES = ("hara", "kobayashi", "yoshikawa", "sakamoto")

# 小林 lane 用の送信アカウント差し替え (KOBA_* → MAIL_BRIDGE_*)。
_KOBA_REMAP = (
    ("KOBA_SMTP_USERNAME", "MAIL_BRIDGE_SMTP_USERNAME"),
    ("KOBA_FROM", "MAIL_BRIDGE_FROM"),
    ("KOBA_GMAIL_APP_PASSWORD", "MAIL_BRIDGE_GMAIL_APP_PASSWORD"),
    ("KOBA_SMTP_HOST", "MAIL_BRIDGE_SMTP_HOST"),
    ("KOBA_SMTP_PORT", "MAIL_BRIDGE_SMTP_PORT"),
    ("KOBA_REPLY_TO", "MAIL_BRIDGE_REPLY_TO"),
)

# 旧 4 job の env 差分を lane 別に再現する (None = 未設定に戻す)。
# ENABLE_SHARE_X_BUTTON は旧 hara / yoshikawa job のみ 1 だった。
_LANE_ENV: dict[str, dict[str, Optional[str]]] = {
    "hara": {"ENABLE_SHARE_X_BUTTON": "1"},
    "yoshikawa": {"ENABLE_SHARE_X_BUTTON": "1"},
    "sakamoto": {"ENABLE_SHARE_X_BUTTON": None},
    "kobayashi": {"ENABLE_SHARE_X_BUTTON": None},
}


def pick_lane(now: datetime) -> Optional[str]:
    """JST 時刻から lane を決める。該当なし hour は None。

    2026-07-07: ゴールデン帯 (17-20時) 再配置。17時は 月水金=吉川、
    他曜日=小林 (吉川の配信頻度は旧 月水金 のまま維持)。"""
    h = now.hour
    if h == 12 or h == 20:
        return "kobayashi"
    if h == 17:
        return "yoshikawa" if now.weekday() in _YOSHIKAWA_WEEKDAYS else "kobayashi"
    if h == 18:
        return "sakamoto"
    if h == 19:
        return "hara"
    return None


def apply_lane_env(lane: str) -> None:
    for key, value in _LANE_ENV.get(lane, {}).items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    if lane == "kobayashi":
        for src, dst in _KOBA_REMAP:
            v = os.environ.get(src)
            if v:
                os.environ[dst] = v


def run_lane(lane: str, argv: Sequence[str]) -> int:
    apply_lane_env(lane)
    # env remap 後に import すること (lane module は import 時に env を読む)。
    if lane == "hara":
        from src.tools.run_hara_meigen_mail import main as lane_main
    elif lane == "kobayashi":
        from src.tools.run_kobayashi_meigen_mail import main as lane_main
    elif lane == "yoshikawa":
        from src.tools.run_yoshikawa_meigen_mail import main as lane_main
    elif lane == "sakamoto":
        from src.tools.run_sakamoto_meigen_mail import main as lane_main
    else:
        raise ValueError(f"unknown lane: {lane}")
    return lane_main(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="meigen mail dispatcher")
    parser.add_argument(
        "--lane", default=os.environ.get("MEIGEN_LANE", ""),
        choices=list(_LANES) + [""],
        help="手動実行時の lane 指定 (省略時は JST 時刻で自動判定)",
    )
    args, rest = parser.parse_known_args(argv)
    lane = args.lane or pick_lane(datetime.now(JST))
    if not lane:
        LOG.info("dispatch: no lane for this hour/weekday — no-op")
        return 0
    if not rest:
        rest = ["--n=1"]  # 旧 scheduler の既定と同じ (小林も default n=1 で等価)
    LOG.info("dispatch: lane=%s argv=%s", lane, rest)
    return run_lane(lane, rest)


if __name__ == "__main__":
    sys.exit(main())
