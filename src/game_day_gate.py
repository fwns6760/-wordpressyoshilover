"""試合日 gate — 試合帯 / スタメン帯の scheduler 便を実際の試合日程で間引く。

2026-07-02 user 決定「野球はない日は今日とか。月曜は確実にない。
土日は昼か夜か読めないし。そこをうまくやりたい」:

scheduler は広めに張り (lineup: 20,40 11-17時 / game: */15 13-21時)、
便の冒頭で NPB 公式月間日程から今日の巨人戦の有無と開始時刻を見て判定する。

- 試合なし (月曜・移動日等) → skip (数秒で終了、LLM 消費ゼロ)
- 開始時刻が取れた → lineup=[start-4h, start) / game=[start-15m, start+4h)
  のみ通す (デーゲームなら昼帯、ナイターなら夜帯に自動で寄る)
- 試合はあるが時刻不明 (終了済で score 表示に変わった等) や取得失敗
  → 従来のナイター決め打ち窓 (lineup 17-18時 / game 17:45-22時) に fail-open
"""

from __future__ import annotations

import logging
import re as _re
from datetime import datetime, timedelta
from typing import Callable, Optional

import requests

LOG = logging.getLogger("game_day_gate")

WINDOWS = ("lineup", "game")

# fail-open 時の従来窓 (旧 scheduler: lineup 17:20,17:40 / game */15 18-21)
_LEGACY_LINEUP = (17 * 60, 18 * 60)          # [17:00, 18:00)
_LEGACY_GAME = (17 * 60 + 45, 22 * 60)       # [17:45, 22:00)


def _fetch_month_html(now: datetime) -> str:
    url = f"https://npb.jp/games/{now.year}/schedule_{now.month:02d}_detail.html"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def _today_block_has_giants(html: str, today) -> bool:
    """今日の日付ブロックに巨人戦があるか (score 有無を問わない)。

    parse_giants_upcoming は未消化試合のみ返すため、終了済 (score 表示に
    変わった) 当日試合の検出用。日付ヘッダから次の日付ヘッダまでを切り出して
    team1/team2 に巨人がいるかを見る。
    """
    pat = _re.compile(r"(\d{1,2})/(\d{1,2})（[日月火水木金土]）")
    blocks = list(pat.finditer(html or ""))
    for i, m in enumerate(blocks):
        if int(m.group(1)) == today.month and int(m.group(2)) == today.day:
            end = blocks[i + 1].start() if i + 1 < len(blocks) else len(html)
            seg = html[m.start():end]
            for tm in _re.finditer(
                r'class="team[12]"[^>]*>(.*?)</[^>]+>', seg, _re.S
            ):
                if "巨人" in _re.sub(r"<[^>]+>", "", tm.group(1)):
                    return True
    return False


def find_today_game(html: str, now: datetime) -> Optional[dict]:
    """今日の巨人戦を {"start": datetime|None} で返す。試合なしは None。"""
    from src.data_site_query import parse_giants_upcoming

    today = now.date()
    try:
        rows = parse_giants_upcoming(html, today.year, today, limit=2)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("find_today_game parse err: %r", exc)
        rows = []
    if rows and rows[0].get("date") == today.isoformat():
        start = None
        tm = _re.match(r"^(\d{1,2}):(\d{2})$", (rows[0].get("time") or "").strip())
        if tm:
            start = now.replace(
                hour=int(tm.group(1)), minute=int(tm.group(2)),
                second=0, microsecond=0,
            )
        return {"start": start}
    if _today_block_has_giants(html, today):
        return {"start": None}  # 終了済等、時刻不明
    return None


def _minutes(now: datetime) -> int:
    return now.hour * 60 + now.minute


def evaluate(
    window: str,
    now: datetime,
    fetch_fn: Optional[Callable[[datetime], str]] = None,
) -> tuple[bool, str, Optional[datetime]]:
    """(通すか, 理由, 開始時刻|None) を返す。

    477: 開始時刻は caller (run_x_post_mail) がデイゲームの試合中モード窓を
    自動注入するのに使う。時刻不明 / 試合なし / fetch 失敗は None。
    """
    if window not in WINDOWS:
        return True, f"window={window!r} は gate 対象外", None
    try:
        html = (fetch_fn or _fetch_month_html)(now)
        game = find_today_game(html, now)
    except Exception as exc:  # noqa: BLE001
        game = {"start": None}
        LOG.warning("gate fetch err (fail-open legacy): %r", exc)
    if game is None:
        return False, "今日は巨人戦なし", None
    start = game.get("start")
    if start is None:
        lo, hi = _LEGACY_LINEUP if window == "lineup" else _LEGACY_GAME
        ok = lo <= _minutes(now) < hi
        return ok, f"時刻不明 → 従来窓 {'内' if ok else '外'}", None
    if window == "lineup":
        ok = start - timedelta(hours=4) <= now < start
        return ok, f"start={start:%H:%M} lineup窓{'内' if ok else '外'}", start
    ok = start - timedelta(minutes=15) <= now < start + timedelta(hours=4)
    return ok, f"start={start:%H:%M} game窓{'内' if ok else '外'}", start


def should_proceed(
    window: str,
    now: datetime,
    fetch_fn: Optional[Callable[[datetime], str]] = None,
) -> tuple[bool, str]:
    """(通すか, 理由) を返す。理由は log 用。後方互換 wrapper。"""
    ok, reason, _ = evaluate(window, now, fetch_fn=fetch_fn)
    return ok, reason
