"""data/team ページ template (球団成績・セ内順位、Phase B 452)。

セ・リーグ6球団の 打率/防御率/本塁打 ランキングを巨人ハイライトで表示。
検証済み team_ranking_publisher の集計を data_site_query.fetch_team_rankings 経由で利用。
SEO: 「巨人 球団打率 順位」「セ・リーグ 防御率 ランキング」等。
"""

from __future__ import annotations

import html as _html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"
_METRIC_ORDER = ["打率", "本塁打", "防御率"]


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


def render_team_title() -> str:
    return "巨人 球団成績・セ・リーグ順位 2026【打率・防御率・本塁打】 | 巨人データ"


def render_team_excerpt(rankings: dict) -> str:
    parts = []
    for m in _METRIC_ORDER:
        for tj, disp, rk, is_g in rankings.get(m, []):
            if is_g:
                parts.append(f"{m}セ{rk}位")
                break
    head = "・".join(parts) if parts else "球団成績"
    return (f"読売ジャイアンツ2026の球団成績とセ・リーグ内順位。{head}。"
            "打率・本塁打・防御率を6球団で比較した巨人専用のチームデータ。")


def _rank_block(metric: str, rows: list) -> str:
    if not rows:
        return ""
    body = "".join(
        '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
        f'border-bottom:1px solid #f0f0f0;{"background:#fff3e0;font-weight:700;" if is_g else ""}">'
        f'<span style="width:24px;color:#888;text-align:center;">{rk}</span>'
        f'<span style="flex:1;">{_esc(tj)}{"（巨人）" if is_g else ""}</span>'
        f'<span style="color:#c0392b;font-weight:700;">{_esc(disp)}</span></div>'
        for (tj, disp, rk, is_g) in rows
    )
    return (
        '<section class="ys-card" style="margin:0 0 14px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">セ・リーグ 球団{_esc(metric)} ランキング</h2>'
        f'{body}</section>'
    )


def _build_team_record_card(rec: dict) -> str:
    """巨人 チーム成績カード (459、 games 由来)。 順位/GB は standings 未populate のため非掲載。"""
    if not rec or (rec.get("wins", 0) + rec.get("losses", 0) + rec.get("draws", 0)) == 0:
        return ""
    wp = rec.get("win_pct")
    wp_s = (f"{wp:.3f}"[1:] if (wp is not None and wp < 1) else (f"{wp:.3f}" if wp is not None else "-"))
    rd = rec.get("run_diff", 0)
    rd_s = f"+{rd}" if rd > 0 else str(rd)
    kind, n = rec.get("streak_kind", ""), rec.get("streak", 0)
    streak_s = (f"{n}連勝" if kind == "W" else (f"{n}連敗" if kind == "L" else "-"))
    hw, hl = rec.get("home", (0, 0))
    aw, al = rec.get("away", (0, 0))
    td = 'style="padding:6px;"'
    tdb = 'style="padding:6px;font-weight:600;"'
    return (
        '<div style="background:#fff;border:1px solid #ffe0cc;border-radius:12px;padding:16px;margin:0 0 16px;">'
        '<h2 style="font-size:16px;margin:0 0 10px;">巨人 チーム成績 '
        '<span style="font-size:11px;color:#e25400;">毎日更新</span></h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;text-align:center;"><tbody>'
        f'<tr><td {td}>勝-敗-分</td><td {tdb}>{rec["wins"]}-{rec["losses"]}-{rec["draws"]}</td>'
        f'<td {td}>勝率</td><td {tdb}>{wp_s}</td></tr>'
        f'<tr><td {td}>得点-失点</td><td {td}>{rec["runs_for"]}-{rec["runs_against"]}</td>'
        f'<td {td}>得失点差</td><td {tdb}>{rd_s}</td></tr>'
        f'<tr><td {td}>連勝/連敗</td><td {td}>{streak_s}</td>'
        f'<td {td}>本拠地/ビジター</td><td {td}>{hw}勝{hl}敗 / {aw}勝{al}敗</td></tr>'
        '</tbody></table></div>'
    )


def render_team_html(rankings: dict, team_record: dict = None) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>球団成績</span></nav>'
    )
    blocks = "".join(_rank_block(m, rankings.get(m) or []) for m in _METRIC_ORDER)
    record_card = _build_team_record_card(team_record or {})
    return (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 球団成績・セ・リーグ順位 2026</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;">巨人のチーム成績と、セ・リーグ6球団の打率・本塁打・防御率ランキング。</p>'
        f'{record_card}'
        f'{blocks or "<p>データ準備中</p>"}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )
