"""data/draft ページ template（巨人ドラフト史 hub）。

ベンチ: my-favorite-giants.net/giants_data/draft/lot.htm の「ドラフト指名/育成/外/競合/スカウト/契約変更」を
巨人特化の 1 hub にまとめる。データ正本は config/giants_draft_history.json（事実のみ・推測で埋めない）。

セクション（user 指定の全 7 枠 + トピックス）:
  1. ドラフト指名選手一覧（年度別・支配下）
  2. 育成ドラフト指名選手一覧
  3. ドラフト外入団選手一覧
  4. 指名競合選手一覧（外れ1位含む / lot.htm 相当）
  5. スカウト名簿
  6. OBスカウト名簿
  7. 契約変更選手一覧
データ未整備のセクションは「準備中」表示（空セクションでも枠は出す = user 確定方針 2026-06-05）。

公開ゲート: 全年代（1965-2024）整備完了まで本番非公開。publisher 側 ENABLE_DATA_SITE_DRAFT で点灯。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os

from src.data_site_internal_link import linkify, roster_moves_nav, breadcrumb_jsonld

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"

_DATA_PATH = _os.path.join(_os.path.dirname(__file__), "..", "config", "giants_draft_history.json")


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_draft_data() -> dict:
    """config/giants_draft_history.json を読む。失敗時は空 dict。"""
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return {}


# ---- 共通パーツ ----

def _cell(v) -> str:
    s = _esc(v).strip()
    return s if s else "—"


def _section_shell(anchor: str, title: str, lead: str, body_html: str, count: int) -> str:
    cnt = (f'<span style="font-size:12px;color:#888;font-weight:normal;">{count}件</span>'
           if count else '<span style="font-size:12px;color:#bbb;font-weight:normal;">準備中</span>')
    return (
        f'<h2 id="{anchor}" style="font-size:17px;margin:26px 0 6px;border-left:4px solid #5d4037;'
        f'padding-left:8px;">{_esc(title)} {cnt}</h2>'
        f'<p style="font-size:12px;color:#777;margin:0 0 8px;">{_esc(lead)}</p>'
        f'{body_html}'
    )


def _todo_box(msg: str) -> str:
    return (
        '<div style="background:#fafafa;border:1px dashed #ccc;border-radius:4px;'
        'padding:14px 16px;color:#999;font-size:13px;margin:0 0 8px;">'
        f'🚧 {_esc(msg)}</div>'
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    th = "".join(
        f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid #5d4037;'
        f'font-size:12px;color:#5d4037;white-space:nowrap;">{_esc(h)}</th>' for h in headers
    )
    trs = []
    for i, r in enumerate(rows):
        bg = "#fff" if i % 2 == 0 else "#fcf9f4"
        tds = "".join(
            f'<td style="padding:6px 8px;border-bottom:1px solid #eee;font-size:13px;">{c}</td>'
            for c in r
        )
        trs.append(f'<tr style="background:{bg};">{tds}</tr>')
    return (
        '<div style="overflow-x:auto;margin:0 0 8px;"><table style="border-collapse:collapse;'
        'width:100%;min-width:480px;">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
    )


def _group_by_year_desc(entries: list[dict]) -> list[tuple[int, list[dict]]]:
    groups: dict[int, list[dict]] = {}
    for e in entries:
        try:
            y = int(e.get("year"))
        except (TypeError, ValueError):
            continue
        groups.setdefault(y, []).append(e)
    return sorted(groups.items(), key=lambda kv: kv[0], reverse=True)


def _round_sort_key(r: str) -> tuple[int, str]:
    """巡目文字列を昇順ソート（'1位'→1, '育成1位'→1）。数字が取れなければ末尾。"""
    digits = "".join(ch for ch in str(r) if ch.isdigit())
    return (int(digits) if digits else 999, str(r))


# ---- セクション 1: 支配下ドラフト指名 ----

def _render_draft_picks(entries: list[dict]) -> str:
    if not entries:
        return _todo_box("年度別の支配下ドラフト指名選手を 1965〜2024 まで順次整備中です。")
    blocks = []
    for year, items in _group_by_year_desc(entries):
        items = sorted(items, key=lambda e: _round_sort_key(e.get("round", "")))
        rows = []
        for e in items:
            mark = ' <span style="color:#e25400;font-size:11px;">（抽選）</span>' if e.get("competed") else ""
            rows.append([
                _esc(e.get("round")) + mark,
                f'<strong>{linkify(e.get("name"))}</strong>',
                _cell(e.get("pos")),
                _cell(e.get("from")),
                _cell(e.get("note")),
            ])
        blocks.append(
            f'<h3 style="font-size:14px;margin:14px 0 4px;color:#444;">{year}年</h3>'
            + _table(["巡目", "選手名", "守備位置", "所属（指名時）", "備考"], rows)
        )
    return "".join(blocks)


# ---- セクション 2: 育成ドラフト ----

def _render_ikusei(entries: list[dict]) -> str:
    if not entries:
        return _todo_box("年度別の育成ドラフト指名選手を順次整備中です。")
    blocks = []
    for year, items in _group_by_year_desc(entries):
        items = sorted(items, key=lambda e: _round_sort_key(e.get("round", "")))
        rows = [[
            _esc(e.get("round")),
            f'<strong>{linkify(e.get("name"))}</strong>',
            _cell(e.get("pos")),
            _cell(e.get("from")),
            _cell(e.get("note")),
        ] for e in items]
        blocks.append(
            f'<h3 style="font-size:14px;margin:14px 0 4px;color:#444;">{year}年</h3>'
            + _table(["巡目", "選手名", "守備位置", "所属（指名時）", "備考"], rows)
        )
    return "".join(blocks)


# ---- セクション 3: ドラフト外入団 ----

def _render_non_draft(entries: list[dict]) -> str:
    if not entries:
        return _todo_box("ドラフト外入団選手（制度のあった年代）を順次整備中です。")
    rows = []
    for year, items in _group_by_year_desc(entries):
        for e in items:
            rows.append([
                str(year),
                f'<strong>{linkify(e.get("name"))}</strong>',
                _cell(e.get("pos")),
                _cell(e.get("from")),
                _cell(e.get("note")),
            ])
    return _table(["年", "選手名", "守備位置", "所属（入団時）", "備考"], rows)


# ---- セクション 4: 指名競合・外れ1位（lot.htm 相当） ----

def _render_lottery(entries: list[dict]) -> str:
    if not entries:
        return _todo_box("指名競合・外れ1位一覧（1965〜2024）を順次整備中です。"
                         "本セクションがベンチマーク（指名競合選手一覧）の中核です。")
    rows = []
    for year, items in _group_by_year_desc(entries):
        items = sorted(items, key=lambda e: _round_sort_key(e.get("round", "")))
        for e in items:
            comps = e.get("competitors") or []
            comp_txt = "、".join(_esc(c) for c in comps) if comps else "—"
            result = _esc(e.get("result"))
            res_html = (f'<span style="color:#2e7d32;font-weight:700;">○</span>' if result == "○"
                        else f'<span style="color:#c62828;font-weight:700;">×</span>' if result == "×"
                        else "—")
            miss = e.get("miss_name")
            miss_html = (f'{linkify(miss)}<span style="color:#999;font-size:11px;">'
                         f'（{_cell(e.get("miss_pos"))}・{_cell(e.get("miss_from"))}）</span>'
                         if miss else "—")
            rows.append([
                str(year),
                _esc(e.get("round")),
                f'<strong>{linkify(e.get("name"))}</strong>',
                _cell(e.get("pos")),
                comp_txt,
                res_html,
                miss_html,
            ])
    note = ('<p style="font-size:11px;color:#999;margin:0 0 6px;">'
            '○=交渉権獲得 / ×=抽選外れ → 外れ指名選手へ。守備位置・所属は指名時のもの。</p>')
    return note + _table(
        ["年", "巡目", "指名選手", "位置", "競合球団", "結果", "外れ指名選手"], rows)


# ---- セクション 5: スカウト名簿 ----

def _render_scouts(entries: list[dict]) -> str:
    if not entries:
        return _todo_box("現役スカウト名簿を整備中です。")
    rows = [[
        f'<strong>{linkify(e.get("name"))}</strong>',
        _cell(e.get("title")),
        _cell(e.get("area")),
        _cell(e.get("note")),
    ] for e in entries]
    return _table(["氏名", "役職", "担当", "備考"], rows)


# ---- セクション 6: OBスカウト名簿 ----

def _render_ob_scouts(entries: list[dict]) -> str:
    if not entries:
        return _todo_box("OBスカウト名簿（元巨人選手のスカウト）を整備中です。")
    rows = [[
        f'<strong>{linkify(e.get("name"))}</strong>',
        _cell(e.get("ob_career")),
        _cell(e.get("title")),
        _cell(e.get("area")),
        _cell(e.get("note")),
    ] for e in entries]
    return _table(["氏名", "現役時代", "役職", "担当", "備考"], rows)


# ---- セクション 7: 契約変更選手 ----

def _render_contract_changes(entries: list[dict]) -> str:
    if not entries:
        return _todo_box("契約変更選手一覧（支配下↔育成 等）を整備中です。")
    rows = []
    for year, items in _group_by_year_desc(entries):
        for e in items:
            rows.append([
                _cell(e.get("date") or year),
                f'<strong>{linkify(e.get("name"))}</strong>',
                _cell(e.get("change")),
                _cell(e.get("note")),
            ])
    return _table(["契約変更日", "選手名", "変更内容", "備考"], rows)


# ---- トピックス（小） ----

def _render_topics(data: dict) -> str:
    """簡易ハイライト: 直近年度の1位指名など。データから自動生成（捏造しない）。"""
    picks = data.get("draft_picks") or []
    firsts = [e for e in picks if str(e.get("round", "")).strip() == "1位"]
    if not firsts:
        return ""
    firsts = sorted(firsts, key=lambda e: int(e.get("year", 0)), reverse=True)[:5]
    items = "".join(
        f'<li style="margin:0 0 4px;">{_esc(e.get("year"))}年 1位 '
        f'<strong>{linkify(e.get("name"))}</strong>'
        f'{("（抽選）" if e.get("competed") else "")}</li>'
        for e in firsts
    )
    return (
        '<section style="background:#fff8e1;border-left:3px solid #f57f17;'
        'padding:12px 16px;border-radius:4px;margin:0 0 18px;">'
        '<h2 style="font-size:15px;margin:0 0 8px;color:#5d4037;">📌 トピックス（直近の1位指名）</h2>'
        f'<ul style="font-size:13px;line-height:1.6;margin:0;padding-left:18px;color:#444;">{items}</ul>'
        '</section>'
    )


# ---- ページ全体 ----

def render_draft_title() -> str:
    return "巨人 歴代ドラフト指名選手一覧【1位・育成・外れ1位・競合】 | 巨人データ"


def render_draft_excerpt(data: dict) -> str:
    n = len(data.get("draft_picks") or []) + len(data.get("ikusei_picks") or [])
    return ("読売ジャイアンツの歴代ドラフト指名選手を巨人専用にまとめたデータベース。"
            "支配下・育成・ドラフト外入団・指名競合（外れ1位）・スカウト名簿・契約変更まで網羅。"
            f"現在{n}件を掲載、1965〜2024年を順次整備中。")


_NAV_LINKS = [
    ("draft", "🟦 ドラフト指名選手"),
    ("ikusei", "🟩 育成ドラフト"),
    ("non-draft", "⬜ ドラフト外入団"),
    ("lottery", "🎯 指名競合・外れ1位"),
    ("scouts", "🔍 スカウト名簿"),
    ("ob-scouts", "👔 OBスカウト名簿"),
    ("contract", "🔁 契約変更選手"),
]


def render_draft_html(data: dict | None = None) -> str:
    data = data if data is not None else load_draft_data()
    updated = _esc(data.get("updated") or "")

    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>歴代ドラフト</span></nav>'
    )

    jump = '<div style="margin:0 0 14px;">' + "".join(
        f'<a href="#{a}" style="display:inline-block;padding:5px 10px;margin:2px;border:1px solid #ffcc80;'
        f'border-radius:14px;color:#e65100;text-decoration:none;font-size:12px;font-weight:600;">{_esc(label)}</a>'
        for a, label in _NAV_LINKS
    ) + "</div>"

    src_note = (
        '<p style="font-size:11px;color:#999;margin:0 0 14px;line-height:1.6;">'
        '出典: NPB公式ドラフト会議結果 / Wikipedia 年度別ドラフト指名選手。'
        '守備位置・所属はドラフト指名時のもの。'
        f'{("最終更新: " + updated if updated else "")}</p>'
    )

    sections = [
        _section_shell("draft", "① ドラフト指名選手一覧（支配下）",
                       "年度別の支配下ドラフト指名。1位の抽選競合は（抽選）表記。",
                       _render_draft_picks(data.get("draft_picks") or []),
                       len(data.get("draft_picks") or [])),
        _section_shell("ikusei", "② 育成ドラフト指名選手一覧",
                       "育成枠でのドラフト指名選手。",
                       _render_ikusei(data.get("ikusei_picks") or []),
                       len(data.get("ikusei_picks") or [])),
        _section_shell("non-draft", "③ ドラフト外入団選手一覧",
                       "ドラフト外入団制度のあった年代の入団選手。",
                       _render_non_draft(data.get("non_draft") or []),
                       len(data.get("non_draft") or [])),
        _section_shell("lottery", "④ 指名競合選手一覧（外れ1位）",
                       "1位指名の抽選競合と、外れ1位の流れ。ベンチマークの中核。",
                       _render_lottery(data.get("lottery") or []),
                       len(data.get("lottery") or [])),
        _section_shell("scouts", "⑤ スカウト名簿",
                       "現役スカウトの担当・役職。",
                       _render_scouts(data.get("scouts") or []),
                       len(data.get("scouts") or [])),
        _section_shell("ob-scouts", "⑥ OBスカウト名簿",
                       "元巨人選手としてのキャリアを持つスカウト。",
                       _render_ob_scouts(data.get("ob_scouts") or []),
                       len(data.get("ob_scouts") or [])),
        _section_shell("contract", "⑦ 契約変更選手一覧",
                       "支配下↔育成などの契約変更履歴。",
                       _render_contract_changes(data.get("contract_changes") or []),
                       len(data.get("contract_changes") or [])),
    ]

    return (
        breadcrumb_jsonld("巨人 歴代ドラフト", "draft")
        + '<div style="font-family:sans-serif;max-width:820px;">'
        f'{nav}'
        + roster_moves_nav("draft")
        + '<h1 style="font-size:20px;margin:0 0 4px;">巨人 歴代ドラフト指名選手データベース</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 12px;">'
        '読売ジャイアンツの歴代ドラフト指名（支配下・育成・ドラフト外）、指名競合と外れ1位、'
        'スカウト名簿、契約変更までを巨人専用に1ページでまとめます。1965〜2024年を順次整備中。</p>'
        f'{src_note}'
        f'{_render_topics(data)}'
        f'{jump}'
        + "".join(sections)
        + f'<p style="margin-top:20px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )


if __name__ == "__main__":  # 手動プレビュー: python -m src.data_site_template_draft > /tmp/draft.html
    import sys as _sys
    _sys.stdout.write(render_draft_html())
