"""data/fa ページ template（巨人FA hub）。

ベンチ: my-favorite-giants.net/giants_data/player/fa.htm（FA獲得選手）/ fa-right.htm（FA有資格選手）。
データ正本は config/giants_fa.json（事実のみ）。

セクション:
  1. FA獲得選手一覧（球団がFAで獲得した選手・前所属・在籍年・タイトル）
  2. FA有資格選手一覧（出典スナップショット asof 年時点・ポジション別）
データ未整備は「準備中」表示。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os

from src.data_site_internal_link import linkify, roster_moves_nav, breadcrumb_jsonld

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"

_DATA_PATH = _os.path.join(_os.path.dirname(__file__), "..", "config", "giants_fa.json")
_POS_ORDER = ["投手", "捕手", "内野手", "外野手"]


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_fa_data() -> dict:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _cell(v) -> str:
    s = _esc(v).strip()
    return s if s else "—"


def _todo_box(msg: str) -> str:
    return ('<div style="background:#fafafa;border:1px dashed #ccc;border-radius:4px;'
            'padding:14px 16px;color:#999;font-size:13px;margin:0 0 8px;">🚧 ' + _esc(msg) + '</div>')


def _table(headers, rows) -> str:
    if not rows:
        return ""
    th = "".join(f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #5d4037;'
                 f'font-size:12px;color:#5d4037;white-space:nowrap;">{_esc(h)}</th>' for h in headers)
    trs = []
    for i, r in enumerate(rows):
        bg = "#fff" if i % 2 == 0 else "#fcf9f4"
        tds = "".join(f'<td style="padding:6px 8px;border-bottom:1px solid #eee;font-size:13px;">{c}</td>'
                      for c in r)
        trs.append(f'<tr style="background:{bg};">{tds}</tr>')
    return ('<div style="overflow-x:auto;margin:0 0 8px;"><table style="border-collapse:collapse;'
            'width:100%;min-width:480px;">'
            f'<thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>')


def _section_shell(anchor, title, lead, body_html, count) -> str:
    cnt = (f'<span style="font-size:12px;color:#888;font-weight:normal;">{count}件</span>'
           if count else '<span style="font-size:12px;color:#bbb;font-weight:normal;">準備中</span>')
    return (f'<h2 id="{anchor}" style="font-size:17px;margin:26px 0 6px;border-left:4px solid #5d4037;'
            f'padding-left:8px;">{_esc(title)} {cnt}</h2>'
            f'<p style="font-size:12px;color:#777;margin:0 0 8px;">{_esc(lead)}</p>{body_html}')


def _render_acquisitions(entries) -> str:
    if not entries:
        return _todo_box("FA獲得選手を整備中です。")
    # FA年降順（新しい順）
    def _yr(e):
        import re
        m = re.search(r"\d{4}", e.get("fa_year", "") or "")
        return int(m.group(0)) if m else 0
    entries = sorted(entries, key=_yr, reverse=True)
    rows = [[
        _cell(e.get("fa_year")),
        f'<strong>{linkify(e.get("name"))}</strong>',
        _cell(e.get("pos")),
        _cell(e.get("prev_team")),
        _cell(e.get("join_year")),
        _cell(e.get("period")),
        _cell(e.get("titles")),
    ] for e in entries]
    return _table(["FA年", "選手名", "守備位置", "前所属", "加入年度", "在籍期間", "巨人での主なタイトル"], rows)


def _render_eligible(entries, asof: str) -> str:
    if not entries:
        return _todo_box("FA有資格選手を整備中です。")
    note = (f'<p style="font-size:11px;color:#999;margin:0 0 6px;">'
            f'※ 出典スナップショット（{_esc(asof) if asof else "—"}年時点）。FA権利は年により変動します。</p>')
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(e.get("group") or "その他", []).append(e)
    order = [g for g in _POS_ORDER if g in groups] + [g for g in groups if g not in _POS_ORDER]
    blocks = []
    for g in order:
        rows = [[
            _cell(e.get("back_no")),
            f'<strong>{linkify(e.get("name"))}</strong>',
            _cell(e.get("age")),
            _cell(e.get("tenure_years")),
            _cell(e.get("right_type")),
            _cell(e.get("status")),
            _cell(e.get("note")),
        ] for e in groups[g]]
        blocks.append(
            f'<h3 style="font-size:14px;margin:14px 0 4px;color:#444;">{_esc(g)}'
            f' <span style="font-size:12px;color:#888;font-weight:normal;">{len(groups[g])}名</span></h3>'
            + _table(["背番号", "選手名", "年齢", "在籍年", "種別", "権利状態", "備考"], rows))
    return note + "".join(blocks)


def _render_topics(data) -> str:
    acq = data.get("fa_acquisitions") or []
    if not acq:
        return ""
    import re
    def _yr(e):
        m = re.search(r"\d{4}", e.get("fa_year", "") or "")
        return int(m.group(0)) if m else 0
    latest = sorted(acq, key=_yr, reverse=True)[:5]
    items = "".join(f'<li style="margin:0 0 4px;">{_esc(e.get("fa_year"))} '
                    f'<strong>{linkify(e.get("name"))}</strong>'
                    f'（前所属: {_esc(e.get("prev_team"))}）</li>' for e in latest)
    return ('<section style="background:#fff8e1;border-left:3px solid #f57f17;'
            'padding:12px 16px;border-radius:4px;margin:0 0 18px;">'
            '<h2 style="font-size:15px;margin:0 0 8px;color:#5d4037;">📌 トピックス（直近のFA獲得）</h2>'
            f'<ul style="font-size:13px;line-height:1.6;margin:0;padding-left:18px;color:#444;">{items}</ul>'
            '</section>')


def render_fa_title() -> str:
    return "巨人 FA獲得選手・FA有資格選手 一覧【歴代】 | 巨人データ"


def render_fa_excerpt(data) -> str:
    n = len(data.get("fa_acquisitions") or [])
    return (f"読売ジャイアンツが歴代FAで獲得した選手{n}名（落合博満・清原和博・工藤公康ほか）と、"
            "FA有資格選手の一覧を巨人専用にまとめたデータベース。前所属・在籍期間・タイトルまで掲載。")


def render_fa_html(data: dict | None = None) -> str:
    data = data if data is not None else load_fa_data()
    asof = _esc(data.get("fa_eligible_asof") or "")
    nav = ('<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
           f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
           f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>FA選手</span></nav>')
    jump = ('<div style="margin:0 0 14px;">'
            '<a href="#acq" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
            'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">🤝 FA獲得選手</a>'
            '<a href="#elig" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
            'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">📝 FA有資格選手</a>'
            '</div>')
    src_note = ('<p style="font-size:11px;color:#999;margin:0 0 14px;line-height:1.6;">'
                '出典: 公開資料の事実テーブル。FA有資格選手は出典の最新スナップショット。'
                f'{("最終更新: " + _esc(data.get("updated")) if data.get("updated") else "")}</p>')
    sections = [
        _section_shell("acq", "① FA獲得選手一覧",
                       "読売ジャイアンツがFA制度で獲得した選手。前所属・在籍期間・タイトル。",
                       _render_acquisitions(data.get("fa_acquisitions") or []),
                       len(data.get("fa_acquisitions") or [])),
        _section_shell("elig", "② FA有資格選手一覧",
                       "FA権利を保有/取得見込みの選手（出典スナップショット）。",
                       _render_eligible(data.get("fa_eligible") or [], asof),
                       len(data.get("fa_eligible") or [])),
    ]
    return (breadcrumb_jsonld("巨人 FA選手", "fa")
            + '<div style="font-family:sans-serif;max-width:820px;">'
            f'{nav}'
            + roster_moves_nav("fa")
            + '<h1 style="font-size:20px;margin:0 0 4px;">巨人 FA選手データベース</h1>'
            '<p style="font-size:13px;color:#666;margin:0 0 12px;">'
            '読売ジャイアンツが歴代FAで獲得した選手と、FA有資格選手を巨人専用に1ページでまとめます。</p>'
            f'{src_note}{_render_topics(data)}{jump}' + "".join(sections)
            + f'<p style="margin-top:20px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
            '</div>')


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.write(render_fa_html())
