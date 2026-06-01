"""data/schedule ページ template (日程・結果カレンダー、Phase B 452)。

games から巨人の日程・結果を月ごとにまとめ、モバイルファーストの1行1試合で表示。
勝=緑 / 負=灰 で視認性。SEO: 「巨人 試合結果 日程 2026」等。投稿でなく evergreen page。
"""

from __future__ import annotations

import html as _html
from typing import Optional

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"
SCHEDULE_SLUG = "data-schedule"


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


def render_schedule_title() -> str:
    return "巨人 試合日程・結果 2026【勝敗・スコア一覧】 | 巨人データ"


def render_schedule_excerpt(rows: list) -> str:
    n = len(rows)
    w = sum(1 for r in rows if getattr(r, "result", "") == "勝")
    l = sum(1 for r in rows if getattr(r, "result", "") == "負")
    return (f"読売ジャイアンツ2026の試合日程・結果一覧。直近{n}試合 {w}勝{l}敗、"
            "スコア・対戦相手・本拠地/ビジターを月別に。大手より見やすい巨人専用カレンダー。")


def _row_html(r) -> str:
    win = r.result == "勝"
    lose = r.result == "負"
    color = "#1b7f3b" if win else ("#888" if lose else "#b0860b")
    bg = "#eef7f0" if win else ("#f5f5f5" if lose else "#fcf7e8")
    score = (f"{r.giants_score}-{r.opp_score}"
             if r.giants_score is not None and r.opp_score is not None else "—")
    md = r.game_date[5:].replace("-", "/")
    return (
        f'<div class="ys-sch-row" style="display:flex;align-items:center;gap:8px;'
        f'padding:8px 10px;border-radius:6px;margin:0 0 6px;background:{bg};">'
        f'<span style="width:42px;color:#666;font-size:13px;">{_esc(md)}</span>'
        f'<span style="width:34px;text-align:center;font-weight:700;color:{color};">{_esc(r.result or "—")}</span>'
        f'<span style="width:64px;font-weight:600;">{_esc(score)}</span>'
        f'<span style="flex:1;font-size:13px;">{_esc(r.home_away)} vs {_esc(r.opponent)}</span>'
        '</div>'
    )


def _build_upcoming_card(upcoming: list) -> str:
    """今後の試合カード (459/C、 NPB公式日程 scrape)。"""
    if not upcoming:
        return ""
    rows = ""
    for u in upcoming:
        md = str(u.get("date", ""))[5:].replace("-", "/")
        starter = ""
        if u.get("starter_g"):
            starter = (f'<div style="font-size:12px;color:#e25400;margin:2px 0 0 50px;">'
                       f'予告先発: {_esc(u.get("starter_g"))} vs {_esc(u.get("starter_o"))}</div>')
        rows += (
            '<div style="padding:8px 10px;border-radius:6px;margin:0 0 6px;background:#fff8f2;">'
            '<div style="display:flex;align-items:center;gap:8px;">'
            f'<span style="width:42px;color:#666;font-size:13px;">{_esc(md)}</span>'
            f'<span style="width:46px;font-size:12px;color:#888;">{_esc(u.get("time"))}</span>'
            f'<span style="flex:1;font-size:13px;">{_esc(u.get("home_away"))} vs {_esc(u.get("opp"))}</span>'
            f'<span style="font-size:12px;color:#888;">{_esc(u.get("place"))}</span>'
            '</div>'
            f'{starter}'
            '</div>'
        )
    return (
        '<section class="ys-card" style="margin:0 0 16px;">'
        '<h2 style="font-size:16px;margin:0 0 8px;">📅 今後の試合 '
        '<span style="font-size:11px;color:#e25400;">毎日更新</span></h2>'
        f'{rows}'
        '<p style="font-size:11px;color:#999;margin:6px 0 0;">出典: NPB公式日程</p>'
        '</section>'
    )


def render_schedule_html(rows: list, upcoming: list = None) -> str:
    """日程・結果ページ本文。今後の試合(上) + 結果を月ごとにグルーピング(新しい月が上)。"""
    by_month: dict[str, list] = {}
    order: list[str] = []
    for r in rows:
        mk = r.game_date[:7]  # YYYY-MM
        if mk not in by_month:
            by_month[mk] = []
            order.append(mk)
        by_month[mk].append(r)
    blocks = []
    for mk in order:
        mlabel = f"{int(mk[5:7])}月"
        rs = by_month[mk]
        w = sum(1 for r in rs if r.result == "勝")
        l = sum(1 for r in rs if r.result == "負")
        rows_html = "".join(_row_html(r) for r in rs)
        blocks.append(
            '<section class="ys-card" style="margin:0 0 16px;">'
            f'<h2 style="font-size:16px;margin:0 0 8px;">{_esc(mlabel)} <span style="font-size:13px;color:#666;">({w}勝{l}敗)</span></h2>'
            f'{rows_html}</section>'
        )
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>試合日程・結果</span></nav>'
    )
    head = (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 試合日程・結果 2026</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;">勝=緑 / 負=灰。スコア・対戦相手・本拠地/ビジターを月別に。</p>'
    )
    upcoming_card = _build_upcoming_card(upcoming or [])
    body = "".join(blocks) if blocks else "<p>データ準備中</p>"
    back = f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
    return head + upcoming_card + body + back + "</div>"
