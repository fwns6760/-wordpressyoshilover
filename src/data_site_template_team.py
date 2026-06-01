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


def render_team_html(rankings: dict) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>球団成績</span></nav>'
    )
    blocks = "".join(_rank_block(m, rankings.get(m) or []) for m in _METRIC_ORDER)
    return (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 球団成績・セ・リーグ順位 2026</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;">セ・リーグ6球団の打率・本塁打・防御率ランキング。巨人をハイライト。</p>'
        f'{blocks or "<p>データ準備中</p>"}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )
