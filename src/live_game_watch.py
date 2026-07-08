"""巨人戦ライブ観戦 v0 — NPB 公式スコアページからイベントを検出する。

目的 (2026-07-08 user GO「フーガみたいな観戦中のポストが無い」):
  試合帯の x-post-mail 便 (15分毎) のたびに NPB 公式のライブスコアを 1 回見て、
  前回 snapshot からスコアが動いた時だけ「実況候補」の素材 (検証済み事実行) を返す。
  文章生成・Candidate 化は x_post_mail_lane 側 (既存の voice / 捏造ガードを通す)。

事実性:
  イベントの数字 (スコア・回・本塁打の号数) はすべて NPB 公式ページの表記だけを使う。
  取れなかった項目は書かない。推測で埋めない。

state:
  GCS `baseballsite-yoshilover-state/live_game_watch/{YYYYMMDD}.json` に前回 snapshot。
  同日内の便同士の差分だけを見る (日付が変われば新規)。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import requests

LOG = logging.getLogger("live_game_watch")

JST = timezone(timedelta(hours=9))
_SCORES_INDEX = "https://npb.jp/scores/{year}/{md}/"
_STATE_BUCKET_ENV = "X_POST_STATE_BUCKET"
_DEFAULT_STATE_BUCKET = "baseballsite-yoshilover-state"
_STATE_PREFIX = "live_game_watch"

# 巨人のチームコード (npb.jp の game path は "<away>-<home>-<n>")
_GIANTS_CODE = "g"
_TEAM_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_STATUS_RE = re.compile(r"(試合終了|試合中\s*(\d+)回(表|裏)|試合前)")
_HOMER_RE = re.compile(r"([\w぀-ヿ一-鿿・]+)\s*(\d+号（[^）]*）)")


@dataclass
class LiveGameState:
    date_key: str
    game_url: str
    status: str  # "試合中" / "試合終了" / "試合前"
    inning_label: str  # 例 "3回裏" (試合中のみ)
    giants_home: bool
    giants_score: int
    opp_score: int
    opp_name: str
    homer_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip(cell: str) -> str:
    return _TAG_RE.sub("", cell).replace("&nbsp;", "").strip()


def _find_giants_game_url(now: datetime) -> str:
    md = now.strftime("%m%d")
    url = _SCORES_INDEX.format(year=now.year, md=md)
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    for m in re.finditer(rf"/scores/{now.year}/{md}/([a-z]+)-([a-z]+)-\d+/", r.text):
        if _GIANTS_CODE in (m.group(1), m.group(2)):
            return "https://npb.jp" + m.group(0)
    return ""


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_live_page(html: str, *, game_url: str, date_key: str) -> Optional[LiveGameState]:
    st = _STATUS_RE.search(_TAG_RE.sub(" ", html))
    if not st:
        return None
    if st.group(1) == "試合終了":
        status, inning = "試合終了", ""
    elif st.group(1) == "試合前":
        status, inning = "試合前", ""
    else:
        status, inning = "試合中", f"{st.group(2)}回{st.group(3)}"

    # linescore: ヘッダ行 (1..9 計 H E) の直後 2 行が away / home
    rows: list[list[str]] = []
    for m in _TEAM_ROW_RE.finditer(html):
        cells = [_strip(c) for c in _CELL_RE.findall(m.group(1))]
        if len(cells) >= 12 and ("計" in cells or "R" in cells):
            continue  # ヘッダ
        if len(cells) >= 12 and cells[0]:
            rows.append(cells)
    if len(rows) < 2:
        return None
    away, home = rows[0], rows[1]

    def team_total(cells: list[str]) -> int:
        # 末尾 3 列 = 計 / H / E
        return _parse_int(cells[-3])

    giants_home = "巨人" in home[0] or "読売" in home[0]
    giants_row, opp_row = (home, away) if giants_home else (away, home)
    if "巨人" not in giants_row[0] and "読売" not in giants_row[0]:
        return None
    opp_name = re.sub(r"(タイガース|カープ|ドラゴンズ|ベイスターズ|スワローズ).*$", r"\1", opp_row[0])
    opp_name = opp_row[0][-2:] if not opp_name else opp_name

    homers = []
    text = _TAG_RE.sub(" ", html)
    for hm in _HOMER_RE.finditer(text):
        homers.append(f"{hm.group(1)} {hm.group(2)}")

    return LiveGameState(
        date_key=date_key,
        game_url=game_url,
        status=status,
        inning_label=inning,
        giants_home=giants_home,
        giants_score=team_total(giants_row),
        opp_score=team_total(opp_row),
        opp_name=opp_name,
        homer_lines=homers[:6],
    )


def fetch_today_live_game(now: Optional[datetime] = None) -> Optional[LiveGameState]:
    current = (now or datetime.now(JST)).astimezone(JST)
    date_key = current.strftime("%Y%m%d")
    try:
        game_url = _find_giants_game_url(current)
        if not game_url:
            return None
        r = requests.get(game_url, timeout=10)
        r.raise_for_status()
        return parse_live_page(r.text, game_url=game_url, date_key=date_key)
    except Exception as exc:  # noqa: BLE001 - lane は fail-open (候補なし)
        LOG.info("live_game_watch fetch failed: %r", exc)
        return None


def _state_blob(date_key: str):
    from google.cloud import storage

    bucket_name = os.environ.get(_STATE_BUCKET_ENV, _DEFAULT_STATE_BUCKET)
    return storage.Client().bucket(bucket_name).blob(f"{_STATE_PREFIX}/{date_key}.json")


def load_prev_state(date_key: str) -> Optional[dict[str, Any]]:
    try:
        return json.loads(_state_blob(date_key).download_as_text())
    except Exception:  # noqa: BLE001 - 初回 / 読めない時は差分なし扱い
        return None


def save_state(state: LiveGameState) -> None:
    try:
        _state_blob(state.date_key).upload_from_string(
            json.dumps(state.to_dict(), ensure_ascii=False), content_type="application/json"
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("live_game_watch state save failed: %r", exc)


def detect_events(prev: Optional[dict[str, Any]], cur: LiveGameState) -> list[dict[str, str]]:
    """前回 snapshot との差分イベント。優先順: 試合終了 > 逆転 > 巨人得点 > 失点。

    各 event: {"kind": ..., "fact": <NPB 公式表記だけで組んだ検証済み事実行>}
    prev が無い (便の初回) 時はイベントを出さない (途中経過の洪水防止)。
    """
    events: list[dict[str, str]] = []
    if cur.status == "試合前":
        return events
    score_line = f"巨人{cur.giants_score}-{cur.opp_score}{cur.opp_name}"
    new_homers = []
    if prev is not None:
        prev_homers = set(prev.get("homer_lines") or [])
        new_homers = [h for h in cur.homer_lines if h not in prev_homers]
    homer_note = ("。本塁打: " + " / ".join(new_homers)) if new_homers else ""

    if cur.status == "試合終了":
        if prev is None or prev.get("status") != "試合終了":
            outcome = "勝利" if cur.giants_score > cur.opp_score else (
                "敗戦" if cur.giants_score < cur.opp_score else "引き分け"
            )
            events.append({
                "kind": "game_end",
                "fact": f"試合終了。{score_line}で巨人の{outcome}{homer_note}",
            })
        return events[:2]

    if prev is None:
        return events

    pg, po = int(prev.get("giants_score") or 0), int(prev.get("opp_score") or 0)
    dg, do = cur.giants_score - pg, cur.opp_score - po
    where = f"{cur.inning_label}時点、" if cur.inning_label else ""
    prev_diff, cur_diff = pg - po, cur.giants_score - cur.opp_score
    if dg > 0 and prev_diff < 0 and cur_diff > 0:
        events.append({
            "kind": "lead_change",
            "fact": f"{where}巨人が{dg}点を取って逆転。{score_line}{homer_note}",
        })
    elif dg > 0:
        label = "先制" if po == 0 and pg == 0 else "追加点" if cur_diff > 0 else "反撃"
        events.append({
            "kind": "giants_score",
            "fact": f"{where}巨人が{dg}点の{label}。{score_line}{homer_note}",
        })
    if do > 0:
        events.append({
            "kind": "opp_score",
            "fact": f"{where}{cur.opp_name}に{do}点。{score_line}{homer_note}",
        })
    return events[:2]
