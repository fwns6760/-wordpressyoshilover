"""data/injured page (巨人 怪我人・離脱選手 最新情報) — 2026-07-06 user GO。

「巨人 怪我人 最新」「◯◯ 抹消 いつ戻る」系の高頻度クエリ向け。
roster-moves と同じデータ (NPB 公示 scrape + baked json) から
「現在離脱中 (抹消日・経過日数・最短復帰可能日)」と「今季の離脱→復帰履歴」を
自動生成する。ライバル (my-favorite-giants の IL/DL) は手動更新のため、
毎朝の rotation-updater 自動更新で鮮度に構造的な差をつける。

注意: 公示は「登録抹消」の事実のみで理由 (怪我/調整) は含まない。
怪我と断定する表現は事実誤認リスクがあるため「離脱 (登録抹消)」表記に留める。
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass
from datetime import date, timedelta

from src.data_site_internal_link import linkify, load_slug_map

# NPB 規定: 出場選手登録を抹消された選手は 10 日間再登録できない。
# 報道慣例の「◯/◯ 以降復帰可能」= 抹消日 + 10 日で表記する。
REREGISTER_WAIT_DAYS = 10


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def _parse_md(md: str, year: int) -> date | None:
    try:
        m, d = str(md or "").strip().split("/", 1)
        return date(year, int(m), int(d))
    except Exception:  # noqa: BLE001
        return None


_ANNOT_RE = None  # set below (re import を局所化しない)
import re as _re  # noqa: E402

_ANNOT_RE = _re.compile(r"[（(]([^）)]*)[）)]")


def _split_annotation(raw: str) -> tuple[str, str]:
    """公示名の「泉口 友汰（脳振盪※）」→ (泉口 友汰, 脳振盪※)。

    注記付き抹消と注記なし再登録をペアリングするため、名前 key は注記を
    落として正規化する (2026-07-06 実データで泉口が離脱中に残る bug を確認)。
    """
    name = str(raw or "").strip()
    m = _ANNOT_RE.search(name)
    note = m.group(1).strip() if m else ""
    clean = _ANNOT_RE.sub("", name).strip()
    return clean, note


@dataclass
class InjuryRow:
    name: str
    out_date: date
    reg_date: date | None = None
    note: str = ""

    @property
    def days_out(self) -> int:
        return ((self.reg_date or date.today()) - self.out_date).days

    def earliest_return(self) -> date:
        return self.out_date + timedelta(days=REREGISTER_WAIT_DAYS)


def compute_injury_board(data: dict, today: date) -> dict:
    """roster_moves data → {year, current: [InjuryRow], history: [InjuryRow]}。

    - current = 最新の公示が「抹消」で、その後の再登録が無い選手
    - history = 今季すでに 抹消→再登録 が完結した離脱
    - 初登録のみ (reg だけ) の選手や公示に出ない選手は対象外
    """
    years = data.get("years") or []
    if not years:
        return {"year": None, "current": [], "history": []}
    latest = years[0]
    year = int(latest.get("year") or today.year)
    events: dict[str, list[tuple[date, str, str]]] = {}
    for mv in latest.get("moves") or []:
        d = _parse_md(mv.get("date"), year)
        if not d or d > today:
            continue
        for n in mv.get("out") or []:
            clean, note = _split_annotation(n)
            if clean:
                events.setdefault(clean, []).append((d, "out", note))
        for n in mv.get("reg") or []:
            clean, note = _split_annotation(n)
            if clean:
                events.setdefault(clean, []).append((d, "reg", note))
    current: list[InjuryRow] = []
    history: list[InjuryRow] = []
    for name, evs in events.items():
        evs.sort(key=lambda e: (e[0], e[1]))
        open_out: date | None = None
        open_note = ""
        for d, kind, note in evs:
            if kind == "out":
                open_out = d
                open_note = note
            elif kind == "reg" and open_out is not None:
                history.append(InjuryRow(name=name, out_date=open_out, reg_date=d, note=open_note))
                open_out = None
                open_note = ""
        if open_out is not None:
            current.append(InjuryRow(name=name, out_date=open_out, note=open_note))
    current.sort(key=lambda r: r.out_date)
    history.sort(key=lambda r: r.reg_date or today, reverse=True)
    return {"year": year, "current": current, "history": history}


def _fmt_md(d: date | None) -> str:
    return f"{d.month}/{d.day}" if d else "-"


def render_injured_title(board: dict) -> str:
    year = board.get("year") or ""
    return f"巨人 離脱選手・登録抹消 最新情報【{year}年 復帰予定つき】 | 巨人データ"


def render_injured_excerpt(board: dict) -> str:
    n = len(board.get("current") or [])
    return (
        f"読売ジャイアンツの現在の離脱選手（登録抹消中 {n}人）を、抹消日・経過日数・"
        "最短復帰可能日つきで毎日自動更新。今季の離脱→復帰の履歴も一覧化した巨人データです。"
    )


def render_injured_html(board: dict, today: date) -> str:
    slug_map = load_slug_map()
    current = board.get("current") or []
    history = board.get("history") or []
    year = board.get("year") or today.year
    parts: list[str] = [
        '<p style="font-size:13px;color:#5d4037;">'
        f"NPB 公示（出場選手登録・抹消）をもとに毎朝自動更新。基準日: {today.year}年{today.month}月{today.day}日。"
        "公示は登録抹消の事実のみで、理由（怪我・調整など）は含まれません。</p>"
    ]
    parts.append(f'<h2 style="font-size:17px;">🏥 現在の離脱選手（登録抹消中 {len(current)}人）</h2>')
    if current:
        rows = "".join(
            "<tr>"
            f"<td>{linkify(r.name, slug_map)}</td>"
            f"<td>{_fmt_md(r.out_date)}</td>"
            f"<td>{r.days_out}日</td>"
            f"<td>{_fmt_md(r.earliest_return())} 以降</td>"
            f"<td>{_esc(r.note) or '-'}</td>"
            "</tr>"
            for r in current
        )
        parts.append(
            "<table><thead><tr>"
            "<th>選手</th><th>抹消日</th><th>経過</th><th>最短復帰</th><th>公示注記</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
            '<p style="font-size:12px;color:#57606a;">※ 最短復帰 = 抹消日から'
            f"{REREGISTER_WAIT_DAYS}日後（NPB 規定で抹消後{REREGISTER_WAIT_DAYS}日間は再登録不可）。"
            "実際の復帰日はチーム状況によります。</p>"
        )
    else:
        parts.append(f"<p>現在、今季（{year}年）の公示ベースで登録抹消中の選手はいません。</p>")
    if history:
        rows = "".join(
            "<tr>"
            f"<td>{linkify(r.name, slug_map)}</td>"
            f"<td>{_fmt_md(r.out_date)} 〜 {_fmt_md(r.reg_date)}</td>"
            f"<td>{r.days_out}日</td>"
            "</tr>"
            for r in history
        )
        parts.append(
            f'<h2 style="font-size:17px;">✅ 今季の離脱→復帰 履歴（{len(history)}件）</h2>'
            "<table><thead><tr>"
            "<th>選手</th><th>離脱期間</th><th>日数</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    parts.append(
        '<p style="margin-top:16px;">📋 登録・抹消の全公示は '
        '<a href="/data/roster-moves">出場選手登録・抹消の一覧</a>、'
        '選手の状態は各選手ページの直近成績をご覧ください。</p>'
    )
    return "\n".join(parts)
