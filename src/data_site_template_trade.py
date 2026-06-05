"""data/trade ページ template（巨人トレード/入退団 hub）。

ベンチ: my-favorite-giants.net/giants_data/trading/ の change.htm（交換トレード）/ all.htm（入退団一覧）。
データ正本は config/giants_trades.json（事実のみ）。

セクション:
  1. 交換トレード一覧（選手⇔選手のトレード）
  2. 入団・移籍・退団一覧（FA移籍 / 自由契約 / 戦力外 / 現役ドラフト / トレード 等の全動き）
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"

_DATA_PATH = _os.path.join(_os.path.dirname(__file__), "..", "config", "giants_trades.json")


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_trade_data() -> dict:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _cell(v) -> str:
    s = _esc(v).strip()
    return s if s else "—"


def _players_html(players) -> str:
    if not players:
        return "—"
    out = []
    for p in players:
        nm = _esc(p.get("name"))
        pos = _esc(p.get("pos"))
        out.append(f'<strong>{nm}</strong>'
                   + (f'<span style="color:#999;font-size:11px;">（{pos}）</span>' if pos else ""))
    return "<br>".join(out)


def _table(headers, rows) -> str:
    if not rows:
        return ""
    th = "".join(f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #5d4037;'
                 f'font-size:12px;color:#5d4037;white-space:nowrap;">{_esc(h)}</th>' for h in headers)
    trs = []
    for i, r in enumerate(rows):
        bg = "#fff" if i % 2 == 0 else "#fcf9f4"
        tds = "".join(f'<td style="padding:6px 8px;border-bottom:1px solid #eee;font-size:13px;'
                      f'vertical-align:top;">{c}</td>' for c in r)
        trs.append(f'<tr style="background:{bg};">{tds}</tr>')
    return ('<div style="overflow-x:auto;margin:0 0 8px;"><table style="border-collapse:collapse;'
            'width:100%;min-width:560px;">'
            f'<thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>')


def _section_shell(anchor, title, lead, body_html, count) -> str:
    cnt = (f'<span style="font-size:12px;color:#888;font-weight:normal;">{count}件</span>'
           if count else '<span style="font-size:12px;color:#bbb;font-weight:normal;">準備中</span>')
    return (f'<h2 id="{anchor}" style="font-size:17px;margin:26px 0 6px;border-left:4px solid #5d4037;'
            f'padding-left:8px;">{_esc(title)} {cnt}</h2>'
            f'<p style="font-size:12px;color:#777;margin:0 0 8px;">{_esc(lead)}</p>{body_html}')


def _todo_box(msg: str) -> str:
    return ('<div style="background:#fafafa;border:1px dashed #ccc;border-radius:4px;'
            'padding:14px 16px;color:#999;font-size:13px;margin:0 0 8px;">🚧 ' + _esc(msg) + '</div>')


def _render_exchange(entries) -> str:
    if not entries:
        return _todo_box("交換トレードを整備中です。")
    rows = [[
        _cell(e.get("date")),
        _players_html(e.get("in_players")),
        _cell(e.get("partner")),
        _players_html(e.get("out_players")),
        _cell(e.get("note")),
    ] for e in entries]
    return _table(["成立日", "獲得選手", "相手球団", "放出選手", "備考"], rows)


def _render_all(entries) -> str:
    if not entries:
        return _todo_box("入退団一覧を整備中です。")
    rows = [[
        _cell(e.get("date")),
        _players_html(e.get("in_players")),
        _cell(e.get("partner")),
        _players_html(e.get("out_players")),
        _cell(e.get("note")),
    ] for e in entries]
    return _table(["日付", "獲得（入団）", "相手球団", "放出（退団）", "区分・備考"], rows)


def _render_topics(data) -> str:
    ex = data.get("trades_exchange") or []
    if not ex:
        return ""
    latest = ex[:5]
    items = []
    for e in latest:
        ins = "・".join(p.get("name", "") for p in (e.get("in_players") or [])) or "—"
        outs = "・".join(p.get("name", "") for p in (e.get("out_players") or [])) or "—"
        items.append(f'<li style="margin:0 0 4px;">{_esc(e.get("date"))} '
                     f'<strong>{_esc(ins)}</strong> ⇔ {_esc(outs)}'
                     f'（{_esc(e.get("partner"))}）</li>')
    return ('<section style="background:#fff8e1;border-left:3px solid #f57f17;'
            'padding:12px 16px;border-radius:4px;margin:0 0 18px;">'
            '<h2 style="font-size:15px;margin:0 0 8px;color:#5d4037;">📌 トピックス（直近の交換トレード）</h2>'
            f'<ul style="font-size:13px;line-height:1.6;margin:0;padding-left:18px;color:#444;">{"".join(items)}</ul>'
            '</section>')


def render_trade_title() -> str:
    return "巨人 トレード・移籍・入退団 一覧【歴代】 | 巨人データ"


def render_trade_excerpt(data) -> str:
    ne = len(data.get("trades_exchange") or [])
    return (f"読売ジャイアンツの歴代トレード（交換{ne}件）と、FA移籍・自由契約・戦力外・現役ドラフトを含む"
            "入団/退団の動きを巨人専用にまとめたデータベース。獲得・放出選手と相手球団を一覧化。")


def render_trade_html(data: dict | None = None) -> str:
    data = data if data is not None else load_trade_data()
    nav = ('<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
           f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
           f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>トレード/移籍</span></nav>')
    jump = ('<div style="margin:0 0 14px;">'
            '<a href="#exchange" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
            'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">🔄 交換トレード</a>'
            '<a href="#all" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
            'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">📋 入団・移籍・退団</a>'
            '</div>')
    src_note = ('<p style="font-size:11px;color:#999;margin:0 0 14px;line-height:1.6;">'
                '出典: 公開資料の事実テーブル。選手名・守備位置は移籍時点のもの。'
                f'{("最終更新: " + _esc(data.get("updated")) if data.get("updated") else "")}</p>')
    sections = [
        _section_shell("exchange", "① 交換トレード一覧",
                       "選手⇔選手の交換トレード（新しい順）。",
                       _render_exchange(data.get("trades_exchange") or []),
                       len(data.get("trades_exchange") or [])),
        _section_shell("all", "② 入団・移籍・退団一覧",
                       "FA移籍・自由契約・戦力外・現役ドラフト・トレードを含む全ての動き（新しい順）。",
                       _render_all(data.get("transactions_all") or []),
                       len(data.get("transactions_all") or [])),
    ]
    return ('<div style="font-family:sans-serif;max-width:860px;">'
            f'{nav}'
            '<h1 style="font-size:20px;margin:0 0 4px;">巨人 トレード・移籍データベース</h1>'
            '<p style="font-size:13px;color:#666;margin:0 0 12px;">'
            '読売ジャイアンツの歴代トレードと、FA移籍・自由契約・戦力外・現役ドラフトを含む入退団の動きを'
            '巨人専用に1ページでまとめます。</p>'
            f'{src_note}{_render_topics(data)}{jump}' + "".join(sections)
            + f'<p style="margin-top:20px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
            '</div>')


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.write(render_trade_html())
